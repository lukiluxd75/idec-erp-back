"""
Presencia de un websocket vivo (geoextraction, resolutions).

El grupo que importa es el de resiliencia: esto corre DENTRO del camino de
conexión del socket (`manager.connect()` emite el broadcast de presencia), así
que una base caída no puede impedir que el arquitecto abra la pantalla. La
primera versión abría la sesión de BD fuera del `try` y la excepción escapaba.
"""
import asyncio
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.presence import socket as socket_mod
from app.core.presence.models import DevicePresenceModel
from app.core.presence.socket import SocketPresence, is_phone_connected
from app.core.presence.store import CHANNEL_GEOEXTRACTION, SqlPresenceStore

USER = "arq-1"


def _boom():
    raise RuntimeError("base de datos inalcanzable")


class SocketPresenceTests(unittest.TestCase):
    def setUp(self):
        # StaticPool: SocketPresence escribe desde otro hilo (asyncio.to_thread),
        # y un SQLite ":memory:" normal da una base DISTINTA por conexion, asi
        # que el hilo de escritura no veria la misma que el de lectura.
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        DevicePresenceModel.__table__.create(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self._original = socket_mod.SessionLocal
        socket_mod.SessionLocal = self.Session

    def tearDown(self):
        socket_mod.SessionLocal = self._original
        self.engine.dispose()

    def _connected(self):
        db = self.Session()
        try:
            return SqlPresenceStore(db).is_phone_connected(USER, CHANNEL_GEOEXTRACTION)
        finally:
            db.close()

    # --- ciclo de vida --------------------------------------------------------

    def test_start_registers_and_stop_releases(self):
        p = SocketPresence(USER, CHANNEL_GEOEXTRACTION, is_mobile=True)
        asyncio.run(p.start())
        self.assertTrue(self._connected())

        asyncio.run(p.stop())
        self.assertFalse(self._connected())

    def test_a_desktop_socket_does_not_light_the_badge(self):
        p = SocketPresence(USER, CHANNEL_GEOEXTRACTION, is_mobile=False)
        asyncio.run(p.start())
        try:
            self.assertFalse(self._connected())
        finally:
            asyncio.run(p.stop())

    def test_each_socket_owns_its_row(self):
        """Dos conexiones de la misma cuenta no se pisan: cerrar una no puede
        desconectar a la otra."""
        a = SocketPresence(USER, CHANNEL_GEOEXTRACTION, is_mobile=True)
        b = SocketPresence(USER, CHANNEL_GEOEXTRACTION, is_mobile=True)
        self.assertNotEqual(a.device_id, b.device_id)

        asyncio.run(a.start())
        asyncio.run(b.start())
        asyncio.run(a.stop())
        try:
            self.assertTrue(self._connected())
        finally:
            asyncio.run(b.stop())

    def test_stop_is_safe_without_start(self):
        asyncio.run(SocketPresence(USER, CHANNEL_GEOEXTRACTION, is_mobile=True).stop())

    # --- resiliencia ----------------------------------------------------------

    def test_start_survives_a_dead_database(self):
        """Si esto lanzara, manager.connect() lanzaria y el websocket no se
        abriria: el arquitecto no podria usar la pantalla porque un indicador
        cosmetico no pudo escribirse."""
        socket_mod.SessionLocal = _boom
        p = SocketPresence(USER, CHANNEL_GEOEXTRACTION, is_mobile=True)
        asyncio.run(p.start())
        asyncio.run(p.stop())

    def test_reading_survives_a_dead_database(self):
        socket_mod.SessionLocal = _boom
        self.assertFalse(is_phone_connected(USER, CHANNEL_GEOEXTRACTION))

    def test_reading_a_dead_database_says_not_connected(self):
        """Ante la duda, apagado: afirmar un celular del que no se sabe nada
        seria peor que no mostrarlo."""
        socket_mod.SessionLocal = _boom
        self.assertIs(is_phone_connected(USER, CHANNEL_GEOEXTRACTION), False)


if __name__ == "__main__":
    unittest.main()
