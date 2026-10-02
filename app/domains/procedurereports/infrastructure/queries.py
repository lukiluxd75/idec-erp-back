from datetime import date, datetime, timedelta


def exclusive_end_datetime(end_date: date) -> datetime:
    return datetime.combine(end_date + timedelta(days=1), datetime.min.time())


def start_datetime(start_date: date) -> datetime:
    return datetime.combine(start_date, datetime.min.time())


def placeholders(n: int) -> str:
    return ",".join("?" * n)


def _procedure_type_join(procedure_type_ids: list[int] | None) -> tuple[str, list]:
    if not procedure_type_ids:
        return "", []
    ph = placeholders(len(procedure_type_ids))
    return (
        f"INNER JOIN seguimientoTramite sFiltro ON sFiltro.idTramite = d.idTramite "
        f"AND sFiltro.idTipoTramite IN ({ph})\n",
        list(procedure_type_ids),
    )


def ranking_sql(
    start_date: date, end_date: date, unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT d.idFuncionario,
       COUNT(d.idTramite) AS despachos,
       COUNT(DISTINCT d.idTramite) AS tramites
FROM detalleTramite d
{join}
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.idFuncionario IN ({ph})
GROUP BY d.idFuncionario
"""
    return sql, [*procedure_type_params, unit_id, start_datetime(start_date), exclusive_end_datetime(end_date), *staff_ids]


def pending_sql(unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT d.idFuncionario,
       COUNT(d.idTramite) AS pend
FROM detalleTramite d
{join}
WHERE d.idUnidad = ?
  AND d.fechaSalida IS NULL
  AND d.idFuncionario IN ({ph})
GROUP BY d.idFuncionario
"""
    return sql, [*procedure_type_params, unit_id, *staff_ids]


def team_daily_sql(
    start_date: date, end_date: date, unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT CONVERT(date, d.fechaSalida) AS dia,
       COUNT(*) AS despachos,
       COUNT(DISTINCT d.idTramite) AS tramites
FROM detalleTramite d
{join}
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.idFuncionario IN ({ph})
GROUP BY CONVERT(date, d.fechaSalida)
ORDER BY dia
"""
    return sql, [*procedure_type_params, unit_id, start_datetime(start_date), exclusive_end_datetime(end_date), *staff_ids]


def staff_daily_sql(
    start_date: date, end_date: date, unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT CONVERT(date, d.fechaSalida) AS dia,
       d.idFuncionario,
       COUNT(*) AS despachos
FROM detalleTramite d
{join}
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.idFuncionario IN ({ph})
GROUP BY CONVERT(date, d.fechaSalida), d.idFuncionario
ORDER BY dia
"""
    return sql, [*procedure_type_params, unit_id, start_datetime(start_date), exclusive_end_datetime(end_date), *staff_ids]


def totals_sql(
    start_date: date, end_date: date, unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT COUNT(*) AS despachos,
       COUNT(DISTINCT d.idTramite) AS tramites
FROM detalleTramite d
{join}
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.idFuncionario IN ({ph})
"""
    return sql, [*procedure_type_params, unit_id, start_datetime(start_date), exclusive_end_datetime(end_date), *staff_ids]


def by_type_sql(
    start_date: date, end_date: date, unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT s.idTipoTramite,
       tt.descripcion,
       COUNT(*) AS despachos,
       COUNT(DISTINCT d.idTramite) AS tramites
FROM detalleTramite d
{join}
INNER JOIN seguimientoTramite s ON s.idTramite = d.idTramite
LEFT JOIN tipoTramite tt ON tt.idTipoTramite = s.idTipoTramite
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.idFuncionario IN ({ph})
GROUP BY s.idTipoTramite, tt.descripcion
ORDER BY despachos DESC
"""
    return sql, [*procedure_type_params, unit_id, start_datetime(start_date), exclusive_end_datetime(end_date), *staff_ids]


def by_type_and_staff_sql(
    start_date: date, end_date: date, unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT d.idFuncionario,
       s.idTipoTramite,
       tt.descripcion,
       COUNT(*) AS despachos,
       COUNT(DISTINCT d.idTramite) AS tramites
FROM detalleTramite d
{join}
INNER JOIN seguimientoTramite s ON s.idTramite = d.idTramite
LEFT JOIN tipoTramite tt ON tt.idTipoTramite = s.idTipoTramite
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.idFuncionario IN ({ph})
GROUP BY d.idFuncionario, s.idTipoTramite, tt.descripcion
ORDER BY despachos DESC
"""
    return sql, [*procedure_type_params, unit_id, start_datetime(start_date), exclusive_end_datetime(end_date), *staff_ids]


def procedures_in_period_sql(
    start_date: date, end_date: date, unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT TOP 2500
       d.idTramite,
       s.nroTramite,
       s.gestionTramite,
       s.idTipoTramite,
       tt.descripcion AS tipo,
       s.codigoCatastral,
       d.idFuncionario,
       d.fechaIngreso,
       d.fechaSalida,
       'Despachado' AS estado
FROM detalleTramite d
{join}
INNER JOIN seguimientoTramite s ON s.idTramite = d.idTramite
LEFT JOIN tipoTramite tt ON tt.idTipoTramite = s.idTipoTramite
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.idFuncionario IN ({ph})
ORDER BY d.fechaSalida DESC
"""
    return sql, [*procedure_type_params, unit_id, start_datetime(start_date), exclusive_end_datetime(end_date), *staff_ids]


def pending_procedures_sql(
    unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT TOP 2500
       d.idTramite,
       s.nroTramite,
       s.gestionTramite,
       s.idTipoTramite,
       tt.descripcion AS tipo,
       s.codigoCatastral,
       d.idFuncionario,
       d.fechaIngreso,
       d.fechaSalida,
       'Pendiente' AS estado
FROM detalleTramite d
{join}
INNER JOIN seguimientoTramite s ON s.idTramite = d.idTramite
LEFT JOIN tipoTramite tt ON tt.idTipoTramite = s.idTipoTramite
WHERE d.idUnidad = ?
  AND d.fechaSalida IS NULL
  AND d.idFuncionario IN ({ph})
ORDER BY d.fechaIngreso DESC
"""
    return sql, [*procedure_type_params, unit_id, *staff_ids]


def sla_summary_sql(
    start_date: date, end_date: date, unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT AVG(CAST(DATEDIFF(day, d.fechaIngreso, d.fechaSalida) AS FLOAT)) AS avgDays,
       MIN(DATEDIFF(day, d.fechaIngreso, d.fechaSalida)) AS minDays,
       MAX(DATEDIFF(day, d.fechaIngreso, d.fechaSalida)) AS maxDays,
       COUNT(*) AS dispatches
FROM detalleTramite d
{join}
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.fechaIngreso IS NOT NULL
  AND d.idFuncionario IN ({ph})
"""
    return sql, [*procedure_type_params, unit_id, start_datetime(start_date), exclusive_end_datetime(end_date), *staff_ids]


def sla_by_type_sql(
    start_date: date, end_date: date, unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT s.idTipoTramite,
       tt.descripcion,
       AVG(CAST(DATEDIFF(day, d.fechaIngreso, d.fechaSalida) AS FLOAT)) AS avgDays,
       COUNT(*) AS dispatches
FROM detalleTramite d
{join}
INNER JOIN seguimientoTramite s ON s.idTramite = d.idTramite
LEFT JOIN tipoTramite tt ON tt.idTipoTramite = s.idTipoTramite
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.fechaIngreso IS NOT NULL
  AND d.idFuncionario IN ({ph})
GROUP BY s.idTipoTramite, tt.descripcion
ORDER BY avgDays DESC
"""
    return sql, [*procedure_type_params, unit_id, start_datetime(start_date), exclusive_end_datetime(end_date), *staff_ids]


def sla_by_staff_sql(
    start_date: date, end_date: date, unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None
) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT d.idFuncionario,
       AVG(CAST(DATEDIFF(day, d.fechaIngreso, d.fechaSalida) AS FLOAT)) AS avgDays,
       COUNT(*) AS dispatches
FROM detalleTramite d
{join}
WHERE d.idUnidad = ?
  AND d.fechaSalida >= ? AND d.fechaSalida < ?
  AND d.fechaIngreso IS NOT NULL
  AND d.idFuncionario IN ({ph})
GROUP BY d.idFuncionario
HAVING COUNT(*) >= 3
ORDER BY avgDays DESC
"""
    return sql, [*procedure_type_params, unit_id, start_datetime(start_date), exclusive_end_datetime(end_date), *staff_ids]


def backlog_aging_sql(unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT CASE
         WHEN DATEDIFF(day, d.fechaIngreso, GETDATE()) <= 7 THEN '0-7'
         WHEN DATEDIFF(day, d.fechaIngreso, GETDATE()) <= 15 THEN '8-15'
         WHEN DATEDIFF(day, d.fechaIngreso, GETDATE()) <= 30 THEN '16-30'
         WHEN DATEDIFF(day, d.fechaIngreso, GETDATE()) <= 60 THEN '31-60'
         ELSE '61+'
       END AS bucket,
       COUNT(*) AS count
FROM detalleTramite d
{join}
WHERE d.idUnidad = ?
  AND d.fechaSalida IS NULL
  AND d.fechaIngreso IS NOT NULL
  AND d.idFuncionario IN ({ph})
GROUP BY CASE
         WHEN DATEDIFF(day, d.fechaIngreso, GETDATE()) <= 7 THEN '0-7'
         WHEN DATEDIFF(day, d.fechaIngreso, GETDATE()) <= 15 THEN '8-15'
         WHEN DATEDIFF(day, d.fechaIngreso, GETDATE()) <= 30 THEN '16-30'
         WHEN DATEDIFF(day, d.fechaIngreso, GETDATE()) <= 60 THEN '31-60'
         ELSE '61+'
       END
"""
    return sql, [*procedure_type_params, unit_id, *staff_ids]


def critical_pending_sql(unit_id: int, staff_ids: list[int], procedure_type_ids: list[int] | None) -> tuple[str, list]:
    join, procedure_type_params = _procedure_type_join(procedure_type_ids)
    ph = placeholders(len(staff_ids))
    sql = f"""
SELECT TOP 25
       d.idTramite,
       s.nroTramite,
       s.gestionTramite,
       s.idTipoTramite,
       tt.descripcion AS tipo,
       s.codigoCatastral,
       d.idFuncionario,
       d.fechaIngreso,
       DATEDIFF(day, d.fechaIngreso, GETDATE()) AS ageDays
FROM detalleTramite d
{join}
INNER JOIN seguimientoTramite s ON s.idTramite = d.idTramite
LEFT JOIN tipoTramite tt ON tt.idTipoTramite = s.idTipoTramite
WHERE d.idUnidad = ?
  AND d.fechaSalida IS NULL
  AND d.fechaIngreso IS NOT NULL
  AND d.idFuncionario IN ({ph})
ORDER BY d.fechaIngreso ASC
"""
    return sql, [*procedure_type_params, unit_id, *staff_ids]
