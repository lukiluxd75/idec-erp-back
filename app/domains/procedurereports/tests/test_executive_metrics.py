from datetime import date

from app.domains.procedurereports.application.executive_metrics import (
    aggregate_procedure_groups,
    build_period_comparison,
    normalize_backlog_aging,
    previous_period,
)


def test_previous_period_same_length():
    start = date(2026, 8, 1)
    end = date(2026, 8, 31)
    prev_start, prev_end = previous_period(start, end)
    assert (end - start).days == (prev_end - prev_start).days
    assert prev_end == date(2026, 7, 31)
    assert prev_start == date(2026, 7, 1)


def test_normalize_backlog_aging_fills_buckets():
    rows = [{"bucket": "0-7", "count": 2}, {"bucket": "61+", "count": 1}]
    out = normalize_backlog_aging(rows, 3)
    assert len(out) == 5
    assert out[0]["count"] == 2
    assert out[-1]["count"] == 1


def test_aggregate_procedure_groups():
    by_type = [
        {"group": "Certificaciones", "dispatches": 10, "procedures": 8},
        {"group": "Certificaciones", "dispatches": 5, "procedures": 4},
        {"group": "Registros catastrales", "dispatches": 3, "procedures": 3},
    ]
    groups = aggregate_procedure_groups(by_type)
    assert groups[0]["group"] == "Certificaciones"
    assert groups[0]["dispatches"] == 15


def test_period_comparison_delta_pct():
    pc = build_period_comparison(date(2026, 8, 1), date(2026, 8, 31), 110, 90, 100, 80)
    assert pc["dispatchesDelta"] == 10
    assert pc["dispatchesDeltaPct"] == 10.0
