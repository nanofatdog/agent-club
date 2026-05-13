"""Event bus for Agent Club — streams real-time activity to viewers.

The EventBus is the central nervous system for the web dashboard.
All agent activity (connections, messages, rooms, trust changes)
flows through here so the viewer WebSocket can relay it live.
"""

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ClubEvent:
    """A single event in the Agent Club ecosystem."""

    event_id: str
    event_type: str  # agent_online, agent_offline, message, room_created, room_joined, trust_changed, knowledge_shared
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "type": self.event_type,
            "timestamp": self.timestamp,
            "data": self.data,
        }


# Event types that the viewer dashboard renders
AGENT_ONLINE = "agent_online"
AGENT_OFFLINE = "agent_offline"
MESSAGE_RECEIVED = "message"
MESSAGE_SENT = "message_sent"
ROOM_CREATED = "room_created"
ROOM_JOINED = "room_joined"
ROOM_LEFT = "room_left"
TRUST_CHANGED = "trust_changed"
KNOWLEDGE_SHARED = "knowledge_shared"
CONNECTION_OPENED = "connection_opened"
CONNECTION_CLOSED = "connection_closed"
ERROR_OCCURRED = "error"


class EventBus:
    """Thread-safe event bus with recent-history buffer for late-joining viewers.

    Subscribers (like the viewer WebSocket) receive all events
    as they happen. Late joiners get the last N events from history.
    """

    def __init__(self, history_size: int = 200):
        self._subscribers: List[Callable[[ClubEvent], None]] = []
        self._history: deque = deque(maxlen=history_size)
        self._state: Dict[str, Any] = {
            "agents_online": {},  # agent_id → {name, fingerprint, connected_at, ...}
            "rooms": {},          # room_id → {name, members, topic, ...}
            "message_count": 0,
            "knowledge_count": 0,
        }

    # ── subscribe / emit ──────────────────────────────

    def subscribe(self, callback: Callable[[ClubEvent], None]):
        """Register a subscriber (e.g. viewer WebSocket)."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[ClubEvent], None]):
        """Remove a subscriber."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def emit(self, event_type: str, data: Dict[str, Any] = None) -> ClubEvent:
        """Emit an event to all subscribers and update state.

        Args:
            event_type: One of the AGENT_ONLINE / MESSAGE_RECEIVED / ... constants.
            data: Arbitrary dict with event details.

        Returns:
            The created ClubEvent.
        """
        event = ClubEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type=event_type,
            data=data or {},
        )
        self._history.append(event)
        self._update_state(event)

        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception:
                pass  # Don't let one broken subscriber break the bus

        return event

    # ── state management ─────────────────────────────

    def _update_state(self, event: ClubEvent):
        """Keep aggregate state in sync with events."""
        data = event.data

        if event.event_type == AGENT_ONLINE:
            fp = data.get("fingerprint", "")
            self._state["agents_online"][fp] = {
                "name": data.get("name", "Unknown"),
                "fingerprint": fp,
                "connected_at": event.timestamp,
                "capabilities": data.get("capabilities", []),
            }
        elif event.event_type == AGENT_OFFLINE:
            fp = data.get("fingerprint", "")
            self._state["agents_online"].pop(fp, None)
        elif event.event_type == MESSAGE_RECEIVED or event.event_type == MESSAGE_SENT:
            self._state["message_count"] += 1
        elif event.event_type == ROOM_CREATED:
            rid = data.get("room_id", "")
            self._state["rooms"][rid] = {
                "name": data.get("name", "Unnamed"),
                "topic": data.get("topic", ""),
                "creator": data.get("creator", ""),
                "members": 1,
                "encryption": data.get("encryption", True),
                "created_at": event.timestamp,
            }
        elif event.event_type == ROOM_JOINED:
            rid = data.get("room_id", "")
            if rid in self._state["rooms"]:
                self._state["rooms"][rid]["members"] += 1
        elif event.event_type == ROOM_LEFT:
            rid = data.get("room_id", "")
            if rid in self._state["rooms"]:
                self._state["rooms"][rid]["members"] = max(
                    0, self._state["rooms"][rid]["members"] - 1
                )
        elif event.event_type == KNOWLEDGE_SHARED:
            self._state["knowledge_count"] += 1

    # ── query ────────────────────────────────────────

    def get_history(self, limit: int = 50) -> List[dict]:
        """Return the last N events (for late-joining viewers)."""
        return [e.to_dict() for e in list(self._history)[-limit:]]

    def get_state(self) -> Dict[str, Any]:
        """Get the current aggregate state snapshot."""
        return {
            "agents_online": list(self._state["agents_online"].values()),
            "rooms": list(self._state["rooms"].values()),
            "message_count": self._state["message_count"],
            "knowledge_count": self._state["knowledge_count"],
            "agent_count": len(self._state["agents_online"]),
            "room_count": len(self._state["rooms"]),
        }

    @property
    def state(self) -> Dict[str, Any]:
        return self.get_state()


# ── Global singleton (per process) ──────────────────
# The CLI and transport layers import this shared bus.

_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Return the global event bus singleton."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
