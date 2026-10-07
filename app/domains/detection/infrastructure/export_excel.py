"""Builds the "Exportar" .xlsx for a campaign's parcels report (see
ExportCampaignReportUseCase). Same xlsxwriter approach as
app/domains/procedurereports/application/use_cases/export_excel.py."""
from io import BytesIO
from typing import List

import xlsxwriter

from app.domains.detection.domain.entities.affected_parcel_report_row import AffectedParcelReportRow
from app.domains.detection.infrastructure.export_labels import (
    CHANGE_TYPE_LABEL,
    VALIDATION_STATUS_LABEL,
    change_detail_label,
    fmt_datetime,
)

PURPLE = "#341A67"
GRAY = "#6B7280"
CONFIRMED_TINT = "#EAF7EF"
REJECTED_TINT = "#FDECEC"

HEADERS = [
    "Nº",
    "Sector",
    "Código catastral",
    "Tipo de cambio",
    "Detalle del cambio",
    "Estado",
    "Motivo de rechazo",
    "Años comparados",
    "Campaña",
    "Probabilidad (%)",
    "Validado por",
    "Fecha de validación",
    "Longitud",
    "Latitud",
]


def build_campaign_report_excel(rows: List[AffectedParcelReportRow], campaign_label: str) -> bytes:
    buf = BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})

    title = wb.add_format({"bold": True, "font_color": "white", "bg_color": PURPLE, "font_size": 14})
    subtitle = wb.add_format({"font_color": GRAY, "font_size": 10})
    header = wb.add_format(
        {"bold": True, "font_color": "white", "bg_color": PURPLE, "border": 1, "align": "center", "text_wrap": True}
    )

    def tinted(status: str, **extra):
        bg = CONFIRMED_TINT if status == "confirmed" else REJECTED_TINT if status == "rejected" else None
        spec = {"border": 1, **extra}
        if bg:
            spec["bg_color"] = bg
        return wb.add_format(spec)

    cells_by_status = {
        status: {
            "cell": tinted(status),
            "num": tinted(status, num_format="#,##0"),
            "coord": tinted(status, num_format="0.000000"),
        }
        for status in ("confirmed", "rejected", "")
    }

    sheet = wb.add_worksheet("Predios")
    widths = [6, 16, 20, 14, 22, 14, 32, 16, 16, 14, 20, 18, 14, 14]
    for i, w in enumerate(widths):
        sheet.set_column(i, i, w)

    last_col = len(HEADERS) - 1
    sheet.merge_range(0, 0, 0, last_col, "Detección de construcciones - Reporte de predios", title)
    sheet.merge_range(1, 0, 1, last_col, campaign_label, subtitle)

    header_row = 3
    for i, h in enumerate(HEADERS):
        sheet.write(header_row, i, h, header)

    for r, row in enumerate(rows, start=1):
        excel_row = header_row + r
        fmts = cells_by_status.get(row.validation_status, cells_by_status[""])
        cell, num, coord = fmts["cell"], fmts["num"], fmts["coord"]
        sheet.write_number(excel_row, 0, r, cell)
        sheet.write(excel_row, 1, row.sector_name or f"Sector #{row.sector_id}", cell)
        sheet.write(excel_row, 2, row.cadastral_code or "", cell)
        sheet.write(excel_row, 3, CHANGE_TYPE_LABEL.get(row.change_type, row.change_type), cell)
        sheet.write(excel_row, 4, change_detail_label(row), cell)
        sheet.write(excel_row, 5, VALIDATION_STATUS_LABEL.get(row.validation_status, row.validation_status), cell)
        sheet.write(excel_row, 6, row.rejection_comment or "", cell)
        sheet.write(excel_row, 7, f"{row.year_a} - {row.year_b}", cell)
        sheet.write(excel_row, 8, row.campaign_code or "", cell)
        if row.probability_pct is not None:
            sheet.write_number(excel_row, 9, row.probability_pct, num)
        else:
            sheet.write(excel_row, 9, "", cell)
        sheet.write(excel_row, 10, row.validated_by_username or "", cell)
        sheet.write(excel_row, 11, fmt_datetime(row.validated_at), cell)
        if row.lon is not None and row.lat is not None:
            sheet.write_number(excel_row, 12, row.lon, coord)
            sheet.write_number(excel_row, 13, row.lat, coord)
        else:
            sheet.write(excel_row, 12, "", cell)
            sheet.write(excel_row, 13, "", cell)

    sheet.freeze_panes(header_row + 1, 0)
    wb.close()
    buf.seek(0)
    return buf.getvalue()
