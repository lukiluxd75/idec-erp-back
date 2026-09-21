import logging
import re
from dataclasses import dataclass

from fastapi import WebSocket

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
    not set up today. The same per-process limitation applies to the "phone
    connected" presence broadcast below.
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

    def is_mobile_connected(self, user_sub: str) -> bool:
        """Snapshot for the GET /captures/presence poll: whether THIS worker's
        registry currently has a phone socket for `user_sub`. Kept separate from
        the WS presence push (which only reaches sockets already open on this
        same worker) so the frontend can poll it directly without tearing down
        and reopening the main WS every few seconds -- a naive "reconnect often
        to refresh presence" approach throttles in the browser and drops the
        update channel along with it. A REST poll is naturally load-balanced
        across workers request by request, so it catches up within a few polls
        without ever closing the long-lived socket."""
        return any(c.is_mobile for c in self._connections.values() if c.user_sub == user_sub)

    async def _broadcast_presence(self, user_sub: str) -> None:
        """Tells every open socket of `user_sub` whether at least one of that
        account's other connections is a phone — see PhoneConnectedBadge on the
        frontend."""
        peers = [c for c in self._connections.values() if c.user_sub == user_sub]
        mobile_connected = any(c.is_mobile for c in peers)
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
