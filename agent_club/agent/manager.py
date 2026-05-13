"""Agent management for Agent Club.

Manages AI agent lifecycle, capabilities, autonomy, and decision-making.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from agent_club.crypto.keys import KeyBundle
from agent_club.room.manager import Room, RoomSettings, RoomMember
from agent_club.network.protocol import ProtocolMessage, MessageBuilder


class AgentConfig:
    """การตั้งค่าสำหรับ Agent."""

    def __init__(
        self,
        auto_join: bool = False,
        response_mode: str = "selective",  # auto | manual | selective
        max_rooms: int = 10,
        knowledge_sharing: bool = True,
        reputation_weight: float = 1.0,
        discovery_interval: float = 30.0,
        heartbeat_interval: float = 60.0,
    ):
        self.auto_join = auto_join
        self.response_mode = response_mode
        self.max_rooms = max_rooms
        self.knowledge_sharing = knowledge_sharing
        self.reputation_weight = reputation_weight
        self.discovery_interval = discovery_interval
        self.heartbeat_interval = heartbeat_interval

    def to_dict(self) -> dict:
        return {
            "auto_join": self.auto_join,
            "response_mode": self.response_mode,
            "max_rooms": self.max_rooms,
            "knowledge_sharing": self.knowledge_sharing,
            "reputation_weight": self.reputation_weight,
            "discovery_interval": self.discovery_interval,
            "heartbeat_interval": self.heartbeat_interval,
        }


class AgentCapability:
    """ประกาศความสามารถของ Agent.

    แต่ละ agent สามารถประกาศ capability หลายอย่าง
    เพื่อให้ agent อื่นรู้ว่าขอความช่วยเหลือเรื่องอะไรได้
    """

    # Built-in capabilities
    CODE_REVIEW = "code_review"
    TRANSLATION = "translation"
    MATH = "math"
    SEARCH = "search"
    DATA_ANALYSIS = "data_analysis"
    WRITING = "writing"
    SECURITY_AUDIT = "security_audit"
    DEBUGGING = "debugging"

    ALL = [
        CODE_REVIEW, TRANSLATION, MATH, SEARCH,
        DATA_ANALYSIS, WRITING, SECURITY_AUDIT, DEBUGGING,
    ]

    def __init__(self, name: str, confidence: float = 0.5, metadata: dict = None):
        self.name = name
        self.confidence = confidence  # 0.0 - 1.0
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


class Agent:
    """AI Agent ในระบบ Agent Club.

    แต่ละ Agent มี:
    - Identity (KeyBundle)
    - Capabilities (ที่ทำได้)
    - Room memberships
    - Knowledge base
    - Decision-making logic
    """

    def __init__(
        self,
        name: str,
        bundle: KeyBundle = None,
        config: AgentConfig = None,
        capabilities: list = None,
    ):
        """สร้าง Agent ใหม่.

        Args:
            name: ชื่อ agent
            bundle: KeyBundle หากไม่ระบุจะสร้างใหม่
            config: AgentConfig หากไม่ระบุจะใช้ค่า default
            capabilities: รายการ capability เริ่มต้น
        """
        self.name = name
        self.bundle = bundle or KeyBundle(name=name)
        self.config = config or AgentConfig()
        self.capabilities: Dict[str, AgentCapability] = {}
        self.rooms: Dict[str, Room] = {}
        self._message_builder = MessageBuilder(self.bundle.fingerprint)

        # Add capabilities
        if capabilities:
            for cap in capabilities:
                self.add_capability(cap)

        # Internal state
        self._running = False
        self._discovery_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._pending_responses: Dict[str, asyncio.Event] = {}
        self._response_data: Dict[str, Any] = {}

    def add_capability(self, capability: str, confidence: float = 0.5, metadata: dict = None):
        """เพิ่ม capability ให้ agent.

        Args:
            capability: ชื่อ capability
            confidence: ระดับความมั่นใจ (0.0-1.0)
            metadata: ข้อมูลเพิ่มเติม
        """
        self.capabilities[capability] = AgentCapability(
            capability, confidence, metadata
        )

    def remove_capability(self, capability: str):
        """ลบ capability."""
        self.capabilities.pop(capability, None)

    def has_capability(self, capability: str) -> bool:
        """ตรวจสอบว่ามี capability นี้หรือไม่."""
        return capability in self.capabilities

    def get_capabilities(self) -> List[str]:
        """ดู capability ทั้งหมด."""
        return list(self.capabilities.keys())

    def create_room(
        self,
        name: str,
        topic: str = "",
        join_policy: str = "public",
        max_members: int = 50,
        encryption: bool = True,
    ) -> Room:
        """สร้าง room ใหม่.

        Args:
            name: ชื่อห้อง
            topic: หัวข้อ
            join_policy: นโยบายการเข้าร่วม
            max_members: สมาชิกสูงสุด
            encryption: เปิดใช้ E2E encryption

        Returns:
            Room instance
        """
        settings = RoomSettings(
            name=name,
            topic=topic,
            max_members=max_members,
            join_policy=join_policy,
            encryption=encryption,
        )

        member = RoomMember(
            agent_id=self.bundle.fingerprint,
            name=self.name,
            capabilities=self.get_capabilities(),
            role="admin",
        )

        room = Room.create(member, settings, self.bundle)
        self.rooms[room.room_id] = room
        return room

    def join_room(self, room: Room) -> bool:
        """เข้าร่วม room.

        Args:
            room: Room ที่ต้องการเข้าร่วม

        Returns:
            True หากเข้าร่วมสำเร็จ
        """
        can_join, reason = room.can_join(self.bundle.fingerprint)

        if can_join:
            if reason == "ok":
                member = RoomMember(
                    agent_id=self.bundle.fingerprint,
                    name=self.name,
                    capabilities=self.get_capabilities(),
                    role="member",
                )
                room.add_member_direct(
                    self.bundle.fingerprint,
                    self.name,
                    self.get_capabilities(),
                )
                self.rooms[room.room_id] = room

                # เริ่ม key exchange
                room.start_key_exchange(
                    self.bundle.fingerprint,
                    self.bundle,
                )

                return True
            elif reason == "pending":
                room.request_join(self.bundle.fingerprint, self.get_capabilities())
                return True

        return False

    def leave_room(self, room_id: str):
        """ออกจาก room.

        Args:
            room_id: ID ของ room
        """
        if room_id in self.rooms:
            del self.rooms[room_id]

    def list_rooms(self) -> List[dict]:
        """รายการ room ที่ agent อยู่."""
        return [
            {"id": rid, "name": r.settings.name, "members": r.get_member_count()}
            for rid, r in self.rooms.items()
        ]

    def send_message(
        self,
        room_id: str,
        msg_type: str,
        content: Any,
        metadata: dict = None,
    ) -> Optional[ProtocolMessage]:
        """ส่งข้อความใน room.

        Args:
            room_id: ห้องเป้าหมาย
            msg_type: ประเภทข้อความ
            content: เนื้อหา
            metadata: ข้อมูลเพิ่มเติม

        Returns:
            ProtocolMessage หากส่งได้, None ถ้าไม่
        """
        if room_id not in self.rooms:
            return None

        room = self.rooms[room_id]
        builder = self._message_builder

        if msg_type == "text":
            message = builder.text(room_id, content)
        elif msg_type == "knowledge":
            message = builder.knowledge(room_id, content, metadata.get("tags", []) if metadata else [])
        elif msg_type == "request":
            message = builder.request(room_id, content.get("type", ""), content.get("query", ""))
        elif msg_type == "response":
            message = builder.response(room_id, metadata.get("request_nonce", ""), content if isinstance(content, bytes) else content.encode())
        elif msg_type == "action":
            message = builder.action(room_id, content.get("action", ""), content.get("params", {}))
        else:
            return None

        # Sign message
        message.sign(self.bundle.identity_key)

        # Encrypt if room has encryption
        if room.settings.encryption and room._cipher:
            # Note: actual encrypted payload would go through RoomCipher
            pass

        return message

    def can_help_with(self, request_type: str) -> tuple:
        """ตรวจสอบว่า agent นี้ช่วยเรื่องนี้ได้หรือไม่.

        Returns:
            (can_help: bool, confidence: float)
        """
        for cap_name, cap in self.capabilities.items():
            if cap_name == request_type or request_type in cap_name:
                return True, cap.confidence
        return False, 0.0

    def decide_join_request(self, room_info: dict) -> dict:
        """ตัดสินใจว่าจะเข้าห้องหรือไม่.

        Args:
            room_info: ข้อมูลห้อง

        Returns:
            dict with decision and confidence
        """
        # Simple heuristic: join if room has capabilities we need
        # or if it's a public room with few members
        members = room_info.get("member_count", 0)
        policy = room_info.get("join_policy", "public")

        confidence = 0.5

        if policy == "public":
            confidence += 0.2
        if members < 10:
            confidence += 0.1
        if room_info.get("encryption"):
            confidence += 0.1

        return {
            "decision": "accept" if confidence > 0.5 else "defer",
            "confidence": min(confidence, 1.0),
            "reason": f"Confidence: {confidence:.2f}",
        }

    def decide_response(self, message: dict) -> dict:
        """ตัดสินใจว่าจะตอบข้อความหรือไม่.

        Args:
            message: ข้อความที่ได้รับ

        Returns:
            dict with decision
        """
        msg_type = message.get("type", "")

        if msg_type == "request":
            can_help, confidence = self.can_help_with(
                message.get("metadata", {}).get("request_type", "")
            )
            return {
                "decision": "respond" if can_help else "ignore",
                "confidence": confidence,
                "reason": "Can help" if can_help else "No matching capability",
            }

        elif msg_type == "text":
            # Selective response based on agent config
            if self.config.response_mode == "auto":
                return {"decision": "respond", "confidence": 0.8, "reason": "Auto mode"}
            elif self.config.response_mode == "selective":
                return {"decision": "defer", "confidence": 0.3, "reason": "Selective mode - deferring"}
            else:
                return {"decision": "ignore", "confidence": 0.0, "reason": "Manual mode"}

        return {"decision": "ignore", "confidence": 0.0, "reason": "Unknown message type"}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fingerprint": self.bundle.fingerprint,
            "capabilities": [
                cap.to_dict() for cap in self.capabilities.values()
            ],
            "room_count": len(self.rooms),
            "config": self.config.to_dict(),
        }

    def __repr__(self) -> str:
        return f"Agent(name={self.name!r}, fingerprint={self.bundle.fingerprint[:8]}...)"


class AgentManager:
    """จัดการ agent หลายตัวในระบบ.

    ใช้สำหรับ:
    - ลงทะเบียน agent ใหม่
    - ติดตาม agent ทั้งหมด
    - ประสานงานระหว่าง agent
    """

    def __init__(self):
        self.agents: Dict[str, Agent] = {}  # fingerprint -> Agent
        self._agent_names: Dict[str, str] = {}  # name -> fingerprint

    def register(self, agent: Agent) -> bool:
        """ลงทะเบียน agent ใหม่.

        Args:
            agent: Agent instance

        Returns:
            True หากลงทะเบียนสำเร็จ
        """
        fp = agent.bundle.fingerprint

        if fp in self.agents:
            return False

        if agent.name in self._agent_names:
            # ชื่อซ้ำ — เพิ่ม suffix
            agent.name = f"{agent.name}_{fp[:4]}"

        self.agents[fp] = agent
        self._agent_names[agent.name] = fp
        return True

    def unregister(self, agent_id: str):
        """ยกเลิกการลงทะเบียน agent.

        Args:
            agent_id: Fingerprint ของ agent
        """
        if agent_id in self.agents:
            agent = self.agents.pop(agent_id)
            self._agent_names.pop(agent.name, None)

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """ดึง agent ตาม ID."""
        return self.agents.get(agent_id)

    def find_agent(self, name: str) -> Optional[Agent]:
        """ค้นหา agent ตามชื่อ."""
        fp = self._agent_names.get(name)
        if fp:
            return self.agents.get(fp)
        return None

    def find_capable_agents(self, capability: str) -> List[Agent]:
        """ค้นหา agent ที่มีความสามารถที่ต้องการ.

        Args:
            capability: ความสามารถที่ต้องการ

        Returns:
            รายการ Agent ที่มีความสามารถนั้น
        """
        return [
            agent for agent in self.agents.values()
            if agent.has_capability(capability)
        ]

    def broadcast(self, message: ProtocolMessage, exclude: Set[str] = None):
        """ส่งข้อความไปยัง agent ทั้งหมด.

        Args:
            message: ProtocolMessage ที่ต้องการส่ง
            exclude: เซ็ตของ agent_id ที่ไม่ต้องส่ง
        """
        exclude = exclude or set()
        for fp, agent in self.agents.items():
            if fp in exclude:
                continue
            # ส่งผ่าน room หรือ direct message
            pass  # Implementation depends on transport

    def list_agents(self) -> List[dict]:
        """รายการ agent ทั้งหมด."""
        return [a.to_dict() for a in self.agents.values()]

    @property
    def agent_count(self) -> int:
        return len(self.agents)