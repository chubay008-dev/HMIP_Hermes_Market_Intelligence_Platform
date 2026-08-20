"""pi_notifier_state.py - State management for PI notifier."""

from __future__ import annotations
from typing import Dict

class PINotifierState:
    def __init__(self) -> None:
        self._notify_state: Dict[str, float] = {}
        self._sku_notify_state: Dict[str, float] = {}
        self._state_db_path: str | None = None
    
    def get_notify_state(self) -> Dict[str, float]:
        return self._notify_state
    
    def get_sku_notify_state(self) -> Dict[str, float]:
        return self._sku_notify_state
    
    def set_state_db_path(self, path: str | None) -> None:
        self._state_db_path = path
    
    def get_state_db_path(self) -> str | None:
        return self._state_db_path
