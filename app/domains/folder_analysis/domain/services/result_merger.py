"""
Turns the per-page model outputs of one document into a single result. Each page
is a separate job (so pages spread across PCs); the model's JSON is first forced
into the profile's template, since it sometimes renames, drops or nests keys.
"""
from typing import Any, Dict, List, Optional

from app.domains.folder_analysis.domain.entities import DocumentType
from app.domains.folder_analysis.domain.extraction_profiles import FOLIO_TEMPLATE, TAX_RECEIPT_TEMPLATE

# A lone "x" marks a blank field.
_EMPTY_STRINGS = {"", "null", "none", "n/a", "-", "x"}


def _scalar(value: Any) -> Optional[str]:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return None if text.lower() in _EMPTY_STRINGS else text


def conform(template: Any, value: Any) -> Any:
    """Shape `value` like `template`: same keys, unknown keys dropped, scalars as
    trimmed strings or None, a lone object accepted where a list is expected."""
    if isinstance(template, dict):
        source = value if isinstance(value, dict) else {}
        return {key: conform(sub, source.get(key)) for key, sub in template.items()}
    if isinstance(template, list):
        items = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
        item_template = template[0] if template else None
        shaped = [conform(item_template, item) for item in items]
        return [item for item in shaped if not is_empty(item)]
    return _scalar(value)


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):
        return all(is_empty(v) for v in value.values())
    if isinstance(value, list):
        return all(is_empty(v) for v in value)
    return False


def _filled_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_filled_count(v) for v in value.values())
    if isinstance(value, list):
        return sum(_filled_count(v) for v in value)
    return 0 if value is None else 1


def _first_filled(template: Any, pages: List[Any]) -> Any:
    """Per key, the first page (in order) that has a value."""
    if isinstance(template, dict):
        return {key: _first_filled(sub, [p.get(key) if isinstance(p, dict) else None for p in pages])
                for key, sub in template.items()}
    return next((p for p in pages if not is_empty(p)), None if not isinstance(template, list) else [])


def _merge_folio(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    header_template = {k: v for k, v in FOLIO_TEMPLATE.items() if k not in ("ownership_entries", "page")}
    merged = _first_filled(header_template, pages)

    entries: List[Dict[str, Any]] = []
    by_number: Dict[str, int] = {}
    for page in pages:
        for entry in page["ownership_entries"]:
            # Skip entries with no owners or other identifying values.
            if is_empty(entry.get("owners")) and all(
                is_empty(entry.get(k)) for k in ("act", "document", "authority", "filing")
            ):
                continue
            number = entry.get("entry_number")
            if number is None:
                entries.append(entry)
            elif number not in by_number:
                by_number[number] = len(entries)
                entries.append(entry)
            elif _filled_count(entry) > _filled_count(entries[by_number[number]]):
                entries[by_number[number]] = entry
    merged["ownership_entries"] = entries
    merged["pages_read"] = [p["page"] for p in pages]
    return merged


def _merge_plan(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "document_type": next((p.get("document_type") for p in pages if p.get("document_type")), None),
        "full_text": "\n\n".join(p.get("full_text") or "" for p in pages).strip(),
        "pages": pages,
    }


def merge_pages(doc_type: str, page_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """`page_results` in page order, straight from the model."""
    if doc_type == DocumentType.FOLIO:
        return _merge_folio([conform(FOLIO_TEMPLATE, r) for r in page_results])
    if doc_type == DocumentType.TAX_RECEIPT:
        return _first_filled(TAX_RECEIPT_TEMPLATE, [conform(TAX_RECEIPT_TEMPLATE, r) for r in page_results])
    return _merge_plan([r if isinstance(r, dict) else {} for r in page_results])
