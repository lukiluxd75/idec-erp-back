from functools import lru_cache
from typing import Optional

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db


@lru_cache()
def get_cadastralviewer_repository() -> Optional[object]:
    return None


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db
