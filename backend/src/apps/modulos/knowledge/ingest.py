"""Ingesta del corpus de documentación interna → `KnowledgeChunk` (idempotente).

Corpus: `docs/**/*.md` + `backend/src/apps/**/README.md` + `README.md` raíz. Cada
archivo se parte por headings markdown (`#`..`###`); los cuerpos largos se subdividen
por párrafos (tope `_MAX_CHUNK_CHARS`). El checksum por archivo evita re-trabajo: si
el archivo no cambió, sus chunks no se tocan; si cambió o desapareció, se reemplazan.
Al final se recalcula el tsvector en español (heading peso A, contenido peso B).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from django.contrib.postgres.search import SearchVector
from django.db import transaction
from django.utils import timezone

from .models import KnowledgeChunk

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_MAX_CHUNK_CHARS = 4000
_CORPUS_GLOBS = ("docs/**/*.md", "backend/src/apps/**/README.md", "README.md")


@dataclass(frozen=True)
class ChunkDraft:
    heading: str
    content: str


@dataclass
class IngestResult:
    files_seen: int = 0
    files_ingested: int = 0
    files_unchanged: int = 0
    files_removed: int = 0
    chunks_written: int = 0


def _split_long(text: str) -> list[str]:
    """Divide un cuerpo largo por párrafos respetando el tope de caracteres."""
    if len(text) <= _MAX_CHUNK_CHARS:
        return [text]
    parts: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > _MAX_CHUNK_CHARS and current:
            parts.append(current)
            current = para
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def chunk_markdown(text: str) -> list[ChunkDraft]:
    """Parte un markdown por headings (#..###). Determinista: mismo texto → mismos chunks."""
    out: list[ChunkDraft] = []
    heading = ""
    body: list[str] = []

    def _flush() -> None:
        content = "\n".join(body).strip()
        if not content and not heading:
            return
        if not content:
            content = heading  # heading sin cuerpo: el título igual es buscable
        for piece in _split_long(content):
            out.append(ChunkDraft(heading=heading[:255], content=piece))

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            _flush()
            heading = m.group(2).strip()
            body = []
        else:
            body.append(line)
    _flush()
    return out


def _corpus_files(root: Path) -> list[Path]:
    seen: set[Path] = set()
    for pattern in _CORPUS_GLOBS:
        for p in root.glob(pattern):
            if p.is_file():
                seen.add(p)
    return sorted(seen)


def ingest_corpus(*, root: Path) -> IngestResult:
    """Sincroniza el índice con el corpus del repo (agrega/reemplaza/poda)."""
    result = IngestResult()
    now = timezone.now()
    alive_paths: set[str] = set()

    for path in _corpus_files(root):
        result.files_seen += 1
        rel = path.relative_to(root).as_posix()
        alive_paths.add(rel)
        raw = path.read_text(encoding="utf-8", errors="replace")
        checksum = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        existing = KnowledgeChunk.objects.filter(source_path=rel).values_list(
            "file_checksum", flat=True
        ).first()
        if existing == checksum:
            result.files_unchanged += 1
            continue

        drafts = chunk_markdown(raw)
        with transaction.atomic():
            KnowledgeChunk.objects.filter(source_path=rel).delete()
            KnowledgeChunk.objects.bulk_create(
                KnowledgeChunk(
                    source_path=rel,
                    heading=d.heading,
                    order=i,
                    content=d.content,
                    file_checksum=checksum,
                    ingested_at=now,
                )
                for i, d in enumerate(drafts)
            )
        result.files_ingested += 1
        result.chunks_written += len(drafts)

    # Poda: archivos que ya no existen en el repo salen del índice.
    removed_qs = KnowledgeChunk.objects.exclude(source_path__in=alive_paths)
    result.files_removed = removed_qs.values("source_path").distinct().count()
    removed_qs.delete()

    # tsvector en español: heading manda (peso A), contenido acompaña (peso B).
    KnowledgeChunk.objects.update(
        search=SearchVector("heading", weight="A", config="spanish")
        + SearchVector("content", weight="B", config="spanish")
    )
    return result
