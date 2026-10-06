import logging
from typing import Generator
from sqlalchemy import create_engine, event
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
    # Guards asked of the server for every connection this app opens.
    _SERVER_GUARDS = (
        f"idle_in_transaction_session_timeout={settings.DB_IDLE_IN_TRANSACTION_TIMEOUT_MS}",
        f"lock_timeout={settings.DB_LOCK_TIMEOUT_MS}",
    )
    engine = create_engine(
        db_uri,
        pool_recycle=3600,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_POOL_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
        connect_args={
            "connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS,
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
        from app.core.presence import models as presence_models  # noqa: F401
        from app.domains.security.infrastructure import models  # noqa: F401
        from app.domains.resolutions.infrastructure import plan_page_models  # noqa: F401
        from app.domains.geoextraction.infrastructure import models  # noqa: F401
        from app.domains.chatbot.infrastructure import models as chatbot_models  # noqa: F401
        from app.domains.folios.infrastructure import models as folios_models  # noqa: F401
        from app.domains.cite.infrastructure import models as cite_models  # noqa: F401
        from app.domains.templates.infrastructure import models as templates_models  # noqa: F401

        if not db_uri.startswith("sqlite"):
            # create_all() only creates tables, never the Postgres schema itself.
            with engine.begin() as conn:
                conn.execute(CreateSchema(chatbot_models.SCHEMA, if_not_exists=True))
                conn.execute(CreateSchema(folios_models.SCHEMA, if_not_exists=True))
                conn.execute(CreateSchema(templates_models.SCHEMA, if_not_exists=True))

        Base.metadata.create_all(bind=engine)

        if not db_uri.startswith("sqlite"):
            # create_all() no altera tablas existentes, y a `device_presence` le cambió una columna después de su primera versión.
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