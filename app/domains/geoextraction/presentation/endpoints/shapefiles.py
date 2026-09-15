import io

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

from app.domains.geoextraction.application.use_cases import (
    GenerateShapefileUseCase,
    MergeShapefilesUseCase,
)
from app.domains.geoextraction.domain.entities.parcel import Point, Parcel
from app.domains.geoextraction.presentation.deps import (
    get_generate_shapefile_use_case,
    get_merge_shapefiles_use_case,
)
from app.domains.geoextraction.presentation.schemas.shapefile_schema import GenerateShapefileRequest
from app.domains.security.contracts import UserProfile, get_current_user

router = APIRouter(tags=["Geoextracción"])


@router.post("/shapefiles")
def generate_shapefile(
    payload: GenerateShapefileRequest,
    use_case: GenerateShapefileUseCase = Depends(get_generate_shapefile_use_case),
    _user: UserProfile = Depends(get_current_user),
):
    """Generate a Shapefile (ZIP) from one or more digitized parcels.
    Request JSON keeps Spanish keys (puntos, atributos, terrenos) for the front."""
    parcels = [
        Parcel(
            points=[Point(x=p.x, y=p.y) for p in terreno.puntos],
            attributes=terreno.atributos,
        )
        for terreno in payload.terrenos
    ]
    content = use_case.execute(parcels)

    file_name = "terreno_individual.zip" if len(parcels) == 1 else "capa_masiva.zip"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={file_name}"},
    )


@router.post("/shapefiles/merges")
async def merge_shapefiles(
    files: list[UploadFile] = File(...),
    use_case: MergeShapefilesUseCase = Depends(get_merge_shapefiles_use_case),
    _user: UserProfile = Depends(get_current_user),
):
    """Merge several uploaded Shapefile ZIPs into a single layer."""
    archives = [await f.read() for f in files]
    content = use_case.execute(archives)

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=shapefiles_unidos.zip"},
    )
