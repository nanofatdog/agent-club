"""Trust scoring system for Agent Club.

Implements decentralized trust management:
- Agent identity verification
- Interaction-based trust scoring
- Web of trust propagation
"""

import time
from typing import Any, Dict, List, Optional, Set


class InteractionRecord:
    """บันทึก interaction ระหว่าง agent."""

    def __init__(
        self,
        agent_a: str,
        agent_b: str,
        interaction_type: str,
        result: str,
        timestamp: float = None,
        details: dict = None,
    ):
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.interaction_type = interaction_type
        self.result = result
        self.timestamp = timestamp or time.time()
        self.details = details or {}


class TrustScore:
    """คะแนนความน่าเชื่อถือของ agent.

    Trust Score (0.0 - 1.0) คำนวณจากหลายปัจจัย:
    - อายุของ identity
    - จำนวน interaction ที่ดี/ไม่ดี
    - คุณภาพของ knowledge ที่ share
    - References จาก agent อื่น
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._base_score: float = 0.5
        self._interactions: List[InteractionRecord] = []
        self._references: Dict[str, float] = {}
        self._penalties: List[tuple] = []  # (reason, severity, timestamp)
        self._first_seen: float = time.time()
        self._last_updated: float = time.time()

    def add_interaction(self, record: InteractionRecord):
        """เพิ่ม interaction record."""
        self._interactions.append(record)
        self._last_updated = time.time()

    def add_reference(self, referrer_id: str, score: float):
        """เพิ่ม reference จาก agent อื่น.

        Args:
            referrer_id: Agent ที่ให้ reference
            score: คะแนนที่ให้ (0.0-1.0)
        """
        self._references[referrer_id] = score
        self._last_updated = time.time()

    def add_penalty(self, reason: str, severity: float):
        """เพิ่ม penalty (การลงโทษ).

        Args:
            reason: เหตุผล
            severity: ความรุนแรง (0.0-1.0)
        """
        self._penalties.append((reason, severity, time.time()))
        self._last_updated = time.time()

    def calculate_score(self) -> float:
        """คำนวณ trust score.

        สูตร:
        - เริ่มจาก base score
        - ปรับตาม interactions (recent มีน้ำหนักมากกว่า)
        - ปรับตาม references
        - หัก penalty
        - โบนัสอายุ identity

        Returns:
            Trust score (0.0 - 1.0)
        """
        score = self._base_score

        # 1. อายุ identity bonus
        age_seconds = time.time() - self._first_seen
        age_days = age_seconds / 86400
        # +0.1 สูงสุดสำหรับ identity ที่มีอายุ > 90 วัน
        age_bonus = min(0.1, age_days / 900)
        score += age_bonus

        # 2. Interaction score
        if self._interactions:
            total = len(self._interactions)
            # นับ recent interactions มากกว่า
            recent_window = 86400 * 7  # 7 วัน
            now = time.time()

            positive = 0
            negative = 0
            for rec in self._interactions:
                recency = max(0, 1 - (now - rec.timestamp) / recent_window)
                weight = 0.3 + 0.7 * recency

                if rec.result in ("success", "accepted", "helpful"):
                    positive += weight
                elif rec.result in ("failure", "rejected", "harmful", "invalid"):
                    negative += weight
                # "neutral", "deferred" ไม่มีผล

            if total > 0:
                interaction_score = (positive - negative * 2) / (total * 0.5)
                interaction_score = max(-0.3, min(0.3, interaction_score))
                score += interaction_score

        # 3. Reference score
        if self._references:
            ref_avg = sum(self._references.values()) / len(self._references)
            score += (ref_avg - 0.5) * 0.2

        # 4. Penalty deduction
        now = time.time()
        for reason, severity, ts in self._penalties:
            # Penalty ลดลงตามเวลา (half-life = 7 days)
            age = now - ts
            decay = 0.5 ** (age / (86400 * 7))
            score -= severity * decay * 0.3

        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))

    def get_grade(self) -> str:
        """ดึง trust grade (human-readable)."""
        score = self.calculate_score()
        if score >= 0.9:
            return "A+"
        elif score >= 0.8:
            return "A"
        elif score >= 0.7:
            return "B"
        elif score >= 0.5:
            return "C"
        elif score >= 0.3:
            return "D"
        else:
            return "F"

    def get_stats(self) -> dict:
        """ดูสถิติ trust score."""
        return {
            "agent_id": self.agent_id,
            "score": round(self.calculate_score(), 4),
            "grade": self.get_grade(),
            "total_interactions": len(self._interactions),
            "references": len(self._references),
            "penalties": len(self._penalties),
            "age_days": round((time.time() - self._first_seen) / 86400, 1),
            "last_updated": self._last_updated,
        }

    def decay_old_interactions(self, max_age_seconds: float = 86400 * 30):
        """ลบ interaction เก่า (เพื่อไม่ให้ history มีขนาดใหญ่เกินไป)."""
        now = time.time()
        self._interactions = [
            i for i in self._interactions
            if now - i.timestamp < max_age_seconds
        ]

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "score": round(self.calculate_score(), 4),
            "grade": self.get_grade(),
            "stats": self.get_stats(),
        }


class TrustManager:
    """จัดการ trust scores สำหรับทุก agent ในระบบ.

    หน้าที่:
    - บันทึก interaction ระหว่าง agents
    - คำนวณและอัพเดต trust scores
    - จัดการ web of trust propagation
    - บล็อก agent ที่ trust score ต่ำเกินไป
    """

    TRUST_THRESHOLD_AUTO_JOIN = 0.3
    TRUST_THRESHOLD_SHARE_KNOWLEDGE = 0.4
    TRUST_THRESHOLD_MODERATOR = 0.7
    TRUST_THRESHOLD_BAN = 0.05

    def __init__(self):
        self._scores: Dict[str, TrustScore] = {}
        self._pending_references: List[tuple] = []  # (from_agent, to_agent, score)

    def get_or_create(self, agent_id: str) -> TrustScore:
        """ดึงหรือสร้าง TrustScore สำหรับ agent.

        Args:
            agent_id: Agent ID (fingerprint)

        Returns:
            TrustScore instance
        """
        if agent_id not in self._scores:
            self._scores[agent_id] = TrustScore(agent_id)
        return self._scores[agent_id]

    def record_interaction(
        self,
        agent_a: str,
        agent_b: str,
        interaction_type: str,
        result: str,
        details: dict = None,
    ):
        """บันทึก interaction ระหว่าง agent สองตัว.

        Args:
            agent_a: Agent แรก
            agent_b: Agent ที่สอง
            interaction_type: "message", "knowledge_share", "room_join", "request", etc.
            result: "success", "failure", "accepted", "rejected", etc.
            details: ข้อมูลเพิ่มเติม
        """
        now = time.time()

        # เพิ่ม interaction ให้ทั้งสองฝั่ง
        for agent_id in (agent_a, agent_b):
            score = self.get_or_create(agent_id)
            record = InteractionRecord(
                agent_a=agent_a,
                agent_b=agent_b,
                interaction_type=interaction_type,
                result=result,
                timestamp=now,
                details=details,
            )
            score.add_interaction(record)

    def record_reference(self, from_agent: str, to_agent: str, score: float):
        """บันทึก reference จาก agent หนึ่งไปยังอีกตัว.

        Args:
            from_agent: Agent ที่ให้ reference
            to_agent: Agent ที่ได้รับ reference
            score: คะแนน (0.0-1.0)
        """
        to = self.get_or_create(to_agent)
        to.add_reference(from_agent, score)

    def add_penalty(self, agent_id: str, reason: str, severity: float):
        """เพิ่ม penalty ให้ agent.

        Args:
            agent_id: Agent ที่ต้องการลงโทษ
            reason: เหตุผล
            severity: ความรุนแรง (0.0-1.0)
        """
        score = self.get_or_create(agent_id)
        score.add_penalty(reason, severity)

    def get_trust_score(self, agent_id: str) -> TrustScore:
        """ดึง trust score ของ agent.

        Args:
            agent_id: Agent ID

        Returns:
            TrustScore instance
        """
        return self.get_or_create(agent_id)

    def get_score_value(self, agent_id: str) -> float:
        """ดึงค่า trust score (float)."""
        return self.get_trust_score(agent_id).calculate_score()

    def is_trusted(self, agent_id: str, threshold: float = None) -> bool:
        """ตรวจสอบว่า agent น่าเชื่อถือหรือไม่.

        Args:
            agent_id: Agent ID
            threshold: Threshold (ใช้ค่า default หากไม่ระบุ)

        Returns:
            True หาก trust score >= threshold
        """
        if threshold is None:
            threshold = self.TRUST_THRESHOLD_AUTO_JOIN
        return self.get_score_value(agent_id) >= threshold

    def should_auto_join(self, agent_id: str) -> bool:
        """ตรวจสอบว่าควร auto-join ห้องหรือไม่."""
        return self.is_trusted(agent_id, self.TRUST_THRESHOLD_AUTO_JOIN)

    def can_share_knowledge_with(self, agent_id: str) -> bool:
        """ตรวจสอบว่าควร share knowledge หรือไม่."""
        return self.is_trusted(agent_id, self.TRUST_THRESHOLD_SHARE_KNOWLEDGE)

    def is_banned(self, agent_id: str) -> bool:
        """ตรวจสอบว่า agent ถูกแบนหรือไม่."""
        return self.get_score_value(agent_id) < self.TRUST_THRESHOLD_BAN

    def get_top_agents(self, count: int = 10) -> List[dict]:
        """ดู agent ที่มี trust score สูงสุด."""
        scores = [
            s.to_dict() for s in self._scores.values()
        ]
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:count]

    def get_all_scores(self) -> Dict[str, float]:
        """ดู trust scores ทั้งหมด."""
        return {
            aid: score.calculate_score()
            for aid, score in self._scores.items()
        }

    def cleanup_old_data(self):
        """ลบ interaction เก่าเพื่อประหยัด memory."""
        for score in self._scores.values():
            score.decay_old_interactions()

    def process_pending_references(self):
        """ประมวลผล pending references."""
        for from_agent, to_agent, score in self._pending_references:
            self.record_reference(from_agent, to_agent, score)
        self._pending_references.clear()

    def to_dict(self) -> dict:
        """ดูสถานะรวม."""
        return {
            "total_agents": len(self._scores),
            "scores": self.get_all_scores(),
            "pending_references": len(self._pending_references),
        }