from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from app.core.config import settings

# Motor de conexión a PostgreSQL / SQLite
db_uri = settings.SQLALCHEMY_DATABASE_URI
if db_uri.startswith("sqlite"):
    engine = create_engine(
        db_uri,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        db_uri,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

# Fábrica de sesiones de base de datos
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Clase base declarativa para los modelos ORM
Base = declarative_base()


def init_db_tables() -> bool:
    """
    Inicializa automáticamente las tablas de la base de datos si no existen.
    """
    try:
        from app.domains.seguridad.infrastructure import models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        return True
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").warning(f"Aviso al inicializar tablas en la BD: {exc}")
        return False


def get_db() -> Generator[Session, None, None]:
    """
    Generador de sesión de base de datos para inyección de dependencias en FastAPI.
    Garantiza el cierre adecuado de la conexión al finalizar la petición.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
