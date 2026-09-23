"""
Background pipeline for one uploaded folio (hybrid computer vision + OCR):

  per page
    1. normalize the photo (EXIF, size cap)                      [OpenCV]
    2. OCR the whole page as-is                                   [OCR]
    3. orientation from the A/B/C column titles, rotate upright   [layout + OpenCV]
       (+ deskew); boxes from step 2 are carried over with the same matrix
    4. ruling lines -> column bounds; plan header / column A crops [OpenCV + layout]
    5. OCR each crop on its own (full-page OCR drops small lines) [OCR]
  whole folio
    6. order pages by their printed 'Pag X de N', parse the header (page 1)
       and column A across all pages, assign PROPORCIÓN values
    7. optional LLM pass for asientos the rules could not fully read
    8. confidence review -> READY / NEEDS_REVIEW, or FAILED with a message

Runs outside any request (BackgroundTasks), so every failure ends up stored on
the folio -- nothing here is allowed to escape.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.errors.exceptions import DomainException
from app.domains.folios.domain.entities.folio import FolioStatus
from app.domains.folios.domain.entities.ocr_block import OcrBlock
from app.domains.folios.domain.exceptions import AsientoStructurerUnavailableException
from app.domains.folios.domain.ports.asiento_structurer_port import AsientoStructurerPort
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort
from app.domains.folios.domain.ports.ocr_port import OcrPort
from app.domains.folios.domain.ports.page_image_port import PageImagePort, RotatedImage
from app.domains.folios.domain.services.header_parser import HeaderResult, parse_header
from app.domains.folios.domain.services.layout import PageLayout, detect_rotation, plan_regions, transform_blocks
from app.domains.folios.domain.services.text import compact, group_lines, join_text, similar
from app.domains.folios.domain.services.titularidad_parser import ColumnLine, current_owners, parse_titularidad

logger = logging.getLogger("uvicorn.error")

EXTRACTION_VERSION = 1
_IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
_PROPORTION_RE = re.compile(r"^\d{1,3}/\d{1,3}$|^\d{1,3}([.,]\d+)?%$")


@dataclass
class PageOutcome:
    page_index: int
    layout: Optional[PageLayout]
    rotation_deg: Optional[float]
    upright: Optional[bytes]
    header_blocks: List[OcrBlock] = field(default_factory=list)
    column_lines: List[ColumnLine] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def _fuzzy_in(needle: str, haystack: str, min_ratio: float = 0.88) -> bool:
    """Is `needle` (compacted) present in `haystack` (compacted), allowing OCR noise?"""
    n, h = compact(needle), compact(haystack)
    if not n:
        return False
    if n in h:
        return True
    if len(n) > len(h):
        return False
    return max(similar(h[i : i + len(n)], n) for i in range(len(h) - len(n) + 1)) >= min_ratio


class ProcessFolioUseCase:
    def __init__(
        self,
        repository: FolioRepositoryPort,
        ocr: OcrPort,
        images: PageImagePort,
        structurer: Optional[AsientoStructurerPort],
        confidence_threshold: float,
    ):
        self._repo = repository
        self._ocr = ocr
        self._images = images
        self._structurer = structurer
        self._threshold = confidence_threshold

    def execute(self, folio_id: str) -> None:
        folio = self._repo.get_for_processing(folio_id)
        if folio is None or folio.status == FolioStatus.CONFIRMED:
            return
        try:
            self._repo.mark_processing(folio_id)
            outcomes = []
            for page_index, content, _mime in self._repo.get_page_bytes_for_processing(folio_id):
                outcome = self._process_page(page_index, content)
                self._repo.save_page_result(
                    folio_id,
                    page_index,
                    upright_jpeg=outcome.upright,
                    rotation_deg=outcome.rotation_deg,
                    detected_page_number=outcome.layout.page_number if outcome.layout else None,
                    diagnostics=outcome.diagnostics,
                )
                outcomes.append(outcome)
            data, status = self._assemble(outcomes)
            self._repo.save_extraction(folio_id, data, status, (data["matricula"] or {}).get("numero"))
        except DomainException as exc:
            logger.warning("Folio %s: procesamiento fallido: %s", folio_id, exc.message)
            self._repo.mark_failed(folio_id, exc.message)
        except Exception:
            logger.exception("Folio %s: error inesperado al procesar", folio_id)
            self._repo.mark_failed(folio_id, "Error inesperado al procesar el folio. Intente reprocesarlo.")

    # ------------------------------------------------------------------ page

    def _orient(self, jpeg: bytes, width: int, height: int, blocks: List[OcrBlock]):
        """(RotatedImage, blocks in its frame, angle) -- or angle None if the
        column titles could not be found in any orientation."""
        angle = detect_rotation(blocks)
        if angle is not None:
            if abs(angle) < 0.3:
                return RotatedImage(jpeg, width, height, _IDENTITY), blocks, 0.0
            upright = self._images.rotate(jpeg, angle)
            return upright, transform_blocks(blocks, upright.matrix), angle

        # Titles not found on the raw photo: try the other 3 orientations.
        for fallback in (90.0, -90.0, 180.0):
            turned = self._images.rotate(jpeg, fallback)
            turned_blocks = self._ocr.read(turned.content)
            residual = detect_rotation(turned_blocks)
            if residual is None:
                continue
            if abs(residual) < 0.3:
                return turned, turned_blocks, fallback
            upright = self._images.rotate(turned.content, residual)
            return upright, transform_blocks(turned_blocks, upright.matrix), fallback + residual
        return RotatedImage(jpeg, width, height, _IDENTITY), blocks, None

    def _process_page(self, page_index: int, content: bytes) -> PageOutcome:
        jpeg, width, height = self._images.normalize(content)
        raw_blocks = self._ocr.read(jpeg, f"folio_p{page_index + 1}.jpg")
        upright, blocks, angle = self._orient(jpeg, width, height, raw_blocks)

        outcome = PageOutcome(page_index=page_index, layout=None, rotation_deg=angle, upright=upright.content)
        label = f"Página {page_index + 1}"
        if angle is None:
            outcome.observations.append(
                f"{label}: no se reconocieron los títulos de las columnas A/B/C; ¿es un folio real?"
            )

        lines = self._images.vertical_lines(upright.content)
        layout = plan_regions(blocks, lines, upright.width, upright.height)
        outcome.layout = layout
        outcome.observations.extend(f"{label}: {o}" for o in layout.observations)

        if layout.header_rect is not None:
            x0, y0, _, _ = layout.header_rect
            crop = self._images.crop(upright.content, layout.header_rect)
            outcome.header_blocks = self._ocr.read(crop, f"folio_p{page_index + 1}_cabecera.jpg")
            header_width = layout.header_rect[2] - x0
        else:
            header_width = 0

        column_blocks: List[OcrBlock] = []
        if layout.titularidad_rect is not None:
            x0, y0, _, _ = layout.titularidad_rect
            crop = self._images.crop(upright.content, layout.titularidad_rect)
            column_blocks = [b.shifted(x0, y0) for b in self._ocr.read(crop, f"folio_p{page_index + 1}_col_a.jpg")]
            outcome.column_lines = self._column_lines(column_blocks, layout, page_index)

        outcome.diagnostics = {
            "rotation_deg": angle,
            "size": [upright.width, upright.height],
            "vertical_lines": [round(x, 1) for x in lines],
            "page_number": layout.page_number,
            "page_total": layout.page_total,
            "header_rect": layout.header_rect,
            "header_width": header_width,
            "titularidad_rect": layout.titularidad_rect,
            "proportion_range": layout.proportion_range,
            "observations": outcome.observations,
            "blocks_page": [b.to_dict() for b in blocks],
            "blocks_header": [b.to_dict() for b in outcome.header_blocks],
            "blocks_titularidad": [b.to_dict() for b in column_blocks],
        }
        return outcome

    @staticmethod
    def _column_lines(column_blocks: List[OcrBlock], layout: PageLayout, page_index: int) -> List[ColumnLine]:
        """Column A text lines (page frame) + the PROPORCION value printed on the
        same row (the crop covers both columns). A value is attached to whatever
        column A line shares its row; the parser only reads it on name lines (on
        the sample folio each '1/1' sits on the row of an owner's name)."""
        proportions, text_blocks = [], []
        for b in column_blocks:
            in_proportion = layout.proportion_range is not None and b.cx >= layout.proportion_range[0]
            if in_proportion:
                if _PROPORTION_RE.match(re.sub(r"\s+", "", b.text)):
                    proportions.append(b)
            else:
                text_blocks.append(b)
        grouped = group_lines(text_blocks)

        assigned: Dict[int, str] = {}
        for p in proportions:
            if not grouped:
                break
            idx, line = min(enumerate(grouped), key=lambda il: abs(sum(x.cy for x in il[1]) / len(il[1]) - p.cy))
            line_cy = sum(x.cy for x in line) / len(line)
            line_h = max(sum(x.h for x in line) / len(line), 1.0)
            if abs(line_cy - p.cy) <= 0.6 * line_h:
                assigned[idx] = re.sub(r"\s+", "", p.text)

        return [
            ColumnLine(
                text=join_text(line),
                confidence=min(b.confidence for b in line),
                page=page_index,
                proportion=assigned.get(i),
            )
            for i, line in enumerate(grouped)
        ]

    # ------------------------------------------------------------- assemble

    def _assemble(self, outcomes: List[PageOutcome]) -> Tuple[Dict[str, Any], str]:
        observations: List[str] = []
        for o in outcomes:
            observations.extend(o.observations)

        # Page order: the printed 'Pag X de N' when every page has a distinct one.
        numbers = [o.layout.page_number if o.layout else None for o in outcomes]
        if all(n is not None for n in numbers) and len(set(numbers)) == len(numbers):
            ordered = sorted(outcomes, key=lambda o: o.layout.page_number)
        else:
            ordered = outcomes
            if len(outcomes) > 1:
                observations.append("No se pudo leer 'Pag X de N' en todas las páginas: se usa el orden de escaneo.")

        declared_total = max((o.layout.page_total for o in outcomes if o.layout and o.layout.page_total), default=None)
        if declared_total and declared_total > len(outcomes):
            observations.append(f"Faltan páginas: el folio tiene {declared_total} y se escanearon {len(outcomes)}.")

        header_pages = [o for o in ordered if o.header_blocks]
        if not header_pages:
            observations.append("No se encontró la página con la cabecera (matrícula, superficie, linderos).")
            header = HeaderResult(data={}, confidence={}, observations=[])
        else:
            if len(header_pages) > 1:
                observations.append("Hay más de una página con cabecera: ¿se escanearon dos folios distintos?")
            first = header_pages[0]
            header = parse_header(first.header_blocks, first.diagnostics.get("header_width") or 0)
            observations.extend(header.observations)

        lines = [line for o in ordered for line in o.column_lines]
        titularidad = parse_titularidad(lines)
        confidence: Dict[str, Optional[float]] = dict(header.confidence)
        for i, asiento in enumerate(titularidad["asientos"]):
            confidence[f"titularidad_dominio.asientos.{i}"] = asiento.get("confianza")

        self._fill_gaps_with_llm(titularidad["asientos"], observations)

        asientos = titularidad["asientos"]
        if not asientos:
            observations.append("No se encontraron asientos en la columna A) Titularidad sobre el dominio.")
        declared_last = titularidad["ultimo_asiento"]
        numbers_read = [a["numero"] for a in asientos if a.get("numero") is not None]
        if declared_last is not None and numbers_read and max(numbers_read) != declared_last:
            observations.append(
                f"El folio indica 'Último Asiento Nro. {declared_last}' pero se leyó hasta el asiento {max(numbers_read)}."
            )

        low = sorted(k for k, v in confidence.items() if v is not None and v < self._threshold)
        if low:
            observations.append("Campos con baja confianza de lectura: revisar " + ", ".join(low) + ".")

        data = {
            "version": EXTRACTION_VERSION,
            "matricula": header.data.get("matricula") or {"numero": None, "estado": None, "zona": None},
            "tipo_inmueble": header.data.get("tipo_inmueble"),
            "ubicacion": header.data.get("ubicacion"),
            "designacion_s_tit": header.data.get("designacion_s_tit"),
            "superficie": header.data.get("superficie") or {"valor": None, "unidad": None, "texto_original": None},
            "medidas": header.data.get("medidas"),
            "linderos": header.data.get("linderos") or {"norte": None, "sud": None, "este": None, "oeste": None},
            "propiedad": header.data.get("propiedad"),
            "titularidad_dominio": {
                "antecedente_dominial": header.data.get("antecedente_dominial") or titularidad["antecedente_dominial"],
                "asientos": asientos,
                "ultimo_asiento": declared_last,
                "titulares_actuales": current_owners(asientos),
                "lineas_sin_asiento": titularidad["lineas_sin_asiento"],
            },
            "documento": {
                "fecha_emision": next((o.layout.issue_date for o in ordered if o.layout and o.layout.issue_date), None),
                "paginas_declaradas": declared_total,
                "paginas_recibidas": len(outcomes),
            },
            "confianza": confidence,
            "campos_baja_confianza": low,
            "observaciones": observations,
        }
        return data, (FolioStatus.NEEDS_REVIEW if observations else FolioStatus.READY)

    def _fill_gaps_with_llm(self, asientos: Sequence[Dict[str, Any]], observations: List[str]) -> None:
        """Only for asientos past the antecedent (numero > 0) missing people or
        act, and only values that literally appear in the asiento's OCR text are
        accepted -- the LLM may restructure, never invent."""
        if self._structurer is None or not self._structurer.is_configured():
            return
        for asiento in asientos:
            if (asiento.get("numero") or 0) == 0 or (asiento["personas"] and asiento["acto"]):
                continue
            text = asiento["texto"]
            try:
                proposal = self._structurer.structure(text)
            except AsientoStructurerUnavailableException as exc:
                observations.append(f"No se pudo usar IA para completar asientos: {exc.message}")
                return
            filled = []
            if not asiento["personas"]:
                for p in proposal.get("personas") or []:
                    name = str((p or {}).get("nombre") or "").strip()
                    if not name or not _fuzzy_in(name, text):
                        continue
                    ci = str(p.get("ci") or "").strip() or None
                    asiento["personas"].append({
                        "nombre": name,
                        "rol": "titular",
                        "estado_civil": p.get("estado_civil") or None,
                        "ci": ci if ci and re.sub(r"\D", "", ci) in re.sub(r"\D", "", text) else None,
                        "expedido": p.get("expedido") or None,
                        "proporcion": None,
                    })
                if asiento["personas"]:
                    filled.append("personas")
            for key in ("acto", "autoridad"):
                value = str(proposal.get(key) or "").strip()
                if not asiento.get(key) and value and _fuzzy_in(value, text):
                    asiento[key] = value
                    filled.append(key)
            doc = str(proposal.get("documento") or "").strip()
            if not asiento.get("documento") and doc and _fuzzy_in(doc, text):
                asiento["documento"] = {"descripcion": doc, "fecha": None}
                filled.append("documento")
            if filled:
                asiento["completado_por_ia"] = filled
