from ..domain.services.procedure_types import DEFAULT_PROCEDURE_TYPES, PROCEDURE_TYPE_METADATA, procedure_type_color
from .config import settings
from .db import fetchall


def pretty_name(raw: str) -> str:
    parts = [p for p in (raw or "").replace(".", " ").split() if p]
    return " ".join(p[:1].upper() + p[1:].lower() for p in parts) or "Sin nombre"


def load_staff(district_id: int | None = None, *, conn=None) -> list[dict]:
    sql = """
SELECT f.idFuncionario,
       f.idPersona,
       f.idComuna,
       ISNULL(c.descripcion, 'SIN COMUNA') AS comuna,
       LTRIM(RTRIM(ISNULL(p.nombre,'') + ' ' + ISNULL(p.apellidoUno,'') + ' ' + ISNULL(p.apellidoDos,''))) AS nombre
FROM funcionario f
LEFT JOIN persona p ON p.idPersona = f.idPersona
LEFT JOIN comuna c ON c.idComuna = f.idComuna
WHERE f.idUnidad = ?
  AND f.estado = 'AC'
"""
    params: list = [settings.unit_id]
    if district_id:
        sql += " AND f.idComuna = ?"
        params.append(district_id)
    sql += " ORDER BY c.descripcion, nombre"
    rows = []
    for row in fetchall(sql, params, conn=conn):
        rows.append(
            {
                "staffId": int(row["staffId"]),
                "personId": int(row["personId"]) if row["personId"] is not None else int(row["staffId"]),
                "districtId": int(row["districtId"]) if row["districtId"] is not None else 0,
                "district": row["district"],
                "name": pretty_name(row["name"]),
            }
        )
    return rows


def load_districts(*, conn=None) -> list[dict]:
    rows = fetchall(
        """
SELECT f.idComuna,
       ISNULL(c.descripcion, 'SIN COMUNA') AS descripcion,
       COUNT(*) AS n
FROM funcionario f
LEFT JOIN comuna c ON c.idComuna = f.idComuna
WHERE f.idUnidad = ? AND f.estado = 'AC'
GROUP BY f.idComuna, c.descripcion
ORDER BY c.descripcion
""",
        [settings.unit_id],
        conn=conn,
    )
    return [
        {
            "districtId": int(r["districtId"]) if r["districtId"] is not None else 0,
            "description": r["description"],
            "count": int(r["count"]),
        }
        for r in rows
    ]


def load_procedure_types() -> list[dict]:
    return [
        {
            "procedureTypeId": procedure_type_id,
            "description": PROCEDURE_TYPE_METADATA[procedure_type_id]["label"],
            "label": PROCEDURE_TYPE_METADATA[procedure_type_id]["label"],
            "group": PROCEDURE_TYPE_METADATA[procedure_type_id]["group"],
            "shortLabel": PROCEDURE_TYPE_METADATA[procedure_type_id]["shortLabel"],
            "color": procedure_type_color(procedure_type_id),
        }
        for procedure_type_id in DEFAULT_PROCEDURE_TYPES
    ]
