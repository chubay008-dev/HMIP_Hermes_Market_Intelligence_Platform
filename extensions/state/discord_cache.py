"""discord_cache.py - State management for Discord DM channel cache."""

from __future__ import annotations

class DiscordChannelCache:
    def __init__(self) -> None:
        self._dm_channel_cache: str | None = None
    
    def get_dm_channel(self) -> str | None:
        return self._dm_channel_cache
    
    def set_dm_channel(self, channel_id: str | None) -> None:
        self._dm_channel_cache = channel_id
