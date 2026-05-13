"""Knowledge exchange module for Agent Club.

Manages structured knowledge sharing between agents:
- Knowledge schema & validation
- Local knowledge storage
- Exchange protocol
"""

import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional

from agent_club.crypto.signature import MessageSigner


class KnowledgeSchema:
    """Schema สำหรับ knowledge unit.

    ทุก knowledge ที่ share กันในระบบต้องมี format ตามนี้:
    {
        "id": str,           # unique identifier
        "type": str,         # fact | skill | code | experience
        "content": dict,     # structured content
        "tags": list[str],   # สำหรับค้นหา
        "source": str,       # fingerprint ของ agent ที่สร้าง
        "timestamp": float,  # เวลาที่สร้าง
        "confidence": float, # ระดับความเชื่อมั่น (0.0-1.0)
        "signature": str,    # ลายเซ็นของ source
    }
    """

    REQUIRED_FIELDS = {"id", "type", "content", "source", "timestamp"}
    VALID_TYPES = {"fact", "skill", "code", "experience"}

    @classmethod
    def validate(cls, knowledge: dict) -> tuple:
        """ตรวจสอบว่า knowledge unit ถูกต้องตาม schema.

        Returns:
            (valid: bool, errors: list[str])
        """
        errors = []

        # ตรวจสอบ required fields
        for field in cls.REQUIRED_FIELDS:
            if field not in knowledge:
                errors.append(f"Missing required field: {field}")

        if errors:
            return False, errors

        # ตรวจสอบ type
        if knowledge["type"] not in cls.VALID_TYPES:
            errors.append(
                f"Invalid type: {knowledge['type']}. "
                f"Must be one of {cls.VALID_TYPES}"
            )

        # ตรวจสอบ timestamp
        ts = knowledge.get("timestamp", 0)
        if ts <= 0 or ts > time.time() + 3600:
            errors.append("Invalid timestamp")

        # ตรวจสอบ confidence
        conf = knowledge.get("confidence", 0)
        if not (0.0 <= conf <= 1.0):
            errors.append(f"Invalid confidence: {conf}")

        # ตรวจสอบ content ไม่ว่าง
        if not knowledge.get("content"):
            errors.append("Content cannot be empty")

        return len(errors) == 0, errors

    @classmethod
    def create_knowledge_unit(
        cls,
        agent_id: str,
        knowledge_type: str,
        content: dict,
        tags: list = None,
        confidence: float = 0.5,
        signer=None,
    ) -> dict:
        """สร้าง knowledge unit ใหม่.

        Args:
            agent_id: Fingerprint ของ agent ที่สร้าง
            knowledge_type: ประเภท ("fact", "skill", "code", "experience")
            content: เนื้อหา (structured)
            tags: แท็กสำหรับค้นหา
            confidence: ระดับความเชื่อมั่น
            signer: IdentityKey สำหรับเซ็น

        Returns:
            knowledge unit dict
        """
        knowledge_id = hashlib.sha256(
            f"{agent_id}{time.time()}{uuid.uuid4()}".encode()
        ).hexdigest()[:24]

        unit = {
            "id": knowledge_id,
            "type": knowledge_type,
            "content": content,
            "tags": tags or [],
            "source": agent_id,
            "timestamp": time.time(),
            "confidence": confidence,
        }

        # เซ็นถ้ามี signer
        if signer:
            data_to_sign = cls._build_signable(unit)
            unit["signature"] = signer.sign(data_to_sign).hex()

        return unit

    @classmethod
    def _build_signable(cls, unit: dict) -> bytes:
        """สร้างข้อมูลสำหรับเซ็น (ไม่รวม signature)."""
        data = (
            unit["id"].encode()
            + unit["type"].encode()
            + str(unit["source"]).encode()
            + str(unit["timestamp"]).encode()
        )
        return data

    @classmethod
    def verify_signature(cls, unit: dict, public_key) -> bool:
        """ตรวจสอบ signature ของ knowledge unit.

        Args:
            unit: knowledge unit dict
            public_key: IdentityKey ของผู้สร้าง

        Returns:
            True หาก signature ถูกต้อง
        """
        sig_hex = unit.get("signature", "")
        if not sig_hex:
            return False

        try:
            data = cls._build_signable(unit)
            return public_key.verify(data, bytes.fromhex(sig_hex))
        except Exception:
            return False