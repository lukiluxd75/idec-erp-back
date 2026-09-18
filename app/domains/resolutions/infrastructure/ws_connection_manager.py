import logging
from dataclasses import dataclass

from fastapi import WebSocket

logger = logging.getLogger("uvicorn.error")


@dataclass
class _Connection:
    websocket: WebSocket
    user_sub: str
    is_mobile: bool


class ResolutionsConnectionManager:
    """
    In-memory registry of sockets connected to the Resolutions update channel.
    Process memory is enough (no Redis pub/sub or distributed bus) because the
    backend runs in a single uvicorn process — see the frontend
    useResolutionsUpdates.js, which already assumes simple reconnection. The
    same per-process limitation applies to the "phone connected" presence
    broadcast below.
    """

    def __init__(self):
        self._connections: dict[WebSocket, _Connection] = {}

    async def connect(self, websocket: WebSocket, user_sub: str, is_mobile: bool) -> None:
        await websocket.accept()
        self._connections[websocket] = _Connection(websocket, user_sub, is_mobile)
        await self._broadcast_presence(user_sub)

    async def disconnect(self, websocket: WebSocket) -> None:
        conn = self._connections.pop(websocket, None)
        if conn:
            await self._broadcast_presence(conn.user_sub)

    async def notify_change(self) -> None:
        """Notify all connected sockets that something changed (message content
        does not matter beyond `type`: the frontend only uses it as a trigger
        to re-fetch the list/detail — see useResolutionsUpdates.js)."""
        await self._broadcast_all({"type": "update"})

    async def _broadcast_presence(self, user_sub: str) -> None:
        """Tells every open socket of `user_sub` whether at least one of that
        account's other connections is a phone — see PhoneConnectedBadge on the
        frontend."""
        peers = [c for c in self._connections.values() if c.user_sub == user_sub]
        mobile_connected = any(c.is_mobile for c in peers)
        payload = {"type": "presence", "mobile_connected": mobile_connected}
        caidos = []
        for conn in peers:
            try:
                await conn.websocket.send_json(payload)
            except Exception:
                caidos.append(conn.websocket)
        for ws in caidos:
            self._connections.pop(ws, None)

    async def _broadcast_all(self, payload: dict) -> None:
        caidos = []
        for ws in list(self._connections.keys()):
            try:
                await ws.send_json(payload)
            except Exception:
                caidos.append(ws)
        for ws in caidos:
            self._connections.pop(ws, None)
