"""
Presence for a long-lived websocket, kept in the shared store.

Exists so geoextraction and resolutions do not each re-implement the two things
that are easy to get wrong here:

**One short DB session per write, never one for the socket's lifetime.** The
pool is `DB_POOL_SIZE + DB_POOL_MAX_OVERFLOW` (5 + 10) per worker, and a socket
stays open for as long as the architect keeps the screen open. Holding a session
per socket would exhaust the pool with a dozen phones and take the whole worker
down with it -- so each beat opens a session, writes one row and closes it.

**A heartbeat, so a dead worker cannot pin the badge to "connected".** `leave()`
on disconnect is best-effort: a killed process never runs it. The row therefore
carries an expiry that only a live heartbeat pushes forward.
"""
import asyncio
import logging
import uuid
from typing import Optional

from app.core.database.connection import SessionLocal
from app.core.presence.store import HEARTBEAT_SECONDS, SqlPresenceStore

logger = logging.getLogger("uvicorn.error")


class SocketPresence:
    """Presence of one websocket. Create on connect, `await start()`, and
    `await stop()` in the disconnect path (a `finally`, so a drop still runs it).

    Writes are swallowed on failure by the store itself: presence is cosmetic and
    must never take the socket down with it.
    """

    def __init__(self, user_sub: str, channel: str, is_mobile: bool, device_id: Optional[str] = None):
        self.user_sub = user_sub
        self.channel = channel
        self.is_mobile = is_mobile
        # One id per socket, not per account: the same architect may have the
        # app on a phone and the ERP open on the desktop, and each connection
        # owns its own row.
        self.device_id = device_id or f"ws-{uuid.uuid4().hex[:16]}"
        self._task: Optional[asyncio.Task] = None

    def _write(self, action: str) -> None:
        """One short-lived session, closed before returning. Runs in a worker
        thread (see `_in_thread`): SQLAlchemy here is blocking, and doing it on
        the event loop would stall every other socket on this worker."""
        db = SessionLocal()
        try:
            store = SqlPresenceStore(db)
            if action == "leave":
                store.leave(self.user_sub, self.channel, self.device_id)
            else:
                store.heartbeat(self.user_sub, self.channel, self.device_id, self.is_mobile)
        finally:
            db.close()

    async def _in_thread(self, action: str) -> None:
        await asyncio.to_thread(self._write, action)

    async def start(self) -> None:
        """Register the socket and keep refreshing it until `stop()`."""
        await self._in_thread("enter")
        self._task = asyncio.create_task(self._beat())

    async def _beat(self) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                await self._in_thread("heartbeat")
        except asyncio.CancelledError:
            raise
        except Exception:
            # A heartbeat that dies must not take the socket with it: the row
            # simply expires and the badge goes grey, which is the truthful
            # outcome if this worker can no longer talk to the database.
            logger.warning("presence: latido detenido en %s", self.channel, exc_info=True)

    async def stop(self) -> None:
        """Cancel the heartbeat and release the row."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        await self._in_thread("leave")


def is_mobile_present(user_sub: str, channel: str) -> bool:
    """Synchronous read on its own short session, for callers without one (the
    websocket path). REST endpoints should take `get_db` and use
    SqlPresenceStore directly instead of this."""
    db = SessionLocal()
    try:
        return SqlPresenceStore(db).is_mobile_present(user_sub, channel)
    except Exception:
        logger.warning("presence: no se pudo leer %s", channel, exc_info=True)
        return False
    finally:
        db.close()
