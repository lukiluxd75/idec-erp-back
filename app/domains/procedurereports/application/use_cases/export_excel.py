from io import BytesIO

import xlsxwriter

from ...domain.services.procedure_types import PALETTE

PURPLE = "#341A67"
CYAN = "#009ED0"
GRAY = "#6B7280"


def _fmt_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def build_excel(data: dict) -> bytes:
    buf = BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    title = wb.add_format({"bold": True, "font_color": "white", "bg_color": PURPLE, "font_size": 14, "align": "left"})
    subtitle = wb.add_format({"bold": True, "font_color": CYAN, "font_size": 11})
    header = wb.add_format({"bold": True, "font_color": "white", "bg_color": PURPLE, "border": 1, "align": "center"})
    cell = wb.add_format({"border": 1})
    num = wb.add_format({"border": 1, "num_format": "#,##0"})
    num1 = wb.add_format({"border": 1, "num_format": "#,##0.0"})
    kpi_v = wb.add_format({"bold": True, "font_size": 16, "font_color": PURPLE, "align": "center"})
    kpi_l = wb.add_format({"font_color": GRAY, "align": "center", "font_size": 9})

    meta = data["meta"]
    kpis = data["kpis"]
    ranking = data["ranking"]
    team = data["teamDaily"]
    colors_by_staff = data.get("colors") or {r["name"]: r.get("color") or PALETTE[i % len(PALETTE)] for i, r in enumerate(ranking)}

    res = wb.add_worksheet("Resumen")
    res.set_column("A:F", 22)
    res.merge_range("A1:F1", "Dirección de Administración Geográfica y Catastro", title)
    unit = meta.get("unit") or "Área Técnica Cartografía"
    res.merge_range("A2:F2", f"Reporte gerencial de trámites · {unit}", subtitle)
    res.write("A3", f"Período: {_fmt_date(meta['startDate'])} al {_fmt_date(meta['endDate'])}")
    res.write("A4", f"Comuna: {meta.get('district') or 'Todas'}")
    procedure_types = meta.get("procedureTypes") or []
    types_text = ", ".join(r["description"] for r in (data.get("byType") or [])[:8]) if data.get("byType") else ("Todos" if not procedure_types else "Selección")
    res.write("A5", f"Tipos: {types_text}")
    res.write("A6", data["analysis"].get("backlog", ""))

    labels = [
        ("Salidas de bandeja", kpis["dispatches"], "A8"),
        ("Trámites distintos", kpis["procedures"], "B8"),
        ("Promedio / día hábil", kpis["avgTeamPerDay"], "C8"),
        ("Pendientes", kpis["pendingCount"], "D8"),
        ("Personas", kpis["staffCount"], "E8"),
    ]
    for label, value, cell_addr in labels:
        col = cell_addr[0]
        res.write(f"{col}8", value, kpi_v)
        res.write(f"{col}9", label, kpi_l)

    sh = wb.add_worksheet("Ranking")
    sh.set_column("A:A", 36)
    sh.set_column("B:G", 16)
    headers = ["Usuario", "Despachos", "Trámites", "Días", "Por día", "Sobre hábiles", "Pendientes"]
    for i, h in enumerate(headers):
        sh.write(0, i, h, header)
    for r, row in enumerate(ranking, start=1):
        days = row["days"] or 0
        workdays = kpis["workingDays"] or 0
        sh.write(r, 0, row["name"], cell)
        sh.write_number(r, 1, row["dispatches"], num)
        sh.write_number(r, 2, row["procedures"], num)
        sh.write_number(r, 3, days, num)
        sh.write_number(r, 4, (row["dispatches"] / days) if days else 0, num1)
        sh.write_number(r, 5, (row["dispatches"] / workdays) if workdays else 0, num1)
        sh.write_number(r, 6, row["pending"], num)

    n = len(ranking)
    if n:
        chart = wb.add_chart({"type": "bar"})
        chart.add_series({
            "name": "Despachos",
            "categories": ["Ranking", 1, 0, n, 0],
            "values": ["Ranking", 1, 1, n, 1],
            "points": [{"fill": {"color": colors_by_staff.get(row["name"], PURPLE)}} for row in ranking],
        })
        chart.set_title({"name": "Ranking de despachos"})
        chart.set_style(10)
        chart.set_legend({"none": True})
        chart.set_size({"width": 720, "height": max(280, n * 18)})
        res.insert_chart("A11", chart)

    staff_count = [r["name"] for r in ranking if r["dispatches"] > 0]
    daily = wb.add_worksheet("Diario")
    daily.set_column(0, 0, 14)
    daily.set_column(1, max(len(staff_count), 1), 16)
    daily.write(0, 0, "Día", header)
    for i, name in enumerate(staff_count, start=1):
        daily.write(0, i, name, header)
    lookup = {(row["name"], row["date"]): row["dispatches"] for row in data.get("staffDaily") or []}
    for r, day in enumerate(team, start=1):
        daily.write(r, 0, day["label"], cell)
        for i, name in enumerate(staff_count, start=1):
            daily.write_number(r, i, lookup.get((name, day["date"]), 0), num)
    nd = len(team)
    if nd and staff_count:
        chart_d = wb.add_chart({"type": "column", "subtype": "stacked"})
        for i, name in enumerate(staff_count, start=1):
            chart_d.add_series({
                "name": name,
                "categories": ["Diario", 1, 0, nd, 0],
                "values": ["Diario", 1, i, nd, i],
                "fill": {"color": colors_by_staff.get(name, PURPLE)},
            })
        chart_d.set_title({"name": "Ritmo del equipo por día"})
        chart_d.set_style(10)
        chart_d.set_size({"width": 820, "height": 360})
        res.insert_chart("A29", chart_d)

    type_sheet = wb.add_worksheet("Por tipo")
    type_sheet.set_column("A:A", 48)
    type_sheet.set_column("B:C", 16)
    for i, h in enumerate(["Tipo", "Despachos", "Trámites"]):
        type_sheet.write(0, i, h, header)
    by_type = data.get("byType") or []
    for r, row in enumerate(by_type, start=1):
        type_sheet.write(r, 0, row["description"], cell)
        type_sheet.write_number(r, 1, row["dispatches"], num)
        type_sheet.write_number(r, 2, row["procedures"], num)
    nt = len(by_type)
    if nt:
        pie_t = wb.add_chart({"type": "pie"})
        pie_t.add_series({
            "name": "Despachos por tipo",
            "categories": ["Por tipo", 1, 0, nt, 0],
            "values": ["Por tipo", 1, 1, nt, 1],
            "points": [{"fill": {"color": row.get("color") or PURPLE}} for row in by_type],
        })
        pie_t.set_title({"name": "Trámites por tipo"})
        pie_t.set_style(10)
        pie_t.set_size({"width": 480, "height": 320})
        res.insert_chart("A65", pie_t)

    breakdown = wb.add_worksheet("Tipo y persona")
    matrix = data.get("typeStaffMatrix") or {"columns": [], "rows": []}
    columns = matrix.get("columns") or []
    matrix_rows = matrix.get("rows") or []
    breakdown.set_column(0, 0, 36)
    breakdown.set_column(1, max(len(columns), 1), 18)
    wrap_h = wb.add_format({"bold": True, "font_color": "white", "bg_color": PURPLE, "border": 1, "align": "center", "text_wrap": True, "valign": "bottom"})
    breakdown.set_row(0, 36)
    breakdown.write(0, 0, "Funcionario", header)
    for i, col in enumerate(columns, start=1):
        breakdown.write(0, i, col.get("description") or "", wrap_h)
    for r, row_data in enumerate(matrix_rows, start=1):
        breakdown.write(r, 0, row_data.get("name") or "", cell)
        for i, val in enumerate(row_data.get("values") or [], start=1):
            if val:
                breakdown.write_number(r, i, val, num)
            else:
                breakdown.write(r, i, "", cell)

    det = wb.add_worksheet("Tramites")
    det.set_column("A:B", 14)
    det.set_column("C:C", 42)
    det.set_column("D:D", 32)
    det.set_column("E:H", 18)
    for i, h in enumerate(["Nro", "Gestión", "Tipo", "Funcionario", "Estado", "Ingreso", "Salida", "Código catastral"]):
        det.write(0, i, h, header)
    for r, row in enumerate(data.get("procedures") or [], start=1):
        det.write(r, 0, row.get("procedureNumber") or "", cell)
        det.write(r, 1, row.get("year") or "", cell)
        det.write(r, 2, row.get("type") or "", cell)
        det.write(r, 3, row.get("name") or "", cell)
        det.write(r, 4, row.get("status") or "", cell)
        det.write(r, 5, row.get("receivedAt") or "", cell)
        det.write(r, 6, row.get("completedAt") or "", cell)
        det.write(r, 7, row.get("cadastralCode") or "", cell)

    wb.close()
    buf.seek(0)
    return buf.getvalue()
