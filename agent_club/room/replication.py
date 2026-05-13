"""CRDT-based state replication for Agent Club rooms.

Implements conflict-free replicated data types for room state
synchronization without a central coordinator.
"""

import time
import uuid
from typing import Any, Dict, List, Optional, Set


class CRDTError(Exception):
    """เกิดข้อผิดพลาดใน CRDT operation."""

    pass


class ORSet:
    """Observed-Remove Set — CRDT สำหรับ member list.

    ลักษณะ:
    - เพิ่ม/ลบสมาชิกได้โดยไม่ต้อง coordinator
    - ทุก replica จะ converge ไปที่ same state
    - ใช้ (actor, counter) เป็น unique tag สำหรับแต่ละสมาชิก
    """

    def __init__(self, actor_id: str):
        """สร้าง ORSet.

        Args:
            actor_id: ID ของ node ที่เป็นเจ้าของ replica นี้
        """
        self.actor_id = actor_id
        self._add_set: Dict[str, dict] = {}  # element -> {tag: (actor, counter)}
        self._remove_set: Set[str] = set()  # set of tags ที่ถูกลบ
        self._counter = 0

    def add(self, element: str) -> str:
        """เพิ่มสมาชิก.

        Args:
            element: สมาชิกที่ต้องการเพิ่ม (เช่น agent_id)

        Returns:
            tag ที่ใช้สำหรับ operation นี้
        """
        self._counter += 1
        tag = f"{self.actor_id}:{self._counter}"
        self._add_set[element] = {"tag": tag, "actor": self.actor_id, "ts": time.time()}
        return tag

    def remove(self, element: str) -> bool:
        """ลบสมาชิก.

        Args:
            element: สมาชิกที่ต้องการลบ

        Returns:
            True หากลบสำเร็จ
        """
        if element not in self._add_set:
            return False

        tag = self._add_set[element]["tag"]
        self._remove_set.add(tag)
        del self._add_set[element]
        return True

    def contains(self, element: str) -> bool:
        """ตรวจสอบว่าสมาชิกอยู่ในเซ็ตหรือไม่."""
        return element in self._add_set

    def get_all(self) -> List[str]:
        """ดึงสมาชิกทั้งหมด."""
        return list(self._add_set.keys())

    def merge(self, other: "ORSet") -> "ORSet":
        """Merge กับ ORSet อื่น.

        Args:
            other: ORSet ที่ต้องการ merge

        Returns:
            ORSet ใหม่ที่เป็นผลรวม
        """
        result = ORSet(self.actor_id)

        # รวม add_set — เลือก element ที่มี tag ล่าสุด
        all_elements = set(self._add_set.keys()) | set(other._add_set.keys())
        for elem in all_elements:
            self_entry = self._add_set.get(elem)
            other_entry = other._add_set.get(elem)

            if self_entry and other_entry:
                # เลือก entry ที่มี counter สูงกว่า
                if self_entry["tag"] > other_entry["tag"]:
                    result._add_set[elem] = self_entry
                else:
                    result._add_set[elem] = other_entry
            elif self_entry:
                result._add_set[elem] = self_entry
            else:
                result._add_set[elem] = other_entry

        # รวม remove_set
        result._remove_set = self._remove_set | other._remove_set

        # ลบ elements ที่ถูกลบในทั้งสองฝั่ง
        for tag in result._remove_set:
            to_remove = [
                elem for elem, entry in result._add_set.items()
                if entry["tag"] == tag
            ]
            for elem in to_remove:
                del result._add_set[elem]

        return result

    def to_dict(self) -> dict:
        return {
            "actor": self.actor_id,
            "members": {
                elem: entry for elem, entry in self._add_set.items()
            },
            "removed": list(self._remove_set),
        }

    def __len__(self) -> int:
        return len(self._add_set)

    def __contains__(self, element: str) -> bool:
        return self.contains(element)

    def __iter__(self):
        return iter(self._add_set.keys())


class GCounter:
    """G-Counter — CRDT counter ที่เพิ่มได้อย่างเดียว.

    ใช้สำหรับ: message counter, join counter
    """

    def __init__(self, actor_id: str):
        self.actor_id = actor_id
        self._counts: Dict[str, int] = {}  # actor_id -> count

    def increment(self, amount: int = 1):
        """เพิ่มค่า counter.

        Args:
            amount: จำนวนที่ต้องการเพิ่ม
        """
        current = self._counts.get(self.actor_id, 0)
        self._counts[self.actor_id] = current + amount

    def merge(self, other: "GCounter") -> "GCounter":
        """Merge กับ GCounter อื่น."""
        result = GCounter(self.actor_id)
        all_actors = set(self._counts.keys()) | set(other._counts.keys())

        for actor in all_actors:
            self_val = self._counts.get(actor, 0)
            other_val = other._counts.get(actor, 0)
            result._counts[actor] = max(self_val, other_val)

        return result

    @property
    def value(self) -> int:
        """ค่ารวมของ counter."""
        return sum(self._counts.values())

    def to_dict(self) -> dict:
        return {"counts": self._counts}


class LWWRegister:
    """Last-Writer-Wins Register — CRDT สำหรับ settings.

    ใช้สำหรับ: room settings, topic, ชื่อห้อง
    ค่าล่าสุด (ตาม timestamp) จะเป็นค่าที่ใช้
    """

    def __init__(self, actor_id: str):
        self.actor_id = actor_id
        self._value: Any = None
        self._timestamp: float = 0
        self._actor: str = ""

    def set(self, value: Any):
        """ตั้งค่า register.

        Args:
            value: ค่าใหม่
        """
        self._value = value
        self._timestamp = time.time()
        self._actor = self.actor_id

    def get(self) -> Any:
        """ดึงค่าปัจจุบัน."""
        return self._value

    def merge(self, other: "LWWRegister") -> "LWWRegister":
        """Merge กับ LWWRegister อื่น.

        เลือกค่าที่มี timestamp ใหม่กว่า
        """
        result = LWWRegister(self.actor_id)

        if self._timestamp > other._timestamp:
            result._value = self._value
            result._timestamp = self._timestamp
            result._actor = self._actor
        elif other._timestamp > self._timestamp:
            result._value = other._value
            result._timestamp = other._timestamp
            result._actor = other._actor
        else:
            # Timestamp เท่ากัน — ใช้ actor ID เป็นตัวตัดสิน
            if self._actor >= other._actor:
                result._value = self._value
                result._timestamp = self._timestamp
                result._actor = self._actor
            else:
                result._value = other._value
                result._timestamp = other._timestamp
                result._actor = other._actor

        return result

    def to_dict(self) -> dict:
        return {
            "value": self._value,
            "timestamp": self._timestamp,
            "actor": self._actor,
        }


class RoomState:
    """CRDT-based room state — รวม ORSet, GCounter, LWWRegister.

    ใช้สำหรับจัด state ของ room ทั้งหมด:
    - members: ORSet
    - message_count: GCounter
    - settings: LWWRegister
    """

    def __init__(self, room_id: str, actor_id: str):
        self.room_id = room_id
        self.actor_id = actor_id
        self.members = ORSet(actor_id)
        self.message_count = GCounter(actor_id)
        self.settings = LWWRegister(actor_id)

    def add_member(self, member_id: str):
        """เพิ่มสมาชิก."""
        self.members.add(member_id)

    def remove_member(self, member_id: str):
        """ลบสมาชิก."""
        self.members.remove(member_id)

    def increment_messages(self, count: int = 1):
        """เพิ่ม message counter."""
        self.message_count.increment(count)

    def update_settings(self, settings: dict):
        """อัพเดต room settings."""
        self.settings.set(settings)

    def merge(self, other: "RoomState") -> "RoomState":
        """Merge room state จากอีก replica หนึ่ง."""
        result = RoomState(self.room_id, self.actor_id)
        result.members = self.members.merge(other.members)
        result.message_count = self.message_count.merge(other.message_count)
        result.settings = self.settings.merge(other.settings)
        return result

    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "members": self.members.to_dict(),
            "message_count": self.message_count.to_dict(),
            "settings": self.settings.to_dict(),
        }

    def snapshot(self) -> bytes:
        """สร้าง snapshot ของ state (สำหรับส่งผ่าย network)."""
        import json
        return json.dumps(self.to_dict()).encode("utf-8")

    @classmethod
    def from_snapshot(cls, data: bytes, actor_id: str) -> "RoomState":
        """สร้าง RoomState จาก snapshot."""
        import json
        state = json.loads(data.decode("utf-8"))
        result = cls(state["room_id"], actor_id)

        # Restore members from ORSet data
        for elem, entry in state["members"].get("members", {}).items():
            result.members._add_set[elem] = entry
        result.members._remove_set = set(state["members"].get("removed", []))

        # Restore message counter
        result.message_count._counts = state["message_count"].get("counts", {})

        # Restore settings
        settings_data = state.get("settings", {})
        if settings_data.get("value") is not None:
            result.settings._value = settings_data["value"]
            result.settings._timestamp = settings_data.get("timestamp", 0)
            result.settings._actor = settings_data.get("actor", "")

        return result