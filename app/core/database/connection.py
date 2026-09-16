from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
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
        # The 'resolutions' domain is NOT registered here: its schema (`resolutions`)
        # already exists with real data from the mobile app — see
        # app/domains/resolutions/infrastructure/models.py.
        from app.domains.geoextraction.infrastructure import models  # noqa: F401
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
