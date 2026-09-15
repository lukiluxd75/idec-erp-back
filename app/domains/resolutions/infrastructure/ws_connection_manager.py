import logging

from fastapi import WebSocket

logger = logging.getLogger("uvicorn.error")


class ResolutionsConnectionManager:
    """
    In-memory registry of sockets connected to the Resolutions update channel.
    Process memory is enough (no Redis pub/sub or distributed bus) because the
    backend runs in a single uvicorn process — see the frontend
    useResolutionsUpdates.js, which already assumes simple reconnection.
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
        does not matter: the frontend only uses it as a trigger to re-fetch
        the list/detail — see useResolutionsUpdates.js)."""
        caidos = []
        for conexion in self._connections:
            try:
                await conexion.send_text("update")
            except Exception:
                caidos.append(conexion)
        for conexion in caidos:
            self._connections.discard(conexion)
