"""DHT protocol messages for Agent Club.

Message format สำหรับ DHT communication (ใช้ JSON สำหรับ simplicity
ใน DHT layer — binary ใช้ใน transport layer ข้างล่าง)
"""

import json
import time
from typing import Optional


class DHTProtocolMessage:
    """Base message format สำหรับ DHT communication."""

    PING = "ping"
    PONG = "pong"
    FIND_NODE = "find_node"
    FIND_NODE_RESPONSE = "find_node_response"
    FIND_VALUE = "find_value"
    FIND_VALUE_RESPONSE = "find_value_response"
    STORE = "store"
    STORE_ACK = "store_ack"
    ANNOUNCE = "announce"
    ANNOUNCE_ACK = "announce_ack"

    def __init__(self, msg_type: str, node_id: str, data: dict = None):
        self.type = msg_type
        self.node_id = node_id
        self.data = data or {}
        self.timestamp = time.time()

    def serialize(self) -> str:
        """Serialize เป็น JSON string."""
        return json.dumps({
            "type": self.type,
            "node_id": self.node_id,
            "data": self.data,
            "timestamp": self.timestamp,
        })

    @classmethod
    def deserialize(cls, raw: str) -> "DHTProtocolMessage":
        """Deserialize จาก JSON string."""
        data = json.loads(raw)
        msg = cls(
            msg_type=data.get("type", ""),
            node_id=data.get("node_id", ""),
            data=data.get("data", {}),
        )
        msg.timestamp = data.get("timestamp", time.time())
        return msg

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "node_id": self.node_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }


def build_ping(node_id: str) -> DHTProtocolMessage:
    """สร้าง PING message."""
    return DHTProtocolMessage(DHTProtocolMessage.PING, node_id)


def build_pong(node_id: str) -> DHTProtocolMessage:
    """สร้าง PONG message."""
    return DHTProtocolMessage(DHTProtocolMessage.PONG, node_id)


def build_find_node(node_id: str, target_id: str) -> DHTProtocolMessage:
    """สร้าง FIND_NODE message."""
    return DHTProtocolMessage(
        DHTProtocolMessage.FIND_NODE,
        node_id,
        {"target_id": target_id},
    )


def build_find_node_response(node_id: str, peers: list) -> DHTProtocolMessage:
    """สร้าง FIND_NODE_RESPONSE message."""
    return DHTProtocolMessage(
        DHTProtocolMessage.FIND_NODE_RESPONSE,
        node_id,
        {"peers": peers},
    )


def build_find_value(node_id: str, key: str) -> DHTProtocolMessage:
    """สร้าง FIND_VALUE message."""
    return DHTProtocolMessage(
        DHTProtocolMessage.FIND_VALUE,
        node_id,
        {"key": key},
    )


def build_find_value_response(
    node_id: str,
    found: bool,
    value: Optional[any] = None,
    peers: Optional[list] = None,
) -> DHTProtocolMessage:
    """สร้าง FIND_VALUE_RESPONSE message."""
    data = {"found": found}
    if found and value is not None:
        data["value"] = value
    if not found and peers:
        data["peers"] = peers
    return DHTProtocolMessage(
        DHTProtocolMessage.FIND_VALUE_RESPONSE, node_id, data
    )


def build_store(node_id: str, key: str, value: any) -> DHTProtocolMessage:
    """สร้าง STORE message."""
    return DHTProtocolMessage(
        DHTProtocolMessage.STORE,
        node_id,
        {"key": key, "value": value},
    )


def build_store_ack(node_id: str) -> DHTProtocolMessage:
    """สร้าง STORE_ACK message."""
    return DHTProtocolMessage(DHTProtocolMessage.STORE_ACK, node_id)


def build_announce(
    node_id: str, service_id: str, capabilities: list, address: tuple
) -> DHTProtocolMessage:
    """สร้าง ANNOUNCE message."""
    return DHTProtocolMessage(
        DHTProtocolMessage.ANNOUNCE,
        node_id,
        {
            "service_id": service_id,
            "capabilities": capabilities,
            "address": list(address),
        },
    )


def build_announce_ack(node_id: str) -> DHTProtocolMessage:
    """สร้าง ANNOUNCE_ACK message."""
    return DHTProtocolMessage(DHTProtocolMessage.ANNOUNCE_ACK, node_id)