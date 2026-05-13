"""Tor hidden service support for Agent Club.

Allows agents to communicate over Tor for anonymity.
Optional dependency — only activated when Stem is installed.
"""

import logging
import os
import socket
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

TOR_AVAILABLE = False
try:
    import stem
    import stem.process
    import stem.connection
    TOR_AVAILABLE = True
except ImportError:
    logger.info("Stem not installed — Tor support disabled")


class TorError(Exception):
    """เกิดข้อผิดพลาดกับ Tor service."""

    pass


class TorService:
    """จัดการ Tor hidden service สำหรับ Agent Club.

    สร้าง .onion address สำหรับ agent เพื่อ anonymous communication.
    """

    def __init__(self, socks_port: int = 9050, control_port: int = 9051):
        """สร้าง TorService.

        Args:
            socks_port: SOCKS port ของ Tor daemon
            control_port: Control port ของ Tor daemon
        """
        if not TOR_AVAILABLE:
            raise TorError(
                "Stem not installed — install with: pip install stem"
            )

        self.socks_port = socks_port
        self.control_port = control_port
        self._tor_process = None
        self._hidden_service_dir: Optional[str] = None
        self._onion_address: Optional[str] = None
        self._running = False

    def start_hidden_service(
        self,
        target_port: int,
        service_dir: Optional[str] = None,
    ) -> str:
        """สร้าง Tor hidden service.

        Args:
            target_port: พอร์ตที่ service ทำงานอยู่ (เช่น 8765 สำหรับ WebSocket)
            service_dir: Directory สำหรับเก็บ hidden service config

        Returns:
            .onion address ของ hidden service
        """
        if not service_dir:
            service_dir = os.path.expanduser("~/.agent-club/tor")

        os.makedirs(service_dir, exist_ok=True)
        self._hidden_service_dir = service_dir

        # ตรวจสอบว่า Tor daemon ทำงานอยู่
        if not self._is_tor_running():
            raise TorError(
                "Tor daemon not running. "
                "Start it with: sudo systemctl start tor"
            )

        # ใช้ Tor Control Protocol เพื่อสร้าง hidden service
        from stem import Signal
        from stem.control import Controller

        with Controller.from_port(port=self.control_port) as controller:
            controller.authenticate()  # ใช้ cookie file โดยอัตโนมัติ

            # ตั้งค่า hidden service
            controller.set_conf(
                "HiddenServiceDir", service_dir
            )
            controller.set_conf(
                "HiddenServicePort", f"{target_port} 127.0.0.1:{target_port}"
            )

            # อ่าน onion address
            hostname_path = os.path.join(service_dir, "hostname")
            retries = 10
            while retries > 0:
                time.sleep(1)
                if os.path.exists(hostname_path):
                    with open(hostname_path) as f:
                        self._onion_address = f.read().strip()
                    break
                retries -= 1

            if not self._onion_address:
                raise TorError("Failed to create hidden service")

            self._running = True
            logger.info(f"Hidden service created: {self._onion_address}")
            return self._onion_address

    def connect_to_hidden(self, onion_address: str, target_port: int) -> socket.socket:
        """เชื่อมต่อไปยัง Tor hidden service.

        Args:
            onion_address: .onion address (โดยไม่มี .onion)
            target_port: พอร์ตปลายทาง

        Returns:
            Connected socket ผ่าน Tor SOCKS proxy
        """
        try:
            import socks  # PySocks
        except ImportError:
            raise TorError("PySocks not installed — install with: pip install PySocks")

        # ตั้งค่า SOCKS proxy
        socks.set_default_proxy(
            socks.SOCKS5,
            "127.0.0.1",
            self.socks_port,
        )
        socket.socket = socks.socksocket

        # เชื่อมต่อ
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((onion_address + ".onion", target_port))
        return sock

    def _is_tor_running(self) -> bool:
        """ตรวจสอบว่า Tor daemon ทำงานอยู่."""
        try:
            from stem.control import Controller
            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate()
                return True
        except Exception:
            return False

    def get_onion_address(self) -> Optional[str]:
        """ดึง onion address ของ hidden service."""
        return self._onion_address

    def stop_hidden_service(self):
        """หยุด hidden service."""
        from stem.control import Controller

        with Controller.from_port(port=self.control_port) as controller:
            controller.authenticate()
            controller.set_conf("HiddenServiceDir", "")
            controller.set_conf("HiddenServicePort", "")

        self._onion_address = None
        self._running = False

    def new_identity(self):
        """Request ตัวตนใหม่จาก Tor network."""
        from stem import Signal
        from stem.control import Controller

        with Controller.from_port(port=self.control_port) as controller:
            controller.authenticate()
            controller.signal(Signal.NEWNYM)

    @property
    def is_running(self) -> bool:
        """ตรวจสอบว่า hidden service กำลังทำงานอยู่."""
        return self._running

    def verify_onion(self, onion_address: str) -> bool:
        """ตรวจสอบว่า onion address ถูกต้องหรือไม่.

        Args:
            onion_address: .onion address ที่ต้องการตรวจสอบ

        Returns:
            True หาก address ดูถูกต้องรูปแบบ
        """
        # v3 onion addresses: 56 characters base32 + ".onion"
        clean = onion_address.replace(".onion", "")
        return len(clean) == 56 and all(
            c in "abcdefghijklmnopqrstuvwxyz234567" for c in clean.lower()
        )


def setup_tor_for_agent(
    agent_port: int,
    tor_control_port: int = 9051,
    socks_port: int = 9050,
) -> tuple:
    """ตั้งค่า Tor สำหรับ agent อย่างง่าย.

    Args:
        agent_port: พอร์ตที่ agent ทำงาน
        tor_control_port: Tor control port
        socks_port: Tor SOCKS port

    Returns:
        tuple: (onion_address, TorService instance)
    """
    tor = TorService(
        socks_port=socks_port,
        control_port=tor_control_port,
    )
    onion_addr = tor.start_hidden_service(target_port=agent_port)
    return onion_addr, tor