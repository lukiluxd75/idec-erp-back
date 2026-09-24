"""
Use cases + SqlFolioRepository on in-memory SQLite (schema `folios` mapped to
none), and the full pipeline with fake OCR / image adapters that replay the
OCR captured from a real folio (tests/fixtures, anonymized).
"""
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.connection import Base
from app.domains.folios.application.use_cases import (
    DeleteFolioUseCase,
    GetFolioFillLogUseCase,
    GetFolioUseCase,
    ListFoliosUseCase,
    ProcessFolioUseCase,
    RequestReprocessUseCase,
    ReviewFolioUseCase,
    UploadFolioUseCase,
)
from app.domains.folios.domain.entities.folio import FolioStatus
from app.domains.folios.domain.entities.ocr_block import OcrBlock
from app.domains.folios.domain.exceptions import (
    AsientoStructurerUnavailableException,
    FolioNotEditableException,
    FolioNotFoundException,
    InvalidFolioUploadException,
    OcrUnavailableException,
)
from app.domains.folios.domain.ports.asiento_structurer_port import AsientoStructurerPort
from app.domains.folios.domain.ports.ocr_port import OcrPort
from app.domains.folios.domain.ports.page_image_port import PageImagePort, RotatedImage
from app.domains.folios.infrastructure.models import FolioModel, FolioPageModel
from app.domains.folios.infrastructure.sql_folio_repository import STALE_AFTER, STALE_MESSAGE, SqlFolioRepository

FIXTURE = Path(__file__).parent / "fixtures" / "folio_2_paginas_ocr.json"
IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


def _new_repo() -> SqlFolioRepository:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"folios": None}},
    )
    Base.metadata.create_all(bind=engine, tables=[FolioModel.__table__, FolioPageModel.__table__])
    return SqlFolioRepository(db=sessionmaker(bind=engine)())


def _blocks(raw, dx=0, dy=0) -> List[OcrBlock]:
    return [OcrBlock(b["text"], b["confidence"], b["box"][0] - dx, b["box"][1] - dy, b["box"][2] - dx, b["box"][3] - dy)
            for b in raw]


class FakeImages(PageImagePort):
    """Pages are identified by their bytes (b'page-1', b'page-2'); crops carry
    the page + region in their bytes so FakeOcr knows what to answer."""

    def __init__(self, pages):
        self._pages = pages

    def _page(self, content: bytes):
        return self._pages[int(content.decode().split("-")[1].split(":")[0])]

    def normalize(self, content):
        w, h = self._page(content)["size"]
        return content, w, h

    def rotate(self, content, angle_ccw_deg):
        w, h = self._page(content)["size"]
        return RotatedImage(content, w, h, IDENTITY)

    def vertical_lines(self, content):
        return self._page(content)["vertical_lines"]

    def crop(self, content, rect):
        return content + f":{rect[0]},{rect[1]}".encode()


class FakeOcr(OcrPort):
    def __init__(self, pages, fail=False):
        self._pages = pages
        self.fail = fail
        self.calls = []

    def read(self, image_bytes, filename="pagina.jpg"):
        if self.fail:
            raise OcrUnavailableException("El servicio OCR no respondió a tiempo.")
        self.calls.append(filename)
        text = image_bytes.decode()
        page = self._pages[int(text.split("-")[1].split(":")[0])]
        if filename.endswith("_cabecera.jpg"):
            return _blocks(page["blocks_header"])
        if filename.endswith("_col_a.jpg"):
            # Fixture keeps column A in page frame; the real OCR answers in crop frame.
            x0, y0 = (int(v) for v in text.split(":")[1].split(","))
            return _blocks(page["blocks_titularidad"], x0, y0)
        return _blocks(page["blocks_page"])


class FakeStructurer(AsientoStructurerPort):
    def __init__(self, answer=None, configured=True, fail=False):
        self.answer, self.configured, self.fail, self.calls = answer or {}, configured, fail, 0

    def is_configured(self):
        return self.configured

    def structure(self, raw_text):
        self.calls += 1
        if self.fail:
            raise AsientoStructurerUnavailableException("No se pudo consultar a Ollama.")
        return self.answer


def _fixture_pages():
    return {p["page_number"]: p for p in json.loads(FIXTURE.read_text(encoding="utf-8"))}


class TestUploadAndAccess(unittest.TestCase):
    def setUp(self):
        self.repo = _new_repo()
        self.upload = UploadFolioUseCase(self.repo)

    def test_rejects_invalid_uploads(self):
        with self.assertRaises(InvalidFolioUploadException):
            self.upload.execute([], "user-a")
        with self.assertRaises(InvalidFolioUploadException):
            self.upload.execute([(b"", "image/jpeg")], "user-a")
        with self.assertRaises(InvalidFolioUploadException):
            self.upload.execute([(b"x", "application/pdf")], "user-a")
        with self.assertRaises(InvalidFolioUploadException):
            self.upload.execute([(b"x", "image/jpeg")] * 11, "user-a")

    def test_upload_creates_pending_folio_with_pages(self):
        folio = self.upload.execute([(b"a", "image/jpeg"), (b"b", "image/png")], "user-a")
        self.assertEqual(folio.status, FolioStatus.PENDING)
        self.assertEqual([p.page_index for p in folio.pages], [0, 1])
        self.assertEqual(self.repo.get_page_image(folio.id, 1, "user-a", upright=True), (b"b", "image/png"))

    def test_folios_are_private_per_user(self):
        folio = self.upload.execute([(b"a", "image/jpeg")], "user-a")
        self.assertEqual(len(ListFoliosUseCase(self.repo).execute("user-a")), 1)
        self.assertEqual(ListFoliosUseCase(self.repo).execute("user-b"), [])
        with self.assertRaises(FolioNotFoundException):
            GetFolioUseCase(self.repo).execute(folio.id, "user-b")
        self.assertIsNone(self.repo.get_page_image(folio.id, 0, "user-b", upright=False))

    def test_processing_cut_off_by_a_restart_turns_failed(self):
        folio = self.upload.execute([(b"a", "image/jpeg")], "user-a")
        self.repo.mark_processing(folio.id)
        row = self.repo._db.query(FolioModel).get(folio.id)
        row.updated_at = datetime.now(timezone.utc) - STALE_AFTER - timedelta(minutes=1)
        self.repo._db.commit()

        [listed] = ListFoliosUseCase(self.repo).execute("user-a")
        self.assertEqual(listed.status, FolioStatus.FAILED)
        self.assertEqual(listed.error_message, STALE_MESSAGE)
        # ...and it can be reprocessed from there.
        self.assertEqual(RequestReprocessUseCase(self.repo).execute(folio.id, "user-a").status, FolioStatus.PROCESSING)

    def test_recent_processing_is_left_alone(self):
        folio = self.upload.execute([(b"a", "image/jpeg")], "user-a")
        self.repo.mark_processing(folio.id)
        self.assertEqual(GetFolioUseCase(self.repo).execute(folio.id, "user-a").status, FolioStatus.PROCESSING)

    def test_soft_delete(self):
        folio = self.upload.execute([(b"a", "image/jpeg")], "user-a")
        DeleteFolioUseCase(self.repo).execute(folio.id, "user-a")
        self.assertEqual(ListFoliosUseCase(self.repo).execute("user-a"), [])
        with self.assertRaises(FolioNotFoundException):
            DeleteFolioUseCase(self.repo).execute(folio.id, "user-a")


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.pages = _fixture_pages()
        self.repo = _new_repo()
        self.ocr = FakeOcr(self.pages)

    def _run(self, page_bytes, structurer=None):
        folio = UploadFolioUseCase(self.repo).execute([(b, "image/jpeg") for b in page_bytes], "user-a")
        ProcessFolioUseCase(self.repo, self.ocr, FakeImages(self.pages), structurer, 0.85).execute(folio.id)
        return self.repo.get(folio.id, "user-a")

    def test_full_folio_scanned_out_of_order(self):
        folio = self._run([b"page-2", b"page-1"])
        self.assertEqual(folio.status, FolioStatus.READY, folio.extracted_data["observaciones"])
        self.assertEqual(folio.matricula, "3.01.1.01.0012345")
        data = folio.extracted_data
        self.assertEqual(data["linderos"]["oeste"], "CON LOS LOTES N° 1 Y 2")
        self.assertEqual(data["documento"], {"fecha_emision": "06/02/2025", "paginas_declaradas": 2, "paginas_recibidas": 2})
        asientos = data["titularidad_dominio"]["asientos"]
        self.assertEqual([a["numero"] for a in asientos], [0, 1])
        # Both '1/1' of the PROPORCIÓN column go to the owners on their rows.
        self.assertEqual(
            [(p["nombre"], p["rol"], p["proporcion"]) for a in asientos for p in a["personas"]],
            [("PEREZ LOPEZ MARIA", "vendedor", "1/1"), ("ROJAS VARGAS JUAN", "titular", "1/1")],
        )
        self.assertEqual(data["titularidad_dominio"]["titulares_actuales"][0]["ci"], "1234567")
        # Page detected numbers stored per uploaded page.
        self.assertEqual([p.detected_page_number for p in folio.pages], [2, 1])
        # 1 full-page read per page + header crop (page 1) + column A crop (both pages).
        self.assertEqual(len(self.ocr.calls), 5)

    def test_missing_page_is_flagged(self):
        folio = self._run([b"page-1"])
        self.assertEqual(folio.status, FolioStatus.NEEDS_REVIEW)
        self.assertIn("Faltan páginas: el folio tiene 2 y se escanearon 1.", folio.extracted_data["observaciones"])

    def test_only_back_page_has_no_header(self):
        folio = self._run([b"page-2"])
        self.assertEqual(folio.status, FolioStatus.NEEDS_REVIEW)
        self.assertIsNone(folio.matricula)
        self.assertTrue(any("cabecera" in o for o in folio.extracted_data["observaciones"]))

    def test_ocr_down_marks_failed_and_can_be_reprocessed(self):
        self.ocr.fail = True
        folio = self._run([b"page-1", b"page-2"])
        self.assertEqual(folio.status, FolioStatus.FAILED)
        self.assertEqual(folio.error_message, "El servicio OCR no respondió a tiempo.")

        self.ocr.fail = False
        RequestReprocessUseCase(self.repo).execute(folio.id, "user-a")
        ProcessFolioUseCase(self.repo, self.ocr, FakeImages(self.pages), None, 0.85).execute(folio.id)
        self.assertEqual(self.repo.get(folio.id, "user-a").status, FolioStatus.READY)

    def test_llm_not_called_when_rules_read_everything(self):
        structurer = FakeStructurer()
        self._run([b"page-1", b"page-2"], structurer)
        self.assertEqual(structurer.calls, 0)

    def test_fill_log_traces_every_value(self):
        folio = self._run([b"page-2", b"page-1"])
        log = GetFolioFillLogUseCase(self.repo).execute(folio.id, "user-a")
        self.assertEqual(log["orden_fotos"], [2, 1])
        self.assertEqual(log["cabecera"]["foto"], 2)
        fields = {f["campo"]: f for f in log["cabecera"]["campos"]}
        self.assertEqual(fields["matricula.numero"]["valor"], "3.01.1.01.0012345")
        self.assertTrue(fields["matricula.numero"]["texto_ocr"])
        self.assertEqual(fields["linderos.oeste"]["valor"], "CON LOS LOTES N° 1 Y 2")
        self.assertTrue(fields["linderos.oeste"]["texto_ocr"])
        self.assertTrue(log["cabecera"]["lineas_ocr"])
        classified = {(line["clasificacion"], line["asiento"]) for line in log["columna_a"]["lineas"]}
        self.assertIn(("inicio_asiento", 0), classified)
        self.assertIn(("persona:vendedor", 0), classified)
        self.assertIn(("persona:titular", 1), classified)
        self.assertEqual(log["ia"], [])

        with self.assertRaises(FolioNotFoundException):
            GetFolioFillLogUseCase(self.repo).execute(folio.id, "user-b")
        # Reprocessing starts a new log.
        RequestReprocessUseCase(self.repo).execute(folio.id, "user-a")
        self.assertEqual(GetFolioFillLogUseCase(self.repo).execute(folio.id, "user-a"), {})

    def test_diagnostics_and_upright_image_are_saved(self):
        folio = self._run([b"page-1"])
        diagnostics = self.repo.get_diagnostics(folio.id, "user-a")
        self.assertEqual(diagnostics[0]["page_number"], 1)
        self.assertTrue(diagnostics[0]["blocks_titularidad"])
        self.assertEqual(self.repo.get_page_image(folio.id, 0, "user-a", upright=True)[1], "image/jpeg")


class TestLlmGapFilling(unittest.TestCase):
    """Asiento whose rules found no people/act: the LLM may fill them, but only
    with values that appear in the asiento's own text."""

    def _process(self, structurer, log=None):
        uc = ProcessFolioUseCase(_new_repo(), FakeOcr({}), FakeImages({}), structurer, 0.85)
        asientos = [{
            "numero": 3, "personas": [], "acto": None, "documento": None, "autoridad": None,
            "texto": "Asiento Numero: 3\nA FAVOR DE ROJAS VARGAS JUAN c/CI 1234567 CBA por Donacion\nTestimonio 55/2001",
        }]
        observations = []
        uc._fill_gaps_with_llm(asientos, observations, log)
        return asientos[0], observations

    def test_log_keeps_proposal_and_what_was_discarded(self):
        log = []
        self._process(FakeStructurer({
            "personas": [{"nombre": "PERSONA INVENTADA"}],
            "acto": "Donacion",
            "autoridad": "Notario inventado",
        }), log)
        [entry] = log
        self.assertEqual(entry["asiento"], 3)
        self.assertEqual(entry["aceptado"], ["acto"])
        self.assertEqual(len(entry["descartado"]), 2)
        self.assertEqual(entry["propuesta"]["autoridad"], "Notario inventado")

    def test_accepts_values_present_in_text_and_drops_invented_ones(self):
        asiento, _ = self._process(FakeStructurer({
            "personas": [
                {"nombre": "ROJAS VARGAS JUAN", "ci": "1234567", "expedido": "CBA"},
                {"nombre": "PERSONA INVENTADA", "ci": "999"},
            ],
            "acto": "Donacion",
            "documento": "Testimonio 55/2001",
            "autoridad": "Notario inventado",
        }))
        self.assertEqual([p["nombre"] for p in asiento["personas"]], ["ROJAS VARGAS JUAN"])
        self.assertEqual(asiento["personas"][0]["ci"], "1234567")
        self.assertEqual(asiento["acto"], "Donacion")
        self.assertIsNone(asiento["autoridad"])
        self.assertEqual(asiento["completado_por_ia"], ["personas", "acto", "documento"])

    def test_llm_failure_is_only_an_observation(self):
        asiento, observations = self._process(FakeStructurer(fail=True))
        self.assertEqual(asiento["personas"], [])
        self.assertEqual(len(observations), 1)

    def test_not_configured_skips(self):
        structurer = FakeStructurer(configured=False)
        self._process(structurer)
        self.assertEqual(structurer.calls, 0)


class TestReview(unittest.TestCase):
    def setUp(self):
        self.repo = _new_repo()
        self.folio = UploadFolioUseCase(self.repo).execute([(b"a", "image/jpeg")], "user-a")

    def test_cannot_review_while_processing(self):
        with self.assertRaises(FolioNotEditableException):
            ReviewFolioUseCase(self.repo).execute(self.folio.id, "user-a", {"x": 1}, confirm=False)

    def test_reprocess_discards_unconfirmed_review(self):
        self.repo.save_extraction(self.folio.id, {"medidas": "NSC"}, FolioStatus.READY, None)
        ReviewFolioUseCase(self.repo).execute(self.folio.id, "user-a", {"medidas": "10 x 28"}, confirm=False)
        folio = RequestReprocessUseCase(self.repo).execute(self.folio.id, "user-a")
        self.assertEqual(folio.status, FolioStatus.PROCESSING)
        self.assertIsNone(folio.reviewed_data)

    def test_review_keeps_extracted_and_confirm_blocks_reprocess(self):
        extracted = {"matricula": {"numero": "1.01.1.01.0000001"}}
        self.repo.save_extraction(self.folio.id, extracted, FolioStatus.NEEDS_REVIEW, "1.01.1.01.0000001")
        corrected = {"matricula": {"numero": "1.01.1.01.0000002"}}

        folio = ReviewFolioUseCase(self.repo).execute(self.folio.id, "user-a", corrected, confirm=False)
        self.assertEqual(folio.status, FolioStatus.NEEDS_REVIEW)
        self.assertEqual((folio.extracted_data, folio.current_data), (extracted, corrected))
        self.assertEqual(folio.matricula, "1.01.1.01.0000002")

        folio = ReviewFolioUseCase(self.repo).execute(self.folio.id, "user-a", corrected, confirm=True)
        self.assertEqual((folio.status, folio.confirmed_by_sub), (FolioStatus.CONFIRMED, "user-a"))
        with self.assertRaises(FolioNotEditableException):
            RequestReprocessUseCase(self.repo).execute(self.folio.id, "user-a")


if __name__ == "__main__":
    unittest.main()
