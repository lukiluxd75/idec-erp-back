from datetime import date
import logging

import pyodbc

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.domains.security.contracts import UserProfile, require_permission

from ...application.use_cases.export_excel import build_excel
from ...application.use_cases.export_pdf import build_pdf
from ...application.use_cases.generate_report import generate_report
from ...domain.entities.report_context import ReportContext
from ...domain.services.procedure_types import DEFAULT_PROCEDURE_TYPES
from ...infrastructure.config import settings
from ...infrastructure.db import report_session
from ...infrastructure.sql_report_repository import SqlReportRepository
from ...infrastructure.staff import load_districts, load_procedure_types

router = APIRouter()
logger = logging.getLogger(__name__)


def _database_error(exc: Exception) -> HTTPException:
    logger.exception("Could not access procedure reports database")
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, pyodbc.Error):
        return HTTPException(status_code=503, detail="No se pudo conectar a SQL Server. Revisa las credenciales y el acceso de la cuenta configurada en el .env del backend.")
    return HTTPException(status_code=503, detail="No se pudo consultar la base de datos. Revisa la terminal del backend.")


def _district_param(district: int | None) -> int | None:
    return None if district in (None, 0) else district


def _procedure_types_param(procedure_types: str | None) -> list[int] | None:
    if procedure_types is None:
        return list(DEFAULT_PROCEDURE_TYPES)
    raw = procedure_types.strip()
    if raw in ("", "0", "all", "todos"):
        return None
    ids: list[int] = []
    allowed = set(DEFAULT_PROCEDURE_TYPES)
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            value = int(part)
            if value in allowed and value not in ids:
                ids.append(value)
    return ids or None


def _get_report(start_date: date, end_date: date, district: int | None, procedure_types: str | None, include_details: bool = False) -> dict:
    context = ReportContext(settings.unit_id, settings.unit_name, settings.db_server, settings.db_name)
    with report_session() as conn:
        return generate_report(
            start_date,
            end_date,
            _district_param(district),
            _procedure_types_param(procedure_types),
            include_details=include_details,
            repository=SqlReportRepository(conn),
            context=context,
        )


def _get_export_report(start_date: date, end_date: date, district: int | None, procedure_types: str | None) -> dict:
    try:
        return _get_report(start_date, end_date, district, procedure_types, include_details=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _database_error(exc) from exc


@router.get("/filters")
def list_filters(_user: UserProfile = Depends(require_permission("procedurereports.view"))):
    try:
        with report_session() as conn:
            return {
                "unitId": settings.unit_id,
                "unit": settings.unit_name,
                "centralDistrictId": settings.central_district_id,
                "defaultProcedureTypes": list(DEFAULT_PROCEDURE_TYPES),
                "districts": load_districts(conn=conn),
                "procedureTypes": load_procedure_types(),
            }
    except Exception as exc:
        raise _database_error(exc) from exc


@router.get("/reports")
def get_report(
    start_date: date = Query(date(2026, 8, 1)),
    end_date: date = Query(date(2026, 8, 31)),
    district: int | None = Query(7),
    procedure_types: str | None = Query(None),
    _user: UserProfile = Depends(require_permission("procedurereports.view")),
):
    try:
        return _get_report(start_date, end_date, district, procedure_types)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _database_error(exc) from exc


@router.get("/reports/export/excel")
def export_excel(
    start_date: date = Query(date(2026, 8, 1)),
    end_date: date = Query(date(2026, 8, 31)),
    district: int | None = Query(7),
    procedure_types: str | None = Query(None),
    _user: UserProfile = Depends(require_permission("procedurereports.view")),
):
    data = _get_export_report(start_date, end_date, district, procedure_types)
    filename = f"reporte-cartografia-{start_date.isoformat()}-{end_date.isoformat()}.xlsx"
    return Response(
        content=build_excel(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/export/pdf")
def export_pdf(
    start_date: date = Query(date(2026, 8, 1)),
    end_date: date = Query(date(2026, 8, 31)),
    district: int | None = Query(7),
    procedure_types: str | None = Query(None),
    _user: UserProfile = Depends(require_permission("procedurereports.view")),
):
    data = _get_export_report(start_date, end_date, district, procedure_types)
    filename = f"reporte-cartografia-{start_date.isoformat()}-{end_date.isoformat()}.pdf"
    return Response(
        content=build_pdf(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
