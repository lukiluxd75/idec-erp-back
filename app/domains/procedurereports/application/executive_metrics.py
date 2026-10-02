from datetime import date, timedelta

BACKLOG_BUCKET_ORDER = ("0-7", "8-15", "16-30", "31-60", "61+")
BACKLOG_BUCKET_LABELS = {
    "0-7": "0–7 días",
    "8-15": "8–15 días",
    "16-30": "16–30 días",
    "31-60": "31–60 días",
    "61+": "Más de 60 días",
}


def previous_period(start_date: date, end_date: date) -> tuple[date, date]:
    span_days = (end_date - start_date).days + 1
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span_days - 1)
    return prev_start, prev_end


def _delta_pct(current: int, previous: int) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


def build_period_comparison(
    start_date: date,
    end_date: date,
    current_dispatches: int,
    current_procedures: int,
    previous_dispatches: int,
    previous_procedures: int,
) -> dict:
    prev_start, prev_end = previous_period(start_date, end_date)
    return {
        "previousStartDate": prev_start.isoformat(),
        "previousEndDate": prev_end.isoformat(),
        "dispatches": previous_dispatches,
        "procedures": previous_procedures,
        "dispatchesDelta": current_dispatches - previous_dispatches,
        "proceduresDelta": current_procedures - previous_procedures,
        "dispatchesDeltaPct": _delta_pct(current_dispatches, previous_dispatches),
        "proceduresDeltaPct": _delta_pct(current_procedures, previous_procedures),
    }


def aggregate_procedure_groups(by_type: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for row in by_type:
        name = row.get("group") or "Otros"
        item = groups.setdefault(
            name,
            {"group": name, "dispatches": 0, "procedures": 0},
        )
        item["dispatches"] += int(row.get("dispatches") or 0)
        item["procedures"] += int(row.get("procedures") or 0)
    return sorted(groups.values(), key=lambda r: (-r["dispatches"], r["group"]))


def aggregate_district_comparison(ranking: list[dict]) -> list[dict]:
    by_district: dict[str, dict] = {}
    for row in ranking:
        district = row.get("district") or "Sin comuna"
        item = by_district.setdefault(
            district,
            {
                "district": district,
                "dispatches": 0,
                "procedures": 0,
                "pending": 0,
                "staffCount": 0,
            },
        )
        item["dispatches"] += int(row.get("dispatches") or 0)
        item["procedures"] += int(row.get("procedures") or 0)
        item["pending"] += int(row.get("pending") or 0)
        item["staffCount"] += 1
    rows = list(by_district.values())
    rows.sort(key=lambda r: (-r["dispatches"], r["district"]))
    return rows


def normalize_backlog_aging(rows: list[dict], total_pending: int) -> list[dict]:
    counts = {str(r.get("bucket") or ""): int(r.get("count") or 0) for r in rows}
    result = []
    for bucket in BACKLOG_BUCKET_ORDER:
        count = counts.get(bucket, 0)
        pct = round(count / total_pending * 100, 1) if total_pending else 0.0
        result.append(
            {
                "bucket": bucket,
                "label": BACKLOG_BUCKET_LABELS[bucket],
                "count": count,
                "pct": pct,
            }
        )
    return result


def build_sla_summary_row(row: dict | None) -> dict:
    if not row:
        return {"avgDays": None, "minDays": None, "maxDays": None, "sampleSize": 0}
    return {
        "avgDays": round(float(row["avgDays"]), 1) if row.get("avgDays") is not None else None,
        "minDays": int(row["minDays"]) if row.get("minDays") is not None else None,
        "maxDays": int(row["maxDays"]) if row.get("maxDays") is not None else None,
        "sampleSize": int(row.get("dispatches") or 0),
    }
