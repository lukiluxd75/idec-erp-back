"""ORM model for `resolutions.resolution_plan_pages` — UNLIKE
`infrastructure/models.py` (which only mirrors the mobile-owned
`resolutions`/`resolution_pages` tables and must never create them, see its
own docstring), this table is new functionality introduced by the ERP itself
(floor-plan photos for working out colindancias, added 2026-09) and this
backend DOES own and create it — see its explicit import in
app.core.database.connection.init_db_tables. It lives in the same `resolutions`
Postgres schema (already created externally) for locality with the rest of
the domain's data, with a plain string `resolution_id` (no DB-level FK) so
`create_all()` never needs to know about the mobile-owned table.
"""
from sqlalchemy import JSON, Column, DateTime, Integer, LargeBinary, String, text
from sqlalchemy.engine import Engine

from app.core.database.connection import Base


class ResolutionPlanPageModel(Base):
    __tablename__ = "resolution_plan_pages"
    __table_args__ = {"schema": "resolutions"}

    plan_page_id = Column(String(36), primary_key=True)
    resolution_id = Column(String(36), nullable=False, index=True)
    order_index = Column(Integer, nullable=False)
    planta = Column(String(60), nullable=False)
    # Todas las plantas de la hoja (JSON list): varias en "PLANTA TIPO 2° - 4° PISO".
    plantas = Column(JSON)
    # Cómo se asignó: ver domain.entities.resolution.PlantaStatus.
    planta_status = Column(String(20), nullable=False, server_default=text("'manual'"))
    planta_title = Column(String(200))
    planta_detection = Column(JSON)
    mime = Column(String(40), nullable=False)
    file_name = Column(String)
    image = Column(LargeBinary, nullable=False)
    source = Column(String(10), nullable=False, server_default=text("'app'"))
    created_at = Column(DateTime, nullable=False, server_default=text("now()"))


_ADDED_COLUMNS = (
    "plantas JSON",
    "planta_status VARCHAR(20) NOT NULL DEFAULT 'manual'",
    "planta_title VARCHAR(200)",
    "planta_detection JSON",
)


def ensure_added_columns(engine: Engine) -> None:
    """Agrega las columnas de _ADDED_COLUMNS que falten, y solo esas.

    `ADD COLUMN IF NOT EXISTS` toma un ACCESS EXCLUSIVE sobre la tabla aunque la
    columna ya exista, asi que sin este chequeo previo cada arranque peleaba por
    un lock que no necesitaba: basta una consulta en curso sobre
    resolution_plan_pages para que el lock_timeout lo cancele y el arranque
    termine con un WARNING que no significa nada. Despues del primer deploy no
    falta ninguna columna y esta funcion no toca la tabla.
    """
    schema = ResolutionPlanPageModel.__table_args__["schema"]
    table = ResolutionPlanPageModel.__tablename__
    with engine.begin() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = :table"
                ),
                {"schema": schema, "table": table},
            )
        }
        missing = [column for column in _ADDED_COLUMNS if column.split()[0] not in existing]
        if not missing:
            return
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        for column in missing:
            conn.execute(
                text(f"ALTER TABLE {schema}.{table} ADD COLUMN IF NOT EXISTS {column}")
            )
