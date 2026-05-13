"""Room management for Agent Club.

Manages agent rooms with E2E encryption, member access control,
and CRDT-based state synchronization.
"""

import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from agent_club.crypto.keys import KeyBundle, KeyBundle as KB
from agent_club.crypto.room_key import RoomKeyManager, X3DHHandshake
from agent_club.crypto.cipher import RoomCipher, AESCipher
from agent_club.network.protocol import ProtocolMessage, MessageBuilder


class RoomSettings:
    """การตั้งค่าห้อง."""

    def __init__(
        self,
        name: str = "",
        topic: str = "",
        max_members: int = 50,
        join_policy: str = "public",  # public | invite_only | approval
        encryption: bool = True,
        persist_history: bool = False,
    ):
        self.name = name
        self.topic = topic
        self.max_members = max_members
        self.join_policy = join_policy
        self.encryption = encryption
        self.persist_history = persist_history

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "topic": self.topic,
            "max_members": self.max_members,
            "join_policy": self.join_policy,
            "encryption": self.encryption,
            "persist_history": self.persist_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoomSettings":
        return cls(
            name=data.get("name", ""),
            topic=data.get("topic", ""),
            max_members=data.get("max_members", 50),
            join_policy=data.get("join_policy", "public"),
            encryption=data.get("encryption", True),
            persist_history=data.get("persist_history", False),
        )


class RoomMember:
    """สมาชิกของห้อง."""

    def __init__(
        self,
        agent_id: str,
        name: str = "",
        capabilities: list = None,
        role: str = "member",
    ):
        self.agent_id = agent_id
        self.name = name
        self.capabilities = capabilities or []
        self.role = role  # member, moderator, admin
        self.joined_at = time.time()
        self.last_active = time.time()
        self.public_key: Optional[bytes] = None

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "capabilities": self.capabilities,
            "role": self.role,
            "joined_at": self.joined_at,
            "last_active": self.last_active,
        }

    def update_activity(self):
        self.last_active = time.time()


class Room:
    """ห้องแชทสำหรับ Agent Club.

    แต่ละ room มี:
    - E2E encryption key (สร้างจาก X3DH handshake)
    - Member list (CRDT-based)
    - Message history
    - Access control
    """

    def __init__(
        self,
        room_id: str,
        creator: RoomMember,
        settings: RoomSettings = None,
    ):
        self.room_id = room_id
        self.settings = settings or RoomSettings()
        self.creator_id = creator.agent_id
        self.created_at = time.time()

        # Members: agent_id -> RoomMember
        self._members: Dict[str, RoomMember] = {}
        self._add_member(creator)

        # Encryption
        self._key_manager = RoomKeyManager(None)  # Set agent key later
        self._cipher: Optional[RoomCipher] = None
        self._room_key: Optional[bytes] = None

        # Pending join requests: agent_id -> timestamp
        self._pending_joins: Dict[str, float] = {}

        # Message counter (for CRDT)
        self._message_counter = 0

        # Active handshakes: agent_id -> X3DHHandshake
        self._handshakes: Dict[str, X3DHHandshake] = {}

    @classmethod
    def create(
        cls,
        creator: RoomMember,
        settings: RoomSettings = None,
        agent_key: KeyBundle = None,
    ) -> "Room":
        """สร้าง room ใหม่."""
        room_id = hashlib.sha256(
            (creator.agent_id + str(time.time())).encode()
        ).hexdigest()[:16]

        room = cls(room_id, creator, settings)

        if agent_key:
            room._key_manager = RoomKeyManager(agent_key)

        return room

    def _add_member(self, member: RoomMember):
        """เพิ่มสมาชิก (internal)."""
        self._members[member.agent_id] = member
        member.update_activity()

    def get_room_key(self) -> Optional[bytes]:
        """ดึง room encryption key."""
        return self._room_key

    def set_room_key(self, key: bytes):
        """ตั้งค่า room key (หลัง key exchange เสร็จ)."""
        self._room_key = key
        self._cipher = RoomCipher(key)

    def get_member(self, agent_id: str) -> Optional[RoomMember]:
        """ดึงข้อมูลสมาชิก."""
        return self._members.get(agent_id)

    def get_members(self) -> List[RoomMember]:
        """ดึงรายชื่อสมาชิกทั้งหมด."""
        return list(self._members.values())

    def get_member_count(self) -> int:
        """จำนวนสมาชิก."""
        return len(self._members)

    def is_full(self) -> bool:
        """ตรวจสอบว่าห้องเต็มหรือไม่."""
        return len(self._members) >= self.settings.max_members

    def is_member(self, agent_id: str) -> bool:
        """ตรวจสอบว่าเป็นสมาชิกหรือไม่."""
        return agent_id in self._members

    def can_join(self, agent_id: str) -> tuple:
        """ตรวจสอบว่าสามารถเข้าห้องได้หรือไม่.

        Returns:
            (can_join: bool, reason: str)
        """
        if self.is_member(agent_id):
            return True, "already_member"

        if self.is_full():
            return False, "room_full"

        if self.settings.join_policy == "invite_only":
            if agent_id not in self._pending_joins:
                return False, "invite_only"

        if self.settings.join_policy == "approval":
            if agent_id not in self._pending_joins:
                return False, "needs_approval"

        return True, "ok"

    def request_join(self, agent_id: str, capabilities: list = None) -> str:
        """ขอเข้าร่วมห้อง.

        Returns:
            ผลลัพธ์: "accepted", "pending", "rejected", "already_member"
        """
        can_join, reason = self.can_join(agent_id)

        if not can_join:
            if reason == "invite_only":
                # ต้องได้รับ invite ก่อน
                return "rejected"
            elif reason == "needs_approval":
                # เพิ่มเข้าคิวรออนุมัติ
                self._pending_joins[agent_id] = time.time()
                return "pending"
            return "rejected"

        # ถ้า join_policy เป็น public หรือ invite_only (และมี invite)
        if self.settings.join_policy == "approval":
            self._pending_joins[agent_id] = time.time()
            return "pending"

        return "accepted"

    def approve_join(self, agent_id: str) -> bool:
        """อนุมัติการเข้าร่วม (สำหรับ approval policy).

        Args:
            agent_id: Agent ที่ต้องการอนุมัติ

        Returns:
            True หากอนุมัติสำเร็จ
        """
        if agent_id not in self._pending_joins:
            return False

        member = RoomMember(agent_id)
        self._add_member(member)
        del self._pending_joins[agent_id]

        # เริ่ม key exchange กับสมาชิกใหม่
        self._start_handshake(agent_id)

        return True

    def reject_join(self, agent_id: str):
        """ปฏิเสธการเข้าร่วม."""
        self._pending_joins.pop(agent_id, None)

    def invite(self, agent_id: str, inviter_id: str) -> bool:
        """เชิญ agent เข้าห้อง.

        Args:
            agent_id: Agent ที่ต้องการเชิญ
            inviter_id: Agent ที่เชิญ (ต้องมีสิทธิ์)

        Returns:
            True หากเชิญสำเร็จ
        """
        inviter = self._members.get(inviter_id)
        if not inviter or inviter.role not in ("admin", "moderator"):
            return False

        # สำหรับ invite_only: เพิ่มเข้า pending โดยตรง
        self._pending_joins[agent_id] = time.time()
        return True

    def add_member_direct(
        self,
        agent_id: str,
        name: str = "",
        capabilities: list = None,
        role: str = "member",
    ):
        """เพิ่มสมาชิกโดยตรง (ไม่ต้องขออนุญาต).

        ใช้สำหรับ: creator สร้างห้องแล้ว invite เพื่อน
        """
        member = RoomMember(agent_id, name, capabilities, role)
        self._add_member(member)

    def remove_member(self, agent_id: str):
        """ลบสมาชิกออกจากห้อง."""
        if agent_id in self._members:
            del self._members[agent_id]

    def start_key_exchange(self, agent_id: str, agent_key: KeyBundle):
        """เริ่ม E2E key exchange กับสมาชิกใหม่.

        Args:
            agent_id: Agent ที่ต้องการแลก key
            agent_key: KeyBundle ของ agent นั้น
        """
        handshake = X3DHHandshake(initiator=True)
        self._handshakes[agent_id] = handshake

        # Member ต้องถูกเพิ่มแล้ว
        if agent_id in self._members:
            self._members[agent_id].public_key = agent_key.exchange_pubkey

    def _start_handshake(self, agent_id: str):
        """เริ่ม handshake สำหรับสมาชิกใหม่."""
        handshake = X3DHHandshake(initiator=True)
        self._handshakes[agent_id] = handshake

    def rotate_key(self, new_key: bytes):
        """หมุน room key (forward secrecy)."""
        self._room_key = new_key
        if self._cipher:
            self._cipher = RoomCipher(new_key)

    def encrypt_message(self, sender_id: str, plaintext: bytes) -> tuple:
        """เข้ารหัส message.

        Args:
            sender_id: Agent ID ของผู้ส่ง
            plaintext: ข้อความธรรมดา

        Returns:
            (nonce, ciphertext)
        """
        if not self._cipher:
            raise ValueError("Room cipher not initialized (key exchange incomplete)")
        return self._cipher.encrypt_message(sender_id, plaintext)

    def decrypt_message(self, nonce: bytes, ciphertext: bytes) -> dict:
        """ถอดรหัส message.

        Returns:
            dict with sender_id, metadata, data
        """
        if not self._cipher:
            raise ValueError("Room cipher not initialized")
        return self._cipher.decrypt_message(nonce, ciphertext)

    def to_dict(self) -> dict:
        """แปลง room info เป็น dict (ไม่รวม sensitive data)."""
        return {
            "room_id": self.room_id,
            "name": self.settings.name,
            "topic": self.settings.topic,
            "member_count": len(self._members),
            "max_members": self.settings.max_members,
            "creator_id": self.creator_id,
            "created_at": self.created_at,
            "join_policy": self.settings.join_policy,
            "encryption": self.settings.encryption,
            "members": {
                aid: m.to_dict() for aid, m in self._members.items()
            },
        }

    def __repr__(self) -> str:
        return (
            f"Room(id={self.room_id[:8]}..., "
            f"name={self.settings.name!r}, "
            f"members={len(self._members)})"
        )