import io

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

from app.domains.geoextraccion.application.use_cases import (
    GenerarShapefileUseCase,
    FusionarShapefilesUseCase,
)
from app.domains.geoextraccion.domain.entities.terreno import Punto, Terreno
from app.domains.geoextraccion.presentation.deps import (
    get_generar_shapefile_use_case,
    get_fusionar_shapefiles_use_case,
)
from app.domains.geoextraccion.presentation.schemas.shapefile_schema import GenerarShapefileRequest
from app.domains.seguridad.contracts import UserProfile, get_current_user

router = APIRouter(tags=["Geoextracción"])


@router.post("/shapefiles")
def generar_shapefile(
    payload: GenerarShapefileRequest,
    use_case: GenerarShapefileUseCase = Depends(get_generar_shapefile_use_case),
    _usuario: UserProfile = Depends(get_current_user),
):
    """Genera un Shapefile (ZIP) a partir de uno o más terrenos digitalizados."""
    terrenos = [
        Terreno(
            puntos=[Punto(x=p.x, y=p.y) for p in terreno.puntos],
            atributos=terreno.atributos,
        )
        for terreno in payload.terrenos
    ]
    contenido = use_case.execute(terrenos)

    nombre_archivo = "terreno_individual.zip" if len(terrenos) == 1 else "capa_masiva.zip"
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"},
    )


@router.post("/shapefiles/fusiones")
async def fusionar_shapefiles(
    files: list[UploadFile] = File(...),
    use_case: FusionarShapefilesUseCase = Depends(get_fusionar_shapefiles_use_case),
    _usuario: UserProfile = Depends(get_current_user),
):
    """Une varios Shapefiles (ZIP) subidos en una sola capa."""
    archivos = [await archivo.read() for archivo in files]
    contenido = use_case.execute(archivos)

    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=shapefiles_unidos.zip"},
    )
