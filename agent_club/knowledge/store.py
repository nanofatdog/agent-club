"""Local knowledge base storage for Agent Club.

Provides persistent storage for knowledge units that agents
create, receive, or discover. Supports search and retrieval.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from agent_club.knowledge.schema import KnowledgeSchema


class KnowledgeBase:
    """ฐานความรู้เฉพาะตัวของ Agent.

    เก็บ knowledge units ทั้งหมดที่ agent สร้าง/รับมา
    รองรับค้นหาและ filtering
    """

    def __init__(self, storage_path: str = None):
        """สร้าง KnowledgeBase.

        Args:
            storage_path: ไฟล์สำหรับ persist ข้อมูล (None = in-memory only)
        """
        self.storage_path = storage_path
        self._units: Dict[str, dict] = {}
        self._tags_index: Dict[str, List[str]] = {}  # tag -> [unit_ids]
        self._type_index: Dict[str, List[str]] = {}  # type -> [unit_ids]
        self._source_index: Dict[str, List[str]] = {}  # agent_id -> [unit_ids]

        # โหลดข้อมูลเก่าถ้ามี
        if storage_path and os.path.exists(storage_path):
            self._load_from_disk()

    def add(self, unit: dict, auto_index: bool = True) -> bool:
        """เพิ่ม knowledge unit.

        Args:
            unit: knowledge unit dict
            auto_index: สร้าง index อัตโนมัติหรือไม่

        Returns:
            True หากเพิ่มสำเร็จ
        """
        # Validate
        valid, errors = KnowledgeSchema.validate(unit)
        if not valid:
            raise ValueError(f"Invalid knowledge unit: {errors}")

        unit_id = unit["id"]
        self._units[unit_id] = unit

        if auto_index:
            self._index_unit(unit)

        # Persist ถ้ามี storage path
        if self.storage_path:
            self._save_to_disk()

        return True

    def get(self, unit_id: str) -> Optional[dict]:
        """ดึง knowledge unit ตาม ID."""
        return self._units.get(unit_id)

    def remove(self, unit_id: str) -> bool:
        """ลบ knowledge unit.

        Args:
            unit_id: ID ของ unit ที่ต้องการลบ

        Returns:
            True หากลบสำเร็จ
        """
        if unit_id not in self._units:
            return False

        unit = self._units.pop(unit_id)

        # ลบจาก index
        for tag in unit.get("tags", []):
            if tag in self._tags_index:
                self._tags_index[tag] = [
                    uid for uid in self._tags_index[tag] if uid != unit_id
                ]

        type_ = unit.get("type", "")
        if type_ in self._type_index:
            self._type_index[type_] = [
                uid for uid in self._type_index[type_] if uid != unit_id
            ]

        source = unit.get("source", "")
        if source in self._source_index:
            self._source_index[source] = [
                uid for uid in self._source_index[source] if uid != unit_id
            ]

        if self.storage_path:
            self._save_to_disk()

        return True

    def search(
        self,
        query: str = "",
        tags: list = None,
        knowledge_type: str = None,
        source: str = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> List[dict]:
        """ค้นหา knowledge units.

        Args:
            query: คำค้นหา (ค้นใน content)
            tags: แสดงเฉพาะ unit ที่มี tags เหล่านี้
            knowledge_type: แสดงเฉพาะ type นี้
            source: แสดงเฉพาะ unit จาก source นี้
            min_confidence: ระดับความเชื่อมั่นขั้นต่ำ
            limit: จำนวนผลลัพธ์สูงสุด

        Returns:
            รายการ knowledge units (เรียงตาม relevance)
        """
        candidates = set(self._units.keys())

        # Filter by tags
        if tags:
            tagged_ids = set()
            for tag in tags:
                if tag in self._tags_index:
                    tagged_ids.update(self._tags_index[tag])
            candidates &= tagged_ids

        # Filter by type
        if knowledge_type:
            if knowledge_type in self._type_index:
                candidates &= set(self._type_index[knowledge_type])
            else:
                return []

        # Filter by source
        if source:
            if source in self._source_index:
                candidates &= set(self._source_index[source])
            else:
                return []

        # คำนวณ relevance score
        results = []
        for unit_id in candidates:
            unit = self._units[unit_id]

            # ตรวจสอบ confidence
            if unit.get("confidence", 0) < min_confidence:
                continue

            score = self._calculate_relevance(unit, query, tags)
            results.append((score, unit))

        # เรียงตาม relevance
        results.sort(key=lambda x: x[0], reverse=True)
        return [unit for _, unit in results[:limit]]

    def get_by_type(self, knowledge_type: str) -> List[dict]:
        """ดึง knowledge ตามประเภท."""
        ids = self._type_index.get(knowledge_type, [])
        return [self._units[uid] for uid in ids if uid in self._units]

    def get_by_source(self, agent_id: str) -> List[dict]:
        """ดึง knowledge ตาม source."""
        ids = self._source_index.get(agent_id, [])
        return [self._units[uid] for uid in ids if uid in self._units]

    def get_by_tag(self, tag: str) -> List[dict]:
        """ดึง knowledge ตาม tag."""
        ids = self._tags_index.get(tag, [])
        return [self._units[uid] for uid in ids if uid in self._units]

    def get_all_tags(self) -> Dict[str, int]:
        """ดู tags ทั้งหมดกับจำนวน unit แต่ละ tag."""
        return {tag: len(ids) for tag, ids in self._tags_index.items()}

    def count(self) -> int:
        """จำนวน knowledge units ทั้งหมด."""
        return len(self._units)

    def clear(self):
        """ล้าง knowledge base ทั้งหมด."""
        self._units.clear()
        self._tags_index.clear()
        self._type_index.clear()
        self._source_index.clear()

    def _index_unit(self, unit: dict):
        """สร้าง index สำหรับ unit.

        Args:
            unit: knowledge unit dict
        """
        unit_id = unit["id"]

        # Index tags
        for tag in unit.get("tags", []):
            if tag not in self._tags_index:
                self._tags_index[tag] = []
            if unit_id not in self._tags_index[tag]:
                self._tags_index[tag].append(unit_id)

        # Index type
        ktype = unit.get("type", "")
        if ktype:
            if ktype not in self._type_index:
                self._type_index[ktype] = []
            if unit_id not in self._type_index[ktype]:
                self._type_index[ktype].append(unit_id)

        # Index source
        source = unit.get("source", "")
        if source:
            if source not in self._source_index:
                self._source_index[source] = []
            if unit_id not in self._source_index[source]:
                self._source_index[source].append(unit_id)

    def _calculate_relevance(
        self, unit: dict, query: str, search_tags: list = None
    ) -> float:
        """คำนวณ relevance score.

        Args:
            unit: knowledge unit
            query: คำค้นหา
            search_tags: แท็กที่ใช้ค้นหา

        Returns:
            relevance score (0.0 - 1.0)
        """
        score = 0.0

        # Match tags ที่ค้นหา
        if search_tags:
            unit_tags = set(unit.get("tags", []))
            search_set = set(search_tags)
            tag_overlap = len(unit_tags & search_set)
            if search_set:
                score += tag_overlap / len(search_set) * 0.5

        # Match text query
        if query:
            content_str = json.dumps(unit.get("content", {})).lower()
            query_lower = query.lower()
            if query_lower in content_str:
                score += 0.5
            # ชื่อเรื่อง (ถ้ามี) สำคัญกว่า
            if query_lower in str(unit.get("id", "")).lower():
                score += 0.2

        # Confidence bonus
        score += unit.get("confidence", 0.5) * 0.2

        return min(score, 1.0)

    def _save_to_disk(self):
        """บันทึกข้อมูลลงไฟล์."""
        try:
            data = {
                "units": list(self._units.values()),
                "timestamp": time.time(),
            }
            # เขียนแบบปลอดภัย (สร้าง temp แล้ว rename)
            temp_path = self.storage_path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.storage_path)
        except Exception:
            pass  # สำหรับ in-memory storage

    def _load_from_disk(self):
        """โหลดข้อมูลจากไฟล์."""
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for unit in data.get("units", []):
                try:
                    valid, _ = KnowledgeSchema.validate(unit)
                    if valid:
                        self._units[unit["id"]] = unit
                        self._index_unit(unit)
                except Exception:
                    continue
        except (json.JSONDecodeError, KeyError):
            pass