"""api_state.py - State management for API auto-scan flags."""

from __future__ import annotations

class APIState:
    def __init__(self) -> None:
        self._auto_scan_in_progress = False
        self._auto_pi_collect_in_progress = False
    
    def is_auto_scan_in_progress(self) -> bool:
        return self._auto_scan_in_progress
    
    def set_auto_scan_in_progress(self, in_progress: bool) -> None:
        self._auto_scan_in_progress = in_progress
    
    def is_auto_pi_collect_in_progress(self) -> bool:
        return self._auto_pi_collect_in_progress
    
    def set_auto_pi_collect_in_progress(self, in_progress: bool) -> None:
        self._auto_pi_collect_in_progress = in_progress
