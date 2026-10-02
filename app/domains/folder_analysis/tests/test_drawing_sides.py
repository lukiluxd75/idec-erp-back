import unittest

from app.domains.folder_analysis.application.use_cases.document_use_cases import RunServerReadingUseCase
from app.domains.folder_analysis.domain.folder_types import document_fields
from app.domains.folder_analysis.domain.services import drawing_sides, plan_checks
from app.domains.folder_analysis.domain.services.field_harvest import harvest

# The labels of the drawing of PlanoPoseedoresV2 as the OCR gave them over the
# drawing alone (centre and size, in pixels): the lot has its frente on the right
# beside "CALLE DE 10.00 mts.", a contra frente on the left, a fondo above and one
# below, and a diagonal of 30.18 m inside it that is not a side.
V2_DIMENSIONS = [
    {"value": 29.61, "x": 740, "y": 348, "w": 138, "h": 63},
    {"value": 9.96, "x": 201, "y": 400, "w": 52, "h": 126},
    {"value": 30.18, "x": 1000, "y": 408, "w": 139, "h": 57},
    {"value": 29.61, "x": 689, "y": 646, "w": 138, "h": 66},
    {"value": 10.11, "x": 1182, "y": 582, "w": 58, "h": 137},
]
V2_STREET = {"width_m": 10.0, "x": 1231, "y": 590, "w": 70, "h": 352}


class DrawingSidesTest(unittest.TestCase):
    def test_reads_a_measure_and_nothing_else(self):
        self.assertEqual(drawing_sides.parse_dimension("29.61m"), 29.61)
        self.assertEqual(drawing_sides.parse_dimension("9.96m:"), 9.96)
        self.assertEqual(drawing_sides.parse_dimension("10,11 m"), 10.11)
        # A surface, a street, a garbled label: none is a side.
        self.assertIsNone(drawing_sides.parse_dimension("295.31 m2"))
        self.assertIsNone(drawing_sides.parse_dimension("CALLE DE 10.00 mts."))
        self.assertIsNone(drawing_sides.parse_dimension("u966"))

    def test_reads_the_width_of_a_street_label(self):
        self.assertEqual(drawing_sides.parse_street("CALLE DE 10.00 mts."), 10.0)
        self.assertEqual(drawing_sides.parse_street("CALLE DE 10.00mts."), 10.0)
        self.assertEqual(drawing_sides.parse_street("AVENIDA DE 12 MTS"), 12.0)
        self.assertIsNone(drawing_sides.parse_street("LOTE N"))

    def test_the_frente_is_beside_the_street_and_the_diagonal_is_left_out(self):
        got = drawing_sides.assign(V2_DIMENSIONS, V2_STREET, 295.31)
        self.assertEqual(
            got["values"],
            {"frontage": "10.11 m", "rear_frontage": "9.96 m", "depth": "29.61 m", "depth_2": "29.61 m"},
        )
        self.assertIn("diagonal", got["note"])

    def test_a_street_below_the_lot_makes_the_horizontal_side_the_frente(self):
        # The same lot turned: the street runs across the bottom.
        turned = [
            {"value": 10.11, "x": 600, "y": 900, "w": 137, "h": 58},
            {"value": 9.96, "x": 600, "y": 100, "w": 126, "h": 52},
            {"value": 29.61, "x": 100, "y": 500, "w": 63, "h": 138},
            {"value": 29.61, "x": 1100, "y": 500, "w": 66, "h": 138},
        ]
        got = drawing_sides.assign(turned, {"width_m": 10.0, "x": 600, "y": 1000, "w": 352, "h": 70}, 295.31)
        self.assertEqual(got["values"]["frontage"], "10.11 m")
        self.assertEqual(got["values"]["rear_frontage"], "9.96 m")
        self.assertEqual(got["values"]["depth"], "29.61 m")

    def test_a_missing_contra_frente_is_left_empty_not_invented(self):
        got = drawing_sides.assign([d for d in V2_DIMENSIONS if d["value"] != 9.96], V2_STREET, 295.31)
        self.assertNotIn("rear_frontage", got["values"])
        self.assertEqual(got["values"]["frontage"], "10.11 m")
        self.assertIn("contra frente", got["note"])

    def test_measures_that_do_not_draw_the_declared_lot_are_not_trusted(self):
        got = drawing_sides.assign(V2_DIMENSIONS, V2_STREET, 150.0)
        self.assertEqual(got["values"], {})
        self.assertIn("150.00 m2", got["note"])

    def test_without_a_street_or_enough_labels_nothing_is_filled(self):
        self.assertEqual(drawing_sides.assign(V2_DIMENSIONS, None, 295.31)["values"], {})
        self.assertEqual(drawing_sides.assign(V2_DIMENSIONS[:2], V2_STREET, 295.31)["values"], {})

    def test_the_reading_fills_the_sides_and_the_street_width_from_the_drawing(self):
        values = {"usable_area": "295.31 M2", "street_width": None, "frontage": None}
        note = RunServerReadingUseCase._complete_plan_values(
            {"pages": [{"dimensions": V2_DIMENSIONS, "street": V2_STREET}]}, values
        )
        self.assertEqual(values["frontage"], "10.11 m")
        self.assertEqual(values["street_width"], "10.00 m")
        self.assertIn("diagonal", note)

    def test_what_the_text_already_gave_is_not_overwritten(self):
        values = {"usable_area": "295.31 M2", "street_width": "12.50 m, 9.00 m", "frontage": "12.00 m"}
        RunServerReadingUseCase._complete_plan_values(
            {"pages": [{"dimensions": V2_DIMENSIONS, "street": V2_STREET}]}, values
        )
        self.assertEqual(values["frontage"], "12.00 m")
        self.assertEqual(values["street_width"], "12.50 m, 9.00 m")


class SecondFormatBoxTest(unittest.TestCase):
    TEXT = (
        "DATOS DE UBICACION : PUKARA GRANDE NORTE\nZONA\nMANZANA : 494\na Berites LOTE VIA\n"
        "ARQUITECTO\nVo.13880 PROCESAMIENTO VB"
    )

    def test_the_zone_is_the_one_in_the_heading_not_the_next_label(self):
        box = plan_checks.read_location_block(self.TEXT)
        self.assertEqual(box["zone"], "PUKARA GRANDE NORTE")
        self.assertEqual(box["block"], "494")

    def test_a_blank_via_is_not_the_next_heading(self):
        self.assertIsNone(plan_checks.read_location_block(self.TEXT)["street"])

    def test_a_blank_lote_is_not_a_number(self):
        values, _ = harvest(
            {"full_text": "LOTE N°\n30.18m\nLOTE VIA", "pages": [{"fields": []}]},
            document_fields("possessors", "plan"),
        )
        self.assertIsNone(values["property_number"])


if __name__ == "__main__":
    unittest.main()
