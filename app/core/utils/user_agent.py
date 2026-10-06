import re

_MOBILE_RE = re.compile(r"Mobi|Android|iPhone|iPad|iPod", re.IGNORECASE)

# Un navegador, cualquiera, se anuncia como "Mozilla/5.0 ...".
_BROWSER_RE = re.compile(r"Mozilla/", re.IGNORECASE)
_NATIVE_CLIENT_RE = re.compile(
    r"okhttp|retrofit|Dart/|dart:io|ktor|CFNetwork|Darwin/|AFNetworking|Alamofire"
    r"|python-requests|axios|node-fetch|Apache-HttpClient|Go-http-client|libcurl|curl/",
    re.IGNORECASE,
)


def is_mobile_user_agent(user_agent: str) -> bool:
    """Heurística de dispositivo a partir del User-Agent del handshake del
    WebSocket — usada por el indicador "celular conectado" (ver
    CapturesConnectionManager / ResolutionsConnectionManager). No pretende ser
    exacta, solo distinguir un navegador de celular de uno de escritorio.

    OJO: solo reconoce *navegadores* de celular. Una app nativa manda
    `okhttp/4.12.0` o `Dart/3.3 (dart:io)`, que no contienen ninguna de estas
    palabras — para eso está `looks_like_phone`.
    """
    return bool(_MOBILE_RE.search(user_agent or ""))


def is_native_app_user_agent(user_agent: str) -> bool:
    """True cuando la petición no viene de un navegador.

    Dos caminos, porque un User-Agent se puede cambiar y no se puede confiar en
    una lista cerrada:

    * coincide con un cliente HTTP nativo conocido (okhttp, Dart, ktor,
      CFNetwork...), o
    * no se anuncia como navegador (`Mozilla/`) en absoluto.

    El segundo es el que cubre los casos que no previmos: la app móvil del IDEC
    puede cambiar de librería HTTP y seguiría reconociéndose. El riesgo es al
    revés -- un script de consola del mismo usuario contaría como "la app" --
    y es aceptable: nadie sube fotos de carpetas con curl, y el peor efecto
    sería un indicador encendido de más.
    """
    ua = (user_agent or "").strip()
    if not ua:
        # Sin User-Agent no hay nada que afirmar.
        return False
    if _NATIVE_CLIENT_RE.search(ua):
        return True
    return not _BROWSER_RE.search(ua)


def looks_like_phone(user_agent: str) -> bool:
    """La pregunta que de verdad importa para el indicador "celular conectado":
    ¿esta petición viene del celular del arquitecto y no del navegador de su PC?

    Sí cuando es un navegador de celular (`is_mobile_user_agent`) o cuando no es
    un navegador en absoluto (`is_native_app_user_agent`, el caso de la app).
    No cuando es un navegador de escritorio, que es el caso que hay que excluir:
    el arquitecto también sube fotos arrastrándolas desde Windows (ver
    captureUpload.js en el frontend) y eso no debe encender nada.
    """
    return is_mobile_user_agent(user_agent) or is_native_app_user_agent(user_agent)
