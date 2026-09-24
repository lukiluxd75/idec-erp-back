from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.templates.domain.entities.cite import CiteConfiguracion, CiteGenerado, render_cite_formato
from app.domains.templates.domain.exceptions import DuplicateCiteConfigurationException
from app.domains.templates.domain.ports.cite_repository_port import CiteRepositoryPort
from app.domains.templates.infrastructure.models import (
    CiteConfiguracionModel,
    CiteCorrelativoModel,
    CiteGeneradoModel,
)


class SqlCiteRepository(CiteRepositoryPort):
    """Repository adapter implementing CiteRepositoryPort against the real
    `plantillas_dinamicas.cite_*` tables (see infrastructure/models.py)."""

    def __init__(self, db: Session):
        self._db = db

    def list_configuraciones(self) -> List[CiteConfiguracion]:
        models = self._db.query(CiteConfiguracionModel).order_by(CiteConfiguracionModel.nombre).all()
        return [self._configuracion_to_entity(m) for m in models]

    def get_configuracion(
        self, area_codigo: str, tipo_documento_codigo: str
    ) -> Optional[CiteConfiguracion]:
        model = (
            self._db.query(CiteConfiguracionModel)
            .filter(
                CiteConfiguracionModel.area_codigo == area_codigo,
                CiteConfiguracionModel.tipo_documento_codigo == tipo_documento_codigo,
            )
            .first()
        )
        return self._configuracion_to_entity(model) if model else None

    def create_configuracion(self, configuracion: CiteConfiguracion) -> CiteConfiguracion:
        model = CiteConfiguracionModel(
            area_codigo=configuracion.area_codigo,
            tipo_documento_codigo=configuracion.tipo_documento_codigo,
            nombre=configuracion.nombre,
            formato=configuracion.formato,
            longitud_numero=configuracion.longitud_numero,
            reinicia_por_gestion=configuracion.reinicia_por_gestion,
            activa=configuracion.activa,
        )
        self._db.add(model)
        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise DuplicateCiteConfigurationException(
                f"Ya existe una sigla para el área '{configuracion.area_codigo}' y tipo de "
                f"documento '{configuracion.tipo_documento_codigo}'."
            ) from exc
        self._db.refresh(model)
        return self._configuracion_to_entity(model)

    def generate(
        self,
        configuracion: CiteConfiguracion,
        gestion: int,
        documento_id: Optional[int],
        tramite_id: Optional[int],
        user_sub: str,
    ) -> CiteGenerado:
        numero = self._next_numero(configuracion.id, gestion, configuracion.reinicia_por_gestion)

        codigo = render_cite_formato(
            configuracion.formato,
            area=configuracion.area_codigo,
            tipo=configuracion.tipo_documento_codigo,
            numero=str(numero).zfill(configuracion.longitud_numero),
            gestion=gestion,
        )

        model = CiteGeneradoModel(
            cite_configuracion_id=configuracion.id,
            documento_id=documento_id,
            gestion=gestion,
            numero_correlativo=numero,
            codigo=codigo,
            tramite_id=tramite_id,
            estado="GENERADO",
            generado_por=user_sub,
        )
        self._db.add(model)
        self._db.commit()
        self._db.refresh(model)
        return self._generado_to_entity(model)

    def _next_numero(self, configuracion_id: int, gestion: int, reinicia_por_gestion: bool) -> int:
        """Locks (or creates) the counter row for this (configuracion, gestion)
        and returns the next number, already persisted -- callers must be inside
        a transaction that commits the same object graph (see generate()).

        `with_for_update()` blocks a second concurrent caller on the same row
        until this transaction commits, so two requests generating a CITE for
        the same sigla at the same time never get the same número_correlativo
        (see database/plantillas_dinamicas_postgresql.sql's comment on
        cite_correlativo)."""
        row = (
            self._db.query(CiteCorrelativoModel)
            .filter(
                CiteCorrelativoModel.cite_configuracion_id == configuracion_id,
                CiteCorrelativoModel.gestion == gestion,
            )
            .with_for_update()
            .first()
        )

        if row is None:
            ultimo_numero = 0
            if not reinicia_por_gestion:
                # Carry the running total forward into the new gestion instead of
                # starting over -- the most recent row for ANY gestion of this
                # configuracion has the last number actually handed out.
                previous = (
                    self._db.query(CiteCorrelativoModel)
                    .filter(CiteCorrelativoModel.cite_configuracion_id == configuracion_id)
                    .order_by(CiteCorrelativoModel.gestion.desc())
                    .with_for_update()
                    .first()
                )
                if previous is not None:
                    ultimo_numero = previous.ultimo_numero
            row = CiteCorrelativoModel(
                cite_configuracion_id=configuracion_id, gestion=gestion, ultimo_numero=ultimo_numero
            )
            self._db.add(row)

        row.ultimo_numero += 1
        self._db.flush()
        return row.ultimo_numero

    def list_generados(self) -> List[CiteGenerado]:
        models = self._db.query(CiteGeneradoModel).order_by(CiteGeneradoModel.generado_en.desc()).all()
        return [self._generado_to_entity(m) for m in models]

    @staticmethod
    def _configuracion_to_entity(model: CiteConfiguracionModel) -> CiteConfiguracion:
        return CiteConfiguracion(
            id=model.id,
            area_codigo=model.area_codigo,
            tipo_documento_codigo=model.tipo_documento_codigo,
            nombre=model.nombre,
            formato=model.formato,
            longitud_numero=model.longitud_numero,
            reinicia_por_gestion=model.reinicia_por_gestion,
            activa=model.activa,
        )

    @staticmethod
    def _generado_to_entity(model: CiteGeneradoModel) -> CiteGenerado:
        return CiteGenerado(
            id=model.id,
            cite_configuracion_id=model.cite_configuracion_id,
            gestion=model.gestion,
            numero_correlativo=model.numero_correlativo,
            codigo=model.codigo,
            documento_id=model.documento_id,
            tramite_id=model.tramite_id,
            estado=model.estado,
            motivo_anulacion=model.motivo_anulacion,
            generado_en=model.generado_en,
            generado_por=model.generado_por,
        )
