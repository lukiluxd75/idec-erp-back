from typing import Generator
from sqlalchemy import create_engine
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
    engine = create_engine(
        db_uri,
        # No pool_pre_ping: the DB (172.16.66.103) is ~120ms away, and pre_ping
        # adds a full round trip to EVERY checkout from the pool -- i.e. to every
        # single DB-touching request, all the time. pool_recycle already discards
        # connections older than an hour, which is enough given how often this
        # app hits the DB (polling every 10s on some pages) to keep connections
        # from going stale between uses.
        pool_recycle=3600,
    )

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
        from app.domains.cite.infrastructure import models as cite_models  # noqa: F401
        from app.domains.templates.infrastructure import models as templates_models  # noqa: F401

        if not db_uri.startswith("sqlite"):
            # create_all() only creates tables, never the Postgres schema itself.
            # Unlike 'resolutions'/'detection', 'chatbot' and 'folios' own their
            # schemas outright (nothing external creates them), so it has to happen here.
            with engine.begin() as conn:
                conn.execute(CreateSchema(chatbot_models.SCHEMA, if_not_exists=True))
                conn.execute(CreateSchema(folios_models.SCHEMA, if_not_exists=True))
                conn.execute(CreateSchema(templates_models.SCHEMA, if_not_exists=True))
        Base.metadata.create_all(bind=engine)
        return True
    except Exception as exc:
        import logging
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
