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


MAX_RECORTES = 6


def recortes_de_titulo(image_bytes: bytes, anclas: List[Tuple[float, float, float, float]]) -> List[Tuple[bytes, int, int]]:
    """[(jpeg, x0, y0)]: una ventana alrededor de cada ANCLA (x0, y0, x1, y1) -- un
    pedazo del título que el OCR leyó ("PLANTA 6", "6°PIS0") -- lo bastante ancha
    para que el título entero caiga en un solo recorte. Los mosaicos parten el
    título en el borde y el OCR lo lee a trozos; recortado alrededor del trozo ya
    leído, se lee de corrido. Ventanas que se pisan se funden en una."""
    imagen = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        return []
    alto, ancho = imagen.shape[:2]
    ventanas: List[List[int]] = []
    for x0, y0, x1, y1 in anclas:
        letra = max(min(x1 - x0, y1 - y0), 20)
        v = [
            int(max(0, x0 - 4 * letra)),
            int(max(0, y0 - 2 * letra)),
            int(min(ancho, x1 + max(10 * letra, 600))),
            int(min(alto, y1 + 2 * letra)),
        ]
        for w in ventanas:
            if v[0] < w[2] and w[0] < v[2] and v[1] < w[3] and w[1] < v[3]:
                w[:] = [min(w[0], v[0]), min(w[1], v[1]), max(w[2], v[2]), max(w[3], v[3])]
                break
        else:
            ventanas.append(v)
    salida = []
    for x0, y0, x1, y1 in ventanas[:MAX_RECORTES]:
        ok, jpg = cv2.imencode(".jpg", imagen[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 90])
        if ok:
            salida.append((jpg.tobytes(), x0, y0))
    return salida


def variantes_de_recorte(jpeg: bytes) -> List[Tuple[bytes, float]]:
    """[(jpeg, escala)]: el mismo recorte en versiones que el OCR lee distinto --
    tal cual, reducido a la mitad y binarizado (Otsu). El servicio OCR a veces
    lee solo el rótulo de escala de un recorte donde el título se ve perfecto, y
    el título sí sale en otra versión. `escala` = tamaño de la versión / tamaño
    del recorte (para devolver los bloques a las coordenadas del recorte)."""
    imagen = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        return [(jpeg, 1.0)]
    variantes = [(jpeg, 1.0)]
    alto, ancho = imagen.shape[:2]
    mitad = cv2.resize(imagen, (max(ancho // 2, 1), max(alto // 2, 1)), interpolation=cv2.INTER_AREA)
    ok, jpg = cv2.imencode(".jpg", mitad, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if ok:
        variantes.append((jpg.tobytes(), 0.5))
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    _, binaria = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ok, jpg = cv2.imencode(".jpg", binaria, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if ok:
        variantes.append((jpg.tobytes(), 1.0))
    return variantes
