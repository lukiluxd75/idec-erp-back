"""
The "croquis de ubicación" of a predio, drawn the way the municipality's
certificate demo draws it: the layers of the map stacked, the predio in grey with a
black outline, a red circle of 50 m around it and its number in red.

The layers come from the GIS already rendered (ArcGIS `export`); what is drawn on
top is done here with OpenCV, so the ERP does not need a browser to make the
picture.
"""
from typing import Sequence, Tuple

import cv2
import numpy as np

CIRCLE_RADIUS_M = 50.0
GREY = (192, 192, 192)
BLACK = (0, 0, 0)
RED = (0, 0, 255)  # BGR


def _decode(content: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError("El GIS no devolvió una imagen legible.")
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
    elif image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    return image


def _stack(layers: Sequence[bytes], size: int) -> np.ndarray:
    canvas = np.full((size, size, 3), 255, np.float32)
    for content in layers:
        layer = _decode(content)
        if layer.shape[0] != size or layer.shape[1] != size:
            layer = cv2.resize(layer, (size, size))
        alpha = layer[:, :, 3:4].astype(np.float32) / 255.0
        canvas = canvas * (1 - alpha) + layer[:, :, :3].astype(np.float32) * alpha
    return canvas.astype(np.uint8)


def compose(
    layers: Sequence[bytes],
    bbox: Tuple[float, float, float, float],
    size: int,
    ring: Sequence[Sequence[float]],
    number: str,
) -> bytes:
    """PNG of the layers with the predio drawn on them. `bbox` is
    (xmin, ymin, xmax, ymax) in the metres of the layers and the picture is square."""
    xmin, ymin, xmax, ymax = bbox
    scale = size / (xmax - xmin)

    def to_pixel(point: Sequence[float]) -> Tuple[int, int]:
        return int(round((point[0] - xmin) * scale)), int(round((ymax - point[1]) * scale))

    image = _stack(layers, size)
    polygon = np.array([to_pixel(p) for p in ring], np.int32)

    fill = image.copy()
    cv2.fillPoly(fill, [polygon], GREY)
    image = cv2.addWeighted(fill, 0.5, image, 0.5, 0)
    cv2.polylines(image, [polygon], True, BLACK, 3, cv2.LINE_AA)

    center = polygon.mean(axis=0)
    center_px = (int(center[0]), int(center[1]))
    cv2.circle(image, center_px, int(CIRCLE_RADIUS_M * scale), RED, 3, cv2.LINE_AA)

    text = str(number)
    font = cv2.FONT_HERSHEY_DUPLEX
    (width, height), _ = cv2.getTextSize(text, font, 1.6, 4)
    cv2.putText(
        image, text, (center_px[0] - width // 2, center_px[1] + height // 2), font, 1.6, RED, 4, cv2.LINE_AA
    )

    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("No se pudo generar la imagen del croquis.")
    return encoded.tobytes()
