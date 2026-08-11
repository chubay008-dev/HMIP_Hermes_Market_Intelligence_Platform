"""Unit tests for EventBus, conforming to 05_Interface_Contract.md
section 4.5's dict-based `EventBus` protocol."""

from __future__ import annotations

from typing import Any

import pytest

from core.event_bus import EventBus
from core.exceptions import EventDeliveryError


def test_publish_with_no_subscribers_does_nothing() -> None:
    bus = EventBus()
    bus.publish({"event_type": "nobody_listening"})  # must not raise


def test_publish_without_event_type_raises() -> None:
    bus = EventBus()

    with pytest.raises(EventDeliveryError):
        bus.publish({"task_id": "collect"})


def test_subscribe_and_publish_calls_handler() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []
    bus.subscribe("task_completed", received.append)

    bus.publish({"event_type": "task_completed", "task_id": "collect"})

    assert len(received) == 1
    assert received[0]["task_id"] == "collect"


def test_multiple_handlers_called_in_subscription_order() -> None:
    bus = EventBus()
    order: list[str] = []
    bus.subscribe("evt", lambda e: order.append("first"))
    bus.subscribe("evt", lambda e: order.append("second"))

    bus.publish({"event_type": "evt"})

    assert order == ["first", "second"]


def test_unsubscribe_stops_further_delivery() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    def handler(event: dict[str, Any]) -> None:
        received.append(event)

    bus.subscribe("evt", handler)
    bus.unsubscribe("evt", handler)
    bus.publish({"event_type": "evt"})

    assert received == []


def test_handler_exception_is_collected_and_raised_after_all_handlers_run() -> None:
    bus = EventBus()
    called: list[str] = []

    def failing_handler(event: dict[str, Any]) -> None:
        called.append("failing")
        raise RuntimeError("boom")

    def healthy_handler(event: dict[str, Any]) -> None:
        called.append("healthy")

    bus.subscribe("evt", failing_handler)
    bus.subscribe("evt", healthy_handler)

    with pytest.raises(EventDeliveryError) as exc_info:
        bus.publish({"event_type": "evt"})

    assert called == ["failing", "healthy"]
    assert len(exc_info.value.errors) == 1
