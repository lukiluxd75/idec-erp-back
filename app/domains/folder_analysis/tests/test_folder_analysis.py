import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timezone

import cv2
import numpy as np

from app.domains.folder_analysis.application.document_synchronizer import DocumentSynchronizer
from app.domains.folder_analysis.application.use_cases import (
    AnalyzeDocumentUseCase,
    CreateDocumentUseCase,
    DeleteCaptureUseCase,
    DeleteDocumentUseCase,
    GetDocumentUseCase,
    ReviewDocumentUseCase,
    SetDocumentPagesUseCase,
    UploadCapturesUseCase,
)
from app.domains.folder_analysis.domain.entities import (
    Capture,
    CaptureStatus,
    DocumentPage,
    DocumentStatus,
    FolderDocument,
    PageStatus,
    QueuedJob,
)
from app.domains.folder_analysis.domain.exceptions import (
    CaptureNotAvailableException,
    DocumentBusyException,
    DocumentNotFoundException,
    InvalidCaptureException,
)
from app.domains.folder_analysis.domain.extraction_profiles import PROFILES
from app.domains.folder_analysis.domain.ports import (
    CaptureRepositoryPort,
    DocumentRepositoryPort,
    ExtractionQueuePort,
)
from app.domains.folder_analysis.domain.services.document_progress import document_status
from app.domains.folder_analysis.domain.services.result_merger import conform, merge_pages
from app.domains.folder_analysis.infrastructure.opencv_thumbnail import OpenCvThumbnail

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


class FakeDocuments(DocumentRepositoryPort):
    def __init__(self):
        self.rows = {}

    def create(self, user_sub, doc_type, capture_ids):
        doc = FolderDocument(str(uuid.uuid4()), user_sub, doc_type, DocumentStatus.DRAFT, NOW, NOW,
                             pages=[DocumentPage(c, i) for i, c in enumerate(capture_ids)])
        self.rows[doc.id] = doc
        return doc

    def get(self, document_id, user_sub):
        doc = self.rows.get(document_id)
        return doc if doc and doc.user_sub == user_sub else None

    def list(self, user_sub, doc_type=None):
        return [d for d in self.rows.values() if d.user_sub == user_sub and (not doc_type or d.doc_type == doc_type)]

    def replace_pages(self, document_id, capture_ids):
        doc = self.rows[document_id]
        self.rows[document_id] = replace(doc, status=DocumentStatus.DRAFT, extracted_data=None, reviewed_data=None,
                                         pages=[DocumentPage(c, i) for i, c in enumerate(capture_ids)])

    def delete(self, document_id):
        self.rows.pop(document_id, None)

    def mark_submitted(self, document_id, job_ids_by_page):
        doc = self.rows[document_id]
        pages = [replace(p, status=PageStatus.QUEUED, job_id=job_ids_by_page[p.page_index], result=None)
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


def _png() -> bytes:
    return cv2.imencode(".png", np.full((800, 600, 3), 255, np.uint8))[1].tobytes()


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
        self.photos = UploadCapturesUseCase(self.captures, OpenCvThumbnail()).execute(
            [(_png(), "image/png", "p1.png"), (_png(), "application/octet-stream", "p2.jpg")], "arq-1"
        )

    def _create(self, doc_type="folio", ids=None):
        return CreateDocumentUseCase(self.documents, self.captures).execute(
            doc_type, ids or [p.id for p in self.photos], "arq-1")

    def test_upload_rejects_non_images_and_normalizes_mime(self):
        with self.assertRaises(InvalidCaptureException):
            UploadCapturesUseCase(self.captures, OpenCvThumbnail()).execute([(b"nope", "image/jpeg", "x")], "arq-1")
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

    def test_full_cycle_analyze_sync_review(self):
        doc = self._create()
        doc = AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        self.assertEqual(doc.status, DocumentStatus.QUEUED)
        self.assertEqual(len(self.queue.submitted), 2)
        self.assertIn("Folio Real", self.queue.submitted[0]["instructions"])

        with self.assertRaises(DocumentBusyException):
            AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")

        get = GetDocumentUseCase(self.documents, DocumentSynchronizer(self.documents, self.queue))
        self.queue.jobs["job-1"] = QueuedJob("done", FOLIO_PAGE_1)
        self.queue.jobs["job-2"] = QueuedJob("processing")
        self.assertEqual(get.execute(doc.id, "arq-1").status, DocumentStatus.PROCESSING)

        self.queue.jobs["job-2"] = QueuedJob("done", FOLIO_PAGE_2)
        doc = get.execute(doc.id, "arq-1")
        self.assertEqual(doc.status, DocumentStatus.EXTRACTED)
        self.assertEqual(len(doc.extracted_data["ownership_entries"]), 3)

        corrected = {**doc.extracted_data, "registration_status": "VIGENTE (revisado)"}
        doc = ReviewDocumentUseCase(self.documents).execute(doc.id, "arq-1", corrected)
        self.assertEqual(doc.status, DocumentStatus.REVIEWED)
        self.assertEqual(doc.current_data["registration_status"], "VIGENTE (revisado)")
        self.assertEqual(doc.extracted_data["registration_status"], "VIGENTE")

        with self.assertRaises(DocumentBusyException):
            AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        doc = AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1", force=True)
        self.assertEqual(doc.status, DocumentStatus.QUEUED)
        self.assertIsNone(doc.reviewed_data)

    def test_plan_is_sent_without_instructions(self):
        doc = self._create("plan", [self.photos[0].id])
        AnalyzeDocumentUseCase(self.documents, self.captures, self.queue).execute(doc.id, "arq-1")
        self.assertIsNone(self.queue.submitted[0]["instructions"])

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


if __name__ == "__main__":
    unittest.main()
