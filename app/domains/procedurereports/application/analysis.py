from datetime import date


def _format_number(n: float | int) -> str:
    if isinstance(n, float):
        return f"{n:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{n:,}".replace(",", ".")


def build_analysis(ranking: list[dict], kpis: dict, district_label: str) -> dict:
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
            f"Concentran el backlog: {include_details}. El resto del equipo suma {_format_number(remaining)}."
        )
    else:
        message = f"Hay {_format_number(pending)} trámites pendientes en las bandejas de {district_label}."
    return {"backlog": message, "outliers": [r["name"] for r in outliers]}
