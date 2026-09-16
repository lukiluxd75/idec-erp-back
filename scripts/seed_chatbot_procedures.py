"""
Loads the municipal-procedure catalog (`tramites_data.json`-style export) into
the `chatbot` schema. Idempotent: re-running with the same input upserts by
`procedures.code`, it never duplicates rows.

The source file is NOT a clean single JSON document — it is several JSON arrays
concatenated back to back (each `[...]` block a separate export batch), and many
records carry leftover `[cite: N]` citation markers from the AI-assisted
extraction that produced them. Both are handled here (see `_parse_concatenated_json`
and `_strip_cite_markers`) rather than expecting a pre-cleaned file.

Two stages, so a missing Ollama host does not block loading the catalog:

    python scripts/seed_chatbot_procedures.py --input /path/to/tramites_data.json
        Stage 1 only: parse, clean, dedupe and upsert procedures + requirements.
        No LLM involved — safe to run today.

    python scripts/seed_chatbot_procedures.py --input ... --reindex
        Also runs stage 2: recompute embeddings for every loaded procedure.
        Requires CHATBOT_OLLAMA_URL to be configured and reachable.
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database.connection import SessionLocal  # noqa: E402
from app.domains.chatbot.infrastructure.models import (  # noqa: E402
    ProcedureModel,
    ProcedureRequirementModel,
)

logger = logging.getLogger("seed_chatbot_procedures")

_CITE_MARKER_RE = re.compile(r"\[cite:\s*\d+(?:\s*,\s*\d+)*\s*\]")


def _strip_cite_markers(value: Any) -> Any:
    """Recursively removes '[cite: N]' / '[cite: N, M]' artifacts left by the AI
    extraction that produced the source file, and collapses the extra whitespace
    they leave behind."""
    if isinstance(value, str):
        cleaned = _CITE_MARKER_RE.sub("", value)
        return re.sub(r"\s{2,}", " ", cleaned).strip()
    if isinstance(value, list):
        return [_strip_cite_markers(item) for item in value]
    if isinstance(value, dict):
        return {key: _strip_cite_markers(item) for key, item in value.items()}
    return value


def _parse_concatenated_json(text: str) -> Tuple[List[Dict[str, Any]], int]:
    """The source file is N JSON arrays back to back (`[...][...]...`), not one
    valid JSON document — json.load() fails on it with "Extra data". Decodes one
    top-level value at a time instead and flattens every array found. Returns
    (items, block_count) -- block_count is how many top-level `[...]` values
    were decoded, purely for the log line below."""
    decoder = json.JSONDecoder()
    items: List[Dict[str, Any]] = []
    block_count = 0
    idx = 0
    length = len(text)
    while idx < length:
        while idx < length and text[idx] in " \n\t\r":
            idx += 1
        if idx >= length:
            break
        obj, end = decoder.raw_decode(text, idx)
        block_count += 1
        if isinstance(obj, list):
            items.extend(obj)
        else:
            items.append(obj)
        idx = end
    return items, block_count


def _dedupe_by_code(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Some `id_tramite` values appear twice in the source file: an earlier,
    dirtier extraction batch and a later, cleaner rewrite of the same trámite
    (confirmed by manual inspection — the later occurrence consistently has the
    fuller name and no leftover [cite: N] marker). Last occurrence wins."""
    by_code: Dict[str, Dict[str, Any]] = {}
    for item in items:
        code = item.get("id_tramite")
        if not code:
            continue
        by_code[code] = item
    return by_code


def _upsert_procedure(db, record: Dict[str, Any]) -> ProcedureModel:
    code = record["id_tramite"]
    name = record.get("nombre_tramite", "").strip()
    search_description = (record.get("descripcion_busqueda") or "").strip() or None
    cost_note = (record.get("costo") or "").strip() or None
    leyes = record.get("leyes_asociadas") or []
    legal_basis = "; ".join(leyes) if leyes else None

    procedure = db.query(ProcedureModel).filter(ProcedureModel.code == code).first()
    if procedure is None:
        procedure = ProcedureModel(code=code)
        db.add(procedure)

    procedure.name = name
    procedure.search_description = search_description
    procedure.cost_note = cost_note
    procedure.legal_basis = legal_basis
    db.flush()  # need procedure.id before touching requirements

    # Requirements are fully replaced on every load, same as the ported
    # prototype's ingesta_repository does on re-ingestion — the source list is
    # the single source of truth for a code, not something merged by hand.
    db.query(ProcedureRequirementModel).filter(
        ProcedureRequirementModel.procedure_id == procedure.id
    ).delete()
    for order, req in enumerate(record.get("requisitos") or []):
        db.add(
            ProcedureRequirementModel(
                procedure_id=procedure.id,
                description=(req.get("nombre") or "").strip(),
                is_mandatory=bool(req.get("obligatorio", True)),
                display_order=order,
            )
        )

    return procedure


def load_catalog(input_path: Path) -> List[str]:
    """Stage 1. Returns the list of procedure codes that were loaded."""
    raw_text = input_path.read_text(encoding="utf-8")
    items, block_count = _parse_concatenated_json(raw_text)
    items = [_strip_cite_markers(item) for item in items]
    deduped = _dedupe_by_code(items)

    logger.info(
        "Parseados %d registros (%d bloques JSON), %d códigos únicos tras deduplicar.",
        len(items),
        block_count,
        len(deduped),
    )

    db = SessionLocal()
    codes: List[str] = []
    try:
        for code, record in deduped.items():
            _upsert_procedure(db, record)
            codes.append(code)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return codes


def reindex_embeddings(codes: List[str]) -> None:
    """Stage 2. Deferred: wires up once the Ollama chat engine (phase 3 of the
    integration plan) exists. Import kept local so stage 1 has zero dependency
    on the LLM engine being implemented or reachable."""
    raise NotImplementedError(
        "El motor de embeddings (OllamaChatEngine) todavía no está implementado "
        "en este dominio -- correr este script sin --reindex por ahora. Ver la "
        "sección 'Motor Ollama' del plan de integración."
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Ruta al JSON de trámites.")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="También recalcula los embeddings de los trámites cargados (requiere Ollama).",
    )
    args = parser.parse_args()

    if not args.input.exists():
        parser.error(f"No existe el archivo: {args.input}")

    codes = load_catalog(args.input)
    logger.info("Cargados/actualizados %d trámites.", len(codes))

    if args.reindex:
        reindex_embeddings(codes)


if __name__ == "__main__":
    main()
