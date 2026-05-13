"""WebSocket transport layer for Agent Club.

Handles all network communication between agents using WebSocket.
Supports clearnet connections and can be used alongside Tor transport.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Set

import websockets

from agent_club.network.protocol import ProtocolMessage

logger = logging.getLogger(__name__)


class ConnectionError(Exception):
    """เกิดข้อผิดพลาดในการเชื่อมต่อ."""

    pass


class WebSocketTransport:
    """WebSocket-based transport สำหรับ P2P communication.

    รองรับทั้ง server (รับ connection) และ client (เชื่อมต่อ)
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        """สร้าง WebSocketTransport.

        Args:
            host: ที่อยู่ที่จะ listen (default: ทุก interface)
            port: พอร์ตที่จะ listen
        """
        self.host = host
        self.port = port
        self._server: Optional[websockets.WebSocketServer] = None
        self._connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self._on_message_callback: Optional[Callable] = None
        self._running = False

    def on_message(self, callback: Callable):
        """ลงทะเบียน callback สำหรับรับข้อความ.

        Args:
            callback: ฟังก์ชันที่รับ ProtocolMessage
        """
        self._on_message_callback = callback

    async def start_server(self):
        """เริ่ม WebSocket server.

        Server จะรอรับ connection จาก agent อื่นๆ
        """
        self._running = True

        async def handle_connection(websocket, path):
            """จัดการ connection ใหม่."""
            peer_id = self._get_peer_id(websocket)
            self._connections[peer_id] = websocket
            logger.info(f"New connection: {peer_id}")

            try:
                async for raw_message in websocket:
                    if isinstance(raw_message, bytes):
                        await self._handle_binary(websocket, raw_message)
                    else:
                        logger.warning(f"Received non-binary message from {peer_id}")
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"Connection closed: {peer_id}")
            finally:
                self._connections.pop(peer_id, None)

        self._server = await websockets.serve(
            handle_connection,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10,
            max_size=10 * 1024 * 1024,  # 10MB max message
        )
        logger.info(f"WebSocket server started on {self.host}:{self.port}")

    async def stop_server(self):
        """หยุด WebSocket server."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("WebSocket server stopped")

    async def connect(self, uri: str) -> str:
        """เชื่อมต่อไปยัง WebSocket server.

        Args:
            uri: WebSocket URI (ws:// หรือ wss://)

        Returns:
            peer_id (connection identifier)
        """
        try:
            websocket = await websockets.connect(
                uri,
                ping_interval=30,
                ping_timeout=10,
                max_size=10 * 1024 * 1024,
            )
            peer_id = uri  # ใช้ URI เป็น peer ID
            self._connections[peer_id] = websocket
            logger.info(f"Connected to {uri}")
            return peer_id
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {uri}: {e}")

    async def send(self, peer_id: str, message: ProtocolMessage) -> bool:
        """ส่งข้อความไปยัง peer.

        Args:
            peer_id: Connection identifier
            message: ProtocolMessage ที่ต้องการส่ง

        Returns:
            True หากส่งสำเร็จ
        """
        if peer_id not in self._connections:
            raise ConnectionError(f"No connection to {peer_id}")

        raw = message.pack()
        websocket = self._connections[peer_id]

        try:
            await websocket.send(raw)
            return True
        except websockets.exceptions.ConnectionClosed:
            self._connections.pop(peer_id, None)
            raise ConnectionError(f"Connection to {peer_id} closed")

    async def broadcast(self, message: ProtocolMessage, exclude: Set[str] = None):
        """ส่งข้อความไปยัง peer ทั้งหมด.

        Args:
            message: ProtocolMessage ที่ต้องการส่ง
            exclude: เซ็ตของ peer_id ที่ไม่ต้องการส่งไป
        """
        exclude = exclude or set()
        raw = message.pack()

        for peer_id, websocket in self._connections.items():
            if peer_id in exclude:
                continue
            try:
                await websocket.send(raw)
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"Failed to send to {peer_id}: connection closed")

    async def _handle_binary(self, websocket, raw: bytes):
        """จัดการข้อความ binary ที่ได้รับ.

        Args:
            websocket: WebSocket connection
            raw: Raw bytes ที่ได้รับ
        """
        try:
            message = ProtocolMessage.unpack(raw)
            peer_id = self._get_peer_id(websocket)

            if self._on_message_callback:
                await self._on_message_callback(peer_id, message)
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _get_peer_id(self, websocket) -> str:
        """ดึง peer ID จาก WebSocket connection."""
        return websocket.remote_address[0] + ":" + str(websocket.remote_address[1])

    async def disconnect(self, peer_id: str):
        """ปิด connection กับ peer.

        Args:
            peer_id: Connection identifier
        """
        if peer_id in self._connections:
            websocket = self._connections.pop(peer_id)
            await websocket.close()
            logger.info(f"Disconnected from {peer_id}")

    def list_connections(self) -> list:
        """รายการทุก connection ที่ใช้งานอยู่."""
        return list(self._connections.keys())

    @property
    def is_running(self) -> bool:
        """ตรวจสอบว่า server กำลังทำงานอยู่หรือไม่."""
        return self._running


class RelayTransport:
    """Transport ผ่าน relay server สำหรับ NAT traversal.

    ใช้เมื่อ agent ไม่สามารถเชื่อมต่อโดยตรงได้
    (อยู่หลัง NAT หรือ firewall)
    """

    def __init__(self, relay_uri: str):
        """สร้าง RelayTransport.

        Args:
            relay_uri: URI ของ relay server
        """
        self.relay_uri = relay_uri
        self._transport = WebSocketTransport()
        self._relay_id: Optional[str] = None

    async def start(self):
        """เชื่อมต่อไปยัง relay server."""
        try:
            self._relay_id = await self._transport.connect(self.relay_uri)
            logger.info(f"Connected to relay: {self._relay_id}")
        except ConnectionError as e:
            logger.error(f"Failed to connect to relay: {e}")
            raise

    async def send_to_peer(self, target_id: str, message: ProtocolMessage):
        """ส่งข้อความไปยัง peer ผ่าน relay.

        Args:
            target_id: Peer ID ปลายทาง
            message: ProtocolMessage ที่ต้องการส่ง
        """
        if not self._relay_id:
            raise ConnectionError("Not connected to relay")

        # ส่งผ่าน relay ด้วย metadata ระบุปลายทาง
        relay_message = ProtocolMessage(
            msg_type="text",
            sender_id=self._transport.connections.get("self", ""),
            payload=message.pack(),
            metadata={"relay_target": target_id},
        )
        await self._transport.send(self._relay_id, relay_message)

    async def stop(self):
        """ปิด relay connection."""
        if self._transport.is_running:
            await self._transport.stop_server()