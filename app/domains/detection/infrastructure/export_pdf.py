"""Builds the "Exportar" .pdf for a campaign's parcels report -- same data and
row styling as export_excel.py (see ExportCampaignReportUseCase), formatted
for a formal/presentation read (architect profile, per the engineer's request)
rather than a working spreadsheet. Same reportlab approach as
app/domains/procedurereports/application/use_cases/export_pdf.py."""
import base64
from datetime import datetime
from io import BytesIO
from typing import List, Optional

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.domains.detection.domain.entities.affected_parcel_report_row import AffectedParcelReportRow
from app.domains.detection.infrastructure.export_labels import (
    CHANGE_TYPE_LABEL,
    VALIDATION_STATUS_LABEL,
    change_detail_label,
    fmt_datetime,
)

PURPLE = colors.HexColor("#341A67")
GRAY = colors.HexColor("#6B7280")
CONFIRMED_TINT = colors.HexColor("#EAF7EF")
REJECTED_TINT = colors.HexColor("#FDECEC")
GRID = colors.HexColor("#E5E7EB")

HEADERS = [
    "Nº", "Sector", "Código catastral", "Tipo de cambio", "Detalle del cambio",
    "Estado", "Motivo de rechazo", "Años", "Campaña", "Prob. (%)",
    "Validado por", "Fecha de validación", "Longitud", "Latitud",
]
COL_WIDTHS_CM = [0.9, 2.0, 2.4, 1.8, 2.2, 1.8, 2.8, 1.5, 1.8, 1.1, 2.0, 2.4, 1.6, 1.6]


def _chart_image_flowable(image_base64: str, max_width: float, max_height: float) -> Image:
    """Decodes a data-URL/base64 PNG (captured client-side from the live
    Recharts component, same pixels the architect already sees in
    "Reportes") and scales it to fit the page while keeping its aspect
    ratio -- the chart's own proportions vary (pie vs. bar vs. line), so a
    fixed width/height would stretch some of them."""
    raw = image_base64.split(",", 1)[-1] if "," in image_base64 else image_base64
    buf = BytesIO(base64.b64decode(raw))
    width_px, height_px = PILImage.open(buf).size
    buf.seek(0)
    scale = min(max_width / width_px, max_height / height_px)
    return Image(buf, width=width_px * scale, height=height_px * scale)


def build_campaign_report_pdf(
    rows: List[AffectedParcelReportRow],
    campaign_label: str,
    charts: Optional[List[dict]] = None,
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title="Reporte de predios — Detección de construcciones",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title2", parent=styles["Heading1"], textColor=PURPLE, fontSize=16, spaceAfter=2)
    subtitle_style = ParagraphStyle("Subtitle2", parent=styles["Normal"], textColor=GRAY, fontSize=10)
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=7.5, leading=9)
    header_style = ParagraphStyle(
        "HeaderCell", parent=cell_style, textColor=colors.white, fontName="Helvetica-Bold", alignment=1
    )

    story = [
        Paragraph("Detección de construcciones — Reporte de predios", title_style),
        Paragraph(campaign_label, subtitle_style),
        Paragraph(
            f"Generado el {fmt_datetime(datetime.now())}",
            ParagraphStyle("Gen", parent=subtitle_style, fontSize=8),
        ),
        Spacer(1, 0.4 * cm),
    ]

    table_data = [[Paragraph(h, header_style) for h in HEADERS]]
    row_backgrounds: list[tuple[int, colors.Color]] = []
    for i, row in enumerate(rows, start=1):
        coords = f"{row.lon:.6f}" if row.lon is not None else ""
        lat = f"{row.lat:.6f}" if row.lat is not None else ""
        table_data.append(
            [
                Paragraph(str(i), cell_style),
                Paragraph(row.sector_name or f"Sector #{row.sector_id}", cell_style),
                Paragraph(row.cadastral_code or "", cell_style),
                Paragraph(CHANGE_TYPE_LABEL.get(row.change_type, row.change_type), cell_style),
                Paragraph(change_detail_label(row), cell_style),
                Paragraph(VALIDATION_STATUS_LABEL.get(row.validation_status, row.validation_status), cell_style),
                Paragraph(row.rejection_comment or "", cell_style),
                Paragraph(f"{row.year_a} → {row.year_b}", cell_style),
                Paragraph(row.campaign_code or "", cell_style),
                Paragraph("" if row.probability_pct is None else str(row.probability_pct), cell_style),
                Paragraph(row.validated_by_username or "", cell_style),
                Paragraph(fmt_datetime(row.validated_at), cell_style),
                Paragraph(coords, cell_style),
                Paragraph(lat, cell_style),
            ]
        )
        if row.validation_status == "confirmed":
            row_backgrounds.append((i, CONFIRMED_TINT))
        elif row.validation_status == "rejected":
            row_backgrounds.append((i, REJECTED_TINT))

    table = Table(table_data, colWidths=[w * cm for w in COL_WIDTHS_CM], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for row_index, bg in row_backgrounds:
        style.append(("BACKGROUND", (0, row_index), (-1, row_index), bg))
    table.setStyle(TableStyle(style))
    story.append(table)

    if not rows:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("Sin predios confirmados o rechazados en esta campaña.", subtitle_style))

    if charts:
        max_w = landscape(A4)[0] - 2.4 * cm
        max_h = landscape(A4)[1] - 4 * cm
        for chart in charts:
            story.append(PageBreak())
            story.append(Paragraph(chart.get("title") or "Gráfica", title_style))
            story.append(Spacer(1, 0.4 * cm))
            story.append(_chart_image_flowable(chart["image_base64"], max_w, max_h))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
