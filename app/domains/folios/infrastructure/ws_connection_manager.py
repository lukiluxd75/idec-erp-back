import logging

from fastapi import WebSocket

logger = logging.getLogger("uvicorn.error")


class FoliosConnectionManager:
    """
    In-memory registry of sockets on the folios update channel (mirrors
    CapturesConnectionManager/ResolutionsConnectionManager, same per-process
    caveat: with several uvicorn workers a notify only reaches sockets of the
    worker that sent it -- the web also refreshes on its own while a folio is
    still processing, so a missed ping only delays the update).
    """

    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def notify_change(self) -> None:
        """Content is irrelevant: the client only uses it as a trigger to re-fetch."""
        dropped = []
        for connection in self._connections:
            try:
                await connection.send_text("update")
            except Exception:
                dropped.append(connection)
        for connection in dropped:
            self._connections.discard(connection)
