"""Request correlation IDs and structured HTTP access records."""

from __future__ import annotations

import json
import logging
import re
import time
import traceback
import uuid
from contextvars import ContextVar
from typing import Any


request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_logger = logging.getLogger("uvicorn.error")


class _RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        request_id = request_id_context.get()
        if request_id:
            message = record.getMessage()
            try:
                payload = json.loads(message)
            except (TypeError, json.JSONDecodeError):
                payload = None
            if not isinstance(payload, dict):
                payload = {"message": message}
            payload.setdefault("request_id", request_id)
            payload.setdefault("logger", record.name)
            payload.setdefault("level", record.levelname)
            if record.exc_info:
                payload["stacktrace"] = "".join(traceback.format_exception(*record.exc_info))
                record.exc_info = None
                record.exc_text = None
            record.msg = json.dumps(payload, ensure_ascii=False)
            record.args = ()
        return True


_logger.addFilter(_RequestContextFilter())


def get_request_id() -> str | None:
    """Return the request ID for the current async context, if one is active."""

    return request_id_context.get()


class RequestIdMiddleware:
    """Attach an ID to HTTP requests and log one JSON record when each finishes."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = next(
            (value.decode("latin-1") for key, value in scope.get("headers", []) if key.lower() == b"x-request-id"),
            "",
        )
        request_id = incoming if _REQUEST_ID_PATTERN.fullmatch(incoming) else str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as error:
            _logger.error(
                json.dumps(
                    {
                        "event": "http.request.failed",
                        "request_id": request_id,
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status_code": 500,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                        "error": str(error),
                        "exception_type": type(error).__name__,
                    },
                    ensure_ascii=False,
                )
            )
            raise
        else:
            _logger.info(
                json.dumps(
                    {
                        "event": "http.request.completed",
                        "request_id": request_id,
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status_code": status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            request_id_context.reset(token)
