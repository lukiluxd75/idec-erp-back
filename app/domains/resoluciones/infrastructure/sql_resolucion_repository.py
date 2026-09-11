import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from app.domains.resoluciones.domain.entities.resolucion import PaginaResolucion, Resolucion
from app.domains.resoluciones.domain.ports.resolucion_repository_port import ResolucionRepositoryPort
from app.domains.resoluciones.infrastructure.models import ResolucionModel, ResolucionPaginaModel


class SqlResolucionRepository(ResolucionRepositoryPort):
    """Adaptador de repositorio que implementa ResolucionRepositoryPort contra el
    esquema real `resolutions` (poblado por la app móvil, ver infrastructure/models.py).
    """

    def __init__(self, db: Session):
        self._db = db

    def listar(self, user_sub: str) -> List[Resolucion]:
        modelos = (
            self._db.query(ResolucionModel)
            .options(joinedload(ResolucionModel.paginas))
            .filter(ResolucionModel.user_sub == user_sub, ResolucionModel.deleted_at.is_(None))
            .order_by(ResolucionModel.created_at.desc())
            .all()
        )
        return [self._to_entity(m) for m in modelos]

    def obtener(self, id_resolucion: str, user_sub: str) -> Optional[Resolucion]:
        modelo = self._get_modelo(id_resolucion, user_sub)
        return self._to_entity(modelo) if modelo else None

    def obtener_pagina(self, id_resolucion: str, orden: int, user_sub: str) -> Optional[Tuple[bytes, str]]:
        if self._get_modelo(id_resolucion, user_sub) is None:
            return None

        pagina = (
            self._db.query(ResolucionPaginaModel)
            .filter(
                ResolucionPaginaModel.resolution_id == id_resolucion,
                ResolucionPaginaModel.order_index == orden,
            )
            .first()
        )
        return (pagina.image, pagina.mime) if pagina else None

    def crear(
        self,
        nombre: str,
        nro_resolucion: str,
        paginas: List[Tuple[bytes, str]],
        user_sub: str,
    ) -> Resolucion:
        ahora = datetime.utcnow()
        modelo = ResolucionModel(
            resolution_id=str(uuid.uuid4()),
            name=nombre,
            resolution_number=nro_resolucion,
            status="pendiente_ocr",
            user_sub=user_sub,
            created_at=ahora,
            updated_at=ahora,
        )
        modelo.paginas = [
            ResolucionPaginaModel(
                page_id=str(uuid.uuid4()),
                order_index=i + 1,
                image=contenido,
                mime=mime,
                file_name=f"pagina_{i + 1}.jpg",
            )
            for i, (contenido, mime) in enumerate(paginas)
        ]
        self._db.add(modelo)
        self._db.commit()
        self._db.refresh(modelo)
        return self._to_entity(modelo)

    def guardar_tabla(
        self, id_resolucion: str, tabla: Dict[str, Any], estado: str, user_sub: str
    ) -> Optional[Resolucion]:
        modelo = self._get_modelo(id_resolucion, user_sub)
        if modelo is None:
            return None

        modelo.table_data = tabla
        modelo.status = estado
        modelo.updated_at = datetime.utcnow()
        self._db.commit()
        self._db.refresh(modelo)
        return self._to_entity(modelo)

    def eliminar(self, id_resolucion: str, user_sub: str) -> bool:
        modelo = self._get_modelo(id_resolucion, user_sub)
        if modelo is None:
            return False

        # Soft delete (columna `deleted_at`): la fila y sus páginas se conservan en la
        # BD, solo dejan de listarse/obtenerse — ver el filtro deleted_at IS NULL arriba.
        modelo.deleted_at = datetime.utcnow()
        self._db.commit()
        return True

    def _get_modelo(self, id_resolucion: str, user_sub: str) -> Optional[ResolucionModel]:
        return (
            self._db.query(ResolucionModel)
            .options(joinedload(ResolucionModel.paginas))
            .filter(
                ResolucionModel.resolution_id == id_resolucion,
                ResolucionModel.user_sub == user_sub,
                ResolucionModel.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def _to_entity(modelo: ResolucionModel) -> Resolucion:
        return Resolucion(
            id_resolucion=modelo.resolution_id,
            nombre=modelo.name,
            nro_resolucion=modelo.resolution_number,
            estado=modelo.status,
            fecha_creacion=modelo.created_at,
            paginas=[
                PaginaResolucion(orden=p.order_index, content_type=p.mime)
                for p in sorted(modelo.paginas, key=lambda p: p.order_index)
            ],
            tabla=modelo.table_data,
        )
