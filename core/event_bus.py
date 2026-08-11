"""EventBus: synchronous in-memory publish/subscribe bus.

Contract locked by 05_Interface_Contract.md section 4.5:
`publish(event: dict)`, `subscribe(event_type, handler)`,
`unsubscribe(event_type, handler)`. The event dict carries its own
routing key under an "event_type" entry (there is no separate
event-type parameter to `publish()`); this implementation reads that
key to determine which subscribers to notify.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from core.exceptions import EventDeliveryError

EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    """Thread-safe synchronous pub/sub bus conforming to
    05_Interface_Contract.md section 4.5's `EventBus` protocol.

    `publish` calls all handlers subscribed to the event's
    "event_type" synchronously, in subscription order. A handler
    exception does not stop delivery to the remaining handlers; all
    exceptions are collected and raised together afterward as
    `EventDeliveryError`, so a broken subscriber can never silently
    swallow delivery to others.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._handlers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(self, event: dict[str, Any]) -> None:
        event_type = event.get("event_type")
        if not isinstance(event_type, str) or not event_type:
            raise EventDeliveryError(
                "event dict must contain a non-empty string 'event_type' key",
                code="EVENT_MISSING_TYPE",
                errors=[],
            )

        with self._lock:
            handlers = list(self._handlers.get(event_type, []))

        errors: list[BaseException] = []
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 - collected below, not swallowed
                errors.append(exc)

        if errors:
            raise EventDeliveryError(
                f"{len(errors)} handler(s) failed for event '{event_type}'",
                code="EVENT_HANDLER_FAILED",
                errors=errors,
            )
