"""
El sello del notario, buscado en la foto con OpenCV y leído con el mismo OCR que
el resto de la hoja.

Por qué no alcanza con el texto de la página: el número del notario casi nunca
está escrito en la redacción. Una minuta va dirigida al notario ("SEÑOR NOTARIO
DE FE PÚBLICA, sírvase insertar") y no lo nombra; cuando nombra a uno es el que
reconoció el documento anterior, que no es el de esta hoja. El número está en el
sello, y el OCR de la hoja entera lo devuelve partido porque la leyenda va
curvada y girada ("NOTARIA DEFE PULCA DEP.SMERA CLAN0.48").

Dónde está el sello: en ninguna parte fija. Un formulario notarial lo trae
encimado al título de la primera hoja, y la hoja de firmas lo trae abajo, al lado
de la tabla de huellas; la misma notaría estampa el redondo de la corona y uno
rectangular con su nombre y su número en renglones derechos. Por eso acá no se
busca un lugar ni una forma: se busca cualquier mancha de tinta de sello del
tamaño de un sello, caiga donde caiga en la hoja.

Cómo se encuentra: la tinta, en sus dos formas, porque la hoja llega de las dos.
  - la tinta de color, cuando la carpeta trae el original: el sello se estampa en
    color y el resto de la hoja es negro sobre blanco. Pero no vale cualquier
    color, solo los tonos con que se entinta un sello (rojo, violeta/azul,
    verde). Mirar nada más la saturación dejaba fuera al sello en vez de
    encontrarlo -- una foto tomada sobre una carpeta amarilla y con luz cálida
    tiñe la hoja entera, todo queda "con color", y el sello se perdía dentro de
    esa única mancha del tamaño de la página.
  - la tinta oscura, cuando lo que se fotografió es una fotocopia: ahí el sello
    salió del mismo negro que la redacción y el color ya no dice nada. Lo que lo
    separa del texto es el tamaño y la forma de la mancha, no su tono.
Las partes de un sello (la corona, los renglones del medio, el escudo) salen como
manchas sueltas, así que la máscara se cierra hasta que vuelven a ser una sola y
lo que se mide es el recuadro de esa mancha, no un círculo: el sello rectangular
no lo es. Un renglón de la redacción es más fino que un sello y un párrafo
entero, cerrado, es más grande que una hoja permite, así que ni uno ni otro llegan
a candidatos.

Lo que esa cuenta no salva es el sello estampado ENCIMA del texto de una
fotocopia: ahí la mancha del sello y la del párrafo son una sola, demasiado
grande, y se descartan juntas. Para eso la tinta oscura se mira dos veces, y la
segunda se queda solo con los trazos largos --el aro, el recuadro-- que una letra
suelta nunca tiene; sobre esa hoja limpia el sello vuelve a ser una mancha de su
tamaño. Las dos miradas se suman y los recuadros que se pisan quedan en uno solo,
igual que el aro de afuera y el de adentro de un sello redondo.

Qué se dejó por el camino: buscar circunferencias con HoughCircles. Sobre una foto
de celular devolvía círculos enormes que no están en la hoja, y en la fotocopia
--que es donde hacía falta-- no encontró ni uno de los sellos de estas carpetas.

Cómo se lee: primero el recorte derecho y agrandado, porque el número suele ir
escrito en línea en el medio del sello ("No. 48") y en el rectangular va derecho
todo; y solo si eso no dijo nada, y solo para el sello redondo, se desenrolla la
corona con warpPolar, que vuelve la leyenda curva una tira horizontal. Cada paso
es una llamada al OCR, así que se van dando de a uno (el puerto devuelve un
iterador) y el que consume corta en cuanto tiene el número.

Qué NO hace: decidir qué dice el sello. Los patrones con los que se le saca el
número viven en el catálogo, junto a los del texto (domain/folder_types.py,
`seal_patterns`), y acá solo se entrega texto.
"""
import logging
import math
from dataclasses import dataclass
from typing import Any, Callable, Iterator, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from app.domains.folder_analysis.domain.ports import SealReadingPort
from app.domains.folios.contracts import read_page_text

logger = logging.getLogger("uvicorn.error")

WORK_WIDTH = 1400

# El tamaño de un sello, como parte del ancho de la hoja: su lado más corto no
# baja de MIN_SIDE_RATIO ni el más largo pasa de MAX_SIDE_RATIO. El tope es
# holgado --en una hoja entera el sello rectangular ocupa un cuarto del ancho--
# porque la foto no siempre es de la hoja entera: a veces llega recortada al pie
# firmado, y ahí el mismo sello ocupa la mitad.
MIN_SIDE_RATIO = 0.07
MAX_SIDE_RATIO = 0.55

# Con qué vecindario se decide si un trazo es más oscuro que su papel, como parte
# del ancho de la hoja, y cuánto más oscuro tiene que ser. Un umbral local y no
# uno para toda la hoja: la fotocopia llega con una mitad más gris que la otra.
DARK_BLOCK_RATIO = 0.022
DARK_OFFSET = 12

# Tinta de sello: rojo, violeta/azul y verde. Lo que queda afuera es el amarillo
# y el anaranjado, que en estas fotos no son tinta sino el papel: la carpeta de
# abajo y la luz cálida con que se tomó la foto.
INK_HUES: Tuple[Tuple[int, int], ...] = ((0, 14), (40, 90), (90, 160), (165, 179))
MIN_SATURATION = 50
MIN_VALUE = 40

# Cuánto se cierra la máscara para que las partes de un sello sean una sola
# mancha, como parte del ancho de la hoja.
CLOSE_RATIO = 0.028

# Cuántos sellos se leen por hoja. Cuatro, porque una hoja puede traer el
# redondo, el rectangular, la huella digital entintada y el cuadro del código QR,
# y en una fotocopia esos últimos se parecen a un sello tanto como el sello
# mismo. Cada uno de más cuesta una llamada al OCR, pero solo cuando los
# anteriores no dieron el número: en cuanto uno lo da, los que siguen ni se leen.
MAX_SEALS_PER_PAGE = 4

# Hasta dónde un recuadro sigue siendo cuadrado, que es como se reconoce al sello
# redondo: solo a ese se le desenrolla la corona.
MAX_SQUARE_RATIO = 1.35

# Cuánto más grande puede ser otro recuadro sobre el mismo sello para seguir
# siendo una vista del sello --el aro entero donde el trazo trajo un pedazo-- y
# no ya la hoja alrededor.
WIDER_VIEW = 4.0

READ_WIDTH = 900

# Un poco más que el sello, para no cortarle la leyenda con el propio recorte.
CROP_MARGIN = 0.08

JPEG_QUALITY = 90

# De dónde salió un sello, de la búsqueda más confiable a la menos: la tinta de
# color (donde hay color de sello hay sello), el trazo largo de la tinta oscura
# (recorta la estampa sola, aunque esté encima de la redacción) y la mancha de
# tinta oscura entera (encuentra el aro que la fotocopiadora partió, pero puede
# traer pegado lo que el sello tenga al lado).
COLOUR, STROKE, BLOB = "colour", "stroke", "blob"
SOURCES = (COLOUR, STROKE, BLOB)


@dataclass(frozen=True)
class Seal:
    """Un sello encontrado, en las coordenadas de la foto original: el centro de
    su recuadro y lo que mide. Un recuadro y no un círculo porque el sello de la
    notaría viene redondo o rectangular, y los dos dicen el mismo número."""

    x: float
    y: float
    w: float
    h: float
    # Cuánta tinta tiene adentro, en píxeles: con eso se ordenan entre ellos.
    ink: float = 0.0
    # Cuál de las búsquedas lo encontró (SOURCES).
    source: str = BLOB

    @property
    def coloured(self) -> bool:
        """Si lo encontró la tinta de color. Una hoja fotocopiada no tiene
        ninguno: ahí el sello salió del mismo negro que la redacción."""
        return self.source == COLOUR

    @property
    def rounded(self) -> bool:
        """Si el recuadro es casi cuadrado, lo estampado es el sello redondo y su
        leyenda va en corona."""
        short, long = sorted((self.w, self.h))
        return short > 0 and long / short <= MAX_SQUARE_RATIO


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

    El orden importa porque solo se leen los primeros: primero manda de qué
    búsqueda salió el sello (SOURCES, de la más confiable a la menos) y después,
    entre los de la misma, cuánta tinta tiene la mancha, porque un sello
    estampado deja más que una firma o que una huella digital.
    """
    scale = min(1.0, WORK_WIDTH / max(page.shape[1], 1))
    frame = (
        cv2.resize(page, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else page
    )
    width = frame.shape[1]
    colour = _colour_mask(frame)
    dark = _dark_mask(frame)
    # De más seguro a menos, que es el orden en que se quedan con lo que se pisa:
    # la tinta de color es un sello seguro; de la oscura, el trazo largo recorta
    # el sello solo y la mancha entera puede traerle pegado lo que tenga al lado.
    found = _merged(
        _by_ink(colour, colour, width, COLOUR),
        # Dos miradas a la misma tinta oscura, porque cada una tiene su punto
        # ciego: los trazos largos encuentran el sello estampado encima de la
        # redacción, donde la mancha se lo come, y la mancha entera encuentra el
        # sello cuyo aro llegó partido de la fotocopiadora.
        _by_ink(_strokes(dark, width), dark, width, STROKE),
        _by_ink(dark, dark, width, BLOB),
    )
    ranked = sorted(found, key=lambda seal: (SOURCES.index(seal.source), -seal.ink))
    return [
        Seal(seal.x / scale, seal.y / scale, seal.w / scale, seal.h / scale, seal.ink, seal.source)
        for seal in ranked[:MAX_SEALS_PER_PAGE]
    ]


def _decode(content: bytes) -> Optional[np.ndarray]:
    try:
        return cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def _colour_mask(frame: np.ndarray) -> np.ndarray:
    """Los píxeles de tinta de sello de color: los de un tono de sello y lo
    bastante vivos. El tono es lo que separa al sello del papel cuando la foto
    entera tiene color."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(frame.shape[:2], np.uint8)
    for low, high in INK_HUES:
        mask |= cv2.inRange(hsv, (low, MIN_SATURATION, MIN_VALUE), (high, 255, 255))
    return mask


def _dark_mask(frame: np.ndarray) -> np.ndarray:
    """Los píxeles de tinta negra, para la hoja fotocopiada: ahí el sello salió
    del mismo color que la redacción y el tono ya no lo distingue.

    Umbral local y no uno solo para toda la hoja: una fotocopia llega con una
    mitad más gris que la otra, y la foto de la fotocopia encima trae la sombra
    de quien la tomó. Lo que se mira es si un trazo es más oscuro que el papel
    que lo rodea, que es lo mismo en la parte clara y en la parte sombreada."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    block = max(3, int(round(DARK_BLOCK_RATIO * frame.shape[1])) | 1)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, DARK_OFFSET
    )


def _strokes(ink: np.ndarray, width: int) -> np.ndarray:
    """De la tinta, solo los trazos largos: el aro del sello redondo y el
    recuadro del rectangular, sin las letras de la redacción.

    Es lo que salva al sello estampado ENCIMA del texto. Ahí cerrar la tinta no
    sirve: el sello y el párrafo quedan pegados en una sola mancha más grande que
    un sello, y se descarta con el sello adentro. Las letras, en cambio, son
    manchitas sueltas --una letra no toca a la siguiente-- y el aro es un solo
    trazo del largo del sello, así que quedarse con los trazos largos deja la
    hoja limpia y el sello entero."""
    count, labels, boxes, _centroids = cv2.connectedComponentsWithStats(ink, 8)
    longest = np.maximum(boxes[:, cv2.CC_STAT_WIDTH], boxes[:, cv2.CC_STAT_HEIGHT])
    keep = (longest >= MIN_SIDE_RATIO * width) & (longest <= MAX_SIDE_RATIO * width)
    if count:
        keep[0] = False  # el fondo
    return np.where(keep[labels], np.uint8(255), np.uint8(0))


def _by_ink(cluster: np.ndarray, ink: np.ndarray, width: int, source: str) -> List[Seal]:
    """Las manchas de tinta del tamaño de un sello, cerradas hasta que las partes
    sueltas del sello vuelvan a ser una sola: lo que se mide es el sello entero,
    no cada letra ni cada aro.

    Es lo mismo para la tinta de color y para la negra, y el tamaño es lo que
    separa al sello de la redacción: un renglón es más fino que un sello y un
    párrafo entero, cerrado, es más grande que la hoja permite.

    `cluster` es la tinta con la que se arma la mancha e `ink` la que se cuenta
    para ordenarla, que no siempre son la misma: de los trazos largos sale el
    recuadro del sello, pero lo que dice cuánto vale es toda la tinta que hay
    adentro."""
    size = max(3, int(round(CLOSE_RATIO * width)) | 1)
    closed = cv2.morphologyEx(
        cluster, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    )
    count, _labels, boxes, _centroids = cv2.connectedComponentsWithStats(closed, 8)
    seals: List[Seal] = []
    for index in range(1, count):
        x, y, w, h, _area = boxes[index]
        if min(w, h) < MIN_SIDE_RATIO * width or max(w, h) > MAX_SIDE_RATIO * width:
            continue
        inside = float(np.count_nonzero(ink[y : y + h, x : x + w]))
        seals.append(Seal(x + w / 2.0, y + h / 2.0, float(w), float(h), inside, source))
    return seals


def _merged(*groups: Sequence[Seal]) -> List[Seal]:
    """Un sello detectado una vez. El redondo tiene dos aros concéntricos, y la
    tinta de un sello de color es además tinta oscura, así que las dos pasadas
    encuentran lo mismo: un recuadro cuyo centro cae dentro de otro ya aceptado
    es el mismo sello.

    `groups` viene de la búsqueda más confiable a la menos, y ese es el orden que
    manda, no el tamaño: donde hubo tinta de color hay sello, mientras que la
    mancha oscura de ese mismo sello se le pega al renglón que tiene encima y
    devuelve un recuadro más grande que la estampa. Dejar que esa se quedara con
    el sello adentro era mandarle al OCR media página.

    Lo que sí sobrevive es la vista MÁS AMPLIA del mismo sello, mientras no pase
    de WIDER_VIEW veces la que ya se tiene: el trazo largo de una fotocopia suele
    traer el aro partido y recortar media estampa, y entonces la mancha entera,
    que es la que la trae completa, tiene que quedar como segunda oportunidad."""
    kept: List[Seal] = []
    ordered = [seal for group in groups for seal in sorted(group, key=lambda s: -(s.w * s.h))]
    for seal in ordered:
        inside = [
            k for k in kept if abs(seal.x - k.x) <= k.w / 2.0 and abs(seal.y - k.y) <= k.h / 2.0
        ]
        if inside and not any(
            k.w * k.h < seal.w * seal.h <= WIDER_VIEW * k.w * k.h for k in inside
        ):
            continue
        kept.append(seal)
    return kept


def _variants(page: np.ndarray, seal: Seal) -> Iterator[np.ndarray]:
    """Las formas en que se le ofrece un sello al OCR, de la más barata a la más
    trabajosa. Generador: la corona solo se calcula si el recorte derecho no
    alcanzó, y solo para el sello redondo -- desenrollar el rectangular no deja
    nada legible, sus renglones ya vienen derechos."""
    crop = _crop(page, seal)
    if crop is None:
        return
    yield crop
    if not seal.rounded:
        return
    ring = unwrap(crop)
    yield ring
    yield cv2.rotate(ring, cv2.ROTATE_180)


def _bounds(shape: Sequence[int], seal: Seal, margin: float) -> Tuple[int, int, int, int]:
    """El recuadro del sello dentro de la foto, agrandado por su margen y sin
    salirse de la hoja."""
    pad = margin * max(seal.w, seal.h)
    x0 = int(max(0, seal.x - seal.w / 2.0 - pad))
    y0 = int(max(0, seal.y - seal.h / 2.0 - pad))
    x1 = int(min(shape[1], seal.x + seal.w / 2.0 + pad))
    y1 = int(min(shape[0], seal.y + seal.h / 2.0 + pad))
    return x0, y0, x1, y1


def _crop(page: np.ndarray, seal: Seal) -> Optional[np.ndarray]:
    x0, y0, x1, y1 = _bounds(page.shape, seal, CROP_MARGIN)
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
