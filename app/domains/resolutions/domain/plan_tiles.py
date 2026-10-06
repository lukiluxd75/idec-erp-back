"""
Mosaico de una página de plano para el OCR del título.

El servicio OCR lee mal las imágenes muy grandes o muy alargadas: el título del
plano ("...PLANTA BAJA ...", en letra de dibujante y mucho más chico que la
página) se pierde. Cortada en mosaicos de lado acotado, la misma letra queda
más grande respecto a la imagen y sí se lee. Puro: bytes JPEG/PNG -> bytes.
"""
from typing import List, Tuple

import cv2
import numpy as np

# Lados de mosaico a probar, de mayor a menor: el título de estos planos (letra
# de dibujante, ~30 px en una página de 4000) solo se lee de forma fiable con
# mosaicos de ~700 px; con 1400 se leen los más grandes y se evita el segundo
# paso (que son bastantes más llamadas al OCR).
LADOS = (1400, 700)
SOLAPE = 0.2  # fracción de mosaico compartida con el vecino: un título cortado en el borde cae entero en el siguiente
MAX_MOSAICOS = 40


def _cortes(largo: int, lado: int) -> List[Tuple[int, int]]:
    if largo <= lado:
        return [(0, largo)]
    paso = int(lado * (1 - SOLAPE))
    tramos, ini = [], 0
    while True:
        fin = min(ini + lado, largo)
        tramos.append((ini, fin))
        if fin >= largo:
            return tramos
        ini += paso


def mosaicos(image_bytes: bytes, lado: int) -> List[Tuple[bytes, int, int]]:
    """[(jpeg, x0, y0)] que cubren la imagen, o [] si no se puede decodificar o
    la imagen ya cabe en un solo mosaico (no hay nada que mejorar cortando)."""
    imagen = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        return []
    alto, ancho = imagen.shape[:2]
    cols, filas = _cortes(ancho, lado), _cortes(alto, lado)
    if len(cols) * len(filas) <= 1 or len(cols) * len(filas) > MAX_MOSAICOS:
        return []
    salida = []
    for y0, y1 in filas:
        for x0, x1 in cols:
            ok, jpg = cv2.imencode(".jpg", imagen[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 90])
            if ok:
                salida.append((jpg.tobytes(), x0, y0))
    return salida
