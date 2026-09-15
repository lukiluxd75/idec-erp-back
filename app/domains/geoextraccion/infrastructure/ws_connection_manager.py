import logging

from fastapi import WebSocket

logger = logging.getLogger("uvicorn.error")


class CapturasConnectionManager:
    """
    Registro en memoria de los sockets conectados al canal de novedades de Capturas
    (calco de ResolucionesConnectionManager, mismo dominio de proceso que
    MemoriaCapturaStore). Alcanza con memoria de proceso porque el backend corre en
    un único proceso uvicorn — ver useCapturasUpdates.js del frontend, que ya asume
    reconexión simple.
    """

    def __init__(self):
        self._conexiones: set[WebSocket] = set()

    async def conectar(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._conexiones.add(websocket)

    def desconectar(self, websocket: WebSocket) -> None:
        self._conexiones.discard(websocket)

    async def avisar_cambio(self) -> None:
        """Notifica a todos los sockets conectados que algo cambió (el contenido del
        mensaje no importa: el frontend solo lo usa como disparador para volver a
        pedir la lista de capturas pendientes — ver useCapturasUpdates.js)."""
        caidos = []
        for conexion in self._conexiones:
            try:
                await conexion.send_text("update")
            except Exception:
                caidos.append(conexion)
        for conexion in caidos:
            self._conexiones.discard(conexion)
