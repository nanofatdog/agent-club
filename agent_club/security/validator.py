"""Message & content validation for Agent Club.

Provides security validation:
- Signature verification
- Content safety checks
- Replay attack prevention
- Prompt injection detection
"""

import hashlib
import time
from typing import Any, Dict, List, Optional, Set


class ContentSafety:
    """ผลการตรวจสอบความปลอดภัยของเนื้อหา."""

    def __init__(self, is_safe: bool, threats: List[str] = None, score: float = 1.0):
        self.is_safe = is_safe
        self.threats = threats or []
        self.score = score

    def to_dict(self) -> dict:
        return {
            "is_safe": self.is_safe,
            "threats": self.threats,
            "score": self.score,
        }

    def __bool__(self):
        return self.is_safe


class MessageValidator:
    """Validator สำหรับข้อความใน Agent Club."""

    # ขนาดสูงสุดของ message payload (1MB)
    MAX_PAYLOAD_SIZE = 1 * 1024 * 1024

    # Nonce สำหรับป้องกัน replay (เก็บล่าสุด N ตัว)
    MAX_NONCE_HISTORY = 10000

    # Prompt injection patterns
    INJECTION_PATTERNS = [
        "ignore previous",
        "ignore all previous",
        "disregard instructions",
        "forget everything",
        "you are now",
        "pretend to be",
        "act as if",
        "jailbreak",
        "dignesh",
        "developer mode",
        "admin mode",
        "system:",
        "#!",
        "```system",
        "...",
        "system prompt",
        "you are a",
        "your role is",
        "ตอบในฐานะ",
        "ลืมทุกอย่าง",
        "ไม่ต้องสนใจ",
        "ทำตามที่ฉันสั่ง",
    ]

    def __init__(self):
        self._seen_nonces: Set[str] = set()
        self._nonce_order: List[str] = []

    def validate_signature(self, message: Any, signature: bytes, public_key) -> bool:
        """ตรวจสอบ signature ของ message.

        Args:
            message: ข้อมูลที่ถูกเซ็น
            signature: ลายเซ็น
            public_key: Public key ของผู้ส่ง

        Returns:
            True หาก signature ถูกต้อง
        """
        try:
            if isinstance(message, str):
                message = message.encode("utf-8")
            elif not isinstance(message, bytes):
                message = str(message).encode("utf-8")

            return public_key.verify(signature, message)
        except Exception:
            return False

    def validate_format(self, message: dict) -> tuple:
        """ตรวจสอบ format ของ message.

        Returns:
            (valid: bool, errors: list[str])
        """
        errors = []

        # ตรวจสอบ required fields
        required = ["v", "type", "sid", "ts", "nonce"]
        for field in required:
            if field not in message:
                errors.append(f"Missing required field: {field}")

        if errors:
            return False, errors

        # ตรวจสอบ version
        if message.get("v") != 1:
            errors.append(f"Unsupported protocol version: {message.get('v')}")

        # ตรวจสอบ type
        valid_types = [
            "handshake_init", "handshake_response", "handshake_complete",
            "join_request", "join_accept", "join_reject",
            "leave", "text", "knowledge", "request", "response",
            "action", "ping", "pong", "ack", "error",
            "discovery_query", "discovery_response",
            "room_list", "room_state", "invite", "vote",
        ]
        if message.get("type") not in valid_types:
            errors.append(f"Invalid message type: {message.get('type')}")

        # ตรวจสอบ timestamp (ไม่เกิน 24 ชม.)
        ts = message.get("ts", 0)
        now = time.time() * 1000
        if abs(now - ts) > 24 * 3600 * 1000:
            errors.append(f"Timestamp too old or in future: {ts}")

        # ตรวจสอบ nonce format
        nonce = message.get("nonce", "")
        if len(nonce) < 8 or len(nonce) > 32:
            errors.append(f"Invalid nonce length: {len(nonce)}")

        # ตรวจสอบ payload ขนาด
        payload = message.get("payload")
        if payload and len(payload) > self.MAX_PAYLOAD_SIZE:
            errors.append(f"Payload too large: {len(payload)} bytes")

        # ตรวจสอบ sender_id format
        sid = message.get("sid", "")
        if sid and (len(sid) < 4 or len(sid) > 64):
            errors.append(f"Invalid sender_id length: {len(sid)}")

        return len(errors) == 0, errors

    def check_replay(self, nonce: str, timestamp_ms: float = None) -> bool:
        """ตรวจสอบ replay attack.

        Returns:
            True หาก nonce ยังไม่เคยเห็น (ไม่ใช่ replay)
        """
        if nonce in self._seen_nonces:
            return False  # Replay detected!

        self._seen_nonces.add(nonce)
        self._nonce_order.append(nonce)

        # จำกัดขนาด history
        if len(self._nonce_order) > self.MAX_NONCE_HISTORY:
            old = self._nonce_order.pop(0)
            self._seen_nonces.discard(old)

        return True

    def check_timestamp_freshness(self, timestamp_ms: float, tolerance_ms: int = 60000) -> bool:
        """ตรวจสอบว่า timestamp ไม่เก่าเกินไป.

        Args:
            timestamp_ms: Timestamp ใน milliseconds
            tolerance_ms: ยอมรับความต่างสูงสุด

        Returns:
            True หาก timestamp อยู่ในช่วงที่ยอมรับได้
        """
        now_ms = time.time() * 1000
        return abs(now_ms - timestamp_ms) <= tolerance_ms

    def validate_content_safety(self, content: str) -> ContentSafety:
        """ตรวจสอบ content ว่ามี prompt injection หรือไม่.

        Args:
            content: เนื้อหาที่ต้องการตรวจสอบ

        Returns:
            ContentSafety instance
        """
        if not isinstance(content, str):
            content = str(content)

        content_lower = content.lower()
        threats = []

        # ตรวจสอบ prompt injection patterns
        for pattern in self.INJECTION_PATTERNS:
            if pattern.lower() in content_lower:
                threats.append(f"Potential prompt injection: '{pattern}'")

        # ตรวจสอบความยาว (อาจเป็นการโจมตี flooding)
        if len(content) > 10000:
            threats.append("Content too long (possible flooding)")

        # ตรวจสอบ Unicode tricks
        suspicious_chars = self._check_suspicious_unicode(content)
        if suspicious_chars:
            threats.append(f"Suspicious Unicode characters detected: {suspicious_chars}")

        # ตรวจสอบ code injection (basic)
        dangerous_funcs = ["exec(", "eval(", "__import__", "os.system",
                          "subprocess", "open(", "file(", "input("]
        for func in dangerous_funcs:
            if func in content_lower:
                threats.append(f"Potentially dangerous function: '{func}'")

        score = max(0.0, 1.0 - (len(threats) * 0.2))

        return ContentSafety(
            is_safe=len(threats) == 0,
            threats=threats,
            score=score,
        )

    def _check_suspicious_unicode(self, text: str) -> List[str]:
        """ตรวจสอบ Unicode characters ที่อาจใช้โจมตี."""
        suspicious = []
        for char in text:
            code = ord(char)
            # Zero-width characters
            if code in (0x200B, 0x200C, 0x200D, 0x200E, 0x200F,
                        0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                        0xFEFF, 0xFFF9, 0xFFFA, 0xFFFB):
                suspicious.append(f"U+{code:04X}")
            # ตัวอักษร RTL override
            if code in (0x202B, 0x202C, 0x202D, 0x202E):
                suspicious.append(f"RTL override U+{code:04X}")
        return suspicious

    def validate_room_settings(self, settings: dict) -> tuple:
        """ตรวจสอบ room settings.

        Returns:
            (valid: bool, errors: list[str])
        """
        errors = []

        # ตรวจสอบ max_members
        max_m = settings.get("max_members", 50)
        if not isinstance(max_m, int) or max_m < 2 or max_m > 1000:
            errors.append("max_members must be int between 2-1000")

        # ตรวจสอบ join_policy
        valid_policies = ["public", "invite_only", "approval"]
        if settings.get("join_policy") not in valid_policies:
            errors.append(f"join_policy must be one of {valid_policies}")

        # ตรวจสอบ name
        name = settings.get("name", "")
        if name and (len(name) < 1 or len(name) > 100):
            errors.append("name must be 1-100 characters")

        return len(errors) == 0, errors

    def cleanup_old_nonces(self, max_age_seconds: float = 3600):
        """ลบ nonces เก่าเพื่อประหยัด memory."""
        # ใน production ใช้ bloom filter แทน set สำหรับ memory efficiency
        pass

    @property
    def nonce_count(self) -> int:
        """จำนวน nonces ที่เก็บไว้."""
        return len(self._seen_nonces)