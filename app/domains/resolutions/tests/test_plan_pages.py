"""
Planta de las páginas del plano: lectura del título (domain/plan_title.py)
contra el OCR de 6 planos reales (tests/fixtures, solo títulos, rótulos y
medidas), y los casos de uso de subida / detección / corrección sobre SQLite
en memoria (schema `resolutions` mapeado a ninguno).
"""
import json
import unittest
from datetime import datetime
from pathlib import Path
from typing import List

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database.connection import Base
from app.domains.resolutions.application.use_cases import (
    AddPlanPagesUseCase,
    DetectPlanPagePlantaUseCase,
    GetResolutionUseCase,
    RequestPlantaDetectionUseCase,
    SetPlanPagePlantasUseCase,
)
from app.domains.resolutions.domain.entities.resolution import PlantaStatus
from app.domains.resolutions.domain.exceptions import (
    InvalidPlantaException,
    PlanOcrUnavailableException,
    PlanPageNotFoundException,
)
from app.domains.resolutions.domain.plan_title import TitleBlock, detect_plantas, plantas_de_titulo
from app.domains.resolutions.domain.ports.plan_ocr_port import PlanOcrPort
from app.domains.resolutions.infrastructure.models import ResolutionModel, ResolutionPageModel
from app.domains.resolutions.infrastructure.plan_page_models import ResolutionPlanPageModel
from app.domains.resolutions.infrastructure.sql_resolution_repository import SqlResolutionRepository

FIXTURE = Path(__file__).parent / "fixtures" / "titulos_planos_ocr.json"
USER = "user-1"


def _bloques(raw) -> List[TitleBlock]:
    return [TitleBlock(b["text"], *b["box"]) for b in raw]


def _pisos(*n):
    return [f"PLANTA {i}º PISO" for i in n]


class TituloDePlantaTest(unittest.TestCase):
    def test_planos_reales(self):
        esperado = {
            "plano_0": ["PLANTA SEMISOTANO"],
            "plano_1": ["PLANTA BAJA"],
            "plano_2": _pisos(1),
            "plano_3": _pisos(2, 3, 4),
            "plano_4": _pisos(5),
            "plano_5": _pisos(6),
        }
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for nombre, plantas in esperado.items():
            with self.subTest(nombre):
                self.assertEqual(detect_plantas(_bloques(fixture[nombre])).plantas, plantas)

    def test_variantes_del_ocr(self):
        casos = {
            "PLANTA 1 ° PISO": _pisos(1),
            "PLANTA 10º PISO": _pisos(10),
            "PLANTA 5° PIS0": _pisos(5),
            "Planta Tipo 2° - 4° Piso": _pisos(2, 3, 4),
            "PLANTA TIPO 2 AL 4 PISO": _pisos(2, 3, 4),
            "PLANTA 2do PISO": _pisos(2),
            "PLANTA SEMI SOTANO": ["PLANTA SEMISOTANO"],
            "PLANTA SÓTANO": ["PLANTA SOTANO"],
            "PLANTA BAJA.": ["PLANTA BAJA"],
            # El OCR de los planos de dibujante lo lee pegado y con puntos.
            ".PLANTABAJA..": ["PLANTA BAJA"],
            "...PLANTASAJA.": ["PLANTA BAJA"],
            ".PLANTA1°PISO...": _pisos(1),
            "PLANTA3PISO": _pisos(3),
            "PLANTATIPO2-4PISO": _pisos(2, 3, 4),
        }
        for texto, plantas in casos.items():
            with self.subTest(texto):
                self.assertEqual(plantas_de_titulo(texto), plantas)

    def test_rotulos_que_no_son_titulo(self):
        # Rótulos de unidades dúplex que mencionan plantas: nunca son el título.
        for texto in (
            "DEPARTAMENTO A DUPLEX (PLANTA BAJA",
            "5° PIS0 +PLANTA ALTA 6° PIS0",
            "PISO+PLANTAALTA6PISO",
            "DUPLEX PLANTA ALTA",
            "PLANTA 4° - 2° PISO",
            "PLANTA 31° PISO",
            "PLANTA CUBIERTA",
        ):
            with self.subTest(texto):
                self.assertIsNone(plantas_de_titulo(texto))

    def test_titulo_partido_en_dos_bloques(self):
        bloques = [
            TitleBlock("PLANTA TIPO", 100, 100, 400, 160),
            TitleBlock("2° - 4° PISO", 440, 102, 700, 160),
            TitleBlock("PISO", 900, 900, 950, 920),
        ]
        d = detect_plantas(bloques)
        self.assertEqual(d.plantas, _pisos(2, 3, 4))
        self.assertEqual(d.titulo, "PLANTA TIPO 2° - 4° PISO")

    def test_elige_el_de_letra_mas_grande(self):
        bloques = [
            TitleBlock("PLANTA BAJA", 0, 0, 300, 20),  # rótulo chico dentro del plano
            TitleBlock("PLANTA 1° PISO", 0, 500, 900, 620),  # título
        ]
        self.assertEqual(detect_plantas(bloques).plantas, _pisos(1))

    def test_titulo_girado(self):
        # Plano de costado: el título vertical, su letra es el lado CORTO.
        bloques = [TitleBlock("PLANTA SEMISOTANO", 50, 100, 150, 1300), TitleBlock("PLANTA BAJA", 0, 0, 400, 30)]
        self.assertEqual(detect_plantas(bloques).plantas, ["PLANTA SEMISOTANO"])

    def test_dos_titulos_distintos_no_adivina(self):
        bloques = [TitleBlock("PLANTA BAJA", 0, 0, 900, 110), TitleBlock("PLANTA 1° PISO", 0, 500, 900, 600)]
        d = detect_plantas(bloques)
        self.assertEqual(d.plantas, [])
        self.assertIn("dos títulos", d.motivo)

    def test_sin_titulo(self):
        d = detect_plantas([TitleBlock("ESC: 1:100", 0, 0, 100, 20), TitleBlock("COCINA", 0, 50, 80, 70)])
        self.assertEqual(d.plantas, [])
        self.assertIsNotNone(d.motivo)


class FakeOcr(PlanOcrPort):
    def __init__(self, bloques=None, falla=False):
        self._bloques = bloques or []
        self._falla = falla

    def read(self, image_bytes, filename="plano.jpg"):
        if self._falla:
            raise PlanOcrUnavailableException("El servicio OCR no respondió a tiempo.")
        return self._bloques


def _new_repo() -> SqlResolutionRepository:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"resolutions": None}},
    )
    # Los modelos usan server_default now() de Postgres.
    event.listen(
        engine, "connect", lambda conn, _: conn.create_function("now", 0, lambda: datetime.utcnow().isoformat(" "))
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[ResolutionModel.__table__, ResolutionPageModel.__table__, ResolutionPlanPageModel.__table__],
    )
    db = sessionmaker(bind=engine)()
    db.add(
        ResolutionModel(
            resolution_id="res-1",
            resolution_number="123/2026",
            name="Edificio",
            status="pendiente_ocr",
            user_sub=USER,
            created_at=datetime(2026, 9, 25),
            updated_at=datetime(2026, 9, 25),
        )
    )
    db.commit()
    return SqlResolutionRepository(db=db)


class PaginasDelPlanoTest(unittest.TestCase):
    def setUp(self):
        self.repo = _new_repo()
        self.add = AddPlanPagesUseCase(self.repo)

    def _pagina(self, order_index):
        res = GetResolutionUseCase(self.repo).execute("res-1", USER)
        return next(p for p in res.plan_pages if p.order_index == order_index)

    def test_con_planta_queda_manual_sin_detectar(self):
        res, pendientes = self.add.execute("res-1", [(b"img", "image/jpeg", ["PLANTA BAJA"])], "app", USER)
        self.assertEqual(pendientes, [])
        self.assertEqual(res.plan_pages[0].plantas, ["PLANTA BAJA"])
        self.assertEqual(res.plan_pages[0].planta, "PLANTA BAJA")
        self.assertEqual(res.plan_pages[0].planta_status, PlantaStatus.MANUAL)

    def test_varias_plantas_en_una_foto_ordenadas(self):
        res, _ = self.add.execute("res-1", [(b"img", "image/jpeg", _pisos(4, 2, 3, 2))], "app", USER)
        self.assertEqual(res.plan_pages[0].plantas, _pisos(2, 3, 4))

    def test_sin_planta_se_detecta_del_titulo(self):
        res, pendientes = self.add.execute(
            "res-1", [(b"a", "image/jpeg", ["PLANTA BAJA"]), (b"b", "image/jpeg", [])], "app", USER
        )
        self.assertEqual(pendientes, [2])
        self.assertEqual(self._pagina(2).planta_status, PlantaStatus.DETECTANDO)
        self.assertEqual(self._pagina(2).planta, "")

        ocr = FakeOcr([TitleBlock("PLANTA TIPO 2° - 4° PISO", 0, 0, 900, 110), TitleBlock("ESC: 1:100", 0, 200, 200, 230)])
        page = DetectPlanPagePlantaUseCase(self.repo, ocr).execute("res-1", 2)
        self.assertEqual(page.plantas, _pisos(2, 3, 4))
        self.assertEqual(page.planta_status, PlantaStatus.DETECTADA)
        self.assertEqual(page.planta_title, "PLANTA TIPO 2° - 4° PISO")
        self.assertEqual(self._pagina(2).plantas, _pisos(2, 3, 4))
        # La otra página no se toca.
        self.assertEqual(self._pagina(1).plantas, ["PLANTA BAJA"])

    def test_sin_titulo_queda_para_asignar_a_mano(self):
        self.add.execute("res-1", [(b"a", "image/jpeg", [])], "app", USER)
        page = DetectPlanPagePlantaUseCase(self.repo, FakeOcr([TitleBlock("COCINA", 0, 0, 100, 20)])).execute("res-1", 1)
        self.assertEqual(page.plantas, [])
        self.assertEqual(page.planta_status, PlantaStatus.SIN_TITULO)
        self.assertTrue(page.planta_detection["motivo"])

    def test_ocr_caido_queda_en_error_y_se_reintenta(self):
        self.add.execute("res-1", [(b"a", "image/jpeg", [])], "app", USER)
        page = DetectPlanPagePlantaUseCase(self.repo, FakeOcr(falla=True)).execute("res-1", 1)
        self.assertEqual(page.planta_status, PlantaStatus.ERROR)
        self.assertIn("no respondió", page.planta_detection["motivo"])

        self.assertEqual(
            RequestPlantaDetectionUseCase(self.repo).execute("res-1", 1, USER).planta_status, PlantaStatus.DETECTANDO
        )
        ocr = FakeOcr([TitleBlock("PLANTA 5° PISO", 0, 0, 900, 110)])
        self.assertEqual(DetectPlanPagePlantaUseCase(self.repo, ocr).execute("res-1", 1).plantas, _pisos(5))

    def test_correccion_a_mano(self):
        self.add.execute("res-1", [(b"a", "image/jpeg", [])], "app", USER)
        page = SetPlanPagePlantasUseCase(self.repo).execute("res-1", 1, _pisos(3, 2), USER)
        self.assertEqual(page.plantas, _pisos(2, 3))
        self.assertEqual(page.planta_status, PlantaStatus.MANUAL)

    def test_correccion_valida_plantas_y_dueno(self):
        self.add.execute("res-1", [(b"a", "image/jpeg", [])], "app", USER)
        uc = SetPlanPagePlantasUseCase(self.repo)
        with self.assertRaises(InvalidPlantaException):
            uc.execute("res-1", 1, ["PLANTA CUBIERTA"], USER)
        with self.assertRaises(InvalidPlantaException):
            uc.execute("res-1", 1, [], USER)
        with self.assertRaises(PlanPageNotFoundException):
            uc.execute("res-1", 1, ["PLANTA BAJA"], "otro-usuario")
        with self.assertRaises(PlanPageNotFoundException):
            uc.execute("res-1", 9, ["PLANTA BAJA"], USER)

    def test_planta_invalida_al_subir(self):
        with self.assertRaises(InvalidPlantaException):
            self.add.execute("res-1", [(b"a", "image/jpeg", ["PLANTA CUBIERTA"])], "app", USER)

    def test_filas_viejas_con_una_sola_planta(self):
        # Páginas subidas antes de la columna `plantas`: se lee `planta`.
        self.repo._db.add(
            ResolutionPlanPageModel(
                plan_page_id="pp-viejo",
                resolution_id="res-1",
                order_index=1,
                planta="PLANTA BAJA",
                plantas=None,
                planta_status="manual",
                image=b"a",
                mime="image/jpeg",
                source="app",
            )
        )
        self.repo._db.commit()
        page = self._pagina(1)
        self.assertEqual(page.plantas, ["PLANTA BAJA"])
        self.assertEqual(page.planta_status, PlantaStatus.MANUAL)


class MosaicosTest(unittest.TestCase):
    def test_cubre_la_imagen_con_solape_y_conserva_posicion(self):
        import cv2
        import numpy as np

        from app.domains.resolutions.domain.plan_tiles import mosaicos

        imagen = np.full((3000, 900, 3), 255, np.uint8)
        ok, jpg = cv2.imencode(".jpg", imagen)
        tiles = mosaicos(jpg.tobytes(), 700)
        self.assertGreater(len(tiles), 4)
        self.assertEqual(sorted({x0 for _, x0, _ in tiles}), [0, 560])
        ultimo_y = max(y0 for _, _, y0 in tiles)
        _, _, y0 = [t for t in tiles if t[2] == ultimo_y][0]
        alto = cv2.imdecode(np.frombuffer([t for t in tiles if t[2] == ultimo_y][0][0], np.uint8), 1).shape[0]
        self.assertEqual(ultimo_y + alto, 3000)

    def test_imagen_chica_no_se_corta(self):
        import cv2
        import numpy as np

        from app.domains.resolutions.domain.plan_tiles import mosaicos

        ok, jpg = cv2.imencode(".jpg", np.full((500, 500, 3), 255, np.uint8))
        self.assertEqual(mosaicos(jpg.tobytes(), 700), [])


class CortesTest(unittest.TestCase):
    def test_tramos_cubren_el_largo_con_solape(self):
        from app.domains.resolutions.domain.plan_tiles import SOLAPE, _cortes

        self.assertEqual(_cortes(500, 700), [(0, 500)])
        self.assertEqual(_cortes(700, 700), [(0, 700)])
        self.assertEqual(_cortes(1260, 700), [(0, 700), (560, 1260)])
        tramos = _cortes(3000, 700)
        self.assertEqual(tramos[0][0], 0)
        self.assertEqual(tramos[-1][1], 3000)
        for (_, fin), (ini, _) in zip(tramos, tramos[1:]):
            self.assertEqual(fin - ini, int(700 * SOLAPE))  # solape fijo entre vecinos
        self.assertTrue(all(fin - ini <= 700 for ini, fin in tramos))

    def test_demasiados_mosaicos_no_se_cortan(self):
        from unittest import mock

        import cv2
        import numpy as np

        from app.domains.resolutions.domain import plan_tiles

        ok, jpg = cv2.imencode(".jpg", np.full((3000, 900, 3), 255, np.uint8))
        self.assertGreater(len(plan_tiles.mosaicos(jpg.tobytes(), 700)), 2)
        with mock.patch.object(plan_tiles, "MAX_MOSAICOS", 2):
            self.assertEqual(plan_tiles.mosaicos(jpg.tobytes(), 700), [])

    def test_imagen_ilegible(self):
        from app.domains.resolutions.domain.plan_tiles import mosaicos

        self.assertEqual(mosaicos(b"no es una imagen", 700), [])


class OcrPorTamano(PlanOcrPort):
    """OCR de mentira: la pagina entera no lee nada; en un mosaico devuelve
    `por_mosaico(alto_del_mosaico, n)` (n = indice del mosaico en el nombre)."""

    def __init__(self, por_mosaico, falla_en_mosaicos=False):
        self._por_mosaico = por_mosaico
        self._falla = falla_en_mosaicos
        self.llamadas = []

    def read(self, image_bytes, filename="plano.jpg"):
        import cv2
        import numpy as np

        self.llamadas.append(filename)
        if "_m" not in filename:
            return []
        if self._falla:
            raise PlanOcrUnavailableException("El servicio OCR no respondió a tiempo.")
        alto = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), 1).shape[0]
        return self._por_mosaico(alto, int(filename.rsplit("_m", 1)[1].split(".")[0]))


class DeteccionPorMosaicosTest(unittest.TestCase):
    def setUp(self):
        import cv2
        import numpy as np

        self.repo = _new_repo()
        ok, jpg = cv2.imencode(".jpg", np.full((3000, 900, 3), 255, np.uint8))
        AddPlanPagesUseCase(self.repo).execute("res-1", [(jpg.tobytes(), "image/jpeg", [])], "app", USER)

    def _detectar(self, ocr):
        return DetectPlanPagePlantaUseCase(self.repo, ocr).execute("res-1", 1)

    def test_titulo_que_solo_se_lee_en_un_mosaico(self):
        # Mosaicos de 1400 de alto en y = 0, 1120, 2240: el titulo cae en el segundo.
        ocr = OcrPorTamano(
            lambda alto, n: [TitleBlock("PLANTA BAJA", 10, 20, 500, 120)] if (alto == 1400 and n == 1) else []
        )
        page = self._detectar(ocr)
        self.assertEqual(page.plantas, ["PLANTA BAJA"])
        self.assertEqual(page.planta_status, PlantaStatus.DETECTADA)
        # Se leyo en mosaicos de 1400 y, al detectarse ahi, no se paso a los de 700.
        self.assertEqual(ocr.llamadas, ["plano_1.jpg", "plano_1_m0.jpg", "plano_1_m1.jpg", "plano_1_m2.jpg"])

    def test_coordenadas_del_mosaico_se_llevan_a_la_pagina(self):
        from unittest import mock

        from app.domains.resolutions.application.use_cases import detect_plan_page_planta_use_case as uc

        vistos = []

        def espia(bloques):
            vistos.append(list(bloques))
            return detect_plantas(bloques)

        ocr = OcrPorTamano(
            lambda alto, n: [TitleBlock("PLANTA BAJA", 10, 20, 500, 120)] if (alto == 1400 and n == 1) else []
        )
        with mock.patch.object(uc, "detect_plantas", espia):
            self._detectar(ocr)
        final = vistos[-1]
        self.assertEqual([(b.text, b.x0, b.y0, b.x1, b.y1) for b in final], [("PLANTA BAJA", 10, 1140, 500, 1240)])

    def test_baja_a_mosaicos_mas_chicos_si_con_los_grandes_no_basta(self):
        ocr = OcrPorTamano(
            lambda alto, n: [TitleBlock("PLANTA 1° PISO", 0, 0, 400, 60)] if (alto <= 700 and n == 0) else []
        )
        page = self._detectar(ocr)
        self.assertEqual(page.plantas, _pisos(1))
        # Pagina + 3 mosaicos de 1400 (sin titulo) + mosaicos de 700.
        self.assertGreater(len(ocr.llamadas), 4)

    def test_sin_titulo_en_ningun_mosaico(self):
        page = self._detectar(OcrPorTamano(lambda alto, n: [TitleBlock("COCINA", 0, 0, 80, 20)]))
        self.assertEqual(page.plantas, [])
        self.assertEqual(page.planta_status, PlantaStatus.SIN_TITULO)

    def test_ocr_que_falla_en_los_mosaicos_deja_sin_titulo(self):
        page = self._detectar(OcrPorTamano(lambda alto, n: [], falla_en_mosaicos=True))
        self.assertEqual(page.planta_status, PlantaStatus.SIN_TITULO)
        self.assertEqual(page.plantas, [])


class TitulosDeLosFormatos2y3Test(unittest.TestCase):
    """Lecturas reales del OCR sobre los planos del formato 2 (titulo al pie, en
    letra de dibujante) y del formato 3 (titulo grande, terraza sin 'PLANTA')."""

    def test_titulos_leidos_por_el_ocr_real(self):
        casos = {
            ".PLANTABAJA...": ["PLANTA BAJA"],
            "...PLANTA1°PISO...": _pisos(1),
            "...PLANTA2°PISO..": _pisos(2),
            ".PLANTA3PISO.": _pisos(3),
            "PLANTA4PISO": _pisos(4),
            ".PLANTA5PISO..": _pisos(5),
            "..PLANTA 6PISO": _pisos(6),
            "PLANTA 6PIS": _pisos(6),  # el OCR corta la O final
            "TERRAZA": ["PLANTA TERRAZA"],
            "PLANTA TERRAZA": ["PLANTA TERRAZA"],
            "PLANTA11 PISO": _pisos(11),
            "PLANTA 7° PISO": _pisos(7),
        }
        for texto, plantas in casos.items():
            with self.subTest(texto):
                self.assertEqual(plantas_de_titulo(texto), plantas)

    def test_cubierta_no_es_una_planta(self):
        self.assertIsNone(plantas_de_titulo("PLANO DE CUBIERTA BLOQUE II"))
        self.assertIsNone(plantas_de_titulo("CUBIERTA CALAMINA SOBRE ESTRUCTURA METALICA"))

    def test_trozos_de_titulo_cortado(self):
        from app.domains.resolutions.domain.plan_title import parece_trozo_de_titulo

        for texto in ("PLANTA 6", "PLANTA3F", "6°PIS0", "PLANT"):
            with self.subTest(texto):
                self.assertTrue(parece_trozo_de_titulo(texto))
        # Un titulo completo no es un trozo, ni lo es un rotulo cualquiera.
        for texto in ("PLANTA BAJA", "PLANTA 6PISO", "COCINA", "ESC: 1:100"):
            with self.subTest(texto):
                self.assertFalse(parece_trozo_de_titulo(texto))

    def test_terraza_es_una_planta_valida(self):
        from app.domains.resolutions.domain.plantas import PLANTAS_RESUMEN

        self.assertIn("PLANTA TERRAZA", PLANTAS_RESUMEN)


class RecortesDeTituloTest(unittest.TestCase):
    def _jpg(self, ancho, alto):
        import cv2
        import numpy as np

        ok, jpg = cv2.imencode(".jpg", np.full((alto, ancho, 3), 255, np.uint8))
        return jpg.tobytes()

    def test_ventana_alrededor_del_trozo_con_su_posicion(self):
        from app.domains.resolutions.domain.plan_tiles import recortes_de_titulo

        recortes = recortes_de_titulo(self._jpg(3000, 3000), [(1000, 2500, 1200, 2540)])
        self.assertEqual(len(recortes), 1)
        _, x0, y0 = recortes[0]
        self.assertLessEqual(x0, 1000)
        self.assertLessEqual(y0, 2500)

    def test_ventanas_que_se_pisan_se_funden(self):
        from app.domains.resolutions.domain.plan_tiles import recortes_de_titulo

        anclas = [(1000, 2500, 1200, 2540), (1300, 2505, 1500, 2545)]
        self.assertEqual(len(recortes_de_titulo(self._jpg(3000, 3000), anclas)), 1)

    def test_tope_de_recortes_e_imagen_ilegible(self):
        from app.domains.resolutions.domain.plan_tiles import MAX_RECORTES, recortes_de_titulo

        lejanas = [(100, 100 + 400 * i, 200, 140 + 400 * i) for i in range(MAX_RECORTES + 3)]
        self.assertLessEqual(len(recortes_de_titulo(self._jpg(3000, 5000), lejanas)), MAX_RECORTES)
        self.assertEqual(recortes_de_titulo(b"no es una imagen", [(0, 0, 10, 10)]), [])


class OcrTituloPartidoEnMosaico(PlanOcrPort):
    """OCR de mentira: la pagina y los mosaicos solo leen medio titulo ('PLANTA'
    y '6PISO' por separado, lejos entre si); el recorte alrededor del trozo lo
    lee entero."""

    def __init__(self):
        self.llamadas = []

    def read(self, image_bytes, filename="plano.jpg"):
        self.llamadas.append(filename)
        if "_r" in filename:
            return [TitleBlock("PLANTA 6PISO", 0, 0, 600, 80)]
        if "_m" in filename and filename.endswith("_m1.jpg"):
            return [TitleBlock("PLANTA 6", 10, 20, 300, 100)]
        return []


class ReleerTrozosDeTituloTest(unittest.TestCase):
    def test_titulo_cortado_en_el_borde_se_relee_en_un_recorte(self):
        import cv2
        import numpy as np

        repo = _new_repo()
        ok, jpg = cv2.imencode(".jpg", np.full((3000, 900, 3), 255, np.uint8))
        AddPlanPagesUseCase(repo).execute("res-1", [(jpg.tobytes(), "image/jpeg", [])], "app", USER)
        ocr = OcrTituloPartidoEnMosaico()
        page = DetectPlanPagePlantaUseCase(repo, ocr).execute("res-1", 1)
        self.assertEqual(page.plantas, _pisos(6))
        self.assertEqual(page.planta_status, PlantaStatus.DETECTADA)
        self.assertTrue(any("_r" in f for f in ocr.llamadas))


if __name__ == "__main__":
    unittest.main()
