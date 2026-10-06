import unittest
from unittest import mock

import requests

from app.domains.folios.domain.exceptions import OcrUnavailableException
from app.domains.folios.infrastructure.gamc_ocr_client import GamcOcrClient

BLOCK = {"points": [[0, 0], [10, 0], [10, 5], [0, 5]], "text": "FOLIO", "confidence": 0.9}


class Response:
    def __init__(self, payload=None, status=200):
        self._payload, self.status_code = payload or {}, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def accepted():
    return Response({"job_id": "j1"})


def done():
    return Response({"status": "done", "result": {"result": [BLOCK]}})


def client(retries=2):
    waits = []
    return (
        GamcOcrClient("http://ocr", timeout_seconds=5, poll_interval_seconds=0.01, retries=retries,
                      retry_delay_seconds=3.0, sleep=waits.append),
        waits,
    )


class GamcOcrRetryTest(unittest.TestCase):
    def test_a_dropped_connection_is_retried_and_the_page_is_read(self):
        ocr, waits = client()
        with mock.patch("requests.post", side_effect=[requests.ConnectionError("down"), accepted()]), \
                mock.patch("requests.get", return_value=done()):
            blocks = ocr.read(b"img")
        self.assertEqual([b.text for b in blocks], ["FOLIO"])
        self.assertEqual(waits, [3.0])

    def test_the_wait_grows_with_each_retry(self):
        ocr, waits = client()
        with mock.patch("requests.post", side_effect=[requests.Timeout(), requests.ConnectionError(), accepted()]), \
                mock.patch("requests.get", return_value=done()):
            ocr.read(b"img")
        self.assertEqual(waits, [3.0, 6.0])

    def test_gives_up_after_the_last_attempt_and_says_how_many(self):
        ocr, waits = client(retries=2)
        with mock.patch("requests.post", side_effect=requests.ConnectionError("down")) as post:
            with self.assertRaises(OcrUnavailableException) as raised:
                ocr.read(b"img")
        self.assertEqual(post.call_count, 3)
        self.assertIn("ConnectionError", raised.exception.message)
        self.assertIn("tras 3 intentos", raised.exception.message)
        self.assertEqual(len(waits), 2)

    def test_a_server_error_is_retried(self):
        ocr, _ = client()
        with mock.patch("requests.post", side_effect=[Response(status=502), accepted()]), \
                mock.patch("requests.get", return_value=done()):
            self.assertEqual(len(ocr.read(b"img")), 1)

    def test_a_job_marked_failed_is_sent_again(self):
        ocr, _ = client()
        failed = Response({"status": "failed"})
        with mock.patch("requests.post", return_value=accepted()) as post, \
                mock.patch("requests.get", side_effect=[failed, done()]):
            self.assertEqual(len(ocr.read(b"img")), 1)
        self.assertEqual(post.call_count, 2)

    def test_a_client_error_is_not_retried(self):
        ocr, waits = client()
        with mock.patch("requests.post", return_value=Response(status=413)) as post:
            with self.assertRaises(OcrUnavailableException):
                ocr.read(b"img")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(waits, [])

    def test_no_retries_when_configured_so(self):
        ocr, waits = client(retries=0)
        with mock.patch("requests.post", side_effect=requests.ConnectionError("down")) as post:
            with self.assertRaises(OcrUnavailableException):
                ocr.read(b"img")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(waits, [])


if __name__ == "__main__":
    unittest.main()
