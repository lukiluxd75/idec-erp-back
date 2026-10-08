import asyncio

from app.core.middleware.request_id import RequestIdMiddleware, get_request_id


def invoke(app, headers=None):
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
                "path": "/api/v1/health",
                "query_string": b"",
                "headers": headers or [],
                "state": {},
            },
            receive,
            send,
        )
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    return start


def health_app(scope, receive, send):
    async def respond():
        assert get_request_id() == scope["state"]["request_id"]
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return respond()


def test_request_id_middleware_preserves_a_valid_incoming_id():
    response = invoke(RequestIdMiddleware(health_app), [(b"x-request-id", b"client-request-42")])

    assert (b"x-request-id", b"client-request-42") in response["headers"]


def test_request_id_middleware_replaces_invalid_incoming_ids():
    response = invoke(RequestIdMiddleware(health_app), [(b"x-request-id", b"invalid request id")])
    request_id = next(value for key, value in response["headers"] if key.lower() == b"x-request-id")

    assert request_id.decode() != "invalid request id"
    assert len(request_id) == 36
