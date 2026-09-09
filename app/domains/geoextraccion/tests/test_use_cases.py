import io
import unittest
import zipfile

from app.domains.geoextraccion.application.use_cases.generar_shapefile_use_case import (
    GenerarShapefileUseCase,
)
from app.domains.geoextraccion.application.use_cases.fusionar_shapefiles_use_case import (
    FusionarShapefilesUseCase,
)
from app.domains.geoextraccion.domain.entities.terreno import Punto, Terreno
from app.domains.geoextraccion.domain.exceptions import (
    GeometriaInvalidaException,
    ShapefileIlegibleException,
)
from app.domains.geoextraccion.infrastructure.geopandas_shapefile_adapter import (
    GeoPandasShapefileAdapter,
)


def _terreno_valido():
    return Terreno(
        puntos=[Punto(0, 0), Punto(1, 0), Punto(1, 1), Punto(0, 1)],
        atributos={"Predio": "1"},
    )


class TestGenerarShapefileUseCase(unittest.TestCase):
    def setUp(self):
        self.use_case = GenerarShapefileUseCase(shapefile_service=GeoPandasShapefileAdapter())

    def test_rechaza_poligono_sin_suficientes_puntos(self):
        terreno_invalido = Terreno(puntos=[Punto(0, 0), Punto(1, 1)], atributos={})

        with self.assertRaises(GeometriaInvalidaException):
            self.use_case.execute([terreno_invalido])

    def test_genera_un_zip_con_el_shapefile(self):
        contenido = self.use_case.execute([_terreno_valido()])

        with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
            nombres = zf.namelist()
            self.assertTrue(any(nombre.endswith(".shp") for nombre in nombres))


class TestFusionarShapefilesUseCase(unittest.TestCase):
    def setUp(self):
        self.use_case = FusionarShapefilesUseCase(shapefile_service=GeoPandasShapefileAdapter())

    def test_rechaza_lista_vacia(self):
        with self.assertRaises(ShapefileIlegibleException):
            self.use_case.execute([])

    def test_rechaza_archivos_no_leibles(self):
        with self.assertRaises(ShapefileIlegibleException):
            self.use_case.execute([b"esto no es un zip valido"])


if __name__ == "__main__":
    unittest.main()
