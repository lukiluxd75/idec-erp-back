"""
Pure-domain tests (layout, header, column A) over OCR output captured from a
real 2-page folio real run through the pipeline (GAMC OCR service), with names,
CI numbers and addresses replaced by fictitious ones. Blocks are in the upright
frame the pipeline produced; the column A blocks are in page frame.
"""
import json
import unittest
from pathlib import Path

from app.domains.folios.domain.entities.ocr_block import OcrBlock
from app.domains.folios.domain.services.header_parser import _parse_surface, parse_header
from app.domains.folios.domain.services.layout import detect_rotation, plan_regions, transform_blocks
from app.domains.folios.domain.services.text import strip_filler
from app.domains.folios.domain.services.titularidad_parser import ColumnLine, current_owners, parse_titularidad

FIXTURE = Path(__file__).parent / "fixtures" / "folio_2_paginas_ocr.json"


def _blocks(raw):
    return [OcrBlock(b["text"], b["confidence"], *b["box"]) for b in raw]


def load_pages():
    pages = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {p["page_number"]: p for p in pages}


class TestOrientation(unittest.TestCase):
    def test_upright_page_needs_no_rotation(self):
        page = load_pages()[1]
        self.assertLess(abs(detect_rotation(_blocks(page["blocks_page"]))), 2)

    def test_page_scanned_sideways_is_detected(self):
        # Turn the upright boxes 90° clockwise (what the sample scan looked like):
        # (x, y) -> (H - y, x). Undoing it needs +90° counter-clockwise.
        page = load_pages()[1]
        height = page["size"][1]
        cw = ((0.0, -1.0, float(height)), (1.0, 0.0, 0.0))
        turned = transform_blocks(_blocks(page["blocks_page"]), cw)
        self.assertAlmostEqual(detect_rotation(turned), 90, delta=2)

    def test_upside_down_page(self):
        page = load_pages()[2]
        w, h = page["size"]
        flip = ((-1.0, 0.0, float(w)), (0.0, -1.0, float(h)))
        angle = detect_rotation(transform_blocks(_blocks(page["blocks_page"]), flip))
        self.assertAlmostEqual(abs(angle), 180, delta=2)

    def test_no_titles_means_unknown(self):
        self.assertIsNone(detect_rotation([OcrBlock("hola", 1, 0, 0, 10, 10)]))


class TestLayout(unittest.TestCase):
    def test_first_page_regions(self):
        page = load_pages()[1]
        w, h = page["size"]
        layout = plan_regions(_blocks(page["blocks_page"]), page["vertical_lines"], w, h)
        self.assertTrue(layout.has_header)
        self.assertEqual((layout.page_number, layout.page_total), (1, 2))
        self.assertEqual(layout.issue_date, "06/02/2025")
        # Column A crop spans from the left border to the PROPORCIÓN|B line.
        lines = sorted(page["vertical_lines"])
        x0, y0, x1, y1 = layout.titularidad_rect
        self.assertLess(abs(x0 - lines[0]), 15)
        self.assertLess(abs(x1 - lines[2]), 15)
        self.assertEqual(layout.proportion_range, (lines[1], lines[2]))
        # Header ends above the column titles, column A starts below them.
        self.assertLess(layout.header_rect[3], y0)

    def test_second_page_has_no_header(self):
        page = load_pages()[2]
        w, h = page["size"]
        layout = plan_regions(_blocks(page["blocks_page"]), page["vertical_lines"], w, h)
        self.assertFalse(layout.has_header)
        self.assertIsNone(layout.header_rect)
        self.assertIsNotNone(layout.titularidad_rect)
        self.assertEqual((layout.page_number, layout.page_total), (2, 2))

    def test_without_ruling_lines_falls_back_to_titles(self):
        page = load_pages()[1]
        w, h = page["size"]
        layout = plan_regions(_blocks(page["blocks_page"]), [], w, h)
        self.assertIsNotNone(layout.titularidad_rect)
        self.assertIsNone(layout.proportion_range)


class TestHeaderParser(unittest.TestCase):
    def setUp(self):
        page = load_pages()[1]
        self.result = parse_header(_blocks(page["blocks_header"]), page["header_width"])
        self.data = self.result.data

    def test_matricula(self):
        self.assertEqual(
            self.data["matricula"],
            {"numero": "3.01.1.01.0012345", "estado": "VIGENTE", "zona": "CERCADO,PRIMERA,ITOCTA"},
        )

    def test_simple_fields(self):
        self.assertEqual(self.data["tipo_inmueble"], "Lote de Terreno")
        self.assertEqual(self.data["ubicacion"], "URB. LAS FLORES, MANZANA Y-1")
        self.assertEqual(self.data["designacion_s_tit"], "LOTE N° 24")
        self.assertEqual(self.data["medidas"], "NSC")
        self.assertEqual(self.data["propiedad"], "INDEFINIDA")

    def test_surface(self):
        self.assertEqual(self.data["superficie"]["valor"], 280.0)
        self.assertEqual(self.data["superficie"]["unidad"], "m2")

    def test_linderos(self):
        self.assertEqual(
            self.data["linderos"],
            {
                "norte": "CON LA CALLE INNOMINADA",
                "sud": "CON EL LOTE N° 3",
                "este": "CON EL LOTE N° 22",
                "oeste": "CON LOS LOTES N° 1 Y 2",
            },
        )

    def test_no_observations_and_confidences(self):
        self.assertEqual(self.result.observations, [])
        self.assertTrue(all(v is not None for v in self.result.confidence.values()))

    def test_surface_number_formats(self):
        self.assertEqual(_parse_surface("****280.00 Metros 2"), (280.0, "m2"))
        self.assertEqual(_parse_surface("1.250,50 Metros 2"), (1250.5, "m2"))
        self.assertEqual(_parse_surface("1,250.50 M2"), (1250.5, "m2"))
        self.assertEqual(_parse_surface("2,5000 Has."), (2.5, "ha"))


class TestTitularidadParser(unittest.TestCase):
    def _lines(self, *texts, proportions=None):
        proportions = proportions or {}
        return [ColumnLine(t, 0.95, 0, proportions.get(i)) for i, t in enumerate(texts)]

    def test_sample_column(self):
        lines = self._lines(
            "Asiento Numero: 0---------",
            "Vendedor(es):-------------",
            "PEREZ LOPEZ MARIA-----------",
            "Asiento Numero: l-------",
            "ROJAS VARGAS JUAN------------",
            "s01.C/CI1234567CBA-----------",
            "Compra.Venta-",
            "Escrit. Priv. de fecha 12/l0/1992---",
            "Not- Pub.PEDRO GOMEZ",
            "JUEZ DE MINIMA CUANTIA---",
            "Present.-No.89304de27/10/2014.-Hrs.112456-",
            "---[GPF]-[GPF]-[GPF]------------",
            "*****+*****+****",
            "---Ultimo Asiento Nro. l---",
            proportions={2: "1/1", 4: "1/1"},
        )
        r = parse_titularidad(lines)
        self.assertEqual(r["ultimo_asiento"], 1)
        a0, a1 = r["asientos"]
        self.assertEqual(a0["numero"], 0)
        self.assertEqual(a0["personas"][0]["nombre"], "PEREZ LOPEZ MARIA")
        self.assertEqual(a0["personas"][0]["rol"], "vendedor")
        self.assertEqual(a1["numero"], 1)
        person = a1["personas"][0]
        self.assertEqual(
            (person["nombre"], person["rol"], person["estado_civil"], person["ci"], person["expedido"], person["proporcion"]),
            ("ROJAS VARGAS JUAN", "titular", "soltero(a)", "1234567", "CBA", "1/1"),
        )
        self.assertEqual(a1["acto"], "Compra.Venta")
        self.assertEqual(a1["documento"], {"descripcion": "Escrit. Priv. de fecha 12/l0/1992", "fecha": "12/10/1992"})
        self.assertEqual(a1["autoridad"], "Not. Pub. PEDRO GOMEZ - JUEZ DE MINIMA CUANTIA")
        self.assertEqual(a1["presentacion"], {"numero": "89304", "fecha": "27/10/2014", "hora": "11:24:56"})
        self.assertEqual(current_owners(r["asientos"]), [
            {"nombre": "ROJAS VARGAS JUAN", "ci": "1234567", "proporcion": "1/1", "asiento": 1}
        ])

    def test_missing_asiento_digit_is_inferred(self):
        r = parse_titularidad(self._lines(
            "Asiento Numero:", "Vendedor(es):", "PEREZ LOPEZ MARIA",
            "Asiento Numero: 1", "ROJAS VARGAS JUAN", "Compra Venta",
        ))
        self.assertEqual(r["asientos"][0]["numero"], 0)
        self.assertTrue(r["asientos"][0]["numero_inferido"])
        self.assertNotIn("numero_inferido", r["asientos"][1])

    def test_low_resolution_ocr_variants(self):
        # What the OCR returned for a ~1000 px wide photo of the sample folio
        # (names anonymized): digits of 'Asiento Numero' lost, glued words,
        # 'Vendedor(es):' without colon, the 'CI' of the CI line lost.
        r = parse_titularidad(self._lines(
            "Asiento-Numeco:",
            "Vendedorles",
            "PEREZLOPEZMARIA",
            "Asiento Numero:",
            "ROJASVARGASJUAN",
            "ol..c/11234567",
            "CompraVente",
            "Escrit.Priv.de techa 12/10/1992",
            "NOt.PUD.PEDROGOMEZ",
            "Present.-No89304de27/10/2014.-Hrs.112456-",
            "-utamo-Fstento.Meo.",
            proportions={2: "1/1", 4: "1/1"},
        ))
        a0, a1 = r["asientos"]
        self.assertEqual((a0["numero"], a1["numero"]), (0, 1))
        self.assertTrue(a0["numero_inferido"] and a1["numero_inferido"])
        self.assertEqual(a0["personas"][0]["rol"], "vendedor")
        self.assertEqual(a1["personas"][0]["ci"], "1234567")
        self.assertEqual(a1["acto"], "CompraVente")
        self.assertEqual(a1["documento"]["fecha"], "12/10/1992")
        self.assertEqual(a1["presentacion"], {"numero": "89304", "fecha": "27/10/2014", "hora": "11:24:56"})

    def test_numbers_counted_back_from_last_declared(self):
        r = parse_titularidad(self._lines(
            "Asiento Numero:", "ROJAS VARGAS JUAN", "Asiento Numero:", "QUISPE MAMANI ROSA",
            "Ultimo Asiento Nro. 5",
        ))
        self.assertEqual([a["numero"] for a in r["asientos"]], [4, 5])

    def test_several_owners_with_nationality(self):
        r = parse_titularidad(self._lines(
            "Asiento Numero: 2",
            "QUISPE MAMANI ROSA",
            "cas. c/ C.I. 3333333 LP",
            "Boliviano(a)",
            "QUISPE MAMANI ANA",
            "sol. nac. 01/12/1987 c/ C.I. 4444444 CBA",
            "Declaratoria de Herederos",
            "Resol. Judicial de fecha 01/02/2020",
            proportions={1: "1/2", 4: "1/2"},
        ))
        people = r["asientos"][0]["personas"]
        self.assertEqual([p["nombre"] for p in people], ["QUISPE MAMANI ROSA", "QUISPE MAMANI ANA"])
        self.assertEqual(people[0]["estado_civil"], "casado(a)")
        self.assertEqual(people[0]["nacionalidad"], "Boliviano(a)")
        self.assertEqual((people[1]["ci"], people[1]["fecha_nacimiento"]), ("4444444", "01/12/1987"))
        self.assertEqual([p["proporcion"] for p in people], ["1/2", "1/2"])
        self.assertEqual(r["asientos"][0]["acto"], "Declaratoria de Herederos")
        self.assertEqual(r["asientos"][0]["documento"]["fecha"], "01/02/2020")

    def test_lines_before_first_asiento_are_kept(self):
        r = parse_titularidad(self._lines("texto suelto", "Asiento Numero: 1", "ROJAS VARGAS JUAN"))
        self.assertEqual(r["lineas_sin_asiento"], ["texto suelto"])

    def test_empty_column(self):
        r = parse_titularidad([])
        self.assertEqual((r["asientos"], r["ultimo_asiento"]), ([], None))


class TestText(unittest.TestCase):
    def test_strip_filler(self):
        self.assertEqual(strip_filler("Asiento Numero: 1-------"), "Asiento Numero: 1")
        self.assertEqual(strip_filler("---Ultimo Asiento Nro. 1---"), "Ultimo Asiento Nro. 1")
        self.assertEqual(strip_filler("3.01.1.01.0012345"), "3.01.1.01.0012345")


if __name__ == "__main__":
    unittest.main()
