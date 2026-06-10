"""Ingesta de hallazgos de seguridad → ledger `SecurityFinding` (rebanada B-2).

Parsea los reports de los scanners de dependencias (pip-audit / npm-audit, que ya
producen JSON y ya están gobernados por `qa/contracts/security_exceptions.json`),
aplica el contrato de excepciones **con vencimiento** y hace upsert determinista en el
ledger, deduplicando por (source_tool, package, vuln_id). Respeta el triage humano:
la re-ingesta solo recalcula estados automáticos (open/accepted_risk/fixed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.utils import timezone

from .domain_map import domain_for_path, risk_class_for_domain
from .models import AUTO_FINDING_STATES, FindingStatus, RiskClass, SecurityFinding


@dataclass(frozen=True)
class RawFinding:
    source_tool: str
    vuln_id: str
    package: str = ""
    package_version: str = ""
    fixed_version: str = ""
    cve_id: str = ""
    severity_raw: str = ""
    # Campos SAST (vacíos para dependencias pip/npm).
    file_path: str = ""
    line_start: int = 0
    symbol: str = ""
    domain: str = ""
    cwe_id: str = ""
    # Riesgo precomputado por el parser (p.ej. SAST dominio-aware). Vacío => se deriva de la severidad.
    risk_class: str = ""


@dataclass(frozen=True)
class ExceptionRule:
    source: str
    package: str
    vuln_id: str
    expires_on: date
    reason: str = ""


@dataclass
class IngestResult:
    created: int = 0
    updated: int = 0
    resolved: int = 0
    sources: list[str] = field(default_factory=list)


# --- Parsing de reports ---------------------------------------------------------

def parse_pip_findings(payload: dict[str, Any]) -> list[RawFinding]:
    """pip-audit: dependencies[].vulns[] (id, severity[].score>=7, fix_versions)."""
    out: list[RawFinding] = []
    for dep in payload.get("dependencies") or []:
        if not isinstance(dep, dict):
            continue
        pkg = str(dep.get("name", "")).strip()
        version = str(dep.get("version", "")).strip()
        for vuln in dep.get("vulns") or []:
            if not isinstance(vuln, dict):
                continue
            vuln_id = str(vuln.get("id", "")).strip()
            if not vuln_id:
                continue
            severity = "high_or_critical" if _pip_is_high_or_critical(vuln) else "low"
            fix_versions = vuln.get("fix_versions") or []
            out.append(
                RawFinding(
                    source_tool="pip",
                    vuln_id=vuln_id,
                    package=pkg,
                    package_version=version,
                    fixed_version=str(fix_versions[0]) if fix_versions else "",
                    cve_id=vuln_id if vuln_id.upper().startswith("CVE-") else "",
                    severity_raw=severity,
                )
            )
    return out


def _pip_is_high_or_critical(vuln: dict[str, Any]) -> bool:
    for entry in vuln.get("severity") or []:
        if not isinstance(entry, dict):
            continue
        score = entry.get("score")
        if score is None:
            continue
        try:
            if float(score) >= 7.0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def parse_npm_findings(payload: dict[str, Any]) -> list[RawFinding]:
    """npm audit: vulnerabilities{pkg:{severity, fixAvailable, via[].source}}."""
    out: list[RawFinding] = []
    vulns = payload.get("vulnerabilities")
    if not isinstance(vulns, dict):
        return out
    for pkg, info in vulns.items():
        if not isinstance(info, dict):
            continue
        severity = str(info.get("severity", "")).lower()
        ids: set[str] = set()
        for via in info.get("via") or []:
            if isinstance(via, dict) and via.get("source") is not None:
                ids.add(str(via["source"]))
        if not ids:
            ids.add(str(pkg))
        fix = info.get("fixAvailable")
        fixed_version = ""
        if isinstance(fix, dict):
            fixed_version = str(fix.get("version", ""))
        elif fix is True:
            fixed_version = "available"
        for vuln_id in sorted(ids):
            out.append(
                RawFinding(
                    source_tool="npm",
                    vuln_id=vuln_id,
                    package=str(pkg),
                    fixed_version=fixed_version,
                    severity_raw=severity,
                )
            )
    return out


def _normalize_sast_path(path: str) -> str:
    """Path repo-relativo estable: quita el prefijo del contenedor (`/app/`) y barras iniciales."""
    p = (path or "").replace("\\", "/")
    marker = "/app/"
    idx = p.find(marker)
    if idx != -1:
        return p[idx + len(marker):]
    return p.lstrip("/")


def parse_bandit_findings(payload: dict[str, Any]) -> list[RawFinding]:
    """bandit -f json: `results[]` (test_id, filename, line_number, issue_severity, issue_cwe).

    Es SAST sobre NUESTRO código (alcanzable), así que el riesgo es **dominio-aware**
    (`risk_for_sast`): un hallazgo severo en un dominio C1 (dinero/fiscal) es C1, no C2.
    Dedup por (archivo, test, línea): `vuln_id="<test_id>:<line>"`, `package=<archivo>` (locus
    para la clave natural). Los campos estructurados (file_path/line_start/symbol/domain) van
    aparte para consulta y display.
    """
    out: list[RawFinding] = []
    for r in payload.get("results") or []:
        if not isinstance(r, dict):
            continue
        test_id = str(r.get("test_id", "")).strip()
        filename = _normalize_sast_path(str(r.get("filename", "")).strip())
        if not test_id or not filename:
            continue
        try:
            line = int(r.get("line_number") or 0)
        except (TypeError, ValueError):
            line = 0
        severity = str(r.get("issue_severity", "")).lower()
        symbol = str(r.get("test_name", ""))[:255]
        cwe = ""
        cwe_obj = r.get("issue_cwe")
        if isinstance(cwe_obj, dict) and cwe_obj.get("id") not in (None, ""):
            cwe = f"CWE-{cwe_obj['id']}"
        domain = domain_for_path(filename)
        out.append(
            RawFinding(
                source_tool="bandit",
                vuln_id=f"{test_id}:{line}",
                package=filename,
                severity_raw=severity,
                file_path=filename,
                line_start=line,
                symbol=symbol,
                domain=domain,
                cwe_id=cwe,
                risk_class=risk_for_sast(severity, domain),
            )
        )
    return out


def load_exceptions(payload: dict[str, Any]) -> list[ExceptionRule]:
    rules: list[ExceptionRule] = []
    for row in payload.get("exceptions") or []:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source", "")).strip().lower()
        package = str(row.get("package", "")).strip()
        vuln_id = str(row.get("vuln_id", "")).strip()
        raw_exp = str(row.get("expires_on", "")).strip()
        if not (source and package and vuln_id and raw_exp):
            continue
        try:
            exp = date.fromisoformat(raw_exp)
        except ValueError:
            continue
        rules.append(
            ExceptionRule(
                source=source,
                package=package,
                vuln_id=vuln_id,
                expires_on=exp,
                reason=str(row.get("reason", "")).strip()[:255],
            )
        )
    return rules


# --- Clasificación + excepciones ------------------------------------------------

def risk_for_severity(severity_raw: str) -> str:
    """Sin reachability confirmada, una vuln de dependencia high/critical es C2 (no C1)."""
    s = (severity_raw or "").lower()
    if s in {"high", "critical", "high_or_critical"}:
        return RiskClass.C2
    return RiskClass.C3


def risk_for_sast(severity_raw: str, domain: str) -> str:
    """Riesgo de un hallazgo SAST (bandit). A diferencia de una dependencia, es **nuestro**
    código (alcanzable), así que el **dominio manda**: un hallazgo severo en un dominio C1
    (dinero/fiscal) es C1. La severidad modula: `low` es C3; `medium` no escala a C1 (baja a C2).
    """
    sev = (severity_raw or "").lower()
    if sev == "low":
        return RiskClass.C3
    domain_risk = risk_class_for_domain(domain)  # C1/C2/C3 según dónde vive el código
    if sev == "high":
        return domain_risk
    # medium: no escalar a C1 automático.
    return RiskClass.C2 if domain_risk == RiskClass.C1 else domain_risk


def _matching_exception(
    finding: RawFinding, exceptions: list[ExceptionRule]
) -> ExceptionRule | None:
    for rule in exceptions:
        if rule.source != finding.source_tool:
            continue
        if rule.vuln_id != finding.vuln_id:
            continue
        if rule.package in {"*", finding.package}:
            return rule
    return None


def _status_for(
    finding: RawFinding, exceptions: list[ExceptionRule], today: date
) -> tuple[str, date | None, str]:
    rule = _matching_exception(finding, exceptions)
    if rule is None:
        return FindingStatus.OPEN, None, ""
    if rule.expires_on < today:
        # Excepción vencida: el hallazgo vuelve a estar abierto (bloquea de nuevo).
        return FindingStatus.OPEN, rule.expires_on, rule.reason
    return FindingStatus.ACCEPTED_RISK, rule.expires_on, rule.reason


# --- Ingesta (ORM) --------------------------------------------------------------

def ingest_findings(
    *,
    raw_findings: list[RawFinding],
    exceptions: list[ExceptionRule],
    sources: list[str],
    now: Any = None,
) -> IngestResult:
    """Upsert determinista + reconciliación (lo no visto en estas fuentes → fixed)."""
    now = now or timezone.now()
    today = now.date()
    result = IngestResult(sources=list(sources))
    seen_pks: set[int] = set()

    for rf in raw_findings:
        status, expires_at, reason = _status_for(rf, exceptions, today)
        # El parser puede precomputar el riesgo (SAST dominio-aware); si no, se deriva de la severidad.
        risk = rf.risk_class or risk_for_severity(rf.severity_raw)
        obj, created = SecurityFinding.objects.get_or_create(
            source_tool=rf.source_tool,
            package=rf.package,
            vuln_id=rf.vuln_id,
            defaults={
                "package_version": rf.package_version,
                "fixed_version": rf.fixed_version,
                "cve_id": rf.cve_id,
                "severity_raw": rf.severity_raw,
                "risk_class": risk,
                "file_path": rf.file_path,
                "line_start": rf.line_start,
                "symbol": rf.symbol,
                "domain": rf.domain,
                "cwe_id": rf.cwe_id,
                "status": status,
                "expires_at": expires_at,
                "accepted_risk_reason": reason,
                "first_seen_at": now,
                "last_seen_at": now,
            },
        )
        if created:
            result.created += 1
        else:
            obj.package_version = rf.package_version
            obj.fixed_version = rf.fixed_version
            obj.cve_id = rf.cve_id
            obj.severity_raw = rf.severity_raw
            obj.risk_class = risk
            obj.file_path = rf.file_path
            obj.line_start = rf.line_start
            obj.symbol = rf.symbol
            obj.domain = rf.domain
            obj.cwe_id = rf.cwe_id
            obj.last_seen_at = now
            # No pisar triage humano (confirmed/triaged/false_positive).
            if obj.status in AUTO_FINDING_STATES:
                obj.status = status
                obj.expires_at = expires_at
                obj.accepted_risk_reason = reason
            obj.save()
            result.updated += 1
        seen_pks.add(obj.pk)

    # Reconciliación: hallazgos de ESTAS fuentes que ya no aparecen y siguen en estado
    # automático abierto/aceptado → resueltos (fixed). No toca triage humano.
    result.resolved = (
        SecurityFinding.objects.filter(source_tool__in=sources)
        .exclude(pk__in=seen_pks)
        .filter(status__in=[FindingStatus.OPEN, FindingStatus.ACCEPTED_RISK])
        .update(status=FindingStatus.FIXED, last_seen_at=now)
    )
    return result
