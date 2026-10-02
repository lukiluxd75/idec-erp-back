"""
Tests for this module's "phone connected" indicator.

What matters here is the User-Agent gate: the architect can upload captures from
the desktop too (file picker and drag & drop, see captureUpload.js), and those
uploads must not light up "Celular conectado".
"""
import unittest
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.presence import CHANNEL_FOLDER_ANALYSIS
from app.core.presence.models import DevicePresenceModel
from app.core.presence.store import SqlPresenceStore
from app.domains.folder_analysis.presentation.deps import record_mobile_presence

USER = "user-abc"

DIGID_APP_UA = "IDEC-DigID-Android-App (Mobi; Android)"
ANDROID_CHROME_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
)
IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148"
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _request(user_agent):
    """Minimal stand-in for fastapi.Request: the dependency only reads a header."""
    headers = {} if user_agent is None else {"user-agent": user_agent}
    return SimpleNamespace(headers=headers)


class FolderAnalysisPresenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        DevicePresenceModel.__table__.create(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.store = SqlPresenceStore(self.db)
        self.user = SimpleNamespace(sub=USER)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _record(self, user_agent):
        record_mobile_presence(_request(user_agent), user=self.user, presence=self.store)

    def _connected(self):
        return self.store.is_mobile_present(USER, CHANNEL_FOLDER_ANALYSIS)

    # --- the gate -------------------------------------------------------------

    def test_digid_app_upload_marks_the_phone_connected(self):
        self._record(DIGID_APP_UA)
        self.assertTrue(self._connected())

    def test_android_browser_also_counts(self):
        """The badge means "a phone is sending photos", and the architect may
        use the mobile web app instead of the DigiD app."""
        self._record(ANDROID_CHROME_UA)
        self.assertTrue(self._connected())

    def test_iphone_counts(self):
        self._record(IPHONE_UA)
        self.assertTrue(self._connected())

    def test_desktop_upload_does_not_mark_anything(self):
        """Dragging files from Windows must leave the indicator grey."""
        self._record(DESKTOP_UA)
        self.assertFalse(self._connected())
        self.assertEqual(self.db.query(DevicePresenceModel).count(), 0)

    def test_missing_user_agent_does_not_mark_anything(self):
        self._record(None)
        self.assertFalse(self._connected())

    def test_empty_user_agent_does_not_mark_anything(self):
        self._record("")
        self.assertFalse(self._connected())

    # --- behaviour ------------------------------------------------------------

    def test_presence_is_scoped_to_this_module(self):
        """A phone uploading here must not light the badge of geoextraction."""
        self._record(DIGID_APP_UA)
        self.assertTrue(self._connected())
        self.assertFalse(self.store.is_mobile_present(USER, "geoextraction"))

    def test_desktop_upload_does_not_clear_a_connected_phone(self):
        self._record(DIGID_APP_UA)
        self._record(DESKTOP_UA)
        self.assertTrue(self._connected())

    def test_repeated_uploads_keep_one_row(self):
        for _ in range(5):
            self._record(DIGID_APP_UA)
        self.assertEqual(self.db.query(DevicePresenceModel).count(), 1)

    def test_presence_is_per_account(self):
        self._record(DIGID_APP_UA)
        self.assertFalse(self.store.is_mobile_present("otro-usuario", CHANNEL_FOLDER_ANALYSIS))

    def test_a_broken_presence_store_does_not_break_the_upload(self):
        """The dependency hangs off POST /captures: if it raised, the upload
        would fail and the architect would lose the batch."""
        self.db.close()
        self._record(DIGID_APP_UA)  # no debe lanzar


if __name__ == "__main__":
    unittest.main()
