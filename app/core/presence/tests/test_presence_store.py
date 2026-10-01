"""
Tests for the shared presence store.

The one that matters is `test_presence_is_visible_from_every_worker`: it is the
regression test for the flickering badge. The old per-process registry answered
True from one worker out of four and False from the other three, so a poll every
3s made the indicator alternate forever.
"""
import unittest
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.connection import Base
from app.core.presence import models as presence_models  # noqa: F401  (registers the table)
from app.core.presence.store import (
    ACTIVITY_TTL,
    SOCKET_TTL,
    SqlPresenceStore,
    device_id_for_request,
)
from app.core.presence.models import DevicePresenceModel

CHANNEL = "folder-analysis"
USER = "user-abc"


class PresenceStoreTests(unittest.TestCase):
    def setUp(self):
        # One shared in-memory DB, several sessions on top of it: that is how a
        # multi-worker deployment looks to this code -- separate processes, one
        # Postgres underneath.
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        DevicePresenceModel.__table__.create(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.store = SqlPresenceStore(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _expire_in(self, delta: timedelta):
        """Move the row's expiry to now + `delta` (negative = already expired)."""
        from app.core.presence.store import _now

        row = self.db.query(DevicePresenceModel).one()
        row.expires_at = _now() + delta
        self.db.commit()

    # --- the regression test --------------------------------------------------

    def test_presence_is_visible_from_every_worker(self):
        """A phone registered through one session is seen by all the others."""
        self.store.enter(USER, CHANNEL, "ws-1", is_mobile=True)

        workers = [SqlPresenceStore(self.Session()) for _ in range(4)]
        try:
            seen = [w.is_mobile_present(USER, CHANNEL) for w in workers]
            self.assertEqual(seen, [True, True, True, True])
        finally:
            for w in workers:
                w._db.close()

    # --- basics ---------------------------------------------------------------

    def test_absent_when_nothing_registered(self):
        self.assertFalse(self.store.is_mobile_present(USER, CHANNEL))

    def test_desktop_connection_does_not_count(self):
        self.store.enter(USER, CHANNEL, "ws-desktop", is_mobile=False)
        self.assertFalse(self.store.is_mobile_present(USER, CHANNEL))

    def test_leave_clears_presence(self):
        self.store.enter(USER, CHANNEL, "ws-1", is_mobile=True)
        self.assertTrue(self.store.is_mobile_present(USER, CHANNEL))
        self.store.leave(USER, CHANNEL, "ws-1")
        self.assertFalse(self.store.is_mobile_present(USER, CHANNEL))

    def test_presence_is_per_account(self):
        self.store.enter(USER, CHANNEL, "ws-1", is_mobile=True)
        self.assertFalse(self.store.is_mobile_present("otro-usuario", CHANNEL))

    def test_presence_is_per_channel(self):
        self.store.enter(USER, "geoextraction", "ws-1", is_mobile=True)
        self.assertFalse(self.store.is_mobile_present(USER, CHANNEL))

    # --- TTL ------------------------------------------------------------------

    def test_expires_after_ttl(self):
        self.store.enter(USER, CHANNEL, "ws-1", is_mobile=True)
        self._expire_in(-timedelta(seconds=1))
        self.assertFalse(self.store.is_mobile_present(USER, CHANNEL))

    def test_still_present_just_inside_ttl(self):
        self.store.enter(USER, CHANNEL, "ws-1", is_mobile=True)
        self._expire_in(timedelta(seconds=1))
        self.assertTrue(self.store.is_mobile_present(USER, CHANNEL))

    def test_socket_presence_uses_the_short_lifetime(self):
        from app.core.presence.store import _now

        self.store.enter(USER, CHANNEL, "ws-1", is_mobile=True)
        row = self.db.query(DevicePresenceModel).one()
        self.assertAlmostEqual((row.expires_at - _now()).total_seconds(),
                               SOCKET_TTL.total_seconds(), delta=5)

    def test_activity_presence_uses_the_long_lifetime(self):
        from app.core.presence.store import _now

        self.store.touch_activity(USER, CHANNEL, "ua-x")
        row = self.db.query(DevicePresenceModel).one()
        self.assertAlmostEqual((row.expires_at - _now()).total_seconds(),
                               ACTIVITY_TTL.total_seconds(), delta=5)
        # El punto del diseño: la actividad aguanta huecos que un socket no.
        self.assertGreater(ACTIVITY_TTL, SOCKET_TTL)

    def test_heartbeat_revives_an_expiring_device(self):
        """A worker that died mid-socket leaves a row behind; a live heartbeat is
        what keeps a real one from expiring."""
        self.store.enter(USER, CHANNEL, "ws-1", is_mobile=True)
        self._expire_in(-timedelta(seconds=1))
        self.assertFalse(self.store.is_mobile_present(USER, CHANNEL))

        self.store.heartbeat(USER, CHANNEL, "ws-1", is_mobile=True)
        self.assertTrue(self.store.is_mobile_present(USER, CHANNEL))

    def test_heartbeat_does_not_duplicate_the_row(self):
        for _ in range(5):
            self.store.heartbeat(USER, CHANNEL, "ws-1", is_mobile=True)
        self.assertEqual(self.db.query(DevicePresenceModel).count(), 1)

    # --- activity-backed presence (folder analysis) ---------------------------

    def test_activity_marks_presence(self):
        device = device_id_for_request(USER, "IDEC-DigID-Android-App (Mobi; Android)")
        self.store.touch_activity(USER, CHANNEL, device)
        self.assertTrue(self.store.is_mobile_present(USER, CHANNEL))

    def test_repeated_activity_reuses_one_row(self):
        device = device_id_for_request(USER, "IDEC-DigID-Android-App (Mobi; Android)")
        for _ in range(4):
            self.store.touch_activity(USER, CHANNEL, device)
        self.assertEqual(self.db.query(DevicePresenceModel).count(), 1)

    def test_two_phones_stay_separate(self):
        a = device_id_for_request(USER, "IDEC-DigID-Android-App (Mobi; Android 13)")
        b = device_id_for_request(USER, "IDEC-DigID-Android-App (Mobi; Android 14)")
        self.assertNotEqual(a, b)
        self.store.touch_activity(USER, CHANNEL, a)
        self.store.touch_activity(USER, CHANNEL, b)
        self.assertEqual(self.db.query(DevicePresenceModel).count(), 2)

        # One leaving does not take the other's presence with it.
        self.store.leave(USER, CHANNEL, a)
        self.assertTrue(self.store.is_mobile_present(USER, CHANNEL))

    def test_device_id_is_stable_and_bounded(self):
        ua = "IDEC-DigID-Android-App (Mobi; Android)"
        first = device_id_for_request(USER, ua)
        self.assertEqual(first, device_id_for_request(USER, ua))
        # Must fit the column (String(64)).
        self.assertLessEqual(len(first), 64)

    def test_device_id_handles_missing_user_agent(self):
        self.assertTrue(device_id_for_request(USER, None).startswith("ua-"))

    # --- esquema --------------------------------------------------------------

    def test_the_model_matches_what_the_reader_queries(self):
        """El bug que dejo el indicador apagado en produccion: la tabla se creo
        con una version del modelo, el modelo cambio de columna despues, y
        `create_all()` no altera tablas existentes. Cada escritura fallaba con
        UndefinedColumn, el store se la tragaba para no romper la subida de
        fotos, y nada lo delataba.

        Esto no sustituye a `ensure_schema` (que es quien repara una tabla ya
        creada), pero sí fija que las columnas por las que filtra la lectura
        existen de verdad en el modelo.
        """
        columnas = set(DevicePresenceModel.__table__.columns.keys())
        self.assertEqual(
            columnas,
            {"user_sub", "channel", "device_id", "is_mobile", "last_seen_at", "expires_at"},
        )
        # El indice tiene que cubrir la columna por la que se filtra, no otra.
        indice = next(iter(DevicePresenceModel.__table__.indexes))
        self.assertIn("expires_at", [c.name for c in indice.columns])

    def test_a_write_is_really_persisted(self):
        """Una escritura que falla se traga el error a proposito; este test
        comprueba que ademas de no lanzar, la fila queda."""
        self.store.open_session(USER, CHANNEL, "ua-x")
        self.assertEqual(self.db.query(DevicePresenceModel).count(), 1)
        self.assertTrue(self.store.is_mobile_present(USER, CHANNEL))

    # --- resilience -----------------------------------------------------------

    def test_write_failure_does_not_raise(self):
        """Presence is cosmetic: a broken DB must not break the upload that
        carried the heartbeat."""
        self.db.close()  # cualquier escritura falla a partir de aqui
        broken = SqlPresenceStore(self.db)
        broken.heartbeat(USER, CHANNEL, "ws-1", is_mobile=True)  # no debe lanzar


if __name__ == "__main__":
    unittest.main()
