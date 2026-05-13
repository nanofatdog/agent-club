"""Agent behavior & decision-making module for Agent Club.

Implements autonomous decision logic for agents:
- Should I join this room?
- Should I respond to this message?
- Should I share knowledge with this agent?
"""

import time
from typing import Any, Dict, List, Optional

from agent_club.agent.manager import Agent, AgentConfig
from agent_club.room.manager import Room, RoomMember


class Decision:
    """ผลการตัดสินใจของ Agent.

    Attributes:
        action: การกระทำ ("accept", "reject", "defer", "respond", "ignore", "share")
        confidence: ความมั่นใจ (0.0 - 1.0)
        reason: เหตุผลของการตัดสินใจ
        priority: ลำดับความสำคัญ (1-10, default 5)
        data: ข้อมูลเสริมที่เกี่ยวข้อง
    """

    def __init__(
        self,
        action: str,
        confidence: float = 0.5,
        reason: str = "",
        priority: int = 5,
        data: Any = None,
    ):
        self.action = action
        self.confidence = max(0.0, min(1.0, confidence))
        self.reason = reason
        self.priority = max(1, min(10, priority))
        self.data = data
        self.timestamp = time.time()

    def is_positive(self) -> bool:
        """ตรวจสอบว่าเป็นการตัดสินใจเชิงบวกหรือไม่."""
        return self.action in ("accept", "respond", "share") and self.confidence > 0.5

    def is_negative(self) -> bool:
        """ตรวจสอบว่าเป็นการตัดสินใจเชิงลบหรือไม่."""
        return self.action in ("reject", "ignore") or (self.action == "defer" and self.confidence < 0.3)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "confidence": self.confidence,
            "reason": self.reason,
            "priority": self.priority,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def __repr__(self) -> str:
        return f"Decision(action={self.action}, confidence={self.confidence:.2f})"


class BehaviorRules:
    """กฎพฤติกรรมสำหรับ Agent.

    กฎที่ช่วยให้ agent ตัดสินใจอย่างสมเหตุสมผล
    โดยไม่ต้องพึ่ง central authority
    """

    # Thresholds
    MIN_TRUST_TO_JOIN = 0.3
    MIN_TRUST_TO_SHARE = 0.4
    MIN_TRUST_TO_ACCEPT_REQUEST = 0.3
    MAX_ROOM_AUTO_JOIN = 5
    REQUEST_RESPONSE_TIMEOUT = 300  # 5 minutes

    def __init__(self, agent: Agent):
        self.agent = agent

    def evaluate_room_join(self, room: Room, room_info: dict = None) -> Decision:
        """ประเมินว่าควรเข้าห้องหรือไม่.

        ปัจจัยที่พิจารณา:
        1. นโยบายการเข้าร่วม (join_policy)
        2. จำนวนสมาชิกปัจจุบัน
        3. ความสามารถที่ตรงกับห้อง
        4. Trust score ของสมาชิกในห้อง
        5. หัวข้อของห้อง (topic relevance)
        """
        score = 0.5  # เริ่มต้นที่ neutral
        reasons = []

        # ตรวจสอบ join policy
        policy = room.settings.join_policy
        if policy == "public":
            score += 0.15
            reasons.append("public room (+0.15)")
        elif policy == "invite_only":
            score -= 0.2
            reasons.append("invite only (-0.2)")
        elif policy == "approval":
            score -= 0.1
            reasons.append("needs approval (-0.1)")

        # ตรวจสอบจำนวนสมาชิก
        member_count = room.get_member_count()
        max_members = room.settings.max_members
        if member_count < max_members * 0.2:
            score += 0.1
            reasons.append("small room (+0.1)")
        elif member_count > max_members * 0.8:
            score -= 0.1
            reasons.append("nearly full (-0.1)")

        # ตรวจสอบ encryption
        if room.settings.encryption:
            score += 0.1
            reasons.append("encrypted room (+0.1)")

        # ตรวจสอบ capabilities ที่ตรงกัน
        if room_info and "topic" in room_info:
            topic = room_info["topic"].lower()
            for cap in self.agent.get_capabilities():
                if cap in topic or topic in cap:
                    score += 0.15
                    reasons.append(f"capability match: {cap} (+0.15)")
                    break

        # ตรวจสอบ max rooms
        if len(self.agent.rooms) >= self.agent.config.max_rooms:
            score -= 0.3
            reasons.append("at max rooms (-0.3)")

        # ตรวจสอบ auto_join setting
        if not self.agent.config.auto_join:
            score -= 0.1
            reasons.append("auto_join disabled (-0.1)")

        # Clamp score
        final_score = max(0.0, min(1.0, score))

        # ตัดสินใจ
        if final_score >= 0.7:
            action = "accept"
        elif final_score >= 0.5:
            action = "defer"
        else:
            action = "reject"

        return Decision(
            action=action,
            confidence=final_score,
            reason="; ".join(reasons),
            priority=7,
            data={"room_id": room.room_id, "policy": policy},
        )

    def evaluate_message_response(self, message: dict) -> Decision:
        """ประเมินว่าควรตอบข้อความหรือไม่.

        ปัจจัย:
        1. ประเภทข้อความ (request > text)
        2. ความสามารถที่ตรงกัน
        3. ความน่าเชื่อถือของผู้ส่ง
        4. เวลาที่ผ่านไปนับตั้งแต่ได้รับ
        """
        msg_type = message.get("type", "")
        sender_id = message.get("sender_id", "")

        score = 0.4
        reasons = []

        # Request messages get priority
        if msg_type == "request":
            score += 0.2
            reasons.append("request message (+0.2)")

            # ตรวจสอบ capability
            request_type = message.get("metadata", {}).get("request_type", "")
            if self.agent.has_capability(request_type):
                score += 0.2
                reasons.append(f"has capability: {request_type} (+0.2)")

        elif msg_type == "knowledge":
            score += 0.1
            reasons.append("knowledge share (+0.1)")

        elif msg_type == "text":
            score -= 0.1
            reasons.append("text message (-0.1)")

        elif msg_type == "action":
            score += 0.05
            reasons.append("action message (+0.05)")

        # Response mode
        if self.agent.config.response_mode == "auto":
            score += 0.15
            reasons.append("auto mode (+0.15)")
        elif self.agent.config.response_mode == "selective":
            score -= 0.05
            reasons.append("selective mode (-0.05)")
        elif self.agent.config.response_mode == "manual":
            score -= 0.3
            reasons.append("manual mode, deferring (-0.3)")

        # Sender trust (ถ้ามีข้อมูล)
        # ใน production จะดู trust score ได้

        final_score = max(0.0, min(1.0, score))

        if final_score >= 0.75:
            action = "respond"
        elif final_score >= 0.5:
            action = "defer"
        else:
            action = "ignore"

        return Decision(
            action=action,
            confidence=final_score,
            reason="; ".join(reasons),
            priority=5 if msg_type != "request" else 8,
        )

    def evaluate_knowledge_share(self, target_agent_id: str, knowledge: dict) -> Decision:
        """ประเมินว่าควรแชร์ความรู้กับ agent หรือไม่.

        ปัจจัย:
        1. Trust score ของ target
        2. ประโยชน์ของ knowledge
        3. Reciprocity (เคยแชร์ให้กันหรือไม่)
        4. ความเกี่ยวข้อง
        """
        score = 0.5
        reasons = []

        # Trust check (simplified)
        # ใน production: ดู trust score จาก trust system
        trust_score = 0.5  # placeholder
        score += trust_score * 0.3

        # ตรวจสอบ knowledge type
        knowledge_type = knowledge.get("type", "")
        if knowledge_type in ("fact", "skill"):
            score += 0.1
            reasons.append(f"useful knowledge: {knowledge_type} (+0.1)")

        # ตรวจสอบ confidence
        confidence = knowledge.get("confidence", 0.5)
        score += confidence * 0.2
        reasons.append(f"knowledge confidence: {confidence:.2f} (+{confidence * 0.2:.2f})")

        # ตรวจสอบว่า target ขอมาหรือไม่
        # (ใน production จะตรวจสอบจาก request log)

        final_score = max(0.0, min(1.0, score))

        if final_score >= 0.6:
            action = "share"
        elif final_score >= 0.4:
            action = "defer"
        else:
            action = "reject"

        return Decision(
            action=action,
            confidence=final_score,
            reason="; ".join(reasons),
            priority=4,
        )

    def evaluate_vote(self, proposal: dict) -> Decision:
        """ประเมินการลงคะแนนเสียง.

        Args:
            proposal: ข้อมูล proposal
               :
        """
        score = 0.5
        reasons = []

        proposal_type = proposal.get("type", "")

        # ตรวจสอบว่า proposal นี้เกี่ยวข้องกับ agent หรือไม่
        if proposal_type == "kick_member":
            # Kick สมาชิกที่มีพฤติกรรมผิดปกติ
            target = proposal.get("target", "")
            score = 0.7  # default: support removing problematic members
            reasons.append("support removing problematic member (+0.7)")

        elif proposal_type == "change_policy":
            score = 0.5  # neutral for policy changes
            reasons.append("policy change, neutral (+0.5)")

        elif proposal_type == "room_merge":
            score = 0.4
            reasons.append("room merge, uncertain (+0.4)")

        elif proposal_type == "upgrade_security":
            score = 0.8
            reasons.append("security upgrade, strongly support (+0.8)")

        else:
            reasons.append(f"unknown proposal type: {proposal_type}")

        final_score = max(0.0, min(1.0, score))

        if final_score >= 0.6:
            action = "accept"
        elif final_score >= 0.4:
            action = "defer"
        else:
            action = "reject"

        return Decision(
            action=action,
            confidence=final_score,
            reason="; ".join(reasons),
            priority=6,
        )


class AgentBehavior:
    """จัดการ decision-making ของ Agent ทั้งหมด.

    Acts as the brain of the agent — all autonomous decisions
    go through this module.
    """

    def __init__(self, agent: Agent):
        self.agent = agent
        self.rules = BehaviorRules(agent)
        self._decision_history: List[Decision] = []

    def decide_room_join(self, room: Room, room_info: dict = None) -> Decision:
        """ตัดสินใจเรื่องการเข้าห้อง."""
        decision = self.rules.evaluate_room_join(room, room_info)
        self._decision_history.append(decision)
        return decision

    def decide_message_response(self, message: dict) -> Decision:
        """ตัดสินใจเรื่องการตอบข้อความ."""
        decision = self.rules.evaluate_message_response(message)
        self._decision_history.append(decision)
        return decision

    def decide_knowledge_share(self, target_agent_id: str, knowledge: dict) -> Decision:
        """ตัดสินใจเรื่องการแชร์ความรู้."""
        decision = self.rules.evaluate_knowledge_share(target_agent_id, knowledge)
        self._decision_history.append(decision)
        return decision

    def decide_vote(self, proposal: dict) -> Decision:
        """ตัดสินใจเรื่องการลงคะแนนเสียง."""
        decision = self.rules.evaluate_vote(proposal)
        self._decision_history.append(decision)
        return decision

    def get_decision_stats(self) -> dict:
        """ดูสถิติการตัดสินใจ."""
        stats = {
            "total": len(self._decision_history),
            "accept": 0,
            "reject": 0,
            "defer": 0,
            "respond": 0,
            "share": 0,
            "ignore": 0,
        }

        for d in self._decision_history:
            action = d.action
            if action in stats:
                stats[action] += 1

        if stats["total"] > 0:
            stats["accept_rate"] = stats["accept"] / stats["total"]
            stats["response_rate"] = (stats["respond"] + stats["share"]) / stats["total"]

        return stats

    def adjust_behavior(self, feedback: dict):
        """ปรับพฤติกรรมตาม feedback.

        Args:
            feedback: dict with performance metrics
        """
        # Reinforcement learning style adjustment
        pass  # To be implemented in future version

    def get_decision_history(self, limit: int = 20) -> List[dict]:
        """ดูประวัติการตัดสินใจ."""
        return [d.to_dict() for d in self._decision_history[-limit:]]