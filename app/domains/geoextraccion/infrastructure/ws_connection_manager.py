import logging

from fastapi import WebSocket

logger = logging.getLogger("uvicorn.error")


class CapturasConnectionManager:
    """
    Registro en memoria de los sockets conectados al canal de novedades de Capturas
    (calco de ResolucionesConnectionManager). A diferencia del store de capturas
    (SqlCapturaStore, en Postgres — compartido entre workers), este registro SÍ es
    por proceso: en un backend con varios workers (ej. `--workers 4`), cada uno
    tiene su propio set de conexiones, así que un `avisar_cambio()` disparado por el
    worker que recibió el POST del celular NO llega a un navegador conectado al
    socket de otro worker. Con el store ya compartido, el peor caso pasó de "nunca
    aparece" a "hace falta refrescar la página" — ver useCapturasUpdates.js del
    frontend, que ya asume reconexión simple y no un canal 100% confiable. Resolver
    esto de raíz (que el aviso llegue sin importar el worker) pide algo tipo Redis
    pub/sub entre los procesos — no está montado hoy.
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
