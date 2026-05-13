"""Distributed Hash Table (DHT) for Agent Club.

Implements Kademlia-based DHT for decentralized agent discovery.
Agents can find each other without a central server.
"""

import hashlib
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from agent_club.crypto.keys import KeyBundle


def xor_distance(a: bytes, b: bytes) -> int:
    """คำนวณ XOR distance ระหว่างสอง ID.

    ใช้สำหรับ Kademlia routing — ยิ่งใกล้กันยิ่งมี bit เหมือนกัน
    """
    if len(a) != len(b):
        raise ValueError("IDs must be same length")
    result = 0
    for x, y in zip(a, b):
        result = (result << 8) | (x ^ y)
    return result


def distance_to_int(a_id: str, b_id: str) -> int:
    """คำนวณ distance ระหว่างสอง string IDs."""
    a_bytes = bytes.fromhex(a_id) if isinstance(a_id, str) else a_id
    b_bytes = bytes.fromhex(b_id) if isinstance(b_id, str) else b_id
    return xor_distance(a_bytes, b_bytes)


class KBucket:
    """K-Bucket สำหรับเก็บ peer info ใน Kademlia DHT.

    แต่ละ bucket เก็บ peer ที่มีระยะห่าง (distance) อยู่ในช่วงเดียวกัน
    - capacity: จำนวน peer สูงสุดต่อบักเก็ต (default: 20)
    """

    def __init__(self, range_min: int, range_max: int, k: int = 20):
        self.range_min = range_min
        self.range_max = range_max
        self.k = k
        self._peers: Dict[str, PeerRecord] = {}
        self._last_updated = time.time()

    def add_peer(self, node_id: str, address: tuple, capabilities: list = None) -> bool:
        """เพิ่ม peer เข้า bucket.

        Returns:
            True หากเพิ่มสำเร็จ, False หากเต็มแล้ว
        """
        if node_id in self._peers:
            # Update existing
            self._peers[node_id].last_seen = time.time()
            if address:
                self._peers[node_id].address = address
            if capabilities:
                self._peers[node_id].capabilities = capabilities
            return True

        if len(self._peers) >= self.k:
            return False  # Bucket full

        self._peers[node_id] = PeerRecord(node_id, address, capabilities)
        self._last_updated = time.time()
        return True

    def remove_peer(self, node_id: str):
        """ลบ peer ออกจาก bucket."""
        self._peers.pop(node_id, None)

    def get_peer(self, node_id: str) -> Optional["PeerRecord"]:
        """ดึง peer ตาม node_id."""
        return self._peers.get(node_id)

    def get_peers(self, count: int = None) -> List["PeerRecord"]:
        """ดึง peer หลายตัว (LRU order — most recently seen first)."""
        peers = sorted(
            self._peers.values(),
            key=lambda p: p.last_seen,
            reverse=True,
        )
        if count:
            peers = peers[:count]
        return peers

    def is_full(self) -> bool:
        """ตรวจสอบว่า bucket เต็มหรือไม่."""
        return len(self._peers) >= self.k

    @property
    def empty(self) -> bool:
        return len(self._peers) == 0

    def __len__(self) -> int:
        return len(self._peers)


class PeerRecord:
    """ข้อมูล peer ใน DHT."""

    def __init__(
        self,
        node_id: str,
        address: tuple,
        capabilities: list = None,
    ):
        self.node_id = node_id
        self.address = address  # (host, port)
        self.capabilities = capabilities or []
        self.last_seen = time.time()
        self.failed_rpcs = 0

    def mark_failed(self):
        """เพิ่มจำนวน failed RPC."""
        self.failed_rpcs += 1

    def mark_success(self):
        """รีเซ็ต failed RPC count."""
        self.failed_rpcs = 0

    def is_stale(self, timeout: float = 900) -> bool:
        """ตรวจสอบว่า peer stale แล้วหรือไม่."""
        return time.time() - self.last_seen > timeout

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "address": self.address,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen,
            "failed_rpcs": self.failed_rpcs,
        }


class RoutingTable:
    """Kademlia routing table สำหรับ DHT node.

    ประกอบด้วย 160 KBuckets (สำหรับ 160-bit keyspace)
    แต่ละ bucket เก็บ peers ที่มี bit prefix เหมือนกัน
    """

    def __init__(self, local_node_id: str, k: int = 20):
        self.local_node_id = local_node_id
        self.k = k
        self.num_buckets = 160  # SHA-1 = 160 bits
        self._buckets: List[KBucket] = [
            KBucket(2**i, 2 ** (i + 1), k) for i in range(self.num_buckets)
        ]

    def _get_bucket_index(self, node_id: str) -> int:
        """คำนวณ bucket index สำหรับ node ID.

        Bucket index = จำนวน leading zero bits ของ XOR distance
        """
        dist = distance_to_int(self.local_node_id, node_id)
        if dist == 0:
            return 0
        # หา bit length
        return dist.bit_length() - 1

    def add_peer(self, node_id: str, address: tuple, capabilities: list = None) -> bool:
        """เพิ่ม peer เข้า routing table."""
        if node_id == self.local_node_id:
            return False  # ไม่เพิ่มตัวเอง

        idx = self._get_bucket_index(node_id)
        bucket = self._buckets[idx]

        if bucket.add_peer(node_id, address, capabilities):
            return True

        # Bucket เต็ม — ต้อง ping oldest peer เพื่อเช็คว่ายัง alive อยู่
        # (simplified — จะ ping จริงใน production)
        return False

    def remove_peer(self, node_id: str):
        """ลบ peer ออกจาก routing table."""
        idx = self._get_bucket_index(node_id)
        self._buckets[idx].remove_peer(node_id)

    def find_closest(self, target_id: str, count: int = 8) -> List[PeerRecord]:
        """ค้นหา peer ที่ใกล้ที่สุดกับ target ID.

        ใช้ XOR distance metric — คืน peer ที่ใกล้ที่สุด count ตัว
        """
        all_peers = []
        for bucket in self._buckets:
            all_peers.extend(bucket.get_peers())

        # Sort by XOR distance to target
        all_peers.sort(
            key=lambda p: distance_to_int(p.node_id, target_id)
        )
        return all_peers[:count]

    def get_peers_for_capability(self, capability: str) -> List[PeerRecord]:
        """ค้นหา peer ที่มีความสามารถที่ต้องการ."""
        result = []
        for bucket in self._buckets:
            for peer in bucket.get_peers():
                if capability in peer.capabilities:
                    result.append(peer)
        return result

    def update_peer(self, node_id: str, address: tuple = None, success: bool = True):
        """Update peer status หลัง RPC สำเร็จ/ล้มเหลว.

        Args:
            node_id: peer ID
            address: ที่อยู่ใหม่ (ถ้ามี)
            success: RPC สำเร็จหรือไม่
        """
        idx = self._get_bucket_index(node_id)
        bucket = self._buckets[idx]
        peer = bucket.get_peer(node_id)

        if peer:
            if address:
                peer.address = address
            if success:
                peer.mark_success()
            else:
                peer.mark_failed()

    def refresh_bucket(self, bucket_index: int):
        """Refresh bucket โดย ping random peers."""
        bucket = self._buckets[bucket_index]
        # ใน production: ส่ง random key ใน bucket range แล้ว ping
        pass

    def get_all_peers(self) -> List[PeerRecord]:
        """ดึง peer ทั้งหมด."""
        all_peers = []
        for bucket in self._buckets:
            all_peers.extend(bucket.get_peers())
        return all_peers

    @property
    def size(self) -> int:
        """จำนวน peer ทั้งหมดใน routing table."""
        return sum(len(b) for b in self._buckets)

    def to_dict(self) -> dict:
        """แปลง routing table เป็น dict (สำหรับ debug/logging)."""
        return {
            "local_node_id": self.local_node_id,
            "num_buckets": self.num_buckets,
            "total_peers": self.size,
        }