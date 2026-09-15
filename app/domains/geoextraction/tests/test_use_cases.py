import io
import unittest
import zipfile

from app.domains.geoextraction.application.use_cases.generate_shapefile_use_case import (
    GenerateShapefileUseCase,
)
from app.domains.geoextraction.application.use_cases.merge_shapefiles_use_case import (
    MergeShapefilesUseCase,
)
from app.domains.geoextraction.domain.entities.parcel import Point, Parcel
from app.domains.geoextraction.domain.exceptions import (
    InvalidGeometryException,
    UnreadableShapefileException,
)
from app.domains.geoextraction.infrastructure.geopandas_shapefile_adapter import (
    GeoPandasShapefileAdapter,
)


def _valid_parcel():
    return Parcel(
        points=[Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)],
        attributes={"Predio": "1"},
    )


class TestGenerateShapefileUseCase(unittest.TestCase):
    def setUp(self):
        self.use_case = GenerateShapefileUseCase(shapefile_service=GeoPandasShapefileAdapter())

    def test_rejects_polygon_without_enough_points(self):
        invalid_parcel = Parcel(points=[Point(0, 0), Point(1, 1)], attributes={})

        with self.assertRaises(InvalidGeometryException):
            self.use_case.execute([invalid_parcel])

    def test_generates_a_zip_with_the_shapefile(self):
        content = self.use_case.execute([_valid_parcel()])

        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = zf.namelist()
            self.assertTrue(any(name.endswith(".shp") for name in names))


class TestMergeShapefilesUseCase(unittest.TestCase):
    def setUp(self):
        self.use_case = MergeShapefilesUseCase(shapefile_service=GeoPandasShapefileAdapter())

    def test_rejects_empty_list(self):
        with self.assertRaises(UnreadableShapefileException):
            self.use_case.execute([])

    def test_rejects_unreadable_files(self):
        with self.assertRaises(UnreadableShapefileException):
            self.use_case.execute([b"esto no es un zip valido"])


if __name__ == "__main__":
    unittest.main()
