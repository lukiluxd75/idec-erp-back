from contextlib import contextmanager

import pyodbc

from .config import settings
from .odbc_connection import build_reports_connection_string

# Translate historical SQL Server column names at the database boundary.
SQL_COLUMN_NAMES = {
    "idFuncionario": "staffId", "idPersona": "personId", "idComuna": "districtId",
    "idTramite": "procedureId", "nroTramite": "procedureNumber",
    "gestionTramite": "procedureYear", "idTipoTramite": "procedureTypeId",
    "codigoCatastral": "cadastralCode", "fechaIngreso": "receivedAt",
    "fechaSalida": "completedAt", "comuna": "district", "nombre": "name",
    "descripcion": "description", "n": "count", "despachos": "dispatches",
    "tramites": "procedures", "pend": "pending", "dia": "date",
    "tipo": "type", "estado": "status",
    "avgDays": "avgDays", "minDays": "minDays", "maxDays": "maxDays",
    "ageDays": "ageDays", "bucket": "bucket",
}


def connection_string() -> str:
    if not all((settings.db_server, settings.db_name, settings.db_user, settings.db_password)):
        raise RuntimeError(
            "Configura REPORTS_DB_SERVER, REPORTS_DB_NAME, REPORTS_DB_USER y REPORTS_DB_PASSWORD en el .env del backend."
        )
    return build_reports_connection_string(
        server=settings.db_server,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        driver=settings.db_driver,
        tds_version=settings.db_tds_version,
        encrypt=settings.db_encrypt,
    )


@contextmanager
def get_connection():
    conn = pyodbc.connect(connection_string(), timeout=20)
    try:
        yield conn
    finally:
        conn.close()


def fetchall(sql: str, params: tuple | list = ()):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        columns = [SQL_COLUMN_NAMES.get(col[0], col[0]) for col in cur.description]
        rows = []
        for row in cur.fetchall():
            rows.append(dict(zip(columns, row)))
        return rows
