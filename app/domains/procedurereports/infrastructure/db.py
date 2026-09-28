from contextlib import contextmanager

import pyodbc

from .config import settings

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
}


def connection_string() -> str:
    if not all((settings.db_server, settings.db_name, settings.db_user, settings.db_password)):
        raise RuntimeError("Configura DB_SERVER, DB_NAME, DB_USER y DB_PASSWORD en el .env del backend.")
    return (
        f"DRIVER={{{settings.db_driver}}};"
        f"SERVER={settings.db_server};"
        f"DATABASE={settings.db_name};"
        f"UID={settings.db_user};"
        f"PWD={settings.db_password};"
        "TrustServerCertificate=yes;"
        "Encrypt=no;"
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
