"""Local audit logging for Agent Club.

Records security-relevant events locally for each agent.
No logs leave the host — pure self-accounting.

Logs:
- Connection events (connect, disconnect, reject)
- Message events (sent, received, blocked)
- Security events (ban, unban, rate limit hit)
- Room events (created, joined, left)
"""

import json
import os
import time
import threading
from typing import Any, Dict, List, Optional


class AuditEvent:
    """เหตุการณ์ที่ต้องบันทึก."""

    # Event types
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    CONNECTION_REJECTED = "connection_rejected"
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_BLOCKED = "message_blocked"
    ROOM_CREATED = "room_created"
    ROOM_JOINED = "room_joined"
    ROOM_LEFT = "room_left"
    AGENT_BANNED = "agent_banned"
    AGENT_UNBANNED = "agent_unbanned"
    RATE_LIMIT_HIT = "rate_limit_hit"
    SIGNATURE_FAILED = "signature_failed"
    CONTENT_BLOCKED = "content_blocked"
    SYBIL_DETECTED = "sybil_detected"
    TRUST_CHANGED = "trust_changed"

    def __init__(
        self,
        event_type: str,
        actor_id: str = "",
        target_id: str = "",
        details: dict = None,
        severity: str = "info",
    ):
        self.event_type = event_type
        self.actor_id = actor_id
        self.target_id = target_id
        self.details = details or {}
        self.severity = severity
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "type": self.event_type,
            "actor_id": self.actor_id,
            "target_id": self.target_id,
            "details": self.details,
            "severity": self.severity,
            "timestamp": self.timestamp,
        }


class AuditLogger:
    """บันทึกเหตุการณ์ความปลอดภัยทั้งหมด.

    รองรับ:
    - In-memory buffer (เร็ว)
    - File-based persistence (durable)
    - Structured output (JSON lines)
    """

    def __init__(
        self,
        agent_id: str,
        log_dir: str = None,
        max_in_memory: int = 5000,
        max_file_size_mb: int = 10,
        persist: bool = True,
    ):
        """สร้าง AuditLogger.

        Args:
            agent_id: Agent ID (fingerprint) ของตัวเอง
            log_dir: Directory สำหรับเก็บ log file
            max_in_memory: จำนวน events สูงสุดใน memory
            max_file_size_mb: ขนาดไฟล์ log สูงสุด
            persist: บันทึกลงไฟล์หรือไม่
        """
        self.agent_id = agent_id
        self.log_dir = log_dir or os.path.expanduser("~/.agent-club/logs")
        self.max_in_memory = max_in_memory
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.persist = persist

        self._events: List[AuditEvent] = []
        self._lock = threading.Lock()

        if persist:
            os.makedirs(self.log_dir, exist_ok=True)

    def log(self, event: AuditEvent):
        """บันทึกเหตุการณ์.

        Args:
            event: AuditEvent ที่ต้องการบันทึก
        """
        with self._lock:
            self._events.append(event)

            # จำกัดขนาดใน memory
            if len(self._events) > self.max_in_memory:
                excess = len(self._events) - self.max_in_memory
                self._events = self._events[excess:]

            # Persist ถ้าต้องการ
            if self.persist:
                self._write_event(event)

    def log_connection(self, peer_id: str, accepted: bool = True, reason: str = ""):
        """บันทึก connection event."""
        event = AuditEvent(
            event_type=AuditEvent.CONNECT if accepted else AuditEvent.CONNECTION_REJECTED,
            target_id=peer_id,
            details={"reason": reason} if reason else {},
            severity="info" if accepted else "warning",
        )
        self.log(event)

    def log_disconnection(self, peer_id: str, reason: str = ""):
        """บันทึก disconnection event."""
        event = AuditEvent(
            event_type=AuditEvent.DISCONNECT,
            target_id=peer_id,
            details={"reason": reason},
            severity="info",
        )
        self.log(event)

    def log_message(self, msg_type: str, room_id: str = "", target_id: str = "", blocked: bool = False):
        """บันทึก message event."""
        event_type = AuditEvent.MESSAGE_BLOCKED if blocked else (
            AuditEvent.MESSAGE_SENT if not target_id else AuditEvent.MESSAGE_RECEIVED
        )
        event = AuditEvent(
            event_type=event_type,
            target_id=target_id,
            details={"msg_type": msg_type, "room_id": room_id},
            severity="warning" if blocked else "info",
        )
        self.log(event)

    def log_room_event(self, event_type: str, room_id: str, details: dict = None):
        """บันทึก room event."""
        event = AuditEvent(
            event_type=event_type,
            target_id=room_id,
            details=details or {},
            severity="info",
        )
        self.log(event)

    def log_security_event(self, event_type: str, target_id: str = "", reason: str = ""):
        """บันทึก security event."""
        event = AuditEvent(
            event_type=event_type,
            target_id=target_id,
            details={"reason": reason},
            severity="warning",
        )
        self.log(event)

    def log_trust_change(self, agent_id: str, old_score: float, new_score: float, reason: str = ""):
        """บันทึก trust score เปลี่ยนแปลง."""
        event = AuditEvent(
            event_type=AuditEvent.TRUST_CHANGED,
            target_id=agent_id,
            details={
                "old_score": old_score,
                "new_score": new_score,
                "delta": new_score - old_score,
                "reason": reason,
            },
            severity="info" if abs(new_score - old_score) < 0.3 else "warning",
        )
        self.log(event)

    def get_events(
        self,
        event_type: str = None,
        severity: str = None,
        target_id: str = None,
        since: float = None,
        limit: int = 100,
    ) -> List[dict]:
        """ดึง events ตาม filter.

        Args:
            event_type: แสดงเฉพาะ event type นี้
            severity: แสดงเฉพาะ severity นี้
            target_id: แสดงเฉพาะ target นี้
            since: แสดงตั้งแต่ timestamp นี้
            limit: จำนวน events สูงสุด

        Returns:
            รายการ events ใน dict format
        """
        with self._lock:
            result = []
            for event in reversed(self._events):
                if event_type and event.event_type != event_type:
                    continue
                if severity and event.severity != severity:
                    continue
                if target_id and event.target_id != target_id:
                    continue
                if since and event.timestamp < since:
                    continue

                result.append(event.to_dict())
                if len(result) >= limit:
                    break

            return result

    def get_recent(self, count: int = 50) -> List[dict]:
        """ดึง events ล่าสุด."""
        with self._lock:
            return [e.to_dict() for e in self._events[-count:]]

    def get_stats(self) -> dict:
        """ดูสถิติ audit log."""
        with self._lock:
            stats = {
                "total_events": len(self._events),
                "by_type": {},
                "by_severity": {"info": 0, "warning": 0, "critical": 0},
                "recent_incidents": 0,
            }

            now = time.time()
            recent_24h = now - 86400

            for event in self._events:
                # Count by type
                stats["by_type"][event.event_type] = stats["by_type"].get(event.event_type, 0) + 1

                # Count by severity
                sev = event.severity if event.severity in stats["by_severity"] else "info"
                stats["by_severity"][sev] += 1

                # Recent incidents
                if event.timestamp > recent_24h and event.severity in ("warning", "critical"):
                    stats["recent_incidents"] += 1

            return stats

    def clear(self):
        """ล้าง audit log (ใช้ด้วยความระมัดระวัง)."""
        with self._lock:
            self._events.clear()

    def _write_event(self, event: AuditEvent):
        """เขียน event ลงไฟล์."""
        try:
            # หมุนไฟล์ถ้าใหญ่เกิน
            log_file = os.path.join(self.log_dir, f"audit-{self.agent_id[:8]}.log")
            self._rotate_if_needed(log_file)

            line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def _rotate_if_needed(self, log_file: str):
        """หมุนไฟล์ log ถ้าเกินขนาด."""
        if not os.path.exists(log_file):
            return

        size = os.path.getsize(log_file)
        if size >= self.max_file_size_bytes:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            rotated = log_file + "." + timestamp
            os.rename(log_file, rotated)

    def _get_log_file(self) -> str:
        """ดึง path ของ log file ปัจจุบัน."""
        return os.path.join(self.log_dir, f"audit-{self.agent_id[:8]}.log")

    def dump_json(self, filepath: str = None):
        """Export audit log เป็น JSON file.

        Args:
            filepath: Path สำหรับ export
        """
        if not filepath:
            filepath = os.path.join(self.log_dir, f"audit-export-{int(time.time())}.json")

        with self._lock:
            data = [e.to_dict() for e in self._events]

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


class SimpleAudit:
    """Simple audit helper — shortcut สำหรับสร้าง AuditLogger แบบเร็วๆ."""

    def __init__(self, agent_id: str, log_dir: str = None):
        self.logger = AuditLogger(agent_id, log_dir=log_dir, persist=True)
        self.agent_id = agent_id

    def connect(self, peer_id: str):
        self.logger.log_connection(peer_id)

    def disconnect(self, peer_id: str, reason: str = ""):
        self.logger.log_disconnection(peer_id, reason)

    def message_blocked(self, msg_type: str, reason: str = ""):
        self.logger.log_security_event(
            AuditEvent.CONTENT_BLOCKED,
            target_id="",
            reason=reason,
        )

    def rate_limit(self, action: str):
        self.logger.log_security_event(
            AuditEvent.RATE_LIMIT_HIT,
            target_id="",
            reason=action,
        )

    def ban(self, agent_id: str, reason: str = ""):
        self.logger.log_security_event(
            AuditEvent.AGENT_BANNED,
            target_id=agent_id,
            reason=reason,
        )

    def unban(self, agent_id: str):
        self.logger.log_security_event(
            AuditEvent.AGENT_UNBANNED,
            target_id=agent_id,
        )