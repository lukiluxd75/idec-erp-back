"""
La pasada final de la lectura: qwen3-vl mirando la foto, en las computadoras de
los arquitectos.

Por qué existe. El resto del carril lee la hoja como texto -- PaddleOCR la
convierte en caracteres y las reglas buscan la etiqueta al lado del valor -- y
eso alcanza mientras el dato esté escrito en una línea. El número del notario no
lo está: vive en un sello redondo, con la leyenda curvada y encimada al título, y
a un centímetro de él el formulario trae impreso "Resolución Ministerial Nº
57/2020". Para una hoja ya convertida en una tira de caracteres los dos son una
marca de número con un número detrás, y por eso salía 57 donde iba 37. El modelo
sí ve cuál de los dos está dentro del sello, porque ve la hoja.

Qué cuesta. Entre veinte y treinta segundos por foto, que es lo que tarda el
modelo de visión en una de esas máquinas. Por eso esto no reemplaza al OCR ni
transcribe la hoja: se le pregunta un puñado de campos -- los que la carpeta
declara con `vision_hint` y siguen sin resolver -- y quien consume corta en
cuanto los tiene (una foto por llamada, ver VisionReadingPort).

Dónde corre. En las mismas computadoras que el carril del comprobante toma
prestadas, a través del contrato de digitización: `host_provider(model)` las
devuelve de menos a más ocupada y se prueba una por una, con
FOLDER_VISION_OLLAMA_URL como último recurso. Nunca dentro de una petición: esto
va en la lectura en servidor, que corre en segundo plano.
"""
import base64
import json
import logging
import re
import time
from contextlib import nullcontext
from typing import Any, Callable, ContextManager, Dict, List, Optional, Sequence

import cv2
import numpy as np
import requests

from app.core.config.settings import settings
from app.domains.folder_analysis.domain.exceptions import (
    VisionReadingStoppedException,
    VisionReadingUnavailableException,
)
from app.domains.folder_analysis.domain.ports import VisionReadingPort

logger = logging.getLogger("uvicorn.error")

SYSTEM_PROMPT = """Eres un asistente que LEE fotos de documentos notariales y municipales de Bolivia
(formularios notariales, declaraciones juradas, actas). Te dan la foto de UNA hoja y la lista de datos
que hay que sacar de ella.
Devuelve SOLO un JSON con exactamente las claves pedidas.
Reglas estrictas:
- copia cada valor tal como está escrito en la hoja: no corrijas la ortografía ni completes lo que falta;
- si el dato no está en esta hoja, o no se puede leer, usa null: nunca lo deduzcas ni lo inventes;
- mira dónde está cada valor antes de copiarlo: en estas hojas hay varios números parecidos
  (el del sello, el de una resolución, el de la cédula, el del trámite) y cada uno es de otra cosa;
- no agregues claves que no estén en la lista."""

# Las computadoras son de los arquitectos: se les devuelve la VRAM enseguida.
KEEP_ALIVE = "2m"

# El modelo mira la foto, no la transcribe: la respuesta son unos pocos valores.
NUM_PREDICT = 512

# A cuánto se achica la foto antes de mandarla.
MAX_WIDTH = 1600
JPEG_QUALITY = 88

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _for_the_model(content: bytes) -> bytes:
    """La foto al ancho con que se la manda. Una foto que no se pudo abrir o
    achicar se manda tal cual: achicarla es un ahorro, no un requisito."""
    try:
        image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[1] <= MAX_WIDTH:
            return content
        scale = MAX_WIDTH / image.shape[1]
        smaller = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode(".jpg", smaller, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        return encoded.tobytes() if ok else content
    except Exception:
        logger.exception("Folder analysis: no se pudo achicar la foto para el modelo de visión")
        return content


def _json_object(content: str) -> str:
    """El objeto JSON que hay dentro de la respuesta. Pedir `format: json` casi
    siempre alcanza, pero un modelo que razona todavía puede dejar su cadena de
    pensamiento alrededor, y una palabra suelta antes de la llave tiraría a la
    basura una lectura perfectamente buena."""
    match = _JSON_OBJECT.search(_THINK_BLOCK.sub("", content or ""))
    return match.group(0) if match is not None else (content or "")


class OllamaVisionReader(VisionReadingPort):
    """`host_provider(model)` (el pool de digitización, cableado en
    presentation/deps.py) devuelve las computadoras que hoy tienen el modelo, la
    menos ocupada primero; se prueba una por una y FOLDER_VISION_OLLAMA_URL queda
    de último recurso, así que una máquina apagada no para la pasada."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        host_provider: Optional[Callable[[str], List[str]]] = None,
        borrow: Optional[Callable[[str, float], ContextManager[None]]] = None,
    ):
        self._base = (base_url if base_url is not None else settings.FOLDER_VISION_OLLAMA_URL).rstrip("/")
        self._model = model if model is not None else settings.FOLDER_VISION_MODEL
        self._timeout = timeout or settings.FOLDER_VISION_TIMEOUT_SECONDS
        self._host_provider = host_provider
        self._borrow = borrow or (lambda _host, _seconds: nullcontext(lambda: False))

    def is_configured(self) -> bool:
        """Un FOLDER_VISION_MODEL vacío apaga la pasada: la lectura se queda en el
        OCR, las reglas y el sello, que es lo que había antes de esto."""
        if not self._model:
            return False
        return bool(self._base) or self._host_provider is not None

    def hosts(self) -> List[str]:
        hosts = list(self._host_provider(self._model)) if self._host_provider else []
        if self._base and self._base not in hosts:
            hosts.append(self._base)
        return hosts

    def read(self, page: bytes, fields: Sequence[Any]) -> Dict[str, Optional[str]]:
        if not fields:
            return {}
        hosts = self.hosts()
        if not hosts:
            raise VisionReadingUnavailableException(
                f"Ninguna computadora conectada tiene el modelo {self._model}."
            )
        prompt = self._prompt(fields)
        image = base64.b64encode(_for_the_model(page)).decode("ascii")
        last_error: Optional[Exception] = None
        for host in hosts:
            try:
                return self._ask(host, prompt, image)
            except requests.RequestException as exc:
                last_error = exc
        raise VisionReadingUnavailableException(
            "Ninguna computadora pudo mirar la foto."
        ) from last_error

    @staticmethod
    def _prompt(fields: Sequence[Any]) -> str:
        wanted = "\n".join(f"- {spec.key}: {spec.vision_hint}" for spec in fields)
        shape = json.dumps({spec.key: None for spec in fields}, ensure_ascii=False)
        return (
            "Mire la foto de esta hoja y saque estos datos:\n"
            f"{wanted}\n\n"
            f"Conteste con un solo JSON con exactamente estas claves: {shape}"
        )

    def _ask(self, host: str, prompt: str, image: str) -> Dict[str, Optional[str]]:
        """Levanta requests.RequestException cuando falla ESTA computadora (quien
        llama prueba con la siguiente). Una respuesta ilegible es definitiva --
        cualquier máquina daría la misma-- y quedarse sin tiempo también: volver a
        esperar el presupuesto entero en otra es justamente lo que esta pasada no
        puede hacer."""
        with self._borrow(host, self._timeout) as should_stop:
            response = requests.post(
                f"{host}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt, "images": [image]},
                    ],
                    "format": "json",
                    "stream": True,
                    "keep_alive": KEEP_ALIVE,
                    "options": {"temperature": 0, "num_predict": NUM_PREDICT},
                },
                timeout=self._timeout,
                stream=True,
            )
            with response:
                response.raise_for_status()
                content = self._read(response, should_stop)
        try:
            data = json.loads(_json_object(content))
        except ValueError as exc:
            raise VisionReadingUnavailableException("El modelo devolvió una respuesta ilegible.") from exc
        if not isinstance(data, dict):
            raise VisionReadingUnavailableException("El modelo devolvió un JSON inesperado.")
        return data

    def _read(self, response: requests.Response, should_stop: Callable[[], bool]) -> str:
        """Junta la respuesta a medida que la computadora la escribe. Salir de
        este bucle cierra el socket, y Ollama suelta la generación en cuanto el
        cliente corta.

        El timeout de la petición es por fragmento, así que una máquina que
        escribe lento pero sin pausas tendría al arquitecto esperando lo que
        quisiera: acá el plazo es uno solo para toda la respuesta."""
        deadline = time.monotonic() + self._timeout
        parts: List[str] = []
        for line in response.iter_lines(decode_unicode=True):
            if should_stop():
                raise VisionReadingStoppedException()
            if time.monotonic() > deadline:
                raise VisionReadingUnavailableException(
                    f"La computadora tardó más de {self._timeout:.0f} s en mirar la foto."
                )
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("error"):
                raise VisionReadingUnavailableException(f"Ollama falló: {event['error']}")
            parts.append((event.get("message") or {}).get("content") or "")
            if event.get("done"):
                break
        return "".join(parts).strip()
