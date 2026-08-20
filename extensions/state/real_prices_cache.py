"""real_prices_cache.py - Cache management for real prices."""

from __future__ import annotations
from typing import Dict, Any

class RealPricesCache:
    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}
    
    def get_cache(self) -> Dict[str, Any]:
        return self._cache
    
    def set_cache(self, cache: Dict[str, Any]) -> None:
        self._cache = cache
    
    def clear_cache(self) -> None:
        self._cache = {}
