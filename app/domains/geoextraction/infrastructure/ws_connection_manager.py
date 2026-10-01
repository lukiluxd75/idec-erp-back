import asyncio
import logging
import re
from dataclasses import dataclass

from fastapi import WebSocket

from app.core.presence import CHANNEL_GEOEXTRACTION
from app.core.presence.socket import is_mobile_present

logger = logging.getLogger("uvicorn.error")

_DIGID_APP_UA_RE = re.compile(r"IDEC-DigID-Android-App", re.IGNORECASE)


def is_digid_app_user_agent(user_agent: str) -> bool:
    """True only for the DigiD mobile app's presence socket (handshake
    User-Agent 'IDEC-DigID-Android-App (Mobi; Android)'), not for a mobile
    *browser* tab of the web app itself. Deliberately narrower than the
    generic app.core.utils.user_agent.is_mobile_user_agent used by
    resolutions: this badge means "the DigiD app has GeoextractScreen open",
    not just "some phone is connected" — a phone browsing the ERP site in
    Chrome must not light it up."""
    return bool(_DIGID_APP_UA_RE.search(user_agent or ""))


@dataclass
class _Connection:
    websocket: WebSocket
    user_sub: str
    is_mobile: bool


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

    The "phone connected" indicator used to share that limitation and no longer
    does: presence moved to app/core/presence, backed by the same Postgres the
    four processes share. Only the `update` hint below is still per-process.
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
        does not matter beyond `type`: the frontend only uses it as a trigger to
        re-fetch the pending captures list — see useCapturasUpdates.js)."""
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
        mobile_connected = await asyncio.to_thread(is_mobile_present, user_sub, CHANNEL_GEOEXTRACTION)
        payload = {"type": "presence", "mobile_connected": mobile_connected}
        dropped = []
        for conn in peers:
            try:
                await conn.websocket.send_json(payload)
            except Exception:
                dropped.append(conn.websocket)
        for ws in dropped:
            self._connections.pop(ws, None)

    async def _broadcast_all(self, payload: dict) -> None:
        dropped = []
        for ws in list(self._connections.keys()):
            try:
                await ws.send_json(payload)
            except Exception:
                dropped.append(ws)
        for ws in dropped:
            self._connections.pop(ws, None)
