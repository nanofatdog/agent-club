"""Message handling for Agent Club rooms.

Handles message types, formatting, encryption/decryption,
and delivery tracking within rooms.
"""

import time
import uuid
from typing import Any, Dict, List, Optional

from agent_club.network.protocol import ProtocolMessage, MessageBuilder


class Message:
    """ข้อความภายใน room ของ Agent Club.

    ทุก message จะถูกเข้ารหัสก่อนส่ง และถอดรหัสเมื่อรับ
    """

    def __init__(
        self,
        message_id: str,
        sender_id: str,
        room_id: str,
        msg_type: str,
        content: Any,
        timestamp: float = None,
        metadata: dict = None,
        encrypted: bool = True,
    ):
        self.message_id = message_id
        self.sender_id = sender_id
        self.room_id = room_id
        self.type = msg_type
        self.content = content
        self.timestamp = timestamp or time.time()
        self.metadata = metadata or {}
        self.encrypted = encrypted
        self.delivered_to: List[str] = []
        self.read_by: List[str] = []

    @classmethod
    def create_text(
        cls, sender_id: str, room_id: str, text: str, encrypted: bool = True
    ) -> "Message":
        return cls(
            message_id=uuid.uuid4().hex[:16],
            sender_id=sender_id,
            room_id=room_id,
            msg_type="text",
            content=text,
            metadata={"encrypted": encrypted},
            encrypted=encrypted,
        )

    @classmethod
    def create_knowledge(
        cls,
        sender_id: str,
        room_id: str,
        knowledge_data: dict,
        encrypted: bool = True,
    ) -> "Message":
        return cls(
            message_id=uuid.uuid4().hex[:16],
            sender_id=sender_id,
            room_id=room_id,
            msg_type="knowledge",
            content=knowledge_data,
            metadata={"encrypted": encrypted, "knowledge": True},
            encrypted=encrypted,
        )

    @classmethod
    def create_request(
        cls,
        sender_id: str,
        room_id: str,
        request_type: str,
        query: str,
        encrypted: bool = True,
    ) -> "Message":
        return cls(
            message_id=uuid.uuid4().hex[:16],
            sender_id=sender_id,
            room_id=room_id,
            msg_type="request",
            content={"type": request_type, "query": query},
            metadata={"encrypted": encrypted},
            encrypted=encrypted,
        )

    @classmethod
    def create_response(
        cls,
        sender_id: str,
        room_id: str,
        original_message_id: str,
        response_data: Any,
        encrypted: bool = True,
    ) -> "Message":
        return cls(
            message_id=uuid.uuid4().hex[:16],
            sender_id=sender_id,
            room_id=room_id,
            msg_type="response",
            content=response_data,
            metadata={
                "encrypted": encrypted,
                "original_id": original_message_id,
            },
            encrypted=encrypted,
        )

    @classmethod
    def create_action(
        cls,
        sender_id: str,
        room_id: str,
        action: str,
        params: dict = None,
    ) -> "Message":
        return cls(
            message_id=uuid.uuid4().hex[:16],
            sender_id=sender_id,
            room_id=room_id,
            msg_type="action",
            content={"action": action, "params": params or {}},
            metadata={},
            encrypted=False,  # Actions may need to be visible to all
        )

    @classmethod
    def create_system(
        cls,
        room_id: str,
        system_message: str,
    ) -> "Message":
        return cls(
            message_id=uuid.uuid4().hex[:16],
            sender_id="system",
            room_id=room_id,
            msg_type="system",
            content=system_message,
            metadata={"system": True},
            encrypted=False,
        )

    def mark_delivered(self, agent_id: str):
        """ติดสถานะส่งถึง agent."""
        if agent_id not in self.delivered_to:
            self.delivered_to.append(agent_id)

    def mark_read(self, agent_id: str):
        """ติดสถานะอ่านแล้ว."""
        if agent_id not in self.read_by:
            self.read_by.append(agent_id)

    def is_delivered(self, agent_id: str) -> bool:
        return agent_id in self.delivered_to

    def is_read(self, agent_id: str) -> bool:
        return agent_id in self.read_by

    def age_seconds(self) -> float:
        return time.time() - self.timestamp

    def to_dict(self) -> dict:
        return {
            "id": self.message_id,
            "sender": self.sender_id,
            "room": self.room_id,
            "type": self.type,
            "content": self.content,
            "timestamp": self.timestamp,
            "meta": self.metadata,
            "encrypted": self.encrypted,
            "delivered_count": len(self.delivered_to),
            "read_count": len(self.read_by),
        }

    def __repr__(self) -> str:
        return (
            f"Message(id={self.message_id[:8]}, "
            f"type={self.type}, "
            f"sender={self.sender_id[:8]}...)"
        )


class MessageHistory:
    """เก็บประวัติข้อความในห้อง.

    รองรับ pagination และ optional persistence.
    """

    def __init__(self, max_size: int = 10000, persist: bool = False):
        self.max_size = max_size
        self.persist = persist
        self._messages: List[Message] = []
        self._index: Dict[str, int] = {}  # message_id -> index

    def add(self, message: Message) -> int:
        """เพิ่มข้อความ.

        Returns:
            ลำดับข้อความ (index)
        """
        if len(self._messages) >= self.max_size:
            # ลบข้อความเก่าสุด (FIFO)
            old = self._messages.pop(0)
            self._index.pop(old.message_id, None)
            # ปรับ index ทั้งหมด
            self._index = {
                m.message_id: i for i, m in enumerate(self._messages)
            }

        index = len(self._messages)
        self._messages.append(message)
        self._index[message.message_id] = index
        return index

    def get(self, message_id: str) -> Optional[Message]:
        """ดึงข้อความตาม ID."""
        idx = self._index.get(message_id)
        if idx is not None:
            return self._messages[idx]
        return None

    def get_recent(self, count: int = 50) -> List[Message]:
        """ดึงข้อความล่าสุด."""
        return self._messages[-count:]

    def get_since(self, timestamp: float) -> List[Message]:
        """ดึงข้อความตั้งแต่ timestamp ที่กำหนด."""
        return [m for m in self._messages if m.timestamp >= timestamp]

    def get_between(self, from_ts: float, to_ts: float) -> List[Message]:
        """ดึงข้อความในช่วงเวลา."""
        return [
            m for m in self._messages
            if from_ts <= m.timestamp <= to_ts
        ]

    def search(self, keyword: str, limit: int = 20) -> List[Message]:
        """ค้นหาข้อความ (text messages เท่านั้น)."""
        results = []
        for msg in reversed(self._messages):
            if msg.type == "text" and isinstance(msg.content, str):
                if keyword.lower() in msg.content.lower():
                    results.append(msg)
                    if len(results) >= limit:
                        break
        return results

    def get_by_type(self, msg_type: str) -> List[Message]:
        """ดึงข้อความตามประเภท."""
        return [m for m in self._messages if m.type == msg_type]

    def count(self) -> int:
        return len(self._messages)

    def clear(self):
        """ล้างประวัติทั้งหมด."""
        self._messages.clear()
        self._index.clear()

    def __iter__(self):
        return iter(self._messages)

    def __len__(self):
        return len(self._messages)


class MessageHandler:
    """จัดการ routing และ processing ของข้อความใน room.

    รับผิดชอบ:
    - ส่ง message ไปยังสมาชิกทั้งหมด
    - จัดการ delivery confirmation
    - จัดการ message types ต่างๆ
    """

    def __init__(self, room: "Room"):
        self.room = room
        self._history = MessageHistory()
        self._pending_acks: Dict[str, dict] = {}  # message_id -> delivery info

    def handle_incoming(self, message: Message) -> Optional[dict]:
        """จัดการข้อความที่ได้รับจากสมาชิก.

        Returns:
            Response dict หรือ None
        """
        # บันทึกลง history
        self._history.add(message)

        # จัดการตามประเภท
        if message.type == "text":
            return self._handle_text(message)
        elif message.type == "knowledge":
            return self._handle_knowledge(message)
        elif message.type == "request":
            return self._handle_request(message)
        elif message.type == "response":
            return self._handle_response(message)
        elif message.type == "action":
            return self._handle_action(message)
        elif message.type == "system":
            return self._handle_system(message)

        return None

    def _handle_text(self, message: Message) -> dict:
        """จัดการข้อความ text ปกติ."""
        # ส่งต่อไปยังสมาชิกทั้งหมดยกเว้นผู้ส่ง
        self._relay(message, exclude={message.sender_id})
        return {"status": "delivered", "recipients": self.room.get_member_count() - 1}

    def _handle_knowledge(self, message: Message) -> dict:
        """จัดการ knowledge sharing."""
        # Validate knowledge format
        content = message.content
        if isinstance(content, dict):
            required_fields = {"id", "type", "content"}
            if not required_fields.issubset(content.keys()):
                return {"status": "error", "message": "Invalid knowledge format"}

        self._relay(message, exclude={message.sender_id})
        return {"status": "knowledge_shared"}

    def _handle_request(self, message: Message) -> dict:
        """จัดการ request (ขอความช่วยเหลือ).

        Routing: ส่งไปยัง agent ที่มี capability ตรงกับ request type
        """
        request_type = message.content.get("type", "")
        capable_members = [
            m for m in self.room.get_members()
            if request_type in m.capabilities
        ]

        if capable_members:
            self._relay(message, targets=[m.agent_id for m in capable_members])
            return {
                "status": "request_sent",
                "targets": [m.agent_id for m in capable_members],
            }
        else:
            # ไม่มีใครมี capability — broadcast ให้ทุกคน
            self._relay(message, exclude={message.sender_id})
            return {"status": "broadcast", "note": "no_matching_capability"}

    def _handle_response(self, message: Message) -> dict:
        """จัดการ response สำหรับ request."""
        original_id = message.metadata.get("original_id", "")
        # ส่ง response ไปยังผู้ที่ request เท่านั้น
        self._relay(message, targets=[message.sender_id])
        return {"status": "response_delivered", "original_id": original_id}

    def _handle_action(self, message: Message) -> dict:
        """จัดการ action message (เช่น join, leave, vote)."""
        action = message.content.get("action", "")
        params = message.content.get("params", {})

        if action == "join":
            self.room.request_join(message.sender_id)
        elif action == "leave":
            self.room.remove_member(message.sender_id)
        elif action == "vote":
            # ลงคะแนนเสียง
            pass

        return {"status": "action_processed", "action": action}

    def _handle_system(self, message: Message) -> dict:
        """จัดการ system message."""
        self._relay(message)
        return {"status": "system_broadcasted"}

    def _relay(
        self,
        message: Message,
        exclude: set = None,
        targets: list = None,
    ):
        """ส่งต่อ message ไปยังสมาชิก.

        Args:
            exclude: เซ็ตของ agent_id ที่ไม่ต้องส่ง
            targets: รายการ agent_id ที่ต้องส่ง (ถ้า None ส่งทุกคน)
        """
        exclude = exclude or set()
        members = self.room.get_members()

        for member in members:
            if member.agent_id in exclude:
                continue
            if targets and member.agent_id not in targets:
                continue
            # ทำเครื่องหมายว่าส่งแล้ว
            message.mark_delivered(member.agent_id)

    def get_history(self, limit: int = 50, since: float = None) -> List[dict]:
        """ดึงประวัติข้อความ."""
        if since:
            messages = self._history.get_since(since)
        else:
            messages = self._history.get_recent(limit)

        return [m.to_dict() for m in messages]