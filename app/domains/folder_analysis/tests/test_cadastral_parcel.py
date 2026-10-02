import unittest
from types import SimpleNamespace

from app.domains.folder_analysis.application.use_cases import (
    GenerateCadastralCroquisUseCase,
    LookupCadastralParcelUseCase,
)
from app.domains.folder_analysis.domain.exceptions import (
    CadastralLookupFailedException,
    CadastralParcelNotFoundException,
    InvalidDocumentRequestException,
)
from app.domains.folder_analysis.domain.ports import CadastralGisPort, GisParcel
from app.domains.folder_analysis.domain.services import cadastral_code, plan_checks, plan_survey
from app.domains.folder_analysis.domain.services.parcel_geometry import (
    Neighbour,
    Street,
    analyze_parcel,
    boundaries_text,
    compass_point,
)
from app.domains.folder_analysis.domain.services.utm import utm_to_wgs84

# Predio 33432012 (manzana 432 of Khara Khara), as the cadastre's GIS answers it.
REAL_RING = [
    [806111.6306, 8063477.0025], [806133.7134, 8063493.0354], [806135.3897, 8063491.333],
    [806135.9309, 8063490.681], [806136.3543, 8063489.9471], [806136.6476, 8063489.1522],
    [806136.8025, 8063488.3193], [806136.8145, 8063487.4721], [806136.6834, 8063486.635],
    [806136.4127, 8063485.8321], [806136.0104, 8063485.0865], [806135.488, 8063484.4194],
    [806134.8605, 8063483.8502], [806117.053, 8063470.2595], [806111.6306, 8063477.0025],
]

PLAN_TEXT = """
Código Catastral: 00-33-432-012-0-00-000-000
COORDENADAS UTM-WGS-84ZONA 19
P1 E 806132.14 N 8063496.75
P2 E 806141.45 N 8063487.34
P3 E 806124.22 N 8063474.20
P4 E 806112.27 N 8063481.58
SUPERFICIE TOTAL UTIL:..............294.66 m2
"""


def square(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


class CompassTest(unittest.TestCase):
    def test_each_point_owns_45_degrees_centred_on_it(self):
        self.assertEqual(compass_point(0)[1], "N")
        self.assertEqual(compass_point(22.4)[1], "N")
        self.assertEqual(compass_point(22.6)[1], "NE")
        self.assertEqual(compass_point(135)[1], "SE")
        self.assertEqual(compass_point(225)[1], "SO")
        self.assertEqual(compass_point(359)[1], "N")


class AnalyzeParcelTest(unittest.TestCase):
    def test_square_lot_with_a_neighbour_and_a_street(self):
        lot = square(0, 0, 10, 20)
        neighbours = [
            Neighbour("A", "5", square(10, 0, 20, 20)),  # to the east
            Neighbour("B", "7", square(-10, 0, 0, 20)),  # to the west
        ]
        streets = [Street("Calle", "", [[[-5, -8], [15, -8]]])]  # south, unnamed
        result = analyze_parcel(lot, "SELF", neighbours, streets)
        by_point = {side.point: side for side in result.sides}
        self.assertEqual(by_point["Este"].name, "5")
        self.assertEqual(by_point["Oeste"].name, "7")
        self.assertEqual(by_point["Sud"].name, "calle innominada")
        self.assertEqual(by_point["Norte"].kind, "none")
        self.assertAlmostEqual(result.area_m2, 200.0)
        self.assertEqual(
            result.boundaries,
            "Norte: sin colindante en el GIS; Este: lote 5; Sud: calle innominada; Oeste: lote 7",
        )

    def test_street_behind_the_lot_is_not_its_front(self):
        lot = square(0, 0, 10, 20)
        result = analyze_parcel(lot, "SELF", [], [Street("Calle", "Bolivar", [[[-5, -8], [15, -8]]])])
        by_point = {side.point: side for side in result.sides}
        self.assertEqual(by_point["Sud"].name, "calle Bolivar")
        self.assertEqual(by_point["Norte"].kind, "none")

    def test_a_corner_lot_faces_two_streets_even_when_neither_has_a_name(self):
        lot = square(0, 0, 10, 20)
        streets = [
            Street("Calle", "", [[[-5, -8], [15, -8]]], key="1"),  # south
            Street("Calle", "", [[[18, -10], [18, 30]]], key="2"),  # east
        ]
        result = analyze_parcel(lot, "SELF", [], streets)
        self.assertEqual(result.street_text, "calle innominada esquina calle innominada")
        self.assertEqual(len(result.streets), 2)

    def test_pieces_of_one_street_are_not_a_corner(self):
        lot = square(0, 0, 10, 20)
        pieces = [Street("Calle", "", [[[-5, -8], [4, -8]]], key="1"), Street("Calle", "", [[[4, -8], [15, -8]]], key="1")]
        self.assertEqual(analyze_parcel(lot, "SELF", [], pieces).street_text, "calle innominada")

    def test_the_predio_itself_is_never_its_own_neighbour(self):
        lot = square(0, 0, 10, 20)
        result = analyze_parcel(lot, "SELF", [Neighbour("SELF", "1", lot)], [])
        self.assertTrue(all(side.kind == "none" for side in result.sides))

    def test_a_lot_turned_from_the_north_uses_the_intercardinal_points(self):
        # A square turned 45 degrees: its sides face NE, SE, SO and NO.
        diamond = [[0, 10], [10, 0], [0, -10], [-10, 0], [0, 10]]
        result = analyze_parcel(diamond, "SELF", [], [])
        self.assertEqual({side.abbreviation for side in result.sides}, {"NE", "SE", "SO", "NO"})

    def test_a_rounded_corner_is_not_a_wall(self):
        neighbours = [Neighbour("33432011000000000", "11", square(806100, 8063478, 806134, 8063500))]
        result = analyze_parcel(REAL_RING, "33432012000000000", neighbours, [])
        # 14 edges, nine of them the arc: they must not become nine sides.
        self.assertLessEqual(len(result.sides), 8)
        self.assertAlmostEqual(result.area_m2, 222.92, places=1)

    def test_boundaries_text_lists_each_point_once(self):
        lot = square(0, 0, 10, 20)
        sides = analyze_parcel(lot, "SELF", [Neighbour("A", "5", square(10, 0, 20, 20))], []).sides
        self.assertEqual(boundaries_text(sides).count("Este"), 1)


class CadastralCodeTest(unittest.TestCase):
    def test_printed_code_is_cut_to_what_the_gis_stores(self):
        self.assertEqual(cadastral_code.to_gis_code("00-33-432-012-0-00-000-000"), "33432012000000000")
        self.assertEqual(cadastral_code.to_gis_code("33432012000000000"), "33432012000000000")

    def test_a_unit_inside_a_building_goes_back_to_its_lot(self):
        self.assertEqual(cadastral_code.to_gis_code("00-33-432-012-1-02-003-004"), "33432012100000000")

    def test_a_code_of_the_wrong_size_is_rejected(self):
        with self.assertRaises(InvalidDocumentRequestException):
            cadastral_code.to_gis_code("33-432")

    def test_printed_is_the_inverse(self):
        self.assertEqual(cadastral_code.printed("33432012000000000"), "00-33-432-012-0-00-000-000")


class PlanSurveyTest(unittest.TestCase):
    def test_reads_the_code_the_vertices_and_the_declared_surface(self):
        reading = plan_survey.read_plan(PLAN_TEXT)
        self.assertEqual(reading["printed_code"], "00-33-432-012-0-00-000-000")
        self.assertEqual(reading["declared_area_m2"], 294.66)
        sides = [side["length_m"] for side in reading["survey"]["sides"]]
        # The same numbers the plano prints as dimension lines.
        self.assertEqual(sides[0], 13.24)
        self.assertEqual(sides[1], 21.67)

    @staticmethod
    def _lot(width=10.0, depth=20.0):
        # A lot of width x depth with its frente on the south side, in UTM metres.
        return plan_survey.survey(
            [
                {"name": "P1", "east": 0.0, "north": 0.0},
                {"name": "P2", "east": width, "north": 0.0},
                {"name": "P3", "east": width, "north": depth},
                {"name": "P4", "east": 0.0, "north": depth},
            ]
        )

    def test_frente_is_the_side_on_the_street_and_the_fondos_are_the_other_two(self):
        street = [[[-30.0, -6.0], [40.0, -6.0]]]
        got = plan_survey.measures(self._lot(), street, 200.0)
        self.assertEqual(
            got["values"],
            {"frontage": "10.00 m", "rear_frontage": "10.00 m", "depth": "20.00 m", "depth_2": "20.00 m"},
        )
        self.assertIsNone(got["note"])

    def test_the_frente_follows_the_street_not_the_order_of_the_points(self):
        street = [[[-6.0, -30.0], [-6.0, 40.0]]]  # on the west side, 20 m long
        got = plan_survey.measures(self._lot(), street, 200.0)
        self.assertEqual(got["values"]["frontage"], "20.00 m")
        self.assertEqual(got["values"]["depth"], "10.00 m")

    def test_coordinates_that_do_not_give_the_declared_surface_are_not_trusted(self):
        got = plan_survey.measures(self._lot(), [[[-30.0, -6.0], [40.0, -6.0]]], 150.0)
        self.assertEqual(got["values"], {})
        self.assertIn("150.0 m2", got["note"])

    def test_a_corner_lot_leaves_the_frente_to_the_architect(self):
        streets = [[[-30.0, -6.0], [40.0, -6.0]], [[-6.0, -30.0], [-6.0, 40.0]]]
        got = plan_survey.measures(self._lot(20.0, 20.0), streets, 400.0)
        self.assertEqual(got["values"], {})
        self.assertIn("esquina", got["note"])

    def test_without_a_street_or_with_other_than_four_sides_nothing_is_filled(self):
        self.assertEqual(plan_survey.measures(self._lot(), [], 200.0)["values"], {})
        triangle = plan_survey.survey(
            [
                {"name": "P1", "east": 0.0, "north": 0.0},
                {"name": "P2", "east": 10.0, "north": 0.0},
                {"name": "P3", "east": 0.0, "north": 10.0},
            ]
        )
        self.assertEqual(plan_survey.measures(triangle, [[[0.0, -5.0], [10.0, -5.0]]], 50.0)["values"], {})
        self.assertIsNone(plan_survey.measures(None, [], None)["values"].get("frontage"))

    def test_the_plano_values_are_the_street_widths_and_the_predio_it_says(self):
        from app.domains.folder_analysis.domain.folder_types import document_fields
        from app.domains.folder_analysis.domain.services.field_harvest import harvest

        values, _missing = harvest(
            {
                "full_text": "LOTE N: 5 to CALLE DE 12.50 MTS.\nMANZANO 432\nLOTE 002\nVIA\nCalle de 9.00 mts.",
                "pages": [{"fields": []}],
            },
            document_fields("possessors", "plan"),
        )
        self.assertEqual(values["street_width"], "12.50 m, 9.00 m")
        # "MANZANO 432 LOTE 002": the lote of the box, not the "LOTE N: 5" of the drawing.
        self.assertEqual(values["property_number"], "2")

    def test_fewer_than_three_vertices_draw_nothing(self):
        self.assertIsNone(plan_survey.read_plan("P1 E 806132.14 N 8063496.75")["survey"])


LOCATION_BOX = """
CROQUIS DE UBICACION
ZONA : KHARA KHARA ARRUMANI
DISTRITO : 15
SUB DISTRITO : 33
MANZANA : 432
LOTE : 002
VIA : Calle de 9.00 mts.
PROCESAMIENTO V B
"""


class PlanChecksTest(unittest.TestCase):
    def test_reads_the_location_box(self):
        box = plan_checks.read_location_block(LOCATION_BOX)
        self.assertEqual(box["zone"], "KHARA KHARA ARRUMANI")
        self.assertEqual(box["district"], "15")
        self.assertEqual(box["subdistrict"], "33")
        self.assertEqual(box["block"], "432")
        self.assertEqual(box["lot"], "002")
        self.assertEqual(box["street"], "CALLE DE 9.00 MTS")

    def test_the_district_is_not_read_from_the_sub_district_line(self):
        box = plan_checks.read_location_block("SUB DISTRITO : 33")
        self.assertIsNone(box["district"])
        self.assertEqual(box["subdistrict"], "33")

    def test_a_lot_that_is_not_the_one_of_the_code_is_flagged(self):
        gis = {"zone": "KHARA KHARA ARRUMANI", "district": 15, "subdistrict": "33", "block": "432", "lot": "012"}
        checks = {c["key"]: c["status"] for c in plan_checks.cross_check(plan_checks.read_location_block(LOCATION_BOX), gis)}
        self.assertEqual(checks["zone"], "ok")
        self.assertEqual(checks["block"], "ok")
        self.assertEqual(checks["lot"], "differs")

    def test_a_line_the_ocr_did_not_read_is_missing_not_wrong(self):
        checks = {c["key"]: c["status"] for c in plan_checks.cross_check({}, {"block": "432"})}
        self.assertEqual(set(checks.values()), {"missing"})


# What the OCR really made of the plano of the example (a photo of a printed sheet):
# no colons, "MANZANO", a zone glued to its neighbour word, "TTAL" for "TOTAL".
OCR_TEXT = """
LOTE N: 5 to CALLE DE 12.50 MTS.
COORDENADAS UTM-WCS-84ZONA19
P1 E 806132.14N 8063496.75
P2 E 806141.45N 8063487.34 BLOQUESUP.mTIPOLOGiA ANO DE CONSTRUCCION
P3 E806124.22 N8063474.20 80 8.00m2 INTERES SOCIAL 2020
P4 E806112.27N8063481.58
Código Catastral: 00-33-432-012-0-00-000-000
SUP.S/MENSURA....
.294.66m2
SUPERFICIE TTAL UTIL...... ..294.66m2
ZONA
KHARA KHARAARRUMANI
DISTRITO :15
SUB DISTRITO33
REGISHRAACIUNTU7
MANZANO 432
LOTE 002
VIA
Calle de 9.00 mts.
PROCESAMIENTOVB
"""


class OcrNoiseTest(unittest.TestCase):
    def test_the_box_is_read_through_the_ocr_noise(self):
        box = plan_checks.read_location_block(OCR_TEXT)
        self.assertEqual(box["zone"], "KHARA KHARAARRUMANI")
        self.assertEqual(box["district"], "15")
        self.assertEqual(box["subdistrict"], "33")
        self.assertEqual(box["block"], "432")
        # Not the "LOTE N: 5" of the drawing, nor the "ZONA19" of the coordinates.
        self.assertEqual(box["lot"], "002")
        self.assertEqual(box["street"], "CALLE DE 9.00 MTS")

    def test_the_zone_glued_to_its_neighbour_still_matches_the_gis(self):
        gis = {"zone": "KHARA KHARA ARRUMANI", "district": 15, "subdistrict": "33", "block": "432", "lot": "012"}
        checks = {c["key"]: c["status"] for c in plan_checks.cross_check(plan_checks.read_location_block(OCR_TEXT), gis)}
        self.assertEqual(checks, {"zone": "ok", "district": "ok", "subdistrict": "ok", "block": "ok", "lot": "differs"})

    def test_the_surface_is_read_with_a_misspelled_label(self):
        self.assertEqual(plan_survey.declared_surface(OCR_TEXT), 294.66)

    def test_the_vertices_are_read_when_the_letters_stick_to_the_numbers(self):
        survey = plan_survey.read_plan(OCR_TEXT)["survey"]
        self.assertEqual([v["name"] for v in survey["vertices"]], ["P1", "P2", "P3", "P4"])
        self.assertEqual(survey["sides"][0]["length_m"], 13.24)


class UtmTest(unittest.TestCase):
    def test_converts_to_cochabamba(self):
        lat, lng = utm_to_wgs84(806132.14, 8063496.75)
        self.assertAlmostEqual(lat, -17.4938, places=3)
        self.assertAlmostEqual(lng, -66.1173, places=3)


class FakeGis(CadastralGisPort):
    def __init__(self, parcel):
        self._parcel = parcel

    def find_parcel(self, gis_code):
        return self._parcel

    def parcels_around(self, ring, distance_m):
        return []

    def streets_around(self, ring, distance_m):
        return [Street("Calle", "", [[[806140, 8063400], [806100, 8063470]]])]

    def land_use_at(self, point):
        return {"Uso_Suelo": "Residencial", "Retriccion": 0, "Distritos": 15, "Sbdistrito": "KHARA KHARA ARRUMANI"}

    def block_at(self, point):
        return {"Manzanas": "432", "Shape.STArea()": 5059.55, "Shape.STLength()": 294.83, "Nombre_SD": "KHARA KHARA ARRUMANI"}

    def map_image(self, layer, bbox, size, transparent):
        import cv2
        import numpy as np

        blank = np.full((size, size, 4), (255, 255, 255, 0 if transparent else 255), np.uint8)
        return cv2.imencode(".png", blank)[1].tobytes()


class LookupUseCaseTest(unittest.TestCase):
    def test_answers_with_the_map_and_compares_the_plano(self):
        gis = FakeGis(GisParcel("33432012000000000", REAL_RING, {"Nro_predio": "012", "Sbdistrito": "KHARA KHARA"}))
        result = LookupCadastralParcelUseCase(gis).execute("00-33-432-012-0-00-000-000", PLAN_TEXT)
        self.assertEqual(result["property_number"], "012")
        self.assertEqual(result["printed_code"], "00-33-432-012-0-00-000-000")
        self.assertEqual(len(result["map"]["parcel"]), len(REAL_RING))
        self.assertEqual(result["plan"]["declared_area_m2"], 294.66)
        self.assertGreater(result["plan"]["area_difference_m2"], 0)

    def test_brings_land_use_and_the_manzana(self):
        gis = FakeGis(GisParcel("33432012000000000", REAL_RING, {"Nro_predio": "012"}))
        result = LookupCadastralParcelUseCase(gis).execute("33432012000000000")
        self.assertEqual(result["land_use"]["use"], "Residencial")
        self.assertEqual(result["land_use"]["restriction"], 0)
        self.assertEqual(result["block_info"]["area_m2"], 5059.55)
        self.assertEqual(result["block_info"]["perimeter_m"], 294.83)

    def test_the_plano_box_is_checked_against_the_gis(self):
        gis = FakeGis(GisParcel("33432012000000000", REAL_RING, {
            "Nro_predio": "012", "Nro_manzan": "432", "Sbdist_Nro": "33", "distrito": 15, "Sbdistrito": "KHARA KHARA ARRUMANI",
        }))
        result = LookupCadastralParcelUseCase(gis).execute("33432012000000000", PLAN_TEXT + LOCATION_BOX)
        checks = {c["key"]: c["status"] for c in result["plan"]["checks"]}
        self.assertEqual(checks, {"zone": "ok", "district": "ok", "subdistrict": "ok", "block": "ok", "lot": "differs"})

    def test_the_croquis_is_a_png_of_the_requested_size(self):
        import cv2
        import numpy as np

        gis = FakeGis(GisParcel("33432012000000000", REAL_RING, {"Nro_predio": "012"}))
        png = GenerateCadastralCroquisUseCase(gis).execute("33432012000000000")
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(image.shape[:2], (600, 600))
        # The red circle and number were drawn over the blank layers.
        self.assertTrue((image[:, :, 2] > 200).any() and (image[:, :, 1] < 80).any())

    def test_without_the_plano_there_is_nothing_to_compare(self):
        gis = FakeGis(GisParcel("33432012000000000", REAL_RING, {}))
        self.assertIsNone(LookupCadastralParcelUseCase(gis).execute("33432012000000000")["plan"])

    def test_a_code_the_gis_does_not_have(self):
        with self.assertRaises(CadastralParcelNotFoundException):
            LookupCadastralParcelUseCase(FakeGis(None)).execute("33432999000000000")


class BrokenGis(FakeGis):
    def find_parcel(self, gis_code):
        raise KeyError("boom")


class UnexpectedFailureTest(unittest.TestCase):
    def test_an_unexpected_error_becomes_a_message_not_a_dropped_connection(self):
        with self.assertRaises(CadastralLookupFailedException) as raised:
            LookupCadastralParcelUseCase(BrokenGis(None)).execute("33432012000000000")
        self.assertIn("KeyError", raised.exception.message)
        self.assertEqual(raised.exception.http_status, 502)

    def test_a_known_failure_keeps_its_own_status(self):
        with self.assertRaises(CadastralParcelNotFoundException):
            LookupCadastralParcelUseCase(FakeGis(None)).execute("33432012000000000")


class ParcelEndpointTest(unittest.TestCase):
    """GET /cadastral/parcel with the plano of a document, through FastAPI."""

    def setUp(self):
        import inspect
        from datetime import datetime

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.core.errors import register_exception_handlers
        from app.domains.folder_analysis.domain.entities import FolderDocument
        from app.domains.folder_analysis.presentation import deps
        from app.domains.folder_analysis.presentation.endpoints import cadastral

        now = datetime(2026, 10, 1)
        self.document = FolderDocument(
            "d1", "u1", "plan", "extracted", now, now, folder_type="possessors",
            extracted_data={"full_text": PLAN_TEXT + LOCATION_BOX},
        )
        gis = FakeGis(GisParcel("33432012000000000", REAL_RING, {
            "Nro_predio": "012", "Nro_manzan": "432", "Sbdist_Nro": "33", "distrito": 15, "Sbdistrito": "KHARA KHARA ARRUMANI",
        }))
        document = self.document

        class Documents:
            def execute(self, document_id, user_sub):
                return document

        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(cadastral.router)
        app.dependency_overrides[inspect.signature(cadastral.lookup_parcel).parameters["user"].default.dependency] = lambda: SimpleNamespace(sub="u1")
        app.dependency_overrides[deps.get_cadastral_gis] = lambda: gis
        app.dependency_overrides[deps.get_get_document_use_case] = lambda: Documents()
        self.client = TestClient(app)

    def test_compares_the_plano_of_the_document_with_the_gis(self):
        response = self.client.get(
            "/cadastral/parcel", params={"code": "00-33-432-012-0-00-000-000", "document_id": "d1"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        checks = {c["key"]: c["status"] for c in response.json()["plan"]["checks"]}
        self.assertEqual(checks["block"], "ok")
        self.assertEqual(checks["lot"], "differs")

    def test_works_without_a_document(self):
        response = self.client.get("/cadastral/parcel", params={"code": "00-33-432-012-0-00-000-000"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["plan"])

    def test_falls_back_to_the_saved_review_when_nothing_was_extracted(self):
        self.document.reviewed_data, self.document.extracted_data = {"full_text": PLAN_TEXT}, None
        response = self.client.get(
            "/cadastral/parcel", params={"code": "00-33-432-012-0-00-000-000", "document_id": "d1"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["plan"]["declared_area_m2"], 294.66)

    def test_a_bad_code_is_a_422_with_a_message(self):
        response = self.client.get("/cadastral/parcel", params={"code": "12"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("19 dígitos", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
