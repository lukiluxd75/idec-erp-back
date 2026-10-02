from datetime import date


def _format_number(n: float | int, digits: int | None = None) -> str:
    if digits is None:
        digits = 1 if isinstance(n, float) and not float(n).is_integer() else 0
    if digits:
        return f"{float(n):,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{int(n):,}".replace(",", ".")


def build_analysis(
    ranking: list[dict],
    kpis: dict,
    district_label: str,
    *,
    sla: dict | None = None,
    backlog_aging: list[dict] | None = None,
    period_comparison: dict | None = None,
    procedure_groups: list[dict] | None = None,
) -> dict:
    pending = kpis["pendingCount"]
    outliers = []
    if pending:
        outliers = [
            r for r in ranking
            if r["pending"] >= max(80, pending * 0.35)
        ]
    remaining = pending - sum(r["pending"] for r in outliers)
    if outliers:
        include_details = "; ".join(f"{r['name']} {_format_number(r['pending'])}" for r in outliers)
        message = (
            f"Hay {_format_number(pending)} trámites pendientes en {district_label}. "
            f"Concentran la bandeja pendiente: {include_details}. El resto del equipo suma {_format_number(remaining)}."
        )
    else:
        message = f"Hay {_format_number(pending)} trámites pendientes en las bandejas de {district_label}."

    bullets: list[str] = []
    dispatches = kpis.get("dispatches") or 0
    if period_comparison and dispatches:
        delta = period_comparison.get("dispatchesDelta")
        pct = period_comparison.get("dispatchesDeltaPct")
        if delta is not None and pct is not None:
            sign = "más" if delta >= 0 else "menos"
            bullets.append(
                f"Salidas de bandeja: {_format_number(dispatches)} "
                f"({sign} {_format_number(abs(delta))} que el período anterior, {pct:+.1f}%)."
            )
        elif delta is not None:
            sign = "más" if delta >= 0 else "menos"
            bullets.append(
                f"Salidas de bandeja: {_format_number(dispatches)} "
                f"({sign} {_format_number(abs(delta))} que el período anterior)."
            )

    summary = (sla or {}).get("summary") or {}
    if summary.get("avgDays") is not None:
        bullets.append(
            f"Tiempo promedio ingreso → salida: {_format_number(summary['avgDays'], 1)} días "
            f"(muestra de {_format_number(summary.get('sampleSize') or 0)} salidas)."
        )

    aging = backlog_aging or []
    stale = sum(b.get("count") or 0 for b in aging if b.get("bucket") in ("31-60", "61+"))
    if pending and stale:
        pct_stale = round(stale / pending * 100, 1)
        bullets.append(
            f"Pendientes con más de 30 días en bandeja: {_format_number(stale)} trámites ({pct_stale}% del total pendiente)."
        )

    groups = procedure_groups or []
    if len(groups) >= 2:
        lead = groups[0]
        share = round(lead["dispatches"] / dispatches * 100, 1) if dispatches else 0
        bullets.append(
            f"Mix del período: {lead['group']} concentra {_format_number(lead['dispatches'])} salidas ({share}%)."
        )

    if kpis.get("avgTeamPerDay"):
        bullets.append(
            f"Ritmo del equipo: {_format_number(kpis['avgTeamPerDay'], 1)} salidas por día hábil "
            f"en {kpis.get('workingDays') or 0} días hábiles del calendario."
        )

    headline = bullets[0] if bullets else message
    return {
        "backlog": message,
        "outliers": [r["name"] for r in outliers],
        "executiveHeadline": headline,
        "executiveBullets": bullets[:5],
    }
