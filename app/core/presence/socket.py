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
        self.device_id = device_id or f"ws-{uuid.uuid4().hex[:16]}"
        self._task: Optional[asyncio.Task] = None

    def _write(self, action: str) -> None:
        """One short-lived session, closed before returning. Runs in a worker
        thread (see `_in_thread`): SQLAlchemy here is blocking, and doing it on
        the event loop would stall every other socket on this worker.

        Todo dentro del try, incluido abrir la sesion: si la BD no esta, pedirla
        ya lanza, y esto se llama desde el camino de conexion del websocket --
        una presencia que no se puede escribir no puede impedir que el
        arquitecto abra la pantalla.
        """
        db = None
        try:
            db = SessionLocal()
            store = SqlPresenceStore(db)
            if action == "leave":
                store.leave(self.user_sub, self.channel, self.device_id)
            else:
                store.heartbeat(self.user_sub, self.channel, self.device_id, self.is_mobile)
        except Exception:
            logger.warning("presence: no se pudo %s en %s", action, self.channel, exc_info=True)
        finally:
            if db is not None:
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


def is_phone_connected(user_sub: str, module_channel: str) -> bool:
    """Lectura sincrona con su propia sesion corta, para quien no tiene una (el
    camino del websocket). Los endpoints REST deben tomar `get_db` y usar
    SqlPresenceStore directamente.

    Misma pregunta que hace el endpoint REST del modulo -- sesion de la app O
    presencia propia -- porque el push por websocket y el poll tienen que
    contestar lo mismo: si discrepan, el indicador vuelve a parpadear.
    """
    db = None
    try:
        db = SessionLocal()
        return SqlPresenceStore(db).is_phone_connected(user_sub, module_channel)
    except Exception:
        logger.warning("presence: no se pudo leer %s", module_channel, exc_info=True)
        return False
    finally:
        if db is not None:
            db.close()
