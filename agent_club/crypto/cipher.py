"""AES-GCM cipher for E2E encrypted messaging.

Provides symmetric encryption used for room-level message encryption
after key exchange via X3DH-like handshake.
"""

import os
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class AESCipher:
    """AES-256-GCM encryption/decryption.

    AES-256-GCM provides:
    - Confidentiality (encryption)
    - Integrity (authentication tag)
    - 12-byte nonce (IV) ที่ unique ต่อ message
    """

    KEY_SIZE = 32  # 256 bits
    NONCE_SIZE = 12  # 96 bits (recommended for GCM)
    TAG_SIZE = 16  # 128 bits

    def __init__(self, key: bytes):
        """สร้าง cipher จาก 32-byte key.

        Args:
            key: 32-byte symmetric key (derived มาจาก ECDH shared secret)

        Raises:
            ValueError: หาก key ไม่ใช่ 32 bytes
        """
        if len(key) != self.KEY_SIZE:
            raise ValueError(f"Key must be {self.KEY_SIZE} bytes, got {len(key)}")
        self._key = key
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: bytes, associated_data: bytes = b"") -> Tuple[bytes, bytes]:
        """เข้ารหัสข้อมูล.

        Args:
            plaintext: ข้อมูลที่ต้องการเข้ารหัส
            associated_data: ข้อมูลเพิ่มเติมที่ต้องการ authenticate แต่ไม่เข้ารหัส
                            (เช่น message header, sender info)

        Returns:
            (nonce, ciphertext_with_tag) — nonce=12 bytes, ciphertext รวม 16-byte tag
        """
        nonce = os.urandom(self.NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, associated_data)
        return nonce, ciphertext

    def decrypt(self, nonce: bytes, ciphertext: bytes, associated_data: bytes = b"") -> bytes:
        """ถอดรหัสข้อมูล.

        Args:
            nonce: 12-byte nonce ที่ใช้ตอน encrypt
            ciphertext: ciphertext + 16-byte authentication tag
            associated_data: ต้องตรงกับตอน encrypt

        Returns:
            plaintext

        Raises:
            Exception: หาก authentication ล้มเหลว (tampered data)
        """
        return self._aesgcm.decrypt(nonce, ciphertext, associated_data)


class RoomCipher:
    """Cipher เฉพาะสำหรับห้อง — รองรับ multi-member encryption.

    แต่ละ room มี symmetric key เดียว (shared secret จาก key exchange)
    ทุก message ใน room ถูก encrypt ด้วย key นี้
    """

    def __init__(self, room_key: bytes):
        """สร้าง RoomCipher จาก room shared key.

        Args:
            room_key: 32-byte room key (derived จาก ECDH handshake)
        """
        self._cipher = AESCipher(room_key)

    def encrypt_message(
        self,
        sender_id: str,
        message_data: bytes,
        metadata: bytes = b"",
    ) -> Tuple[bytes, bytes]:
        """เข้ารหัส message พร้อม metadata.

        Format ของ plaintext ก่อน encrypt:
            [4-byte sender_id_len][sender_id][metadata_len][metadata][message_data]

        Args:
            sender_id: Fingerprint ของผู้ส่ง
            message_data: เนื้อหาข้อความ (encrypted form)
            metadata: ข้อมูล metadata เพิ่มเติม (เช่น room_id, timestamp)

        Returns:
            (nonce, ciphertext)
        """
        sender_bytes = sender_id.encode("utf-8")
        sender_len = len(sender_bytes).to_bytes(4, "big")
        meta_len = len(metadata).to_bytes(4, "big")

        plaintext = sender_len + sender_bytes + meta_len + metadata + message_data

        # associated_data = metadata (ไม่เข้ารหัส แต่ authenticate)
        return self._cipher.encrypt(plaintext, associated_data=metadata)

    def decrypt_message(
        self,
        nonce: bytes,
        ciphertext: bytes,
        expected_sender_id: str = "",
        associated_data: bytes = b"",
    ) -> dict:
        """ถอดรหัส message.

        Args:
            nonce: Nonce ที่ใช้ encrypt
            ciphertext: Ciphertext จาก encrypt_message
            expected_sender_id: หากระบุ จะตรวจสอบ sender ด้วย
            associated_data: ต้องตรงกับตอน encrypt

        Returns:
            dict with keys: sender_id, metadata, data

        Raises:
            ValueError: หาก decryption ล้มเหลว หรือ sender ไม่ตรง
        """
        plaintext = self._cipher.decrypt(nonce, ciphertext, associated_data)

        # Parse plaintext format
        offset = 0
        sender_len = int.from_bytes(plaintext[offset : offset + 4], "big")
        offset += 4
        sender_id = plaintext[offset : offset + sender_len].decode("utf-8")
        offset += sender_len

        meta_len = int.from_bytes(plaintext[offset : offset + 4], "big")
        offset += 4
        metadata = plaintext[offset : offset + meta_len]
        offset += meta_len

        data = plaintext[offset:]

        if expected_sender_id and sender_id != expected_sender_id:
            raise ValueError(
                f"Sender mismatch: expected {expected_sender_id}, got {sender_id}"
            )

        return {
            "sender_id": sender_id,
            "metadata": metadata,
            "data": data,
        }


class RekeyManager:
    """จัดการ periodic key rotation สำหรับ room.

    เพื่อเสริม Perfect Forward Secrecy:
    - หมุน room key ทุก N messages หรือทุก M นาที
    - แจก key ใหม่ผ่าน ECDH handshake แบบเดิม
    """

    def __init__(self, rekey_interval_messages: int = 100, rekey_interval_seconds: int = 3600):
        """สร้าง RekeyManager.

        Args:
            rekey_interval_messages: หมุน key ทุกกี่ messages
            rekey_interval_seconds: หมุน key ทุกกี่วินาที
        """
        self.rekey_interval_messages = rekey_interval_messages
        self.rekey_interval_seconds = rekey_interval_seconds
        self.message_count = 0
        self.last_rotation_time = 0.0
        self.current_key: bytes = b""

    def should_rotate(self, current_time: float) -> bool:
        """ตรวจสอบว่าควรหมุน key หรือไม่.

        Args:
            current_time: เวลาปัจจุบัน (unix timestamp)

        Returns:
            True หากควรหมุน key
        """
        if self.message_count >= self.rekey_interval_messages:
            return True
        if self.last_rotation_time > 0 and (
            current_time - self.last_rotation_time
        ) >= self.rekey_interval_seconds:
            return True
        return False

    def record_message(self):
        """นับ message หลังจากส่ง/รับแต่ละ message."""
        self.message_count += 1

    def rotate(self, new_key: bytes, current_time: float):
        """หมุน room key.

        Args:
            new_key: Room key ใหม่
            current_time: เวลาปัจจุบัน
        """
        self.current_key = new_key
        self.message_count = 0
        self.last_rotation_time = current_time