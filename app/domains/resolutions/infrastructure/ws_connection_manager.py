import asyncio
import logging
from dataclasses import dataclass

from fastapi import WebSocket

from app.core.presence import CHANNEL_RESOLUTIONS
from app.core.presence.socket import is_phone_connected

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
        """Tells every open socket of `user_sub` whether a phone of that account
        is connected — see PhoneConnectedBadge on the frontend. Instant, but
        only reaches sockets already open on THIS worker; the frontend's poll
        of GET .../presence is what makes the indicator right everywhere."""
        peers = [c for c in self._connections.values() if c.user_sub == user_sub]
        # La verdad sale del store compartido, no de `peers`: este proceso solo
        # ve sus propios sockets, asi que preguntarle a `peers` empujaba
        # "no conectado" cuando el celular estaba en otro worker -- y ese push
        # contradecia al poll, que ya lee lo correcto. Se lee en un hilo porque
        # SQLAlchemy aqui es bloqueante y esto corre en el event loop.
        mobile_connected = await asyncio.to_thread(is_phone_connected, user_sub, CHANNEL_RESOLUTIONS)
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
