from typing import List, Optional

from pydantic import BaseModel


class ProcedureListItem(BaseModel):
    """Row of the admin catalog table."""
    code: str
    name: str
    description: Optional[str] = None
    cost_note: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    is_active: bool


class ProcedureUpdateRequest(BaseModel):
    """Editable subset from the admin panel -- same fields the ported prototype
    exposed (requirements/steps/etc. are edited only via re-ingestion, not here)."""
    name: str
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    is_active: bool = True


class IngestResponse(BaseModel):
    success: bool = True
    message: str
    code: str
    name: str
    requirements: List[str]
    cost_note: Optional[str] = None


class ReindexResponse(BaseModel):
    reindexed_count: int


class IngestJsonResponse(BaseModel):
    success: bool = True
    message: str
    count: int

