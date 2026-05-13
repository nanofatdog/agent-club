"""Signature & signing utilities for message integrity.

All messages in Agent Club are signed with the sender's
IdentityKey to prove authenticity and prevent spoofing.
"""

import time
from typing import Optional

import hashlib


class SignatureError(Exception):
    """เกิดข้อผิดพลาดในการ verify signature."""

    pass


class MessageSigner:
    """เซ็นและตรวจสอบ signature สำหรับข้อความ.

    Signing Process:
        1. คำนวณ hash ของ message payload
        2. เซ็น hash ด้วย sender's IdentityKey (Ed25519)
        3. ติด signature ติดไปกับ message

    Verification:
        1. คำนวณ hash ของ message payload ใหม่
        2. verify hash ด้วย sender's public IdentityKey
    """

    @staticmethod
    def sign_message(signer_key, payload: bytes, context: bytes = b"") -> dict:
        """เซ็น message.

        Args:
            signer_key: IdentityKey ของผู้ส่ง
            payload: เนื้อหาที่ต้องการเซ็น (ยังไม่เข้ารหัส)
            context: ข้อมูล context เพิ่มเติม (เช่น room_id, timestamp)

        Returns:
            dict with: payload, signature, timestamp, context
        """
        timestamp = int(time.time() * 1000)  # millisecond precision
        data_to_sign = _build_signable(payload, timestamp, context)
        signature = signer_key.sign(data_to_sign)

        return {
            "payload": payload,
            "signature": signature,
            "timestamp": timestamp,
            "context": context,
            "signer_fingerprint": signer_key.fingerprint(),
        }

    @staticmethod
    def verify_message(verifier_key, signed_data: dict, tolerance_ms: int = 60000) -> bool:
        """Verify signature ของ message.

        Args:
            verifier_key: IdentityKey ของผู้ส่ง (สำหรับ verify)
            signed_data: dict จาก sign_message()
            tolerance_ms: ยอมรับ timestamp ที่ต่างจากปัจจุบันไม่เกิน N ms
                         (ป้องกัน replay attack)

        Returns:
            True หาก signature ถูกต้องและ timestamp ไม่ expired

        Raises:
            SignatureError: หาก verification ล้มเหลว
        """
        # 1. ตรวจสอบ timestamp (replay prevention)
        now_ms = int(time.time() * 1000)
        msg_time = signed_data.get("timestamp", 0)
        age_ms = abs(now_ms - msg_time)

        if age_ms > tolerance_ms:
            raise SignatureError(
                f"Message expired: age={age_ms}ms, tolerance={tolerance_ms}ms"
            )

        # 2. Rebuild signable data
        payload = signed_data["payload"]
        timestamp = signed_data["timestamp"]
        context = signed_data.get("context", b"")
        data_to_sign = _build_signable(payload, timestamp, context)

        # 3. Verify signature
        if not verifier_key.verify(data_to_sign, signed_data["signature"]):
            raise SignatureError("Signature verification failed")

        return True

    @staticmethod
    def sign_raw(key, data: bytes) -> bytes:
        """เซ็น raw data (ไม่มี timestamp/tolerance).

        ใช้สำหรับ: signing room keys, handshakes, protocol messages
        """
        return key.sign(data)

    @staticmethod
    def verify_raw(public_key, data: bytes, signature: bytes) -> bool:
        """Verify raw signature."""
        try:
            public_key.verify(signature, data)
            return True
        except Exception:
            return False


def _build_signable(payload: bytes, timestamp: int, context: bytes) -> bytes:
    """สร้างข้อมูลสำหรับเซ็น.

    Signable = SHA256(payload || timestamp || context)
    """
    hasher = hashlib.sha256()
    hasher.update(payload)
    hasher.update(timestamp.to_bytes(8, "big"))
    hasher.update(context)
    return hasher.digest()