import logging
from typing import Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.schema import CreateSchema
from app.core.config import settings

# PostgreSQL / SQLite connection engine
db_uri = settings.SQLALCHEMY_DATABASE_URI
if db_uri.startswith("sqlite"):
    engine = create_engine(
        db_uri,
        connect_args={"check_same_thread": False},
    )
else:
    # Guards asked of the server for every connection this app opens. They live
    # here rather than in ALTER DATABASE so they are versioned with the code and
    # bind only this app, leaving the other databases on the shared server alone.
    # They are applied on the "connect" event below, not as libpq startup
    # `options`: a connection pooler sits in front of this database and rejects
    # that parameter ("Unsupported startup parameter: options"). It pools by
    # session, so a plain SET holds for the life of the connection.
    _SERVER_GUARDS = (
        # A transaction left open holds its locks, and Postgres grants locks in
        # arrival order: one forgotten transaction is enough to queue every later
        # query on that table behind it, which is how this database once stopped
        # answering while the rest of the server was fine. Ten minutes is far above
        # any real request -- the longest legitimate chain is folios (90s OCR +
        # 120s LLM) and chatbot (60s embedding + 180s vision) -- so this only ever
        # reaches an abandoned one. Tighten it once those domains release the
        # session before their slow call, the way digitization now does.
        f"idle_in_transaction_session_timeout={settings.DB_IDLE_IN_TRANSACTION_TIMEOUT_MS}",
        # Nothing waits forever for a lock: a statement that cannot get one fails
        # and frees its connection instead of adding to the queue behind it.
        f"lock_timeout={settings.DB_LOCK_TIMEOUT_MS}",
    )
    engine = create_engine(
        db_uri,
        # No pool_pre_ping: the DB (172.16.66.103) is ~120ms away, and pre_ping
        # adds a full round trip to EVERY checkout from the pool -- i.e. to every
        # single DB-touching request, all the time. pool_recycle already discards
        # connections older than an hour, which is enough given how often this
        # app hits the DB (polling every 10s on some pages) to keep connections
        # from going stale between uses.
        pool_recycle=3600,
        # Bounded and explicit, so the ceiling this app can put on a shared server
        # is predictable: processes x (size + overflow), against max_connections.
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_POOL_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
        connect_args={
            "connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS,
            # Without keepalives the server cannot tell a client that died from one
            # that is merely quiet: it waits in ClientRead forever, holding whatever
            # locks that transaction took. That is exactly how a killed backend left
            # this table unusable for the better part of an hour. These make the
            # kernel notice a gone client in about a minute and roll it back.
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )

    @event.listens_for(engine, "connect")
    def _apply_server_guards(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            for guard in _SERVER_GUARDS:
                name, value = guard.split("=", 1)
                cursor.execute(f"SET {name} = {value}")
        finally:
            cursor.close()
        dbapi_connection.commit()

# Database session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Declarative base class for ORM models
Base = declarative_base()


def init_db_tables() -> bool:
    """
    Automatically create database tables if they do not exist.
    """
    try:
        # Shared "phone connected" presence (app/core/presence): one table in
        # `public`, used by geoextraction, resolutions and folder analysis.
        from app.core.presence import models as presence_models  # noqa: F401
        from app.domains.security.infrastructure import models  # noqa: F401
        # The 'resolutions' domain's MIRRORED models (resolutions/resolution_pages,
        # owned by the mobile app) are deliberately NOT imported here — see
        # app/domains/resolutions/infrastructure/models.py. `plan_page_models` is
        # different: it's a table the ERP itself owns (added 2026-09, floor-plan
        # photos for colindancias), living in the same already-existing
        # `resolutions` schema, so it IS registered for create_all() below.
        from app.domains.resolutions.infrastructure import plan_page_models  # noqa: F401
        from app.domains.geoextraction.infrastructure import models  # noqa: F401
        from app.domains.chatbot.infrastructure import models as chatbot_models  # noqa: F401
        from app.domains.folios.infrastructure import models as folios_models  # noqa: F401
        from app.domains.cadastralviewer.infrastructure import models as cadastralviewer_models  # noqa: F401
        from app.domains.cite.infrastructure import models as cite_models  # noqa: F401
        from app.domains.templates.infrastructure import models as templates_models  # noqa: F401

        if not db_uri.startswith("sqlite"):
            # create_all() only creates tables, never the Postgres schema itself.
            # Unlike 'resolutions'/'detection', 'chatbot', 'folios', 'cadastralviewer' and 'templates' own their
            # schemas outright (nothing external creates them), so it has to happen here.
            with engine.begin() as conn:
                conn.execute(CreateSchema(chatbot_models.SCHEMA, if_not_exists=True))
                conn.execute(CreateSchema(folios_models.SCHEMA, if_not_exists=True))
                conn.execute(CreateSchema(cadastralviewer_models.SCHEMA, if_not_exists=True))
                conn.execute(CreateSchema(templates_models.SCHEMA, if_not_exists=True))
                conn.execute(text("DROP INDEX IF EXISTS cadastralviewer.ux_advertisement_one_active"))
        Base.metadata.create_all(bind=engine)

        if not db_uri.startswith("sqlite"):
            # create_all() no altera tablas existentes, y a `device_presence` le
            # cambió una columna después de su primera versión. Se registra
            # aparte y con nivel error: si esto falla, el indicador "Celular
            # conectado" queda apagado en silencio, que es muy difícil de
            # diagnosticar desde la pantalla.
            try:
                presence_models.ensure_schema(engine)
            except Exception as exc:
                logging.getLogger("uvicorn.error").error(
                    "No se pudo poner al dia la tabla device_presence: %s. "
                    "El indicador 'Celular conectado' quedara apagado hasta que se resuelva.",
                    exc,
                    exc_info=True,
                )
        return True
    except Exception as exc:
        logging.getLogger("uvicorn.error").warning(f"Aviso al inicializar tablas en la BD: {exc}")
        return False


def get_db() -> Generator[Session, None, None]:
    """
    Database session generator for FastAPI dependency injection.
    Ensures the connection is closed properly when the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()