"""rate_limit_state.py - State management for notification rate limiting."""

from __future__ import annotations
from typing import Dict, Any

class RateLimitState:
    def __init__(self) -> None:
        self._state: Dict[str, Dict[str, Any]] = {}
        self._state_db_path: str | None = None
    
    def get_state(self) -> Dict[str, Dict[str, Any]]:
        return self._state
    
    def set_state_db_path(self, path: str | None) -> None:
        self._state_db_path = path
    
    def get_state_db_path(self) -> str | None:
        return self._state_db_path
