"""
Adaptador Postgres del CapturaStorePort. Reemplaza a MemoriaCapturaStore: con el
backend corriendo en varios workers (`--workers 4` en producción), cada proceso
tenía su propia memoria separada, así que una foto guardada por el worker que
atendió el POST del celular era invisible para el worker que atendía el GET de la
web — este adaptador la persiste en la misma Postgres que ya comparten los 4
procesos, así cualquiera de ellos ve lo mismo.

Sigue sin ser un registro de negocio: TTL de 30 min (purgado perezosamente, sin job
de fondo) y tope por usuario, igual que la versión en memoria — ver su docstring
para el razonamiento completo. La diferencia real de este cambio es solo el
"dónde", no el "qué tan permanente".
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.domains.geoextraccion.domain.entities.captura import Captura
from app.domains.geoextraccion.domain.ports.captura_store_port import CapturaStorePort
from app.domains.geoextraccion.infrastructure.models import CapturaModel

TTL = timedelta(minutes=30)
MAX_CAPTURAS_POR_USUARIO = 5


def _a_entidad(fila: CapturaModel) -> Captura:
    return Captura(id_captura=fila.id_captura, mime=fila.mime, fecha_creacion=fila.fecha_creacion)


class SqlCapturaStore(CapturaStorePort):
    def __init__(self, db: Session):
        self._db = db

    def _purgar_vencidas(self) -> None:
        """Borra las capturas (de cualquier usuario) que superaron el TTL. Se llama
        al principio de cada operación pública — no hay tarea de fondo, alcanza con
        purgar de forma perezosa para el volumen esperado."""
        limite = datetime.now(timezone.utc) - TTL
        self._db.query(CapturaModel).filter(CapturaModel.fecha_creacion < limite).delete(
            synchronize_session=False
        )
        self._db.commit()

    def guardar(self, contenido: bytes, mime: str, user_sub: str) -> Captura:
        self._purgar_vencidas()

        pendientes = (
            self._db.query(CapturaModel)
            .filter(CapturaModel.user_sub == user_sub)
            .order_by(CapturaModel.fecha_creacion.asc())
            .all()
        )
        while len(pendientes) >= MAX_CAPTURAS_POR_USUARIO:
            self._db.delete(pendientes.pop(0))  # descarta la más vieja (FIFO)

        fila = CapturaModel(
            id_captura=str(uuid.uuid4()),
            user_sub=user_sub,
            mime=mime,
            imagen=contenido,
            fecha_creacion=datetime.now(timezone.utc),
        )
        self._db.add(fila)
        self._db.commit()
        self._db.refresh(fila)
        return _a_entidad(fila)

    def listar_pendientes(self, user_sub: str) -> List[Captura]:
        self._purgar_vencidas()
        filas = (
            self._db.query(CapturaModel)
            .filter(CapturaModel.user_sub == user_sub)
            .order_by(CapturaModel.fecha_creacion.desc())
            .all()
        )
        return [_a_entidad(f) for f in filas]

    def obtener_imagen(self, id_captura: str, user_sub: str) -> Optional[Tuple[bytes, str]]:
        self._purgar_vencidas()
        fila = (
            self._db.query(CapturaModel)
            .filter(CapturaModel.id_captura == id_captura, CapturaModel.user_sub == user_sub)
            .first()
        )
        if fila is None:
            return None
        return fila.imagen, fila.mime

    def descartar(self, id_captura: str, user_sub: str) -> bool:
        self._purgar_vencidas()
        fila = (
            self._db.query(CapturaModel)
            .filter(CapturaModel.id_captura == id_captura, CapturaModel.user_sub == user_sub)
            .first()
        )
        if fila is None:
            return False
        self._db.delete(fila)
        self._db.commit()
        return True
