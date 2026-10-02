from datetime import date, datetime

from ..domain.entities.report_context import ReportContext
from ..domain.ports.report_repository import ReportRepository
from ..infrastructure.config import settings
from .executive_metrics import normalize_backlog_aging


def _sum_pending(rows: list[dict]) -> int:
    return sum(int(r.get("pending") or 0) for r in rows)


def build_panel_summary(
    start_date: date,
    end_date: date,
    district_id: int | None,
    procedure_type_ids: list[int] | None,
    repository: ReportRepository,
    context: ReportContext,
) -> dict:
    staff = repository.load_staff(district_id)
    staff_ids = [int(s["staffId"]) for s in staff]
    if not staff_ids:
        return {
            "meta": _meta(start_date, end_date, context),
            "kpis": {
                "dispatches": 0,
                "procedures": 0,
                "pendingCount": 0,
                "slaAvgDays": None,
                "staffCount": 0,
            },
            "backlogAging": normalize_backlog_aging([], 0),
            "criticalPending": [],
        }

    totals_row = (repository.query("totals", start_date, end_date, settings.unit_id, staff_ids, procedure_type_ids) or [{}])[0]
    pending_rows = repository.query("pending", start_date, end_date, settings.unit_id, staff_ids, procedure_type_ids)
    sla_row = (repository.query("sla_summary", start_date, end_date, settings.unit_id, staff_ids, procedure_type_ids) or [{}])[0]
    aging_rows = repository.query("backlog_aging", start_date, end_date, settings.unit_id, staff_ids, procedure_type_ids)
    critical = repository.query("critical_pending", start_date, end_date, settings.unit_id, staff_ids, procedure_type_ids)[:8]

    dispatches = int(totals_row.get("dispatches") or 0)
    procedures = int(totals_row.get("procedures") or 0)
    pending_count = _sum_pending(pending_rows)
    avg_days = sla_row.get("avgDays")
    sla_avg = round(float(avg_days), 1) if avg_days is not None else None

    return {
        "meta": _meta(start_date, end_date, context),
        "kpis": {
            "dispatches": dispatches,
            "procedures": procedures,
            "pendingCount": pending_count,
            "slaAvgDays": sla_avg,
            "staffCount": len(staff_ids),
        },
        "backlogAging": normalize_backlog_aging(aging_rows, pending_count),
        "criticalPending": [_format_critical(r) for r in critical],
    }


def _meta(start_date: date, end_date: date, context: ReportContext) -> dict:
    return {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "unitId": context.unit_id,
        "unit": context.unit_name,
        "receptionUnitId": settings.reception_unit_id,
        "receptionUnit": settings.reception_unit_name,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
    }


def _format_critical(row: dict) -> dict:
    received = row.get("receivedAt")
    age = int(row.get("ageDays") or 0)
    return {
        "procedureNumber": row.get("procedureNumber"),
        "type": row.get("type"),
        "cadastralCode": row.get("cadastralCode"),
        "receivedAt": received.isoformat(timespec="minutes") if isinstance(received, datetime) else str(received or "")[:16],
        "ageDays": age,
    }
