"""Room management module for Agent Club.

Manages agent rooms with E2E encryption, member access control,
CRDT-based state synchronization, and message handling.
"""

from agent_club.room.manager import Room, RoomMember, RoomSettings
from agent_club.room.message import Message, MessageHistory, MessageHandler
from agent_club.room.replication import (
    RoomState,
    ORSet,
    GCounter,
    LWWRegister,
    CRDTError,
)

__all__ = [
    "Room",
    "RoomMember",
    "RoomSettings",
    "Message",
    "MessageHistory",
    "MessageHandler",
    "RoomState",
    "ORSet",
    "GCounter",
    "LWWRegister",
    "CRDTError",
]