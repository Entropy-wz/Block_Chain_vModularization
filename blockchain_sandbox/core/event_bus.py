from typing import Any, Callable, Dict, List

from .interfaces import IEventBus


class SimpleEventBus(IEventBus):
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[Any], None]) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def publish(self, event_type: str, payload: Any) -> None:
        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            handler(payload)
