"""
Cross-worker presence store for the "phone connected" indicator.

Two kinds of presence feed it, because the two cases on this ERP are different:

* **socket** — the mobile app holds a websocket open (geoextraction's DigiD
  screen, resolutions). `enter()` on connect, `heartbeat()` every
  HEARTBEAT_SECONDS while it lives, `leave()` on disconnect. Short lifetime:
  there is a live connection to tell the truth about.
* **activity** — the mobile app only makes HTTP requests and never opens a
  socket (folder analysis: the contract in docs/FOLDER_ANALYSIS_API_MOVIL.md is
  a plain `POST /captures`). `touch_activity()` on each request that arrived
  from a phone. Longer lifetime, because uploads come in bursts with gaps
  between them and the app is plainly still there during a gap.

Both land in the same table with their own `expires_at`, so the reader is one
query that does not care which wrote the row.
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.presence.models import DevicePresenceModel

logger = logging.getLogger("uvicorn.error")

# --- canales -----------------------------------------------------------------
#
# Constantes y no cadenas sueltas, para que un typo no haga que un escritor y un
# lector dejen de verse en silencio (el indicador simplemente no se encenderia).
# Viven aqui y no en __init__ porque is_phone_connected() necesita CHANNEL_SESSION.
CHANNEL_GEOEXTRACTION = "geoextraction"
CHANNEL_RESOLUTIONS = "resolutions"
CHANNEL_FOLDER_ANALYSIS = "folder-analysis"
# Canal transversal: "la app movil tiene sesion abierta con el ERP". No pertenece
# a ningun modulo -- lo escribe el login/refresh/logout (dominio security) y lo
# cuenta el indicador de cualquier modulo.
CHANNEL_SESSION = "session"

# --- lifetimes ---------------------------------------------------------------

# Websocket-backed presence. Sized against the heartbeat below, not picked
# round: 70s tolerates two missed beats before the badge goes grey -- enough
# that a slow network does not make it blink, short enough that closing the app
# is noticed within about a minute.
SOCKET_TTL = timedelta(seconds=70)

# Socket heartbeat period. Must stay comfortably under SOCKET_TTL.
HEARTBEAT_SECONDS = 25.0

# Activity-backed presence. Deliberately much longer than SOCKET_TTL: there is
# no connection here, only "the app made a request". An architect photographing
# a folder sends a batch, then spends a couple of minutes on the next document
# before sending again, and the phone is obviously still connected throughout.
# Three minutes keeps the badge steady across those gaps while still going grey
# a few minutes after the app is actually put away.
ACTIVITY_TTL = timedelta(minutes=3)

# Presencia de SESION: "el arquitecto inicio sesion en la app movil y no la ha
# cerrado". No describe una conexion viva sino una sesion abierta, asi que dura
# mucho mas que las dos anteriores y la refresca cualquier peticion autenticada
# que llegue desde la app (el login, el refresh del token, una subida de fotos).
#
# Se borra en el acto cuando la app cierra sesion (DELETE /api/presence/session).
# El TTL es la red de seguridad para el caso en el que eso no llega nunca --
# la app se mata desde el administrador de tareas, el celular se queda sin
# bateria -- y por eso no es de horas: dos horas sin que la app diga nada es
# señal suficiente de que ya no esta ahi.
SESSION_TTL = timedelta(hours=2)

# Rows long past their expiry are dropped on the next lookup. Housekeeping
# only: `is_mobile_present` already ignores anything expired.
_PURGE_AFTER = timedelta(hours=6)


def _now() -> datetime:
    # Naive UTC, matching DateTime(timezone=False) used across this codebase's
    # models (geoextraction_captures, folder analysis) so comparisons line up.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SqlPresenceStore:
    """Postgres-backed presence. One instance per request/session, like
    SqlCaptureStore -- deliberately NOT a process-wide singleton, since the
    whole point is that the state does not live in this process."""

    def __init__(self, db: Session):
        self._db = db

    # --- writers --------------------------------------------------------------

    def enter(self, user_sub: str, channel: str, device_id: str, is_mobile: bool) -> None:
        """Register a websocket that just connected."""
        self._upsert(user_sub, channel, device_id, is_mobile, SOCKET_TTL)

    def heartbeat(self, user_sub: str, channel: str, device_id: str, is_mobile: bool) -> None:
        """Push a live socket's expiry forward."""
        self._upsert(user_sub, channel, device_id, is_mobile, SOCKET_TTL)

    def open_session(self, user_sub: str, channel: str, device_id: str) -> None:
        """La app movil inicio sesion (o sigue usandola). Ver SESSION_TTL."""
        self._upsert(user_sub, channel, device_id, True, SESSION_TTL)

    def close_session(self, user_sub: str, channel: str, device_id: str) -> None:
        """La app movil cerro sesion: el indicador se apaga en el acto, sin
        esperar al TTL. Es lo que hace que "cerrar sesion en el celular" se vea
        de inmediato en el escritorio."""
        self.leave(user_sub, channel, device_id)

    def close_all_sessions(self, user_sub: str, channel: str) -> None:
        """Cierra toda sesion de esta cuenta en el canal, sin importar el
        device_id. Hace falta porque la app no tiene por que mandar en el logout
        el mismo User-Agent con el que inicio sesion (ni acordarse de un id), y
        una sesion que no se puede cerrar dejaria el indicador encendido hasta
        que expire."""
        try:
            self._db.execute(
                delete(DevicePresenceModel).where(
                    DevicePresenceModel.user_sub == user_sub,
                    DevicePresenceModel.channel == channel,
                )
            )
            self._db.commit()
        except Exception:
            self._db.rollback()
            logger.warning("presence: no se pudo cerrar la sesion de %s", channel, exc_info=True)

    def close_all_mobile(self, user_sub: str) -> None:
        """Desconecta TODA presencia de celular de esta cuenta, en cualquier
        canal. Es lo que corresponde al cerrar sesion en la app: el celular ya
        no esta en ningun modulo, y dejar la presencia de "actividad reciente"
        viva mantendria el indicador encendido hasta tres minutos despues de
        haber cerrado sesion.

        Filtra por is_mobile para no borrar las filas de los sockets del
        escritorio, que no encienden nada pero son contabilidad de otra cosa.
        """
        try:
            self._db.execute(
                delete(DevicePresenceModel).where(
                    DevicePresenceModel.user_sub == user_sub,
                    DevicePresenceModel.is_mobile.is_(True),
                )
            )
            self._db.commit()
        except Exception:
            self._db.rollback()
            logger.warning("presence: no se pudo desconectar el celular", exc_info=True)

    def touch_activity(self, user_sub: str, channel: str, device_id: str) -> None:
        """Presence derived from an HTTP request that came from a phone. Always
        `is_mobile=True`: the caller only calls this after classifying the
        User-Agent, so a request from the desktop web app never gets here (the
        architect can upload captures from the browser too -- see
        captureUpload.js -- and that must not light the badge)."""
        self._upsert(user_sub, channel, device_id, True, ACTIVITY_TTL)

    def leave(self, user_sub: str, channel: str, device_id: str) -> None:
        """Deregister a socket that disconnected. Best-effort: if this never
        runs -- worker killed, connection reset -- `expires_at` retires the row
        on its own."""
        try:
            self._db.execute(
                delete(DevicePresenceModel).where(
                    DevicePresenceModel.user_sub == user_sub,
                    DevicePresenceModel.channel == channel,
                    DevicePresenceModel.device_id == device_id,
                )
            )
            self._db.commit()
        except Exception:
            self._db.rollback()
            logger.warning("presence: no se pudo liberar %s/%s", channel, device_id, exc_info=True)

    # --- reader ---------------------------------------------------------------

    def is_mobile_present(self, user_sub: str, channel: str) -> bool:
        """True if this account has at least one unexpired phone on `channel`.
        Answered from Postgres, so all four workers give the same answer -- which
        is the whole fix for the badge that used to flicker every few seconds."""
        self._purge_old()
        row = self._db.execute(
            select(DevicePresenceModel.device_id)
            .where(
                DevicePresenceModel.user_sub == user_sub,
                DevicePresenceModel.channel == channel,
                DevicePresenceModel.is_mobile.is_(True),
                DevicePresenceModel.expires_at > _now(),
            )
            .limit(1)
        ).first()
        return row is not None

    def is_phone_connected(self, user_sub: str, module_channel: str) -> bool:
        """La pregunta que hace el indicador "Celular conectado" de CUALQUIER
        modulo. Es cierta por dos motivos distintos, y basta uno:

          * CHANNEL_SESSION -- el arquitecto inicio sesion en la app movil y no
            la ha cerrado. Es el motivo principal: dura toda la sesion, asi que
            el indicador queda encendido tambien mientras no esta haciendo nada
            en ese modulo concreto.
          * `module_channel` -- presencia propia del modulo: un websocket vivo
            (geoextraction, resolutions) o actividad reciente (folder analysis).

        Un unico metodo y no la tupla repetida en cada endpoint porque hay SEIS
        sitios que leen presencia -- tres endpoints REST y dos broadcasts por
        websocket -- y si uno contesta distinto que otro vuelve el parpadeo que
        todo esto venia a quitar: el push diria "no conectado" justo despues de
        que el poll dijera que si.
        """
        return self.is_mobile_present_any(user_sub, (CHANNEL_SESSION, module_channel))

    def is_mobile_present_any(self, user_sub: str, channels) -> bool:
        """True si hay celular en CUALQUIERA de `channels`. Una pantalla puede
        encenderse por mas de un motivo: el analizador de carpetas cuenta tanto
        "la app tiene sesion abierta" como "la app acaba de subir fotos", y le
        basta con que uno de los dos sea cierto."""
        return any(self.is_mobile_present(user_sub, c) for c in channels)

    # --- internals ------------------------------------------------------------

    def _upsert(
        self, user_sub: str, channel: str, device_id: str, is_mobile: bool, ttl: timedelta
    ) -> None:
        """ON CONFLICT so a heartbeat is one statement and two workers racing on
        the same device cannot raise a duplicate-key error.

        The construct is dialect-specific, so it is picked from the bind: the app
        runs on Postgres, the test suite on SQLite (connection.py supports both).
        Both dialects expose the same on_conflict_do_update API.
        """
        try:
            now = _now()
            bind = self._db.get_bind()
            insert = sqlite_insert if bind.dialect.name == "sqlite" else pg_insert
            stmt = insert(DevicePresenceModel).values(
                user_sub=user_sub,
                channel=channel,
                device_id=device_id,
                is_mobile=is_mobile,
                last_seen_at=now,
                expires_at=now + ttl,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_sub", "channel", "device_id"],
                set_={
                    "is_mobile": stmt.excluded.is_mobile,
                    "last_seen_at": stmt.excluded.last_seen_at,
                    "expires_at": stmt.excluded.expires_at,
                },
            )
            self._db.execute(stmt)
            self._db.commit()
        except Exception:
            self._db.rollback()
            # Presence is cosmetic: a failed write must never break the request
            # that carried it (an upload, a socket connect). Worst case the
            # badge stays grey for a cycle.
            logger.warning("presence: no se pudo registrar %s/%s", channel, device_id, exc_info=True)

    def _purge_old(self) -> None:
        try:
            self._db.execute(
                delete(DevicePresenceModel).where(DevicePresenceModel.expires_at < _now() - _PURGE_AFTER)
            )
            self._db.commit()
        except Exception:
            self._db.rollback()


def device_id_for_request(user_sub: str, user_agent: Optional[str]) -> str:
    """Stable device key for activity-backed presence, where there is no socket
    to identify. Derived from the account plus the User-Agent so the same phone
    keeps refreshing one row instead of inserting a new one per upload, while
    two different phones on the same account stay apart."""
    digest = hashlib.sha1(f"{user_sub}|{user_agent or ''}".encode("utf-8")).hexdigest()
    return f"ua-{digest[:24]}"
