import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from app.domains.digitization.application.use_cases import (
    GetJobUseCase,
    ProcessJobUseCase,
    RetryJobUseCase,
    SubmitDocumentUseCase,
)
from app.domains.digitization.domain.entities import DigitizationJob, JobStatus
from app.domains.digitization.domain.exceptions import (
    InvalidDocumentException,
    JobNotFoundException,
    JobNotRetryableException,
    WorkerOutputException,
    WorkerUnavailableException,
)
from app.domains.digitization.infrastructure.ollama_vision_worker import OllamaVisionWorker
from app.domains.digitization.infrastructure.opencv_image_preprocessor import OpenCvImagePreprocessor


def _job(attempts=1, status=JobStatus.PROCESSING, requested_by="user-1"):
    now = datetime.now(timezone.utc)
    return DigitizationJob(
        id="11111111-1111-1111-1111-111111111111",
        status=status,
        file_name="doc.jpg",
        mime_type="image/jpeg",
        requested_by=requested_by,
        attempts=attempts,
        created_at=now,
        updated_at=now,
    )


def _document_image(width=2400, height=3200, angle=0.0) -> bytes:
    image = np.full((height, width, 3), 255, np.uint8)
    for i in range(20):
        y = 300 + i * 120
        cv2.putText(image, "PREDIO 12-345 SUPERFICIE 250 M2", (200, y), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 0, 0), 5)
    if angle:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        image = cv2.warpAffine(image, matrix, (width, height), borderValue=(255, 255, 255))
    return cv2.imencode(".png", image)[1].tobytes()


class TestOpenCvImagePreprocessor(unittest.TestCase):
    def setUp(self):
        self.preprocessor = OpenCvImagePreprocessor(max_side=1600)

    def test_rejects_non_image_bytes(self):
        with self.assertRaises(InvalidDocumentException):
            self.preprocessor.prepare(b"not an image")

    def test_shrinks_to_max_side_and_returns_jpeg(self):
        prepared = self.preprocessor.prepare(_document_image())
        decoded = cv2.imdecode(np.frombuffer(prepared, np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(max(decoded.shape[:2]), 1600)
        self.assertEqual(prepared[:2], b"\xff\xd8")

    def test_straightens_slightly_skewed_scan(self):
        skewed = cv2.imdecode(np.frombuffer(_document_image(angle=5), np.uint8), cv2.IMREAD_COLOR)
        self.assertGreater(abs(OpenCvImagePreprocessor._skew_angle(skewed)), 3)

        prepared = self.preprocessor.prepare(_document_image(angle=5))
        straightened = cv2.imdecode(np.frombuffer(prepared, np.uint8), cv2.IMREAD_COLOR)
        self.assertLess(abs(OpenCvImagePreprocessor._skew_angle(straightened)), 1.5)


class TestSubmitDocumentUseCase(unittest.TestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.preprocessor = MagicMock()
        self.preprocessor.prepare.return_value = b"prepared"
        self.use_case = SubmitDocumentUseCase(self.repository, self.preprocessor, max_bytes=1024)

    def test_rejects_empty_file(self):
        with self.assertRaises(InvalidDocumentException):
            self.use_case.execute("a.jpg", "image/jpeg", b"", "user-1")

    def test_rejects_oversized_file(self):
        with self.assertRaises(InvalidDocumentException):
            self.use_case.execute("a.jpg", "image/jpeg", b"x" * 2048, "user-1")

    def test_rejects_pdf(self):
        with self.assertRaises(InvalidDocumentException):
            self.use_case.execute("a.pdf", "application/pdf", b"%PDF-1.7 ...", "user-1")
        self.repository.create.assert_not_called()

    def test_enqueues_original_and_prepared_image(self):
        self.use_case.execute("a.jpg", "image/jpeg", b"raw", "user-1")
        kwargs = self.repository.create.call_args.kwargs
        self.assertEqual(kwargs["image"], b"raw")
        self.assertEqual(kwargs["prepared_image"], b"prepared")
        self.assertEqual(kwargs["requested_by"], "user-1")


class TestProcessJobUseCase(unittest.TestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.repository.get_prepared_image.return_value = b"img"
        self.worker = MagicMock()
        self.use_case = ProcessJobUseCase(self.repository, self.worker, max_attempts=3)

    def test_marks_done_with_result(self):
        self.worker.extract.return_value = {"full_text": "x"}
        self.use_case.execute(_job(), "http://pc1:11434")
        self.repository.mark_done.assert_called_once_with(_job().id, {"full_text": "x"})

    def test_unavailable_pc_releases_job_and_reraises(self):
        self.worker.extract.side_effect = WorkerUnavailableException("timeout")
        with self.assertRaises(WorkerUnavailableException):
            self.use_case.execute(_job(attempts=1), "http://pc1:11434")
        self.repository.release.assert_called_once()
        self.repository.mark_failed.assert_not_called()

    def test_bad_output_releases_job_without_raising(self):
        self.worker.extract.side_effect = WorkerOutputException("bad json")
        self.use_case.execute(_job(attempts=2), "http://pc1:11434")
        self.repository.release.assert_called_once()

    def test_fails_job_after_last_attempt(self):
        self.worker.extract.side_effect = WorkerOutputException("bad json")
        self.use_case.execute(_job(attempts=3), "http://pc1:11434")
        self.repository.mark_failed.assert_called_once()
        self.repository.release.assert_not_called()


class TestOwnership(unittest.TestCase):
    def test_other_users_job_is_not_found(self):
        repository = MagicMock()
        repository.get.return_value = _job(requested_by="someone-else")
        with self.assertRaises(JobNotFoundException):
            GetJobUseCase(repository).execute(_job().id, "user-1")

    def test_only_failed_jobs_can_be_retried(self):
        repository = MagicMock()
        repository.get.return_value = _job(status=JobStatus.DONE)
        with self.assertRaises(JobNotRetryableException):
            RetryJobUseCase(repository).execute(_job().id, "user-1")


class TestOllamaVisionWorker(unittest.TestCase):
    def setUp(self):
        self.worker = OllamaVisionWorker("qwen3-vl:4b", "2m", 1, 1, 1)

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_extract_normalizes_model_json(self, post):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "message": {"content": '{"document_type": " Plano ", "full_text": "abc", '
                                   '"fields": [{"name": "Predio", "value": 12}, {"name": ""}], '
                                   '"tables": [[["a", 1]]]}'}
        }
        post.return_value = response
        result = self.worker.extract("http://pc1:11434", b"img")
        self.assertEqual(result["document_type"], "Plano")
        self.assertEqual(result["fields"], [{"name": "Predio", "value": "12"}])
        self.assertEqual(result["tables"], [[["a", "1"]]])

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_extract_non_json_is_output_error(self, post):
        response = MagicMock(status_code=200)
        response.json.return_value = {"message": {"content": "no soy json"}}
        post.return_value = response
        with self.assertRaises(WorkerOutputException):
            self.worker.extract("http://pc1:11434", b"img")

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_extract_http_error_means_unavailable(self, post):
        post.return_value = MagicMock(status_code=500, text="out of memory")
        with self.assertRaises(WorkerUnavailableException):
            self.worker.extract("http://pc1:11434", b"img")

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.get")
    def test_check_reports_missing_model(self, get):
        get.return_value.json.return_value = {"models": [{"name": "gemma4:e4b"}]}
        status = self.worker.check("http://pc1:11434")
        self.assertTrue(status.reachable)
        self.assertFalse(status.available)


class TestJobDispatcherRound(unittest.TestCase):
    def _dispatcher(self, repository, worker, hosts):
        from app.domains.digitization.infrastructure.dispatcher import JobDispatcher

        session = MagicMock()
        session.__enter__.return_value = session
        return JobDispatcher(
            engine=MagicMock(), session_factory=lambda: session, repository_factory=lambda _db: repository,
            worker=worker, hosts=hosts, max_attempts=3, poll_interval=1, host_cooldown=60,
        )

    @patch("app.domains.digitization.infrastructure.dispatcher.threading.Thread")
    def test_sends_one_job_per_available_pc_and_rests_the_others(self, thread):
        from app.domains.digitization.domain.entities import WorkerStatus

        repository = MagicMock()
        repository.has_pending.return_value = True
        repository.claim_next.side_effect = lambda host: _job()
        worker = MagicMock()
        worker.check.side_effect = lambda host: WorkerStatus(host, host != "pc2", host != "pc2")
        dispatcher = self._dispatcher(repository, worker, ["pc1", "pc2", "pc3"])

        dispatcher._dispatch_round()
        self.assertEqual([c.args[0] for c in repository.claim_next.call_args_list], ["pc1", "pc3"])
        self.assertEqual(thread.call_count, 2)

        # Busy PCs and the resting one are skipped on the next round.
        dispatcher._dispatch_round()
        self.assertEqual(repository.claim_next.call_count, 2)

    def test_skips_health_checks_when_queue_is_empty(self):
        repository = MagicMock()
        repository.has_pending.return_value = False
        worker = MagicMock()
        self._dispatcher(repository, worker, ["pc1"])._dispatch_round()
        worker.check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
