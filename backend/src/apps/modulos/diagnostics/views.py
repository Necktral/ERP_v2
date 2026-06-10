from __future__ import annotations

from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission

from .ai_diagnosis import AIDisabledError, run_ai_diagnosis
from .diagnose import create_diagnostic_run
from .gates import evaluate_release_gates
from .models import (
    AIControl,
    CodeUnitEvidence,
    DiagnosticRun,
    ErrorEvent,
    SecurityFinding,
)
from .serializers import (
    AIControlSerializer,
    AIControlUpdateSerializer,
    CodeUnitEvidenceSerializer,
    DiagnosticRunSerializer,
    ErrorEventDetailSerializer,
    ErrorEventSerializer,
    SecurityFindingSerializer,
    TriageSerializer,
)
from .supervision import build_supervision_summary
from .triage import TriageError, triage_error, triage_finding


class ErrorEventListView(APIView):
    permission_classes = [rbac_permission("diagnostics.error.read")]

    def get(self, request):
        qs = ErrorEvent.objects.all()
        domain_f = request.query_params.get("domain")
        if domain_f:
            qs = qs.filter(domain=domain_f)
        risk_f = request.query_params.get("risk_class")
        if risk_f:
            qs = qs.filter(risk_class=risk_f)
        status_f = request.query_params.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        data = ErrorEventSerializer(qs[:200], many=True).data
        return Response({"results": data}, status=status.HTTP_200_OK)


class ErrorEventDetailView(APIView):
    permission_classes = [rbac_permission("diagnostics.error.read")]

    def get(self, request, error_id):
        obj = get_object_or_404(ErrorEvent, error_id=error_id)
        return Response(ErrorEventDetailSerializer(obj).data, status=status.HTTP_200_OK)


class SecurityFindingListView(APIView):
    permission_classes = [rbac_permission("diagnostics.finding.read")]

    def get(self, request):
        qs = SecurityFinding.objects.all()
        for f in ("source_tool", "risk_class", "status"):
            val = request.query_params.get(f)
            if val:
                qs = qs.filter(**{f: val})
        data = SecurityFindingSerializer(qs[:300], many=True).data
        return Response({"results": data}, status=status.HTTP_200_OK)


class SecurityFindingDetailView(APIView):
    permission_classes = [rbac_permission("diagnostics.finding.read")]

    def get(self, request, finding_id):
        obj = get_object_or_404(SecurityFinding, finding_id=finding_id)
        return Response(SecurityFindingSerializer(obj).data, status=status.HTTP_200_OK)


class AIControlView(APIView):
    """Botón de apagado de la IA. GET lee el estado; POST enciende/apaga (en caliente)."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("diagnostics.ai_control.manage")()]
        return [rbac_permission("diagnostics.ai_control.read")()]

    def get(self, request):
        return Response(AIControlSerializer(AIControl.current()).data, status=status.HTTP_200_OK)

    def post(self, request):
        s = AIControlUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        ctrl = AIControl.current()
        ctrl.ai_enabled = bool(v["enabled"])
        ctrl.reason = v.get("reason", "")
        ctrl.updated_by = request.user if request.user.is_authenticated else None
        ctrl.save()
        return Response(AIControlSerializer(ctrl).data, status=status.HTTP_200_OK)


class DiagnoseErrorView(APIView):
    """Arma el diagnóstico de causa raíz (evidencia DETERMINISTA) de un fallo."""

    permission_classes = [rbac_permission("diagnostics.diagnose.run")]

    def post(self, request, error_id):
        error = get_object_or_404(ErrorEvent, error_id=error_id)
        run = create_diagnostic_run(error=error, trigger_type="manual", created_by=request.user)
        return Response(DiagnosticRunSerializer(run).data, status=status.HTTP_201_CREATED)


class DiagnosticRunListView(APIView):
    permission_classes = [rbac_permission("diagnostics.diagnose.read")]

    def get(self, request):
        qs = DiagnosticRun.objects.all()
        for f in ("subject_id", "risk_class", "status", "domain"):
            val = request.query_params.get(f)
            if val:
                qs = qs.filter(**{f: val})
        data = DiagnosticRunSerializer(qs[:200], many=True).data
        return Response({"results": data}, status=status.HTTP_200_OK)


class DiagnosticRunDetailView(APIView):
    permission_classes = [rbac_permission("diagnostics.diagnose.read")]

    def get(self, request, run_id):
        obj = get_object_or_404(DiagnosticRun, run_id=run_id)
        return Response(DiagnosticRunSerializer(obj).data, status=status.HTTP_200_OK)


class CodeUnitEvidenceListView(APIView):
    """¿La línea que falló está testeada? Evidencia por línea (cobertura + refs)."""

    permission_classes = [rbac_permission("diagnostics.error.read")]

    def get(self, request):
        qs = CodeUnitEvidence.objects.all()
        for f in ("domain", "coverage_state"):
            val = request.query_params.get(f)
            if val:
                qs = qs.filter(**{f: val})
        data = CodeUnitEvidenceSerializer(qs[:300], many=True).data
        return Response({"results": data}, status=status.HTTP_200_OK)


class ReleaseReadinessView(APIView):
    """Verdicto de gate de release: un C1 abierto (error o hallazgo) bloquea."""

    permission_classes = [rbac_permission("diagnostics.error.read")]

    def get(self, request):
        return Response(evaluate_release_gates(), status=status.HTTP_200_OK)


class SupervisionView(APIView):
    """Supervisión determinista: la cola priorizada del *qué falla y por qué* (sin IA).

    Responde *qué está fallando AHORA, qué tan grave y por qué*: salud global, alertas y los
    fallos activos ordenados por `priority_score` (con su desglose auditable). Lee el rol
    transversal `platform_observer` (gate `diagnostics.error.read`).
    """

    permission_classes = [rbac_permission("diagnostics.error.read")]

    _MAX_LIMIT = 100

    def get(self, request):
        raw = request.query_params.get("limit", "20")
        try:
            limit = int(raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "limit debe ser un entero."}, status=status.HTTP_400_BAD_REQUEST
            )
        if limit < 1:
            return Response(
                {"detail": "limit debe ser >= 1."}, status=status.HTTP_400_BAD_REQUEST
            )
        limit = min(limit, self._MAX_LIMIT)
        return Response(build_supervision_summary(limit=limit), status=status.HTTP_200_OK)


class AIDiagnoseView(APIView):
    """Motor IA advisory: rellena la hipótesis de causa de un diagnóstico.

    SIEMPRE detrás del kill switch: si la IA está apagada → 409 (no toca nada).
    """

    permission_classes = [rbac_permission("diagnostics.ai_diagnose.run")]

    def post(self, request, run_id):
        run = get_object_or_404(DiagnosticRun, run_id=run_id)
        try:
            run = run_ai_diagnosis(run=run, actor=request.user)
        except AIDisabledError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(DiagnosticRunSerializer(run).data, status=status.HTTP_200_OK)


class ErrorEventTriageView(APIView):
    """Triage humano de un error: confirmar / falso positivo / corregido / riesgo aceptado.

    Deja rastro de quién decidió (`owner`). El centinela de regresión sigue mandando:
    un `fixed` que reaparece vuelve a `regressed` — al ledger no se le puede mentir.
    """

    permission_classes = [rbac_permission("diagnostics.error.triage")]

    def post(self, request, error_id):
        s = TriageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = get_object_or_404(ErrorEvent, error_id=error_id)
        try:
            obj = triage_error(
                error=obj, status=s.validated_data["status"], owner=request.user.username
            )
        except TriageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ErrorEventSerializer(obj).data, status=status.HTTP_200_OK)


class SecurityFindingTriageView(APIView):
    """Triage humano de un hallazgo. `accepted_risk` NO pasa por acá: esa decisión vive
    en el contrato de excepciones CON VENCIMIENTO (la API no permite saltárselo)."""

    permission_classes = [rbac_permission("diagnostics.finding.triage")]

    def post(self, request, finding_id):
        s = TriageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = get_object_or_404(SecurityFinding, finding_id=finding_id)
        try:
            obj = triage_finding(
                finding=obj, status=s.validated_data["status"], owner=request.user.username
            )
        except TriageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SecurityFindingSerializer(obj).data, status=status.HTTP_200_OK)
