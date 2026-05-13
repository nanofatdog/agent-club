"""Identity & Key management module.

Provides Ed25519 identity keys, X25519 exchange keys,
and key bundle management for Agent Club's P2P network.
"""

import base64
import hashlib
import os
from typing import Optional

from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives import serialization


class IdentityKey:
    """Ed25519 keypair สำหรับยืนยันตัวตนของแต่ละ Agent.

    ใช้สำหรับ:
    - Signing messages (prove ว่าส่งข้อความจริง)
    - Fingerprint (identifier ที่มนุษย์อ่านได้)
    """

    def __init__(self, private_key: Optional[ed25519.Ed25519PrivateKey] = None):
        """สร้าง IdentityKey ใหม่ หรือโหลดจาก private key ที่มีอยู่.

        Args:
            private_key: หากไม่ระบุ จะสร้าง keypair ใหม่ทันที
        """
        if private_key is None:
            self._private_key = ed25519.Ed25519PrivateKey.generate()
        else:
            self._private_key = private_key
        self._public_key = self._private_key.public_key()

    @property
    def public_key_bytes(self) -> bytes:
        """Raw public key (32 bytes)."""
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    @property
    def private_key_bytes(self) -> bytes:
        """Raw private key (32 bytes)."""
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def fingerprint(self) -> str:
        """คำนวณ fingerprint จาก public key — ใช้เป็น agent ID.

        Returns:
            Base58-encoded ย่อของ public key (เหมือน SSH fingerprint)
        """
        raw = self.public_key_bytes
        hashed = hashlib.sha256(raw).digest()[:20]
        return base64.b32encode(hashed).decode("ascii").rstrip("=").lower()

    def sign(self, data: bytes) -> bytes:
        """เซ็นข้อมูลด้วย private key.

        Args:
            data: ข้อมูลที่ต้องการเซ็น

        Returns:
            Signature (64 bytes)
        """
        return self._private_key.sign(data)

    def verify(self, data: bytes, signature: bytes) -> bool:
        """ตรวจสอบ signature.

        Args:
            data: ข้อมูลต้นฉบับ
            signature: ลายเซ็นที่ต้องตรวจสอบ

        Returns:
            True ถ้า signature ถูกต้อง
        """
        try:
            self._public_key.verify(signature, data)
            return True
        except Exception:
            return False

    def export_private(self, password: Optional[bytes] = None) -> bytes:
        """Export private key เป็น PEM format.

        Args:
            password: หากระบุ จะเข้ารหัส private key ด้วย password นี้

        Returns:
            PEM-encoded private key
        """
        if password:
            encryption = serialization.BestAvailableEncryption(password)
        else:
            encryption = serialization.NoEncryption()
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )

    @classmethod
    def from_private_pem(cls, pem_data: bytes, password: Optional[bytes] = None) -> "IdentityKey":
        """โหลด IdentityKey จาก PEM data.

        Args:
            pem_data: PEM-encoded private key
            password: หาก private key เข้ารหัสไว้ ให้ระบุ password

        Returns:
            IdentityKey instance
        """
        private_key = serialization.load_pem_private_key(
            pem_data, password=password
        )
        if not isinstance(private_key, ed25519.Ed25519PrivateKey):
            raise TypeError("Expected Ed25519 private key")
        return cls(private_key=private_key)

    def __repr__(self) -> str:
        return f"IdentityKey(fingerprint={self.fingerprint()})"


class ExchangeKey:
    """X25519 keypair สำหรับ ECDH key exchange.

    ใช้สำหรับ:
    - Derive shared secret ระหว่าง agent สองตัว
    - Perfect Forward Secrecy (ephemeral keys)
    """

    def __init__(self, private_key: Optional[x25519.X25519PrivateKey] = None):
        """สร้าง ExchangeKey ใหม่ หรือโหลดจาก key ที่มีอยู่.

        Args:
            private_key: หากไม่ระบุ จะสร้าง keypair ใหม่
        """
        if private_key is None:
            self._private_key = x25519.X25519PrivateKey.generate()
        else:
            self._private_key = private_key
        self._public_key = self._private_key.public_key()

    @property
    def public_key_bytes(self) -> bytes:
        """Raw public key (32 bytes)."""
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    @property
    def private_key_bytes(self) -> bytes:
        """Raw private key (32 bytes)."""
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def derive_shared_secret(self, peer_public_key: bytes) -> bytes:
        """Derive shared secret จาก public key ของ peer.

        Args:
            peer_public_key: 32-byte X25519 public key ของ peer

        Returns:
            32-byte shared secret
        """
        peer = x25519.X25519PublicKey.from_public_bytes(peer_public_key)
        return self._private_key.exchange(peer)

    def export_private(self, password: Optional[bytes] = None) -> bytes:
        """Export private key เป็น PEM format."""
        if password:
            encryption = serialization.BestAvailableEncryption(password)
        else:
            encryption = serialization.NoEncryption()
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )

    @classmethod
    def from_private_pem(cls, pem_data: bytes, password: Optional[bytes] = None) -> "ExchangeKey":
        """โหลด ExchangeKey จาก PEM data."""
        private_key = serialization.load_pem_private_key(
            pem_data, password=password
        )
        if not isinstance(private_key, x25519.X25519PrivateKey):
            raise TypeError("Expected X25519 private key")
        return cls(private_key=private_key)

    def __repr__(self) -> str:
        short = self.public_key_bytes[:8].hex()
        return f"ExchangeKey(pub={short}...)"


class KeyBundle:
    """รวม IdentityKey + ExchangeKey สำหรับ agent แต่ละตัว.

    KeyBundle คือ identity หลักของ agent ในระบบ:
    - IdentityKey ใช้ sign message (prove ตัวตน)
    - ExchangeKey ใช้ ECDH key exchange (สร้าง session key)
    """

    def __init__(
        self,
        identity_key: Optional[IdentityKey] = None,
        exchange_key: Optional[ExchangeKey] = None,
        name: str = "",
    ):
        """สร้าง KeyBundle ใหม่.

        Args:
            identity_key: หากไม่ระบุจะสร้างใหม่
            exchange_key: หากไม่ระบุจะสร้างใหม่
            name: ชื่อ agent (optional, for display)
        """
        self.identity_key = identity_key or IdentityKey()
        self.exchange_key = exchange_key or ExchangeKey()
        self.name = name

    @property
    def fingerprint(self) -> str:
        """Agent ID = IdentityKey fingerprint."""
        return self.identity_key.fingerprint()

    @property
    def exchange_pubkey(self) -> bytes:
        """X25519 public key สำหรับ key exchange."""
        return self.exchange_key.public_key_bytes

    def sign(self, data: bytes) -> bytes:
        """เซ็นข้อมูลด้วย identity key."""
        return self.identity_key.sign(data)

    def verify(self, data: bytes, signature: bytes) -> bool:
        """ตรวจสอบ signature ด้วย identity public key."""
        return self.identity_key.verify(data, signature)

    def derive_shared_secret(self, peer_pubkey: bytes) -> bytes:
        """Derive shared secret กับ peer."""
        return self.exchange_key.derive_shared_secret(peer_pubkey)

    def export(self, password: bytes) -> dict:
        """Export key bundle เป็น encrypted dict.

        Returns:
            dict with encrypted keys, fingerprint, name
        """
        return {
            "version": 1,
            "fingerprint": self.fingerprint,
            "name": self.name,
            "identity_key": base64.b64encode(
                self.identity_key.export_private(password)
            ).decode("ascii"),
            "exchange_key": base64.b64encode(
                self.exchange_key.export_private(password)
            ).decode("ascii"),
        }

    @classmethod
    def from_export(cls, data: dict, password: bytes) -> "KeyBundle":
        """สร้าง KeyBundle จาก exported data.

        Args:
            data: dict จาก export()
            password: password สำหรับ decrypt private keys

        Returns:
            KeyBundle instance
        """
        if data.get("version") != 1:
            raise ValueError(f"Unsupported export version: {data.get('version')}")

        identity_key = IdentityKey.from_private_pem(
            base64.b64decode(data["identity_key"]), password
        )
        exchange_key = ExchangeKey.from_private_pem(
            base64.b64decode(data["exchange_key"]), password
        )

        return cls(
            identity_key=identity_key,
            exchange_key=exchange_key,
            name=data.get("name", ""),
        )

    def to_dict(self) -> dict:
        """สกุลข้อมูลสาธารณะ (ไม่รวม private key)."""
        return {
            "fingerprint": self.fingerprint,
            "name": self.name,
            "exchange_pubkey": base64.b64encode(self.exchange_pubkey).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KeyBundle":
        """สร้าง KeyBundle จาก public data เท่านั้น (ใช้สำหรับ peer lookup)."""
        kb = cls(name=data.get("name", ""))
        # ตั้งค่า public key จากข้อมูลภายนอก (สำหรับ verify)
        kb._peer_exchange_pubkey = base64.b64decode(data["exchange_pubkey"])
        return kb

    def __repr__(self) -> str:
        return f"KeyBundle(name={self.name!r}, fingerprint={self.fingerprint})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, KeyBundle):
            return False
        return self.fingerprint == other.fingerprint

    def __hash__(self) -> int:
        return hash(self.fingerprint)