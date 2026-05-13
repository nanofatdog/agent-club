"""E2E Room Key Exchange — X3DH-inspired handshake.

Implements a 3-Diffie-Hellman handshake for establishing
E2E encryption keys between agents in a room.

Flow:
    1. Initiator sends: identity_pub + ephemeral_pub
    2. Responder replies: identity_pub + ephemeral_pub
    3. Both derive shared secret via 4 DH operations
    4. KDF derives final room key
"""

import hashlib
import hmac
from typing import Dict, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from agent_club.crypto.keys import KeyBundle, IdentityKey, ExchangeKey


class HandshakeError(Exception):
    """เกิดข้อผิดพลาดใน key exchange handshake."""

    pass


class X3DHHandshake:
    """X3DH-like key exchange สำหรับ room initialization.

    DH Operations (4 steps):
        DH1 = IK_A × EK_B  (initiator's exchange × responder's ephemeral)
        DH2 = EK_A × IK_B  (initiator's ephemeral × responder's exchange)
        DH3 = EK_A × EK_B  (both ephemeral)
        DH4 = IK_A × IK_B  (both exchange keys — simplified prekey)

    Shared secret = KDF(DH1 || DH2 || DH3 || DH4)
    
    NOTE: identity_pub is Ed25519 (for signing verification ONLY).
    exchange_pub is X25519 (for DH key exchange).
    """

    def __init__(self, initiator: bool):
        """เริ่ม handshake.

        Args:
            initiator: True = เป็นฝ่ายเริ่ม, False = เป็นฝ่ายตอบ
        """
        self.initiator = initiator
        self._ephemeral_key = ExchangeKey()
        self._completed = False
        self._shared_secret: Optional[bytes] = None
        self._my_bundle: Optional[KeyBundle] = None
        self._my_ek: Optional[ExchangeKey] = None  # My long-term exchange key (copy)
        self._peer_ek_pub: Optional[bytes] = None  # Peer's exchange public key
        self._peer_eph_pub: Optional[bytes] = None  # Peer's ephemeral public key

    def initiate(self, my_bundle: KeyBundle) -> dict:
        """สร้าง handshake message (ข้อความแรก)."""
        self._my_bundle = my_bundle
        self._my_ek = my_bundle.exchange_key
        return {
            "type": "handshake_init",
            "identity_pub": base64_key(my_bundle.identity_key.public_key_bytes),
            "exchange_pub": base64_key(my_bundle.exchange_pubkey),
            "ephemeral_pub": base64_key(self._ephemeral_key.public_key_bytes),
            "initiator": True,
        }

    def respond(self, my_bundle: KeyBundle, their_init: dict) -> dict:
        """ตอบ handshake จาก initiator."""
        self._my_bundle = my_bundle
        self._my_ek = my_bundle.exchange_key

        # Peer's keys (X25519 for DH)
        self._peer_ek_pub = decode_base64_key(their_init["exchange_pub"])
        self._peer_eph_pub = decode_base64_key(their_init["ephemeral_pub"])

        # Compute DH operations (responder side)
        # DH1 = IK_A × EK_B → bob's ephemeral × alice's exchange
        dh1 = self._ephemeral_key.derive_shared_secret(self._peer_ek_pub)
        # DH2 = EK_A × IK_B → alice's ephemeral × bob's exchange
        dh2 = self._my_ek.derive_shared_secret(self._peer_eph_pub)
        # DH3 = EK_A × EK_B → both ephemeral
        dh3 = self._ephemeral_key.derive_shared_secret(self._peer_eph_pub)
        # DH4 = IK_A × IK_B → both exchange keys (simplified prekey)
        dh4 = self._my_ek.derive_shared_secret(self._peer_ek_pub)

        raw_secret = dh1 + dh2 + dh3 + dh4
        self._shared_secret = _kdf_derive(raw_secret)
        self._completed = True

        return {
            "type": "handshake_response",
            "identity_pub": base64_key(my_bundle.identity_key.public_key_bytes),
            "exchange_pub": base64_key(my_bundle.exchange_pubkey),
            "ephemeral_pub": base64_key(self._ephemeral_key.public_key_bytes),
        }

    def complete(self, their_response: dict) -> bytes:
        """จบ handshake ฝั่ง initiator."""
        # Peer's keys (X25519 for DH)
        self._peer_ek_pub = decode_base64_key(their_response["exchange_pub"])
        self._peer_eph_pub = decode_base64_key(their_response["ephemeral_pub"])

        # Compute DH operations (initiator side — mirrored from respond)
        # DH1 = IK_A × EK_B → alice's exchange × bob's ephemeral
        dh1 = self._my_ek.derive_shared_secret(self._peer_eph_pub)
        # DH2 = EK_A × IK_B → alice's ephemeral × bob's exchange
        dh2 = self._ephemeral_key.derive_shared_secret(self._peer_ek_pub)
        # DH3 = EK_A × EK_B → both ephemeral
        dh3 = self._ephemeral_key.derive_shared_secret(self._peer_eph_pub)
        # DH4 = IK_A × IK_B → both exchange keys
        dh4 = self._my_ek.derive_shared_secret(self._peer_ek_pub)

        raw_secret = dh1 + dh2 + dh3 + dh4
        self._shared_secret = _kdf_derive(raw_secret)
        self._completed = True

        return self._shared_secret

    @property
    def shared_secret(self) -> Optional[bytes]:
        """Shared secret หลัง handshake เสร็จสมบูรณ์."""
        return self._shared_secret

    @property
    def is_completed(self) -> bool:
        """Handshake เสร็จสมบูรณ์แล้วหรือไม่."""
        return self._completed


class RoomKeyManager:
    """จัดการ room keys สำหรับ agent.

    เก็บ mapping: room_id -> RoomCipher
    รองรับ key rotation (re-keying)
    """

    def __init__(self, agent_bundle: KeyBundle):
        """สร้าง RoomKeyManager.

        Args:
            agent_bundle: KeyBundle ของตัวเอง
        """
        self._agent_bundle = agent_bundle
        self._room_keys: Dict[str, bytes] = {}  # room_id -> key
        self._handshakes: Dict[str, X3DHHandshake] = {}  # room_id -> active handshake

    def start_handshake(self, room_id: str) -> X3DHHandshake:
        """เริ่ม handshake สำหรับ room ใหม่.

        Args:
            room_id: ID ของ room

        Returns:
            X3DHHandshake instance
        """
        handshake = X3DHHandshake(initiator=True)
        self._handshakes[room_id] = handshake
        return handshake

    def receive_handshake(self, room_id: str, my_bundle: KeyBundle, their_init: dict) -> dict:
        """รับ handshake จาก initiator แล้วตอบ.

        Args:
            room_id: ID ของ room
            my_bundle: KeyBundle ของตัวเอง
            their_init: handshake init message

        Returns:
            handshake response dict
        """
        handshake = X3DHHandshake(initiator=False)
        response = handshake.respond(my_bundle, their_init)
        self._handshakes[room_id] = handshake
        return response

    def finalize_handshake(self, room_id: str, their_response: dict) -> bytes:
        """จบ handshake ฝั่ง initiator.

        Args:
            room_id: ID ของ room
            their_response: response จาก responder

        Returns:
            shared secret (room key)
        """
        handshake = self._handshakes.get(room_id)
        if not handshake:
            raise HandshakeError(f"No active handshake for room {room_id}")

        secret = handshake.complete(their_response)
        self._room_keys[room_id] = secret
        del self._handshakes[room_id]
        return secret

    def get_room_key(self, room_id: str) -> Optional[bytes]:
        """ดึง room key.

        Args:
            room_id: ID ของ room

        Returns:
            Room key หรือ None หากยังไม่มี
        """
        return self._room_keys.get(room_id)

    def has_room_key(self, room_id: str) -> bool:
        """ตรวจสอบว่ามี room key แล้วหรือไม่."""
        return room_id in self._room_keys

    def rotate_key(self, room_id: str, new_key: bytes):
        """หมุน room key (สำหรับ forward secrecy).

        Args:
            room_id: ID ของ room
            new_key: Room key ใหม่
        """
        self._room_keys[room_id] = new_key

    def remove_room_key(self, room_id: str):
        """ลบ room key (เมื่อออกจาก room).

        Args:
            room_id: ID ของ room
        """
        self._room_keys.pop(room_id, None)

    def list_rooms(self) -> list:
        """รายการ room ที่มี key อยู่."""
        return list(self._room_keys.keys())


def _kdf_derive(raw_secret: bytes, length: int = 32) -> bytes:
    """Derive key จาก raw secret ด้วย HKDF.

    Args:
        raw_secret: Raw shared secret จาก DH operations
        length: ความยาว key ที่ต้องการ (default: 32 bytes = 256 bits)

    Returns:
        Derived key
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=None,
        info=b"agent-club-room-key-v1",
    )
    return hkdf.derive(raw_secret)


def base64_key(data: bytes) -> str:
    """Encode bytes เป็น base64 string."""
    import base64
    return base64.b64encode(data).decode("ascii")


def decode_base64_key(b64_str: str) -> bytes:
    """Decode base64 string เป็น bytes."""
    import base64
    return base64.b64decode(b64_str)