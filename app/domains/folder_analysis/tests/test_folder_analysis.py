import unittest
import uuid
from unittest.mock import patch
from dataclasses import replace
from datetime import datetime, timezone

import cv2
import numpy as np

from app.domains.folder_analysis.application.document_synchronizer import DocumentSynchronizer
from app.domains.folder_analysis.application.use_cases import (
    AddDocumentsToRegisteredFolderUseCase,
    ClearInboxUseCase,
    AnalyzeDocumentUseCase,
    CreateDocumentUseCase,
    CreateRegisteredFolderUseCase,
    DeleteCaptureUseCase,
    DeleteDocumentUseCase,
    DeleteRegisteredFolderUseCase,
    GetDocumentUseCase,
    ListRegisteredFoldersUseCase,
    RegisteredFolderService,
    RemoveDocumentFromRegisteredFolderUseCase,
    ReviewDocumentUseCase,
    RunServerReadingUseCase,
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
    RegisteredFolder,
)
from app.domains.folder_analysis.domain.exceptions import (
    CaptureNotAvailableException,
    DocumentAlreadyFiledException,
    DocumentBusyException,
    DocumentNotFoundException,
    InvalidCaptureException,
    InvalidDocumentRequestException,
    InvalidRegisteredFolderException,
    RegisteredFolderNameTakenException,
    RegisteredFolderNotFoundException,
    TaxStructurerUnavailableException,
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
from app.domains.folder_analysis.domain.services.field_harvest import harvest, observation
from app.domains.folder_analysis.domain.services.spanish_dates import to_iso_like, words_to_number
from app.domains.folder_analysis.domain.ports import (
    CaptureRepositoryPort,
    DocumentRepositoryPort,
    ExtractionQueuePort,
    RegisteredFolderRepositoryPort,
    ServerReadingPort,
    TaxStructurerPort,
)
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

    def create(self, user_sub, doc_type, capture_ids, folder_type=None):
        doc = FolderDocument(str(uuid.uuid4()), user_sub, doc_type, DocumentStatus.DRAFT, NOW, NOW,
                             pages=[DocumentPage(c, i) for i, c in enumerate(capture_ids)],
                             folder_type=folder_type)
        self.rows[doc.id] = doc
        return doc

    def get(self, document_id, user_sub):
        doc = self.rows.get(document_id)
        return doc if doc and doc.user_sub == user_sub else None

    def list(self, user_sub, doc_type=None, folder_id=None):
        return [
            d
            for d in self.rows.values()
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
        self.rows[document_id] = replace(doc, pages=pages, status=status, error=error,
                                         extracted_data=extracted_data or doc.extracted_data)

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
        # Runs right after the use case is told a page is finished, so a test can
        # look at the document mid-reading.
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


def _png() -> bytes:
    return cv2.imencode(".png", np.full((800, 600, 3), 255, np.uint8))[1].tobytes()


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


# A FUR as the OCR reads it: values next to their label, and one row of stacked
# boxes (Nº INMUEBLE / COD. CAT. / CLASE / TIPO PROPIEDAD over their values).
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
        # The number is printed on the title's line: it goes to its own field and
        # is taken out of the type.
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
        # The label ends in a sign that is not a letter or a digit: it must not be
        # left at the front of the value.
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

    def list(self, user_sub):
        rows = [r for fid, r in self.rows.items() if self._owners.get(fid) == user_sub]
        return [self._entity(r) for r in sorted(rows, key=lambda r: r["name"].lower())]

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

    def test_removing_leaves_the_document_saved_and_free_to_file_again(self):
        folio = self._reviewed()
        folder = self._create("Proyecto Sur", ids=[folio.id])
        emptied = RemoveDocumentFromRegisteredFolderUseCase(self.folders, self.service).execute(
            folder.id, "arq-1", folio.id
        )
        self.assertEqual(emptied.document_ids, [])
        self.assertEqual(self.documents.get(folio.id, "arq-1").status, DocumentStatus.REVIEWED)
        self.assertEqual(self._create("Proyecto Norte", ids=[folio.id]).document_ids, [folio.id])

    def test_removing_something_that_is_not_in_the_carpeta(self):
        folder = self._create("Proyecto Sur")
        with self.assertRaises(DocumentNotFoundException):
            RemoveDocumentFromRegisteredFolderUseCase(self.folders, self.service).execute(
                folder.id, "arq-1", self._reviewed().id
            )

    def test_deleting_the_carpeta_keeps_its_documents(self):
        folio = self._reviewed()
        folder = self._create("Proyecto Sur", ids=[folio.id])
        DeleteRegisteredFolderUseCase(self.folders, self.service).execute(folder.id, "arq-1")
        self.assertEqual(ListRegisteredFoldersUseCase(self.folders).execute("arq-1"), [])
        self.assertEqual(self.documents.get(folio.id, "arq-1").status, DocumentStatus.REVIEWED)

    def test_another_user_cannot_delete_the_carpeta(self):
        folder = self._create("Proyecto Sur")
        with self.assertRaises(RegisteredFolderNotFoundException):
            DeleteRegisteredFolderUseCase(self.folders, self.service).execute(folder.id, "arq-2")

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
        of them would never be shown again, and a fixed field is not the user's
        to write."""
        folder = self._create(
            "Poseedores Sarco",
            kind="possessors",
            data={"inventado": "x", "legal_status": "Municipal"},
        )
        self.assertNotIn("inventado", folder.data)
        self.assertEqual(folder.data["legal_status"], "Particular")

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
        document = self._create(DocumentType.SWORN_STATEMENT, folder.id)
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
    STATEMENT = document_fields("possessors", DocumentType.SWORN_STATEMENT)

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
            "SUPERFICIE UTIL 240.00 M2"
        )
        values, missing = harvest(reading, self.PLAN)
        self.assertEqual(values["frontage"], "12.50 M")
        self.assertEqual(values["rear_frontage"], "12.50 M")
        self.assertEqual(values["depth"], "25.00 M")
        self.assertEqual(values["depth_2"], "24.80 M")
        self.assertEqual(values["usable_area"], "240.00 M2")
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

    FIELDS = document_fields("possessors", DocumentType.SWORN_STATEMENT)

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

    def _read(self, document, data):
        RunServerReadingUseCase(
            self.documents,
            self.captures,
            {document.doc_type: FakeExtractor(data)},
            folders=self.folders,
        ).execute(document.id, "arq-1")
        return self.documents.get(document.id, "arq-1")

    def _document(self, folder=None, doc_type=DocumentType.SWORN_STATEMENT):
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
            {"notary_number": "23", "owner_name": "MARIA LOPEZ", "statement_dates": "12 de marzo de 2025"},
        )
        # La lectura entera se conserva: los valores se suman, no la reemplazan.
        self.assertEqual(document.extracted_data["full_text"], "DECLARACION JURADA")

    def test_they_fill_the_empty_fields_of_the_carpeta(self):
        folder = self._folder()
        self._read(self._document(folder), self._statement())
        sheet = self.folders.get(folder.id, "arq-1").data
        self.assertEqual(sheet["notary_number"], "23")
        self.assertEqual(sheet["owner_name"], "MARIA LOPEZ")

    def test_what_the_architect_typed_is_never_overwritten(self):
        folder = self._folder({"owner_name": "Como lo escribí yo"})
        self._read(self._document(folder), self._statement())
        self.assertEqual(
            self.folders.get(folder.id, "arq-1").data["owner_name"], "Como lo escribí yo"
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

    def test_what_was_not_found_is_written_in_the_observations(self):
        """El arquitecto tiene que ver qué quedó vacío, no descubrirlo después."""
        document = self._read(
            self._document(),
            {"full_text": "HOJA VACIA", "pages": [], "reading": {"observations": []}},
        )
        notes = document.extracted_data["reading"]["observations"]
        self.assertTrue(any("No se encontraron" in note for note in notes), notes)


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

    def test_poseedores_carries_its_five_documents_and_its_sheet(self):
        poseedores = folder_type("possessors")
        self.assertEqual(
            poseedores.document_types,
            (
                DocumentType.APPRAISAL,
                DocumentType.PLAN,
                DocumentType.FORM,
                DocumentType.SWORN_STATEMENT,
                DocumentType.ID_CARD,
            ),
        )
        self.assertEqual(
            [field.key for field in poseedores.fields],
            [
                "street", "boundaries", "frontage", "rear_frontage", "depth", "depth_2", "usable_area",
                "notary_number", "property_number", "owner_name", "statement_dates", "legal_status",
            ],
        )

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


if __name__ == "__main__":
    unittest.main()
