from datetime import date

from .queries import exclusive_end_datetime, placeholders, start_datetime


STAFF_FULL_NAME_SQL = (
    "LTRIM(RTRIM(ISNULL(p.nombre,'') + ' ' + ISNULL(p.apellidoUno,'') + ' ' + ISNULL(p.apellidoDos,'')))"
)


def resolve_procedure_sql(procedure_number: int) -> tuple[str, list]:
    sql = """
SELECT TOP 1
       s.idTramite,
       s.nroTramite,
       s.gestionTramite,
       s.idTipoTramite,
       tt.descripcion AS tipo,
       s.codigoCatastral
FROM seguimientoTramite s
LEFT JOIN tipoTramite tt ON tt.idTipoTramite = s.idTipoTramite
WHERE s.nroTramite = ?
ORDER BY s.idTramite DESC
"""
    return sql, [procedure_number]


def procedure_trace_sql(procedure_id: int) -> tuple[str, list]:
    sql = """
SELECT d.idSecuencia,
       d.idUnidad,
       u.descripcion AS unidad,
       d.idFuncionario,
       LTRIM(RTRIM(ISNULL(p.nombre,'') + ' ' + ISNULL(p.apellidoUno,'') + ' ' + ISNULL(p.apellidoDos,''))) AS nombre,
       d.fechaIngreso,
       d.fechaSalida,
       d.motivo,
       d.nroTramo
FROM detalleTramite d
LEFT JOIN unidad u ON u.idUnidad = d.idUnidad
LEFT JOIN funcionario f ON f.idFuncionario = d.idFuncionario
LEFT JOIN persona p ON p.idPersona = f.idPersona
WHERE d.idTramite = ?
ORDER BY d.idSecuencia
"""
    return sql, [procedure_id]


def mass_forwarding_staff_sql(
    start_date: date,
    end_date: date,
    unit_id: int,
    max_minutes: int,
    min_dispatches: int,
) -> tuple[str, list]:
    sql = """
SELECT d.idFuncionario,
       LTRIM(RTRIM(ISNULL(p.nombre,'') + ' ' + ISNULL(p.apellidoUno,'') + ' ' + ISNULL(p.apellidoDos,''))) AS nombre,
       COUNT(*) AS despachos,
       SUM(CASE
             WHEN DATEDIFF(minute, d.fechaIngreso, d.fechaSalida) <= ?
             THEN 1 ELSE 0
           END) AS rapidos,
       AVG(CAST(DATEDIFF(minute, d.fechaIngreso, d.fechaSalida) AS FLOAT)) AS avgMin
FROM detalleTramite d
LEFT JOIN funcionario f ON f.idFuncionario = d.idFuncionario
LEFT JOIN persona p ON p.idPersona = f.idPersona
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.fechaIngreso IS NOT NULL
  AND d.fechaSalida IS NOT NULL
GROUP BY d.idFuncionario,
         LTRIM(RTRIM(ISNULL(p.nombre,'') + ' ' + ISNULL(p.apellidoUno,'') + ' ' + ISNULL(p.apellidoDos,'')))
HAVING COUNT(*) >= ?
ORDER BY rapidos DESC, despachos DESC
"""
    return sql, [
        max_minutes,
        unit_id,
        start_datetime(start_date),
        exclusive_end_datetime(end_date),
        min_dispatches,
    ]


def mass_forwarding_cases_sql(
    start_date: date,
    end_date: date,
    unit_id: int,
    max_minutes: int,
    staff_name: str | None,
    *,
    staff_name_exact: bool = False,
    limit: int = 150,
) -> tuple[str, list]:
    staff_filter = ""
    params: list = [
        unit_id,
        start_datetime(start_date),
        exclusive_end_datetime(end_date),
        max_minutes,
    ]
    if staff_name and staff_name.strip():
        if staff_name_exact:
            staff_filter = f" AND {STAFF_FULL_NAME_SQL} = ?"
            params.append(staff_name.strip())
        else:
            staff_filter = f" AND {STAFF_FULL_NAME_SQL} LIKE ?"
            params.append(f"%{staff_name.strip()}%")
    sql = f"""
SELECT TOP {int(limit)}
       d.idTramite,
       s.nroTramite,
       s.gestionTramite,
       s.codigoCatastral,
       tt.descripcion AS tipo,
       d.idFuncionario,
       LTRIM(RTRIM(ISNULL(p.nombre,'') + ' ' + ISNULL(p.apellidoUno,'') + ' ' + ISNULL(p.apellidoDos,''))) AS nombre,
       d.fechaIngreso,
       d.fechaSalida,
       DATEDIFF(minute, d.fechaIngreso, d.fechaSalida) AS minutos,
       d.motivo
FROM detalleTramite d
INNER JOIN seguimientoTramite s ON s.idTramite = d.idTramite
LEFT JOIN tipoTramite tt ON tt.idTipoTramite = s.idTipoTramite
LEFT JOIN funcionario f ON f.idFuncionario = d.idFuncionario
LEFT JOIN persona p ON p.idPersona = f.idPersona
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.fechaIngreso IS NOT NULL
  AND DATEDIFF(minute, d.fechaIngreso, d.fechaSalida) <= ?
  {staff_filter}
ORDER BY minutos ASC, d.fechaSalida DESC
"""
    return sql, params
