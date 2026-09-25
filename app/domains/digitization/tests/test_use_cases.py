import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from app.domains.digitization.application.use_cases import (
    BorrowHostUseCase,
    CheckWorkersUseCase,
    GetJobUseCase,
    PickWorkerHostsUseCase,
    ProcessJobUseCase,
    RetryJobUseCase,
    StopWorkerUseCase,
    SubmitDocumentUseCase,
)
from app.domains.digitization.domain.entities import DigitizationJob, JobStatus
from app.domains.digitization.domain.exceptions import (
    InvalidDocumentException,
    JobNotFoundException,
    JobNotRetryableException,
    JobStoppedException,
    NoJobRunningException,
    WorkerNotFoundException,
    WorkerOutputException,
    WorkerTimeoutException,
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


def _stream(*events, status_code=200, text=""):
    """A mocked Ollama answer: one line of NDJSON per event, as it streams."""
    response = MagicMock(status_code=status_code, text=text)
    response.__enter__.return_value = response
    response.iter_lines.return_value = iter([json.dumps(event) for event in events])
    return response


def _answer(content, done_reason="stop"):
    """The content arriving in two fragments, then the closing line."""
    half = len(content) // 2
    return [
        {"message": {"content": content[:half]}},
        {"message": {"content": content[half:]}},
        {"message": {"content": ""}, "done": True, "done_reason": done_reason},
    ]


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

    def test_passes_the_job_instructions_to_the_pc(self):
        job = _job()
        job.instructions, job.output_template = "Read the FUR.", {"receipt_number": None}
        self.worker.extract.return_value = {"receipt_number": "1"}
        self.use_case.execute(job, "http://pc1:11434")
        self.worker.extract.assert_called_once_with(
            "http://pc1:11434", b"img", "Read the FUR.", {"receipt_number": None}, None
        )

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

    def test_stopped_job_ends_stopped_and_is_not_queued_again(self):
        self.worker.extract.side_effect = JobStoppedException()
        self.use_case.execute(_job(attempts=1), "http://pc1:11434")
        self.repository.mark_stopped.assert_called_once()
        self.repository.release.assert_not_called()
        self.repository.mark_failed.assert_not_called()

    def test_timeout_fails_the_job_instead_of_spending_another_attempt(self):
        self.worker.extract.side_effect = WorkerTimeoutException("el equipo no terminó en 300 segundos")
        self.use_case.execute(_job(attempts=1), "http://pc1:11434")
        self.repository.mark_failed.assert_called_once()
        self.repository.release.assert_not_called()

    def test_the_stop_watcher_reaches_the_pc(self):
        watcher = MagicMock(return_value=False)
        self.worker.extract.return_value = {"full_text": "x"}
        self.use_case.execute(_job(), "http://pc1:11434", should_stop=watcher)
        self.assertIs(self.worker.extract.call_args.args[4], watcher)


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

    def test_a_stopped_job_can_be_sent_again_by_hand(self):
        repository = MagicMock()
        repository.get.return_value = _job(status=JobStatus.STOPPED)
        repository.requeue_failed.return_value = _job(status=JobStatus.PENDING)
        self.assertEqual(RetryJobUseCase(repository).execute(_job().id, "user-1").status, JobStatus.PENDING)


class TestOllamaVisionWorker(unittest.TestCase):
    def setUp(self):
        self.worker = OllamaVisionWorker("qwen3-vl:4b", "2m", 1, 1, 1)

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_extract_normalizes_model_json(self, post):
        post.return_value = _stream(*_answer(
            '{"document_type": " Plano ", "full_text": "abc", '
            '"fields": [{"name": "Predio", "value": 12}, {"name": ""}], '
            '"tables": [[["a", 1]]]}'
        ))
        result = self.worker.extract("http://pc1:11434", b"img")
        self.assertEqual(result["document_type"], "Plano")
        self.assertEqual(result["fields"], [{"name": "Predio", "value": "12"}])
        self.assertEqual(result["tables"], [[["a", "1"]]])

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_extract_non_json_is_output_error(self, post):
        post.return_value = _stream(*_answer("no soy json"))
        with self.assertRaises(WorkerOutputException):
            self.worker.extract("http://pc1:11434", b"img")

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_extract_http_error_means_unavailable(self, post):
        post.return_value = _stream(status_code=500, text="out of memory")
        with self.assertRaises(WorkerUnavailableException):
            self.worker.extract("http://pc1:11434", b"img")

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_extract_ignores_reasoning_and_code_fences(self, post):
        post.return_value = _stream(*_answer(
            '<think>{"x": 1}</think>\n```json\n{"full_text": "ok"}\n```'
        ))
        self.assertEqual(self.worker.extract("http://pc1:11434", b"img")["full_text"], "ok")

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_extract_empty_answer_after_reasoning_is_output_error(self, post):
        post.return_value = _stream(
            {"message": {"content": "", "thinking": "..."}, "done": True, "done_reason": "length"}
        )
        with self.assertRaises(WorkerOutputException):
            self.worker.extract("http://pc1:11434", b"img")

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_repeat_loop_is_output_error_not_unavailable(self, post):
        post.return_value = _stream(
            status_code=500, text='{"error":"prediction aborted, token repeat limit reached"}'
        )
        with self.assertRaises(WorkerOutputException):
            self.worker.extract("http://pc1:11434", b"img")

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_repeat_loop_reported_mid_answer_is_output_error(self, post):
        post.return_value = _stream(
            {"message": {"content": "{"}}, {"error": "token repeat limit reached"}
        )
        with self.assertRaises(WorkerOutputException):
            self.worker.extract("http://pc1:11434", b"img")

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_custom_instructions_return_the_model_object_and_put_template_in_prompt(self, post):
        post.return_value = _stream(*_answer('{"receipt_number": "59122836", "cashier": null}'))
        result = self.worker.extract(
            "http://pc1:11434", b"img", "Read the FUR.", {"receipt_number": None, "cashier": None}
        )
        self.assertEqual(result, {"receipt_number": "59122836", "cashier": None})
        payload = post.call_args.kwargs["json"]
        self.assertNotIn("format", payload)
        self.assertIn("receipt_number", payload["messages"][1]["content"])
        self.assertIn("num_ctx", payload["options"])

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_stop_asked_mid_answer_drops_the_run_and_hangs_up(self, post):
        response = _stream(*_answer('{"full_text": "abc"}'))
        post.return_value = response
        with self.assertRaises(JobStoppedException):
            self.worker.extract("http://pc1:11434", b"img", should_stop=lambda: True)
        # Leaving the block closes the socket: that is what stops the PC.
        response.__exit__.assert_called_once()

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.post")
    def test_answer_longer_than_the_timeout_is_cut(self, post):
        worker = OllamaVisionWorker("qwen3-vl:4b", "2m", connect_timeout=1, request_timeout=0, health_timeout=1)
        post.return_value = _stream(*_answer('{"full_text": "abc"}'))
        with self.assertRaises(WorkerTimeoutException):
            worker.extract("http://pc1:11434", b"img")

    @patch("app.domains.digitization.infrastructure.ollama_vision_worker.requests.get")
    def test_check_reports_missing_model(self, get):
        get.return_value.json.return_value = {"models": [{"name": "gemma4:e4b"}]}
        status = self.worker.check("http://pc1:11434")
        self.assertTrue(status.reachable)
        self.assertFalse(status.available)


class TestStopWorkerUseCase(unittest.TestCase):
    """The monitor's "Detener" button: it only raises a flag, because the run
    itself lives in whichever process is dispatching the queue."""

    def _use_case(self, running=None, borrowed=None, flagged=1):
        repository = MagicMock()
        repository.find_processing_on.return_value = running
        usage = MagicMock()
        usage.active.return_value = borrowed or {}
        usage.request_stop.return_value = flagged
        use_case = StopWorkerUseCase(repository, usage, ["http://pc1:11434", "http://pc2:11434"])
        return use_case, repository, usage

    def test_flags_the_job_that_pc_is_running(self):
        use_case, repository, _usage = self._use_case(running=_job())
        stopped = use_case.execute("http://pc1:11434")
        self.assertEqual((stopped.used_by, stopped.job_id), ("digitization", _job().id))
        repository.request_stop.assert_called_once_with(_job().id)

    def test_stops_a_pc_another_module_borrowed(self):
        """The usual case on the monitor: folios or the chatbot took the PC, so
        there is no job of ours to flag, but the call can still be dropped."""
        use_case, repository, usage = self._use_case(running=None, borrowed={"http://pc2:11434": "folios"})
        stopped = use_case.execute("http://pc2:11434")
        self.assertEqual((stopped.used_by, stopped.job_id), ("folios", None))
        usage.request_stop.assert_called_once_with("http://pc2:11434")
        repository.request_stop.assert_not_called()

    def test_trailing_slash_is_still_the_same_pc(self):
        use_case, repository, _usage = self._use_case(running=_job())
        use_case.execute("http://pc1:11434/")
        repository.find_processing_on.assert_called_once_with("http://pc1:11434")

    def test_unknown_pc_is_rejected(self):
        use_case, repository, usage = self._use_case(running=_job())
        with self.assertRaises(WorkerNotFoundException):
            use_case.execute("http://otra-pc:11434")
        repository.request_stop.assert_not_called()
        usage.request_stop.assert_not_called()

    def test_nothing_to_stop_on_an_idle_pc(self):
        use_case, repository, usage = self._use_case(running=None)
        with self.assertRaises(NoJobRunningException):
            use_case.execute("http://pc2:11434")
        repository.request_stop.assert_not_called()
        usage.request_stop.assert_not_called()

    def test_a_usage_that_expired_between_the_two_reads_is_nothing_to_stop(self):
        use_case, _repository, _usage = self._use_case(
            running=None, borrowed={"http://pc2:11434": "folios"}, flagged=0
        )
        with self.assertRaises(NoJobRunningException):
            use_case.execute("http://pc2:11434")


class TestCheckWorkersUseCase(unittest.TestCase):
    """The monitor must show a PC as working whoever started the work: a
    digitization job, or another domain borrowing it (folios, chatbot)."""

    def _statuses(self, processing, borrowed):
        from app.domains.digitization.domain.entities import WorkerStatus

        repository = MagicMock()
        repository.list_processing.return_value = processing
        worker = MagicMock()
        worker.check.side_effect = lambda host: WorkerStatus(host, True, True)
        usage = MagicMock()
        usage.active.return_value = borrowed
        use_case = CheckWorkersUseCase(repository, worker, ["pc1", "pc2"], usage)
        return {s.host: s for s in use_case.execute()}

    def test_digitization_job_shows_the_job_id(self):
        job = _job()
        job.worker_host = "pc1"
        statuses = self._statuses([job], {})
        self.assertEqual((statuses["pc1"].used_by, statuses["pc1"].current_job_id), ("digitization", job.id))
        self.assertFalse(statuses["pc2"].busy)

    def test_pc_borrowed_by_another_domain_is_busy_without_a_job(self):
        statuses = self._statuses([], {"pc2": "chatbot"})
        self.assertEqual(statuses["pc2"].used_by, "chatbot")
        self.assertIsNone(statuses["pc2"].current_job_id)
        self.assertFalse(statuses["pc1"].busy)


class TestBorrowHostUseCase(unittest.TestCase):
    def test_records_and_releases_the_pc(self):
        usage = MagicMock()
        usage.start.return_value = "usage-1"
        with BorrowHostUseCase(usage, "folios").execute("pc1", 120):
            usage.start.assert_called_once_with("pc1", "folios", 120)
            usage.finish.assert_not_called()
        usage.finish.assert_called_once_with("usage-1")

    def test_bookkeeping_failure_does_not_break_the_caller(self):
        usage = MagicMock()
        usage.start.side_effect = RuntimeError("db caída")
        with BorrowHostUseCase(usage, "folios").execute("pc1", 120) as should_stop:
            self.assertFalse(should_stop())  # nothing was recorded, so nothing to stop
        usage.finish.assert_not_called()

    @patch("app.domains.digitization.application.use_cases.borrow_host_use_case.time.monotonic")
    def test_the_borrower_is_told_when_the_monitor_asks_it_to_stop(self, monotonic):
        usage = MagicMock()
        usage.start.return_value = "usage-1"
        usage.stop_requested.side_effect = [False, True]
        with BorrowHostUseCase(usage, "folios").execute("pc1", 120) as should_stop:
            monotonic.return_value = 100.0
            self.assertFalse(should_stop())
            monotonic.return_value = 100.5  # between tokens: the cached answer
            self.assertFalse(should_stop())
            self.assertEqual(usage.stop_requested.call_count, 1)

            monotonic.return_value = 103.0  # past the poll interval
            self.assertTrue(should_stop())

    def test_a_flag_that_cannot_be_read_lets_the_call_carry_on(self):
        usage = MagicMock()
        usage.start.return_value = "usage-1"
        usage.stop_requested.side_effect = RuntimeError("db caída")
        with BorrowHostUseCase(usage, "folios").execute("pc1", 120) as should_stop:
            self.assertFalse(should_stop())


class TestPickWorkerHostsUseCase(unittest.TestCase):
    def _use_case(self, installed, busy=()):
        worker = MagicMock()
        worker.models.side_effect = lambda host: installed[host]
        return PickWorkerHostsUseCase(worker, list(installed), lambda: set(busy))

    def test_only_pcs_that_have_the_model(self):
        use_case = self._use_case({"pc1": {"gemma4:e4b"}, "pc2": {"qwen3-vl:4b"}, "pc3": None})
        self.assertEqual(use_case.execute("gemma4:e4b"), ["pc1"])

    def test_pc_digitizing_goes_last(self):
        use_case = self._use_case({"pc1": {"gemma4:e4b"}, "pc2": {"gemma4:e4b"}}, busy=["pc1"])
        self.assertEqual(use_case.execute("gemma4:e4b"), ["pc2", "pc1"])

    def test_no_hosts_configured_returns_empty(self):
        self.assertEqual(PickWorkerHostsUseCase(MagicMock(), [], set).execute("gemma4:e4b"), [])


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

    @patch("app.domains.digitization.infrastructure.dispatcher.time.monotonic")
    def test_stop_watcher_caches_between_tokens_and_latches_once_stopped(self, monotonic):
        repository = MagicMock()
        repository.stop_requested.side_effect = [False, True]
        watcher = self._dispatcher(repository, MagicMock(), ["pc1"])._stop_watcher("job-1")

        monotonic.return_value = 100.0
        self.assertFalse(watcher())
        monotonic.return_value = 100.5  # a few tokens later, still the cached answer
        self.assertFalse(watcher())
        self.assertEqual(repository.stop_requested.call_count, 1)

        monotonic.return_value = 103.0  # past the poll interval: asks again
        self.assertTrue(watcher())
        monotonic.return_value = 200.0  # once stopped it never asks again
        self.assertTrue(watcher())
        self.assertEqual(repository.stop_requested.call_count, 2)

    def test_skips_health_checks_when_queue_is_empty(self):
        repository = MagicMock()
        repository.has_pending.return_value = False
        worker = MagicMock()
        self._dispatcher(repository, worker, ["pc1"])._dispatch_round()
        worker.check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
