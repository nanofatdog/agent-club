"""Cryptographic primitives for Agent Club.

Provides:
- IdentityKey: Ed25519 keypair for signing & identity
- ExchangeKey: X25519 keypair for ECDH key exchange
- KeyBundle: Combined identity + exchange key pair
- AESCipher: AES-256-GCM symmetric encryption
- RoomCipher: Room-level encryption with sender info
- RekeyManager: Periodic key rotation for forward secrecy
- MessageSigner: Sign & verify messages
- X3DHHandshake: 3-DH key exchange handshake
- RoomKeyManager: Manage room keys & key rotation
"""

from agent_club.crypto.keys import IdentityKey, ExchangeKey, KeyBundle
from agent_club.crypto.cipher import AESCipher, RoomCipher, RekeyManager
from agent_club.crypto.signature import MessageSigner, SignatureError
from agent_club.crypto.room_key import X3DHHandshake, RoomKeyManager, HandshakeError

__all__ = [
    "IdentityKey",
    "ExchangeKey",
    "KeyBundle",
    "AESCipher",
    "RoomCipher",
    "RekeyManager",
    "MessageSigner",
    "SignatureError",
    "X3DHHandshake",
    "RoomKeyManager",
    "HandshakeError",
]