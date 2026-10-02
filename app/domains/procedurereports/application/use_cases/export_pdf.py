from io import BytesIO

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ...domain.services.procedure_types import PALETTE

PURPLE = colors.HexColor("#341A67")
CYAN = colors.HexColor("#009ED0")
BG = colors.HexColor("#F3F4F6")
INK = colors.HexColor("#1F2937")


def _format_number(n, digits=0):
    return f"{n:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".") if digits else f"{n:,}".replace(",", ".")


def _fmt_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def _hex(value: str):
    return colors.HexColor(value if value and value.startswith("#") else PALETTE[0])


def _hchart(title: str, names: list[str], values: list[float], fills: list[str]) -> Drawing:
    n = max(len(names), 1)
    height = max(160, 18 * n + 50)
    d = Drawing(740, height)
    d.add(String(0, height - 14, title, fontName="Helvetica-Bold", fontSize=11, fillColor=PURPLE))
    chart = HorizontalBarChart()
    chart.x = 150
    chart.y = 10
    chart.height = height - 40
    chart.width = 560
    chart.data = [values or [0]]
    chart.categoryAxis.categoryNames = names or [""]
    chart.barWidth = 12
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.gridStrokeColor = colors.HexColor("#E5E7EB")
    d.add(chart)
    for i, fill in enumerate(fills or [PALETTE[0]]):
        try:
            chart.bars[(0, i)].fillColor = _hex(fill)
        except Exception:
            chart.bars[0].fillColor = _hex(fill)
    return d


def _vstacked(title: str, categories: list[str], series: list[tuple[str, list[float], str]]) -> Drawing:
    d = Drawing(740, 300)
    d.add(String(0, 286, title, fontName="Helvetica-Bold", fontSize=11, fillColor=PURPLE))
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 50
    chart.height = 200
    chart.width = 520
    chart.data = [vals for _, vals, _ in series] or [[0]]
    chart.categoryAxis.categoryNames = categories or [""]
    chart.categoryAxis.style = "stacked"
    chart.categoryAxis.labels.angle = 45
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.labels.fontSize = 8
    d.add(chart)
    for i, (_, _, fill) in enumerate(series):
        try:
            chart.bars[i].fillColor = _hex(fill)
        except Exception:
            pass
    legend = Legend()
    legend.x = 570
    legend.y = 60
    legend.fontSize = 6
    legend.boxAnchor = "sw"
    legend.columnMaximum = 12
    legend.colorNamePairs = [(_hex(fill), name[:22]) for name, _, fill in series]
    d.add(legend)
    return d


def build_pdf(data: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title="Reporte gerencial de trámites",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Title"], textColor=PURPLE, fontSize=16, alignment=TA_CENTER, spaceAfter=2)
    h2 = ParagraphStyle("H2", parent=styles["Normal"], textColor=CYAN, fontSize=11, alignment=TA_CENTER, spaceAfter=8, fontName="Helvetica-Bold")
    body = ParagraphStyle("Body", parent=styles["Normal"], textColor=INK, fontSize=9, leading=12, alignment=TA_LEFT)
    small = ParagraphStyle("Small", parent=styles["Normal"], textColor=colors.HexColor("#6B7280"), fontSize=8)

    meta = data["meta"]
    kpis = data["kpis"]
    ranking = data["ranking"]
    team = data["teamDaily"]
    colors_by_staff = data.get("colors") or {}

    story = []
    story.append(Paragraph("DIRECCIÓN DE ADMINISTRACIÓN GEOGRÁFICA Y CATASTRO", h1))
    story.append(Paragraph("Reporte gerencial · Área Técnica Cartografía", h2))
    story.append(Paragraph(
        f"Período {_fmt_date(meta['startDate'])} al {_fmt_date(meta['endDate'])} · Comuna: {meta.get('district') or 'Todas'}",
        small,
    ))
    story.append(Spacer(1, 8))

    kpi_data = [[
        Paragraph(f"<b>{_format_number(kpis['dispatches'])}</b><br/>Salidas", body),
        Paragraph(f"<b>{_format_number(kpis['procedures'])}</b><br/>Trámites", body),
        Paragraph(f"<b>{_format_number(kpis['avgTeamPerDay'], 1)}</b><br/>Prom. día hábil", body),
        Paragraph(f"<b>{_format_number(kpis['pendingCount'])}</b><br/>Pendientes", body),
        Paragraph(f"<b>{kpis['staffCount']}</b><br/>Personas", body),
    ]]
    kt = Table(kpi_data, colWidths=[5.2 * cm] * 5)
    kt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, PURPLE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(kt)
    story.append(Spacer(1, 8))
    story.append(Paragraph(data["analysis"].get("backlog", ""), body))
    story.append(Spacer(1, 10))

    names = [r["name"] for r in ranking][::-1]
    vals = [r["dispatches"] for r in ranking][::-1]
    fills = [colors_by_staff.get(r["name"], r.get("color") or PALETTE[0]) for r in ranking][::-1]
    if names:
        story.append(_hchart("Ranking de despachos", names, vals, fills))

    staff_count = [r["name"] for r in ranking if r["dispatches"] > 0]
    lookup = {(row["name"], row["date"]): row["dispatches"] for row in data.get("staffDaily") or []}
    if team and staff_count:
        series = []
        for name in staff_count:
            series.append((
                name,
                [float(lookup.get((name, day["date"]), 0)) for day in team],
                colors_by_staff.get(name, PALETTE[0]),
            ))
        story.append(Spacer(1, 8))
        story.append(_vstacked("Ritmo del equipo por día", [d["label"] for d in team], series))

    story.append(PageBreak())
    story.append(Paragraph("Estimado por persona", h2))
    head = ["Usuario", "Despachos", "Trámites", "Días", "Por día", "Sobre hábiles"]
    rows = [head]
    workdays = kpis["workingDays"] or 0
    for r in ranking:
        por = (r["dispatches"] / r["days"]) if r["days"] else 0
        sobre = (r["dispatches"] / workdays) if workdays else 0
        rows.append([
            r["name"],
            _format_number(r["dispatches"]),
            _format_number(r["procedures"]),
            str(r["days"]),
            f"{por:.1f}".replace(".", ","),
            f"{sobre:.1f}".replace(".", ","),
        ])
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
    ]))
    story.append(table)

    story.append(Spacer(1, 12))
    story.append(Paragraph("Pendientes actuales", h2))
    pend_head = ["Usuario", "Pendientes"]
    pend_table_rows = [pend_head] + [[r["name"], _format_number(r["pending"])] for r in ranking]
    pt = Table(pend_table_rows, repeatRows=1)
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
    ]))
    story.append(pt)

    if data.get("byType"):
        story.append(PageBreak())
        story.append(Paragraph("Trámites por tipo", h2))
        trows = [["Tipo", "Despachos", "Trámites"]]
        for row in data["byType"]:
            trows.append([row["description"], _format_number(row["dispatches"]), _format_number(row["procedures"])])
        tt = Table(trows, repeatRows=1, colWidths=[16.2 * cm, 3.5 * cm, 3.5 * cm])
        tt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
        ]))
        story.append(tt)

    matrix = data.get("typeStaffMatrix") or {}
    columns = matrix.get("columns") or []
    matrix_rows = matrix.get("rows") or []
    if columns and matrix_rows:
        story.append(Spacer(1, 12))
        story.append(Paragraph("Despachos por tipo y funcionario", h2))
        head_m = ["Funcionario"] + [c.get("description") or "" for c in columns]
        crows = [head_m]
        for row_data in matrix_rows:
            crows.append(
                [row_data.get("name") or ""] + [(_format_number(v) if v else "") for v in (row_data.get("values") or [])]
            )
        col_w = [5.2 * cm] + [max(2.2 * cm, 18 * cm / max(len(columns), 1))] * len(columns)
        ct = Table(crows, repeatRows=1, colWidths=col_w[: 1 + len(columns)])
        ct.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
        ]))
        story.append(ct)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Fuente: {meta['database']} · unidad {meta['unitId']} {meta['unit']} · generado {meta['generatedAt']}",
        small,
    ))
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
