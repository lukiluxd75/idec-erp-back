import time
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
    "unidad": "unitName", "motivo": "reason", "avgMin": "avgMinutes",
    "rapidos": "rapidDispatches", "minutos": "minutes",
    "idSecuencia": "sequenceId", "nroTramo": "legNumber",
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


def _connect_with_retry(*, attempts: int = 3, timeout: int = 25) -> pyodbc.Connection:
    last: pyodbc.Error | None = None
    for attempt in range(attempts):
        try:
            return pyodbc.connect(connection_string(), timeout=timeout)
        except pyodbc.Error as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.35 * (attempt + 1))
    assert last is not None
    raise last


@contextmanager
def get_connection():
    conn = _connect_with_retry()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def report_session():
    """One ODBC connection for a full report request (many queries, single connect)."""
    conn = _connect_with_retry()
    try:
        yield conn
    finally:
        conn.close()


def _fetchall_on_connection(conn: pyodbc.Connection, sql: str, params: tuple | list) -> list[dict]:
    cur = conn.cursor()
    cur.execute(sql, params)
    columns = [SQL_COLUMN_NAMES.get(col[0], col[0]) for col in cur.description]
    rows = []
    for row in cur.fetchall():
        rows.append(dict(zip(columns, row)))
    return rows


def fetchall(sql: str, params: tuple | list = (), conn: pyodbc.Connection | None = None):
    if conn is not None:
        return _fetchall_on_connection(conn, sql, params)
    with get_connection() as session:
        return _fetchall_on_connection(session, sql, params)
