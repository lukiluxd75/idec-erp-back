"""Builds the "Exportar" .xlsx for a campaign's parcels report (see
ExportCampaignReportUseCase). Same xlsxwriter approach as
app/domains/procedurereports/application/use_cases/export_excel.py."""
from datetime import datetime
from io import BytesIO
from typing import List, Optional

import xlsxwriter

from app.domains.detection.domain.entities.affected_parcel_report_row import AffectedParcelReportRow

PURPLE = "#341A67"
GRAY = "#6B7280"

CHANGE_TYPE_LABEL = {
    "new": "Nueva",
    "removed": "Eliminada",
    "modified": "Cambio",
    "unchanged": "Sin cambio",
}

# Kept in sync with ParcelValidationModal's CONSTRUCTION_TYPES -- "otro" never
# reaches here as the literal word, only as the architect's free-text label
# (see ReviewAffectedParcelUseCase), so it needs no entry of its own.
CONSTRUCTION_TYPE_LABEL = {
    "nueva_construccion": "Construcción nueva",
    "ampliacion": "Ampliación",
    "cambio_techo": "Cambio de techo",
    "muro_nuevo": "Muro nuevo",
    "demolicion": "Demolición",
}

VALIDATION_STATUS_LABEL = {
    "confirmed": "Confirmado",
    "rejected": "Rechazado",
}

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


def _fmt_datetime(value: Optional[datetime]) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else ""


def build_campaign_report_excel(rows: List[AffectedParcelReportRow], campaign_label: str) -> bytes:
    buf = BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})

    title = wb.add_format({"bold": True, "font_color": "white", "bg_color": PURPLE, "font_size": 14})
    subtitle = wb.add_format({"font_color": GRAY, "font_size": 10})
    header = wb.add_format(
        {"bold": True, "font_color": "white", "bg_color": PURPLE, "border": 1, "align": "center", "text_wrap": True}
    )
    cell = wb.add_format({"border": 1})
    num = wb.add_format({"border": 1, "num_format": "#,##0"})
    coord = wb.add_format({"border": 1, "num_format": "0.000000"})

    sheet = wb.add_worksheet("Predios")
    widths = [6, 16, 20, 14, 22, 14, 32, 16, 16, 14, 20, 18, 14, 14]
    for i, w in enumerate(widths):
        sheet.set_column(i, i, w)

    last_col = len(HEADERS) - 1
    sheet.merge_range(0, 0, 0, last_col, "Detección de construcciones — Reporte de predios", title)
    sheet.merge_range(1, 0, 1, last_col, campaign_label, subtitle)

    header_row = 3
    for i, h in enumerate(HEADERS):
        sheet.write(header_row, i, h, header)

    for r, row in enumerate(rows, start=1):
        excel_row = header_row + r
        # construction_type can be set on a confirmed finding of ANY
        # change_type (new/removed/modified), not just "modified" ones --
        # verified against real data (e.g. a "removed" finding classified
        # with the architect's own free-text label).
        change_detail = CONSTRUCTION_TYPE_LABEL.get(row.construction_type, row.construction_type or "")
        sheet.write_number(excel_row, 0, r, cell)
        sheet.write(excel_row, 1, row.sector_name or f"Sector #{row.sector_id}", cell)
        sheet.write(excel_row, 2, row.cadastral_code or "", cell)
        sheet.write(excel_row, 3, CHANGE_TYPE_LABEL.get(row.change_type, row.change_type), cell)
        sheet.write(excel_row, 4, change_detail, cell)
        sheet.write(excel_row, 5, VALIDATION_STATUS_LABEL.get(row.validation_status, row.validation_status), cell)
        sheet.write(excel_row, 6, row.rejection_comment or "", cell)
        sheet.write(excel_row, 7, f"{row.year_a} → {row.year_b}", cell)
        sheet.write(excel_row, 8, row.campaign_code or "", cell)
        if row.probability_pct is not None:
            sheet.write_number(excel_row, 9, row.probability_pct, num)
        else:
            sheet.write(excel_row, 9, "", cell)
        sheet.write(excel_row, 10, row.validated_by_username or "", cell)
        sheet.write(excel_row, 11, _fmt_datetime(row.validated_at), cell)
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
