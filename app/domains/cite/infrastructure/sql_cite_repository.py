"""
Implementación SQL del CiteRepositoryPort.
Toda la lógica de concurrencia vive aquí; los use_cases son ignorantes del motor de BD.

Estrategia anti-concurrencia:
  - `SELECT ... FOR UPDATE` bloquea el ÚLTIMO registro de documento_cite
    para id_configuracion dado. Si dos hilos llegan simultáneamente, el segundo
    espera a que el primero commitee antes de leer el MAX(correlativo) actualizado.
  - El UNIQUE constraint (id_configuracion, correlativo) actúa como red de seguridad
    de nivel BD: cualquier race-condition residual dispara IntegrityError, que se
    convierte en CiteGenerationException con mensaje descriptivo.
"""
import logging
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.domains.cite.domain.entities import (
    Area,
    ConfiguracionCite,
    DocumentoCite,
    Gestion,
)
from app.domains.cite.domain.exceptions import CiteGenerationException
from app.domains.cite.domain.ports import CiteRepositoryPort
from app.domains.cite.infrastructure.models import (
    AreaModel,
    ConfiguracionCiteModel,
    DocumentoCiteModel,
    GestionModel,
)

logger = logging.getLogger("uvicorn.error")


def _map_gestion(m: GestionModel) -> Gestion:
    return Gestion(
        id_gestion=m.id_gestion,
        anio=m.anio,
        fecha_inicial=m.fecha_inicial,
        fecha_final=m.fecha_final,
        activa=m.activa,
    )


def _map_area(m: AreaModel) -> Area:
    return Area(
        id_area=m.id_area,
        nombre=m.nombre,
        tipo=m.tipo,
        id_area_padre=m.id_area_padre,
    )


def _map_configuracion(m: ConfiguracionCiteModel) -> ConfiguracionCite:
    return ConfiguracionCite(
        id_configuracion=m.id_configuracion,
        id_area=m.id_area,
        id_gestion=m.id_gestion,
        prefijo=m.prefijo,
        activo=m.activo,
        gestion_activa=m.gestion.activa,  # requiere eager-load o lazy (default OK aquí)
    )


def _map_documento(m: DocumentoCiteModel) -> DocumentoCite:
    return DocumentoCite(
        id_documento=m.id_documento,
        id_configuracion=m.id_configuracion,
        prefijo=m.prefijo,
        correlativo=m.correlativo,
        codigo_cite_completo=m.codigo_cite_completo,
        fecha_generacion=m.fecha_generacion,
        referencia=m.referencia,
        id_funcionario_remitente=m.id_funcionario_remitente,
    )


class SqlCiteRepository(CiteRepositoryPort):

    def __init__(self, db: Session):
        self._db = db

    # ── Gestión ──────────────────────────────────────────────────────────────

    def get_gestion_activa(self):
        m = self._db.query(GestionModel).filter(GestionModel.activa == True).first()  # noqa: E712
        return _map_gestion(m) if m else None

    def get_gestion_by_id(self, id_gestion: int):
        m = self._db.get(GestionModel, id_gestion)
        return _map_gestion(m) if m else None

    # ── Área ─────────────────────────────────────────────────────────────────

    def get_area_by_id(self, id_area: int):
        m = self._db.get(AreaModel, id_area)
        return _map_area(m) if m else None

    # ── ConfiguracionCite ────────────────────────────────────────────────────

    def get_configuracion_by_id(self, id_configuracion: int):
        m = (
            self._db.query(ConfiguracionCiteModel)
            .filter(ConfiguracionCiteModel.id_configuracion == id_configuracion)
            .first()
        )
        return _map_configuracion(m) if m else None

    def prefijo_existe_en_gestion(self, id_gestion: int, prefijo: str) -> bool:
        return (
            self._db.query(ConfiguracionCiteModel)
            .filter(
                ConfiguracionCiteModel.id_gestion == id_gestion,
                ConfiguracionCiteModel.prefijo == prefijo,
            )
            .count()
        ) > 0

    def crear_configuracion(self, id_area: int, id_gestion: int, prefijo: str) -> ConfiguracionCite:
        nuevo = ConfiguracionCiteModel(
            id_area=id_area,
            id_gestion=id_gestion,
            prefijo=prefijo,
            activo=True,
        )
        self._db.add(nuevo)
        self._db.flush()   # obtiene id_configuracion sin cerrar la transacción externa
        self._db.refresh(nuevo)
        return _map_configuracion(nuevo)

    # ── DocumentoCite (core transaccional) ───────────────────────────────────

    def generar_cite(
        self,
        id_configuracion: int,
        referencia: str,
        id_funcionario_remitente: int,
    ) -> DocumentoCite:
        """
        Transacción serializable mediante SELECT ... FOR UPDATE.

        Flujo:
          1. Lock del configuracion_cite (FOR UPDATE) para serializar generaciones
             concurrentes del MISMO prefijo/gestión.
          2. MAX(correlativo) + 1, o 1 si la tabla aún está vacía para esa config.
          3. INSERT físico del prefijo (columna generada no se toca).
          4. REFRESH para leer codigo_cite_completo calculado por MySQL.
        """
        try:
            # ── 1. Bloqueo optimista de la fila de configuración ──────────────
            # Al lockear configuracion_cite garantizamos serialización por prefijo:
            # dos requests del mismo id_configuracion se encolan aquí.
            self._db.execute(
                text(
                    "SELECT id_configuracion FROM configuracion_cite "
                    "WHERE id_configuracion = :id FOR UPDATE"
                ),
                {"id": id_configuracion},
            )

            # ── 2. Obtener el próximo correlativo ─────────────────────────────
            # Se lee DENTRO de la misma transacción, tras adquirir el lock,
            # por lo que refleja el valor commiteado por cualquier request previo.
            resultado = self._db.execute(
                select(func.max(DocumentoCiteModel.correlativo)).where(
                    DocumentoCiteModel.id_configuracion == id_configuracion
                )
            ).scalar()

            siguiente_correlativo: int = 1 if resultado is None else resultado + 1

            # ── 3. Leer prefijo desde la configuración (ya en sesión/caché) ───
            cfg_model = self._db.get(ConfiguracionCiteModel, id_configuracion)
            prefijo = cfg_model.prefijo

            # ── 4. Insertar con prefijo físico ────────────────────────────────
            # `codigo_cite_completo` es GENERATED STORED: NO se incluye en el INSERT.
            # SQLAlchemy lo omite automáticamente por ser Computed; aquí lo reforzamos
            # con el mapeo explícito de `prefijo` y `correlativo`.
            nuevo_doc = DocumentoCiteModel(
                id_configuracion=id_configuracion,
                prefijo=prefijo,
                correlativo=siguiente_correlativo,
                fecha_generacion=datetime.utcnow(),
                referencia=referencia,
                id_funcionario_remitente=id_funcionario_remitente,
            )
            self._db.add(nuevo_doc)
            self._db.flush()   # dispara el INSERT; MySQL calcula codigo_cite_completo
            self._db.refresh(nuevo_doc)  # re-lee la fila, incluyendo la columna GENERATED

            return _map_documento(nuevo_doc)

        except IntegrityError as exc:
            self._db.rollback()
            logger.error("CITE IntegrityError (probable race condition): %s", exc)
            raise CiteGenerationException(
                "Conflicto de correlativo al generar el CITE. "
                "Reintente la operación (dos solicitudes simultáneas colisionaron)."
            ) from exc

        except OperationalError as exc:
            self._db.rollback()
            logger.error("CITE OperationalError (lock timeout / deadlock): %s", exc)
            raise CiteGenerationException(
                "Error de base de datos al bloquear el correlativo. "
                "El servidor puede estar bajo alta carga; reintente en unos segundos."
            ) from exc
