import unittest
from datetime import timedelta

from app.domains.geoextraccion.application.use_cases.crear_captura_use_case import (
    CrearCapturaUseCase,
)
from app.domains.geoextraccion.application.use_cases.descartar_captura_use_case import (
    DescartarCapturaUseCase,
)
from app.domains.geoextraccion.application.use_cases.listar_capturas_pendientes_use_case import (
    ListarCapturasPendientesUseCase,
)
from app.domains.geoextraccion.application.use_cases.obtener_imagen_captura_use_case import (
    ObtenerImagenCapturaUseCase,
)
from app.domains.geoextraccion.domain.exceptions import (
    CapturaInvalidaException,
    CapturaNoEncontradaException,
)
from app.domains.geoextraccion.infrastructure.memoria_captura_store import (
    MAX_CAPTURAS_POR_USUARIO,
    MemoriaCapturaStore,
)


class TestCrearCapturaUseCase(unittest.TestCase):
    def setUp(self):
        self.store = MemoriaCapturaStore()
        self.use_case = CrearCapturaUseCase(store=self.store)

    def test_rechaza_contenido_vacio(self):
        with self.assertRaises(CapturaInvalidaException):
            self.use_case.execute(contenido=b"", mime="image/jpeg", user_sub="user-a")

    def test_rechaza_mime_no_soportado(self):
        with self.assertRaises(CapturaInvalidaException):
            self.use_case.execute(contenido=b"foto", mime="application/pdf", user_sub="user-a")

    def test_guarda_una_captura_valida(self):
        captura = self.use_case.execute(contenido=b"foto", mime="image/jpeg", user_sub="user-a")
        self.assertIsNotNone(captura.id_captura)
        self.assertEqual(captura.mime, "image/jpeg")


class TestAislamientoPorUsuario(unittest.TestCase):
    """Nadie puede listar ni descargar las capturas de otro usuario — el store se
    indexa por user_sub en cada método (ver CapturaStorePort)."""

    def setUp(self):
        self.store = MemoriaCapturaStore()
        self.crear = CrearCapturaUseCase(store=self.store)
        self.listar = ListarCapturasPendientesUseCase(store=self.store)
        self.obtener_imagen = ObtenerImagenCapturaUseCase(store=self.store)
        self.descartar = DescartarCapturaUseCase(store=self.store)

    def test_lista_vacia_para_otro_usuario(self):
        self.crear.execute(contenido=b"foto", mime="image/jpeg", user_sub="user-a")
        self.assertEqual(self.listar.execute("user-b"), [])

    def test_no_se_puede_descargar_captura_de_otro_usuario(self):
        captura = self.crear.execute(contenido=b"foto", mime="image/jpeg", user_sub="user-a")
        with self.assertRaises(CapturaNoEncontradaException):
            self.obtener_imagen.execute(captura.id_captura, user_sub="user-b")

    def test_no_se_puede_descartar_captura_de_otro_usuario(self):
        captura = self.crear.execute(contenido=b"foto", mime="image/jpeg", user_sub="user-a")
        with self.assertRaises(CapturaNoEncontradaException):
            self.descartar.execute(captura.id_captura, user_sub="user-b")
        # Sigue estando ahí para su dueño real.
        self.assertEqual(len(self.listar.execute("user-a")), 1)

    def test_orden_mas_nuevas_primero(self):
        c1 = self.crear.execute(contenido=b"foto1", mime="image/jpeg", user_sub="user-a")
        c2 = self.crear.execute(contenido=b"foto2", mime="image/jpeg", user_sub="user-a")
        ids = [c.id_captura for c in self.listar.execute("user-a")]
        self.assertEqual(ids, [c2.id_captura, c1.id_captura])


class TestTopePorUsuario(unittest.TestCase):
    def test_descarta_la_mas_vieja_al_superar_el_tope(self):
        store = MemoriaCapturaStore()
        crear = CrearCapturaUseCase(store=store)
        listar = ListarCapturasPendientesUseCase(store=store)

        primera = crear.execute(contenido=b"foto0", mime="image/jpeg", user_sub="user-a")
        for i in range(1, MAX_CAPTURAS_POR_USUARIO + 2):
            crear.execute(contenido=f"foto{i}".encode(), mime="image/jpeg", user_sub="user-a")

        pendientes = listar.execute("user-a")
        self.assertEqual(len(pendientes), MAX_CAPTURAS_POR_USUARIO)
        self.assertNotIn(primera.id_captura, [c.id_captura for c in pendientes])


class TestTTL(unittest.TestCase):
    def test_purga_capturas_vencidas(self):
        store = MemoriaCapturaStore()
        crear = CrearCapturaUseCase(store=store)
        listar = ListarCapturasPendientesUseCase(store=store)

        captura = crear.execute(contenido=b"foto", mime="image/jpeg", user_sub="user-a")
        self.assertEqual(len(listar.execute("user-a")), 1)

        # Simula que pasaron 31 minutos retrocediendo la fecha_creacion guardada,
        # en vez de mockear datetime.now() global (más simple y menos frágil).
        almacenada = store._por_usuario["user-a"][captura.id_captura]
        almacenada.fecha_creacion -= timedelta(minutes=31)

        self.assertEqual(listar.execute("user-a"), [])


class TestDescartarCapturaUseCase(unittest.TestCase):
    def test_falla_si_no_existe(self):
        store = MemoriaCapturaStore()
        use_case = DescartarCapturaUseCase(store=store)
        with self.assertRaises(CapturaNoEncontradaException):
            use_case.execute("no-existe", user_sub="user-a")


if __name__ == "__main__":
    unittest.main()
