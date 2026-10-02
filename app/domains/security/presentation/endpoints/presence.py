"""
"Celular conectado" ligado a la SESIÓN de la app móvil.

Vive en `security` porque lo que describe es una sesión, y este dominio es el
dueño del login y del refresh. El estado, en cambio, es compartido
(app/core/presence, en Postgres): los cuatro workers tienen que responder lo
mismo, y cualquier módulo del ERP puede leerlo para su indicador.

La app móvil solo tiene que hacer dos llamadas:

    POST   /api/presence/session   -> al iniciar sesión (y cada tanto, opcional)
    DELETE /api/presence/session   -> al cerrar sesión

Y aun si no las hiciera, el indicador se enciende solo: `login` y `refresh`
(ver endpoints/auth.py) registran la sesión cuando la petición no viene de un
navegador de escritorio, y la app ya llama a los dos.
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.core.presence import CHANNEL_SESSION, SqlPresenceStore, device_id_for_request
from app.core.utils.user_agent import looks_like_phone
from app.domains.security.domain.entities.user import UserProfile
from app.domains.security.presentation.deps import get_current_user
from app.domains.security.presentation.schemas.auth_schema import PhonePresenceOut

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/presence", tags=["Presencia del celular"])


@router.post("/session", response_model=PhonePresenceOut)
def open_session(
    request: Request,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    """La app móvil acaba de iniciar sesión: a partir de aquí el escritorio
    muestra "Celular conectado".

    No filtra por User-Agent: si alguien llama a esto con un token válido es
    porque quiere declararse como dispositivo conectado, y el único cliente que
    lo llama es la app. Llamarlo de nuevo cada cierto tiempo renueva la sesión
    (ver SESSION_TTL), que es lo que mantiene el indicador encendido si la app
    se queda abierta sin subir nada.
    """
    store = SqlPresenceStore(db)
    store.open_session(user.sub, CHANNEL_SESSION, device_id_for_request(user.sub, request.headers.get("user-agent")))
    return PhonePresenceOut(mobile_connected=True)


@router.delete("/session", response_model=PhonePresenceOut)
def close_session(
    db: Session = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    """La app móvil cerró sesión: el indicador se apaga de inmediato, en todos
    los módulos.

    Borra toda presencia de celular de la cuenta, no solo la del `device_id`
    que mandó esta petición ni solo la del canal de sesión, por dos razones:

      * la app no tiene por qué repetir en el logout el mismo User-Agent con el
        que inició sesión, y una fila que no se puede identificar dejaría el
        indicador encendido hasta que expirara el TTL;
      * si la app acababa de subir fotos, su presencia de "actividad reciente"
        seguiría viva hasta tres minutos después de cerrar sesión.
    """
    SqlPresenceStore(db).close_all_mobile(user.sub)
    return PhonePresenceOut(mobile_connected=False)


@router.get("/session", response_model=PhonePresenceOut)
def get_session(
    db: Session = Depends(get_db),
    user: UserProfile = Depends(get_current_user),
):
    """Si esta cuenta tiene sesión de celular abierta. Sirve para que la propia
    app verifique que quedó registrada, y para diagnosticar desde el escritorio
    por qué el indicador está apagado."""
    return PhonePresenceOut(
        mobile_connected=SqlPresenceStore(db).is_mobile_present(user.sub, CHANNEL_SESSION)
    )


def record_session_from_request(request: Request, db: Session, user_sub: str) -> None:
    """Registra sesión de celular desde el login o el refresh, para que el
    indicador funcione SIN cambios en la app móvil.

    Aquí sí se filtra por User-Agent, al contrario que en `open_session`: por
    este camino pasa también el login del navegador de escritorio, que no debe
    encender nada. `looks_like_phone` acepta navegadores de celular y cualquier
    cliente que no sea un navegador -- que es lo que manda una app nativa
    (`okhttp/4.12.0`, `Dart/3.3 (dart:io)`), y la razón por la que la versión
    anterior de esto nunca se encendía.

    Nunca lanza: un fallo aquí no puede tumbar un login.
    """
    try:
        user_agent = request.headers.get("user-agent", "")
        if not looks_like_phone(user_agent):
            return
        SqlPresenceStore(db).open_session(
            user_sub, CHANNEL_SESSION, device_id_for_request(user_sub, user_agent)
        )
    except Exception:
        logger.warning("presence: no se pudo registrar la sesion movil", exc_info=True)
