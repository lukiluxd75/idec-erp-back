from abc import ABC, abstractmethod
from typing import Iterator, Sequence


class SealReadingPort(ABC):
    """Los sellos estampados en las fotos de un documento, leídos aparte del
    resto de la hoja.

    Un sello redondo no se lee con el texto de la página: su leyenda va curvada,
    así que el OCR de la hoja entera la devuelve hecha pedazos ("NOTARIA DEFE
    PULCA DEP.SMERA CLAN0.48"). Para leerlo hay que encontrarlo en la imagen,
    recortarlo y desenrollar su corona, que es trabajo de OpenCV.

    Devuelve un iterador y no una lista a propósito: cada lectura de sello cuesta
    una llamada al OCR (segundos), así que quien lo consume deja de pedir en
    cuanto tiene lo que buscaba y las fotos siguientes no se procesan. El orden
    es foto por foto, y dentro de cada sello primero el recorte derecho y después
    su corona desenrollada, porque esa es la que cuesta.

    Como el resto de la lectura en servidor, nunca dentro de una petición.
    """

    @abstractmethod
    def read(self, pages: Sequence[bytes]) -> Iterator[str]:
        """Las fotos de un documento, en orden de página -> el texto de cada
        lectura de sello. Nunca levanta por una foto que no se pudo abrir: esa
        foto simplemente no aporta sellos."""
