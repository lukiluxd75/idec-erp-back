"""Opt-in pagination for JSON-array GET responses across list endpoints."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs


_EXCLUDED_PREFIXES = ("/detection", "/cadastralviewer", "/procedurereports")


class PaginationMiddleware:
    """Slice JSON list responses when callers supply ``page_size`` and/or ``page_offset``.

    The response remains a JSON array for compatibility. Page metadata is sent
    in X-Total-Count, X-Page-Limit, and X-Page-Offset headers.
    """

    def __init__(self, app: Any, max_limit: int = 500, default_limit: int = 50) -> None:
        self.app = app
        self.max_limit = max_limit
        self.default_limit = default_limit

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("method") != "GET":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(f"{prefix}/" in path or path.endswith(prefix) for prefix in _EXCLUDED_PREFIXES):
            await self.app(scope, receive, send)
            return

        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        if "page_size" not in query and "page_offset" not in query:
            await self.app(scope, receive, send)
            return

        try:
            limit = int(query.get("page_size", [str(self.default_limit)])[0])
            offset = int(query.get("page_offset", ["0"])[0])
        except (TypeError, ValueError):
            await self.app(scope, receive, send)
            return
        if limit < 1 or limit > self.max_limit or offset < 0:
            await self.app(scope, receive, send)
            return

        response_start: dict[str, Any] | None = None
        body_chunks: list[bytes] = []

        async def collect_response(message: dict[str, Any]) -> None:
            nonlocal response_start
            if message["type"] == "http.response.start":
                response_start = message
                return
            if message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return

                body = b"".join(body_chunks)
                headers = list((response_start or {}).get("headers", []))
                content_type = next(
                    (value.split(b";", 1)[0].strip().lower() for key, value in headers if key.lower() == b"content-type"),
                    b"",
                )
                if content_type == b"application/json":
                    try:
                        payload = json.loads(body)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        payload = None
                    if isinstance(payload, list):
                        total = len(payload)
                        body = json.dumps(
                            payload[offset : offset + limit],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode("utf-8")
                        headers = [(key, value) for key, value in headers if key.lower() != b"content-length"]
                        headers.extend(
                            [
                                (b"x-total-count", str(total).encode("ascii")),
                                (b"x-page-limit", str(limit).encode("ascii")),
                                (b"x-page-offset", str(offset).encode("ascii")),
                                (b"content-length", str(len(body)).encode("ascii")),
                            ]
                        )
                        start = dict(response_start or {})
                        start["headers"] = headers
                        await send(start)
                        await send({"type": "http.response.body", "body": body, "more_body": False})
                        return

                if response_start is not None:
                    await send(response_start)
                await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, receive, collect_response)
