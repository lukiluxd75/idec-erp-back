"""
El sello del notario, buscado en la foto con OpenCV y leído con el mismo OCR que
el resto de la hoja.

Por qué no alcanza con el texto de la página: el número del notario casi nunca
está escrito en la redacción. Una minuta va dirigida al notario ("SEÑOR NOTARIO
DE FE PÚBLICA, sírvase insertar") y no lo nombra; cuando nombra a uno es el que
reconoció el documento anterior, que no es el de esta hoja. El número está en el
sello, y el OCR de la hoja entera lo devuelve partido porque la leyenda va
curvada y girada ("NOTARIA DEFE PULCA DEP.SMERA CLAN0.48").

Cómo se encuentra: dos señales, porque ninguna sola aguanta una foto de celular.
  - el color: el sello se estampa en tinta violeta o azul y el resto de la hoja
    es negro sobre blanco, así que la saturación en HSV lo separa sin depender de
    la luz con que se tomó la foto.
  - la forma: una circunferencia con HoughCircles, que es lo que queda cuando el
    sello se estampó en negro o la tinta salió lavada.
Las dos listas se juntan y los círculos que caen uno dentro del otro quedan en
uno solo -- un sello tiene dos aros concéntricos y los dos se detectan.

Cómo se lee: primero el recorte derecho y agrandado, porque en el centro del
sello el número suele ir escrito en línea ("No. 48"), y solo si eso no dijo nada
se desenrolla la corona con warpPolar, que vuelve la leyenda curva una tira
horizontal. Cada paso es una llamada al OCR, así que se van dando de a uno (el
puerto devuelve un iterador) y el que consume corta en cuanto tiene el número.

Qué NO hace: decidir qué dice el sello. Los patrones con los que se le saca el
número viven en el catálogo, junto a los del texto (domain/folder_types.py,
`seal_patterns`), y acá solo se entrega texto.
"""
import logging
import math
from dataclasses import dataclass
from typing import Any, Callable, Iterator, List, Optional, Sequence

import cv2
import numpy as np

from app.domains.folder_analysis.domain.ports import SealReadingPort
from app.domains.folios.contracts import read_page_text

logger = logging.getLogger("uvicorn.error")

# Para buscar, la foto reducida: un sello se reconoce por su forma, no por su
# detalle, y en una foto de 12 Mpx las dos pasadas costarían de más. El recorte
# que se manda a leer sale igual de la foto original.
WORK_WIDTH = 1400

# El radio de un sello de notario, como parte del ancho de la hoja. Por debajo
# del mínimo es un punto de la impresión; por encima del máximo es el borde de la
# foto o un plato, no un sello.
MIN_RADIUS_RATIO = 0.035
MAX_RADIUS_RATIO = 0.22

# Tinta de sello: violeta o azul. Lo impreso en negro no tiene saturación, y por
# eso esto separa el sello del texto de la hoja y no de la luz de la foto.
MIN_SATURATION = 55
MIN_VALUE = 40

# Una mancha es redonda cuando su área se parece a la del círculo que la encierra.
# Flojo a propósito: el sello llega cortado por el borde del papel o pisado por
# una firma más veces de las que llega entero.
MIN_ROUNDNESS = 0.55

# Cuántos sellos se leen por hoja. Una hoja tiene el del notario y a veces el de
# la ventanilla; más que eso son manchas, y cada una cuesta OCR.
MAX_SEALS_PER_PAGE = 2

# El recorte se agranda a este ancho antes de leerlo: la leyenda de un sello es
# letra chica, y el OCR la lee mucho mejor en grande que en los 200 px que ocupa
# en la hoja.
READ_WIDTH = 900

# Un poco más que el sello, para no cortarle la leyenda con el propio recorte.
CROP_MARGIN = 1.08

JPEG_QUALITY = 90


@dataclass(frozen=True)
class Seal:
    """Un sello encontrado, en las coordenadas de la foto original."""

    x: float
    y: float
    r: float


class OpenCvSealReader(SealReadingPort):
    """`read_page` se inyecta para poder probar el carril sin el servicio de OCR,
    igual que hace el lector del plano."""

    def __init__(self, read_page: Optional[Callable[..., Any]] = None):
        self._read_page = read_page or read_page_text

    def read(self, pages: Sequence[bytes]) -> Iterator[str]:
        for index, content in enumerate(pages):
            number = index + 1
            page = _decode(content)
            if page is None:
                continue
            try:
                seals = seals_in(page)
            except Exception:
                logger.exception(
                    "Folder analysis: no se pudieron buscar sellos en la página %d", number
                )
                continue
            for order, seal in enumerate(seals, start=1):
                for variant, image in enumerate(_variants(page, seal), start=1):
                    text = self._text(image, f"sello_p{number}_{order}_{variant}.jpg")
                    if text:
                        yield text

    def _text(self, image: np.ndarray, filename: str) -> str:
        """El texto de un recorte. Un sello que no se puede leer no corta la
        búsqueda: queda el recorte siguiente, y después el texto de la hoja."""
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            return ""
        try:
            read = self._read_page(encoded.tobytes(), filename)
        except Exception:
            logger.exception("Folder analysis: no se pudo leer el sello %s", filename)
            return ""
        return " ".join(block.text.strip() for block in read.blocks if block.text.strip())


def seals_in(page: np.ndarray) -> List[Seal]:
    """Los sellos de una hoja, el más entintado primero.

    El orden importa porque solo se leen los primeros: entre dos manchas
    redondas, la que tiene tinta de sello es la que vale. Los círculos que salen
    de la forma y no del color quedan con puntaje cero y conservan entre ellos el
    orden en que HoughCircles los dio, que es el de su propia confianza.
    """
    scale = min(1.0, WORK_WIDTH / max(page.shape[1], 1))
    frame = (
        cv2.resize(page, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else page
    )
    low = MIN_RADIUS_RATIO * frame.shape[1]
    high = MAX_RADIUS_RATIO * frame.shape[1]
    found = _merged(_by_colour(frame, low, high) + _by_shape(frame, low, high))
    ranked = sorted(found, key=lambda seal: -_ink(frame, seal))
    return [
        Seal(seal.x / scale, seal.y / scale, seal.r / scale)
        for seal in ranked[:MAX_SEALS_PER_PAGE]
    ]


def _decode(content: bytes) -> Optional[np.ndarray]:
    try:
        return cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def _by_colour(frame: np.ndarray, low: float, high: float) -> List[Seal]:
    """La mancha de tinta de color, cerrada hasta que la leyenda suelta vuelva a
    ser un aro: lo que se mide es el aro, no cada letra."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, MIN_SATURATION, MIN_VALUE), (179, 255, 255))
    size = max(3, int(round(low / 3)) | 1)
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    )
    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    seals: List[Seal] = []
    for contour in contours:
        (x, y), radius = cv2.minEnclosingCircle(contour)
        if not low <= radius <= high:
            continue
        if cv2.contourArea(contour) / (math.pi * radius * radius) < MIN_ROUNDNESS:
            continue
        seals.append(Seal(x, y, radius))
    return seals


def _by_shape(frame: np.ndarray, low: float, high: float) -> List[Seal]:
    """La circunferencia, para el sello que no tiene color: negro, o tan lavado
    que la saturación ya no lo distingue del texto."""
    gray = cv2.medianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 5)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(low * 2.0, 1.0),
        param1=120,
        param2=50,
        minRadius=int(low),
        maxRadius=int(high),
    )
    if circles is None:
        return []
    return [Seal(float(x), float(y), float(r)) for x, y, r in circles[0]]


def _merged(seals: Sequence[Seal]) -> List[Seal]:
    """Un sello detectado una vez. Tiene dos aros concéntricos y las dos pasadas
    lo encuentran, así que un círculo cuyo centro cae dentro de otro ya aceptado
    es el mismo sello; se queda el más grande, que es el que trae la leyenda."""
    kept: List[Seal] = []
    for seal in sorted(seals, key=lambda s: -s.r):
        if any(math.hypot(seal.x - k.x, seal.y - k.y) < k.r for k in kept):
            continue
        kept.append(seal)
    return kept


def _ink(frame: np.ndarray, seal: Seal) -> float:
    """Cuánta tinta de color hay dentro del círculo, de 0 a 1."""
    x0, y0 = int(max(0, seal.x - seal.r)), int(max(0, seal.y - seal.r))
    x1 = int(min(frame.shape[1], seal.x + seal.r))
    y1 = int(min(frame.shape[0], seal.y + seal.r))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    saturation = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)[:, :, 1]
    if saturation.size == 0:
        return 0.0
    return float(np.count_nonzero(saturation >= MIN_SATURATION)) / saturation.size


def _variants(page: np.ndarray, seal: Seal) -> Iterator[np.ndarray]:
    """Las formas en que se le ofrece un sello al OCR, de la más barata a la más
    trabajosa. Generador: la corona solo se calcula si el recorte derecho no
    alcanzó."""
    crop = _crop(page, seal)
    if crop is None:
        return
    yield crop
    ring = unwrap(crop)
    yield ring
    # La mitad de abajo del sello está cabeza abajo en la hoja, así que al
    # desenrollar queda media vuelta girada respecto de la de arriba: una de las
    # dos tiras lee derecho, y cuál de ellas depende de dónde arranca la leyenda.
    yield cv2.rotate(ring, cv2.ROTATE_180)


def _crop(page: np.ndarray, seal: Seal) -> Optional[np.ndarray]:
    margin = seal.r * CROP_MARGIN
    x0, y0 = int(max(0, seal.x - margin)), int(max(0, seal.y - margin))
    x1 = int(min(page.shape[1], seal.x + margin))
    y1 = int(min(page.shape[0], seal.y + margin))
    if x1 - x0 < 24 or y1 - y0 < 24:
        return None
    crop = page[y0:y1, x0:x1]
    scale = READ_WIDTH / crop.shape[1]
    if scale <= 1.0:
        return crop
    return cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def unwrap(crop: np.ndarray) -> np.ndarray:
    """La corona del sello puesta en línea.

    warpPolar devuelve un ángulo por fila y el radio por columna; girando eso un
    cuarto de vuelta, la leyenda que iba curvada queda escrita de izquierda a
    derecha en una tira ancha y baja, que es lo que el OCR sabe leer.
    """
    height, width = crop.shape[:2]
    radius = min(height, width) / 2.0
    polar = cv2.warpPolar(
        crop,
        (max(int(radius), 1), max(int(2 * math.pi * radius), 1)),
        (width / 2.0, height / 2.0),
        radius,
        cv2.INTER_CUBIC + cv2.WARP_POLAR_LINEAR + cv2.WARP_FILL_OUTLIERS,
    )
    return cv2.rotate(polar, cv2.ROTATE_90_COUNTERCLOCKWISE)
