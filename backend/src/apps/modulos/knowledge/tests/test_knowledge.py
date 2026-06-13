"""Tests del RAG de documentación interna (retrieval determinista + síntesis opcional).

Fijan: el chunking por headings (determinista), la ingesta idempotente con poda, el
FTS en ESPAÑOL (stemming: "cierres" encuentra "cierre"), las citas como contrato, el
permiso RBAC, y las reglas duras de la síntesis: kill switch apagado → sin IA pero el
retrieval sigue; LLM caído → degrada a retrieval-only sin romper. LLM siempre mockeado.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.knowledge import synthesis as synthesis_mod
from apps.modulos.knowledge.ingest import chunk_markdown, ingest_corpus
from apps.modulos.knowledge.models import KnowledgeChunk
from apps.modulos.knowledge.search import search_docs
from apps.modulos.knowledge.synthesis import synthesize_answer
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()

_DOC = """# Política de cierre de caja

El cierre de caja diario requiere conteo físico y aprobación del supervisor.

## Diferencias

Toda diferencia de caja se registra y se investiga antes de aprobar el cierre.
"""


def _mk_corpus(tmp_path, *, text: str = _DOC, name: str = "politica_caja.md"):
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / name).write_text(text, encoding="utf-8")
    return tmp_path


# --- Chunking (puro) ---------------------------------------------------------------

def test_chunking_por_headings_es_determinista():
    chunks = chunk_markdown(_DOC)
    assert [c.heading for c in chunks] == ["Política de cierre de caja", "Diferencias"]
    assert "conteo físico" in chunks[0].content
    assert chunk_markdown(_DOC) == chunks


def test_chunking_texto_sin_headings_no_pierde_contenido():
    chunks = chunk_markdown("solo un párrafo sin título")
    assert len(chunks) == 1
    assert chunks[0].heading == ""
    assert "párrafo" in chunks[0].content


def test_chunking_parrafo_monolitico_respeta_tope():
    chunks = chunk_markdown("# Doc\n" + ("palabra " * 3000))
    assert len(chunks) > 1
    assert all(len(c.content) <= 4200 for c in chunks)


# --- Ingesta (DB) --------------------------------------------------------------------

@pytest.mark.django_db
def test_ingesta_idempotente_y_poda(tmp_path):
    root = _mk_corpus(tmp_path)
    r1 = ingest_corpus(root=root)
    assert r1.files_ingested == 1 and r1.chunks_written == 2

    r2 = ingest_corpus(root=root)  # sin cambios => no re-trabaja
    assert r2.files_unchanged == 1 and r2.files_ingested == 0
    assert KnowledgeChunk.objects.count() == 2

    (root / "docs" / "politica_caja.md").unlink()  # archivo desaparece => poda
    r3 = ingest_corpus(root=root)
    assert r3.files_removed == 1
    assert KnowledgeChunk.objects.count() == 0


@pytest.mark.django_db
def test_ingesta_reemplaza_archivo_cambiado(tmp_path):
    root = _mk_corpus(tmp_path)
    ingest_corpus(root=root)
    _mk_corpus(tmp_path, text="# Nueva versión\n\nContenido distinto sobre combustible.")
    ingest_corpus(root=root)
    assert KnowledgeChunk.objects.count() == 1
    assert "combustible" in KnowledgeChunk.objects.get().content


# --- Búsqueda determinista (FTS español) ---------------------------------------------

@pytest.mark.django_db
def test_busqueda_en_espanol_con_stemming(tmp_path):
    ingest_corpus(root=_mk_corpus(tmp_path))
    results = search_docs("cierres de caja")  # plural; el doc dice "cierre"
    assert results, "el stemming español debe encontrar 'cierre' buscando 'cierres'"
    top = results[0]
    assert top["source_path"] == "docs/politica_caja.md"
    assert top["heading"]  # la cita (fuente + heading) es parte del contrato
    assert "**" in top["excerpt"]  # extracto con resaltado


@pytest.mark.django_db
def test_busqueda_sin_match_devuelve_vacio(tmp_path):
    ingest_corpus(root=_mk_corpus(tmp_path))
    assert search_docs("blockchain cuántico interestelar") == []


# --- Síntesis: kill switch + degradación ---------------------------------------------

_RESULTS = [
    {"source_path": "docs/x.md", "heading": "Cierre", "excerpt": "el cierre requiere conteo", "rank": 0.9}
]


def test_sintesis_apagada_sin_kill_switch(monkeypatch):
    monkeypatch.setattr(synthesis_mod, "ai_features_enabled", lambda: False)
    assert synthesize_answer("¿cómo cierro caja?", _RESULTS) is None


def test_sintesis_sin_url_configurada(monkeypatch, settings):
    monkeypatch.setattr(synthesis_mod, "ai_features_enabled", lambda: True)
    settings.KNOWLEDGE_LLM_BASE_URL = ""
    settings.DIAGNOSTICS_LLM_BASE_URL = ""
    assert synthesize_answer("¿cómo cierro caja?", _RESULTS) is None


def test_sintesis_responde_con_citas(monkeypatch, settings):
    monkeypatch.setattr(synthesis_mod, "ai_features_enabled", lambda: True)
    settings.KNOWLEDGE_LLM_BASE_URL = "http://llm.test:8080"

    def _fake_post(url, json=None, timeout=None):
        assert url == "http://llm.test:8080/v1/chat/completions"
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "El cierre requiere conteo físico [1]."}}]},
        )

    monkeypatch.setattr(synthesis_mod.requests, "post", _fake_post)
    out = synthesize_answer("¿cómo cierro caja?", _RESULTS)
    assert out is not None
    assert "[1]" in out["text"]
    assert out["sources"][0]["source_path"] == "docs/x.md"


def test_sintesis_degrada_si_el_llm_falla(monkeypatch, settings):
    monkeypatch.setattr(synthesis_mod, "ai_features_enabled", lambda: True)
    settings.KNOWLEDGE_LLM_BASE_URL = "http://llm.test:8080"

    def _boom(url, json=None, timeout=None):
        raise synthesis_mod.requests.ConnectionError("llm caído")

    monkeypatch.setattr(synthesis_mod.requests, "post", _boom)
    assert synthesize_answer("¿cómo cierro caja?", _RESULTS) is None  # nunca lanza


# --- API + RBAC ----------------------------------------------------------------------

def _mk_client(perm_codes: list[str]) -> APIClient:
    t = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C{t}", parent=holding)
    user = User.objects.create_user(username=f"kn_{t}", email=f"kn_{t}@t.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    role = Role.objects.create(name=f"kn_role_{t}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    return client


@pytest.mark.django_db
def test_api_requiere_permiso():
    assert APIClient().get("/api/knowledge/search/?q=caja").status_code in (401, 403)


@pytest.mark.django_db
def test_api_busca_y_sin_ia_answer_es_null(tmp_path):
    ingest_corpus(root=_mk_corpus(tmp_path))
    client = _mk_client(["knowledge.docs.read"])
    r = client.get("/api/knowledge/search/?q=cierre de caja&synthesize=1")
    assert r.status_code == 200, r.data
    assert r.data["results"]
    assert r.data["answer"] is None  # kill switch OFF por defecto => sin IA
    assert r.data["ai_used"] is False


@pytest.mark.django_db
def test_api_q_vacio_es_400():
    client = _mk_client(["knowledge.docs.read"])
    assert client.get("/api/knowledge/search/").status_code == 400


@pytest.mark.django_db
def test_command_ingesta(tmp_path):
    _mk_corpus(tmp_path)
    call_command("ingest_knowledge_docs", "--root", str(tmp_path))
    assert KnowledgeChunk.objects.count() == 2


@pytest.mark.django_db
def test_seed_otorga_knowledge_a_company_admin():
    from apps.modulos.rbac.seed_v01 import seed_rbac_v01

    seed_rbac_v01()
    role = Role.objects.get(name="company_admin")
    codes = set(RolePermission.objects.filter(role=role).values_list("permission__code", flat=True))
    assert "knowledge.docs.read" in codes
