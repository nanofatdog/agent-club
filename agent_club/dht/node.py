"""DHT Node implementation for Agent Club.

Implements a Kademlia DHT node that allows agents to discover
each other in a decentralized manner — no central server needed.
"""

import asyncio
import hashlib
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from agent_club.dht.routing import (
    RoutingTable,
    PeerRecord,
    distance_to_int,
)
from agent_club.crypto.keys import KeyBundle


class DHTNode:
    """Kademlia DHT node สำหรับ Agent Club.

    แต่ละ agent จะรัน DHTNode หนึ่งตัว เพื่อ:
    - ค้นหา agent อื่นในเครือข่าย
    - ประกาศตัวเอง (พร้อม capabilities)
    - ค้นหาห้อง/บริการต่างๆ
    """

    # Protocol constants
    ALPHA = 3  # จำนวน parallel lookups
    K = 20  # bucket size
    ID_LENGTH = 20  # 160 bits (SHA-1)

    def __init__(
        self,
        local_bundle: KeyBundle,
        host: str = "0.0.0.0",
        port: int = 6881,
        bootstrap_nodes: list = None,
    ):
        """สร้าง DHTNode.

        Args:
            local_bundle: KeyBundle ของตัวเอง
            host: ที่อยู่ที่จะ listen
            port: พอร์ต DHT
            bootstrap_nodes: รายการ (host, port) ของ bootstrap nodes
        """
        self.local_bundle = local_bundle
        self.host = host
        self.port = port
        self.bootstrap_nodes = bootstrap_nodes or []

        # Node ID = hash ของ public key (160-bit)
        self.node_id = self._generate_node_id(local_bundle)

        # Routing table
        self.routing_table = RoutingTable(self.node_id, self.K)

        # Known services: key -> (value, timestamp)
        self._storage: Dict[str, Any] = {}

        # Active lookups
        self._active_lookups: Dict[str, asyncio.Task] = {}

        # Callbacks
        self._on_peer_found_callbacks: list = []
        self._on_service_announce_callbacks: list = []

        self._running = False
        self._server: Optional[asyncio.DatagramTransport] = None

    @staticmethod
    def _generate_node_id(bundle: KeyBundle) -> str:
        """สร้าง node ID จาก public key.

        Node ID = SHA1(identity_pubkey || exchange_pubkey)
        """
        data = bundle.identity_key.public_key_bytes + bundle.exchange_pubkey
        return hashlib.sha1(data).hexdigest()

    def on_peer_found(self, callback):
        """ลงทะเบียน callback เมื่อพบ peer ใหม่."""
        self._on_peer_found_callbacks.append(callback)

    def on_service_announce(self, callback):
        """ลงทะเบียน callback เมื่อมี service ประกาศตัว."""
        self._on_service_announce_callbacks.append(callback)

    async def start(self):
        """เริ่ม DHT node."""
        self._running = True

        # สร้าง UDP server
        loop = asyncio.get_event_loop()
        self._server = await loop.create_datagram_endpoint(
            lambda: DHTProtocol(self),
            local_addr=(self.host, self.port),
        )

        self._last_self_refresh = time.time()

        # Bootstrap
        if self.bootstrap_nodes:
            await self._bootstrap()

        # เริ่ม periodic refresh
        asyncio.ensure_future(self._periodic_refresh())

    async def stop(self):
        """หยุด DHT node."""
        self._running = False
        if self._server:
            self._server.close()

    async def _bootstrap(self):
        """Bootstrap กับ known nodes."""
        for host, port in self.bootstrap_nodes:
            self._send_ping(host, port)

    async def _periodic_refresh(self):
        """Refresh routing table ทุกๆ ช่วงเวลา."""
        while self._running:
            await asyncio.sleep(60)

            now = time.time()
            if now - self._last_self_refresh > 300:
                # Refresh buckets ที่ไม่มีกิจกรรมมานาน
                self._refresh_stale_buckets()
                self._last_self_refresh = now

    def _refresh_stale_buckets(self):
        """Refresh buckets ที่ยังไม่มีกิจกรรม."""
        for i, bucket in enumerate(self.routing_table._buckets):
            if bucket.empty or time.time() - bucket._last_updated > 300:
                # ส่ง random lookup เพื่อ refresh bucket
                random_id = hashlib.sha1(os.urandom(20)).hexdigest()
                asyncio.ensure_future(self.find_node(random_id))

    # ======== DHT Operations ========

    async def find_node(self, target_id: str) -> List[PeerRecord]:
        """ค้นหา peer ที่ใกล้ที่สุดกับ target ID.

        Args:
            target_id: Node ID ที่ต้องการค้นหา

        Returns:
            รายการ peer records ที่ใกล้ที่สุด
        """
        closest = self.routing_table.find_closest(target_id, self.ALPHA)

        # Iterative lookup
        contacted = set()
        while True:
            # ส่ง FIND_NODE ไปยัง Alpha peer ที่ยังไม่ติดต่อ
            to_contact = []
            for peer in closest:
                if peer.node_id not in contacted:
                    to_contact.append(peer)
                    contacted.add(peer.node_id)

            if not to_contact:
                break

            # Send parallel FIND_NODE requests
            for peer in to_contact[:self.ALPHA]:
                self._send_find_node(
                    peer.address[0], peer.address[1], target_id
                )

            # รอผล (simplified — ใน production ใช้ event/timeout)
            await asyncio.sleep(0.5)

            # Check for new closer peers
            new_closest = self.routing_table.find_closest(target_id, self.K)
            if new_closest == closest or len(new_closest) >= self.K:
                break
            closest = new_closest

        return closest

    async def find_value(self, key: str) -> Optional[Any]:
        """ค้นหา value จาก DHT.

        Args:
            key: คีย์ที่ต้องการค้นหา

        Returns:
            Value หากพบ, None ถ้าไม่พบ
        """
        # ตรวจสอบ local storage ก่อน
        if key in self._storage:
            return self._storage[key]

        # ค้นหาจาก network
        closest = await self.find_node(key)

        # ส่ง FIND_VALUE ไปยัง closest nodes
        for peer in closest[:self.ALPHA]:
            self._send_find_value(peer.address[0], peer.address[1], key)

        return None  # สำหรับ async สมบูรณ์ ต้องใช้ event/callback

    def store(self, key: str, value: Any, ttl: int = 3600):
        """เก็บ key-value ใน DHT (local storage).

        Args:
            key: คีย์
            value: ค่า
            ttl: Time-to-live (วินาที)
        """
        self._storage[key] = {
            "value": value,
            "timestamp": time.time(),
            "ttl": ttl,
        }

    def announce(
        self,
        service_id: str,
        capabilities: list = None,
        address: tuple = None,
    ):
        """ประกาศว่ามี service/agent อยู่.

        Args:
            service_id: ID ของ service
            capabilities: ความสามารถ
            address: ที่อยู่ (ใช้ค่า default ของตัวเอง)
        """
        addr = address or (self.host, self.port)
        self.routing_table.add_peer(service_id, addr, capabilities)

        # ประกาศไปยัง network
        self._send_announce(
            service_id, capabilities, addr
        )

    # ======== Message Sending ========

    def _send_ping(self, host: str, port: int):
        """ส่ง PING message."""
        msg = {
            "type": "ping",
            "node_id": self.node_id,
            "timestamp": time.time(),
        }
        self._send_raw(host, port, msg)

    def _send_find_node(self, host: str, port: int, target_id: str):
        """ส่ง FIND_NODE message."""
        msg = {
            "type": "find_node",
            "node_id": self.node_id,
            "target_id": target_id,
        }
        self._send_raw(host, port, msg)

    def _send_find_value(self, host: str, port: int, key: str):
        """ส่ง FIND_VALUE message."""
        msg = {
            "type": "find_value",
            "node_id": self.node_id,
            "key": key,
        }
        self._send_raw(host, port, msg)

    def _send_store(self, host: str, port: int, key: str, value: Any):
        """ส่ง STORE message."""
        msg = {
            "type": "store",
            "node_id": self.node_id,
            "key": key,
            "value": value,
        }
        self._send_raw(host, port, msg)

    def _send_announce(self, service_id: str, capabilities: list, address: tuple):
        """ส่ง ANNOUNCE message ไปยัง bootstrap nodes."""
        msg = {
            "type": "announce",
            "node_id": self.node_id,
            "service_id": service_id,
            "capabilities": capabilities,
            "address": address,
        }
        for host, port in self.bootstrap_nodes:
            self._send_raw(host, port, msg)

    def _send_raw(self, host: str, port: int, msg: dict):
        """ส่งข้อมูล raw ผ่าน UDP."""
        import json
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(
            json.dumps(msg).encode("utf-8"),
            (host, port),
        )
        sock.close()

    # ======== Message Handling ========

    def handle_ping(self, sender_id: str, sender_addr: tuple) -> dict:
        """จัดการ PING message.

        Returns:
            Response dict
        """
        # Add sender to routing table
        self.routing_table.add_peer(sender_id, sender_addr)
        return {"type": "pong", "node_id": self.node_id}

    def handle_find_node(self, target_id: str, sender_id: str, sender_addr: tuple) -> dict:
        """จัดการ FIND_NODE message.

        Returns:
            Response dict with closest peers
        """
        self.routing_table.add_peer(sender_id, sender_addr)

        closest = self.routing_table.find_closest(target_id, self.K)
        return {
            "type": "find_node_response",
            "node_id": self.node_id,
            "peers": [p.to_dict() for p in closest],
        }

    def handle_find_value(self, key: str, sender_id: str, sender_addr: tuple) -> dict:
        """จัดการ FIND_VALUE message.

        Returns:
            Response dict with value (ถ้ามี) หรือ closest peers
        """
        self.routing_table.add_peer(sender_id, sender_addr)

        if key in self._storage:
            entry = self._storage[key]
            if time.time() - entry["timestamp"] < entry["ttl"]:
                return {
                    "type": "find_value_response",
                    "node_id": self.node_id,
                    "value": entry["value"],
                    "found": True,
                }
            else:
                del self._storage[key]  # Expired

        # ไม่มีค่า — ส่ง closest peers แทน
        closest = self.routing_table.find_closest(key, self.K)
        return {
            "type": "find_value_response",
            "node_id": self.node_id,
            "peers": [p.to_dict() for p in closest],
            "found": False,
        }

    def handle_store(self, key: str, value: Any, sender_id: str, sender_addr: tuple):
        """จัดการ STORE message.

        เก็บ key-value หาก node ใกล้กับ key ที่สุด
        """
        self.routing_table.add_peer(sender_id, sender_addr)

        # เก็บถ้าใกล้ที่สุด (simplified — ใน production ต้อง verify)
        if self._should_store(key):
            self._storage[key] = {
                "value": value,
                "timestamp": time.time(),
                "ttl": 3600,
            }

    def _should_store(self, key: str) -> bool:
        """ตรวจสอบว่า node นี้ควรเก็บ key หรือไม่."""
        key_int = int(key[:8], 16) if len(key) >= 8 else 0
        node_int = int(self.node_id[:8], 16)
        closest = self.routing_table.find_closest(key, 1)

        if not closest:
            return True

        closest_id = closest[0].node_id
        closest_int = int(closest_id[:8], 16)

        return node_int <= closest_int

    def handle_announce(self, service_id: str, capabilities: list, address: tuple, sender_id: str):
        """จัดการ ANNOUNCE message."""
        self.routing_table.add_peer(service_id, address, capabilities)

        for cb in self._on_service_announce_callbacks:
            try:
                cb(service_id, capabilities, address)
            except Exception as e:
                pass  # Don't break on callback errors

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def peers_count(self) -> int:
        return self.routing_table.size