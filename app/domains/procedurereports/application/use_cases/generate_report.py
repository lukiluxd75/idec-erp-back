from datetime import date, datetime, timedelta

from ..analysis import build_analysis
from ..executive_metrics import (
    aggregate_district_comparison,
    aggregate_procedure_groups,
    build_period_comparison,
    build_sla_summary_row,
    normalize_backlog_aging,
    previous_period,
)
from ...domain.services.procedure_types import PALETTE, color_at, procedure_type_color, procedure_type_label, procedure_type_group
from ...domain.entities.report_context import ReportContext
from ...domain.ports.report_repository import ReportRepository

SPANISH_WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _as_int(v) -> int:
    return int(v or 0)


def _as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _fmt_dt(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)[:16]


def _label(d: date) -> str:
    return f"{SPANISH_WEEKDAYS[d.weekday()]} {d.day}"


def _day_type(d: date) -> str:
    return "weekend" if d.weekday() >= 5 else "weekday"


def _empty_report(start_date: date, end_date: date, district_id: int | None, district_label: str, procedure_type_ids: list[int] | None, context: ReportContext) -> dict:
    kpis = {
        "dispatches": 0,
        "procedures": 0,
        "workingDays": 0,
        "avgTeamPerDay": 0.0,
        "pendingCount": 0,
        "pendingWithoutOutliers": 0,
        "coreAvgPerDay": 0.0,
        "idleWorkdays": [],
        "weekdayDispatches": 0,
        "staffCount": 0,
    }
    return {
        "meta": {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "unitId": context.unit_id,
            "unit": context.unit_name,
            "districtId": district_id,
            "district": district_label,
            "procedureTypes": procedure_type_ids or [],
            "server": context.server,
            "database": context.database,
            "source": "sqlserver",
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
        },
        "kpis": kpis,
        "ranking": [],
        "teamDaily": [],
        "staffDaily": [],
        "byType": [],
        "byTypeAndStaff": [],
        "typeStaffMatrix": {"columns": [], "rows": []},
        "procedures": [],
        "colors": {},
        "sla": {"summary": build_sla_summary_row(None), "byType": [], "byStaff": []},
        "backlogAging": [],
        "criticalPending": [],
        "procedureGroups": [],
        "districtComparison": [],
        "periodComparison": None,
        "analysis": {
            "backlog": "No hay funcionarios activos en el filtro.",
            "outliers": [],
            "executiveHeadline": "Sin datos para el filtro seleccionado.",
            "executiveBullets": [],
        },
    }


def _build_metrics(ranking: list[dict], team_daily: list[dict], start_date: date, end_date: date, dispatches: int, procedures: int) -> dict:
    pending = sum(r["pending"] for r in ranking)
    outliers = [r for r in ranking if pending and r["pending"] >= max(80, pending * 0.35)]
    pend_out = sum(r["pending"] for r in outliers)
    working_days = [d for d in team_daily if d["type"] == "weekday"]
    weekday_desp = sum(d["dispatches"] for d in working_days)
    working_days_count = len(working_days)
    average = round(weekday_desp / working_days_count, 1) if working_days_count else 0.0
    threshold = ranking[0]["dispatches"] * 0.7 if ranking and ranking[0]["dispatches"] else 0
    core_staff = [r for r in ranking if r["dispatches"] >= threshold]
    core_average = (
        round(sum(r["dispatches"] for r in core_staff) / len(core_staff) / working_days_count, 1)
        if core_staff and working_days_count
        else 0.0
    )
    idle_days = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            hit = next((d for d in team_daily if d["date"] == cursor.isoformat()), None)
            if not hit:
                idle_days.append(_label(cursor))
        cursor += timedelta(days=1)
    return {
        "dispatches": dispatches,
        "procedures": procedures,
        "workingDays": working_days_count,
        "avgTeamPerDay": average,
        "pendingCount": pending,
        "pendingWithoutOutliers": pending - pend_out,
        "coreAvgPerDay": core_average,
        "idleWorkdays": idle_days,
        "weekdayDispatches": weekday_desp,
        "staffCount": len(ranking),
    }


def _procedure_row(row: dict, staff_by_id: dict) -> dict | None:
    s = staff_by_id.get(_as_int(row["staffId"]))
    if not s:
        return None
    return {
        "procedureId": _as_int(row["procedureId"]),
        "procedureNumber": _as_int(row["procedureNumber"]) if row.get("procedureNumber") is not None else None,
        "year": _as_int(row["procedureYear"]) if row.get("procedureYear") is not None else None,
        "procedureTypeId": _as_int(row["procedureTypeId"]) if row.get("procedureTypeId") is not None else None,
        "type": row.get("type") or "",
        "cadastralCode": (row.get("cadastralCode") or "").strip(),
        "name": s["name"],
        "district": s["district"],
        "receivedAt": _fmt_dt(row.get("receivedAt")),
        "completedAt": _fmt_dt(row.get("completedAt")),
        "status": row.get("status") or "",
        "color": "",
    }


def _type_staff_matrix(ranking: list[dict], by_type: list[dict], by_type_and_staff: list[dict]) -> dict:
    columns = [
        {"procedureTypeId": t["procedureTypeId"], "description": t["description"]}
        for t in by_type
        if t.get("dispatches")
    ]
    lookup: dict[tuple[str, int], int] = {}
    for row in by_type_and_staff:
        lookup[(row["name"], row["procedureTypeId"])] = row["dispatches"]
    rows = []
    for r in ranking:
        if not r["dispatches"]:
            continue
        rows.append(
            {
                "name": r["name"],
                "values": [lookup.get((r["name"], c["procedureTypeId"])) for c in columns],
            }
        )
    return {"columns": columns, "rows": rows}


def generate_report(
    start_date: date,
    end_date: date,
    district_id: int | None = None,
    procedure_type_ids: list[int] | None = None,
    include_details: bool = False,
    *,
    repository: ReportRepository,
    context: ReportContext,
) -> dict:
    if end_date < start_date:
        raise ValueError("La fecha hasta no puede ser menor que desde.")

    procedure_types = list(dict.fromkeys(procedure_type_ids or []))
    staff = repository.load_staff(district_id)
    if not staff:
        return _empty_report(start_date, end_date, district_id, "sin comuna", procedure_types, context)

    staff_by_id = {s["staffId"]: s for s in staff}
    staff_ids = list(staff_by_id.keys())
    districts = sorted({s["district"] for s in staff})
    district_label = districts[0] if len(districts) == 1 else "Todas las comunas"

    by_person: dict[int, dict] = {}
    for s in staff:
        item = by_person.setdefault(
            s["personId"],
            {
                "name": s["name"],
                "district": s["district"],
                "dispatches": 0,
                "procedures": 0,
                "days": 0,
                "pending": 0,
            },
        )
        item["_ids"] = item.get("_ids", []) + [s["staffId"]]
    for row in repository.query("ranking", start_date, end_date, context.unit_id, staff_ids, procedure_types or None):
        s = staff_by_id.get(_as_int(row["staffId"]))
        if not s:
            continue
        item = by_person[s["personId"]]
        item["dispatches"] += _as_int(row["dispatches"])
        item["procedures"] += _as_int(row["procedures"])
    for row in repository.query("pending", start_date, end_date, context.unit_id, staff_ids, procedure_types or None):
        s = staff_by_id.get(_as_int(row["staffId"]))
        if not s:
            continue
        item = by_person[s["personId"]]
        item["pending"] += _as_int(row["pending"])
    team_daily = []
    for row in repository.query("team_daily", start_date, end_date, context.unit_id, staff_ids, procedure_types or None):
        d = _as_date(row["date"])
        team_daily.append(
            {
                "date": d.isoformat(),
                "label": _label(d),
                "dispatches": _as_int(row["dispatches"]),
                "procedures": _as_int(row["procedures"]),
                "type": _day_type(d),
            }
        )
    totals = repository.query("totals", start_date, end_date, context.unit_id, staff_ids, procedure_types or None)[0]
    daily_totals: dict[tuple[str, str], int] = {}
    staff_days: dict[int, set[str]] = {}
    for row in repository.query("staff_daily", start_date, end_date, context.unit_id, staff_ids, procedure_types or None):
        s = staff_by_id.get(_as_int(row["staffId"]))
        if not s:
            continue
        d = _as_date(row["date"]).isoformat()
        key = (s["name"], d)
        daily_totals[key] = daily_totals.get(key, 0) + _as_int(row["dispatches"])
        staff_days.setdefault(s["personId"], set()).add(d)

    for person_id, item in by_person.items():
        item["days"] = len(staff_days.get(person_id, set()))
        item.pop("_ids", None)

    ranking = sorted(by_person.values(), key=lambda r: (-r["dispatches"], r["name"]))
    colors_by_staff = {row["name"]: color_at(i) for i, row in enumerate(ranking)}
    for row in ranking:
        row["color"] = colors_by_staff[row["name"]]

    staff_daily = [
        {"name": n, "date": d, "dispatches": v, "color": colors_by_staff.get(n, PALETTE[0])}
        for (n, d), v in sorted(daily_totals.items(), key=lambda x: (x[0][1], x[0][0]))
    ]
    by_type = []
    for row in repository.query("by_type", start_date, end_date, context.unit_id, staff_ids, procedure_types or None):
        procedure_type_id = _as_int(row["procedureTypeId"])
        by_type.append(
            {
                "procedureTypeId": procedure_type_id,
                "description": procedure_type_label(procedure_type_id, row["description"] or ""),
                "group": procedure_type_group(procedure_type_id),
                "dispatches": _as_int(row["dispatches"]),
                "procedures": _as_int(row["procedures"]),
                "color": procedure_type_color(procedure_type_id),
            }
        )
    by_type_and_staff = []
    for row in repository.query("by_type_and_staff", start_date, end_date, context.unit_id, staff_ids, procedure_types or None):
        s = staff_by_id.get(_as_int(row["staffId"]))
        if not s:
            continue
        procedure_type_id = _as_int(row["procedureTypeId"])
        by_type_and_staff.append(
            {
                "name": s["name"],
                "district": s["district"],
                "color": colors_by_staff.get(s["name"], PALETTE[0]),
                "procedureTypeId": procedure_type_id,
                "type": procedure_type_label(procedure_type_id, row["description"] or ""),
                "group": procedure_type_group(procedure_type_id),
                "typeColor": procedure_type_color(procedure_type_id),
                "dispatches": _as_int(row["dispatches"]),
                "procedures": _as_int(row["procedures"]),
            }
        )

    procedures: list[dict] = []
    if include_details:
        if procedure_types:
            for row in repository.query("pending_procedures", start_date, end_date, context.unit_id, staff_ids, procedure_types):
                item = _procedure_row(row, staff_by_id)
                if item:
                    item["type"] = procedure_type_label(item["procedureTypeId"] or 0, item["type"])
                    item["color"] = colors_by_staff.get(item["name"], PALETTE[0])
                    procedures.append(item)
        for row in repository.query("procedures_in_period", start_date, end_date, context.unit_id, staff_ids, procedure_types or None):
            item = _procedure_row(row, staff_by_id)
            if item:
                item["type"] = procedure_type_label(item["procedureTypeId"] or 0, item["type"])
                item["color"] = colors_by_staff.get(item["name"], PALETTE[0])
                procedures.append(item)

    dispatches_total = _as_int(totals["dispatches"])
    procedures_total = _as_int(totals["procedures"])
    kpis = _build_metrics(
        ranking,
        team_daily,
        start_date,
        end_date,
        dispatches=dispatches_total,
        procedures=procedures_total,
    )

    sla_rows = repository.query("sla_summary", start_date, end_date, context.unit_id, staff_ids, procedure_types or None)
    sla_summary = build_sla_summary_row(sla_rows[0] if sla_rows else None)
    sla_by_type = []
    for row in repository.query("sla_by_type", start_date, end_date, context.unit_id, staff_ids, procedure_types or None):
        procedure_type_id = _as_int(row["procedureTypeId"])
        avg_days = row.get("avgDays")
        sla_by_type.append(
            {
                "procedureTypeId": procedure_type_id,
                "description": procedure_type_label(procedure_type_id, row.get("description") or ""),
                "group": procedure_type_group(procedure_type_id),
                "avgDays": round(float(avg_days), 1) if avg_days is not None else None,
                "dispatches": _as_int(row.get("dispatches")),
                "color": procedure_type_color(procedure_type_id),
            }
        )
    sla_by_staff = []
    for row in repository.query("sla_by_staff", start_date, end_date, context.unit_id, staff_ids, procedure_types or None):
        s = staff_by_id.get(_as_int(row["staffId"]))
        if not s:
            continue
        avg_days = row.get("avgDays")
        sla_by_staff.append(
            {
                "name": s["name"],
                "district": s["district"],
                "color": colors_by_staff.get(s["name"], PALETTE[0]),
                "avgDays": round(float(avg_days), 1) if avg_days is not None else None,
                "dispatches": _as_int(row.get("dispatches")),
            }
        )

    aging_raw = repository.query("backlog_aging", start_date, end_date, context.unit_id, staff_ids, procedure_types or None)
    backlog_aging = normalize_backlog_aging(aging_raw, kpis["pendingCount"])

    critical_pending = []
    for row in repository.query("critical_pending", start_date, end_date, context.unit_id, staff_ids, procedure_types or None):
        s = staff_by_id.get(_as_int(row["staffId"]))
        if not s:
            continue
        procedure_type_id = _as_int(row["procedureTypeId"]) if row.get("procedureTypeId") is not None else None
        critical_pending.append(
            {
                "procedureId": _as_int(row["procedureId"]),
                "procedureNumber": _as_int(row["procedureNumber"]) if row.get("procedureNumber") is not None else None,
                "year": _as_int(row["procedureYear"]) if row.get("procedureYear") is not None else None,
                "procedureTypeId": procedure_type_id,
                "type": procedure_type_label(procedure_type_id or 0, row.get("type") or ""),
                "cadastralCode": (row.get("cadastralCode") or "").strip(),
                "name": s["name"],
                "district": s["district"],
                "receivedAt": _fmt_dt(row.get("receivedAt")),
                "ageDays": _as_int(row.get("ageDays")),
            }
        )

    procedure_groups = aggregate_procedure_groups(by_type)
    district_comparison = aggregate_district_comparison(ranking)
    prev_start, prev_end = previous_period(start_date, end_date)
    prev_totals = repository.query("totals", prev_start, prev_end, context.unit_id, staff_ids, procedure_types or None)
    prev_row = prev_totals[0] if prev_totals else {"dispatches": 0, "procedures": 0}
    period_comparison = build_period_comparison(
        start_date,
        end_date,
        dispatches_total,
        procedures_total,
        _as_int(prev_row.get("dispatches")),
        _as_int(prev_row.get("procedures")),
    )

    sla = {"summary": sla_summary, "byType": sla_by_type, "byStaff": sla_by_staff}

    return {
        "meta": {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "unitId": context.unit_id,
            "unit": context.unit_name,
            "districtId": district_id,
            "district": district_label,
            "procedureTypes": procedure_types,
            "server": context.server,
            "database": context.database,
            "source": "sqlserver",
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
        },
        "kpis": kpis,
        "ranking": ranking,
        "teamDaily": team_daily,
        "staffDaily": staff_daily,
        "byType": by_type,
        "byTypeAndStaff": by_type_and_staff,
        "typeStaffMatrix": _type_staff_matrix(ranking, by_type, by_type_and_staff),
        "procedures": procedures,
        "colors": colors_by_staff,
        "sla": sla,
        "backlogAging": backlog_aging,
        "criticalPending": critical_pending,
        "procedureGroups": procedure_groups,
        "districtComparison": district_comparison,
        "periodComparison": period_comparison,
        "analysis": build_analysis(
            ranking,
            kpis,
            district_label,
            sla=sla,
            backlog_aging=backlog_aging,
            period_comparison=period_comparison,
            procedure_groups=procedure_groups,
        ),
    }
