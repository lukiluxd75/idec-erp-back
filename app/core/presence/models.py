"""
ORM model backing the "phone connected" indicator (see PhoneConnectedBadge on
the frontend), shared by every domain that shows it.

Why a table and not a dict in memory: the badge used to be answered from a
per-process registry (`CapturesConnectionManager._connections`), but production
runs `--workers 4`. The phone's websocket is pinned to ONE of those four
processes, while `GET .../presence` is load-balanced per request, so three polls
out of four reported "not connected" and the badge flipped every few seconds
forever. Exactly the problem SqlCaptureStore already solved for the captures
themselves: the four processes share this Postgres, so they share this too.

Lives in the `public` schema, same criterion as `geoextraction_captures`: today
the whole real ERP database is there.

Not a business record: rows are heartbeats with a TTL, purged lazily (see
SqlPresenceStore). No soft delete, no updated_at.
"""
from sqlalchemy import Boolean, Column, DateTime, Index, String, text

from app.core.database.connection import Base


class DevicePresenceModel(Base):
    __tablename__ = "device_presence"

    # One row per (account, channel, device). `device_id` is the websocket's own
    # uuid for a socket-backed presence, or a stable key for an activity-backed
    # one (see SqlPresenceStore.touch_activity), so one account with the app on
    # two phones does not collapse into a single row.
    user_sub = Column(String(64), primary_key=True)
    channel = Column(String(40), primary_key=True)
    device_id = Column(String(64), primary_key=True)
    is_mobile = Column(Boolean, nullable=False)
    # Kept for diagnosis only ("when was this phone last heard from"); the
    # reader never filters on it.
    last_seen_at = Column(DateTime, nullable=False)
    # When this row stops counting as present. An absolute instant, not a TTL
    # applied at read time, for two reasons:
    #
    #  * each writer gets its own lifetime -- a websocket heartbeats every 25s
    #    and expires 70s out, while folder analysis' presence comes from bursts
    #    of HTTP uploads and needs minutes of slack. A single global TTL would
    #    have to lie about one of the two.
    #  * comparing a stored instant against now() is the same SQL on Postgres
    #    and on SQLite; `last_seen_at + interval` is not.
    #
    # It also means a worker killed mid-socket cannot pin the badge to
    # "connected": nothing refreshes the row and it expires on its own.
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_device_presence_expiry", "user_sub", "channel", "expires_at"),
    )


def ensure_schema(engine) -> None:
    """Pone al día una tabla `device_presence` que ya existía.

    `create_all()` solo crea tablas que faltan: nunca altera una que ya está.
    Esta tabla nació con el TTL calculado sobre `last_seen_at` y después pasó a
    `expires_at` (ver el comentario de la columna), así que toda instalación
    creada entre una versión y otra se quedó sin esa columna. El síntoma no es
    un error visible sino el peor posible: cada escritura de presencia falla con
    UndefinedColumn, el store la traga para no romper la subida de fotos, y el
    indicador "Celular conectado" se queda apagado para siempre.

    Mismo patrón que digitization/folder_analysis/resolutions usan para sus
    columnas añadidas: idempotente, y en una instalación nueva no hace nada.
    """
    with engine.begin() as conn:
        # ADD COLUMN pide ACCESS EXCLUSIVE y Postgres concede los locks por
        # orden de llegada, así que un ALTER esperando a un lector largo encola
        # a todos los demás detrás. Mejor rendirse: el llamador lo registra, el
        # backend arranca igual y se reintenta en el siguiente arranque.
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text("ALTER TABLE device_presence ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP"))
        # Las filas que venían de la versión anterior caducan en su último
        # latido: no se sabe nada mejor de ellas, y dar por conectado a un
        # celular del que no se sabe nada sería peor que darlo por ausente.
        conn.execute(text("UPDATE device_presence SET expires_at = last_seen_at WHERE expires_at IS NULL"))
        conn.execute(text("ALTER TABLE device_presence ALTER COLUMN expires_at SET NOT NULL"))
        # El índice se declaraba sobre last_seen_at y ahora cubre expires_at,
        # que es por donde filtra la lectura. Nombre nuevo para no depender de
        # que el viejo se recree.
        conn.execute(text("DROP INDEX IF EXISTS ix_device_presence_lookup"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_device_presence_expiry "
                "ON device_presence (user_sub, channel, expires_at)"
            )
        )
