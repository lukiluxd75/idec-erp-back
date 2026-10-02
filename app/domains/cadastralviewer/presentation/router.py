import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.cadastralviewer.infrastructure.models import (
    AdvertisementModel,
    CadastralProcedureModel,
    MapLayerModel,
)
from app.domains.cadastralviewer.presentation.schemas import (
    AdminAdvertisementPayload,
    AdminLayerPayload,
    AdminProcedurePayload,
    AdvertisementUpdatePayload,
    AdvertisementItem,
    HealthResponse,
    MapSearchItem,
    MapLayerItem,
    ProcedureItem,
)
from app.domains.security.contracts import get_current_user

router = APIRouter(prefix="/cadastralviewer", tags=["Cadastral Viewer"])
MEDIA_DIR = Path(__file__).resolve().parents[3] / "storage" / "advertisements"
MEDIA_PREFIX = "/api/cadastralviewer/advertisements/media"
MAX_VIDEO_BYTES = 250 * 1024 * 1024
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".ogg"}
ARCGIS_SEARCH_URLS = {
    "parcel": "https://gs.catastrocbba.com/arcgis/rest/services/catastro/prediosWms/MapServer/0/query",
    "street": "https://gs.catastrocbba.com/arcgis/rest/services/planificacion/vias/MapServer/0/query",
}


def _actor(user) -> str:
    return str(getattr(user, "sub", None) or "system")[:100]


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:100] or uuid.uuid4().hex


def _procedure_item(row: CadastralProcedureModel) -> ProcedureItem:
    return ProcedureItem(
        id=str(row.id), code=row.code, name=row.name, description=row.description,
        category=row.category, icon="📋", requirements=row.requirements or [],
        estimated_days=row.estimated_days, location=row.location, status=row.status,
        display_order=row.display_order,
    )


def _layer_item(row: MapLayerModel) -> MapLayerItem:
    return MapLayerItem(
        id=str(row.id), code=row.code, name=row.name, layer_type=row.layer_type,
        service_type=row.service_type, service_url=row.service_url,
        service_layer=row.service_layer, year=row.year, source=row.source,
        is_active=row.is_active, display_order=row.display_order,
    )


def _advertisement_item(row: AdvertisementModel) -> AdvertisementItem:
    download_url = row.source_url or f"{MEDIA_PREFIX}/{row.storage_key}"
    return AdvertisementItem(
        id=str(row.id), title=row.title, source_type=row.source_type,
        source_url=row.source_url, original_file_name=row.original_file_name,
        mime_type=row.mime_type, file_size=row.file_size, storage_key=row.storage_key,
        is_active=row.is_active, display_order=row.display_order,
        download_url=download_url,
    )


def _get_row(db: Session, model, item_id, label: str):
    row = db.query(model).filter(model.id == item_id, model.deleted_at.is_(None)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No se encontró {label}.")
    return row


def _geojson_geometry(geometry: dict) -> dict | None:
    if "rings" in geometry:
        return {"type": "Polygon", "coordinates": geometry["rings"]}
    if "paths" in geometry:
        paths = geometry["paths"]
        if len(paths) == 1:
            return {"type": "LineString", "coordinates": paths[0]}
        return {"type": "MultiLineString", "coordinates": paths}
    return None


def _search_map_features(kind: Literal["parcel", "street"], query: str) -> List[MapSearchItem]:
    escaped_query = query.replace("'", "''")
    if kind == "parcel":
        where = f"CodCat LIKE '%{escaped_query}%'"
        fields = "OBJECTID,CodCat,Nro_predio,distrito,comuna,Sbdistrito"
    else:
        where = f"Nombre LIKE '%{escaped_query}%' OR Nombre_V LIKE '%{escaped_query}%'"
        fields = "OBJECTID,Nombre,Nombre_V,Tipo"

    try:
        response = requests.get(
            ARCGIS_SEARCH_URLS[kind],
            params={
                "where": where,
                "outFields": fields,
                "returnGeometry": "true",
                "outSR": "4326",
                "resultRecordCount": 20,
                "f": "json",
            },
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=502, detail="No se pudo consultar el servicio catastral.") from exc

    if data.get("error"):
        raise HTTPException(status_code=502, detail="El servicio catastral rechazó la búsqueda.")

    results = []
    for feature in data.get("features", []):
        attributes = feature.get("attributes") or {}
        geometry = _geojson_geometry(feature.get("geometry") or {})
        if geometry is None:
            continue
        if kind == "parcel":
            code = str(attributes.get("CodCat") or "")
            title = code or "Predio catastral"
            details = ["Predio", attributes.get("Nro_predio"), attributes.get("distrito") and f"Distrito {attributes['distrito']}"]
            subtitle = " · ".join(str(value) for value in details if value)
        else:
            title = str(attributes.get("Nombre_V") or attributes.get("Nombre") or "Vía municipal")
            subtitle = str(attributes.get("Tipo") or "Calle")
        results.append(MapSearchItem(
            id=str(attributes.get("OBJECTID") or title),
            kind=kind,
            title=title,
            subtitle=subtitle,
            geometry=geometry,
        ))
    return results


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, schema="cadastralviewer", service="cadastralviewer")


@router.get("/procedures", response_model=List[ProcedureItem])
def list_public_procedures(db: Session = Depends(get_db)) -> List[ProcedureItem]:
    rows = db.query(CadastralProcedureModel).filter(
        CadastralProcedureModel.status == "published",
        CadastralProcedureModel.deleted_at.is_(None),
    ).order_by(CadastralProcedureModel.display_order, CadastralProcedureModel.name).all()
    return [_procedure_item(row) for row in rows]


@router.get("/procedures/admin", response_model=List[ProcedureItem])
def list_admin_procedures(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> List[ProcedureItem]:
    rows = db.query(CadastralProcedureModel).filter(
        CadastralProcedureModel.deleted_at.is_(None),
    ).order_by(CadastralProcedureModel.display_order, CadastralProcedureModel.name).all()
    return [_procedure_item(row) for row in rows]


@router.post("/procedures", response_model=ProcedureItem, status_code=status.HTTP_201_CREATED)
def create_procedure(
    payload: AdminProcedurePayload,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> ProcedureItem:
    row = CadastralProcedureModel(
        code=payload.code or _slug(payload.name), name=payload.name,
        description=payload.description, category=payload.category or "services",
        icon="📋", requirements=payload.requirements,
        estimated_days=payload.estimated_days, location=payload.location,
        status=payload.status, display_order=payload.display_order,
        created_by=_actor(user), updated_by=_actor(user),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _procedure_item(row)


@router.put("/procedures/{item_id}", response_model=ProcedureItem)
def update_procedure(
    item_id: uuid.UUID, payload: AdminProcedurePayload, db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> ProcedureItem:
    row = _get_row(db, CadastralProcedureModel, item_id, "trámite")
    for field in ("name", "description", "category", "requirements", "estimated_days", "location", "status", "display_order"):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    if payload.code:
        row.code = payload.code
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = _actor(user)
    db.commit()
    db.refresh(row)
    return _procedure_item(row)


@router.delete("/procedures/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_procedure(
    item_id: uuid.UUID, db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> None:
    row = _get_row(db, CadastralProcedureModel, item_id, "trámite")
    row.deleted_at = datetime.now(timezone.utc)
    row.updated_by = _actor(user)
    db.commit()


@router.get("/layers", response_model=List[MapLayerItem])
def list_public_layers(db: Session = Depends(get_db)) -> List[MapLayerItem]:
    rows = db.query(MapLayerModel).filter(
        MapLayerModel.is_active.is_(True), MapLayerModel.deleted_at.is_(None),
    ).order_by(MapLayerModel.display_order, MapLayerModel.name).all()
    return [_layer_item(row) for row in rows]


@router.get("/layers/admin", response_model=List[MapLayerItem])
def list_admin_layers(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> List[MapLayerItem]:
    rows = db.query(MapLayerModel).filter(
        MapLayerModel.deleted_at.is_(None),
    ).order_by(MapLayerModel.display_order, MapLayerModel.name).all()
    return [_layer_item(row) for row in rows]


@router.get("/search", response_model=List[MapSearchItem])
def search_map_features(
    kind: Literal["parcel", "street"],
    q: str = Query(min_length=2, max_length=80),
) -> List[MapSearchItem]:
    return _search_map_features(kind, q.strip())


@router.post("/layers", response_model=MapLayerItem, status_code=status.HTTP_201_CREATED)
def create_layer(
    payload: AdminLayerPayload,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> MapLayerItem:
    row = MapLayerModel(
        code=payload.code or _slug(payload.name), name=payload.name,
        layer_type=payload.layer_type, service_type=payload.service_type,
        service_url=payload.service_url, service_layer=payload.service_layer,
        year=payload.year, source=payload.source, is_active=payload.is_active,
        display_order=payload.display_order, created_by=_actor(user), updated_by=_actor(user),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _layer_item(row)


@router.put("/layers/{item_id}", response_model=MapLayerItem)
def update_layer(
    item_id: uuid.UUID, payload: AdminLayerPayload, db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> MapLayerItem:
    row = _get_row(db, MapLayerModel, item_id, "capa")
    for field in ("name", "layer_type", "service_type", "service_url", "service_layer", "year", "source", "is_active", "display_order"):
        setattr(row, field, getattr(payload, field))
    if payload.code:
        row.code = payload.code
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = _actor(user)
    db.commit()
    db.refresh(row)
    return _layer_item(row)


@router.delete("/layers/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_layer(
    item_id: uuid.UUID, db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> None:
    row = _get_row(db, MapLayerModel, item_id, "capa")
    row.deleted_at = datetime.now(timezone.utc)
    row.updated_by = _actor(user)
    db.commit()


@router.get("/advertisements", response_model=List[AdvertisementItem])
def list_advertisements(db: Session = Depends(get_db)) -> List[AdvertisementItem]:
    rows = db.query(AdvertisementModel).filter(
        AdvertisementModel.is_active.is_(True), AdvertisementModel.deleted_at.is_(None),
    ).order_by(AdvertisementModel.display_order, AdvertisementModel.created_at.desc()).all()
    return [_advertisement_item(row) for row in rows]


@router.get("/advertisements/admin", response_model=List[AdvertisementItem])
def list_advertisements_admin(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> List[AdvertisementItem]:
    rows = db.query(AdvertisementModel).filter(
        AdvertisementModel.deleted_at.is_(None),
    ).order_by(AdvertisementModel.display_order, AdvertisementModel.created_at.desc()).all()
    return [_advertisement_item(row) for row in rows]


@router.post("/advertisements", response_model=AdvertisementItem, status_code=status.HTTP_201_CREATED)
def create_advertisement_link(
    payload: AdminAdvertisementPayload, db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> AdvertisementItem:
    if not payload.source_url.startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail="El enlace debe comenzar con http:// o https://.")
    row = AdvertisementModel(
        title=payload.title, source_type="url", source_url=payload.source_url,
        is_active=payload.is_active, display_order=payload.display_order,
        created_by=_actor(user), updated_by=_actor(user),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _advertisement_item(row)


@router.post("/advertisements/upload", response_model=AdvertisementItem, status_code=status.HTTP_201_CREATED)
async def upload_advertisement(
    file: UploadFile = File(...),
    title: str = Form(""),
    is_active: bool = Form(False),
    display_order: int = Form(0),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> AdvertisementItem:
    extension = Path(file.filename or "").suffix.lower()
    if not (file.content_type or "").startswith("video/") or extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Formato de video no permitido. Usa MP4, WebM, MOV, M4V u OGG.")

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    storage_key = f"{uuid.uuid4().hex}{extension}"
    destination = MEDIA_DIR / storage_key
    file_size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > MAX_VIDEO_BYTES:
                    raise HTTPException(status_code=413, detail="El video supera el límite de 250 MB.")
                output.write(chunk)
        if file_size == 0:
            raise HTTPException(status_code=400, detail="El archivo está vacío.")

        row = AdvertisementModel(
            title=title.strip() or Path(file.filename or "Video").stem,
            source_type="upload", original_file_name=file.filename or storage_key,
            storage_key=storage_key, mime_type=file.content_type or "video/mp4",
            file_size=file_size, is_active=is_active, display_order=display_order,
            created_by=_actor(user), updated_by=_actor(user),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _advertisement_item(row)
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.put("/advertisements/{item_id}", response_model=AdvertisementItem)
def update_advertisement(
    item_id: uuid.UUID, payload: AdvertisementUpdatePayload, db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> AdvertisementItem:
    row = _get_row(db, AdvertisementModel, item_id, "video")
    if payload.title is not None:
        row.title = payload.title
    if payload.source_url is not None:
        if row.source_type != "url":
            raise HTTPException(status_code=422, detail="No se puede reemplazar un archivo subido por un enlace.")
        if not payload.source_url.startswith(("https://", "http://")):
            raise HTTPException(status_code=422, detail="El enlace debe comenzar con http:// o https://.")
        row.source_url = payload.source_url
    if payload.display_order is not None:
        row.display_order = payload.display_order
    if payload.is_active is not None:
        row.is_active = payload.is_active
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = _actor(user)
    db.commit()
    db.refresh(row)
    return _advertisement_item(row)


@router.delete("/advertisements/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_advertisement(
    item_id: uuid.UUID, db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> None:
    row = _get_row(db, AdvertisementModel, item_id, "video")
    row.deleted_at = datetime.now(timezone.utc)
    row.is_active = False
    row.updated_by = _actor(user)
    storage_key = row.storage_key if row.source_type == "upload" else None
    db.commit()
    if storage_key:
        (MEDIA_DIR / storage_key).unlink(missing_ok=True)


@router.get("/advertisements/media/{storage_key}")
def get_advertisement_media(storage_key: str, db: Session = Depends(get_db)):
    if Path(storage_key).name != storage_key:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    record = db.query(AdvertisementModel).filter(
        AdvertisementModel.storage_key == storage_key,
        AdvertisementModel.deleted_at.is_(None),
    ).first()
    path = MEDIA_DIR / storage_key
    if record is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    return FileResponse(path, media_type=record.mime_type or "application/octet-stream", content_disposition_type="inline")
