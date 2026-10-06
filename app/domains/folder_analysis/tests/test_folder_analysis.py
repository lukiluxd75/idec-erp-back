import io
import unittest
import uuid
from unittest.mock import patch
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import pypdfium2 as pdfium

from app.domains.folder_analysis.application.document_synchronizer import DocumentSynchronizer
from app.domains.folder_analysis.application.use_cases import capture_use_cases
from app.domains.folder_analysis.application.use_cases.document_use_cases import MAX_PAGES
from app.domains.folder_analysis.application.use_cases import (
    AddDocumentsToRegisteredFolderUseCase,
    ClearInboxUseCase,
    AnalyzeDocumentUseCase,
    ConsolidateDocumentsUseCase,
    CreateDocumentUseCase,
    CreateRegisteredFolderUseCase,
    DeleteCaptureUseCase,
    DeleteDocumentUseCase,
    DeleteRegisteredFolderUseCase,
    GetCaptureImageUseCase,
    GetDocumentUseCase,
    ListRegisteredFoldersUseCase,
    RegisteredFolderService,
    RemoveDocumentFromRegisteredFolderUseCase,
    SaveBoardToFolderUseCase,
    ReviewDocumentUseCase,
    RunServerReadingUseCase,
    GetFolderPhotoUseCase,
    SearchRegisteredFoldersUseCase,
    SetDocumentPagesUseCase,
    UpdateRegisteredFolderUseCase,
    UploadCapturesUseCase,
)
from app.domains.folder_analysis.domain.entities import (
    MAX_DOCUMENTS,
    MAX_NAME_LENGTH,
    Capture,
    CaptureStatus,
    DocumentPage,
    DocumentStatus,
    DocumentType,
    FolderDocument,
    PageStatus,
    QueuedJob,
    ReadingStage,
    RegisteredFolder,
)
from app.domains.folder_analysis.domain.exceptions import (
    CaptureNotAvailableException,
    CaptureNotFoundException,
    DocumentAlreadyFiledException,
    DocumentBusyException,
    DocumentNotFoundException,
    InvalidCaptureException,
    InvalidDocumentRequestException,
    InvalidRegisteredFolderException,
    RegisteredFolderNameTakenException,
    RegisteredFolderNotFoundException,
    TaxStructurerUnavailableException,
    VisionReadingUnavailableException,
)
from app.domains.folder_analysis.domain.extraction_profiles import (
    FOLDER_PROFILES,
    GENERIC_PROFILE,
    PROFILES,
    ExtractionProfile,
    profile_for,
)
from app.domains.folder_analysis.domain.folder_types import (
    DOCUMENT_TYPES,
    FOLDER_TYPES,
    DocumentField,
    FieldSource,
    document_fields,
    folder_type,
)
from app.domains.folder_analysis.domain.services.field_harvest import (
    from_seals,
    from_vision,
    harvest,
    observation,
    vision_wanted,
)
from app.domains.folder_analysis.domain.services.cadastral_code import to_gis_code
from app.domains.folder_analysis.domain.services.spanish_dates import (
    any_date,
    leading_number,
    to_iso_like,
    words_to_number,
)
from app.domains.folder_analysis.domain.ports import (
    CaptureRepositoryPort,
    DocumentRepositoryPort,
    ExtractionQueuePort,
    RegisteredFolderRepositoryPort,
    SealReadingPort,
    ServerReadingPort,
    TaxStructurerPort,
    VisionReadingPort,
)
from app.domains.folder_analysis.presentation.schemas.folder_analysis_schema import CatalogOut
from app.domains.folios.contracts import PageText, TextBlock
from app.domains.folios.domain.exceptions import OcrUnavailableException
from app.domains.folder_analysis.domain.services.document_progress import document_status
from app.domains.folder_analysis.domain.services.folio_result_mapper import to_folio_template
from app.domains.folder_analysis.domain.services.fur_parser import (
    low_confidence_fields,
    missing_fields,
    parse_fur,
)
from app.domains.folder_analysis.domain.services.plan_layout import (
    Segment,
    labelled_fields,
    table_regions,
    _split_scattered,
)
from app.domains.folder_analysis.domain.services.result_merger import conform, merge_pages
from app.domains.folder_analysis.domain.services.tax_result_mapper import to_tax_receipt_template
from app.domains.folder_analysis.domain.services.text import group_lines
from app.domains.folder_analysis.infrastructure import opencv_plan_reader
from app.domains.folder_analysis.infrastructure.ocr_plan_extractor import OcrPlanExtractor
from app.domains.folder_analysis.infrastructure.ocr_tax_extractor import OcrTaxExtractor
from app.domains.folder_analysis.infrastructure.ollama_fur_structurer import (
    OllamaFurStructurer,
    _json_object,
)
from app.domains.folder_analysis.infrastructure.opencv_seal_reader import OpenCvSealReader
from app.domains.folder_analysis.infrastructure.opencv_thumbnail import OpenCvThumbnail
from app.domains.folder_analysis.infrastructure.pdfium_rasterizer import PdfiumRasterizer

NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------- in-memory fakes

class FakeCaptures(CaptureRepositoryPort):
    def __init__(self):
        self.rows = {}

    def create(self, user_sub, file_name, mime, image, thumbnail):
        capture = Capture(str(uuid.uuid4()), user_sub, file_name, mime, CaptureStatus.INBOX, NOW)
        self.rows[capture.id] = (capture, image, thumbnail)
        return capture

    def get(self, capture_id, user_sub):
        row = self.rows.get(capture_id)
        return row[0] if row and row[0].user_sub == user_sub else None

    def get_many(self, capture_ids, user_sub):
        return [c for c in (self.get(i, user_sub) for i in capture_ids) if c]

    def list_by_status(self, user_sub, status):
        return [r[0] for r in self.rows.values() if r[0].user_sub == user_sub and r[0].status == status]

    def get_image(self, capture_id, user_sub, thumbnail=False):
        row = self.rows.get(capture_id)
        if not row or row[0].user_sub != user_sub:
            return None
        return (row[2], "image/jpeg") if thumbnail else (row[1], row[0].mime)

    def set_status(self, capture_ids, status):
        for i in capture_ids:
            capture, image, thumb = self.rows[i]
            self.rows[i] = (replace(capture, status=status), image, thumb)

    def delete(self, capture_id, user_sub):
        self.rows.pop(capture_id, None)

    def delete_many(self, capture_ids, user_sub):
        removed = 0
        for capture_id in capture_ids:
            row = self.rows.get(capture_id)
            if row and row[0].user_sub == user_sub:
                del self.rows[capture_id]
                removed += 1
        return removed


class FakeDocuments(DocumentRepositoryPort):
    def __init__(self):
        self.rows = {}
        self.stages = []
        self.clock = 0

    def create(self, user_sub, doc_type, capture_ids, folder_type=None):
        self.clock += 1
        born = NOW + timedelta(seconds=self.clock)
        doc = FolderDocument(str(uuid.uuid4()), user_sub, doc_type, DocumentStatus.DRAFT, born, born,
                             pages=[DocumentPage(c, i) for i, c in enumerate(capture_ids)],
                             folder_type=folder_type)
        self.rows[doc.id] = doc
        return doc

    def get(self, document_id, user_sub):
        doc = self.rows.get(document_id)
        return doc if doc and doc.user_sub == user_sub else None

    def list(self, user_sub, doc_type=None, folder_id=None):
        # Del mas nuevo al mas viejo, como el repositorio de verdad (su puerto lo dice: "Newest first").
        return [
            d
            for d in reversed(list(self.rows.values()))
            if d.user_sub == user_sub
            and (not doc_type or d.doc_type == doc_type)
            and (not folder_id or d.folder_id == folder_id)
        ]

    def replace_pages(self, document_id, capture_ids):
        doc = self.rows[document_id]
        self.rows[document_id] = replace(doc, status=DocumentStatus.DRAFT, extracted_data=None, reviewed_data=None,
                                         pages=[DocumentPage(c, i) for i, c in enumerate(capture_ids)])

    def delete(self, document_id):
        self.rows.pop(document_id, None)

    def mark_submitted(self, document_id, job_ids_by_page):
        doc = self.rows[document_id]
        pages = [replace(p, status=PageStatus.QUEUED, job_id=job_ids_by_page.get(p.page_index), result=None)
                 for p in doc.pages]
        self.rows[document_id] = replace(doc, pages=pages, status=DocumentStatus.QUEUED,
                                         extracted_data=None, reviewed_data=None)

    def save_progress(self, document_id, pages, status, extracted_data, error):
        doc = self.rows[document_id]
        # Como la base: una lectura que termina apaga el cartel de la etapa.
        stage = doc.stage if status in DocumentStatus.IN_PROGRESS else None
        self.rows[document_id] = replace(doc, pages=pages, status=status, error=error, stage=stage,
                                         extracted_data=extracted_data or doc.extracted_data)

    def set_stage(self, document_id, stage):
        # Las etapas por las que pasó, en orden, para poder comprobar que la pantalla se entera de la pasada del modelo de visión.
        self.stages.append(stage)
        if document_id in self.rows:
            self.rows[document_id] = replace(self.rows[document_id], stage=stage)

    def save_review(self, document_id, data):
        self.rows[document_id] = replace(self.rows[document_id], reviewed_data=data, status=DocumentStatus.REVIEWED)


class FakeQueue(ExtractionQueuePort):
    def __init__(self):
        self.submitted = []
        self.jobs = {}

    def submit(self, **kwargs):
        job_id = f"job-{len(self.submitted) + 1}"
        self.submitted.append(kwargs)
        self.jobs[job_id] = QueuedJob("pending")
        return job_id

    def status(self, job_ids):
        return {j: self.jobs[j] for j in job_ids if j in self.jobs}


class FakeExtractor(ServerReadingPort):
    """Stands in for whichever lane is read on the server (folio, tax receipt)."""

    def __init__(self, data=None, error=None, on_each_page=None):
        self.data, self.error, self.calls = data or {}, error, []
        # Runs right after the use case is told a page is finished, so a test can look at the document mid-reading.
        self._on_each_page = on_each_page

    def extract(self, pages, on_page=None):
        self.calls.append(list(pages))
        if self.error is not None:
            raise self.error
        for index in range(len(pages)):
            if on_page is not None:
                on_page(index)
            if self._on_each_page is not None:
                self._on_each_page(index)
        return self.data, ["una observación"]


class FakeSeals(SealReadingPort):
    """Los sellos ya leídos. Deja ver qué fotos se le pidieron y, por ser
    generador como el de verdad, que no se le piden más de las necesarias."""

    def __init__(self, texts):
        self.texts, self.pages, self.asked = texts, [], []

    def read(self, pages):
        self.pages.append(list(pages))
        for text in self.texts:
            self.asked.append(text)
            yield text


class FakeVision(VisionReadingPort):
    """El modelo de visión ya contestado. Deja ver cuántas fotos se le mostraron
    y qué campos se le preguntaron en cada una, que es lo que hay que cuidar:
    cada foto son veinte o treinta segundos de una computadora."""

    def __init__(self, answers, configured=True, fails=None):
        self.answers, self.configured, self.fails = answers, configured, fails
        self.asked = []

    def is_configured(self):
        return self.configured

    def read(self, page, fields):
        self.asked.append([spec.key for spec in fields])
        if self.fails is not None:
            raise self.fails
        return self.answers.pop(0) if self.answers else {}


def _pdf(pages: int = 1) -> bytes:
    """Un PDF de `pages` hojas, armado acá para no guardar un binario de prueba."""
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(300, 400)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _png() -> bytes:
    return cv2.imencode(".png", np.full((800, 600, 3), 255, np.uint8))[1].tobytes()


def _sheet_with_seal(centre=(430, 620), radius=90):
    """Una hoja con un sello redondo estampado en tinta violeta, como el de un
    notario: dos aros concéntricos y el número escrito derecho en el medio."""
    sheet = np.full((800, 600, 3), 255, np.uint8)
    cv2.putText(sheet, "SENOR NOTARIO DE FE PUBLICA", (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    ink = (150, 30, 120)
    cv2.circle(sheet, centre, radius, ink, 6)
    cv2.circle(sheet, centre, radius - 14, ink, 3)
    cv2.putText(sheet, "No.48", (centre[0] - 45, centre[1] + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, ink, 2)
    return cv2.imencode(".png", sheet)[1].tobytes()


def _uploader(captures) -> UploadCapturesUseCase:
    """The upload as the API wires it: thumbnails plus the PDF rasterizer, since
    a PDF arrives as one photo per page."""
    return UploadCapturesUseCase(captures, OpenCvThumbnail(), PdfiumRasterizer())


# ---------------------------------------------------------------- merger

# Real model outputs from the architects' PC (feasibility test with the user's photos).
FOLIO_PAGE_1 = {
    "registration_number": "3.01.1.01.0058438", "registration_status": "VIGENTE",
    "administrative_location": "CERCADO, PRIMERA, ITOCTA", "cadastre": None, "property_type": "Lote de Terreno",
    "location": "URB. ALALAY VALLE HERMOSO, MANZANA Y-1", "designation": "LOTE N° 24", "surface": "280.00 Metros 2",
    "measures": "NSC",
    "boundaries": {"north": "CON LA CALLE INNOMINADA", "south": "CON EL LOTE N° 3", "east": "CON EL LOTE N° 22",
                   "west": "CON LOS LOTES N° 1 Y 2"},
    "page": {"number": 1, "total": 2}, "unexpected_key": "dropped",
    "ownership_entries": [
        {"entry_number": "0", "owners": {"name": "MENESES RODRIGUEZ PATRICIA", "role": "Vendedor"}, "share": "1/1"},
        {"entry_number": "1", "owners": [{"name": "CRUZ COLOMI PATRICIO", "id_number": 4482143,
                                           "id_issued_at": "CBA", "marital_status": "soltero"}],
         "share": "1/1", "act": "Compra Venta"},
    ],
}
FOLIO_PAGE_2 = {
    "registration_number": None, "page": {"number": "2", "total": "2"},
    "ownership_entries": [
        {"entry_number": "1", "owners": [{"name": "CRUZ COLOMI PATRICIO", "id_number": "4482143",
                                           "id_issued_at": "CBA", "marital_status": "soltero"}],
         "share": "1/1", "act": "Compra Venta", "document": "Escrit. Priv. de fecha 12/10/1992",
         "filing": "Present.- No. 89304 de 27/10/2014"},
        {"entry_number": "2", "owners": [{"name": "RAMALLO RIVA ELOY"}], "share": "1/1"},
    ],
}


class TestResultMerger(unittest.TestCase):
    def test_conform_drops_unknown_keys_and_wraps_single_objects(self):
        shaped = conform(PROFILES["folio"].output_template, FOLIO_PAGE_1)
        self.assertNotIn("unexpected_key", shaped)
        self.assertEqual(shaped["ownership_entries"][0]["owners"][0]["name"], "MENESES RODRIGUEZ PATRICIA")
        self.assertEqual(shaped["ownership_entries"][1]["owners"][0]["id_number"], "4482143")
        self.assertIsNone(shaped["cadastre"])

    def test_folio_takes_header_from_first_page_and_merges_entries_across_pages(self):
        merged = merge_pages("folio", [FOLIO_PAGE_1, FOLIO_PAGE_2])
        self.assertEqual(merged["registration_number"], "3.01.1.01.0058438")
        self.assertEqual(merged["boundaries"]["west"], "CON LOS LOTES N° 1 Y 2")
        self.assertEqual([e["entry_number"] for e in merged["ownership_entries"]], ["0", "1", "2"])
        # The fuller copy of asiento 1 (page 2 continues it) wins.
        self.assertEqual(merged["ownership_entries"][1]["filing"], "Present.- No. 89304 de 27/10/2014")
        self.assertEqual(len(merged["pages_read"]), 2)

    def test_folio_drops_empty_asiento_headers_and_lone_x_values(self):
        page = {**FOLIO_PAGE_1, "cadastre": "x",
                "ownership_entries": FOLIO_PAGE_1["ownership_entries"] + [{"entry_number": "2", "owners": [], "share": "1/1"}]}
        merged = merge_pages("folio", [page])
        self.assertEqual([e["entry_number"] for e in merged["ownership_entries"]], ["0", "1"])
        self.assertIsNone(merged["cadastre"])

    def test_tax_receipt_first_filled_value_per_field(self):
        merged = merge_pages("tax_receipt", [
            {"receipt_number": "59122836", "cashier": "SWPAGOSQRBUN", "taxpayer": {"id_number": "7946847"}, "ufv": ""},
            {"ufv": "2.68451", "taxpayer": {"name": "ELOY RAMALLO RIVA"}},
        ])
        self.assertEqual(merged["receipt_number"], "59122836")
        self.assertEqual(merged["ufv"], "2.68451")
        self.assertEqual(merged["taxpayer"], {"type": None, "id_number": "7946847", "name": "ELOY RAMALLO RIVA"})

    def test_plan_keeps_every_generic_page(self):
        merged = merge_pages("plan", [{"document_type": "Plano", "full_text": "A"}, {"full_text": "B"}])
        self.assertEqual(merged["full_text"], "A\n\nB")
        self.assertEqual(len(merged["pages"]), 2)


class TestFolioResultMapper(unittest.TestCase):
    """Shape the folios pipeline answers with, taken from a real Cochabamba folio."""

    EXTRACTED = {
        "matricula": {"numero": "3.01.1.99.0022305", "estado": "VIGENTE", "zona": "CERCADO,PRIMERA,CIUDAD CBBA"},
        "catastro": "13103024000000000",
        "tipo_inmueble": "Lote de Terreno",
        "ubicacion": "ZONA LA CUADRAS,AVENIDA 9 DE ABRIL",
        "designacion_s_tit": "LOTE S/N,DISTRITO 11",
        "superficie": {"valor": 205.22, "unidad": "m2", "texto_original": "205.22Metros2"},
        "medidas": "NSC",
        "linderos": {"norte": "LOTE N 106", "sud": "AVENIDA 9 DE ABRIL", "este": "LOTE N 107", "oeste": "M. SILES"},
        "propiedad": "INDEFINIDA",
        "documento": {"fecha_emision": "01/12/2025", "paginas_declaradas": 4, "paginas_recibidas": 1},
        "campos_baja_confianza": ["titularidad_dominio.asientos.0"],
        "observaciones": ["Faltan páginas: el folio tiene 4 y se escanearon 1."],
        "titularidad_dominio": {
            "antecedente_dominial": "L:PCPA A:1998 P:0974",
            "ultimo_asiento": 2,
            "titulares_actuales": [{"nombre": "RONDAL ARIAS MIGUEL"}],
            "lineas_sin_asiento": ["sientoMumero:0"],
            "asientos": [
                {
                    "numero": 1,
                    "personas": [
                        {"nombre": "RONDAL ARIAS MIGUEL", "rol": "titular", "estado_civil": None,
                         "ci": "4482143", "expedido": "CBA", "proporcion": "1/2"},
                        {"nombre": "RONDAL BORDA MARGARITA", "rol": "titular", "estado_civil": "cas.",
                         "ci": None, "expedido": None, "proporcion": "1/2"},
                    ],
                    "acto": "Compra Venta",
                    "documento": {"descripcion": "Escrit. Pub. Nro. 127 de 03/04/1998", "fecha": "03/04/1998"},
                    "autoridad": "Not. Pub. JORGE CAMPOS CAMPOS",
                    "presentacion": {"numero": "14910", "fecha": "09/04/1998", "hora": "09:14:00"},
                    "confianza": 0.83,
                },
                # Cut off at the bottom edge of the photo: nothing but its number.
                {"numero": 2, "personas": [], "acto": None, "documento": None,
                 "autoridad": None, "presentacion": None, "confianza": None},
            ],
        },
    }
    FILL_LOG = {"fotos": [{"pagina_impresa": 1, "total_impreso": 4}]}

    def setUp(self):
        self.data = to_folio_template(self.EXTRACTED, self.FILL_LOG)

    def test_header_fields_use_the_lane_keys(self):
        self.assertEqual(self.data["registration_number"], "3.01.1.99.0022305")
        self.assertEqual(self.data["administrative_location"], "CERCADO,PRIMERA,CIUDAD CBBA")
        self.assertEqual(self.data["cadastre"], "13103024000000000")
        self.assertEqual(self.data["property_type"], "Lote de Terreno")
        self.assertEqual(self.data["prior_title"], "L:PCPA A:1998 P:0974")
        self.assertEqual(self.data["date"], "01/12/2025")
        self.assertEqual(self.data["boundaries"]["west"], "M. SILES")

    def test_surface_keeps_the_number_and_its_unit(self):
        self.assertEqual(self.data["surface"], "205.22 m2")

    def test_surface_falls_back_to_the_ocr_text(self):
        extracted = {**self.EXTRACTED, "superficie": {"valor": None, "unidad": None, "texto_original": "ilegible"}}
        self.assertEqual(to_folio_template(extracted)["surface"], "ilegible")

    def test_entries_and_owners(self):
        entry = self.data["ownership_entries"][0]
        self.assertEqual(entry["entry_number"], "1")
        self.assertEqual([o["name"] for o in entry["owners"]], ["RONDAL ARIAS MIGUEL", "RONDAL BORDA MARGARITA"])
        self.assertEqual(entry["owners"][0]["id_number"], "4482143")
        self.assertEqual(entry["owners"][0]["id_issued_at"], "CBA")
        self.assertEqual(entry["owners"][1]["marital_status"], "cas.")
        self.assertEqual(entry["share"], "1/2")
        self.assertEqual(entry["document"], "Escrit. Pub. Nro. 127 de 03/04/1998")
        self.assertEqual(entry["filing"], "No. 14910 de 09/04/1998 Hrs. 09:14:00")

    def test_an_entry_with_nothing_but_its_number_is_dropped(self):
        self.assertEqual([e["entry_number"] for e in self.data["ownership_entries"]], ["1"])

    def test_differing_shares_are_kept_together(self):
        people = [{"proporcion": "1/2"}, {"proporcion": "1/4"}, {"proporcion": "1/2"}]
        extracted = {"titularidad_dominio": {"asientos": [{"numero": 3, "personas": people, "acto": "Compra"}]}}
        self.assertEqual(to_folio_template(extracted)["ownership_entries"][0]["share"], "1/2 y 1/4")

    def test_what_the_rules_saw_is_kept_for_the_json_tab(self):
        reading = self.data["reading"]
        self.assertEqual(reading["source"], "ocr_rules")
        self.assertEqual(reading["unassigned_lines"], ["sientoMumero:0"])
        # Translated to the keys the review form renders, not the folios ones.
        self.assertEqual(reading["low_confidence_fields"], ["ownership_entries.0"])
        self.assertEqual(self.data["pages_read"], [{"number": "1", "total": "4"}])

    def test_low_confidence_keys_are_translated(self):
        extracted = {
            **self.EXTRACTED,
            "campos_baja_confianza": ["matricula.numero", "linderos.norte", "superficie", "no_existe"],
        }
        self.assertEqual(
            to_folio_template(extracted)["reading"]["low_confidence_fields"],
            ["registration_number", "boundaries.north", "surface"],
        )

    def test_asiento_positions_shift_when_an_empty_one_is_dropped(self):
        """The second asiento is header-only and disappears, so the third one is
        flagged at the position it actually has in the form."""
        person = [{"nombre": "ROJAS VARGAS JUAN", "rol": "titular", "proporcion": "1/1"}]
        asientos = [
            {"numero": 1, "personas": person, "acto": "Compra Venta"},
            {"numero": 2, "personas": [], "acto": None},
            {"numero": 3, "personas": person, "acto": "Compra Venta"},
        ]
        extracted = {
            "titularidad_dominio": {"asientos": asientos},
            "campos_baja_confianza": ["titularidad_dominio.asientos.2", "titularidad_dominio.asientos.1"],
        }
        result = to_folio_template(extracted)
        self.assertEqual([e["entry_number"] for e in result["ownership_entries"]], ["1", "3"])
        # asiento index 2 -> position 1; index 1 was dropped, so it is not flagged.
        self.assertEqual(result["reading"]["low_confidence_fields"], ["ownership_entries.1"])

    def test_the_raw_key_list_is_not_repeated_at_the_architect(self):
        """The form marks those fields one by one, so the observation that spells
        out the internal keys is dropped."""
        extracted = {
            **self.EXTRACTED,
            "observaciones": [
                "Faltan páginas: el folio tiene 4 y se escanearon 1.",
                "Campos con baja confianza de lectura: revisar titularidad_dominio.asientos.0.",
            ],
        }
        self.assertEqual(
            to_folio_template(extracted)["reading"]["observations"],
            ["Faltan páginas: el folio tiene 4 y se escanearon 1."],
        )

    def test_an_empty_extraction_still_has_the_shape_the_form_needs(self):
        data = to_folio_template({})
        self.assertIsNone(data["registration_number"])
        self.assertEqual(data["ownership_entries"], [])
        self.assertEqual(set(data["boundaries"]), {"north", "south", "east", "west"})


class TestDocumentProgress(unittest.TestCase):
    def test_failed_page_waits_for_the_others(self):
        pages = [DocumentPage("a", 0, PageStatus.FAILED, error="x"), DocumentPage("b", 1, PageStatus.PROCESSING)]
        self.assertEqual(document_status(pages)[0], DocumentStatus.PROCESSING)
        pages[1] = replace(pages[1], status=PageStatus.DONE)
        status, error = document_status(pages)
        self.assertEqual(status, DocumentStatus.FAILED)
        self.assertIn("página 1", error)

    def test_all_done_is_extracted(self):
        self.assertEqual(document_status([DocumentPage("a", 0, PageStatus.DONE)])[0], DocumentStatus.EXTRACTED)


# ---------------------------------------------------------------- use cases

class TestFolderAnalysisFlow(unittest.TestCase):
    def setUp(self):
        self.captures, self.documents, self.queue = FakeCaptures(), FakeDocuments(), FakeQueue()
        self.photos = _uploader(self.captures).execute(
            [(_png(), "image/png", "p1.png"), (_png(), "application/octet-stream", "p2.jpg")], "arq-1"
        )

    def _create(self, doc_type="folio", ids=None):
        return CreateDocumentUseCase(self.documents, self.captures).execute(
            doc_type, ids or [p.id for p in self.photos], "arq-1")

    def _read(self, document, extractor):
        """Runs the server-side reading of `document` with that extractor."""
        RunServerReadingUseCase(
            self.documents, self.captures, {document.doc_type: extractor}
        ).execute(document.id, "arq-1")

    def test_upload_rejects_non_images_and_normalizes_mime(self):
        with self.assertRaises(InvalidCaptureException):
            _uploader(self.captures).execute([(b"nope", "image/jpeg", "x")], "arq-1")
        self.assertEqual(self.photos[1].mime, "image/jpeg")

    def test_create_moves_photos_out_of_the_inbox_and_blocks_reuse(self):
        self._create()
        self.assertEqual(self.captures.list_by_status("arq-1", CaptureStatus.INBOX), [])
        with self.assertRaises(CaptureNotAvailableException):
            self._create("plan")
        with self.assertRaises(CaptureNotAvailableException):
            DeleteCaptureUseCase(self.captures).execute(self.photos[0].id, "arq-1")

    def test_other_users_cannot_see_the_document(self):
        doc = self._create()
        sync = DocumentSynchronizer(self.documents, self.queue)
        with self.assertRaises(DocumentNotFoundException):
            GetDocumentUseCase(self.documents, sync).execute(doc.id, "someone-else")

    @patch.object(DocumentType, "SERVER_READ", (DocumentType.FOLIO, DocumentType.TAX_RECEIPT))
    def test_full_cycle_analyze_sync_review(self):
        """The queue path, end to end. No lane takes it any more -- the plano was
        the last one and is read here now -- but the machinery stays for the
        documents that were already queued when it moved, so it is still tested:
        the lane is put back on the queue for the length of this test."""
        doc = self._create("plan")
        doc = AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        self.assertEqual(doc.status, DocumentStatus.QUEUED)
        self.assertEqual(len(self.queue.submitted), 2)

        with self.assertRaises(DocumentBusyException):
            AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")

        get = GetDocumentUseCase(self.documents, DocumentSynchronizer(self.documents, self.queue))
        self.queue.jobs["job-1"] = QueuedJob("done", {"document_type": "Plano", "full_text": "A"})
        self.queue.jobs["job-2"] = QueuedJob("processing")
        self.assertEqual(get.execute(doc.id, "arq-1").status, DocumentStatus.PROCESSING)

        self.queue.jobs["job-2"] = QueuedJob("done", {"full_text": "B"})
        doc = get.execute(doc.id, "arq-1")
        self.assertEqual(doc.status, DocumentStatus.EXTRACTED)
        self.assertEqual(doc.extracted_data["document_type"], "Plano")
        self.assertEqual(doc.extracted_data["full_text"], "A\n\nB")

        corrected = {**doc.extracted_data, "document_type": "Plano (revisado)"}
        doc = ReviewDocumentUseCase(self.documents).execute(doc.id, "arq-1", corrected)
        self.assertEqual(doc.status, DocumentStatus.REVIEWED)
        self.assertEqual(doc.current_data["document_type"], "Plano (revisado)")
        self.assertEqual(doc.extracted_data["document_type"], "Plano")

        with self.assertRaises(DocumentBusyException):
            AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        doc = AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1", force=True)
        self.assertEqual(doc.status, DocumentStatus.QUEUED)
        self.assertIsNone(doc.reviewed_data)

    def test_plan_is_read_on_the_server_and_queues_no_job(self):
        """The plano used to be queued to the architects' PCs for the vision
        model; it is read here with PaddleOCR and OpenCV like the other two."""
        doc = self._create("plan", [self.photos[0].id])
        doc = AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        self.assertEqual(self.queue.submitted, [])
        self.assertTrue(all(p.job_id is None for p in doc.pages))

        self._read(doc, FakeExtractor({"full_text": "PLANTA BAJA", "tables": []}))
        stored = self.documents.get(doc.id, "arq-1")
        self.assertEqual(stored.status, DocumentStatus.EXTRACTED)
        self.assertEqual(stored.extracted_data["full_text"], "PLANTA BAJA")

    def test_folio_is_read_on_the_server_and_queues_no_job(self):
        doc = self._create("folio")
        doc = AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        self.assertEqual(doc.status, DocumentStatus.QUEUED)
        self.assertEqual(self.queue.submitted, [])
        self.assertTrue(all(p.job_id is None for p in doc.pages))

        # A document with no job ids must not confuse the queue synchronizer.
        sync = DocumentSynchronizer(self.documents, self.queue)
        self.assertEqual(sync.refresh([doc])[0].status, DocumentStatus.QUEUED)

        extractor = FakeExtractor({"registration_number": "3.01.1.99.0022305"})
        self._read(doc, extractor)

        doc = self.documents.get(doc.id, "arq-1")
        self.assertEqual(doc.status, DocumentStatus.EXTRACTED)
        self.assertEqual(doc.extracted_data["registration_number"], "3.01.1.99.0022305")
        self.assertEqual([p.status for p in doc.pages], [PageStatus.DONE, PageStatus.DONE])
        # Both photos went in one call, in page order.
        self.assertEqual(len(extractor.calls), 1)
        self.assertEqual(len(extractor.calls[0]), 2)

    def test_tax_receipt_is_read_on_the_server_and_queues_no_job(self):
        """What changed for this lane: it no longer waits for a PC to pick a job
        up -- it is read here, like the folio."""
        doc = self._create("tax_receipt", [self.photos[0].id])
        doc = AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        self.assertEqual(doc.status, DocumentStatus.QUEUED)
        self.assertEqual(self.queue.submitted, [])
        self.assertTrue(all(p.job_id is None for p in doc.pages))

        self._read(doc, FakeExtractor({"receipt_number": "59122836"}))

        doc = self.documents.get(doc.id, "arq-1")
        self.assertEqual(doc.status, DocumentStatus.EXTRACTED)
        self.assertEqual(doc.extracted_data["receipt_number"], "59122836")
        self.assertEqual([p.status for p in doc.pages], [PageStatus.DONE])

    def test_each_lane_is_read_by_its_own_extractor(self):
        folio = self._create("folio", [self.photos[0].id])
        receipt = self._create("tax_receipt", [self.photos[1].id])
        for document in (folio, receipt):
            AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(document.id, "arq-1")

        readers = {
            "folio": FakeExtractor({"registration_number": "3.01.1.99.0022305"}),
            "tax_receipt": FakeExtractor({"receipt_number": "59122836"}),
        }
        for document in (folio, receipt):
            RunServerReadingUseCase(self.documents, self.captures, readers).execute(document.id, "arq-1")

        self.assertEqual(len(readers["folio"].calls), 1)
        self.assertEqual(len(readers["tax_receipt"].calls), 1)
        self.assertEqual(
            self.documents.get(folio.id, "arq-1").extracted_data["registration_number"], "3.01.1.99.0022305"
        )
        self.assertEqual(self.documents.get(receipt.id, "arq-1").extracted_data["receipt_number"], "59122836")

    def test_a_type_with_no_reader_is_left_alone_instead_of_failing(self):
        """Defensive: a lane declared as read on the server but not wired yet must
        not mark the document failed, which would lose the architect's photos."""
        doc = self._create("tax_receipt", [self.photos[0].id])
        AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        RunServerReadingUseCase(self.documents, self.captures, {}).execute(doc.id, "arq-1")
        self.assertEqual(self.documents.get(doc.id, "arq-1").status, DocumentStatus.QUEUED)

    def test_pages_are_marked_as_they_are_read(self):
        """The screen shows how many photos are left, so each one is stored as
        soon as it is read instead of all of them at the end."""
        doc = self._create("folio")
        AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")

        seen = []
        extractor = FakeExtractor(
            {"registration_number": "X"},
            on_each_page=lambda _i: seen.append(
                [p.status for p in self.documents.get(doc.id, "arq-1").pages]
            ),
        )
        self._read(doc, extractor)

        self.assertEqual(seen, [
            [PageStatus.DONE, PageStatus.PROCESSING],
            [PageStatus.DONE, PageStatus.DONE],
        ])
        self.assertEqual(self.documents.get(doc.id, "arq-1").status, DocumentStatus.EXTRACTED)

    def test_a_failure_saving_progress_does_not_lose_the_reading(self):
        doc = self._create("folio")
        AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        original = self.documents.save_progress
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:  # the first per-page save
                raise RuntimeError("database hiccup")
            return original(*args, **kwargs)

        self.documents.save_progress = flaky
        self._read(doc, FakeExtractor({"registration_number": "X"}))
        self.documents.save_progress = original

        doc = self.documents.get(doc.id, "arq-1")
        self.assertEqual(doc.status, DocumentStatus.EXTRACTED)
        self.assertEqual(doc.extracted_data["registration_number"], "X")

    def test_the_queue_synchronizer_keeps_its_hands_off_a_folio(self):
        """With every photo read but the data not assembled yet, the queue's own
        rule reads the pages as finished and would store an empty result over
        the reading still running. It only runs at all because another document
        IS queue-driven, which is the everyday case on this screen."""
        folio = self._create("folio", [self.photos[0].id])
        AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(folio.id, "arq-1")
        plan = self._create("plan", [self.photos[1].id])
        AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(plan.id, "arq-1")

        mid_reading = replace(
            self.documents.get(folio.id, "arq-1"),
            pages=[DocumentPage(p.capture_id, p.page_index, PageStatus.DONE) for p in folio.pages],
            status=DocumentStatus.PROCESSING,
        )
        queued_plan = self.documents.get(plan.id, "arq-1")

        refreshed = DocumentSynchronizer(self.documents, self.queue).refresh([mid_reading, queued_plan])

        self.assertEqual(refreshed[0].status, DocumentStatus.PROCESSING)
        self.assertIsNone(refreshed[0].extracted_data)
        # Nothing was written over the reading that is still running.
        self.assertIsNone(self.documents.get(folio.id, "arq-1").extracted_data)

    def test_folio_reading_failure_is_stored_on_the_document(self):
        doc = self._create("folio")
        AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        extractor = FakeExtractor(error=OcrUnavailableException("El servicio OCR no respondió a tiempo."))
        self._read(doc, extractor)

        doc = self.documents.get(doc.id, "arq-1")
        self.assertEqual(doc.status, DocumentStatus.FAILED)
        self.assertIn("OCR", doc.error)

    def test_an_unexpected_error_does_not_escape_the_background_task(self):
        doc = self._create("folio")
        AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        extractor = FakeExtractor(error=RuntimeError("boom"))
        self._read(doc, extractor)
        self.assertEqual(self.documents.get(doc.id, "arq-1").status, DocumentStatus.FAILED)

    def test_a_stale_run_does_not_touch_a_document_that_moved_on(self):
        doc = self._create("folio")
        extractor = FakeExtractor({"registration_number": "X"})
        # Never analyzed: the document is still a draft, so this run is stale.
        self._read(doc, extractor)
        self.assertEqual(extractor.calls, [])
        self.assertEqual(self.documents.get(doc.id, "arq-1").status, DocumentStatus.DRAFT)

    def test_pages_can_be_changed_and_deleting_returns_photos_to_inbox(self):
        doc = self._create("folio", [self.photos[0].id])
        doc = SetDocumentPagesUseCase(self.documents, self.captures).execute(
            doc.id, [self.photos[1].id, self.photos[0].id], "arq-1")
        self.assertEqual([p.capture_id for p in doc.pages], [self.photos[1].id, self.photos[0].id])
        DeleteDocumentUseCase(self.documents, self.captures).execute(doc.id, "arq-1")
        self.assertEqual(len(self.captures.list_by_status("arq-1", CaptureStatus.INBOX)), 2)

    def test_review_requires_an_analyzed_document(self):
        doc = self._create()
        with self.assertRaises(DocumentBusyException):
            ReviewDocumentUseCase(self.documents).execute(doc.id, "arq-1", {"x": 1})


# ---------------------------------------------------------------- tax receipt lane

def _fur_blocks(rows, confidence=0.99):
    """Blocks of a receipt laid out row by row: (text, x0, x1) per row, 20 px
    apart and 12 px tall, which is what group_lines() needs to see lines."""
    blocks = []
    for row, items in enumerate(rows):
        for text, x0, x1 in items:
            y0 = 20 * row
            blocks.append(TextBlock(text, confidence, float(x0), float(y0), float(x1), float(y0 + 12)))
    return blocks


# A FUR as the OCR reads it: values next to their label, and one row of stacked boxes (Nº INMUEBLE / COD.
FUR_ROWS = [
    [("FUR - COMPROBANTE DE PAGO", 100, 400), ("Nº 59122836", 500, 650)],
    [("GAM - COCHABAMBA", 100, 300)],
    [("ENTIDAD RECAUDADORA:", 10, 140), ("BANCO UNION", 150, 260), ("CORRESP.:", 300, 360), ("0012", 365, 400)],
    [("SUCURSAL:", 10, 70), ("CENTRAL", 80, 140), ("AGENCIA:", 160, 220), ("A-15", 225, 260),
     ("CAJERO:", 280, 330), ("J. PEREZ", 335, 400), ("FOLIO:", 420, 460), ("7788", 465, 500)],
    [("FECHA:", 10, 50), ("12/03/2024 10:35", 55, 180)],
    [("CONTRIBUYENTE:", 10, 100), ("NATURAL CI-4482143 CRUZ COLOMI PATRICIO", 105, 400)],
    [("INMUEBLES IMPBI 2024 TOTAL", 10, 200)],
    [("Nº INMUEBLE", 10, 80), ("COD. CAT.", 120, 180), ("CLASE", 220, 260), ("TIPO PROPIEDAD", 300, 390)],
    [("123456", 10, 60), ("3-01-1-01-0058", 120, 200), ("URBANO", 220, 270), ("PROPIA", 300, 350)],
    [("UBICACION:", 10, 70), ("URB. ALALAY VALLE HERMOSO, MANZANA Y-1", 75, 400)],
    [("SUP. TERRENO:", 10, 90), ("280.00 m2", 95, 160),
     ("SUP. TOTAL CONSTRUCCION:", 200, 350), ("120.50 m2", 355, 420)],
    [("FACTOR ANTIGUEDAD:", 10, 110), ("0.85", 115, 150), ("UFV:", 200, 230), ("2.68451", 235, 300)],
    [("BASE IMPONIBLE:", 10, 100), ("350000.00", 105, 180)],
    [("IMPUESTO DETERMINADO:", 10, 130), ("1050.00", 135, 200)],
    [("EXENCION:", 10, 70), ("0.00", 75, 110)],
    [("DESCUENTO 10%:", 10, 100), ("105.00", 105, 160)],
    [("DESCUENTO APP 5%:", 10, 110), ("52.50", 115, 165)],
    [("IMPORTE A PAGAR:", 10, 110), ("892.50", 115, 170)],
    [("MONTO PAGADO:", 10, 100), ("892.50", 105, 160)],
    [("SALDO GESTION:", 10, 100), ("0.00", 105, 140)],
]


def _rows_with_unreadable_cashier_label():
    """The same receipt with the CAJERO label unreadable: its value is still on
    the photo, so the rules leave the field empty and only the LLM pass can
    place it -- which is exactly what the pass is for."""
    rows = []
    for row in FUR_ROWS:
        if "CAJERO:" in [text for text, _x0, _x1 in row]:
            rows.append([("SUCURSAL:", 10, 70), ("CENTRAL", 80, 140), ("AGENCIA:", 160, 220), ("A-15", 225, 260),
                         ("FOLIO:", 420, 460), ("7788", 465, 500)])
            rows.append([("J. PEREZ", 280, 400)])
        else:
            rows.append(row)
    return rows


class TestFurParser(unittest.TestCase):
    """The rules over the OCR of one receipt: no OCR service and no LLM."""

    def setUp(self):
        self.reading = parse_fur([_fur_blocks(FUR_ROWS)], 0.85)

    def test_values_printed_next_to_their_label(self):
        data = self.reading.data
        self.assertEqual(data["collecting_entity"], "BANCO UNION")
        self.assertEqual(data["correspondent"], "0012")
        self.assertEqual(data["branch"], "CENTRAL")
        self.assertEqual(data["agency"], "A-15")
        self.assertEqual(data["cashier"], "J. PEREZ")
        self.assertEqual(data["folio"], "7788")
        self.assertEqual(data["paid_at"], "12/03/2024 10:35")
        self.assertEqual(data["location"], "URB. ALALAY VALLE HERMOSO, MANZANA Y-1")
        self.assertEqual(data["land_area"], "280.00 m2")
        self.assertEqual(data["built_area"], "120.50 m2")
        self.assertEqual(data["age_factor"], "0.85")

    def test_a_value_stops_at_the_next_label(self):
        """'BANCO UNION' must not swallow the CORRESP. box printed beside it."""
        self.assertEqual(self.reading.data["collecting_entity"], "BANCO UNION")
        self.assertEqual(self.reading.data["cashier"], "J. PEREZ")

    def test_values_printed_under_their_label(self):
        """A row of stacked boxes: each value belongs to the box above it and not
        to its neighbour's."""
        data = self.reading.data
        self.assertEqual(data["property_number"], "123456")
        self.assertEqual(data["cadastral_code"], "3-01-1-01-0058")
        self.assertEqual(data["property_class"], "URBANO")
        self.assertEqual(data["ownership_type"], "PROPIA")

    def test_amounts_are_kept_as_printed(self):
        data = self.reading.data
        self.assertEqual(data["ufv"], "2.68451")
        self.assertEqual(data["taxable_base"], "350000.00")
        self.assertEqual(data["assessed_tax"], "1050.00")
        self.assertEqual(data["exemption"], "0.00")
        self.assertEqual(data["discount_10"], "105.00")
        self.assertEqual(data["discount_app_5"], "52.50")
        self.assertEqual(data["amount_due"], "892.50")
        self.assertEqual(data["amount_paid"], "892.50")
        self.assertEqual(data["balance"], "0.00")

    def test_the_lines_printed_without_a_label(self):
        data = self.reading.data
        # The number is printed on the title's line: it goes to its own field and is taken out of the type.
        self.assertEqual(data["receipt_type"], "FUR - COMPROBANTE DE PAGO")
        self.assertEqual(data["receipt_number"], "59122836")
        self.assertEqual(data["municipality"], "GAM - COCHABAMBA")
        self.assertEqual(data["concept"], "INMUEBLES IMPBI 2024 TOTAL")
        self.assertEqual(data["tax_year"], "2024")

    def test_the_taxpayer_line_is_split_into_its_three_pieces(self):
        self.assertEqual(
            self.reading.data["taxpayer"],
            {"type": "NATURAL", "id_number": "4482143", "name": "CRUZ COLOMI PATRICIO"},
        )

    def test_a_receipt_that_adds_up_has_nothing_to_report(self):
        self.assertEqual(self.reading.observations, [])
        self.assertEqual(sorted(missing_fields(self.reading)), [])

    def test_a_liquidation_that_does_not_add_up_is_reported(self):
        rows = [row for row in FUR_ROWS if "IMPORTE A PAGAR:" not in [t for t, _a, _b in row]]
        rows.append([("IMPORTE A PAGAR:", 10, 110), ("992.50", 115, 170)])
        reading = parse_fur([_fur_blocks(rows)], 0.85)
        self.assertTrue(any("no cuadra" in note for note in reading.observations))
        self.assertTrue(any("no coinciden" in note for note in reading.observations))

    def test_a_photo_that_is_not_a_receipt_says_so(self):
        reading = parse_fur([_fur_blocks([[("UNA HOJA CUALQUIERA", 10, 200)]])], 0.85)
        self.assertTrue(any("no se reconoció" in note.lower() for note in reading.observations))

    def test_low_confidence_values_are_listed_by_their_form_key(self):
        reading = parse_fur([_fur_blocks(FUR_ROWS, confidence=0.4)], 0.85)
        self.assertIn("amount_due", reading.confidence)
        self.assertIn("taxpayer.name", low_confidence_fields(reading, 0.85))
        self.assertTrue(any("baja confianza" in note for note in reading.observations))

    def test_a_label_and_its_value_in_one_block(self):
        """What the OCR service actually returns on these forms: the label, its
        colon and the value as ONE block, with the spaces dropped."""
        rows = [
            [("FUR-COMPROBANTEDEPAGO No59122836", 100, 650)],
            [("ENTIDADRECAUDADORA:BANCOUNION", 10, 260), ("CORRESP.0012", 300, 400)],
            [("BASEIMPONIBLE:350000.00", 10, 180)],
            [("DESCUENT010%:105.00", 10, 160)],
            [("IMP0RTEAPAGAR892.50", 10, 170)],
            [("UBICACIONURB.ALALAY VALLE HERMOSO", 10, 400)],
        ]
        reading = parse_fur([_fur_blocks(rows)], 0.85)
        self.assertEqual(reading.data["receipt_type"], "FUR-COMPROBANTEDEPAGO")
        self.assertEqual(reading.data["receipt_number"], "59122836")
        self.assertEqual(reading.data["collecting_entity"], "BANCOUNION")
        self.assertEqual(reading.data["correspondent"], "0012")
        self.assertEqual(reading.data["taxable_base"], "350000.00")
        # The label ends in a sign that is not a letter or a digit: it must not be left at the front of the value.
        self.assertEqual(reading.data["discount_10"], "105.00")
        self.assertEqual(reading.data["location"], "URB.ALALAY VALLE HERMOSO")

    def test_a_label_the_ocr_read_with_digits_for_letters(self):
        """'IMPUEST0 DETERMINAD0', 'M0NT0 PAGAD0', 'FOLI0': the classic O/0 swap
        must not lose the field."""
        rows = [
            [("IMPUEST0 DETERMINAD0:", 10, 130), ("1050.00", 135, 200)],
            [("M0NT0 PAGAD0:", 10, 100), ("892.50", 105, 160)],
            [("FOLI0:", 10, 60), ("7788", 65, 100)],
        ]
        reading = parse_fur([_fur_blocks(rows)], 0.85)
        self.assertEqual(reading.data["assessed_tax"], "1050.00")
        self.assertEqual(reading.data["amount_paid"], "892.50")
        self.assertEqual(reading.data["folio"], "7788")

    def test_a_second_photo_only_fills_gaps(self):
        """The first photo that has a value wins, so re-photographing a receipt
        cannot overwrite what was already read."""
        first = [[("FUR - COMPROBANTE DE PAGO", 100, 400)], [("IMPORTE A PAGAR:", 10, 110), ("892.50", 115, 170)]]
        second = [[("IMPORTE A PAGAR:", 10, 110), ("111.11", 115, 170)], [("FOLIO:", 10, 60), ("7788", 65, 100)]]
        reading = parse_fur([_fur_blocks(first), _fur_blocks(second)], 0.85)
        self.assertEqual(reading.data["amount_due"], "892.50")
        self.assertEqual(reading.data["folio"], "7788")


class FakeStructurer(TaxStructurerPort):
    def __init__(self, proposal=None, error=None, configured=True):
        self.proposal, self.error, self.configured = proposal or {}, error, configured
        self.asked = []

    def is_configured(self):
        return self.configured

    def structure(self, ocr_text, missing):
        self.asked.append((ocr_text, list(missing)))
        if self.error is not None:
            raise self.error
        return self.proposal


class TestOcrTaxExtractor(unittest.TestCase):
    """The lane's reading end to end, with the OCR step and the LLM step faked."""

    def _extractor(self, structurer=None, rows=None):
        blocks = _fur_blocks(rows if rows is not None else FUR_ROWS)
        return OcrTaxExtractor(
            structurer=structurer,
            confidence_threshold=0.85,
            read_page=lambda _content, _name: PageText(blocks=blocks, width=800, height=600),
        )

    def test_the_rules_alone_fill_the_stored_shape(self):
        data, observations = self._extractor().extract([b"foto"])
        self.assertEqual(data["amount_due"], "892.50")
        self.assertEqual(data["taxpayer"]["name"], "CRUZ COLOMI PATRICIO")
        self.assertEqual(observations, [])
        self.assertEqual(data["reading"]["source"], "ocr_rules")
        self.assertEqual(data["reading"]["low_confidence_fields"], [])
        self.assertEqual(data["reading"]["fields_filled_by_ai"], [])
        self.assertIn("INMUEBLES IMPBI 2024 TOTAL", data["reading"]["ocr_lines"])

    def test_each_photo_is_reported_as_it_is_read(self):
        seen = []
        self._extractor().extract([b"a", b"b"], on_page=seen.append)
        self.assertEqual(seen, [0, 1])

    def test_the_llm_is_only_asked_for_what_the_rules_could_not_read(self):
        rows = _rows_with_unreadable_cashier_label()
        structurer = FakeStructurer({"cashier": "J. PEREZ"})
        data, _observations = self._extractor(structurer, rows).extract([b"foto"])

        asked_text, asked_keys = structurer.asked[0]
        self.assertIn("cashier", asked_keys)
        self.assertNotIn("amount_due", asked_keys)
        self.assertIn("BANCO UNION", asked_text)
        self.assertEqual(data["cashier"], "J. PEREZ")
        self.assertEqual(data["reading"]["fields_filled_by_ai"], ["cashier"])

    def test_a_value_the_llm_invented_is_discarded(self):
        rows = _rows_with_unreadable_cashier_label()
        structurer = FakeStructurer({"cashier": "ALGUIEN QUE NO ESTA EN LA FOTO"})
        data, _observations = self._extractor(structurer, rows).extract([b"foto"])
        self.assertIsNone(data["cashier"])
        self.assertEqual(data["reading"]["fields_filled_by_ai"], [])

    def test_the_reading_survives_the_llm_being_unavailable(self):
        rows = _rows_with_unreadable_cashier_label()
        structurer = FakeStructurer(error=TaxStructurerUnavailableException("Ninguna computadora conectada."))
        data, observations = self._extractor(structurer, rows).extract([b"foto"])
        self.assertEqual(data["amount_due"], "892.50")
        self.assertTrue(any("IA" in note for note in observations))

    def test_with_no_llm_configured_nothing_is_asked(self):
        structurer = FakeStructurer(configured=False)
        self._extractor(structurer).extract([b"foto"])
        self.assertEqual(structurer.asked, [])

    def test_an_ocr_failure_reaches_the_use_case(self):
        def boom(_content, _name):
            raise OcrUnavailableException("El servicio OCR no respondió a tiempo.")

        extractor = OcrTaxExtractor(structurer=None, confidence_threshold=0.85, read_page=boom)
        with self.assertRaises(OcrUnavailableException):
            extractor.extract([b"foto"])


class TestTaxResultMapper(unittest.TestCase):
    def test_an_empty_reading_still_has_the_shape_the_form_needs(self):
        data = to_tax_receipt_template(parse_fur([], 0.85), 0.85)
        self.assertEqual(set(PROFILES["tax_receipt"].output_template) - set(data), set())
        self.assertEqual(data["taxpayer"], {"type": None, "id_number": None, "name": None})
        self.assertEqual(data["reading"]["low_confidence_fields"], [])

    def test_what_the_ai_filled_is_named_for_the_review_screen(self):
        reading = parse_fur([_fur_blocks(FUR_ROWS)], 0.85)
        data = to_tax_receipt_template(reading, 0.85, ["cashier", "taxpayer.name"])
        self.assertEqual(data["reading"]["fields_filled_by_ai"], ["cashier", "taxpayer.name"])
        self.assertEqual(data["reading"]["labels_not_found"], [])


class TestOllamaAnswer(unittest.TestCase):
    """The model is asked for JSON, but it is a reasoning model: it may still wrap
    the object in its thinking, and one stray word would throw the reading away."""

    def test_the_object_is_taken_out_of_whatever_surrounds_it(self):
        self.assertEqual(
            _json_object('<think>veamos el texto</think>\n{"cashier": "J. PEREZ"}'),
            '{"cashier": "J. PEREZ"}',
        )

    def test_a_clean_answer_is_left_alone(self):
        self.assertEqual(_json_object('{"cashier": null}'), '{"cashier": null}')

    def test_no_model_configured_turns_the_pass_off(self):
        """One line of .env leaves the lane on its rules alone."""
        self.assertFalse(OllamaFurStructurer(model="", host_provider=lambda _m: ["http://pc"]).is_configured())
        self.assertTrue(
            OllamaFurStructurer(model="un-modelo", host_provider=lambda _m: ["http://pc"]).is_configured()
        )

    def test_an_answer_with_no_object_is_handed_back_to_fail_on_its_own(self):
        self.assertEqual(_json_object("no tengo nada"), "no tengo nada")
        self.assertEqual(_json_object(""), "")


# ---------------------------------------------------------------- plano lane

def _sheet(tilt_deg: float = 0.0):
    """A plano like the ones that are scanned: a drawing whose walls are long
    straight strokes, a cuadro de superficies in one corner and a rótulo in the
    other. Returns the photo and the blocks a clean OCR would answer with."""
    width, height = 1800, 1200
    sheet = np.full((height, width, 3), 255, np.uint8)
    blocks = []

    def write(text, x, y, scale=0.7, thickness=2):
        cv2.putText(sheet, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness, cv2.LINE_AA)
        (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
        blocks.append(TextBlock(text, 0.95, float(x), float(y - h), float(x + w), float(y)))

    def grid(rows, columns, cells):
        for y in rows:
            cv2.line(sheet, (columns[0], y), (columns[-1], y), (0, 0, 0), 3)
        for x in columns:
            cv2.line(sheet, (x, rows[0]), (x, rows[-1]), (0, 0, 0), 3)
        for r, row in enumerate(cells):
            for c, cell in enumerate(row):
                write(cell, columns[c] + 15, rows[r] + 42, scale=0.6)

    # The drawing: walls as long as any rule, and no company above them.
    for y in (200, 450, 700):
        cv2.line(sheet, (80, y), (900, y), (0, 0, 0), 5)
    for x in (80, 900):
        cv2.line(sheet, (x, 200), (x, 700), (0, 0, 0), 5)
    write("PLANTA ALTA", 300, 160, scale=1.5, thickness=4)
    write("DORMITORIO", 200, 350)
    write("ESC: 1:100", 80, 780)
    write("PROPIETARIO: JUAN PEREZ", 80, 830)

    grid([140, 200, 260, 320], [1150, 1450, 1720],
         [["AMBIENTE", "SUP. m2"], ["DORMITORIO", "18.40"], ["SALA", "31.75"]])
    grid([900, 960, 1020, 1080], [1150, 1400, 1720],
         [["COD CAT", "04-015-022"], ["MANZANO", "17"], ["ESCALA", "1:100"]])

    if tilt_deg:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), tilt_deg, 1.0)
        sheet = cv2.warpAffine(sheet, matrix, (width, height), borderValue=(255, 255, 255))
    photo = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
    return photo, blocks, width, height


class TestPlanLayout(unittest.TestCase):
    """The pure half: what makes a cuadro a cuadro, and a value a value."""

    def test_a_lone_wall_is_not_a_cuadro(self):
        walls = [Segment(position=200, start=80, end=900), Segment(position=700, start=80, end=900)]
        self.assertEqual(table_regions(walls, 1200), [])

    def test_three_rules_over_the_same_paper_are_a_cuadro(self):
        rules = [Segment(position=y, start=1150, end=1720) for y in (140, 200, 260)]
        region = table_regions(rules, 1200)[0]
        self.assertEqual((region.top, region.bottom), (140, 260))
        self.assertEqual(region.left, 1150)

    def test_a_wall_across_the_sheet_does_not_split_a_cuadro(self):
        """The wall runs between two rows of a cuadro on the other side of the
        sheet: the cuadro has to survive it."""
        rules = [Segment(position=y, start=1150, end=1720) for y in (140, 200, 260, 320)]
        rules.append(Segment(position=200, start=80, end=900))
        regions = table_regions(rules, 1200)
        self.assertEqual(len(regions), 1)
        self.assertEqual(len(regions[0].rows), 4)

    def test_a_scale_is_not_a_label_with_its_value(self):
        blocks = [TextBlock("ESCALA 1:100", 0.9, 0, 0, 200, 20)]
        self.assertEqual(labelled_fields(group_lines(blocks)), [])

    def test_a_label_keeps_a_value_that_has_a_colon(self):
        blocks = [TextBlock("ESC: 1:100", 0.9, 0, 0, 200, 20)]
        self.assertEqual(labelled_fields(group_lines(blocks)), [{"name": "ESC", "value": "1:100"}])

    def test_a_row_of_scattered_notes_is_not_one_field(self):
        """A rótulo strip along the bottom of the sheet: ESC, the planta name and a
        handful of room notes all sit at the same height because there was nowhere
        else to put them. group_lines() alone reads that as one line, so ESC would
        swallow every note after it as its own value; the gap between one note and
        the next is what tells them apart."""
        row = [
            TextBlock("ESC:1:100", 0.9, 80, 780, 200, 792),
            TextBlock("PLANTA", 0.9, 300, 780, 380, 792),
            TextBlock("SEMISOTANO", 0.9, 385, 780, 520, 792),
            TextBlock("BAULERA", 0.9, 800, 780, 900, 792),
            TextBlock("2.", 0.9, 905, 780, 925, 792),
        ]
        lines = _split_scattered(group_lines(row))
        self.assertEqual(
            [[b.text for b in line] for line in lines],
            [["ESC:1:100"], ["PLANTA", "SEMISOTANO"], ["BAULERA", "2."]],
        )
        self.assertEqual(labelled_fields(lines), [{"name": "ESC", "value": "1:100"}])


class TestOcrPlanExtractor(unittest.TestCase):
    """The lane end to end with the OCR service faked -- OpenCV is the real one."""

    def _extractor(self, blocks, width, height):
        return OcrPlanExtractor(
            read_page=lambda _content, _name=None: PageText(blocks=blocks, width=width, height=height)
        )

    def test_the_sheet_is_read_into_text_fields_and_cuadros(self):
        photo, blocks, width, height = _sheet()
        data, observations = self._extractor(blocks, width, height).extract([photo])

        page = data["pages"][0]
        self.assertEqual(page["document_type"], "PLANTA ALTA")
        self.assertEqual(page["tables"][0], [["AMBIENTE", "SUP. m2"], ["DORMITORIO", "18.40"], ["SALA", "31.75"]])
        self.assertEqual(page["tables"][1][0], ["COD CAT", "04-015-022"])
        self.assertIn({"name": "PROPIETARIO", "value": "JUAN PEREZ"}, page["fields"])
        self.assertIn("PLANTA ALTA", page["full_text"])
        self.assertEqual(observations, [])

    def test_the_walls_of_the_drawing_are_not_read_as_a_cuadro(self):
        photo, blocks, width, height = _sheet()
        data, _observations = self._extractor(blocks, width, height).extract([photo])
        self.assertEqual(data["reading"]["tables_found"], 2)

    def test_the_stored_shape_is_the_one_the_lane_always_had(self):
        """The vision model answered with document_type / full_text / fields /
        tables; the review screen and the stored documents expect no less."""
        photo, blocks, width, height = _sheet()
        data, _observations = self._extractor(blocks, width, height).extract([photo])
        self.assertEqual(set(data), {"document_type", "full_text", "pages", "reading"})
        self.assertEqual(set(data["pages"][0]), {"page", "document_type", "full_text", "fields", "tables"})
        self.assertEqual(data["reading"]["engine"], "paddleocr+opencv")

    def test_a_crooked_photo_is_straightened_before_it_is_read(self):
        photo, _blocks, _width, _height = _sheet(tilt_deg=2.0)
        straightened = opencv_plan_reader.deskew(photo)
        self.assertTrue(straightened.corrected)
        self.assertLess(abs(straightened.angle), 4.0)
        rules = opencv_plan_reader.row_rules(straightened.frame)
        self.assertEqual(len(table_regions(rules, straightened.frame.shape[0])), 2)

    def test_a_photo_tilted_beyond_sense_is_left_as_it_came(self):
        photo, _blocks, _width, _height = _sheet(tilt_deg=25.0)
        straightened = opencv_plan_reader.deskew(photo)
        self.assertFalse(straightened.corrected)
        self.assertEqual(straightened.image, photo)

    def test_a_page_the_ocr_cannot_read_is_reported_and_the_rest_are_read(self):
        photo, blocks, width, height = _sheet()
        answers = [
            PageText(blocks=[], width=width, height=height),
            PageText(blocks=blocks, width=width, height=height),
        ]
        extractor = OcrPlanExtractor(read_page=lambda _content, _name=None: answers.pop(0))

        data, observations = extractor.extract([photo, photo])
        self.assertEqual(observations, ["La página 1 no tiene texto que el OCR pueda leer."])
        self.assertEqual(data["pages"][0]["full_text"], "")
        self.assertIn("PLANTA ALTA", data["pages"][1]["full_text"])
        self.assertEqual(data["document_type"], "PLANTA ALTA")

    def test_each_photo_is_reported_as_it_is_read(self):
        photo, blocks, width, height = _sheet()
        seen = []
        self._extractor(blocks, width, height).extract([photo, photo], on_page=seen.append)
        self.assertEqual(seen, [0, 1])

    def test_a_page_opencv_cannot_open_still_gets_its_text(self):
        """No OpenCV, no cuadros -- but the OCR text is not lost with them."""
        _photo, blocks, width, height = _sheet()
        data, _observations = self._extractor(blocks, width, height).extract([b"esto no es una imagen"])
        self.assertIn("PLANTA ALTA", data["pages"][0]["full_text"])
        self.assertEqual(data["pages"][0]["tables"], [])



# ------------------------------------------------------- carpetas registradas

class FakeRegisteredFolders(RegisteredFolderRepositoryPort):
    """In-memory carpetas. Mirrors what the SQL repository guarantees: filing
    order is kept, a document sits in one carpeta at a time, and the document
    itself carries which carpeta holds it (there it is read off the row that
    files it, here it is written on the document when it is filed)."""

    def __init__(self, documents):
        self.rows = {}
        self._owners = {}
        self._documents = documents

    def _entity(self, row):
        return RegisteredFolder(
            id=row["id"],
            user_sub=self._owners[row["id"]],
            name=row["name"],
            notes=row["notes"],
            folder_type=row["folder_type"],
            data=dict(row["data"]),
            created_at=NOW,
            updated_at=NOW,
            documents=[self._documents.rows[i] for i in row["ids"] if i in self._documents.rows],
        )

    def _file(self, folder_id, ids):
        """Keeps every document's folder_id in step with what the carpeta holds."""
        for document_id, document in self._documents.rows.items():
            if document_id in ids:
                self._documents.rows[document_id] = replace(document, folder_id=folder_id)
            elif document.folder_id == folder_id:
                self._documents.rows[document_id] = replace(document, folder_id=None)

    def create(self, user_sub, name, notes, folder_type, data, document_ids):
        folder_id = str(uuid.uuid4())
        self._owners[folder_id] = user_sub
        self.rows[folder_id] = {
            "id": folder_id,
            "name": name,
            "notes": notes,
            "folder_type": folder_type,
            "data": dict(data or {}),
            "ids": list(document_ids),
        }
        self._file(folder_id, list(document_ids))
        return self._entity(self.rows[folder_id])

    def get(self, folder_id, user_sub):
        row = self.rows.get(folder_id)
        if row is None or self._owners.get(folder_id) != user_sub:
            return None
        return self._entity(row)

    def find_any(self, folder_id):
        row = self.rows.get(folder_id)
        return None if row is None else self._entity(row)

    def list(self, user_sub):
        rows = [r for fid, r in self.rows.items() if self._owners.get(fid) == user_sub]
        return [self._entity(r) for r in sorted(rows, key=lambda r: r["name"].lower())]

    def search_by_name(self, name, user_sub=None, limit=50):
        term = (name or "").strip().lower()
        if not term:
            return []
        rows = [
            r
            for fid, r in self.rows.items()
            if term in r["name"].lower()
            and (user_sub is None or self._owners.get(fid) == user_sub)
        ]
        return [self._entity(r) for r in sorted(rows, key=lambda r: r["name"].lower())[:limit]]

    def update_details(self, folder_id, name, notes, data):
        self.rows[folder_id].update(name=name, notes=notes, data=dict(data or {}))

    def file_document(self, folder_id, document_id):
        row = self.rows[folder_id]
        if document_id not in row["ids"]:
            row["ids"].append(document_id)
        self._file(folder_id, row["ids"])

    def set_documents(self, folder_id, document_ids):
        self.rows[folder_id]["ids"] = list(document_ids)
        self._file(folder_id, list(document_ids))

    def delete(self, folder_id):
        row = self.rows.pop(folder_id, None)
        self._owners.pop(folder_id, None)
        if row is not None:
            self._file(folder_id, [])

    def name_taken(self, user_sub, name, exclude_folder_id=None):
        return any(
            r["name"].lower() == name.strip().lower()
            for fid, r in self.rows.items()
            if self._owners.get(fid) == user_sub and fid != exclude_folder_id
        )

    def folder_names_of_documents(self, user_sub, document_ids, exclude_folder_id=None):
        taken = {}
        for fid, row in self.rows.items():
            if self._owners.get(fid) != user_sub or fid == exclude_folder_id:
                continue
            for document_id in row["ids"]:
                if document_id in document_ids:
                    taken[document_id] = row["name"]
        return taken


class TestRegisteredFolders(unittest.TestCase):
    """The "Carpetas registradas" submodule: the architect names a project and
    files the documents already solved in it."""

    def setUp(self):
        self.captures, self.documents = FakeCaptures(), FakeDocuments()
        self.folders = FakeRegisteredFolders(self.documents)
        self.service = RegisteredFolderService(self.folders, self.documents)

    def _reviewed(self, doc_type="folio", user_sub="arq-1"):
        """A document as it looks once its review was saved."""
        photo = self.captures.create(user_sub, "p.png", "image/png", b"x", b"t")
        document = self.documents.create(user_sub, doc_type, [photo.id])
        self.documents.save_progress(document.id, document.pages, DocumentStatus.EXTRACTED, {"a": 1}, None)
        ReviewDocumentUseCase(self.documents).execute(document.id, user_sub, {"registration_number": "1.1.1"})
        return self.documents.get(document.id, user_sub)

    def _draft(self, doc_type="plan", user_sub="arq-1"):
        photo = self.captures.create(user_sub, "p.png", "image/png", b"x", b"t")
        return self.documents.create(user_sub, doc_type, [photo.id])

    def _create(self, name="Proyecto Sur", notes=None, ids=None, user_sub="arq-1", kind=None, data=None):
        return CreateRegisteredFolderUseCase(self.folders, self.service).execute(
            user_sub, name, notes, folder_type_key=kind, data=data, document_ids=ids or []
        )

    # ------------------------------------------------------------------ create

    def test_a_carpeta_groups_the_three_kinds_of_saved_document(self):
        folio, tax, plan = self._reviewed("folio"), self._reviewed("tax_receipt"), self._reviewed("plan")
        folder = self._create("Av. Ballivián 220", "Ampliación", [folio.id, tax.id, plan.id])
        self.assertEqual(folder.name, "Av. Ballivián 220")
        self.assertEqual(folder.notes, "Ampliación")
        self.assertEqual(folder.document_ids, [folio.id, tax.id, plan.id])
        self.assertEqual(folder.counts_by_type, {"folio": 1, "tax_receipt": 1, "plan": 1})

    def test_the_counters_name_every_type_even_when_empty(self):
        """The screen draws three counters, so none of them may be missing."""
        self.assertEqual(self._create().counts_by_type, {"folio": 0, "tax_receipt": 0, "plan": 0})

    def test_the_name_is_required_and_trimmed(self):
        self.assertEqual(self._create("  Proyecto   Norte  ").name, "Proyecto Norte")
        with self.assertRaises(InvalidRegisteredFolderException):
            self._create("   ")

    def test_a_name_too_long_is_refused(self):
        with self.assertRaises(InvalidRegisteredFolderException):
            self._create("x" * (MAX_NAME_LENGTH + 1))

    def test_two_carpetas_cannot_share_a_name_however_it_is_typed(self):
        self._create("Proyecto Sur")
        with self.assertRaises(RegisteredFolderNameTakenException):
            self._create("  proyecto sur ")

    def test_another_user_may_use_the_same_project_name(self):
        self._create("Proyecto Sur")
        self.assertEqual(self._create("Proyecto Sur", user_sub="arq-2").name, "Proyecto Sur")

    def test_repeated_picks_are_filed_once(self):
        folio = self._reviewed()
        self.assertEqual(self._create(ids=[folio.id, folio.id]).document_ids, [folio.id])

    # ------------------------------------------------------------ what may go in

    def test_only_documents_whose_review_was_saved_can_be_filed(self):
        with self.assertRaises(InvalidRegisteredFolderException):
            self._create(ids=[self._draft().id])

    def test_another_users_document_cannot_be_filed(self):
        other = self._reviewed(user_sub="arq-2")
        with self.assertRaises(DocumentNotFoundException):
            self._create(ids=[other.id])

    def test_a_document_already_filed_says_which_carpeta_holds_it(self):
        folio = self._reviewed()
        self._create("Proyecto Sur", ids=[folio.id])
        with self.assertRaises(DocumentAlreadyFiledException) as raised:
            self._create("Proyecto Norte", ids=[folio.id])
        self.assertIn("Proyecto Sur", raised.exception.message)

    def test_more_documents_than_a_carpeta_admits_are_refused(self):
        with self.assertRaises(InvalidRegisteredFolderException):
            self._create(ids=[str(uuid.uuid4()) for _ in range(MAX_DOCUMENTS + 1)])

    # ------------------------------------------------------------------ update

    def test_renaming_alone_keeps_the_documents(self):
        folio = self._reviewed()
        folder = self._create("Proyecto Sur", ids=[folio.id])
        renamed = UpdateRegisteredFolderUseCase(self.folders, self.service).execute(
            folder.id, "arq-1", "Proyecto Sur — etapa 2", "Con plano nuevo"
        )
        self.assertEqual(renamed.name, "Proyecto Sur — etapa 2")
        self.assertEqual(renamed.notes, "Con plano nuevo")
        self.assertEqual(renamed.document_ids, [folio.id])

    def test_a_carpeta_can_keep_its_own_name_while_being_edited(self):
        folder = self._create("Proyecto Sur")
        self.assertEqual(
            UpdateRegisteredFolderUseCase(self.folders, self.service)
            .execute(folder.id, "arq-1", "Proyecto Sur", "otra nota").name,
            "Proyecto Sur",
        )

    def test_sending_documents_replaces_the_whole_content(self):
        folio, tax = self._reviewed("folio"), self._reviewed("tax_receipt")
        folder = self._create("Proyecto Sur", ids=[folio.id])
        updated = UpdateRegisteredFolderUseCase(self.folders, self.service).execute(
            folder.id, "arq-1", "Proyecto Sur", None, document_ids=[tax.id]
        )
        self.assertEqual(updated.document_ids, [tax.id])

    def test_reordering_its_own_documents_is_not_a_conflict(self):
        folio, tax = self._reviewed("folio"), self._reviewed("tax_receipt")
        folder = self._create("Proyecto Sur", ids=[folio.id, tax.id])
        updated = UpdateRegisteredFolderUseCase(self.folders, self.service).execute(
            folder.id, "arq-1", "Proyecto Sur", None, document_ids=[tax.id, folio.id]
        )
        self.assertEqual(updated.document_ids, [tax.id, folio.id])

    def test_another_user_cannot_touch_the_carpeta(self):
        folder = self._create("Proyecto Sur")
        with self.assertRaises(RegisteredFolderNotFoundException):
            UpdateRegisteredFolderUseCase(self.folders, self.service).execute(
                folder.id, "arq-2", "Mío"
            )

    # ------------------------------------------------------- add / remove / delete

    def test_adding_files_at_the_end_and_keeps_what_was_there(self):
        folio, plan = self._reviewed("folio"), self._reviewed("plan")
        folder = self._create("Proyecto Sur", ids=[folio.id])
        added = AddDocumentsToRegisteredFolderUseCase(self.folders, self.service).execute(
            folder.id, "arq-1", [plan.id]
        )
        self.assertEqual(added.document_ids, [folio.id, plan.id])

    def test_adding_what_is_already_inside_is_asked_again(self):
        folio = self._reviewed()
        folder = self._create("Proyecto Sur", ids=[folio.id])
        with self.assertRaises(InvalidRegisteredFolderException):
            AddDocumentsToRegisteredFolderUseCase(self.folders, self.service).execute(
                folder.id, "arq-1", [folio.id]
            )

    def _remover(self):
        return RemoveDocumentFromRegisteredFolderUseCase(
            self.folders, self.service, self.documents, self.captures
        )

    def test_removing_deletes_the_document_and_its_photos(self):
        folio, plan = self._reviewed(), self._reviewed("plan")
        folder = self._create("Proyecto Sur", ids=[folio.id, plan.id])
        photo = folio.pages[0].capture_id
        left = self._remover().execute(folder.id, "arq-1", folio.id)
        self.assertEqual(left.document_ids, [plan.id])
        self.assertIsNone(self.documents.get(folio.id, "arq-1"))
        self.assertIsNone(self.captures.get(photo, "arq-1"))
        self.assertIsNotNone(self.captures.get(plan.pages[0].capture_id, "arq-1"))

    def test_removing_something_that_is_not_in_the_carpeta(self):
        folder = self._create("Proyecto Sur")
        with self.assertRaises(DocumentNotFoundException):
            self._remover().execute(
                folder.id, "arq-1", self._reviewed().id
            )

    def _deleter(self):
        return DeleteRegisteredFolderUseCase(self.folders, self.service, self.documents, self.captures)

    def test_deleting_the_carpeta_deletes_its_documents_and_photos(self):
        """They must not go back to the loose board as if they were the next folder's."""
        folio, draft = self._reviewed(), self._draft()
        kept = self._draft()
        folder = self._create("Proyecto Sur", ids=[folio.id])
        self.folders.file_document(folder.id, draft.id)
        photos = [p.capture_id for d in (folio, draft) for p in d.pages]
        self._deleter().execute(folder.id, "arq-1")
        self.assertEqual(ListRegisteredFoldersUseCase(self.folders).execute("arq-1"), [])
        self.assertIsNone(self.documents.get(folio.id, "arq-1"))
        self.assertIsNone(self.documents.get(draft.id, "arq-1"))
        self.assertEqual(self.captures.get_many(photos, "arq-1"), [])
        self.assertIsNotNone(self.documents.get(kept.id, "arq-1"))
        self.assertEqual(len(self.captures.get_many([kept.pages[0].capture_id], "arq-1")), 1)

    def test_another_user_cannot_delete_the_carpeta(self):
        folder = self._create("Proyecto Sur")
        with self.assertRaises(RegisteredFolderNotFoundException):
            self._deleter().execute(folder.id, "arq-2")

    # -------------------------------------------------------------------- list

    def test_the_list_is_alphabetical_and_only_the_users_own(self):
        self._create("Zona Sur")
        self._create("Achumani")
        self._create("Ajena", user_sub="arq-2")
        self.assertEqual(
            [f.name for f in ListRegisteredFoldersUseCase(self.folders).execute("arq-1")],
            ["Achumani", "Zona Sur"],
        )

    # ------------------------------------------------------------ tipo y hoja

    def test_a_carpeta_is_opened_with_its_kind_and_its_sheet(self):
        folder = self._create(
            "Poseedores Sarco",
            kind="possessors",
            data={"street": "  Av.  Ballivián ", "usable_area": "240 m2"},
        )
        self.assertEqual(folder.folder_type, "possessors")
        self.assertEqual(folder.data["street"], "Av. Ballivián")
        self.assertEqual(folder.data["usable_area"], "240 m2")

    def test_the_sheet_only_keeps_what_its_kind_declares(self):
        """The catalogue is the truth about a carpeta's fields: what is not one
        of them would never be shown again.

        "notary_number" está acá a propósito: era un campo de esta carpeta hasta
        que se quitó el apartado de declaración jurada, y lo que una carpeta
        guardada traiga de entonces tampoco vuelve a entrar."""
        folder = self._create(
            "Poseedores Sarco",
            kind="possessors",
            data={"inventado": "x", "notary_number": "15", "cadastral_code": "00-33-432-012-0-00-000-000"},
        )
        self.assertNotIn("inventado", folder.data)
        self.assertNotIn("notary_number", folder.data)
        self.assertEqual(folder.data["cadastral_code"], "00-33-432-012-0-00-000-000")

    def test_a_carpeta_without_a_kind_is_the_general_one(self):
        self.assertEqual(self._create("Proyecto Sur").folder_type, "general")

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(InvalidRegisteredFolderException):
            self._create("Proyecto Sur", kind="tramite-inventado")

    def test_editing_saves_the_sheet_and_keeps_the_kind(self):
        folder = self._create("Poseedores Sarco", kind="possessors", data={"street": "Calle A"})
        updated = UpdateRegisteredFolderUseCase(self.folders, self.service).execute(
            folder.id, "arq-1", "Poseedores Sarco", None, data={"street": "Calle B"}
        )
        self.assertEqual(updated.folder_type, "possessors")
        self.assertEqual(updated.data["street"], "Calle B")

    def test_editing_does_not_throw_out_the_documents_still_being_worked_on(self):
        """The screen that sends the selection lists reviewed documents only, so
        what it sends cannot be read as "and nothing else"."""
        folder = self._create("Poseedores Sarco", kind="possessors")
        draft = self._draft(doc_type="plan")
        self.folders.file_document(folder.id, draft.id)
        reviewed = self._reviewed()
        updated = UpdateRegisteredFolderUseCase(self.folders, self.service).execute(
            folder.id, "arq-1", "Poseedores Sarco", None, document_ids=[reviewed.id]
        )
        self.assertEqual(set(updated.document_ids), {reviewed.id, draft.id})

    def test_a_carpeta_carries_the_saved_data_of_its_documents(self):
        """The screen shows the matrícula under each row, so the data travels
        with the carpeta instead of asking for every document."""
        folio = self._reviewed()
        folder = self._create("Proyecto Sur", ids=[folio.id])
        self.assertEqual(folder.documents[0].reviewed_data, {"registration_number": "1.1.1"})

    # ------------------------------------------------- guardar tablero en carpeta

    def _save_board(self, number="1520", ids=None, kind=None):
        return SaveBoardToFolderUseCase(self.folders, self.documents, self.service).execute(
            "arq-1", number, kind, ids or []
        )

    def test_the_board_goes_into_a_carpeta_named_after_its_number(self):
        """Whatever state each document is in: the physical folder is saved whole."""
        draft, reviewed = self._draft("plan"), self._reviewed("folio")
        folder = self._save_board("  1520 ", [draft.id, reviewed.id])
        self.assertEqual(folder.name, "1520")
        self.assertEqual(folder.folder_type, "general")
        self.assertEqual(folder.document_ids, [draft.id, reviewed.id])
        self.assertEqual(self.documents.get(draft.id, "arq-1").folder_id, folder.id)

    def test_saving_an_empty_board_is_refused(self):
        with self.assertRaises(InvalidRegisteredFolderException):
            self._save_board(ids=[])

    def test_a_number_already_registered_is_refused(self):
        self._create("1520")
        with self.assertRaises(RegisteredFolderNameTakenException) as raised:
            self._save_board("1520", [self._draft().id])
        self.assertIn("1520", raised.exception.message)

    def test_a_document_already_in_a_carpeta_is_not_moved(self):
        draft = self._draft()
        self._save_board("1520", [draft.id])
        with self.assertRaises(DocumentAlreadyFiledException):
            self._save_board("1521", [draft.id])

    def test_a_document_outside_the_kinds_lanes_is_refused(self):
        """The general kind has no carnet lane."""
        with self.assertRaises(InvalidRegisteredFolderException):
            self._save_board("1520", [self._draft("id_card").id])

class DocumentosDentroDeUnaCarpetaTests(unittest.TestCase):
    """A document is opened inside a carpeta, so from the moment it is created it
    belongs to it -- and it has to be one of the types that carpeta works with."""

    def setUp(self):
        self.captures, self.documents = FakeCaptures(), FakeDocuments()
        self.folders = FakeRegisteredFolders(self.documents)
        self.service = RegisteredFolderService(self.folders, self.documents)
        self.photo = self.captures.create("arq-1", "p.png", "image/png", b"x", b"t")

    def _folder(self, kind="possessors"):
        return CreateRegisteredFolderUseCase(self.folders, self.service).execute(
            "arq-1", "Poseedores Sarco", None, folder_type_key=kind
        )

    def _create(self, doc_type, folder_id=None):
        return CreateDocumentUseCase(self.documents, self.captures, self.folders).execute(
            doc_type, [self.photo.id], "arq-1", folder_id
        )

    def test_a_document_opened_in_a_carpeta_is_filed_in_it_as_a_draft(self):
        folder = self._folder()
        document = self._create(DocumentType.FORM, folder.id)
        self.assertEqual(document.folder_id, folder.id)
        self.assertEqual(document.status, DocumentStatus.DRAFT)
        self.assertEqual(
            self.folders.get(folder.id, "arq-1").document_ids, [document.id]
        )

    def test_a_carpeta_refuses_a_document_it_does_not_work_with(self):
        folder = self._folder()
        with self.assertRaises(InvalidDocumentRequestException):
            self._create(DocumentType.TAX_RECEIPT, folder.id)

    def test_on_the_loose_board_a_document_belongs_to_no_carpeta(self):
        self.assertIsNone(self._create(DocumentType.FOLIO).folder_id)

    def test_a_carpeta_that_is_not_the_users_is_not_found(self):
        folder = CreateRegisteredFolderUseCase(self.folders, self.service).execute(
            "arq-2", "Ajena", None, folder_type_key="possessors"
        )
        with self.assertRaises(RegisteredFolderNotFoundException):
            self._create(DocumentType.PLAN, folder.id)

    def test_the_board_of_a_carpeta_lists_only_its_documents(self):
        folder = self._folder()
        mine = self._create(DocumentType.PLAN, folder.id)
        other_photo = self.captures.create("arq-1", "q.png", "image/png", b"x", b"t")
        CreateDocumentUseCase(self.documents, self.captures, self.folders).execute(
            DocumentType.FOLIO, [other_photo.id], "arq-1"
        )
        self.assertEqual(
            [d.id for d in self.documents.list("arq-1", folder_id=folder.id)], [mine.id]
        )


class OtrosDocumentosNoSeLeenTests(unittest.TestCase):
    """El carril de "otros documentos": lo que el poseedor trae de respaldo.

    No tiene datos que sacarle, así que se guarda con sus fotos y nada más -- ni
    OCR, ni cola, ni pantalla de revisión. Queda archivado desde que se suelta,
    que es lo que hace que la pantalla no ofrezca analizarlo.
    """

    def setUp(self):
        self.captures, self.documents, self.queue = FakeCaptures(), FakeDocuments(), FakeQueue()
        self.folders = FakeRegisteredFolders(self.documents)
        self.service = RegisteredFolderService(self.folders, self.documents)
        self.photo = self.captures.create("arq-1", "p.png", "image/png", b"x", b"t")

    def _create(self, doc_type=DocumentType.ID_CARD, ids=None):
        return CreateDocumentUseCase(self.documents, self.captures, self.folders).execute(
            doc_type, ids or [self.photo.id], "arq-1"
        )

    def _analyze(self, document):
        return AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(
            document.id, "arq-1"
        )

    def test_the_catalogue_and_the_lanes_agree_on_which_types_are_read(self):
        """Los dos conjuntos tienen que cubrir ALL sin pisarse: si alguien agrega
        un carril y se olvida de uno, se lee lo que no debía o al revés."""
        self.assertEqual(
            sorted(DocumentType.SERVER_READ + DocumentType.NOT_READ), sorted(DocumentType.ALL)
        )
        self.assertEqual(set(DocumentType.SERVER_READ) & set(DocumentType.NOT_READ), set())

    def test_it_is_filed_the_moment_it_is_created(self):
        document = self._create()
        self.assertEqual(document.status, DocumentStatus.FILED)
        self.assertEqual([p.status for p in document.pages], [PageStatus.DONE])

    def test_its_photos_are_kept_assigned_to_it(self):
        document = self._create()
        self.assertEqual([p.capture_id for p in document.pages], [self.photo.id])
        self.assertEqual(self.captures.list_by_status("arq-1", CaptureStatus.INBOX), [])

    def test_asking_to_analyze_it_queues_nothing(self):
        """La pantalla ya no ofrece el botón, pero la regla vive en el caso de
        uso: una petición vieja no puede mandarlo al OCR por la ventana."""
        document = self._analyze(self._create())
        self.assertEqual(document.status, DocumentStatus.FILED)
        self.assertEqual(self.queue.submitted, [])

    def test_the_server_reading_leaves_it_alone(self):
        document = self._create()
        RunServerReadingUseCase(self.documents, self.captures, {}).execute(document.id, "arq-1")
        self.assertEqual(
            self.documents.get(document.id, "arq-1").status, DocumentStatus.FILED
        )

    def test_changing_its_pages_leaves_it_filed_again(self):
        """replace_pages devuelve cualquier documento a borrador para que se
        vuelva a analizar; este no tiene a qué volver."""
        document = self._create()
        other = self.captures.create("arq-1", "q.png", "image/png", b"x", b"t")
        document = SetDocumentPagesUseCase(self.documents, self.captures).execute(
            document.id, [self.photo.id, other.id], "arq-1"
        )
        self.assertEqual(document.status, DocumentStatus.FILED)
        self.assertEqual(len(document.pages), 2)

    def test_a_lane_that_is_read_is_untouched(self):
        document = self._create(DocumentType.FORM)
        self.assertEqual(document.status, DocumentStatus.DRAFT)

    def test_it_is_named_otros_documentos_and_says_it_is_not_read(self):
        spec = DOCUMENT_TYPES[DocumentType.ID_CARD]
        self.assertEqual(spec.label, "Otros documentos")
        self.assertIn("no se leen", spec.hint)


class JuntarTodoEnUnDocumentoTests(unittest.TestCase):
    """El botón del carril: lo suelto queda en un solo documento.

    Un poseedor trae un montón de respaldos que no son un trámite cada uno sino
    el mismo legajo. Esto junta las fotos que quedaron en la bandeja con las
    tarjetas que ya están en el carril.
    """

    def setUp(self):
        self.captures, self.documents = FakeCaptures(), FakeDocuments()
        self.folders = FakeRegisteredFolders(self.documents)
        self.service = RegisteredFolderService(self.folders, self.documents)

    def _photo(self, name):
        return self.captures.create("arq-1", name, "image/png", b"x", b"t")

    def _folder(self):
        return CreateRegisteredFolderUseCase(self.folders, self.service).execute(
            "arq-1", "Poseedores Sarco", None, folder_type_key="possessors"
        )

    def _create(self, doc_type, capture_ids, folder_id=None):
        return CreateDocumentUseCase(self.documents, self.captures, self.folders).execute(
            doc_type, capture_ids, "arq-1", folder_id
        )

    def _consolidate(self, doc_type=DocumentType.ID_CARD, folder_id=None, folder_type_key="possessors"):
        return ConsolidateDocumentsUseCase(self.documents, self.captures, self.folders).execute(
            doc_type, "arq-1", folder_id, folder_type_key
        )

    def test_the_loose_photos_of_the_inbox_become_one_document(self):
        photos = [self._photo(f"p{i}.png") for i in range(3)]
        document = self._consolidate()
        self.assertEqual(document.status, DocumentStatus.FILED)
        self.assertEqual([p.capture_id for p in document.pages], [p.id for p in photos])
        self.assertEqual(self.captures.list_by_status("arq-1", CaptureStatus.INBOX), [])

    def test_the_cards_already_in_the_lane_are_merged_into_the_oldest(self):
        first = self._create(DocumentType.ID_CARD, [self._photo("a.png").id])
        second = self._create(DocumentType.ID_CARD, [self._photo("b.png").id])
        document = self._consolidate()
        self.assertEqual(document.id, first.id)
        self.assertEqual(len(document.pages), 2)
        self.assertIsNone(self.documents.get(second.id, "arq-1"))

    def test_the_inbox_and_the_lane_go_into_the_same_one(self):
        card = self._create(DocumentType.ID_CARD, [self._photo("a.png").id])
        loose = self._photo("b.png")
        document = self._consolidate()
        self.assertEqual(document.id, card.id)
        self.assertEqual([p.capture_id for p in document.pages][-1], loose.id)
        self.assertEqual(len(document.pages), 2)

    def test_the_pages_keep_their_order_and_the_loose_ones_go_last(self):
        a, b = self._photo("a.png"), self._photo("b.png")
        self._create(DocumentType.ID_CARD, [a.id])
        self._create(DocumentType.ID_CARD, [b.id])
        loose = self._photo("c.png")
        self.assertEqual(
            [p.capture_id for p in self._consolidate().pages], [a.id, b.id, loose.id]
        )

    def test_a_lane_that_is_read_is_refused(self):
        self._photo("a.png")
        with self.assertRaises(InvalidDocumentRequestException):
            self._consolidate(DocumentType.FORM)

    def test_with_nothing_to_gather_it_says_so(self):
        with self.assertRaises(InvalidDocumentRequestException):
            self._consolidate()

    def test_more_photos_than_a_document_takes_is_refused_with_the_count(self):
        for i in range(MAX_PAGES + 1):
            self._photo(f"p{i}.png")
        with self.assertRaises(InvalidDocumentRequestException) as caught:
            self._consolidate()
        self.assertIn(str(MAX_PAGES + 1), caught.exception.message)
        # Nada a medias: las fotos siguen en la bandeja para repartirlas.
        self.assertEqual(
            len(self.captures.list_by_status("arq-1", CaptureStatus.INBOX)), MAX_PAGES + 1
        )

    def test_inside_a_carpeta_the_result_belongs_to_it_only_once(self):
        folder = self._folder()
        self._create(DocumentType.ID_CARD, [self._photo("a.png").id], folder.id)
        self._photo("b.png")
        document = self._consolidate(folder_id=folder.id)
        self.assertEqual(
            self.folders.get(folder.id, "arq-1").document_ids, [document.id]
        )

    def test_if_the_rebuild_fails_the_photos_go_back_to_the_inbox(self):
        """Las tarjetas que se borraron ya no están. Sin esto sus fotos quedaban
        asignadas a nada: fuera de la bandeja y fuera de todo documento, o sea
        invisibles."""
        a, b = self._photo("a.png"), self._photo("b.png")
        self._create(DocumentType.ID_CARD, [a.id])
        self._create(DocumentType.ID_CARD, [b.id])

        def boom(*args, **kwargs):
            raise RuntimeError("se cayó la base")

        self.documents.replace_pages = boom
        with self.assertRaises(RuntimeError):
            self._consolidate()
        self.assertIn(b.id, [c.id for c in self.captures.list_by_status("arq-1", CaptureStatus.INBOX)])

    def test_on_the_loose_board_the_cards_already_in_a_carpeta_are_left_alone(self):
        """Once the board is saved into a carpeta, its carnets belong there: the
        next folder scanned on the loose board must not swallow them."""
        folder = self._folder()
        filed = self._create(DocumentType.ID_CARD, [self._photo("a.png").id])
        self.folders.file_document(folder.id, filed.id)
        self._photo("b.png")
        document = self._consolidate()
        self.assertNotEqual(document.id, filed.id)
        self.assertEqual(len(self.documents.get(filed.id, "arq-1").pages), 1)

    def test_it_does_not_touch_another_lane(self):
        other = self._create(DocumentType.FORM, [self._photo("a.png").id])
        self._photo("b.png")
        self._consolidate()
        kept = self.documents.get(other.id, "arq-1")
        self.assertEqual([p.capture_id for p in kept.pages], [p.capture_id for p in other.pages])


class VaciarLaBandejaTests(unittest.TestCase):
    """El botón de vaciar la bandeja: se borran de una vez las fotos que quedaron
    sin clasificar, sin tocar las que ya son página de un documento."""

    def setUp(self):
        self.captures = FakeCaptures()
        self.documents = FakeDocuments()
        self.use_case = ClearInboxUseCase(self.captures)

    def _photo(self, user_sub="arq-1"):
        return self.captures.create(user_sub, "p.png", "image/png", b"x", b"t")

    def test_empties_the_inbox_and_says_how_many_went(self):
        self._photo(), self._photo(), self._photo()
        self.assertEqual(self.use_case.execute("arq-1"), 3)
        self.assertEqual(self.captures.list_by_status("arq-1", CaptureStatus.INBOX), [])

    def test_the_photos_already_in_a_document_stay(self):
        loose, used = self._photo(), self._photo()
        CreateDocumentUseCase(self.documents, self.captures).execute(
            DocumentType.FOLIO, [used.id], "arq-1"
        )
        self.assertEqual(self.use_case.execute("arq-1"), 1)
        self.assertIsNone(self.captures.get(loose.id, "arq-1"))
        self.assertIsNotNone(self.captures.get(used.id, "arq-1"))

    def test_it_only_empties_the_users_own_bandeja(self):
        mine, theirs = self._photo(), self._photo("arq-2")
        self.assertEqual(self.use_case.execute("arq-1"), 1)
        self.assertIsNone(self.captures.get(mine.id, "arq-1"))
        self.assertIsNotNone(self.captures.get(theirs.id, "arq-2"))

    def test_an_empty_bandeja_is_not_an_error(self):
        self.assertEqual(self.use_case.execute("arq-1"), 0)


class CosechaDeCamposTests(unittest.TestCase):
    """Sacar de una hoja leída genéricamente los valores que la carpeta pide.

    Las lecturas de acá tienen la forma que devuelve el OCR genérico: el texto de
    la hoja y los pares "ETIQUETA: valor" que pudo separar.
    """

    PLAN = document_fields("possessors", DocumentType.PLAN)
    STATEMENT = document_fields("possessors", DocumentType.FORM)

    def _reading(self, text="", fields=()):
        return {
            "full_text": text,
            "pages": [{"fields": [dict(f) for f in fields], "full_text": text, "tables": []}],
        }

    def test_reads_the_measurements_written_on_the_sheet(self):
        reading = self._reading(
            "PLANO DE UBICACION\n"
            "FRENTE 12.50 M\n"
            "CONTRA FRENTE 12.50 M\n"
            "FONDO 25.00 M\n"
            "FONDO 2 24.80 M\n"
            "SUPERFICIE UTIL 240.00 M2\n"
            "LOTE N: 5 to CALLE DE 12.50 MTS.\n"
            "MANZANO 432\nLOTE 002\nVIA\nCalle de 9.00 mts.\n"
            "Código Catastral: 00-33-432-012-0-00-000-000"
        )
        values, missing = harvest(reading, self.PLAN)
        self.assertEqual(values["cadastral_code"], "00-33-432-012-0-00-000-000")
        # Lo que se copia del IDE no se busca en la hoja: no es un rótulo faltante.
        self.assertIsNone(values["street"])
        self.assertEqual(values["frontage"], "12.50 M")
        self.assertEqual(values["rear_frontage"], "12.50 M")
        self.assertEqual(values["depth"], "25.00 M")
        self.assertEqual(values["depth_2"], "24.80 M")
        self.assertEqual(values["usable_area"], "240.00 M2")
        # Arriba va lo que el plano dice de sí mismo: el ancho de cada calle y su lote.
        self.assertEqual(values["street_width"], "12.50 m, 9.00 m")
        self.assertEqual(values["property_number"], "2")
        self.assertEqual(missing, [])

    def test_a_fondo_of_25_metres_is_not_read_as_the_second_fondo(self):
        """Sin el corte de la etiqueta, "FONDO 25.00" y "FONDO 2" son la misma
        hilera de letras y dígitos, y el fondo 2 se llevaba un "5.00"."""
        values, _ = harvest(self._reading("FONDO 25.00 M"), self.PLAN)
        self.assertEqual(values["depth"], "25.00 M")
        self.assertIsNone(values["depth_2"])

    def test_the_longer_label_does_not_lend_its_line_to_the_shorter_one(self):
        values, _ = harvest(self._reading("FONDO 2 24.80 M\nFONDO 25.00 M"), self.PLAN)
        self.assertEqual(values["depth_2"], "24.80 M")
        self.assertEqual(values["depth"], "25.00 M")

    def test_a_labelled_pair_is_read_before_the_running_text(self):
        reading = self._reading(
            "FRENTE 9.00 M", [{"name": "FRENTE", "value": "12,50 m"}]
        )
        self.assertEqual(harvest(reading, self.PLAN)[0]["frontage"], "12,50 m")

    def test_the_notary_is_kept_by_its_number(self):
        reading = self._reading(
            fields=[{"name": "NOTARIA DE FE PUBLICA", "value": "N 23 DEL DISTRITO"}]
        )
        self.assertEqual(harvest(reading, self.STATEMENT)[0]["notary_number"], "23")

    def test_what_is_not_on_the_sheet_stays_empty_and_is_named(self):
        values, missing = harvest(self._reading("HOJA SIN DATOS"), self.STATEMENT)
        self.assertEqual(set(values.values()), {None})
        self.assertEqual(missing, [f.label for f in self.STATEMENT])
        self.assertIn("Notario", observation(missing))

    def test_a_label_that_is_only_part_of_a_word_is_not_a_match(self):
        values, _ = harvest(self._reading("FRENTERA DEL LOTE 3"), self.PLAN)
        self.assertIsNone(values["frontage"])

    def test_nothing_is_asked_of_a_document_the_carpeta_says_nothing_about(self):
        self.assertEqual(document_fields("general", DocumentType.FOLIO), ())
        self.assertEqual(document_fields("possessors", DocumentType.ID_CARD), ())


class ActaNotarialTests(unittest.TestCase):
    """Un acta notarial no rotula nada: el número del notario, la persona y la
    fecha viven dentro de su redacción, y la fecha viene escrita con letras."""

    FIELDS = document_fields("possessors", DocumentType.FORM)

    # El párrafo de apertura, tal como lo lee el OCR de un acta de Cochabamba.
    ACTA = (
        "En el municipio de Cochabamba del departamento de Cochabamba del Estado Plurinacional de\n"
        "Bolivia, a horas 13:18 (trece y dieciocho), del día, lunes veintiun del mes de septiembre del año dos\n"
        "mil veintiseis, ANTE MÍ ANGEL RODRIGUEZ SALAZAR, Notario de Fe Pública N° 15 del municipio\n"
        "de Cochabamba del departamento de Cochabamba, se hizo presente NOELIA ALMENDRAS\n"
        "RODRIGUEZ con Cédula de Identidad N° 8806991 (ocho, ocho, cero, seis, nueve, nueve, uno),\n"
        "Boliviana, Soltera, mayor de edad, de profesión ESTUDIANTE, con domicilio en AV. PETROLERA"
    )

    def _harvest(self, text):
        reading = {"full_text": text, "pages": [{"fields": [], "full_text": text, "tables": []}]}
        return harvest(reading, self.FIELDS)[0]

    def test_reads_the_three_values_out_of_the_opening_paragraph(self):
        values = self._harvest(self.ACTA)
        self.assertEqual(values["notary_number"], "15")
        self.assertEqual(values["owner_name"], "NOELIA ALMENDRAS RODRIGUEZ")
        self.assertEqual(values["statement_dates"], "21/09/2026")

    def test_the_name_stops_at_the_identity_card(self):
        """Sin el corte, el nombre se llevaba media acta -- la nacionalidad, el
        estado civil y el domicilio van en la misma frase."""
        self.assertNotIn("CEDULA", self._harvest(self.ACTA)["owner_name"])

    def test_another_wording_of_the_same_act(self):
        values = self._harvest(
            "A los veintiun días del mes de septiembre de dos mil veintiseis, ante mí, "
            "Notaria de Fe Pública Nº 3, compareció JUAN PEREZ LOPEZ con C.I. 123"
        )
        self.assertEqual(values["notary_number"], "3")
        self.assertEqual(values["owner_name"], "JUAN PEREZ LOPEZ")
        self.assertEqual(values["statement_dates"], "21/09/2026")

    def test_a_date_already_written_in_figures(self):
        self.assertEqual(self._harvest("Cochabamba, 5 de enero de 1998.")["statement_dates"], "05/01/1998")

    def test_a_sheet_that_says_none_of_it_leaves_everything_empty(self):
        self.assertEqual(set(self._harvest("HOJA CUALQUIERA").values()), {None})


class MinutaDirigidaAlNotarioTests(unittest.TestCase):
    """La otra forma del mismo trámite: una minuta no es un acta.

    No dice "ante mí" ni "compareció" -- va dirigida al notario ("SEÑOR NOTARIO
    DE FE PÚBLICA, sírvase insertar"), enumera a las partes con su cédula
    colgando del nombre, cita las fechas de los documentos que la anteceden y
    recién al final, junto a la ciudad, pone la suya. El notario no se nombra en
    el texto: está en el sello.

    De una de estas (una guarda con cesión, cuatro hojas) salía el notario como
    "DE FE", y el nombre y la fecha vacíos.
    """

    FIELDS = document_fields("possessors", DocumentType.FORM)

    MINUTA = (
        "IVON JANNET RICO LEDEZMA ABOGADO NOTARIA DE FE PUBLICA DE PRIMERA CLASE No. 48\n"
        "Cochabamba - Bolivia\n"
        "SEÑOR NOTARIO DE FE PÚBLICA\n"
        "Entre los documentos de escrituras públicas que se encuentran a su cargo sírvase\n"
        "insertar una de GUARDA DEFINITIVA Y / O TUTELA, DERECHO DE VISITA.\n"
        "PRIMERA: (DE LAS PARTES) Dirá usted señor notario que son parte del presente documento:\n"
        "1.- JUAN CHILE ARIAS. Con C.I:5918362 Cbba., quien es mayor de edad, hábil por ley\n"
        "de nacionalidad boliviano, de ocupación Albañil, con domicilio en Pucara Molle Molle - Cbba.\n"
        "2.- ROBERTA HUMACAYA MAMANI, con C.I: 5932821 Cbba., quien es mayor de edad.\n"
        "SEGUNDA: (DE LOS ANTECEDENTES) según sentencia de fecha 08 de Agosto del presente año.\n"
        "CUARTO: (DE LOS BIENES) compraron un lote de terreno Registrado en Derechos Reales a\n"
        "Fs. 2542, Ptda. 2542, en fecha 08 de Agosto de 1996. Con una superficie de 10.116 m2.\n"
        "Adquirido de su anterior dueño según documento de fecha 29 de Agosto del 2007, y\n"
        "reconocido ante Notario de Primera Clase Nro. 44 Dr. Tatiana Céspedes Morales.\n"
        "Ud. señor notario sirvase agregar las demás clausulas de estilo y seguridad.\n"
        "Cochabamba 26 de Agosto del 2014\n"
        "ADJUNTAR AL FORMULARIO DE RECONOCIMIENTO DE FIRMAS N° 3025076"
    )

    def _harvest(self, text, fields=None):
        reading = {"full_text": text, "pages": [{"fields": fields or [], "tables": []}]}
        return harvest(reading, self.FIELDS)[0]

    def test_reads_the_three_values_out_of_the_minuta(self):
        values = self._harvest(self.MINUTA)
        self.assertEqual(values["notary_number"], "48")
        self.assertEqual(values["owner_name"], "JUAN CHILE ARIAS, ROBERTA HUMACAYA MAMANI")
        self.assertEqual(values["statement_dates"], "26/08/2014")

    def test_every_poseedor_is_read_not_only_the_first(self):
        """La carpeta va a nombre de los dos cónyuges: quedarse con el primero
        obligaba a copiar el otro a mano sin que nada avisara que faltaba."""
        self.assertEqual(
            self._harvest(self.MINUTA)["owner_name"].split(", "),
            ["JUAN CHILE ARIAS", "ROBERTA HUMACAYA MAMANI"],
        )

    def test_the_same_poseedor_named_twice_is_kept_once(self):
        values = self._harvest(
            "1.- JUAN CHILE ARIAS. Con C.I:5918362 Cbba. "
            "Reitera el señor JUAN CHILE ARIAS, con C.I: 5918362 Cbba."
        )
        self.assertEqual(values["owner_name"], "JUAN CHILE ARIAS")

    def test_a_looser_wording_does_not_add_a_second_reading_of_the_same_person(self):
        """Un acta la lee la frase "se hizo presente"; el patrón suelto de la
        minuta leería la misma persona arrastrando la palabra de antes, y las dos
        lecturas quedaban juntas."""
        values = self._harvest(
            "se hizo presente NOELIA ALMENDRAS RODRIGUEZ con Cédula de Identidad N° 8806991"
        )
        self.assertEqual(values["owner_name"], "NOELIA ALMENDRAS RODRIGUEZ")

    def test_the_notary_of_the_stamp_is_read_through_its_office(self):
        """El sello mete el oficio entre el nombre del cargo y el número."""
        self.assertEqual(
            self._harvest("NOTARIA DE FE PUBLICA DE PRIMERA CLASE No. 48")["notary_number"], "48"
        )

    def test_the_notary_of_an_earlier_document_is_not_taken(self):
        """La minuta nombra al notario que reconoció el documento anterior. Ese
        no lleva "de fe pública" delante y no es el de esta hoja."""
        self.assertIsNone(
            self._harvest("reconocido ante Notario de Primera Clase Nro. 44")["notary_number"]
        )

    def test_the_heading_does_not_pass_as_the_number_of_the_notary(self):
        """"NOTARIO" encabeza la hoja y le prestaba su línea a "DE FE PUBLICA",
        que se guardaba como si fuera el número."""
        values = self._harvest(
            "SEÑOR NOTARIO DE FE PUBLICA", [{"name": "NOTARIO", "value": "DE FE"}]
        )
        self.assertIsNone(values["notary_number"])

    def test_the_date_of_the_act_wins_over_the_ones_it_cites(self):
        """1996 y 2007 son del antecedente y vienen antes en la hoja; 2014 es la
        de la minuta y cierra el documento."""
        self.assertEqual(self._harvest(self.MINUTA)["statement_dates"], "26/08/2014")

    def test_a_year_written_after_del(self):
        self.assertEqual(
            self._harvest("Cochabamba 26 de Agosto del 2014")["statement_dates"], "26/08/2014"
        )

    def test_a_sheet_whose_only_date_is_presented_as_one_is_still_read(self):
        """Si no hay otra, la fecha citada es la que hay."""
        self.assertEqual(
            self._harvest("Declaración jurada de fecha 12 de marzo de 2025")["statement_dates"],
            "12/03/2025",
        )

    def test_the_name_is_cut_at_the_identity_card(self):
        values = self._harvest("2.- ROBERTA HUMACAYA MAMANI, con C.I: 5932821 Cbba., mayor de edad")
        self.assertEqual(values["owner_name"], "ROBERTA HUMACAYA MAMANI")


class SelloDelNotarioTests(unittest.TestCase):
    """El número del notario sale del sello, que es donde siempre está.

    La redacción no lo trae: una minuta va dirigida al notario y no lo nombra, y
    el notario que sí nombra es el que reconoció el documento anterior. El sello
    se busca en la foto y se lee aparte, así que acá llega el texto de UN sello y
    lo que se comprueba es qué número se le saca.
    """

    FIELDS = document_fields("possessors", DocumentType.FORM)

    def test_the_number_is_read_out_of_a_legend_the_ocr_broke(self):
        """Tal como vuelve un sello redondo: sin "PUBLICA", con el oficio pegado
        al número y la N leída como parte de la palabra de antes."""
        self.assertEqual(
            from_seals(["NOTARIA DEFE PULCA DEP.SMERA CLAN0.48 COCHABAMBA BOLIVIA"], self.FIELDS),
            {"notary_number": "48"},
        )

    def test_the_number_without_its_mark(self):
        """Al sello le comió la marca: queda el oficio y el número."""
        self.assertEqual(
            from_seals(["ABOGADO NOTARIA DE FE PUBLICA DE PRIMERA CLASE 48"], self.FIELDS),
            {"notary_number": "48"},
        )

    def test_a_stamp_with_no_number_leaves_the_field_to_the_text(self):
        self.assertEqual(from_seals(["NOTARIA DE FE PUBLICA COCHABAMBA BOLIVIA"], self.FIELDS), {})

    def test_no_more_stamps_are_read_once_the_number_came_out(self):
        """Cada lectura de sello cuesta una llamada al OCR: en cuanto el número
        salió, las fotos que siguen no se procesan."""
        asked = []

        def texts():
            for text in ["ILEGIBLE", "NOTARIA DE FE PUBLICA No 23", "OTRO SELLO No 99"]:
                asked.append(text)
                yield text

        self.assertEqual(from_seals(texts(), self.FIELDS), {"notary_number": "23"})
        self.assertEqual(len(asked), 2)

    def test_a_document_that_asks_for_nothing_stamped_reads_no_stamp(self):
        """El plano no tiene nada en un sello, así que no se le busca ninguno."""
        self.assertEqual(from_seals(["NOTARIA No 23"], document_fields("possessors", DocumentType.PLAN)), {})


class LecturaDelSelloConOpenCvTests(unittest.TestCase):
    """El sello encontrado en la foto, con OpenCV de verdad y el OCR falso.

    Lo que se comprueba no es qué dice el sello --eso lo deciden los patrones del
    catálogo-- sino que se lo encuentre en la hoja y que lo que se manda a leer
    sea el sello y no la página entera.
    """

    def _reader(self, answers):
        self.asked = []

        def read_page(content, filename=None):
            image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
            self.asked.append((filename, image))
            text = answers.pop(0) if answers else ""
            blocks = [TextBlock(text, 0.95, 0, 0, 10, 10)] if text else []
            return PageText(blocks=blocks, width=10, height=10)

        return OpenCvSealReader(read_page=read_page)

    def test_the_stamp_is_found_and_only_the_stamp_is_sent_to_the_ocr(self):
        reader = self._reader(["NOTARIA DE FE PUBLICA No.48"])
        self.assertEqual(next(reader.read([_sheet_with_seal()])), "NOTARIA DE FE PUBLICA No.48")
        self.assertEqual(len(self.asked), 1)
        name, crop = self.asked[0]
        self.assertTrue(name.startswith("sello_p1"), name)
        # El recorte es cuadrado y es el sello: la hoja es más alta que ancha.
        self.assertAlmostEqual(crop.shape[0] / crop.shape[1], 1.0, delta=0.05)

    def test_the_ring_is_unwrapped_when_the_straight_crop_said_nothing(self):
        """La leyenda va curvada: puesta en línea es una tira ancha y baja."""
        reader = self._reader(["", "NOTARIA DE FE PUBLICA No.48"])
        self.assertEqual(next(reader.read([_sheet_with_seal()])), "NOTARIA DE FE PUBLICA No.48")
        self.assertEqual(len(self.asked), 2)
        _name, strip = self.asked[1]
        self.assertGreater(strip.shape[1], strip.shape[0] * 3)

    def test_a_sheet_with_no_stamp_costs_no_ocr_call(self):
        reader = self._reader(["lo que sea"])
        self.assertEqual(list(reader.read([_png()])), [])
        self.assertEqual(self.asked, [])

    def test_a_photo_that_is_not_an_image_is_skipped(self):
        reader = self._reader(["lo que sea"])
        self.assertEqual(list(reader.read([b"esto no es una imagen"])), [])
        self.assertEqual(self.asked, [])


class LoQueElOcrDevuelveDeVerdadTests(unittest.TestCase):
    """Los mismos campos, pero sobre el texto tal como sale del OCR.

    Las reglas se escribieron mirando el papel y por eso no encontraban nada: la
    hoja llega fotografiada y PaddleOCR la devuelve rota. Los textos de abajo son
    literales de la lectura de una minuta de cuatro hojas, no una transcripción
    -- se perdían el notario, la fecha y la segunda poseedora.
    """

    FIELDS = document_fields("possessors", DocumentType.FORM)

    def _harvest(self, text):
        return harvest({"full_text": text, "pages": [{"fields": [], "tables": []}]}, self.FIELDS)[0]

    def test_the_number_of_a_stamp_the_ocr_broke_apart(self):
        """El sello es redondo y va girado: "NOTARIA DE FE PUBLICA DE PRIMERA
        CLASE No. 48" vuelve partido, sin "PUBLICA", con "DE FE" pegado y con la
        O del "No." cambiada por un cero."""
        for read_as in (
            "ABOGADO NOTARIA DEFE PULCA DEP.SMERA CLAN0.48",
            "RICo AROGADO NOTARIADEFE PURUCA DEPAIMERA CLASENo.48",
        ):
            with self.subTest(read_as=read_as):
                self.assertEqual(self._harvest(read_as)["notary_number"], "48")

    def test_the_i_of_the_identity_card_read_as_an_l(self):
        """"con C.I: 5932821" vuelve "CON C.L:5932821", y con la I exigida la
        segunda poseedora no entraba."""
        values = self._harvest("A. 2.-ROBERTA HUMACAYA MAMANI,CON C.L:5932821 Cbba.")
        self.assertEqual(values["owner_name"], "ROBERTA HUMACAYA MAMANI")

    def test_the_closing_date_written_over_the_ruled_line(self):
        """La fecha va escrita sobre el renglón: el OCR mete barras donde hay
        espacios y lee un cero en "Agosto"."""
        values = self._harvest("Y SEGURIDAD. CHABAMBA/26 DE/AGOST0 DEL 2014 3025076")
        self.assertEqual(values["statement_dates"], "26/08/2014")

    def test_the_whole_reading_gives_the_three_values(self):
        values = self._harvest(
            "ABOGADO NOTARIA DEFE PULCA DEP.SMERA CLAN0.48 SENORNOTARIODEFEPUBLICA\n"
            "Entre los dacumentos de escrituras publicas que se encuentran a su cargo\n"
            "PRIMERA: (DE LAS PARTES) Dirä usted senor notario que son parte del\n"
            "presente-documento: 1.-JUAN CHILE ARIAS.Con C.I:5918362 Cbba.,quien es mayor de edad,\n"
            "2.-ROBERTA HUMACAYA MAMANI,con C.l:5932821 Cbba.,quien es mayor\n"
            "segün sentencia de fecha 08 de Agosto del presente ano. tramitado. en el\n"
            "reconocido ante Notario de Primera Clase Nro. 44 Dr. Tatiana Cespedes Morales\n"
            "categoria de instrumento duplico y Ud. serior notario sirvase agregar las\n"
            "demas clausulas.de estilo y seguridad. chabamba/26 de/Agost0 del 2014 3025076"
        )
        self.assertEqual(values["notary_number"], "48")
        self.assertEqual(values["owner_name"], "JUAN CHILE ARIAS, ROBERTA HUMACAYA MAMANI")
        self.assertEqual(values["statement_dates"], "26/08/2014")


class FechasEnLetrasTests(unittest.TestCase):
    def test_the_year_of_an_old_minuta_and_of_a_recent_one(self):
        self.assertEqual(words_to_number("MIL NOVECIENTOS NOVENTA Y DOS"), 1992)
        self.assertEqual(words_to_number("DOS MIL VEINTISEIS"), 2026)

    def test_the_ways_a_day_is_written(self):
        self.assertEqual(words_to_number("VEINTIUN"), 21)
        self.assertEqual(words_to_number("PRIMERO"), 1)
        self.assertEqual(words_to_number("TREINTA Y UNO"), 31)

    def test_what_is_not_a_number_is_not_invented(self):
        self.assertIsNone(words_to_number("CUALQUIER COSA"))
        self.assertIsNone(words_to_number(""))

    def test_the_three_parts_become_one_date(self):
        self.assertEqual(to_iso_like("VEINTIUN", "SEPTIEMBRE", "DOS MIL VEINTISEIS"), "21/09/2026")
        self.assertEqual(to_iso_like("5", "ENERO", "1998"), "05/01/1998")

    def test_half_a_date_is_no_date(self):
        """Una fecha a medias es peor que ninguna: nadie la vuelve a mirar."""
        self.assertIsNone(to_iso_like("CUARENTA", "SEPTIEMBRE", "DOS MIL"))
        self.assertIsNone(to_iso_like("DIEZ", "BRUMARIO", "DOS MIL"))
        self.assertIsNone(to_iso_like("DIEZ", "ENERO", "MIL OCHOCIENTOS"))


class LecturaQueLlenaLaCarpetaTests(unittest.TestCase):
    """Lo leído de un documento entra en la hoja de su carpeta: es lo que hace
    que "notario" o "propietario" no se tengan que copiar a mano."""

    def setUp(self):
        self.captures, self.documents = FakeCaptures(), FakeDocuments()
        self.folders = FakeRegisteredFolders(self.documents)
        self.service = RegisteredFolderService(self.folders, self.documents)
        self.photo = self.captures.create("arq-1", "p.png", "image/png", b"x", b"t")

    def _read(self, document, data, seals=None, vision=None, vision_max_pages=3):
        RunServerReadingUseCase(
            self.documents,
            self.captures,
            {document.doc_type: FakeExtractor(data)},
            folders=self.folders,
            seals=seals,
            vision=vision,
            vision_max_pages=vision_max_pages,
        ).execute(document.id, "arq-1")
        return self.documents.get(document.id, "arq-1")

    def _document(self, folder=None, doc_type=DocumentType.FORM):
        document = CreateDocumentUseCase(self.documents, self.captures, self.folders).execute(
            doc_type, [self.photo.id], "arq-1", folder.id if folder else None, "possessors"
        )
        AnalyzeDocumentUseCase(self.documents, self.captures, FakeQueue()).execute(
            document.id, "arq-1"
        )
        return self.documents.get(document.id, "arq-1")

    def _folder(self, data=None):
        return CreateRegisteredFolderUseCase(self.folders, self.service).execute(
            "arq-1", "Poseedores Sarco", None, folder_type_key="possessors", data=data
        )

    @staticmethod
    def _statement():
        return {
            "full_text": "DECLARACION JURADA",
            "pages": [
                {
                    "fields": [
                        {"name": "NOTARIA", "value": "N 23"},
                        {"name": "PROPIETARIO", "value": "MARIA LOPEZ"},
                        {"name": "FECHA", "value": "12 de marzo de 2025"},
                    ],
                    "full_text": "DECLARACION JURADA",
                    "tables": [],
                }
            ],
            "reading": {"observations": []},
        }

    def test_the_read_values_are_stored_next_to_the_text(self):
        document = self._read(self._document(), self._statement())
        self.assertEqual(
            document.extracted_data["values"],
            {"notary_number": "23", "owner_name": "MARIA LOPEZ", "statement_dates": "12/03/2025"},
        )
        # La lectura entera se conserva: los valores se suman, no la reemplazan.
        self.assertEqual(document.extracted_data["full_text"], "DECLARACION JURADA")

    # El plano, que es de donde la hoja de la carpeta toma su único campo leído.
    CODE = "00-33-432-012-0-00-000-000"

    def _plan(self):
        return {
            "full_text": f"PLANO DE UBICACION\nCódigo Catastral: {self.CODE}",
            "pages": [],
            "reading": {"observations": []},
        }

    def test_they_fill_the_empty_fields_of_the_carpeta(self):
        folder = self._folder()
        self._read(self._document(folder, DocumentType.PLAN), self._plan())
        self.assertEqual(self.folders.get(folder.id, "arq-1").data["cadastral_code"], self.CODE)

    def test_what_the_architect_typed_is_never_overwritten(self):
        folder = self._folder({"cadastral_code": "Como lo escribí yo"})
        self._read(self._document(folder, DocumentType.PLAN), self._plan())
        self.assertEqual(
            self.folders.get(folder.id, "arq-1").data["cadastral_code"], "Como lo escribí yo"
        )

    def test_a_document_outside_a_carpeta_still_gets_its_values(self):
        """En el tablero suelto no hay carpeta que llenar, pero el tipo elegido
        ahí es el que dice qué sacarle al documento."""
        document = self._read(self._document(), self._statement())
        self.assertEqual(document.folder_type, "possessors")
        self.assertEqual(document.extracted_data["values"]["notary_number"], "23")

    def test_a_document_of_a_kind_that_asks_for_nothing_is_left_as_read(self):
        document = CreateDocumentUseCase(self.documents, self.captures, self.folders).execute(
            DocumentType.FOLIO, [self.photo.id], "arq-1"
        )
        AnalyzeDocumentUseCase(self.documents, self.captures, FakeQueue()).execute(
            document.id, "arq-1"
        )
        read = self._read(self.documents.get(document.id, "arq-1"), {"full_text": "FOLIO REAL"})
        self.assertNotIn("values", read.extracted_data)

    def test_the_number_of_the_stamp_wins_over_the_one_in_the_text(self):
        """El notario escrito en una minuta es el del documento anterior; el de
        esta hoja está en el sello, y es el que vale."""
        document = self._read(
            self._document(doc_type=DocumentType.FORM),
            {
                "full_text": "reconocido ante Notaria de Fe Publica Nro. 44",
                "pages": [],
                "reading": {"observations": []},
            },
            seals=FakeSeals(["NOTARIA DEFE PULCA DEP.SMERA CLAN0.48"]),
        )
        self.assertEqual(document.extracted_data["values"]["notary_number"], "48")

    def test_a_stamp_that_disagrees_with_the_text_is_said_so(self):
        """Tomar uno de los dos en silencio es lo que no se puede hacer: el
        arquitecto tiene que poder mirar la foto."""
        document = self._read(
            self._document(doc_type=DocumentType.FORM),
            {
                "full_text": "reconocido ante Notaria de Fe Publica Nro. 44",
                "pages": [],
                "reading": {"observations": []},
            },
            seals=FakeSeals(["NOTARIA DE FE PUBLICA No 48"]),
        )
        notes = document.extracted_data["reading"]["observations"]
        self.assertTrue(any("sello" in note and "48" in note and "44" in note for note in notes), notes)

    def test_the_text_answers_when_no_stamp_was_found(self):
        document = self._read(
            self._document(doc_type=DocumentType.FORM),
            {
                "full_text": "ante mí, Notaria de Fe Pública Nº 3, compareció JUAN PEREZ LOPEZ con C.I. 123",
                "pages": [],
                "reading": {"observations": []},
            },
            seals=FakeSeals([]),
        )
        self.assertEqual(document.extracted_data["values"]["notary_number"], "3")

    def test_the_stamp_is_looked_for_in_the_photos_of_the_document(self):
        seals = FakeSeals(["NOTARIA DE FE PUBLICA No 23"])
        self._read(
            self._document(doc_type=DocumentType.FORM),
            {"full_text": "HOJA SIN NOTARIO", "pages": [], "reading": {"observations": []}},
            seals=seals,
        )
        self.assertEqual(seals.pages, [[b"x"]])

    def test_what_the_stamp_gave_is_not_reported_as_missing(self):
        """Nombrarlo como vacío mandaría a cargar a mano algo que ya está leído."""
        document = self._read(
            self._document(doc_type=DocumentType.FORM),
            {"full_text": "HOJA SIN NOTARIO", "pages": [], "reading": {"observations": []}},
            seals=FakeSeals(["NOTARIA DE FE PUBLICA No 23"]),
        )
        self.assertEqual(document.extracted_data["values"]["notary_number"], "23")
        notes = document.extracted_data["reading"]["observations"]
        missing = next(note for note in notes if "No se encontraron" in note)
        self.assertNotIn("Notario", missing)

    def test_a_stamp_reader_that_breaks_leaves_the_reading_as_it_was(self):
        class Roto(SealReadingPort):
            def read(self, pages):
                raise RuntimeError("el servicio de OCR no responde")
                yield ""  # pragma: no cover - lo hace generador, como el de verdad

        document = self._read(
            self._document(doc_type=DocumentType.FORM),
            {
                "full_text": "ante mí, Notaria de Fe Pública Nº 3",
                "pages": [],
                "reading": {"observations": []},
            },
            seals=Roto(),
        )
        self.assertEqual(document.extracted_data["values"]["notary_number"], "3")

    def test_what_was_not_found_is_written_in_the_observations(self):
        """El arquitecto tiene que ver qué quedó vacío, no descubrirlo después."""
        document = self._read(
            self._document(),
            {"full_text": "HOJA VACIA", "pages": [], "reading": {"observations": []}},
        )
        notes = document.extracted_data["reading"]["observations"]
        self.assertTrue(any("No se encontraron" in note for note in notes), notes)


class BuscarCarpetasDeOtrosUsuariosTests(unittest.TestCase):
    """Buscar una carpeta registrada por su nombre.

    Una carpeta física la escanea quien la tiene en la mano, así que queda a su
    nombre y el resto no podía volver a encontrarla. Quien administra el módulo
    busca entre las de todos; quien no, entre las suyas, que es lo mismo que
    filtrar su lista. En los dos casos es solo buscar y solo por nombre: una
    carpeta ajena no entra en la lista de nadie ni se puede escribir.
    """

    def setUp(self):
        self.documents = FakeDocuments()
        self.folders = FakeRegisteredFolders(self.documents)
        self.service = RegisteredFolderService(self.folders, self.documents)
        self._folder("arq-1", "Carpeta 1024")
        self._folder("arq-2", "Carpeta 2048")
        self._folder("arq-2", "Carpeta 2049")

    def _folder(self, user_sub, name):
        return CreateRegisteredFolderUseCase(self.folders, self.service).execute(user_sub, name)

    def _search(self, name, across_users=False, user_sub="arq-1"):
        found = SearchRegisteredFoldersUseCase(self.folders).execute(
            user_sub, name, across_users=across_users
        )
        return [folder.name for folder in found]

    def test_an_administrator_finds_the_carpeta_of_another_user(self):
        self.assertEqual(self._search("2048", across_users=True), ["Carpeta 2048"])

    def test_without_the_permission_only_the_own_carpetas_are_searched(self):
        self.assertEqual(self._search("2048"), [])
        self.assertEqual(self._search("1024"), ["Carpeta 1024"])

    def test_the_search_is_by_name_and_not_a_listing(self):
        """Lo ajeno aparece porque se lo buscó: la lista sigue siendo la propia."""
        self.assertEqual([f.name for f in self.folders.list("arq-1")], ["Carpeta 1024"])

    def test_several_matches_come_back_a_to_z(self):
        self.assertEqual(
            self._search("Carpeta 204", across_users=True), ["Carpeta 2048", "Carpeta 2049"]
        )

    def test_a_term_too_short_searches_nothing(self):
        """Con una letra, buscar entre las de todos devuelve media base."""
        self.assertEqual(self._search("2", across_users=True), [])
        self.assertEqual(self._search("", across_users=True), [])

    def test_a_carpeta_of_another_user_still_cannot_be_opened_by_id(self):
        """Encontrarla no es poder entrar en ella: lo que escribe pasa por
        require_folder, que sigue exigiendo ser el dueño."""
        found = SearchRegisteredFoldersUseCase(self.folders).execute(
            "arq-1", "2048", across_users=True
        )
        with self.assertRaises(RegisteredFolderNotFoundException):
            self.service.require_folder(found[0].id, "arq-1")

    def test_the_photos_of_a_carpeta_found_this_way_can_be_looked_at(self):
        """Encontrarla sirve de poco sin ver lo escaneado: las fotos se piden por
        la carpeta, no por su dueño."""
        captures = FakeCaptures()
        documents = FakeDocuments()
        folders = FakeRegisteredFolders(documents)
        service = RegisteredFolderService(folders, documents)
        photo = captures.create("arq-2", "p.png", "image/png", b"la foto", b"mini")
        document = documents.create("arq-2", DocumentType.PLAN, [photo.id])
        folder = CreateRegisteredFolderUseCase(folders, service).execute("arq-2", "Carpeta 4096")
        # Como cuando se escanea dentro de la carpeta: entra en ella desde que se abre.
        folders.file_document(folder.id, document.id)
        use_case = GetFolderPhotoUseCase(folders, GetCaptureImageUseCase(captures, OpenCvThumbnail()))

        content, _mime = use_case.execute(
            folder.id, photo.id, "arq-1", administra=True, variant="original"
        )
        self.assertEqual(content, b"la foto")

    def test_without_the_permission_the_photos_of_another_user_are_out_of_reach(self):
        captures = FakeCaptures()
        documents = FakeDocuments()
        folders = FakeRegisteredFolders(documents)
        service = RegisteredFolderService(folders, documents)
        photo = captures.create("arq-2", "p.png", "image/png", b"la foto", b"mini")
        document = documents.create("arq-2", DocumentType.PLAN, [photo.id])
        folder = CreateRegisteredFolderUseCase(folders, service).execute("arq-2", "Carpeta 4096")
        # Como cuando se escanea dentro de la carpeta: entra en ella desde que se abre.
        folders.file_document(folder.id, document.id)
        use_case = GetFolderPhotoUseCase(folders, GetCaptureImageUseCase(captures, OpenCvThumbnail()))

        with self.assertRaises(RegisteredFolderNotFoundException):
            use_case.execute(folder.id, photo.id, "arq-1", administra=False, variant="original")

    def test_a_photo_that_is_not_of_that_carpeta_is_not_served_through_it(self):
        """La carpeta no es una puerta a la bandeja de su dueño: solo se llega a
        lo que está archivado en ella."""
        captures = FakeCaptures()
        documents = FakeDocuments()
        folders = FakeRegisteredFolders(documents)
        service = RegisteredFolderService(folders, documents)
        suelta = captures.create("arq-2", "otra.png", "image/png", b"suelta", b"mini")
        folder = CreateRegisteredFolderUseCase(folders, service).execute("arq-2", "Carpeta 4096")
        use_case = GetFolderPhotoUseCase(folders, GetCaptureImageUseCase(captures, OpenCvThumbnail()))

        with self.assertRaises(CaptureNotFoundException):
            use_case.execute(folder.id, suelta.id, "arq-1", administra=True, variant="original")

    def test_the_answer_says_whose_each_carpeta_is(self):
        """Es lo que la pantalla usa para marcarla como ajena y de solo lectura."""
        found = SearchRegisteredFoldersUseCase(self.folders).execute(
            "arq-1", "Carpeta", across_users=True
        )
        self.assertEqual(
            {folder.name: folder.user_sub for folder in found},
            {"Carpeta 1024": "arq-1", "Carpeta 2048": "arq-2", "Carpeta 2049": "arq-2"},
        )


class CatalogoDeCarpetasTests(unittest.TestCase):
    """The catalogue is data, so what is tested is that it holds together: a
    carpeta cannot ask for a document that does not exist, and a field cannot
    say it is copied from somewhere without saying from where."""

    def test_every_document_of_a_carpeta_is_a_known_document_type(self):
        for spec in FOLDER_TYPES.values():
            for doc_type in spec.document_types:
                self.assertIn(doc_type, DOCUMENT_TYPES, f"{spec.key} pide {doc_type}")

    def test_every_document_type_is_in_the_catalogue(self):
        """A type the board can create but the catalogue does not name would
        reach the screen with no label and no hint."""
        self.assertEqual(set(DOCUMENT_TYPES), set(DocumentType.ALL))

    def test_the_fields_of_a_carpeta_do_not_repeat_their_key(self):
        for spec in FOLDER_TYPES.values():
            keys = [field.key for field in spec.fields]
            self.assertEqual(len(keys), len(set(keys)), f"{spec.key} repite un campo")

    def test_a_field_read_off_a_document_names_a_document_the_carpeta_holds(self):
        for spec in FOLDER_TYPES.values():
            for field in spec.fields:
                if field.source == FieldSource.DOCUMENT:
                    self.assertIn(field.from_document, spec.document_types, field.key)

    def test_a_fixed_field_says_what_it_always_says(self):
        for spec in FOLDER_TYPES.values():
            for field in spec.fields:
                if field.source == FieldSource.FIXED:
                    self.assertTrue(field.value, field.key)

    def test_poseedores_carries_its_four_documents_and_its_sheet(self):
        """Eran cinco: el carril de declaración jurada se quitó, porque es la
        misma hoja que el formulario. Con él se fue el apartado de la hoja que se
        llenaba desde ahí."""
        poseedores = folder_type("possessors")
        self.assertEqual(
            poseedores.document_types,
            (
                DocumentType.APPRAISAL,
                DocumentType.PLAN,
                DocumentType.FORM,
                DocumentType.ID_CARD,
            ),
        )
        self.assertEqual(
            [field.key for field in poseedores.fields],
            [
                "cadastral_code", "street", "boundaries", "frontage", "rear_frontage", "depth", "depth_2",
                "usable_area",
            ],
        )

    def test_the_catalogue_says_which_fields_carry_several_values(self):
        """La pantalla le da un apartado a cada poseedor, y para saber a qué campo
        hacerle eso no lo conoce por su nombre: se lo dice el catálogo."""
        poseedores = folder_type("possessors")
        values = {
            doc_type: {field.key: field for field in document_fields(poseedores.key, doc_type)}
            for doc_type in poseedores.document_types
            if document_fields(poseedores.key, doc_type)
        }
        owner = values[DocumentType.FORM]["owner_name"]
        self.assertTrue(owner.collect_all)
        self.assertEqual(owner.item_label, "Poseedor")
        # Y el que trae uno solo no lo dice, así que la pantalla le da una caja.
        self.assertFalse(values[DocumentType.FORM]["notary_number"].collect_all)
        self.assertIsNone(values[DocumentType.FORM]["notary_number"].item_label)

    def test_what_carries_several_reaches_the_screen_as_such(self):
        """El contrato con la web: sin estas dos claves la pantalla no tendría de
        dónde saberlo (presentation/schemas, DocumentValueOut)."""
        catalog = CatalogOut.current()
        poseedores = next(ft for ft in catalog.folder_types if ft.key == "possessors")
        by_key = {v.key: v for v in poseedores.document_values[DocumentType.FORM]}
        self.assertTrue(by_key["owner_name"].multiple)
        self.assertEqual(by_key["owner_name"].item_label, "Poseedor")
        self.assertFalse(by_key["statement_dates"].multiple)

    def test_several_owners_travel_in_one_text_separated_by_comma(self):
        """Es la forma que la pantalla abre en apartados y vuelve a cerrar para
        guardar. Si esto cambia, hay que cambiar utils/multiValue.js con ella."""
        values, _ = harvest(
            {
                "full_text": (
                    "se hicieron presentes JUAN PEREZ LOPEZ con C.I. 123456 "
                    "y MARIA ROJAS VARGAS con C.I. 654321"
                ),
                "pages": [],
            },
            document_fields("possessors", DocumentType.FORM),
        )
        self.assertEqual(values["owner_name"], "JUAN PEREZ LOPEZ, MARIA ROJAS VARGAS")

    def test_the_lane_that_was_retired_is_in_no_carpeta(self):
        """El tipo sigue en el catálogo por los documentos que ya se guardaron con
        él --sin su entrada perderían el nombre en pantalla-- pero ninguna carpeta
        lo lleva, así que no se puede crear uno nuevo."""
        self.assertIn(DocumentType.SWORN_STATEMENT, DOCUMENT_TYPES)
        for spec in FOLDER_TYPES.values():
            with self.subTest(spec.key):
                self.assertNotIn(DocumentType.SWORN_STATEMENT, spec.document_types)

    def test_an_unknown_carpeta_falls_back_to_the_general_one(self):
        """The carpetas created before the catalogue carry no kind, and they
        keep opening with the three lanes they were filed with."""
        self.assertEqual(folder_type(None).key, "general")
        self.assertEqual(
            folder_type("una-que-no-existe").document_types,
            (DocumentType.FOLIO, DocumentType.TAX_RECEIPT, DocumentType.PLAN),
        )


class PerfilDeExtraccionPorCarpetaTests(unittest.TestCase):
    def test_without_a_carpeta_a_document_keeps_its_own_profile(self):
        self.assertIs(profile_for(DocumentType.FOLIO), PROFILES[DocumentType.FOLIO])

    def test_a_carpeta_that_says_nothing_reads_the_document_the_usual_way(self):
        self.assertIs(profile_for(DocumentType.FOLIO, "possessors"), PROFILES[DocumentType.FOLIO])

    def test_a_carpeta_can_ask_for_its_own_reading_of_a_document(self):
        mine = ExtractionProfile("solo la matrícula", {"registration_number": None})
        with patch.dict(FOLDER_PROFILES, {("possessors", DocumentType.FOLIO): mine}):
            self.assertIs(profile_for(DocumentType.FOLIO, "possessors"), mine)
            # ...and only inside that carpeta.
            self.assertIs(profile_for(DocumentType.FOLIO, "general"), PROFILES[DocumentType.FOLIO])

    def test_a_document_with_no_rules_gets_the_generic_digitization(self):
        self.assertIs(profile_for(DocumentType.SWORN_STATEMENT), GENERIC_PROFILE)


class ResolucionMinisterialNoEsElNotarioTests(unittest.TestCase):
    """Un formulario notarial imprime "Resolución Ministerial Nº 57/2020" debajo
    del título, a un centímetro del sello. Esa marca de número se lee igual que la
    del sello, así que 57 entraba donde iba el número del notario -- y 57 es el
    mismo en TODOS los formularios, así que no era un valor flojo sino el de otro
    campo."""

    FIELDS = document_fields("possessors", DocumentType.FORM)

    def _harvest(self, text):
        return harvest({"full_text": text, "pages": []}, self.FIELDS)[0]

    def test_the_number_of_the_resolution_is_not_taken_as_the_notary(self):
        values = self._harvest(
            "NOTARIA DE FE PUBLICA FORMULARIO NOTARIAL Resolucion Ministerial N° 57/2020"
        )
        self.assertIsNone(values["notary_number"])

    def test_the_notary_is_still_read_when_the_resolution_comes_first(self):
        """Descartar uno no puede apagar el patrón: lo que viene después sigue
        buscándose."""
        values = self._harvest(
            "FORMULARIO NOTARIAL Resolucion Ministerial N° 57/2020 "
            "ante mi, Notaria de Fe Publica N° 37, se hizo presente"
        )
        self.assertEqual(values["notary_number"], "37")

    def test_the_seal_does_not_take_it_either(self):
        """El recorte del sello alcanza esa línea cuando el círculo detectado sale
        un poco grande, que es lo que pasó con la foto que lo destapó."""
        self.assertEqual(
            from_seals(["FORMULARIO NOTARIAL Resolucion Ministerial N° 57/2020"], self.FIELDS),
            {},
        )

    def test_the_mark_of_the_seal_without_its_little_o(self):
        """El "º" chico del sello se pierde en la foto más veces de las que se
        lee: "N 37" bajo "NOTARIA DE FE PUBLICA"."""
        self.assertEqual(
            from_seals(["NOTARIA DE FE PUBLICA N 37 25.04.2018"], self.FIELDS),
            {"notary_number": "37"},
        )


class LoQueSeLePreguntaALaFotoTests(unittest.TestCase):
    """Qué campos van a la pasada del modelo de visión y qué se guarda de lo que
    conteste. Cada foto cuesta medio minuto de una computadora de los arquitectos,
    así que lo que NO se pregunta importa tanto como lo que sí."""

    FIELDS = document_fields("possessors", DocumentType.FORM)

    def _keys(self, values):
        return [spec.key for spec in vision_wanted(self.FIELDS, values)]

    def test_what_is_stamped_is_asked_even_when_the_text_answered(self):
        """El número del notario vive en un sello y al lado está la resolución
        ministerial: que el texto haya dicho algo no quiere decir que sea eso."""
        self.assertIn("notary_number", self._keys({"notary_number": "57"}))

    def test_what_the_text_read_well_is_not_sent_to_a_model(self):
        values = {
            "notary_number": "37",
            "owner_name": "MARIA LOPEZ",
            "statement_dates": "12/03/2025",
        }
        self.assertEqual(self._keys(values), ["notary_number"])

    def test_an_empty_field_is_asked_for(self):
        self.assertIn("owner_name", self._keys({"owner_name": None}))

    def test_a_document_that_declares_nothing_costs_no_call(self):
        self.assertEqual(vision_wanted(document_fields("possessors", DocumentType.PLAN), {}), [])

    def test_only_the_number_of_the_notary_is_kept(self):
        answer = from_vision({"notary_number": "Notaría N° 37"}, self.FIELDS)
        self.assertEqual(answer["notary_number"], "37")

    def test_what_the_photo_does_not_show_stays_empty(self):
        """null y "[ilegible]" son las dos formas en que se le pidió decir que no
        está: ninguna de las dos entra en la carpeta."""
        answer = from_vision(
            {"notary_number": None, "owner_name": "[ilegible]", "statement_dates": ""},
            self.FIELDS,
        )
        self.assertEqual(answer, {})

    def test_a_key_nobody_asked_for_does_not_enter(self):
        self.assertEqual(from_vision({"inventado": "algo"}, self.FIELDS), {})


class LaFotoMiradaAlFinalTests(unittest.TestCase):
    """La última pasada de la lectura en servidor: el modelo de visión mirando la
    foto, después del OCR y del sello."""

    def setUp(self):
        self.captures, self.documents = FakeCaptures(), FakeDocuments()
        self.folders = FakeRegisteredFolders(self.documents)
        self.photo = self.captures.create("arq-1", "p.png", "image/png", b"x", b"t")

    def _of(self, doc_type, photos):
        document = CreateDocumentUseCase(self.documents, self.captures, self.folders).execute(
            doc_type, photos, "arq-1", None, "possessors"
        )
        AnalyzeDocumentUseCase(self.documents, self.captures, FakeQueue()).execute(
            document.id, "arq-1"
        )
        return self.documents.get(document.id, "arq-1")

    def _photos(self, count):
        return [
            self.captures.create("arq-1", "p%d.png" % i, "image/png", b"x", b"t").id
            for i in range(count)
        ]

    def _run(self, document, data, vision=None, seals=None, vision_max_pages=3):
        RunServerReadingUseCase(
            self.documents,
            self.captures,
            {document.doc_type: FakeExtractor(data)},
            folders=self.folders,
            seals=seals,
            vision=vision,
            vision_max_pages=vision_max_pages,
        ).execute(document.id, "arq-1")
        return self.documents.get(document.id, "arq-1")

    @staticmethod
    def _formulario(text="FORMULARIO NOTARIAL Resolucion Ministerial N° 57/2020"):
        return {"full_text": text, "pages": [], "reading": {"observations": []}}

    def test_what_is_seen_in_the_photo_wins_over_the_text(self):
        """El caso que destapó esto: el texto daba 57, el de la resolución
        ministerial, y en el sello de la hoja dice 37."""
        vision = FakeVision([{"notary_number": "37"}])
        document = self._run(
            self._of(DocumentType.FORM, [self.photo.id]),
            self._formulario("ante Notaria de Fe Publica N° 57, se hizo presente"),
            vision=vision,
        )
        self.assertEqual(document.extracted_data["values"]["notary_number"], "37")

    def test_a_disagreement_is_said_out_loud(self):
        vision = FakeVision([{"notary_number": "37"}])
        document = self._run(
            self._of(DocumentType.FORM, [self.photo.id]),
            self._formulario("ante Notaria de Fe Publica N° 57, se hizo presente"),
            vision=vision,
        )
        notes = document.extracted_data["reading"]["observations"]
        self.assertTrue(any("foto" in n and "37" in n and "57" in n for n in notes), notes)

    def test_the_photo_is_looked_at_after_the_stamp(self):
        """El sello se lee primero porque es barato; la foto decide al final."""
        vision = FakeVision([{"notary_number": "37"}])
        document = self._run(
            self._of(DocumentType.FORM, [self.photo.id]),
            self._formulario(),
            vision=vision,
            seals=FakeSeals(["NOTARIA DE FE PUBLICA No 48"]),
        )
        self.assertEqual(document.extracted_data["values"]["notary_number"], "37")

    def test_nothing_is_asked_when_the_pass_is_off(self):
        vision = FakeVision([{"notary_number": "37"}], configured=False)
        document = self._run(
            self._of(DocumentType.FORM, [self.photo.id]), self._formulario(), vision=vision
        )
        self.assertEqual(vision.asked, [])
        self.assertIsNone(document.extracted_data["values"]["notary_number"])

    def test_a_pass_that_is_off_says_so_instead_of_leaving_a_silence(self):
        """Había algo que preguntarle a la foto y no se pudo. Sin decirlo, el
        arquitecto ve el campo vacío y no tiene cómo saber si la hoja no lo dice o
        si faltó la pasada."""
        document = self._run(
            self._of(DocumentType.FORM, [self.photo.id]),
            self._formulario(),
            vision=FakeVision([], configured=False),
        )
        notes = document.extracted_data["reading"]["observations"]
        self.assertTrue(any("modelo de visión" in note for note in notes), notes)

    def test_a_document_with_nothing_to_ask_says_nothing_either(self):
        """El plano no le pregunta nada al modelo, así que que la pasada esté
        apagada no es noticia para él."""
        document = self._run(
            self._of(DocumentType.PLAN, [self.photo.id]),
            {"full_text": "PLANO", "pages": [], "reading": {"observations": []}},
            vision=FakeVision([], configured=False),
        )
        notes = document.extracted_data["reading"]["observations"]
        self.assertFalse(any("modelo de visión" in note for note in notes), notes)

    def test_a_computer_that_could_not_look_leaves_the_reading_as_it_was(self):
        """Una computadora apagada no puede hacer fallar una lectura que ya está
        hecha: queda lo que leyó el texto y queda dicho por qué."""
        vision = FakeVision([], fails=VisionReadingUnavailableException("Ninguna contestó."))
        document = self._run(
            self._of(DocumentType.FORM, [self.photo.id]),
            self._formulario("ante Notaria de Fe Publica N° 37, se hizo presente"),
            vision=vision,
        )
        self.assertEqual(document.status, DocumentStatus.EXTRACTED)
        self.assertEqual(document.extracted_data["values"]["notary_number"], "37")
        notes = document.extracted_data["reading"]["observations"]
        self.assertTrue(any("modelo de visión" in n for n in notes), notes)

    def test_an_unexpected_error_does_not_break_the_reading_either(self):
        vision = FakeVision([], fails=RuntimeError("boom"))
        document = self._run(
            self._of(DocumentType.FORM, [self.photo.id]), self._formulario(), vision=vision
        )
        self.assertEqual(document.status, DocumentStatus.EXTRACTED)

    def test_the_photos_that_follow_are_not_looked_at_once_everything_came_out(self):
        """Veinte segundos por foto: en cuanto están todos los campos, se corta."""
        vision = FakeVision(
            [{"notary_number": "37", "owner_name": "MARIA LOPEZ", "statement_dates": "12/03/2025"}]
        )
        self._run(self._of(DocumentType.FORM, self._photos(3)), self._formulario(), vision=vision)
        self.assertEqual(len(vision.asked), 1)

    def test_only_what_is_still_missing_is_asked_of_the_next_photo(self):
        vision = FakeVision([{"notary_number": "37"}, {"owner_name": "MARIA LOPEZ"}])
        self._run(self._of(DocumentType.FORM, self._photos(2)), self._formulario(), vision=vision)
        self.assertEqual(vision.asked[0], ["notary_number", "owner_name", "statement_dates"])
        self.assertEqual(vision.asked[1], ["owner_name", "statement_dates"])

    def test_a_long_document_does_not_cost_a_whole_computer(self):
        vision = FakeVision([])
        self._run(
            self._of(DocumentType.FORM, self._photos(6)),
            self._formulario(),
            vision=vision,
            vision_max_pages=2,
        )
        self.assertEqual(len(vision.asked), 2)

    def test_a_lane_that_asks_for_nothing_never_reaches_the_model(self):
        vision = FakeVision([{"notary_number": "37"}])
        self._run(
            self._of(DocumentType.PLAN, [self.photo.id]),
            {"full_text": "PLANO", "pages": []},
            vision=vision,
        )
        self.assertEqual(vision.asked, [])


class LaBandejaNoTieneTopeTests(unittest.TestCase):
    """Cuántas fotos entran en "Fotos recibidas" no se limita: una carpeta de
    poseedores llega con las hojas que llega, y hacer dos viajes porque el envío
    pasaba de diez archivos era trabajo inventado.

    Lo único que se mira es cuánto pesa junto lo que llega en UNA petición, que
    es lo que el servidor tiene que sostener en memoria mientras la lee entera.
    """

    def setUp(self):
        self.captures = FakeCaptures()

    def test_a_batch_far_over_the_old_ten_is_received(self):
        photos = [(_png(), "image/png", "p%d.png" % i) for i in range(40)]
        created = _uploader(self.captures).execute(photos, "arq-1")
        self.assertEqual(len(created), 40)
        self.assertEqual(len(self.captures.list_by_status("arq-1", CaptureStatus.INBOX)), 40)

    def test_the_inbox_holds_everything_that_was_sent(self):
        """Y en varios envíos también: la bandeja no se vacía ni se recorta."""
        uploader = _uploader(self.captures)
        for batch in range(3):
            uploader.execute([(_png(), "image/png", "b%d-%d.png" % (batch, i)) for i in range(15)], "arq-1")
        self.assertEqual(len(self.captures.list_by_status("arq-1", CaptureStatus.INBOX)), 45)

    def test_what_weighs_more_than_one_request_can_hold_is_refused_with_how_to_fix_it(self):
        """El tope que queda es de memoria, no de cantidad, y el mensaje lo dice:
        el arquitecto tiene que saber que puede mandarlas en dos tandas."""
        files = [(b"x" * 600, "image/jpeg", "a.jpg"), (b"x" * 600, "image/jpeg", "b.jpg")]
        with patch.object(capture_use_cases, "MAX_UPLOAD_BYTES", 1000):
            with self.assertRaises(InvalidCaptureException) as caught:
                _uploader(self.captures).execute(files, "arq-1")
        self.assertIn("no tiene límite de fotos", caught.exception.message)
        # Y no se guardó nada: la subida es entera o ninguna.
        self.assertEqual(self.captures.list_by_status("arq-1", CaptureStatus.INBOX), [])

    def test_one_file_is_still_measured_on_its_own(self):
        """Quitar el tope de cuántas no quita el de cuánto pesa una: un archivo de
        más de 15 MB sigue siendo un error con su nombre adelante."""
        with self.assertRaises(InvalidCaptureException) as caught:
            _uploader(self.captures).execute([(b"x" * (16 * 1024 * 1024), "image/jpeg", "gorda.jpg")], "arq-1")
        self.assertIn("gorda.jpg", caught.exception.message)


class UnPdfLargoEsUnaCarpetaEscaneadaTests(unittest.TestCase):
    """Un PDF se separa en una foto por página y ya no se corta a las veinte:
    cincuenta hojas escaneadas de una vez es una carpeta entera, que es justo lo
    que la bandeja tiene que poder recibir."""

    def test_a_pdf_longer_than_the_old_twenty_pages_comes_in_whole(self):
        created = _uploader(FakeCaptures()).execute(
            [(_pdf(pages=28), "application/pdf", "carpeta.pdf")], "arq-1"
        )
        self.assertEqual(len(created), 28)

    def test_the_pages_keep_their_reading_order(self):
        created = _uploader(FakeCaptures()).execute(
            [(_pdf(pages=25), "application/pdf", "carpeta.pdf")], "arq-1"
        )
        self.assertEqual(created[0].file_name, "carpeta · pág. 1")
        self.assertEqual(created[-1].file_name, "carpeta · pág. 25")

    def test_a_caller_that_asks_for_a_cap_still_gets_one(self):
        """El tope sigue existiendo para quien lo pida: lo que cambió es que la
        bandeja no lo pide."""
        with self.assertRaises(InvalidCaptureException):
            PdfiumRasterizer().pages(_pdf(pages=4), 2)


class LaPantallaSabeEnQueAndaLaLecturaTests(unittest.TestCase):
    """El cartel de etapa que el servidor publica mientras lee.

    Hace falta porque las dos últimas pasadas trabajan sobre el documento entero
    y no sobre una foto: cuando empiezan, todas las fotos ya figuran leídas y la
    pantalla no tendría de dónde saber que sigue avanzando. La del modelo de
    visión se lleva entre veinte y treinta segundos por foto, así que sin esto el
    cartel decía "Interpretando" y se quedaba quieto hasta un minuto.
    """

    def setUp(self):
        self.captures, self.documents = FakeCaptures(), FakeDocuments()
        self.folders = FakeRegisteredFolders(self.documents)
        self.photo = self.captures.create("arq-1", "p.png", "image/png", b"x", b"t")

    def _run(self, doc_type=DocumentType.FORM, data=None, vision=None, seals=None):
        document = CreateDocumentUseCase(self.documents, self.captures, self.folders).execute(
            doc_type, [self.photo.id], "arq-1", None, "possessors"
        )
        AnalyzeDocumentUseCase(self.documents, self.captures, FakeQueue()).execute(
            document.id, "arq-1"
        )
        RunServerReadingUseCase(
            self.documents,
            self.captures,
            {doc_type: FakeExtractor(data or {"full_text": "FORMULARIO", "pages": [], "reading": {"observations": []}})},
            folders=self.folders,
            seals=seals,
            vision=vision,
        ).execute(document.id, "arq-1")
        return self.documents.get(document.id, "arq-1")

    def test_the_vision_pass_announces_itself_before_looking(self):
        self._run(vision=FakeVision([{"notary_number": "37"}]))
        self.assertIn(ReadingStage.VISION, self.documents.stages)

    def test_the_stamp_pass_announces_itself_too(self):
        self._run(seals=FakeSeals(["NOTARIA DE FE PUBLICA No 48"]))
        self.assertIn(ReadingStage.SEALS, self.documents.stages)

    def test_the_stamps_are_announced_before_the_model(self):
        """El orden del cartel es el orden del trabajo: primero el sello, que es
        barato, y recién al final la foto."""
        self._run(
            seals=FakeSeals(["ILEGIBLE"]), vision=FakeVision([{"notary_number": "37"}])
        )
        stages = [stage for stage in self.documents.stages if stage]
        self.assertEqual(stages.index(ReadingStage.SEALS) < stages.index(ReadingStage.VISION), True)

    def test_a_document_with_nothing_to_ask_never_lights_the_model_up(self):
        """Un plano no le pregunta nada al modelo: aparecer en pantalla como si lo
        estuviera esperando sería mentir sobre lo que tarda."""
        self._run(
            doc_type=DocumentType.PLAN,
            data={"full_text": "PLANO", "pages": []},
            vision=FakeVision([{"notary_number": "37"}]),
        )
        self.assertNotIn(ReadingStage.VISION, self.documents.stages)

    def test_a_reading_that_ended_is_in_no_stage(self):
        """El cartel se apaga al guardar, que es por donde salen todas las
        lecturas: uno encendido en un documento ya leído mandaría a la pantalla a
        mostrar para siempre que el modelo está mirando."""
        document = self._run(vision=FakeVision([{"notary_number": "37"}]))
        self.assertEqual(document.status, DocumentStatus.EXTRACTED)
        self.assertIsNone(document.stage)

    def test_a_reading_that_failed_is_in_no_stage_either(self):
        document = CreateDocumentUseCase(self.documents, self.captures, self.folders).execute(
            DocumentType.FORM, [self.photo.id], "arq-1", None, "possessors"
        )
        AnalyzeDocumentUseCase(self.documents, self.captures, FakeQueue()).execute(
            document.id, "arq-1"
        )
        self.documents.set_stage(document.id, ReadingStage.VISION)
        RunServerReadingUseCase(
            self.documents,
            self.captures,
            {DocumentType.FORM: FakeExtractor(error=OcrUnavailableException("El OCR no responde."))},
            folders=self.folders,
        ).execute(document.id, "arq-1")
        failed = self.documents.get(document.id, "arq-1")
        self.assertEqual(failed.status, DocumentStatus.FAILED)
        self.assertIsNone(failed.stage)

    def test_a_cartel_that_could_not_be_written_does_not_stop_the_reading(self):
        """Es un cartel para una pantalla: perderlo no puede costar una lectura."""
        def explode(_document_id, _stage):
            raise RuntimeError("database hiccup")

        with patch.object(FakeDocuments, "set_stage", explode):
            document = self._run(vision=FakeVision([{"notary_number": "37"}]))
        self.assertEqual(document.status, DocumentStatus.EXTRACTED)
        self.assertEqual(document.extracted_data["values"]["notary_number"], "37")


# Un formulario notarial de verdad, como lo lee el OCR: el de la foto 21.jpg.
FORMULARIO_NOTARIAL = """FORMULARIO NOTARIAL
Resolución Ministerial N° 57/2020
Código de seguridad: RL123ZKxxo6t
VALOR Bs. 3.-
DECLARACIONES VOLUNTARIAS
NÚMERO: UN MIL CIENTO CINCUENTA Y UN/DOS MIL VEINTISEIS - 1151/2026-
En el municipio de Cochabamba del departamento de Cochabamba del Estado Plurinacional de
Bolivia, a horas 13:18 (trece y dieciocho), del día, lunes veintiun del mes de septiembre del año dos
mil veintiseis, ANTE MÍ ANGEL RODRIGUEZ SALAZAR, Notario de Fe Pública N° 15 del municipio
de Cochabamba del departamento de Cochabamba, se hizo presente NOELIA ALMENDRAS
RODRIGUEZ con Cédula de Identidad N° 8806991 (ocho, ocho, cero, seis, nueve, nueve, uno),
Boliviana, Soltera, con profesión y/o ocupación ESTUDIANTE, con domicilio en AV. PETROLERA
KM. 10 . B/ VILLA SAN SALVADOR - CBBA quien se apersona en su propio derecho, en su
condición de SOLICITANTE. A quien de identificarle en oficina y haciéndose responsable del
contenido y veracidad de su afirmación encontrándose en pleno goce, capacidad y ejercicio de sus
derechos civiles para este acto, dijo:-
Declaro: ser poseedora, del bien inmueble con código catastral N° 00-33-432-012-0-00-000-000-
Declaro: la veracidad de datos técnicos consignados en los formularios y otros registros
informatices, consignados en los sistemas del Gobierno Autónomo Municipal de Cochabamba.-
Con lo que termino la declaración, que le fue leida en su integridad, ratificándose en el tenor integro
de la presente declaración suscribe la declarante juntamente conmigo ANTE MI, ÁNGEL
RODRÍGUEZ SALAZAR, ABOGADO NOTARIO DE FE PUBLICA NUMERO QUINCE, DEL
MUNICIPIO DE COCHABAMBA- CERCADO.-de este distrito judicial, de todo lo que doy fe.-
CONCLUSION.-
Con lo que concluyo DOY FE.-
Firmado en documento original con código de contenido:
8abf1b7f5ae19a8182ffe69dadcab18e790cf393975da2829cf4f7da36aaa4f9.-
Nombre Firma Huella
NOELIA ALMENDRAS RODRIGUEZ
Cédula de Identidad 8806991
Abg. Angel Rodriguez Salazar
NOTARÍA DE FE PÚBLICA
DIRNOPLU N° 15
https://sinplu.dirnoplu.gob.bo/verificacion-documentos/b50031fc-RLi23ZKxxo6t
Este es un documento firmado digitalmente por la/el Notario de Fe Pública
"""


class FormularioNotarialEnteroTests(unittest.TestCase):
    """La hoja completa, leída de punta a punta.

    Es la prueba que importa: cada valor por separado se saca con un patrón, pero
    lo que rompe en producción es la hoja entera -- el número de la Resolución
    Ministerial al lado del sello, la fecha del nombramiento del notario dentro
    del sello, y el nombre del notario escrito antes y más grande que el del
    poseedor.
    """

    FIELDS = document_fields("possessors", DocumentType.FORM)

    def setUp(self):
        self.values, self.missing = harvest(
            {"full_text": FORMULARIO_NOTARIAL, "pages": []}, self.FIELDS
        )

    def test_the_notary_is_the_one_of_the_seal_and_not_the_resolution(self):
        self.assertEqual(self.values["notary_number"], "15")

    def test_the_owner_is_the_one_who_appeared_and_not_the_notary(self):
        self.assertEqual(self.values["owner_name"], "NOELIA ALMENDRAS RODRIGUEZ")

    def test_the_date_is_the_one_of_the_act_in_figures(self):
        self.assertEqual(self.values["statement_dates"], "21/09/2026")

    def test_nothing_is_left_for_the_architect_to_type(self):
        self.assertEqual(self.missing, [])


class FechaDeUnActaEnSusMuchasFormasTests(unittest.TestCase):
    """Cómo escriben la fecha estas hojas. No hay una redacción: cada notaría
    tiene la suya, y la misma notaría la cambia entre el formulario y la
    declaración jurada."""

    FIELDS = document_fields("possessors", DocumentType.FORM)

    FORMAS = [
        ("21/09/2026", "del dia, lunes veintiun del mes de septiembre del ano dos mil veintiseis, ANTE MI"),
        ("21/09/2026", "a los veintiun dias del mes de septiembre de dos mil veintiseis, ante mi"),
        ("21/09/2026", "del dia lunes 21 del mes de septiembre del ano 2026, ANTE MI"),
        ("21/09/2026", "del dia veintiuno de septiembre del ano dos mil veintiseis, ANTE MI"),
        ("21/09/2026", "a los 21 dias del mes de septiembre de 2026."),
        ("21/09/2026", "a los veintiun dias de septiembre de dos mil veintiseis"),
        ("21/09/2026", "del dia 21 de septiembre de 2026, ante mi"),
        ("31/01/2025", "el dia martes treinta y uno del mes de enero del ano dos mil veinticinco,"),
        ("01/01/2025", "el dia primero del mes de enero del ano dos mil veinticinco y en presencia de"),
        ("05/03/2024", "dia 5 de marzo de 2024"),
        ("12/03/2025", "declaracion jurada de fecha 12 de marzo de 2025"),
        ("26/08/2014", "26 de/Agosto del 2014"),
        # El día de semana solo, sin "del día" delante.
        ("21/09/2026", "Lunes veinte y uno del mes de septiembre del dos mil veintiseis"),
        ("21/09/2026", "Lunes veinte y uno del mes de septiembre del dos mil veintiseis, ANTE MI"),
        ("21/09/2026", "lunes 21 del mes de septiembre del 2026"),
        ("21/09/2026", "martes veinte y uno de septiembre de dos mil veintiseis"),
        # El día compuesto escrito separado, que es la mitad de las veces.
        ("21/09/2026", "del dia veinte y un del mes de septiembre del ano dos mil veintiseis"),
        ("28/02/2025", "a los veinte y ocho dias del mes de febrero de dos mil veinticinco"),
        # Y en cifras, rotulada o suelta.
        ("21/09/2026", "Fecha: 21/09/2026"),
        ("21/09/2026", "FECHA 21-09-2026"),
        ("21/09/2026", "Cochabamba, 21/09/2026"),
        ("21/09/2026", "En la ciudad de Cochabamba, 21.09.2026, ante mi"),
        # Suelta en letras, sin nada que la anuncie.
        ("21/09/2026", "En la ciudad de Cochabamba, veinte y uno de septiembre de dos mil veintiseis"),
    ]

    def test_every_wording_gives_the_same_date(self):
        for expected, text in self.FORMAS:
            with self.subTest(text):
                values, _ = harvest({"full_text": text, "pages": []}, self.FIELDS)
                self.assertEqual(values["statement_dates"], expected)

    def test_the_number_of_the_resolution_is_not_a_date(self):
        values, _ = harvest(
            {"full_text": "Resolucion Ministerial N 57/2020 codigo RL123ZKxxo6t", "pages": []},
            self.FIELDS,
        )
        self.assertIsNone(values["statement_dates"])

    def test_the_date_inside_the_seal_is_not_the_date_of_the_act(self):
        """La chica que va dentro del sello es la del nombramiento del notario, y
        viene pegada al número de la notaría. Que una fecha en cifras siga a otro
        número es lo que la delata: eso es una línea de registro, no una fecha."""
        values, _ = harvest(
            {"full_text": "NOTARIA DE FE PUBLICA N 15 22.04.2018 DIRNOPLU", "pages": []}, self.FIELDS
        )
        self.assertIsNone(values["statement_dates"])

    def test_a_number_of_the_sheet_is_not_a_date_in_figures(self):
        """La hoja está llena de números con barras y guiones. Lo que separa a una
        fecha es el año de cuatro cifras en el último lugar."""
        for text in [
            "codigo catastral N 00-33-432-012-0-00-000-000",
            "NUMERO: UN MIL CIENTO CINCUENTA Y UN/DOS MIL VEINTISEIS - 1151/2026-",
            "Resolucion Ministerial N 57/2020 codigo RL123ZKxxo6t",
        ]:
            with self.subTest(text):
                values, _ = harvest({"full_text": text, "pages": []}, self.FIELDS)
                self.assertIsNone(values["statement_dates"])

    def test_a_labelled_date_in_figures_is_not_cut_to_its_day(self):
        """El principio de una fecha se lee igual que el principio de una medida
        del plano, así que "FECHA: 21/09/2026" se guardaba como "21"."""
        values, _ = harvest(
            {
                "full_text": "DECLARACION JURADA",
                "pages": [{"fields": [{"name": "FECHA", "value": "21/09/2026"}]}],
            },
            self.FIELDS,
        )
        self.assertEqual(values["statement_dates"], "21/09/2026")

    def test_a_labelled_date_in_words_is_stored_in_figures(self):
        """Venga de donde venga, la oficina la guarda en dd/mm/aaaa."""
        values, _ = harvest(
            {
                "full_text": "DECLARACION JURADA",
                "pages": [{"fields": [{"name": "FECHA", "value": "12 de marzo de 2025"}]}],
            },
            self.FIELDS,
        )
        self.assertEqual(values["statement_dates"], "12/03/2025")

    def test_a_day_that_does_not_exist_is_not_a_date(self):
        """Un "31 de febrero" no es una fecha floja: es una lectura equivocada, y
        guardarla deja en la carpeta algo que nadie vuelve a mirar."""
        self.assertIsNone(to_iso_like("31", "FEBRERO", "2026"))
        self.assertIsNone(to_iso_like("29", "FEBRERO", "2025"))
        self.assertEqual(to_iso_like("29", "FEBRERO", "2024"), "29/02/2024")

    def test_a_photo_does_not_hand_over_a_clean_sentence(self):
        """La misma frase, leída de una foto en vez de un texto limpio.

        Es lo que de verdad llega: el OCR mete la raya del renglón entre las
        palabras, cambia la I por una L, y el notario escribe "ventiun" donde la
        ortografía dice "veintiún". Cada una de estas dejaba el campo vacío.
        """
        for expected, text in [
            ("21/09/2026", "del día, lunes veintiun del-mes de septiembre del año dos mil veintiseis"),
            ("21/09/2026", "del día, lunes veintiun del mes de. septiembre. del año dos mil veintiseis"),
            ("21/09/2026", "del día: lunes veintiun del mes de septiembre del año: dos mil veintiseis"),
            ("21/09/2026", "del día, lunes veintiun del mes de septlembre del año dos mil veintiseis"),
            ("21/09/2026", "del día, lunes velntiun del mes de septiembre del año dos mil veintiseis"),
            ("21/09/2026", "del día, lunes ventiun del mes de septiembre del año dos mil veintiseis"),
            ("21/09/2026", "del día, lunes veintiun del mes de septiembre del año dos mil veintlseis"),
            ("21/09/2026", "del día, lunes veintiun del mes de setiembre del año dos mil veintiseis"),
            ("16/09/2026", "del día, miércoles diez y seis del mes de septiembre del año dos mil veintiseis"),
            ("16/09/2026", "del día, miércoles diesiseis de septiembre de dos mil veintiseis"),
        ]:
            with self.subTest(text):
                values, _ = harvest({"full_text": text, "pages": []}, self.FIELDS)
                self.assertEqual(values["statement_dates"], expected)

    def test_a_word_that_is_not_a_number_does_not_become_one(self):
        """El parecido se exige alto a propósito: una fecha inventada no la
        vuelve a mirar nadie, y un campo vacío sí se avisa."""
        self.assertIsNone(leading_number("CUALQUIER COSA"))
        self.assertIsNone(leading_number("MUNICIPIO"))
        self.assertIsNone(leading_number("RODRIGUEZ"))
        values, _ = harvest(
            {"full_text": "a horas 13:18 (trece y dieciocho), ANTE MI", "pages": []}, self.FIELDS
        )
        self.assertIsNone(values["statement_dates"])

    def test_the_number_is_cut_where_it_stops_being_one(self):
        """Es lo que deja capturar con holgura: el patrón ya no tiene que adivinar
        dónde termina la fecha."""
        self.assertEqual(leading_number("DOS MIL VEINTISEIS ANTE MI ANGEL"), 2026)
        self.assertEqual(leading_number("VEINTIUN DEL MES DE"), 21)
        # El día compuesto se escribe junto y separado, y vale lo mismo.
        self.assertEqual(leading_number("VEINTIUNO"), leading_number("VEINTE Y UNO"))
        self.assertEqual(leading_number("VEINTE Y OCHO"), 28)
        self.assertEqual(leading_number("2026"), 2026)
        self.assertIsNone(leading_number("CUALQUIER COSA"))


class LaFechaQueContestaElModeloTests(unittest.TestCase):
    """La oficina guarda la fecha en dd/mm/aaaa y en ninguna otra forma. Al modelo
    de visión se le pide así, pero también la devuelve como la leyó de la hoja o
    con el año adelante, así que se la pasa por una sola puerta antes de
    guardarla."""

    FIELDS = document_fields("possessors", DocumentType.FORM)

    def test_every_shape_it_answers_is_stored_the_same_way(self):
        for raw in [
            "21/09/2026",
            "21-9-2026",
            "2026-09-21",
            "21 de septiembre de 2026",
            "veintiuno de septiembre de dos mil veintiseis",
            "Veintiún de septiembre del año dos mil veintiséis",
            "21/9/26",
        ]:
            with self.subTest(raw):
                self.assertEqual(any_date(raw), "21/09/2026")

    def test_what_cannot_be_read_as_a_date_is_not_stored(self):
        for raw in ["09/21/2026", "31/02/2026", "cualquier cosa", ""]:
            with self.subTest(raw):
                self.assertIsNone(any_date(raw))

    def test_the_answer_of_the_model_reaches_the_carpeta_in_figures(self):
        answer = from_vision({"statement_dates": "21 de septiembre de 2026"}, self.FIELDS)
        self.assertEqual(answer["statement_dates"], "21/09/2026")

    def test_a_date_the_model_wrote_in_a_shape_nobody_understands_is_dropped(self):
        self.assertEqual(from_vision({"statement_dates": "el lunes pasado"}, self.FIELDS), {})


class NombreDelPoseedorEnSusMuchasFormasTests(unittest.TestCase):
    """Cómo presentan al poseedor estas hojas, y qué NO es su nombre.

    Lo que sostiene la lectura es la lista de palabras que un acta pone alrededor
    de un nombre y no son parte de él (folder_types._NOT_NAME): sin ella entraban
    el verbo, el tratamiento, la nacionalidad y el estado civil.
    """

    FIELDS = document_fields("possessors", DocumentType.FORM)

    ANTE_MI = (
        "ANTE MI ANGEL RODRIGUEZ SALAZAR, Notario de Fe Publica N 15 del municipio "
        "de Cochabamba del departamento de Cochabamba, "
    )

    FORMAS = [
        ("NOELIA ALMENDRAS RODRIGUEZ",
         "se hizo presente NOELIA ALMENDRAS RODRIGUEZ con Cedula de Identidad N 8806991 (ocho, ocho)"),
        ("NOELIA ALMENDRAS RODRIGUEZ",
         "se hizo presente NOELIA ALMENDRAS RODRIGUEZ, boliviana, mayor de edad, con C.I. 8806991"),
        ("NOELIA ALMENDRAS RODRIGUEZ",
         "se hizo presente la senora NOELIA ALMENDRAS RODRIGUEZ con C.I. N 8806991"),
        ("JUAN PEREZ LOPEZ, MARIA ROJAS VARGAS",
         "se hicieron presentes JUAN PEREZ LOPEZ con C.I. 123456 y MARIA ROJAS VARGAS con C.I. 654321"),
        ("JUAN PEREZ LOPEZ", "comparecio JUAN PEREZ LOPEZ con Cedula de Identidad 123456"),
        ("JUAN PEREZ LOPEZ", "comparecen JUAN PEREZ LOPEZ con Cedula de Identidad 123456"),
        ("JUAN PEREZ LOPEZ", "se presento JUAN PEREZ LOPEZ con C.I. 123456"),
        ("MARIA DE LA CRUZ PEREZ", "se hizo presente MARIA DE LA CRUZ PEREZ con C.I. 999888"),
    ]

    def _harvest(self, text):
        return harvest({"full_text": self.ANTE_MI + text, "pages": []}, self.FIELDS)[0]

    def test_every_wording_gives_the_same_name(self):
        for expected, text in self.FORMAS:
            with self.subTest(text):
                self.assertEqual(self._harvest(text)["owner_name"], expected)

    def test_the_signature_table_answers_when_the_wording_could_not_be_read(self):
        """El nombre vuelve a estar impreso al pie, rotulado y con su cédula
        debajo: es la red cuando la foto salió ilegible en el párrafo."""
        values, _ = harvest(
            {
                "full_text": "Nombre Firma Huella NOELIA ALMENDRAS RODRIGUEZ Cedula de Identidad 8806991",
                "pages": [],
            },
            self.FIELDS,
        )
        self.assertEqual(values["owner_name"], "NOELIA ALMENDRAS RODRIGUEZ")

    def test_the_notary_is_never_the_owner(self):
        for text in [
            "de este distrito judicial, de todo lo que doy fe.",
            "ANTE MI, ANGEL RODRIGUEZ SALAZAR, ABOGADO NOTARIO DE FE PUBLICA NUMERO QUINCE",
        ]:
            with self.subTest(text):
                values, _ = harvest({"full_text": text, "pages": []}, self.FIELDS)
                self.assertIsNone(values["owner_name"])

    def test_a_word_that_only_looks_like_a_card_is_not_one(self):
        """La marca de la cédula es dos letras, así que sin pedir el número detrás
        cualquier palabra que empiece igual la imitaba."""
        values, _ = harvest(
            {"full_text": "se hizo presente con ciudadania boliviana y vecindad", "pages": []},
            self.FIELDS,
        )
        self.assertIsNone(values["owner_name"])


AVALUO = """GOBIERNO AUTONOMO MUNICIPAL DE COCHABAMBA
FORMULARIO PARA ACTUALIZACION DE DATOS TECNICOS
DECLARACION JURADA
33-432-012-0-00-000-000          0        8806991015
Código catastral              # Inmueble      PMC
1.- Información del propietario     2.- Información legal      Formulario No.: 493002
NOELIA ALMENDRAS RODRIGUEZ          Matricula: No registra     Fecha: 26/08/2026
CI:8806991 Cochabamba               Asiento: No registra       Código: I92314F493002
                                    Fecha DDRR: No registra
Croquis del predio    LOTE N° 5    CALLE DE 12.50 MTS.
Lote N° 4  Sup. Total Util 299.02 m2    25.01    23.91    13.24    21.67
3.- Descripción del predio    Frente de lote: 35.01    Zona homogénea: Zona 11
Ltd.: -17,394013, Lgt.: -66,156951   Superficie Lote: 294.66   Fondo del lote: 25.01
6.- Características de la(s) construcciones
1 2009 2009 A 93.00 M2 1 Marginal -
2 2020 2009 A 93.00 M2 1 Interes Social -
3 2024 2009 A 93.00 M2 1 Interes Social -
Página 1/2
"""


class CodigoCatastralDelAvaluoTests(unittest.TestCase):
    """El avalúo no identifica al predio por su matrícula --su casilla de
    información legal dice "No registra"-- sino por el código catastral, impreso
    grande en la cabecera y con el rótulo DEBAJO, como pie."""

    APPRAISAL = document_fields("possessors", DocumentType.APPRAISAL)
    PLAN = document_fields("possessors", DocumentType.PLAN)

    def _code(self, text, fields=None):
        values, _ = harvest({"full_text": text, "pages": []}, fields or self.APPRAISAL)
        return values["cadastral_code"]

    def test_it_is_read_as_the_sheet_prints_it(self):
        self.assertEqual(self._code(AVALUO), "33-432-012-0-00-000-000")

    def test_the_plano_keeps_printing_it_with_the_pair_in_front(self):
        code = self._code("Código Catastral: 00-33-432-012-0-00-000-000", self.PLAN)
        self.assertEqual(code, "00-33-432-012-0-00-000-000")

    def test_both_sheets_are_the_same_predio_for_the_gis(self):
        """Los dos primeros dígitos no son parte del código: lo dice
        cadastral_code.to_gis_code() desde antes que el avalúo se leyera."""
        self.assertEqual(
            to_gis_code(self._code(AVALUO)),
            to_gis_code(self._code("Código Catastral: 00-33-432-012-0-00-000-000", self.PLAN)),
        )

    def test_the_other_numbers_of_the_sheet_are_not_the_code(self):
        """La hoja está llena de números largos: el del formulario, el PMC, las
        coordenadas del predio y la cédula del propietario."""
        for text in [
            "Formulario No.: 493002 Código: I92314F493002",
            "Ltd.: -17,394013, Lgt.: -66,156951",
            "Fecha: 26/08/2026 CI:8806991 Cochabamba",
            "8806991015 PMC # Inmueble 0",
        ]:
            with self.subTest(text):
                self.assertIsNone(self._code(text))

    def test_the_appraisal_asks_for_nothing_else(self):
        """La superficie útil y el código: lo demás de esta hoja todavía no se le
        pide."""
        self.assertEqual(
            sorted(field.key for field in self.APPRAISAL), ["cadastral_code", "usable_area"]
        )


class SuperficieUtilDelAvaluoTests(unittest.TestCase):
    """El avalúo imprime DOS superficies y solo una es la que pide la carpeta:
    "Superficie Lote: 294.66" en su cuadro de descripción, que es el área del
    lote, y "Sup. Total Util 299.02 m2" escrita sobre el croquis, que es la
    útil."""

    FIELDS = document_fields("possessors", DocumentType.APPRAISAL)

    def _area(self, text):
        values, _ = harvest({"full_text": text, "pages": []}, self.FIELDS)
        return values["usable_area"]

    def test_the_useful_one_is_taken_and_not_the_lot(self):
        self.assertEqual(self._area(AVALUO), "299.02 M2")

    def test_the_lot_area_alone_is_not_the_useful_one(self):
        """Si la útil no se pudo leer, el campo queda vacío y se avisa: guardar el
        área del lote en su lugar sería guardar otro número sin decirlo."""
        self.assertIsNone(self._area("3.- Descripcion del predio Superficie Lote: 294.66 Ubicacion: Medio"))

    def test_the_table_of_constructions_is_not_a_surface(self):
        """Cada construcción repite sus metros, y el avalúo de esta hoja repite
        "93.00 M2" tres veces: la cifra más repetida de la hoja NO es su
        superficie útil."""
        self.assertIsNone(
            self._area(
                "6.- Caracteristicas 1 2009 2009 A 93.00 M2 1 Marginal "
                "2 2020 2009 A 93.00 M2 1 Interes Social 3 2024 2009 A 93.00 M2"
            )
        )

    def test_it_is_also_read_when_the_sheet_labels_it(self):
        self.assertEqual(self._area("SUPERFICIE TOTAL UTIL: 299.02 M2"), "299.02 M2")


class ElCompletadoDelPlanoEsDelPlanoTests(unittest.TestCase):
    """Buscar la cifra que la hoja repite y repartir los lados medidos sobre el
    dibujo son reglas del plano, y solo del plano. En otra hoja hacían daño: un
    avalúo repite los metros de cada construcción, y un formulario terminaba con
    un frente y un fondo que esa hoja no declara."""

    def setUp(self):
        self.captures, self.documents = FakeCaptures(), FakeDocuments()
        self.folders = FakeRegisteredFolders(self.documents)
        self.photo = self.captures.create("arq-1", "p.png", "image/png", b"x", b"t")

    def _read(self, doc_type, data):
        document = CreateDocumentUseCase(self.documents, self.captures, self.folders).execute(
            doc_type, [self.photo.id], "arq-1", None, "possessors"
        )
        AnalyzeDocumentUseCase(self.documents, self.captures, FakeQueue()).execute(
            document.id, "arq-1"
        )
        RunServerReadingUseCase(
            self.documents, self.captures, {doc_type: FakeExtractor(data)}, folders=self.folders
        ).execute(document.id, "arq-1")
        return self.documents.get(document.id, "arq-1").extracted_data["values"]

    # Lo que el lector deja en una página cuando midió el dibujo: es lo que
    # dispara el reparto de lados.
    DRAWING = {
        "full_text": "CROQUIS",
        "pages": [{"fields": [], "dimensions": [12.5, 25.0, 12.5, 25.0], "street": None}],
        "reading": {"observations": []},
    }

    def test_a_form_does_not_get_sides_it_never_declared(self):
        values = self._read(DocumentType.FORM, self.DRAWING)
        self.assertEqual(sorted(values), ["notary_number", "owner_name", "statement_dates"])

    def test_an_appraisal_does_not_get_them_either(self):
        values = self._read(DocumentType.APPRAISAL, self.DRAWING)
        self.assertEqual(sorted(values), ["cadastral_code", "usable_area"])

    def test_the_repeated_figure_is_not_the_surface_of_an_appraisal(self):
        """La cifra más repetida de un avalúo son los metros de sus
        construcciones."""
        values = self._read(
            DocumentType.APPRAISAL,
            {
                "full_text": "1 2009 A 93.00 M2 2 2020 A 93.00 M2 3 2024 A 93.00 M2",
                "pages": [],
                "reading": {"observations": []},
            },
        )
        self.assertIsNone(values["usable_area"])


if __name__ == "__main__":
    unittest.main()
