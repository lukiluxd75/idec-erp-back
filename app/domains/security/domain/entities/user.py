from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass(frozen=True)
class UserProfile:
    """
    Domain entity representing user data and profile
    autenticado a través del proveedor de identidad.
    """
    username: str
    email: str
    roles: List[str] = field(default_factory=list)
    client_id: Optional[str] = None
    sub: Optional[str] = None
    domain: Optional[str] = None
    is_active: bool = True
    claims: Dict[str, Any] = field(default_factory=dict)
