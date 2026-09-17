"""Independent connection to catastro_operativo, the external Avalúos system's own DB.
Mostly read (queue, detail, photos); the only writes this domain ever makes here are the
two narrow status_id updates in SqlOperativoAppraisalRepository (mark_needs_correction /
mark_approved) — nothing else touches this connection with a commit.
"""
from functools import lru_cache
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class OperativoBase(DeclarativeBase):
    """Own declarative base — these models describe a foreign schema (Avalúos'), they are
    never registered in app.core.database.connection.init_db_tables."""


@lru_cache
def get_operativo_engine():
    return create_engine(settings.AVALUOS_SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)


@lru_cache
def get_operativo_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_operativo_engine(), autoflush=False, autocommit=False)


def get_operativo_db() -> Generator[Session, None, None]:
    session = get_operativo_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
