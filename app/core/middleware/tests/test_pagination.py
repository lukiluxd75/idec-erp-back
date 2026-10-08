import asyncio
import json

from app.core.middleware.pagination import PaginationMiddleware


def invoke(app, path, query=b""):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "query_string": query,
                "headers": [],
            },
            receive,
            send,
        )
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return start, json.loads(body)


def json_list_app(items):
    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json"), (b"content-length", b"999")],
            }
        )
        await send({"type": "http.response.body", "body": json.dumps(items).encode()})

    return app


def headers_as_dict(start):
    return {key.lower(): value for key, value in start["headers"]}


def test_pagination_slices_json_list_and_adds_page_metadata():
    start, payload = invoke(
        PaginationMiddleware(json_list_app(["a", "b", "c", "d"])),
        "/api/v1/templates",
        b"page_size=2&page_offset=1",
    )

    headers = headers_as_dict(start)
    assert payload == ["b", "c"]
    assert headers[b"x-total-count"] == b"4"
    assert headers[b"x-page-limit"] == b"2"
    assert headers[b"x-page-offset"] == b"1"
    assert int(headers[b"content-length"]) == len(json.dumps(payload, separators=(",", ":")).encode())


def test_pagination_does_not_change_response_without_query_parameters():
    start, payload = invoke(PaginationMiddleware(json_list_app([1, 2, 3])), "/api/v1/templates")

    assert payload == [1, 2, 3]
    assert b"x-total-count" not in headers_as_dict(start)


def test_pagination_leaves_excluded_domain_routes_untouched():
    start, payload = invoke(
        PaginationMiddleware(json_list_app([1, 2, 3])),
        "/api/v1/detection/campaigns",
        b"page_size=1",
    )

    assert payload == [1, 2, 3]
    assert b"x-total-count" not in headers_as_dict(start)
