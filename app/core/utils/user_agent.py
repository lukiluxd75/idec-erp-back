import re

_MOBILE_RE = re.compile(r"Mobi|Android|iPhone|iPad|iPod", re.IGNORECASE)


def is_mobile_user_agent(user_agent: str) -> bool:
    """Heuristic device classification from the WebSocket handshake's User-Agent
    header — used to show a "phone connected" indicator (see
    CapturesConnectionManager / ResolutionsConnectionManager). Not meant to be
    exact, only good enough to tell a phone browser from a desktop one."""
    return bool(_MOBILE_RE.search(user_agent or ""))
