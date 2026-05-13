"""Peer connection management for Agent Club.

Manages individual peer connections, handles connect/disconnect,
and maintains connection state.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional, Set

from agent_club.network.protocol import ProtocolMessage
from agent_club.crypto.keys import KeyBundle

logger = logging.getLogger(__name__)


class PeerInfo:
    """ข้อมูลของ peer แต่ละตัว."""

    def __init__(self, peer_id: str, capabilities: list = None, metadata: dict = None):
        self.peer_id = peer_id
        self.capabilities = capabilities or []
        self.metadata = metadata or {}
        self.connected_at = time.time()
        self.last_seen = time.time()
        self.messages_sent = 0
        self.messages_received = 0
        self.trust_score: float = 0.5  # เริ่มต้นที่ 0.5 (neutral)
        self.status: str = "online"  # online, offline, blocked

    def update_activity(self):
        """อัพเดต last_seen time."""
        self.last_seen = time.time()
        self.status = "online"

    def to_dict(self) -> dict:
        return {
            "peer_id": self.peer_id,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
            "connected_at": self.connected_at,
            "last_seen": self.last_seen,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "trust_score": self.trust_score,
            "status": self.status,
        }


class PeerManager:
    """จัดการ peer connections ทั้งหมด.

    หน้าที่:
    - ติดตาม connection ทั้งหมด
    - จัดการ reconnect logic
    - คำนวณ trust score ของ peer แต่ละตัว
    - บล็อก/แบน peer ที่มีพฤติกรรมผิดปกติ
    """

    def __init__(
        self,
        local_bundle: KeyBundle,
        max_connections: int = 100,
        reconnect_delay: float = 5.0,
        max_reconnect_attempts: int = 10,
    ):
        """สร้าง PeerManager.

        Args:
            local_bundle: KeyBundle ของตัวเอง
            max_connections: จำนวน connection สูงสุด
            reconnect_delay: เวลารอ reconnect (วินาที)
            max_reconnect_attempts: จำนวนครั้งสูงสุดที่จะ reconnect
        """
        self.local_bundle = local_bundle
        self.max_connections = max_connections
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts

        self._peers: Dict[str, PeerInfo] = {}
        self._pending_connections: Dict[str, asyncio.Task] = {}
        self._blocked_peers: Set[str] = set()
        self._on_connect_callbacks: list = []
        self._on_disconnect_callbacks: list = []
        self._logger = logging.getLogger(f"{__name__}.PeerManager")

    def register_on_connect(self, callback: Callable):
        """ลงทะเบียน callback เมื่อมี peer เชื่อมต่อ.

        Args:
            callback: ฟังก์ชันรับ (peer_id: str, peer_info: PeerInfo)
        """
        self._on_connect_callbacks.append(callback)

    def register_on_disconnect(self, callback: Callable):
        """ลงทะเบียน callback เมื่อ peer disconnect.

        Args:
            callback: ฟังก์ชันรับ (peer_id: str)
        """
        self._on_disconnect_callbacks.append(callback)

    def add_peer(self, peer_id: str, capabilities: list = None, metadata: dict = None) -> PeerInfo:
        """เพิ่ม peer ใหม่.

        Args:
            peer_id: Connection identifier
            capabilities: ความสามารถของ peer
            metadata: ข้อมูลเพิ่มเติม

        Returns:
            PeerInfo instance
        """
        if len(self._peers) >= self.max_connections:
            raise ConnectionError(f"Max connections ({self.max_connections}) reached")

        if peer_id in self._blocked_peers:
            raise ConnectionError(f"Peer {peer_id} is blocked")

        if peer_id in self._peers:
            # Update existing peer
            peer = self._peers[peer_id]
            if capabilities:
                peer.capabilities = capabilities
            if metadata:
                peer.metadata.update(metadata)
        else:
            peer = PeerInfo(peer_id, capabilities, metadata)
            self._peers[peer_id] = peer
            self._logger.info(f"New peer added: {peer_id}")

            # Notify callbacks
            for cb in self._on_connect_callbacks:
                try:
                    cb(peer_id, peer)
                except Exception as e:
                    self._logger.error(f"Error in on_connect callback: {e}")

        peer.update_activity()
        peer.status = "online"
        return peer

    def remove_peer(self, peer_id: str):
        """ลบ peer (เมื่อ disconnect).

        Args:
            peer_id: Connection identifier
        """
        if peer_id in self._peers:
            del self._peers[peer_id]
            self._logger.info(f"Peer removed: {peer_id}")

            for cb in self._on_disconnect_callbacks:
                try:
                    cb(peer_id)
                except Exception as e:
                    self._logger.error(f"Error in on_disconnect callback: {e}")

    def block_peer(self, peer_id: str, reason: str = ""):
        """บล็อก peer ไม่ให้เชื่อมต่อ.

        Args:
            peer_id: Connection identifier
            reason: เหตุผลในการบล็อก
        """
        self._blocked_peers.add(peer_id)
        if peer_id in self._peers:
            self._peers[peer_id].status = "blocked"
        self._logger.warning(f"Peer blocked: {peer_id}, reason: {reason}")

    def unblock_peer(self, peer_id: str):
        """ปลดบล็อก peer.

        Args:
            peer_id: Connection identifier
        """
        self._blocked_peers.discard(peer_id)
        if peer_id in self._peers:
            self._peers[peer_id].status = "online"

    def get_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """ดึงข้อมูล peer.

        Args:
            peer_id: Connection identifier

        Returns:
            PeerInfo หรือ None
        """
        return self._peers.get(peer_id)

    def find_peers_with_capability(self, capability: str) -> list:
        """ค้นหา peer ที่มีความสามารถที่ต้องการ.

        Args:
            capability: ความสามารถที่ต้องการค้นหา

        Returns:
            รายการ PeerInfo ที่มีความสามารถนั้น
        """
        return [
            peer for peer in self._peers.values()
            if capability in peer.capabilities and peer.status == "online"
        ]

    def record_message_sent(self, peer_id: str):
        """บันทึก message ที่ส่งไปยัง peer."""
        if peer_id in self._peers:
            self._peers[peer_id].messages_sent += 1
            self._peers[peer_id].update_activity()

    def record_message_received(self, peer_id: str):
        """บันทึก message ที่ได้รับจาก peer."""
        if peer_id in self._peers:
            self._peers[peer_id].messages_received += 1
            self._peers[peer_id].update_activity()

    def update_trust_score(self, peer_id: str, delta: float):
        """ปรับ trust score ของ peer.

        Args:
            peer_id: Connection identifier
            delta: ค่าที่จะเพิ่ม/ลด (สามารถเป็นลบได้)
        """
        if peer_id in self._peers:
            peer = self._peers[peer_id]
            peer.trust_score = max(0.0, min(1.0, peer.trust_score + delta))

            # Auto-block if trust too low
            if peer.trust_score < 0.1:
                self.block_peer(peer_id, "Trust score too low")

    def get_online_peers(self) -> Dict[str, PeerInfo]:
        """ดึง peer ที่ online อยู่."""
        return {
            pid: peer for pid, peer in self._peers.items()
            if peer.status == "online" and time.time() - peer.last_seen < 300
        }

    def cleanup_stale(self, timeout: float = 600):
        """ลบ peer ที่ไม่ได้เชื่อมต่อมานาน.

        Args:
            timeout: เวลาที่ไม่มีกิจกรรม (วินาที)
        """
        now = time.time()
        stale = [
            pid for pid, peer in self._peers.items()
            if now - peer.last_seen > timeout
        ]
        for pid in stale:
            self._peers[pid].status = "offline"
            self._logger.info(f"Peer marked offline: {pid}")

    def list_peers(self) -> Dict[str, dict]:
        """รายการ peer ทั้งหมด."""
        return {pid: peer.to_dict() for pid, peer in self._peers.items()}

    @property
    def peer_count(self) -> int:
        """จำนวน peer ทั้งหมด."""
        return len(self._peers)

    @property
    def online_count(self) -> int:
        """จำนวน peer ที่ online."""
        return len(self.get_online_peers())