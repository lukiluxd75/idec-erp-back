import logging

from fastapi import WebSocket

logger = logging.getLogger("uvicorn.error")


class CapturesConnectionManager:
    """
    In-memory registry of sockets connected to the Captures update channel
    (mirrors ResolutionsConnectionManager). Unlike the capture store
    (SqlCaptureStore, in Postgres — shared across workers), this registry IS
    per-process: with several workers (e.g. `--workers 4`), each has its own
    connection set, so a `notify_change()` from the worker that got the phone
    POST does NOT reach a browser on another worker's socket. With the store
    already shared, the worst case went from "never appears" to "need to refresh
    the page" — see useCapturasUpdates.js on the frontend, which already assumes
    simple reconnect and not a 100% reliable channel. Fixing this properly (notify
    regardless of worker) needs something like Redis pub/sub between processes —
    not set up today.
    """

    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def notify_change(self) -> None:
        """Notify all connected sockets that something changed (message content
        does not matter: the frontend only uses it as a trigger to re-fetch the
        pending captures list — see useCapturasUpdates.js)."""
        dropped = []
        for connection in self._connections:
            try:
                await connection.send_text("update")
            except Exception:
                dropped.append(connection)
        for connection in dropped:
            self._connections.discard(connection)
