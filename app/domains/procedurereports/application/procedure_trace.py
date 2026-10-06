from datetime import datetime

from ..infrastructure import special_queries
from ..infrastructure.db import fetchall
from ..infrastructure.staff import pretty_name


def _fmt_dt(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)[:16]


def _minutes_between(start, end) -> int | None:
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        return None
    delta = end - start
    return max(0, int(delta.total_seconds() // 60))


def _human_duration(minutes: int | None) -> str:
    if minutes is None:
        return "—"
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    mins = minutes % 60
    if hours < 48:
        return f"{hours} h {mins} min" if mins else f"{hours} h"
    days = hours // 24
    rem_h = hours % 24
    return f"{days} d {rem_h} h" if rem_h else f"{days} d"


def build_procedure_trace(
    *,
    conn,
    procedure_number: int,
    stall_threshold_days: int = 5,
) -> dict:
    if not procedure_number:
        raise ValueError("Indique el número de trámite.")
    resolve_sql, resolve_params = special_queries.resolve_procedure_sql(procedure_number)
    header_rows = fetchall(resolve_sql, resolve_params, conn=conn)
    if not header_rows:
        raise ValueError("No se encontró el trámite indicado.")
    header = header_rows[0]
    pid = int(header["procedureId"])

    trace_sql, trace_params = special_queries.procedure_trace_sql(pid)
    raw_steps = fetchall(trace_sql, trace_params, conn=conn)

    steps = []
    prev_completed: datetime | None = None
    max_wait = 0
    bottleneck = None

    for row in raw_steps:
        received = row.get("receivedAt")
        completed = row.get("completedAt")
        handling = _minutes_between(received, completed) if completed else None
        wait = _minutes_between(prev_completed, received) if prev_completed and received else None
        if wait is not None and wait > max_wait:
            max_wait = wait
            bottleneck = int(row.get("sequenceId") or 0)

        is_open = completed is None
        age_days = None
        if is_open and isinstance(received, datetime):
            age_days = (datetime.now() - received).days

        stall = False
        if handling is not None and handling >= stall_threshold_days * 24 * 60:
            stall = True
        if is_open and age_days is not None and age_days >= stall_threshold_days:
            stall = True
        if wait is not None and wait >= stall_threshold_days * 24 * 60:
            stall = True

        steps.append(
            {
                "sequenceId": int(row.get("sequenceId") or 0),
                "unitId": int(row.get("idUnidad") or 0),
                "unitName": row.get("unitName") or "—",
                "staffId": int(row.get("staffId") or 0),
                "staffName": pretty_name(row.get("name") or ""),
                "receivedAt": _fmt_dt(received),
                "completedAt": _fmt_dt(completed),
                "reason": (row.get("reason") or "").strip() or None,
                "legNumber": row.get("legNumber"),
                "handlingMinutes": handling,
                "handlingLabel": _human_duration(handling),
                "waitMinutes": wait,
                "waitLabel": _human_duration(wait),
                "openInUnit": is_open,
                "ageDays": age_days,
                "stall": stall,
            }
        )
        if isinstance(completed, datetime):
            prev_completed = completed
        elif isinstance(received, datetime) and completed is None:
            prev_completed = None

    total_span = None
    if raw_steps:
        first_in = raw_steps[0].get("receivedAt")
        last_out = raw_steps[-1].get("completedAt")
        if isinstance(first_in, datetime) and isinstance(last_out, datetime):
            total_span = _minutes_between(first_in, last_out)

    return {
        "procedure": {
            "procedureNumber": header.get("procedureNumber"),
            "type": header.get("type"),
            "cadastralCode": header.get("cadastralCode"),
        },
        "summary": {
            "steps": len(steps),
            "totalDurationLabel": _human_duration(total_span),
            "bottleneckSequenceId": bottleneck,
            "bottleneckWaitLabel": _human_duration(max_wait if bottleneck else None),
            "stallThresholdDays": stall_threshold_days,
        },
        "steps": steps,
    }
