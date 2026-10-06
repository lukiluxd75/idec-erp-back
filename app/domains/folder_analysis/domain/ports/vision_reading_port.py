from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Sequence


class VisionReadingPort(ABC):
    """La última pasada de la lectura: el modelo de visión mirando la foto.

    El OCR y las reglas leen la hoja como texto, y eso alcanza mientras el valor
    esté escrito en una línea. Cuando no lo está -- el número del notario vive en
    un sello redondo, encimado al título del formulario -- el texto plano no
    distingue el número del sello del de la "Resolución Ministerial Nº 57/2020"
    impresa tres centímetros más abajo: para la hoja ya convertida en una tira de
    caracteres los dos son "Nº" y un número. Mirar la foto sí los distingue,
    porque el modelo ve dónde está cada uno.

    Por eso va al final y no en lugar del OCR: cuesta entre veinte y treinta
    segundos por foto en las computadoras de los arquitectos, así que se le
    pregunta una sola cosa -- los campos que la carpeta declara (`vision_hint`) --
    y solo los que no quedaron resueltos, foto por foto, parando en cuanto están
    todos.

    Devuelve el valor tal como está escrito en la foto, o None por cada campo que
    no esté en ella. Nunca deduce: un campo que la hoja no trae se queda vacío y
    lo llena el arquitecto a mano.
    """

    @abstractmethod
    def is_configured(self) -> bool:
        """¿Hay modelo y alguna computadora a la que pedírselo? Con esto en falso
        la lectura se queda en lo que dieron el OCR, las reglas y el sello, que es
        exactamente lo que había antes de esta pasada."""

    @abstractmethod
    def read(self, page: bytes, fields: Sequence[Any]) -> Dict[str, Optional[str]]:
        """Una foto y los campos que se le piden (DocumentField con `vision_hint`)
        -> lo que el modelo leyó de cada uno.

        Una foto por llamada a propósito: así quien consume corta en cuanto tiene
        lo que buscaba y las hojas siguientes no cuestan media computadora.
        Levanta `VisionReadingUnavailableException` cuando ninguna computadora
        pudo contestar."""
