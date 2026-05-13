"""Knowledge exchange protocol for Agent Club.

Manages the process of agents sharing knowledge with each other:
- Publishing knowledge availability
- Requesting specific knowledge
- Transfer with verification
"""

import time
import uuid
from typing import Any, Dict, List, Optional

from agent_club.knowledge.schema import KnowledgeSchema


class ExchangeStatus:
    """สถานะของการแลกเปลี่ยน knowledge."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class KnowledgeOffer:
    """ข้อเสนอแชร์ knowledge."""

    def __init__(
        self,
        offer_id: str,
        sender_id: str,
        knowledge_ids: List[str],
        metadata: dict = None,
    ):
        self.offer_id = offer_id
        self.sender_id = sender_id
        self.knowledge_ids = knowledge_ids
        self.metadata = metadata or {}
        self.created_at = time.time()
        self.status = ExchangeStatus.PENDING

    def to_dict(self) -> dict:
        return {
            "offer_id": self.offer_id,
            "sender_id": self.sender_id,
            "knowledge_ids": self.knowledge_ids,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "status": self.status,
        }


class KnowledgeRequest:
    """คำขอรับ knowledge."""

    def __init__(
        self,
        request_id: str,
        requester_id: str,
        query: str,
        tags: List[str] = None,
        knowledge_type: str = None,
        max_results: int = 10,
    ):
        self.request_id = request_id
        self.requester_id = requester_id
        self.query = query
        self.tags = tags or []
        self.knowledge_type = knowledge_type
        self.max_results = max_results
        self.created_at = time.time()
        self.status = ExchangeStatus.PENDING
        self.responses: List[dict] = []

    def add_response(self, response: dict):
        """เพิ่ม response จากการค้นหา."""
        self.responses.append(response)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "requester_id": self.requester_id,
            "query": self.query,
            "tags": self.tags,
            "knowledge_type": self.knowledge_type,
            "status": self.status,
            "response_count": len(self.responses),
            "created_at": self.created_at,
        }


class KnowledgeExchange:
    """จัดการการแลกเปลี่ยน knowledge ระหว่าง agents.

    Workflow:
    1. Agent A ประกาศ knowledge ที่มี (publish)
    2. Agent B ค้นหาความรู้ที่ต้องการ (search/request)
    3. Agent A ส่ง knowledge ให้ Agent B (transfer)
    4. Agent B verify และเก็บลง local knowledge base
    """

    def __init__(self, local_agent_id: str, knowledge_base):
        """สร้าง KnowledgeExchange.

        Args:
            local_agent_id: Fingerprint ของตัวเอง
            knowledge_base: KnowledgeBase instance ของตัวเอง
        """
        self.local_agent_id = local_agent_id
        self.knowledge_base = knowledge_base

        # Active exchanges
        self._offers: Dict[str, KnowledgeOffer] = {}
        self._requests: Dict[str, KnowledgeRequest] = {}

        # Published knowledge index (for discovery)
        self._published_tags: Dict[str, List[str]] = {}  # tag -> [unit_ids]
        self._published_types: Dict[str, List[str]] = {}  # type -> [unit_ids]

    def publish(self, unit_ids: List[str], visibility: str = "room") -> str:
        """ประกาศว่ามี knowledge ให้ share.

        Args:
            unit_ids: รายการ knowledge unit IDs
            visibility: "room" | "public" | "private"

        Returns:
            offer_id
        """
        offer_id = uuid.uuid4().hex[:16]
        offer = KnowledgeOffer(
            offer_id=offer_id,
            sender_id=self.local_agent_id,
            knowledge_ids=unit_ids,
            metadata={"visibility": visibility},
        )
        self._offers[offer_id] = offer

        # อัพเดต published index
        for unit_id in unit_ids:
            unit = self.knowledge_base.get(unit_id)
            if unit:
                for tag in unit.get("tags", []):
                    if tag not in self._published_tags:
                        self._published_tags[tag] = []
                    if unit_id not in self._published_tags[tag]:
                        self._published_tags[tag].append(unit_id)

                ktype = unit.get("type", "")
                if ktype:
                    if ktype not in self._published_types:
                        self._published_types[ktype] = []
                    if unit_id not in self._published_types[ktype]:
                        self._published_types[ktype].append(unit_id)

        return offer_id

    def unpublish(self, offer_id: str):
        """ยกเลิกการประกาศ knowledge."""
        self._offers.pop(offer_id, None)

    def query_available(self, tags: list = None, knowledge_type: str = None) -> dict:
        """ดู knowledge ที่มีให้ share ในห้อง.

        Returns:
            dict with available knowledge summaries
        """
        available = []

        # ค้นหาจาก published index
        unit_ids = set()

        if tags:
            for tag in tags:
                if tag in self._published_tags:
                    unit_ids.update(self._published_tags[tag])

        if knowledge_type:
            if knowledge_type in self._published_types:
                unit_ids.update(self._published_types[knowledge_type])

        # ถ้าไม่มี filter ให้แสดงทั้งหมด
        if not tags and not knowledge_type:
            for offer in self._offers.values():
                unit_ids.update(offer.knowledge_ids)

        for unit_id in unit_ids:
            unit = self.knowledge_base.get(unit_id)
            if unit:
                available.append({
                    "id": unit_id,
                    "type": unit["type"],
                    "tags": unit.get("tags", []),
                    "confidence": unit.get("confidence", 0.5),
                    "source": unit["source"],
                })

        return {"count": len(available), "knowledge": available}

    def request_knowledge(
        self, query: str, tags: list = None, knowledge_type: str = None
    ) -> KnowledgeRequest:
        """สร้างคำขอ knowledge.

        Args:
            query: คำอธิบายสิ่งที่ต้องการ
            tags: แท็กที่ต้องการ
            knowledge_type: ประเภทที่ต้องการ

        Returns:
            KnowledgeRequest instance
        """
        request_id = uuid.uuid4().hex[:16]
        request = KnowledgeRequest(
            request_id=request_id,
            requester_id=self.local_agent_id,
            query=query,
            tags=tags,
            knowledge_type=knowledge_type,
        )
        self._requests[request_id] = request
        return request

    def respond_to_request(
        self, request_id: str, unit_ids: List[str]
    ) -> Optional[KnowledgeOffer]:
        """ตอบกลับคำขอ knowledge.

        Args:
            request_id: ID ของคำขอ
            unit_ids: รายการ knowledge unit IDs ที่จะส่ง

        Returns:
            KnowledgeOffer สำหรับการ transfer
        """
        request = self._requests.get(request_id)
        if not request:
            return None

        # ตรวจสอบว่า unit ทั้งหมดมีอยู่จริง
        valid_ids = []
        for unit_id in unit_ids:
            unit = self.knowledge_base.get(unit_id)
            if unit:
                valid_ids.append(unit_id)

        if not valid_ids:
            return None

        # สร้าง offer
        offer_id = uuid.uuid4().hex[:16]
        offer = KnowledgeOffer(
            offer_id=offer_id,
            sender_id=self.local_agent_id,
            knowledge_ids=valid_ids,
            metadata={"in_reply_to": request_id},
        )
        self._offers[offer_id] = offer

        # Update request status
        request.status = ExchangeStatus.IN_PROGRESS
        request.responses.append({
            "offer_id": offer_id,
            "unit_count": len(valid_ids),
            "sender_id": self.local_agent_id,
        })

        return offer

    def transfer_knowledge(
        self, offer_id: str, target_agent_id: str, signer=None
    ) -> List[dict]:
        """Transfer knowledge units ตาม offer.

        Args:
            offer_id: ID ของ offer
            target_agent_id: Agent ปลายทาง
            signer: IdentityKey สำหรับเซ็น

        Returns:
            รายการ knowledge units ที่ transfer
        """
        offer = self._offers.get(offer_id)
        if not offer:
            return []

        transfer_units = []
        for unit_id in offer.knowledge_ids:
            unit = self.knowledge_base.get(unit_id)
            if unit:
                # สร้าง copy สำหรับ transfer (ไม่ส่ง private data)
                transfer_unit = {
                    "id": unit["id"],
                    "type": unit["type"],
                    "content": unit["content"],
                    "tags": unit.get("tags", []),
                    "source": unit["source"],
                    "timestamp": unit["timestamp"],
                    "confidence": unit.get("confidence", 0.5),
                }

                # เซ็นถ้ามี signer
                if signer:
                    valid, _ = KnowledgeSchema.validate(transfer_unit)
                    if valid:
                        data = KnowledgeSchema._build_signable(transfer_unit)
                        transfer_unit["signature"] = signer.sign(data).hex()

                transfer_units.append(transfer_unit)

        offer.status = ExchangeStatus.COMPLETED
        return transfer_units

    def receive_knowledge(
        self, units: List[dict], sender_id: str, signer=None
    ) -> dict:
        """รับ knowledge จาก agent อื่น.

        Args:
            units: รายการ knowledge units
            sender_id: Agent ผู้ส่ง
            signer: IdentityKey ของผู้ส่ง (สำหรับ verify)

        Returns:
            dict with results
        """
        results = {
            "accepted": 0,
            "rejected": 0,
            "verified": 0,
            "failed_verification": 0,
            "errors": [],
        }

        for unit in units:
            # Validate schema
            valid, errors = KnowledgeSchema.validate(unit)
            if not valid:
                results["rejected"] += 1
                results["errors"].append(
                    f"Unit {unit.get('id')}: {errors}"
                )
                continue

            # Verify signature ถ้ามี signer
            if signer and "signature" in unit:
                if KnowledgeSchema.verify_signature(unit, signer):
                    results["verified"] += 1
                else:
                    results["failed_verification"] += 1
                    results["errors"].append(
                        f"Unit {unit['id']}: signature verification failed"
                    )
                    continue

            # เพิ่มลง local knowledge base (ใช้ original unit_id หรือสร้างใหม่)
            try:
                self.knowledge_base.add(unit)
                results["accepted"] += 1
            except Exception as e:
                results["rejected"] += 1
                results["errors"].append(f"Unit {unit['id']}: {str(e)}")

        return results

    def get_active_offers(self) -> List[dict]:
        """ดู active offers ทั้งหมด."""
        return [
            o.to_dict() for o in self._offers.values()
            if o.status in (ExchangeStatus.PENDING, ExchangeStatus.IN_PROGRESS)
        ]

    def get_active_requests(self) -> List[dict]:
        """ดู active requests ทั้งหมด."""
        return [
            r.to_dict() for r in self._requests.values()
            if r.status in (ExchangeStatus.PENDING, ExchangeStatus.IN_PROGRESS)
        ]

    def cleanup_expired(self, max_age_seconds: float = 3600):
        """ลบ exchange ที่หมดอายุ."""
        now = time.time()

        # Clean offers
        expired_offers = [
            oid for oid, offer in self._offers.items()
            if now - offer.created_at > max_age_seconds
        ]
        for oid in expired_offers:
            self._offers.pop(oid, None)

        # Clean requests
        expired_requests = [
            rid for rid, req in self._requests.items()
            if now - req.created_at > max_age_seconds
        ]
        for rid in expired_requests:
            self._requests.pop(rid, None)

    def get_stats(self) -> dict:
        """ดูสถิติการแลกเปลี่ยน."""
        return {
            "active_offers": len([
                o for o in self._offers.values()
                if o.status != ExchangeStatus.COMPLETED
            ]),
            "active_requests": len([
                r for r in self._requests.values()
                if r.status != ExchangeStatus.COMPLETED
            ]),
            "published_units": sum(
                len(ids) for ids in self._published_tags.values()
            ),
            "tags_count": len(self._published_tags),
            "types_count": len(self._published_types),
        }