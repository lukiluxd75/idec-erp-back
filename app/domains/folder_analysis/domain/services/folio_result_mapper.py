"""
The folio lane reads its pages with the folios domain's pipeline (OCR + OpenCV +
rule parsers) instead of the vision model. That pipeline answers in its own
Spanish shape; this turns it into the FOLIO_TEMPLATE the lane stores and the
review screen renders, so nothing downstream had to change.

What the rules give that the model never did -- per-field confidence and the
observations -- is kept under `reading` for the JSON tab.
"""
from typing import Any, Dict, List, Optional

from app.domains.folder_analysis.domain.extraction_profiles import FOLIO_TEMPLATE
from app.domains.folder_analysis.domain.services.result_merger import conform, is_empty

_BOUNDARIES = (("north", "norte"), ("south", "sud"), ("east", "este"), ("west", "oeste"))
_OWNER_FIELDS = (
    ("name", "nombre"),
    ("id_number", "ci"),
    ("id_issued_at", "expedido"),
    ("marital_status", "estado_civil"),
    ("role", "rol"),
)


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _surface(surface: Dict[str, Any]) -> Optional[str]:
    """'205.22 m2'. Falls back to the OCR text when the number could not be read."""
    value, unit = surface.get("valor"), surface.get("unidad")
    if value is None:
        return _text(surface.get("texto_original"))
    number = f"{value:g}"
    return f"{number} {unit}" if unit else number


def _filing(filing: Optional[Dict[str, Any]]) -> Optional[str]:
    """The 'Present.-' line put back together from its parsed pieces."""
    if not isinstance(filing, dict):
        return _text(filing)
    parts = []
    if filing.get("numero"):
        parts.append(f"No. {filing['numero']}")
    if filing.get("fecha"):
        parts.append(f"de {filing['fecha']}")
    if filing.get("hora"):
        parts.append(f"Hrs. {filing['hora']}")
    return " ".join(parts) or None


def _share(people: List[Dict[str, Any]]) -> Optional[str]:
    """PROPORCIÓN is printed per person; the lane keeps one value per asiento, so
    the distinct ones are joined ('1/2', or '1/2 y 1/4' when they differ)."""
    seen = [p.get("proporcion") for p in people if p.get("proporcion")]
    unique = list(dict.fromkeys(seen))
    return " y ".join(unique) or None


def _entry(asiento: Dict[str, Any]) -> Dict[str, Any]:
    people = asiento.get("personas") or []
    document = asiento.get("documento")
    return {
        "entry_number": _text(asiento.get("numero")),
        "owners": [{key: _text(person.get(source)) for key, source in _OWNER_FIELDS} for person in people],
        "share": _share(people),
        "act": _text(asiento.get("acto")),
        "document": _text(document.get("descripcion") if isinstance(document, dict) else document),
        "authority": _text(asiento.get("autoridad")),
        "filing": _filing(asiento.get("presentacion")),
    }


def to_folio_template(extracted: Dict[str, Any], fill_log: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """`extracted` as the folios contract returns it -> the lane's stored shape."""
    matricula = extracted.get("matricula") or {}
    titularidad = extracted.get("titularidad_dominio") or {}
    documento = extracted.get("documento") or {}
    linderos = extracted.get("linderos") or {}

    data = {
        "registration_number": _text(matricula.get("numero")),
        "registration_status": _text(matricula.get("estado")),
        "administrative_location": _text(matricula.get("zona")),
        "cadastre": _text(extracted.get("catastro")),
        "property_type": _text(extracted.get("tipo_inmueble")),
        "location": _text(extracted.get("ubicacion")),
        "designation": _text(extracted.get("designacion_s_tit")),
        "surface": _surface(extracted.get("superficie") or {}),
        "measures": _text(extracted.get("medidas")),
        "boundaries": {key: _text(linderos.get(source)) for key, source in _BOUNDARIES},
        "property": _text(extracted.get("propiedad")),
        "prior_title": _text(titularidad.get("antecedente_dominial")),
        "date": _text(documento.get("fecha_emision")),
        "page": {"number": None, "total": _text(documento.get("paginas_declaradas"))},
        "ownership_entries": [_entry(a) for a in titularidad.get("asientos") or []],
    }
    result = conform(FOLIO_TEMPLATE, data)
    # Same rule the model path used: an "Asiento Numero" header with nothing
    # under it (the next asiento starting at the bottom edge of the photo) is
    # not an entry yet.
    result["ownership_entries"] = [
        entry for entry in result["ownership_entries"]
        if not (
            is_empty(entry.get("owners"))
            and all(is_empty(entry.get(key)) for key in ("act", "document", "authority", "filing"))
        )
    ]
    result["pages_read"] = [
        {"number": _text(photo.get("pagina_impresa")), "total": _text(photo.get("total_impreso"))}
        for photo in (fill_log or {}).get("fotos") or []
    ]
    result["reading"] = {
        "source": "ocr_rules",
        "current_owners": titularidad.get("titulares_actuales") or [],
        "last_entry_declared": titularidad.get("ultimo_asiento"),
        "low_confidence_fields": extracted.get("campos_baja_confianza") or [],
        # Column A lines the rules could not attach to an asiento: shown in the
        # JSON tab so nothing read from the photo is silently dropped.
        "unassigned_lines": titularidad.get("lineas_sin_asiento") or [],
        "observations": extracted.get("observaciones") or [],
    }
    return result
