"""
Ciclo de vida de "Celular conectado" ligado a la sesión de la app móvil:
inicia sesión -> conectado todo el rato -> cierra sesión -> desconectado.

El test que explica el bug original es
`test_native_app_login_is_detected`: la detección anterior solo reconocía
*navegadores* de celular, así que una app nativa (`okhttp/4.12.0`) subía la foto
correctamente y jamás encendía el indicador.
"""
import unittest
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.presence import CHANNEL_FOLDER_ANALYSIS, CHANNEL_SESSION
from app.core.presence.models import DevicePresenceModel
from app.core.presence.store import SESSION_TTL, SqlPresenceStore
from app.domains.security.presentation.endpoints.presence import record_session_from_request

USER = "arq-1"

OKHTTP_UA = "okhttp/4.12.0"
FLUTTER_UA = "Dart/3.3 (dart:io)"
DIGID_UA = "IDEC-DigID-Android-App (Mobi; Android)"
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _request(user_agent):
    headers = {} if user_agent is None else {"user-agent": user_agent}
    return SimpleNamespace(headers=headers)


class PresenceSessionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        DevicePresenceModel.__table__.create(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.store = SqlPresenceStore(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _login(self, user_agent):
        record_session_from_request(_request(user_agent), self.db, USER)

    def _connected(self):
        """Lo que responde el endpoint del analizador de carpetas."""
        return self.store.is_mobile_present_any(USER, (CHANNEL_SESSION, CHANNEL_FOLDER_ANALYSIS))

    # --- el bug que reportaste ------------------------------------------------

    def test_native_app_login_is_detected(self):
        """okhttp: lo que manda de verdad una app Android nativa."""
        self._login(OKHTTP_UA)
        self.assertTrue(self._connected())

    def test_flutter_app_login_is_detected(self):
        self._login(FLUTTER_UA)
        self.assertTrue(self._connected())

    def test_digid_app_login_is_detected(self):
        self._login(DIGID_UA)
        self.assertTrue(self._connected())

    def test_desktop_login_does_not_connect_a_phone(self):
        """El arquitecto entrando al ERP desde su PC no es un celular."""
        self._login(DESKTOP_UA)
        self.assertFalse(self._connected())
        self.assertEqual(self.db.query(DevicePresenceModel).count(), 0)

    # --- el ciclo que pediste -------------------------------------------------

    def test_full_cycle_login_stays_connected_logout_disconnects(self):
        self.assertFalse(self._connected())

        # inicia sesion en la app
        self._login(OKHTTP_UA)
        self.assertTrue(self._connected())

        # sigue conectado sin hacer nada mas (no hace falta subir fotos)
        self.assertTrue(self._connected())
        self.assertTrue(self._connected())

        # cierra sesion en la app: lo mismo que hace DELETE /api/presence/session
        self.store.close_all_mobile(USER)
        self.assertFalse(self._connected())

    def test_logout_clears_even_with_a_different_user_agent(self):
        """La app no tiene por que repetir el mismo User-Agent en el logout."""
        self._login(OKHTTP_UA)
        self._login(FLUTTER_UA)  # p.ej. tras actualizar la app
        self.assertEqual(self.db.query(DevicePresenceModel).count(), 2)

        self.store.close_all_mobile(USER)
        self.assertFalse(self._connected())
        self.assertEqual(self.db.query(DevicePresenceModel).count(), 0)

    def test_logout_does_not_touch_another_account(self):
        self._login(OKHTTP_UA)
        record_session_from_request(_request(OKHTTP_UA), self.db, "otro-arq")

        self.store.close_all_mobile(USER)
        self.assertFalse(self._connected())
        self.assertTrue(
            self.store.is_mobile_present("otro-arq", CHANNEL_SESSION),
            "cerrar sesion en un celular no puede desconectar al de otro usuario",
        )

    def test_logout_also_clears_a_recent_upload(self):
        """Sin esto el indicador seguiria encendido hasta 3 minutos despues de
        cerrar sesion, por la presencia de "actividad reciente"."""
        self._login(OKHTTP_UA)
        self.store.touch_activity(USER, CHANNEL_FOLDER_ANALYSIS, "ua-x")
        self.assertTrue(self._connected())

        self.store.close_all_mobile(USER)
        self.assertFalse(self._connected())

    def test_logout_leaves_desktop_rows_alone(self):
        """Solo se desconectan celulares: un socket del escritorio no enciende
        nada, pero su fila es contabilidad de otra cosa."""
        self.store.enter(USER, "resolutions", "ws-pc", is_mobile=False)
        self._login(OKHTTP_UA)

        self.store.close_all_mobile(USER)
        self.assertEqual(self.db.query(DevicePresenceModel).count(), 1)
        self.assertFalse(self.db.query(DevicePresenceModel).one().is_mobile)

    # --- duracion -------------------------------------------------------------

    def test_session_lasts_far_longer_than_an_upload(self):
        """Es lo que hace que aparezca "todo el rato" y no solo al subir."""
        from app.core.presence.store import ACTIVITY_TTL, _now

        self._login(OKHTTP_UA)
        row = self.db.query(DevicePresenceModel).one()
        self.assertAlmostEqual(
            (row.expires_at - _now()).total_seconds(), SESSION_TTL.total_seconds(), delta=5
        )
        self.assertGreater(SESSION_TTL, ACTIVITY_TTL)

    def test_an_abandoned_session_expires(self):
        """Si la app se mata sin cerrar sesion, el TTL la retira: el indicador
        no se queda encendido para siempre."""
        self._login(OKHTTP_UA)
        row = self.db.query(DevicePresenceModel).one()
        row.expires_at = row.expires_at - SESSION_TTL - timedelta(seconds=1)
        self.db.commit()
        self.assertFalse(self._connected())

    def test_refresh_renews_the_session(self):
        """El refresh del token es el latido natural de la app."""
        from app.core.presence.store import _now

        self._login(OKHTTP_UA)
        row = self.db.query(DevicePresenceModel).one()
        row.expires_at = _now() + timedelta(seconds=30)
        self.db.commit()

        self._login(OKHTTP_UA)  # lo que hace /refresh
        row = self.db.query(DevicePresenceModel).one()
        self.assertGreater((row.expires_at - _now()).total_seconds(), 60)

    # --- resiliencia ----------------------------------------------------------

    def test_a_broken_store_does_not_break_the_login(self):
        """Esto cuelga del login: si lanzara, nadie podria entrar al ERP."""
        self.db.close()
        self._login(OKHTTP_UA)  # no debe lanzar

    def test_session_is_visible_from_every_worker(self):
        self._login(OKHTTP_UA)
        workers = [SqlPresenceStore(self.Session()) for _ in range(4)]
        try:
            seen = [w.is_mobile_present(USER, CHANNEL_SESSION) for w in workers]
            self.assertEqual(seen, [True, True, True, True])
        finally:
            for w in workers:
                w._db.close()


if __name__ == "__main__":
    unittest.main()
