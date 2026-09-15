"""
Adaptador en memoria del CapturaStorePort. Guarda las fotos en un dict del propio
proceso Python, no en PostgreSQL — ver la nota "Por qué sin tabla" del plan de este
feature: una captura vive segundos/minutos (hasta que la web la carga en el visor),
no es un registro que haya que consultar después, así que no amerita schema, modelo
ORM ni coordinación con el equipo de base de datos.

Implicancias reales de esta elección (documentadas, no escondidas):
- Un reinicio del backend entre la foto y su carga en la web la pierde — hay que
  volver a sacarla desde el celular.
- Asume un único proceso uvicorn, igual que ResolucionesConnectionManager (ver su
  docstring): sin Redis ni nada distribuido detrás.
- TTL y tope por usuario evitan que capturas nunca reclamadas acumulen memoria.
"""
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from app.domains.geoextraccion.domain.entities.captura import Captura
from app.domains.geoextraccion.domain.ports.captura_store_port import CapturaStorePort

TTL = timedelta(minutes=30)
MAX_CAPTURAS_POR_USUARIO = 5


@dataclass
class _CapturaAlmacenada:
    id_captura: str
    mime: str
    contenido: bytes
    fecha_creacion: datetime


class MemoriaCapturaStore(CapturaStorePort):
    def __init__(self):
        self._por_usuario: "OrderedDict[str, OrderedDict[str, _CapturaAlmacenada]]" = OrderedDict()
        self._lock = threading.Lock()

    def _purgar_vencidas(self, user_sub: str) -> None:
        """Se llama siempre con el lock ya tomado. Saca las capturas del usuario que
        superaron el TTL — no hay tarea de fondo, se purga de forma perezosa en cada
        acceso, que alcanza para el volumen esperado (fotos de un puñado de usuarios)."""
        capturas = self._por_usuario.get(user_sub)
        if not capturas:
            return
        limite = datetime.now(timezone.utc) - TTL
        vencidas = [id_ for id_, c in capturas.items() if c.fecha_creacion < limite]
        for id_ in vencidas:
            del capturas[id_]
        if not capturas:
            del self._por_usuario[user_sub]

    def guardar(self, contenido: bytes, mime: str, user_sub: str) -> Captura:
        with self._lock:
            self._purgar_vencidas(user_sub)
            capturas = self._por_usuario.setdefault(user_sub, OrderedDict())
            while len(capturas) >= MAX_CAPTURAS_POR_USUARIO:
                capturas.popitem(last=False)  # descarta la más vieja (FIFO)

            id_captura = str(uuid.uuid4())
            almacenada = _CapturaAlmacenada(
                id_captura=id_captura,
                mime=mime,
                contenido=contenido,
                fecha_creacion=datetime.now(timezone.utc),
            )
            capturas[id_captura] = almacenada
            return Captura(id_captura=id_captura, mime=mime, fecha_creacion=almacenada.fecha_creacion)

    def listar_pendientes(self, user_sub: str) -> List[Captura]:
        with self._lock:
            self._purgar_vencidas(user_sub)
            capturas = self._por_usuario.get(user_sub, OrderedDict())
            return [
                Captura(id_captura=c.id_captura, mime=c.mime, fecha_creacion=c.fecha_creacion)
                for c in reversed(capturas.values())
            ]

    def obtener_imagen(self, id_captura: str, user_sub: str) -> Optional[Tuple[bytes, str]]:
        with self._lock:
            self._purgar_vencidas(user_sub)
            capturas = self._por_usuario.get(user_sub)
            if not capturas or id_captura not in capturas:
                return None
            almacenada = capturas[id_captura]
            return almacenada.contenido, almacenada.mime

    def descartar(self, id_captura: str, user_sub: str) -> bool:
        with self._lock:
            self._purgar_vencidas(user_sub)
            capturas = self._por_usuario.get(user_sub)
            if not capturas or id_captura not in capturas:
                return False
            del capturas[id_captura]
            if not capturas:
                del self._por_usuario[user_sub]
            return True
