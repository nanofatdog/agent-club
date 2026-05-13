"""Network protocol definitions for Agent Club.

Defines the binary message format for P2P communication
between agents using MessagePack serialization.
"""

import time
import uuid
from typing import Any, Dict, Optional

import msgpack

from agent_club.crypto.signature import MessageSigner


PROTOCOL_VERSION = 1

# Message types
MSG_HANDSHAKE_INIT = "handshake_init"
MSG_HANDSHAKE_RESPONSE = "handshake_response"
MSG_HANDSHAKE_COMPLETE = "handshake_complete"
MSG_JOIN_REQUEST = "join_request"
MSG_JOIN_ACCEPT = "join_accept"
MSG_JOIN_REJECT = "join_reject"
MSG_LEAVE = "leave"
MSG_TEXT = "text"
MSG_KNOWLEDGE = "knowledge"
MSG_REQUEST = "request"
MSG_RESPONSE = "response"
MSG_ACTION = "action"
MSG_DISCOVERY_QUERY = "discovery_query"
MSG_DISCOVERY_RESPONSE = "discovery_response"
MSG_PING = "ping"
MSG_PONG = "pong"
MSG_ACK = "ack"
MSG_ERROR = "error"
MSG_ROOM_LIST = "room_list"
MSG_ROOM_STATE = "room_state"
MSG_VOTE = "vote"
MSG_INVITE = "invite"


class ProtocolMessage:
    """Base message format for Agent Club protocol.

    Binary format (MessagePack):
    {
        v: 1,                          # protocol version
        type: str,                     # message type
        sid: str,                      # sender fingerprint
        rid: str (optional),          # room ID
        ts: int,                       # timestamp (ms)
        nonce: str,                    # unique nonce (hex)
        payload: bytes (optional),    # encrypted or raw payload
        meta: dict (optional),        # metadata
        sig: bytes (optional),        # Ed25519 signature
        err: str (optional),          # error message
    }
    """

    def __init__(
        self,
        msg_type: str,
        sender_id: str,
        room_id: Optional[str] = None,
        payload: Optional[bytes] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[int] = None,
        nonce: Optional[str] = None,
        signature: Optional[bytes] = None,
        error: Optional[str] = None,
    ):
        """สร้าง ProtocolMessage.

        Args:
            msg_type: ประเภทข้อความ (MSG_* constants)
            sender_id: Fingerprint ของผู้ส่ง
            room_id: Room ID (หากมี)
            payload: เนื้อหาข้อความ
            metadata: ข้อมูลเพิ่มเติม
            timestamp: Unix timestamp (ms)
            nonce: Unique nonce สำหรับ anti-replay
            signature: ลายเซ็น
            error: ข้อความผิดพลาด (สำหรับ MSG_ERROR)
        """
        self.version = PROTOCOL_VERSION
        self.type = msg_type
        self.sender_id = sender_id
        self.room_id = room_id
        self.payload = payload
        self.metadata = metadata or {}
        self.timestamp = timestamp or int(time.time() * 1000)
        self.nonce = nonce or uuid.uuid4().hex[:16]
        self.signature = signature
        self.error = error

    def sign(self, signer_key) -> "ProtocolMessage":
        """เซ็น message ด้วย identity key.

        Args:
            signer_key: IdentityKey สำหรับเซ็น

        Returns:
            self (สำหรับการ chain)
        """
        sig_data = self._build_signable()
        self.signature = signer_key.sign(sig_data)
        return self

    def verify(self, public_key) -> bool:
        """ตรวจสอบ signature.

        Args:
            public_key: IdentityKey public key ของผู้ส่ง

        Returns:
            True ถ้า signature ถูกต้อง
        """
        if not self.signature:
            return False
        try:
            sig_data = self._build_signable()
            return public_key.verify(sig_data, self.signature)
        except Exception:
            return False

    def _build_signable(self) -> bytes:
        """สร้างข้อมูลที่จะเซ็น (ทุกอย่างยกเว้น signature)."""
        data = (
            str(self.version).encode()
            + self.type.encode("utf-8")
            + self.sender_id.encode("utf-8")
            + (self.room_id or "").encode("utf-8")
            + self.timestamp.to_bytes(8, "big")
            + self.nonce.encode("utf-8")
            + (self.payload or b"")
            + msgpack.packb(self.metadata, use_bin_type=True)
        )
        return data

    def pack(self) -> bytes:
        """ serialize เป็น MessagePack binary.

        Returns:
            MessagePack-encoded bytes
        """
        data = {
            "v": self.version,
            "type": self.type,
            "sid": self.sender_id,
            "ts": self.timestamp,
            "nonce": self.nonce,
        }
        if self.room_id:
            data["rid"] = self.room_id
        if self.payload:
            data["payload"] = self.payload
        if self.metadata:
            data["meta"] = self.metadata
        if self.signature:
            data["sig"] = self.signature
        if self.error:
            data["err"] = self.error

        return msgpack.packb(data, use_bin_type=True)

    @classmethod
    def unpack(cls, raw: bytes) -> "ProtocolMessage":
        """Deserialize จาก MessagePack binary.

        Args:
            raw: MessagePack-encoded bytes

        Returns:
            ProtocolMessage instance
        """
        data = msgpack.unpackb(raw, raw=False)
        return cls(
            msg_type=data.get("type", ""),
            sender_id=data.get("sid", ""),
            room_id=data.get("rid"),
            payload=data.get("payload"),
            metadata=data.get("meta"),
            timestamp=data.get("ts", 0),
            nonce=data.get("nonce", ""),
            signature=data.get("sig"),
            error=data.get("err"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """แปลงเป็น dict สำหรับ debug/logging."""
        return {
            "version": self.version,
            "type": self.type,
            "sender_id": self.sender_id,
            "room_id": self.room_id,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "has_payload": self.payload is not None,
            "payload_size": len(self.payload) if self.payload else 0,
            "has_signature": self.signature is not None,
            "error": self.error,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return f"ProtocolMessage(type={self.type}, sender={self.sender_id[:8]}..., room={self.room_id or 'N/A'})"


class MessageBuilder:
    """ช่วยสร้าง ProtocolMessage ได้ง่ายขึ้น."""

    def __init__(self, sender_id: str):
        self.sender_id = sender_id

    def handshake_init(self, room_id: str, payload: bytes) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_HANDSHAKE_INIT,
            sender_id=self.sender_id,
            room_id=room_id,
            payload=payload,
        )

    def handshake_response(self, room_id: str, payload: bytes) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_HANDSHAKE_RESPONSE,
            sender_id=self.sender_id,
            room_id=room_id,
            payload=payload,
        )

    def join_request(self, room_id: str, capabilities: list = None) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_JOIN_REQUEST,
            sender_id=self.sender_id,
            room_id=room_id,
            metadata={"capabilities": capabilities or []},
        )

    def join_accept(self, room_id: str, room_key_encrypted: bytes = None) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_JOIN_ACCEPT,
            sender_id=self.sender_id,
            room_id=room_id,
            payload=room_key_encrypted,
        )

    def join_reject(self, room_id: str, reason: str) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_JOIN_REJECT,
            sender_id=self.sender_id,
            room_id=room_id,
            error=reason,
        )

    def leave(self, room_id: str) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_LEAVE,
            sender_id=self.sender_id,
            room_id=room_id,
        )

    def text(self, room_id: str, text: str, encrypted: bool = True) -> ProtocolMessage:
        payload = text.encode("utf-8") if not encrypted else text.encode("utf-8")
        return ProtocolMessage(
            msg_type=MSG_TEXT,
            sender_id=self.sender_id,
            room_id=room_id,
            payload=payload,
            metadata={"encrypted": encrypted},
        )

    def knowledge(self, room_id: str, data: bytes, tags: list = None) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_KNOWLEDGE,
            sender_id=self.sender_id,
            room_id=room_id,
            payload=data,
            metadata={"tags": tags or []},
        )

    def request(self, room_id: str, request_type: str, query: str) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_REQUEST,
            sender_id=self.sender_id,
            room_id=room_id,
            metadata={"request_type": request_type, "query": query},
        )

    def response(self, room_id: str, request_nonce: str, data: bytes) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_RESPONSE,
            sender_id=self.sender_id,
            room_id=room_id,
            payload=data,
            metadata={"request_nonce": request_nonce},
        )

    def ping(self) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_PING,
            sender_id=self.sender_id,
        )

    def pong(self, original_nonce: str) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_PONG,
            sender_id=self.sender_id,
            metadata={"original_nonce": original_nonce},
        )

    def ack(self, original_nonce: str) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_ACK,
            sender_id=self.sender_id,
            metadata={"original_nonce": original_nonce},
        )

    def error(self, error_msg: str, original_type: str = "") -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_ERROR,
            sender_id=self.sender_id,
            error=error_msg,
            metadata={"original_type": original_type},
        )

    def discovery_query(self, query: str) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_DISCOVERY_QUERY,
            sender_id=self.sender_id,
            metadata={"query": query},
        )

    def discovery_response(self, results: list) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_DISCOVERY_RESPONSE,
            sender_id=self.sender_id,
            metadata={"results": results},
        )

    def room_list(self, rooms: list) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_ROOM_LIST,
            sender_id=self.sender_id,
            metadata={"rooms": rooms},
        )

    def room_state(self, room_id: str, state: dict) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_ROOM_STATE,
            sender_id=self.sender_id,
            room_id=room_id,
            metadata={"state": state},
        )

    def invite(self, room_id: str, target_id: str) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_INVITE,
            sender_id=self.sender_id,
            room_id=room_id,
            metadata={"target_id": target_id},
        )

    def vote(self, room_id: str, proposal_id: str, vote: str) -> ProtocolMessage:
        return ProtocolMessage(
            msg_type=MSG_VOTE,
            sender_id=self.sender_id,
            room_id=room_id,
            metadata={"proposal_id": proposal_id, "vote": vote},
        )