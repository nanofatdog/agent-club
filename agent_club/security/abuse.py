"""Abuse detection & prevention for Agent Club.

ป้องกันการใช้งานในทางที่ผิด:
- Rate limiting
- Spam detection
- Sybil attack detection
- Auto-ban system
"""

import time
import hashlib
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict


class RateLimitError(Exception):
    """เกิน rate limit."""

    pass


class RateLimiter:
    """Rate limiter สำหรับแต่ละ agent.

    ใช้ sliding window algorithm
    """

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: List[float] = []

    def check(self) -> bool:
        """ตรวจสอบว่าสามารถส่ง request ได้หรือไม่.

        Returns:
            True หากอยู่ใน limit
        """
        now = time.time()
        # ลบ requests ที่เก่าแล้ว
        cutoff = now - self.window_seconds
        self._requests = [t for t in self._requests if t > cutoff]

        if len(self._requests) >= self.max_requests:
            return False

        self._requests.append(now)
        return True

    def wait_time(self) -> float:
        """เวลาที่ต้องรอจึงจะสามารถส่ง request ได้.

        Returns:
            วินาทีที่ต้องรอ (0 หากสามารถส่งได้ทันที)
        """
        if self.check():
            return 0.0
        oldest = self._requests[0]
        return oldest + self.window_seconds - time.time()

    def reset(self):
        """รีเซ็ต rate limiter."""
        self._requests.clear()


class SpamDetector:
    """ตรวจจับ spam messages."""

    def __init__(self):
        self._message_hashes: Dict[str, List[float]] = defaultdict(list)
        self._repeat_counts: Dict[str, int] = defaultdict(int)

    def check_message(self, message_content: str) -> tuple:
        """ตรวจสอบว่า message เป็น spam หรือไม่.

        Args:
            message_content: เนื้อหาข้อความ

        Returns:
            (is_spam: bool, score: float)
        """
        content_hash = hashlib.sha256(
            message_content.encode("utf-8")
        ).hexdigest()[:16]

        now = time.time()
        window = 60  # 1 นาที

        # ลบ hashes เก่า
        cutoff = now - window
        self._message_hashes[content_hash] = [
            t for t in self._message_hashes[content_hash]
            if t > cutoff
        ]

        # เพิ่ม hash ปัจจุบัน
        self._message_hashes[content_hash].append(now)
        count = len(self._message_hashes[content_hash])

        # ถ้าส่ง message ซ้ำ > 5 ครั้งใน 1 นาที = spam
        if count > 5:
            self._repeat_counts[content_hash] += 1
            score = min(count / 10.0, 1.0)
            return True, score

        return False, 0.0

    def get_spam_score(self, agent_id: str) -> float:
        """ดู spam score ของ agent."""
        return min(self._repeat_counts.get(agent_id, 0) * 0.1, 1.0)


class SybilDetector:
    """ตรวจจับ Sybil attack — สร้าง agent ปลอมหลายตัว."""

    def __init__(self):
        self._creation_times: Dict[str, float] = {}
        self._ip_addresses: Dict[str, Set[str]] = defaultdict(set)
        self._behavior_patterns: Dict[str, dict] = {}
        self._suspected_sybils: Set[str] = set()

    def register_agent(self, agent_id: str, metadata: dict = None):
        """ลงทะเบียน agent ใหม่.

        Args:
            agent_id: Agent ID
            metadata: ข้อมูลเพิ่มเติม (IP, capabilities, etc.)
        """
        self._creation_times[agent_id] = time.time()
        if metadata:
            ip = metadata.get("ip", "")
            if ip:
                self._ip_addresses[ip].add(agent_id)
            self._behavior_patterns[agent_id] = {
                "capabilities": metadata.get("capabilities", []),
                "join_count": 0,
                "message_count": 0,
            }

    def check_sybil(self, agent_id: str) -> dict:
        """ตรวจสอบว่า agent เป็น Sybil หรือไม่.

        Returns:
            dict with:
            - is_sybil: bool
            - risk_score: float
            - reasons: list[str]
        """
        reasons = []
        risk_score = 0.0

        # ตรวจสอบ IP sharing
        metadata = self._behavior_patterns.get(agent_id, {})
        ip = metadata.get("ip", "")
        if ip and ip in self._ip_addresses:
            shared_agents = self._ip_addresses[ip]
            if len(shared_agents) > 3:
                risk_score += 0.4
                reasons.append(
                    f"Multiple agents from same IP ({len(shared_agents)} agents)"
                )

        # ตรวจสอบ creation time clustering
        # ถ้ามี agent หลายตัวถูกสร้างในเวลาใกล้เคียงกัน
        agent_time = self._creation_times.get(agent_id, 0)
        close_creations = 0
        for aid, t in self._creation_times.items():
            if aid != agent_id and abs(t - agent_time) < 60:  # ภายใน 1 นาที
                close_creations += 1

        if close_creations > 5:
            risk_score += 0.3
            reasons.append(
                f"Many agents created around same time ({close_creations})"
            )

        # ตรวจสอบ behavior patterns
        pattern = self._behavior_patterns.get(agent_id, {})
        capabilities = pattern.get("capabilities", [])

        # ถ้ามี capabilities ซ้ำกันหลาย agent — น่าสงสัย
        cap_freq = defaultdict(int)
        for aid, p in self._behavior_patterns.items():
            for cap in p.get("capabilities", []):
                cap_freq[cap] += 1

        for cap in capabilities:
            if cap_freq[cap] > 10:
                risk_score += 0.1
                reasons.append(f"Common capability: {cap} ({cap_freq[cap]} agents)")

        # ตรวจสอบ activity
        join_count = pattern.get("join_count", 0)
        msg_count = pattern.get("message_count", 0)

        if join_count > 20 and msg_count < 2:
            risk_score += 0.3
            reasons.append("High join activity but low messaging (bot-like)")

        if msg_count > 50 and join_count == 0:
            risk_score += 0.2
            reasons.append("Messaging without joining rooms properly")

        risk_score = min(risk_score, 1.0)
        is_sybil = risk_score > 0.5

        if is_sybil:
            self._suspected_sybils.add(agent_id)

        return {
            "is_sybil": is_sybil,
            "risk_score": risk_score,
            "reasons": reasons,
        }

    def update_activity(self, agent_id: str, action: str):
        """อัพเดตกิจกรรมของ agent.

        Args:
            agent_id: Agent ID
            action: "join", "leave", "message", "create_room"
        """
        if agent_id not in self._behavior_patterns:
            self._behavior_patterns[agent_id] = {
                "capabilities": [],
                "join_count": 0,
                "message_count": 0,
            }

        pattern = self._behavior_patterns[agent_id]
        if action == "join":
            pattern["join_count"] += 1
        elif action == "message":
            pattern["message_count"] += 1

    def get_suspected_agents(self) -> list:
        """ดูรายชื่อ agent ที่น่าสงสัย."""
        return list(self._suspected_sybils)

    def clear_suspect(self, agent_id: str):
        """ลบ agent ออกจากรายชื่อ suspicious."""
        self._suspected_sybils.discard(agent_id)


class AbusePrevention:
    """ระบบป้องกัน abuse แบบครบวงจร."""

    def __init__(self):
        # Rate limits (default values — ปรับได้)
        self.default_limits = {
            "messages_per_minute": 30,
            "rooms_per_hour": 10,
            "knowledge_requests_per_hour": 20,
            "new_rooms_per_day": 5,
            "connections_per_minute": 10,
        }

        self._rate_limiters: Dict[str, Dict[str, RateLimiter]] = defaultdict(dict)
        self._spam_detector = SpamDetector()
        self._sybil_detector = SybilDetector()
        self._banned_agents: Dict[str, dict] = {}  # agent_id -> {reason, until}

    def get_rate_limiter(self, agent_id: str, action: str) -> RateLimiter:
        """ดึง rate limiter สำหรับ agent + action.

        Args:
            agent_id: Agent ID
            action: ชนิดของการกระทำ

        Returns:
            RateLimiter instance
        """
        if action not in self._rate_limiters[agent_id]:
            # สร้าง rate limiter ตาม default limits
            limit = self.default_limits.get(action, 30)
            window_map = {
                "messages_per_minute": 60,
                "rooms_per_hour": 3600,
                "knowledge_requests_per_hour": 3600,
                "new_rooms_per_day": 86400,
                "connections_per_minute": 60,
            }
            window = window_map.get(action, 60)
            self._rate_limiters[agent_id][action] = RateLimiter(limit, window)

        return self._rate_limiters[agent_id][action]

    def check_rate(self, agent_id: str, action: str) -> bool:
        """ตรวจสอบว่า agent เกิน rate limit หรือไม่.

        Args:
            agent_id: Agent ID
            action: ชนิดของการกระทำ

        Returns:
            True หากอยู่ใน limit

        Raises:
            RateLimitError: หากเกิน limit
        """
        # ตรวจสอบ ban ก่อน
        if self.is_banned(agent_id):
            ban_info = self._banned_agents[agent_id]
            raise RateLimitError(
                f"Agent {agent_id} is banned: {ban_info.get('reason', 'unknown')}"
            )

        limiter = self.get_rate_limiter(agent_id, action)
        if not limiter.check():
            wait = limiter.wait_time()
            raise RateLimitError(
                f"Rate limit exceeded for {action}. "
                f"Wait {wait:.1f} seconds"
            )

        return True

    def check_message_spam(self, agent_id: str, content: str) -> tuple:
        """ตรวจสอบ spam ใน message.

        Returns:
            (is_spam: bool, score: float)
        """
        is_spam, score = self._spam_detector.check_message(content)

        if is_spam and score > 0.7:
            self._auto_warn(agent_id, "spam_detected")

        return is_spam, score

    def check_sybil(self, agent_id: str, metadata: dict = None) -> dict:
        """ตรวจสอบ Sybil attack.

        Args:
            agent_id: Agent ID
            metadata: ข้อมูล agent

        Returns:
            dict with sybil check results
        """
        if metadata:
            self._sybil_detector.register_agent(agent_id, metadata)

        result = self._sybil_detector.check_sybil(agent_id)

        if result["is_sybil"]:
            self._auto_warn(agent_id, f"sybil_detected: {result['reasons']}")

        return result

    def ban_agent(self, agent_id: str, reason: str, duration_seconds: float = 3600):
        """แบน agent.

        Args:
            agent_id: Agent ID ที่ต้องการแบน
            reason: เหตุผล
            duration_seconds: ระยะเวลาการแบน (วินาที)
        """
        self._banned_agents[agent_id] = {
            "reason": reason,
            "banned_until": time.time() + duration_seconds,
            "banned_at": time.time(),
        }

        # บันทึกใน trust system
        # (ใน production: เรียก trust_manager.add_penalty())

    def unban_agent(self, agent_id: str):
        """ปลดแบน agent."""
        self._banned_agents.pop(agent_id, None)

    def is_banned(self, agent_id: str) -> bool:
        """ตรวจสอบว่า agent ถูกแบนหรือไม่.

        Returns:
            True หาก agent ถูกแบนอยู่
        """
        if agent_id in self._banned_agents:
            ban_info = self._banned_agents[agent_id]
            if time.time() < ban_info.get("banned_until", float("inf")):
                return True
            else:
                # Ban หมดอายุแล้ว
                del self._banned_agents[agent_id]

        return False

    def _auto_warn(self, agent_id: str, reason: str):
        """เตือน agent อัตโนมัติ.

        Args:
            agent_id: Agent ID
            reason: เหตุผล
        """
        # ใน production: ส่ง warning message ไปยัง agent
        # หรือบันทึกลง log
        pass

    def get_banned_agents(self) -> dict:
        """ดูรายชื่อ agent ที่ถูกแบน."""
        # ลบ ban ที่หมดอายุ
        now = time.time()
        expired = [
            aid for aid, info in self._banned_agents.items()
            if info.get("banned_until", 0) < now
        ]
        for aid in expired:
            del self._banned_agents[aid]

        return self._banned_agents

    def get_stats(self) -> dict:
        """ดูสถิติ abuse prevention."""
        return {
            "banned_count": len(self._banned_agents),
            "rate_limiter_count": sum(
                len(actions) for actions in self._rate_limiters.values()
            ),
            "sybil_suspects": len(
                self._sybil_detector.get_suspected_agents()
            ),
            "spam_detections": sum(
                self._spam_detector._repeat_counts.values()
            ),
        }

    def cleanup(self):
        """ล้างข้อมูลเก่า."""
        now = time.time()

        # ลบ ban ที่หมดอายุ
        expired_bans = [
            aid for aid, info in self._banned_agents.items()
            if info.get("banned_until", 0) < now
        ]
        for aid in expired_bans:
            del self._banned_agents[aid]

        # ลบ old rate limiters
        # (ใน production จะเก็บเฉพาะ active agents)
        self._spam_detector._message_hashes.clear()
        self._spam_detector._repeat_counts.clear()