import unittest

from app.domains.folder_analysis.domain.exceptions import InvalidDocumentRequestException
from app.domains.folder_analysis.domain.folder_types import document_fields
from app.domains.folder_analysis.domain.services import cadastral_code, plan_checks, plan_survey
from app.domains.folder_analysis.domain.services.field_harvest import harvest

# The table of coordinates of PlanoPoseedoresV3 as the OCR gave it: the P1..P4 column
# is lost and the OCR swapped the rows of P2 and P3.
V3_TABLE = (
    "PUNTOS PERIMETROS DE LOTE\nCOORDENADAS GPS. UTM. WGS-84\nPUNTOS ESTE(X NORTE (Y)_DISTANCIA (Mts)\n"
    "E795805.354 N 8065810.909\n"
    "E 795825.883N 8065794.856 E 795828.137N 8065806.642 12.00 23.18\n"
    "E795803.077 N 8065799.124 23.20\n"
    "E795805.354N8065810.909 12.00\n"
)
V3_TEXT = (
    "DE 11.00 Mts. LOTE N°003 23.18\nCALLE SUP.TOTAL UTIL LOTE N°002\nR5.00 267.55 m2\n23.20 R5.00\n"
    + V3_TABLE
    + "Código Catastral: 00-30-B37-002-0-00-000-000\n.267.55 m2\n267.55m\n67.55m\n"
    "DATOS DE UBICACION\nZONA\n.1ro DE MAYO\nSUB DISTRITO .....30\nMANZANO ...B37\nLOTE\n......0.\n"
    "VIA\n.CALLEDE11.00Mts\nSELLO COLEGIO DE ARQUITECTOS"
)
# The west side is the street; the lot is the one of the plano (23.2 x 12, two R5 corners).
WEST_STREET = [[[795795.0, 8065790.0], [795799.0, 8065815.0]]]


class CodeWithALetterTest(unittest.TestCase):
    def test_the_printed_code_keeps_the_letter_of_the_manzana(self):
        self.assertEqual(plan_survey.printed_code(V3_TEXT), "00-30-B37-002-0-00-000-000")

    def test_the_gis_knows_it_by_its_seventeen_characters(self):
        self.assertEqual(cadastral_code.to_gis_code("00-30-B37-002-0-00-000-000"), "30B37002000000000")
        self.assertEqual(cadastral_code.to_gis_code("30B37002000000000"), "30B37002000000000")
        self.assertEqual(cadastral_code.printed("30B37002000000000"), "00-30-B37-002-0-00-000-000")

    def test_a_letter_anywhere_else_is_the_ocr_confusing_a_digit(self):
        self.assertEqual(cadastral_code.to_gis_code("00-30-432-O12-0-00-000-000"), "30432012000000000")
        with self.assertRaises(InvalidDocumentRequestException):
            cadastral_code.to_gis_code("00-30-432-0X2-0-00-000-000")

    def test_the_reading_takes_the_code_with_the_letter(self):
        values, _ = harvest({"full_text": V3_TEXT, "pages": [{"fields": []}]}, document_fields("possessors", "plan"))
        self.assertEqual(values["cadastral_code"], "00-30-B37-002-0-00-000-000")


class UnlabelledCoordinatesTest(unittest.TestCase):
    def test_the_vertices_are_paired_by_position_and_the_swapped_rows_put_back(self):
        vertices = plan_survey.parse_vertices(V3_TABLE)
        self.assertEqual([v["name"] for v in vertices], ["P1", "P2", "P3", "P4"])
        survey = plan_survey.survey(vertices)
        # The sides the table prints in its DISTANCIA column.
        self.assertEqual(sorted(s["length_m"] for s in survey["sides"]), [12.0, 12.0, 23.18, 23.2])
        self.assertEqual(survey["area_m2"], 278.31)

    def test_labelled_points_still_win(self):
        text = "P1 E 806132.14 N 8063496.75 P2 E 806141.45 N 8063487.34 P3 E806124.22 N8063474.20"
        self.assertEqual([v["name"] for v in plan_survey.parse_vertices(text)], ["P1", "P2", "P3"])

    def test_without_the_same_number_of_eastings_and_northings_nothing_is_guessed(self):
        self.assertEqual(plan_survey.parse_vertices("E 795805.354 E 795828.137 N 8065810.909"), [])


class SurfaceAndCornersTest(unittest.TestCase):
    def test_the_surface_is_the_figure_the_sheet_repeats(self):
        self.assertEqual(plan_survey.declared_surface(V3_TEXT), 267.55)
        # A side the OCR put after the label is not the surface.
        self.assertEqual(
            plan_survey.declared_surface("SUP. TOTAL UTIL 30.18m\n295.31 m2\n.295.31 m2\n394.94m2"), 295.31
        )

    def test_the_rounded_corners_are_read(self):
        self.assertEqual(plan_survey.corner_radii(V3_TEXT), [5.0, 5.0])
        self.assertEqual(plan_survey.corner_radii("R.M. 12.00 SUP"), [])

    def test_the_net_surface_leaves_out_the_rounded_corners(self):
        survey = plan_survey.read_plan(V3_TEXT)["survey"]
        self.assertEqual(survey["area_m2"], 278.31)
        self.assertAlmostEqual(survey["area_net_m2"], 267.57, places=1)

    def test_sides_are_computed_when_the_rounded_corners_explain_the_difference(self):
        reading = plan_survey.read_plan(V3_TEXT)
        got = plan_survey.measures(reading["survey"], WEST_STREET, 267.55, plan_survey.corner_radii(V3_TEXT))
        self.assertEqual(
            got["values"],
            {"frontage": "12.00 m", "rear_frontage": "12.00 m", "depth": "23.18 m", "depth_2": "23.20 m"},
        )

    def test_without_the_corners_the_same_difference_is_not_trusted(self):
        reading = plan_survey.read_plan(V3_TEXT)
        got = plan_survey.measures(reading["survey"], WEST_STREET, 267.55)
        self.assertEqual(got["values"], {})
        self.assertIn("267.55", got["note"])


class ThirdFormatBoxTest(unittest.TestCase):
    def test_the_manzana_may_be_a_code_with_a_letter(self):
        box = plan_checks.read_location_block(V3_TEXT)
        self.assertEqual(box["block"], "B37")
        self.assertEqual(box["zone"], "1RO DE MAYO")
        self.assertEqual(box["subdistrict"], "30")

    def test_a_smudged_lote_is_missing_not_wrong(self):
        self.assertIsNone(plan_checks.read_location_block(V3_TEXT)["lot"])

    def test_the_manzana_is_compared_letter_and_all(self):
        gis = {"zone": "1ro. DE MAYO", "district": 9, "subdistrict": "30", "block": "B37", "lot": "002"}
        checks = {c["key"]: c["status"] for c in plan_checks.cross_check(plan_checks.read_location_block(V3_TEXT), gis)}
        self.assertEqual(checks["block"], "ok")
        self.assertEqual(checks["lot"], "missing")
        gis["block"] = "A37"
        checks = {c["key"]: c["status"] for c in plan_checks.cross_check(plan_checks.read_location_block(V3_TEXT), gis)}
        self.assertEqual(checks["block"], "differs")


class ThirdFormatValuesTest(unittest.TestCase):
    def _values(self, text):
        values, _ = harvest({"full_text": text, "pages": [{"fields": []}]}, document_fields("possessors", "plan"))
        return values

    def test_the_street_width_is_read_even_when_the_ocr_glues_the_words(self):
        self.assertEqual(self._values(V3_TEXT)["street_width"], "11.00 m")

    def test_the_lote_is_the_one_over_its_own_surface_not_the_neighbours(self):
        self.assertEqual(self._values(V3_TEXT)["property_number"], "2")

    def test_a_blank_lote_followed_by_a_side_is_not_a_number(self):
        self.assertIsNone(self._values("SUP. TOTAL UTIL LOTE N° 30.18M 295.31 M2")["property_number"])


if __name__ == "__main__":
    unittest.main()
