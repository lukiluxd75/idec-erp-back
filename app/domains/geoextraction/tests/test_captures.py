import unittest
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.connection import Base
from app.domains.geoextraction.application.use_cases.create_capture_use_case import (
    CreateCaptureUseCase,
)
from app.domains.geoextraction.application.use_cases.discard_capture_use_case import (
    DiscardCaptureUseCase,
)
from app.domains.geoextraction.application.use_cases.list_pending_captures_use_case import (
    ListPendingCapturesUseCase,
)
from app.domains.geoextraction.application.use_cases.get_capture_image_use_case import (
    GetCaptureImageUseCase,
)
from app.domains.geoextraction.domain.exceptions import (
    InvalidCaptureException,
    CaptureNotFoundException,
)
from app.domains.geoextraction.infrastructure.models import CaptureModel  # noqa: F401 (registers table on Base)
from app.domains.geoextraction.infrastructure.sql_capture_store import (
    MAX_CAPTURES_PER_USER,
    SqlCaptureStore,
)


def _new_store():
    """SqlCaptureStore on in-memory SQLite: same code that runs against Postgres
    in production (the store uses nothing dialect-specific), without depending on
    a real database to run tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=[CaptureModel.__table__])
    db = sessionmaker(bind=engine)()
    return SqlCaptureStore(db=db)


class TestCreateCaptureUseCase(unittest.TestCase):
    def setUp(self):
        self.store = _new_store()
        self.use_case = CreateCaptureUseCase(store=self.store)

    def test_rejects_empty_content(self):
        with self.assertRaises(InvalidCaptureException):
            self.use_case.execute(content=b"", mime="image/jpeg", user_sub="user-a")

    def test_rejects_unsupported_mime(self):
        with self.assertRaises(InvalidCaptureException):
            self.use_case.execute(content=b"foto", mime="application/pdf", user_sub="user-a")

    def test_saves_valid_capture(self):
        capture = self.use_case.execute(content=b"foto", mime="image/jpeg", user_sub="user-a")
        self.assertIsNotNone(capture.id_captura)
        self.assertEqual(capture.mime, "image/jpeg")


class TestIsolationByUser(unittest.TestCase):
    """Nobody can list or download another user's captures — the store filters by
    user_sub on every method (see CaptureStorePort). Especially important now that
    the store is shared across N backend workers via Postgres, not isolated per
    process as before."""

    def setUp(self):
        self.store = _new_store()
        self.create = CreateCaptureUseCase(store=self.store)
        self.list_pending = ListPendingCapturesUseCase(store=self.store)
        self.get_image = GetCaptureImageUseCase(store=self.store)
        self.discard = DiscardCaptureUseCase(store=self.store)

    def test_empty_list_for_other_user(self):
        self.create.execute(content=b"foto", mime="image/jpeg", user_sub="user-a")
        self.assertEqual(self.list_pending.execute("user-b"), [])

    def test_cannot_download_other_user_capture(self):
        capture = self.create.execute(content=b"foto", mime="image/jpeg", user_sub="user-a")
        with self.assertRaises(CaptureNotFoundException):
            self.get_image.execute(capture.id_captura, user_sub="user-b")

    def test_cannot_discard_other_user_capture(self):
        capture = self.create.execute(content=b"foto", mime="image/jpeg", user_sub="user-a")
        with self.assertRaises(CaptureNotFoundException):
            self.discard.execute(capture.id_captura, user_sub="user-b")
        # Still there for the real owner.
        self.assertEqual(len(self.list_pending.execute("user-a")), 1)

    def test_newest_first_order(self):
        c1 = self.create.execute(content=b"foto1", mime="image/jpeg", user_sub="user-a")
        c2 = self.create.execute(content=b"foto2", mime="image/jpeg", user_sub="user-a")
        ids = [c.id_captura for c in self.list_pending.execute("user-a")]
        self.assertEqual(ids, [c2.id_captura, c1.id_captura])

    def test_bytes_roundtrip_intact(self):
        capture = self.create.execute(content=b"contenido-binario", mime="image/png", user_sub="user-a")
        content, mime = self.get_image.execute(capture.id_captura, user_sub="user-a")
        self.assertEqual(content, b"contenido-binario")
        self.assertEqual(mime, "image/png")


class TestPerUserCap(unittest.TestCase):
    def test_discards_oldest_when_exceeding_cap(self):
        store = _new_store()
        create = CreateCaptureUseCase(store=store)
        list_pending = ListPendingCapturesUseCase(store=store)

        first = create.execute(content=b"foto0", mime="image/jpeg", user_sub="user-a")
        for i in range(1, MAX_CAPTURES_PER_USER + 2):
            create.execute(content=f"foto{i}".encode(), mime="image/jpeg", user_sub="user-a")

        pending = list_pending.execute("user-a")
        self.assertEqual(len(pending), MAX_CAPTURES_PER_USER)
        self.assertNotIn(first.id_captura, [c.id_captura for c in pending])


class TestTTL(unittest.TestCase):
    def test_purges_expired_captures(self):
        store = _new_store()
        create = CreateCaptureUseCase(store=store)
        list_pending = ListPendingCapturesUseCase(store=store)

        capture = create.execute(content=b"foto", mime="image/jpeg", user_sub="user-a")
        self.assertEqual(len(list_pending.execute("user-a")), 1)

        # Simulate 31 minutes elapsed by rewinding fecha_creacion on the row,
        # instead of mocking datetime.now() globally (simpler and less brittle).
        row = store._db.query(CaptureModel).filter_by(id_captura=capture.id_captura).first()
        row.fecha_creacion -= timedelta(minutes=31)
        store._db.commit()

        self.assertEqual(list_pending.execute("user-a"), [])


class TestDiscardCaptureUseCase(unittest.TestCase):
    def test_fails_if_missing(self):
        store = _new_store()
        use_case = DiscardCaptureUseCase(store=store)
        with self.assertRaises(CaptureNotFoundException):
            use_case.execute("no-existe", user_sub="user-a")


if __name__ == "__main__":
    unittest.main()
