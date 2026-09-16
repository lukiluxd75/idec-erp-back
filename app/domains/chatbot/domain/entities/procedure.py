from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Requirement:
    id: Optional[str]
    description: str
    is_mandatory: bool = True
    display_order: int = 0
    detail: Optional[str] = None
    where_to_obtain: Optional[str] = None
    validity: Optional[str] = None
    estimated_cost: Optional[str] = None


@dataclass
class Step:
    id: Optional[str]
    step_number: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    estimated_duration: Optional[str] = None
    note: Optional[str] = None


@dataclass
class ProcedureException:
    id: Optional[str]
    case_name: str
    description: str
    additional_requirements: Optional[str] = None
    note: Optional[str] = None


@dataclass
class Faq:
    id: Optional[str]
    question: str
    answer: str
    category: str = "general"


@dataclass
class Procedure:
    """A municipal `trámite`. `search_description` and the alias list exist purely
    to give the retrieval step more text to embed than the name alone (see
    domain/services/similarity.py) — they are not shown to the citizen verbatim."""

    id: Optional[str]
    code: str
    name: str
    description: Optional[str] = None
    search_description: Optional[str] = None
    cost_note: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    min_days: Optional[int] = None
    max_days: Optional[int] = None
    legal_basis: Optional[str] = None
    category: Optional[str] = None
    qr_images: List[str] = field(default_factory=list)
    is_active: bool = True
    aliases: List[str] = field(default_factory=list)
    requirements: List[Requirement] = field(default_factory=list)
    steps: List[Step] = field(default_factory=list)
    exceptions: List[ProcedureException] = field(default_factory=list)
    faqs: List[Faq] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class InstitutionalContext:
    """General GAMC info (contact numbers, schedule) injected into every chat
    prompt regardless of which procedure was matched — see
    domain/services/prompt_builder.py."""

    id: Optional[str]
    code: str
    category: str
    title: str
    content: str
