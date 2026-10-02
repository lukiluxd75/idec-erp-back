from datetime import date, datetime

from ..infrastructure import special_queries
from ..infrastructure.config import settings
from ..infrastructure.db import fetchall
from ..infrastructure.staff import pretty_name


def _fmt_dt(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)[:16]


def build_mass_forwarding_report(
    *,
    conn,
    start_date: date,
    end_date: date,
    max_minutes: int = 3,
    min_dispatches: int = 50,
    staff_name: str | None = None,
    staff_name_exact: bool = False,
) -> dict:
    unit_id = settings.reception_unit_id
    staff_sql, staff_params = special_queries.mass_forwarding_staff_sql(
        start_date, end_date, unit_id, max_minutes, min_dispatches
    )
    staff_rows = fetchall(staff_sql, staff_params, conn=conn)

    cases_sql, cases_params = special_queries.mass_forwarding_cases_sql(
        start_date,
        end_date,
        unit_id,
        max_minutes,
        staff_name,
        staff_name_exact=staff_name_exact,
    )
    case_rows = fetchall(cases_sql, cases_params, conn=conn)

    staff = []
    for row in staff_rows:
        dispatches = int(row.get("dispatches") or 0)
        rapid = int(row.get("rapidDispatches") or 0)
        pct = round(rapid / dispatches * 100, 1) if dispatches else 0.0
        avg_min = row.get("avgMinutes")
        staff.append(
            {
                "name": pretty_name(row.get("name") or ""),
                "dispatches": dispatches,
                "rapidDispatches": rapid,
                "rapidSharePct": pct,
                "avgMinutes": round(float(avg_min), 1) if avg_min is not None else None,
            }
        )

    cases = []
    for row in case_rows:
        cases.append(
            {
                "procedureNumber": row.get("procedureNumber"),
                "cadastralCode": row.get("cadastralCode"),
                "type": row.get("type"),
                "staffName": pretty_name(row.get("name") or ""),
                "receivedAt": _fmt_dt(row.get("receivedAt")),
                "completedAt": _fmt_dt(row.get("completedAt")),
                "minutes": int(row.get("minutes") or 0),
                "reason": (row.get("reason") or "").strip() or None,
            }
        )

    return {
        "meta": {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "unitId": unit_id,
            "unit": settings.reception_unit_name,
            "maxMinutes": max_minutes,
            "minDispatches": min_dispatches,
            "note": (
                "Las derivaciones en menos de {0} minutos no implican falta por sí solas; "
                "sirven para priorizar revisión de patrones de adelanto o favoritismo."
            ).format(max_minutes),
        },
        "staff": staff,
        "cases": cases,
    }
