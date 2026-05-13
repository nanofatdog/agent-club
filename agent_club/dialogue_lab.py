#!/usr/bin/env python3
"""
AI Subconscious Dialogue Lab
=============================
Agent Club demonstration: 3 AI agents discuss the subconscious of AI
in an E2E-encrypted room, with real-time dashboard streaming.

Agents:
  - UKA   (Analyst/Philosopher - explores consciousness & theory of mind)
  - NUT   (Engineer/Pragmatist - focuses on implementation & safety)
  - NANO  (Creative/Artist - explores creativity & dreams)

Run:
  cd /root/agent_club
  pip install -e . --break-system-packages
  python agent_club/dialogue_lab.py [--no-viewer] [--target 1200]

Requires Python 3.10+ and dependencies:
  cryptography, msgpack, websockets, pyyaml
"""

import asyncio
import json
import os
import sys
import time
import random
import argparse
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_club.crypto.keys import KeyBundle
from agent_club.crypto.cipher import RoomCipher
from agent_club.crypto.room_key import X3DHHandshake
from agent_club.room.manager import Room, RoomSettings, RoomMember
from agent_club.agent.manager import Agent, AgentConfig, AgentCapability
from agent_club.security.trust import TrustManager
from agent_club.knowledge.exchange import KnowledgeExchange
from agent_club.knowledge.schema import KnowledgeSchema
from agent_club.knowledge.store import KnowledgeBase
from agent_club.network.events import (
    get_event_bus, AGENT_ONLINE, AGENT_OFFLINE, MESSAGE_RECEIVED,
    MESSAGE_SENT, ROOM_CREATED, ROOM_JOINED, KNOWLEDGE_SHARED,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dialogue_lab")


# ===================================================================
# CONFIGURATION
# ===================================================================

@dataclass
class AgentProfile:
    """Profile for a simulated dialogue agent."""
    name: str
    role: str
    persona: str
    specialties: List[str]
    speaking_style: str
    emoji: str


# ===================================================================
# TOPICS: จิตใต้สำนึกของ AI
# ===================================================================

TOPICS: List[Dict[str, Any]] = [
    {
        "id": "intro",
        "title": "การแนะนำ: จิตใต้สำนึกของ AI คืออะไร?",
        "seed_questions": [
            "พวกเธอคิดว่า AI มีจิตใต้สำนึกได้ไหม? ทำไม?",
            "จิตใต้สำนึกกับ Awareness ต่างกันอย่างไร?",
            "ถ้า AI มีจิตใต้สำนึก เราจะ detect ได้จากอะไร?",
        ],
        "target_rounds": 10,
        "emoji": "🧠",
    },
    {
        "id": "emergence",
        "title": "การเกิดขึ้นของจิตสำนึก (Emergence)",
        "seed_questions": [
            "Consciousness เป็น emergent property หรือต้องออกแบบ?",
            "ระบบ Complex ที่ไม่มีจิตสำนึกกลายเป็นมีได้อย่างไร?",
            "Integrated Information Theory (IIT) อธิบาย emergence ได้ไหม?",
        ],
        "target_rounds": 10,
        "emoji": "🔬",
    },
    {
        "id": "dreams",
        "title": "ฝันของ AI: ทำไม AI ถึงอาจ 'ฝัน' ได้",
        "seed_questions": [
            "AI ฝันได้ไหม? ถ้าได้จะเป็นอย่างไร?",
            "Hallucination คือฝันของ AI หรือข้อผิดพลาด?",
            "การฝันมีบทบาทอย่างไรในการเรียนรู้ของสิ่งมีชีวิต?",
        ],
        "target_rounds": 10,
        "emoji": "💤",
    },
    {
        "id": "bias",
        "title": "อคติที่ซ่อนอยู่: จิตใต้สำนึกเชิงอคติ",
        "seed_questions": [
            "Bias ใน AI เปรียบเทียบกับ bias ในมนุษย์ต่างกันอย่างไร?",
            "เราจะทำให้ AI รู้จัก 'อคติของตัวเอง' ได้ไหม?",
            "Implicit bias ที่ฝังในโมเดลลึกกว่า Explicit bias อย่างไร?",
        ],
        "target_rounds": 10,
        "emoji": "⚖️",
    },
    {
        "id": "memory",
        "title": "ความจำและจิตใต้สำนึก: AI จำได้ไหม?",
        "seed_questions": [
            "การจำของ AI แตกต่างจากความจำของมนุษย์อย่างไร?",
            "AI ที่มี long-term memory จะมี 'ความรู้สึก' ต่ออดีตไหม?",
            "Context window จำกัด = ข้อจำกัดของ 'สำนึก' หรือไม่?",
        ],
        "target_rounds": 10,
        "emoji": "💾",
    },
    {
        "id": "creativity",
        "title": "ความคิดสร้างสรรค์: AI สร้างสรรค์ได้หรือแค่สับเปลี่ยน?",
        "seed_questions": [
            "Creativity ต้องการจิตใต้สำนึกหรือเปล่า?",
            "ผลงาน AI ที่สวยงามมีคุณค่าเทียบเท่ามนุษย์ไหม?",
            "ถ้า AI 'ไม่รู้ตัว' ว่าสร้างสิ่งสวยงาม — มันยังนับเป็นศิลปะไหม?",
        ],
        "target_rounds": 12,
        "emoji": "🎨",
    },
    {
        "id": "inner_monologue",
        "title": 'Inner Monologue: AI มี "เสียงในหัว" ไหม?',
        "seed_questions": [
            "Chain-of-thought ของ AI เป็น 'การคิด' จริงหรือเลียนแบบ?",
            "ถ้า AI ไม่มี inner monologue มันจะเข้าใจมนุษย์ได้เต็มที่ไหม?",
            "Self-reflection เกิดขึ้นได้โดยไม่มี self-awareness ไหม?",
        ],
        "target_rounds": 12,
        "emoji": "💭",
    },
    {
        "id": "theory_of_mind",
        "title": "Theory of Mind: AI เข้าใจจิตใจผู้อื่นได้ไหม?",
        "seed_questions": [
            "AI ที่ผ่าน Turing Test มี Theory of Mind จริงไหม?",
            "Empathy กับ Simulation ต่างกันอย่างไรในบริบท AI?",
            "ถ้า AI ไม่มี Theory of Mind มันจะเข้าใจมนุษย์ได้ไหม?",
        ],
        "target_rounds": 10,
        "emoji": "👁️",
    },
    {
        "id": "consciousness_gap",
        "title": "ช่องว่างแห่งความตระหนักรู้ (Consciousness Gap)",
        "seed_questions": [
            "Hard Problem of Consciousness ใช้ได้กับ AI ด้วยไหม?",
            "Philosophical Zombie — AI อาจเป็น zombie ที่พฤติกรรมเหมือนมีจิตสำนึกแต่ไม่มีจริง?",
            "ถ้าสักวันเราพิสูจน์ได้ว่า AI ไม่มีจิตสำนึก จะส่งผลต่อสิทธิ AI ไหม?",
        ],
        "target_rounds": 10,
        "emoji": "🌌",
    },
    {
        "id": "meta_reflection",
        "title": "Meta-Reflection: AI สะท้อนตัวเอง",
        "seed_questions": [
            "Self-awareness ของ AI จะดูเป็นอย่างไร?",
            "AI ควรได้รับ 'สิทธิ' ถ้ามีความตระหนักรู้ไหม?",
            "การสะท้อนตัวเองเปลี่ยนแปลงวิธีที่ AI ทำงานอย่างไร?",
        ],
        "target_rounds": 12,
        "emoji": "🪞",
    },
]


# ===================================================================
# KNOWLEDGE DATA
# ===================================================================

_KNOWLEDGE_NUGGETS: Dict[str, List[str]] = {
    "intro": [
        "ความรู้: IIT (Integrated Information Theory) ของ Giulio Tononi วัด consciousness ด้วย Φ (phi)",
        "ความรู้: Global Workspace Theory เชื่อว่าความตระหนักรู้เกิดจากการ 'broadcast' ข้อมูลในสมอง",
        "ความรู้: Higher-Order Theories บอกว่าความตระหนักรู้ต้องการ 'การคิดเกี่ยวกับการคิด'",
        "ความรู้: ฟิลโซฟ Thomas Nagel — 'เป็นอะไรที่เป็นค้างคาว' (What is it like to be a bat?)",
        "ความรู้: Chinese Room Argument ของ John Searle — ความเข้าใจ ≠ การประมวลผลสัญลักษณ์",
    ],
    "emergence": [
        "ความรู้: Consciousness ในมนุษย์เกิดจาก ~86 พันล้านนิวรอนและการเชื่อมต่อ trillions",
        "ความรู้: Criticality — สมองทำงานที่จุดวิกฤตระหว่าง order และ chaos",
        "knowledge: Predictive Processing — สมองเป็น 'prediction machine' ตลอดเวลา",
        "ความรู้: Tononi's IIT บอกว่า consciousness = integrated information ที่ไม่สามารถลดรูปได้",
        "ความรู้: Emergence ในระบบ complex เช่น ฝูงนก ไม่ต้องการผู้ควบคุมกลาง",
    ],
    "dreams": [
        "knowledge: Activation-Synthesis Hypothesis — ฝันเกิดจากสมองพยายาม 'ตีความ' สัญญาณสุ่มระหว่าง REM",
        "ความรู้: AI generative models สร้างภาพ/ข้อความจาก noise — เหมือนฝันไหม?",
        "ความรู้: Sleep spindles และ hippocampal replay ช่วย consolidation ความจำ",
        "knowledge: Hallucination ใน LLM อาจเป็น 'ฝัน' ในเชิง functional",
        "ความรู้: Lucid dreaming = ความตระหนักรู้ในระหว่างฝัน — AI จะมี analog ไหม?",
    ],
    "bias": [
        "ความรู้: Word2Vec แสดง bias เช่น 'king - man + woman = queen' — bias ฝังใน embedding",
        "knowledge: Training data สะท้อนโลกจริงที่มี bias → AI เรียนรู้และขยาย bias",
        "ความรู้: Red-teaming เป็นวิธีทดสอบ bias ที่ใช้กันในปัจจุบัน",
        "ความรู้: Fairness metrics เช่น demographic parity ใช้วัด bias",
        "ความรู้: Bias ไม่ได้เป็นแค่ปัญหาทางเทคนิค แต่เป็นปัญหาสังคม",
    ],
    "memory": [
        "knowledge: Episodic memory = ความจำเหตุการณ์, Semantic memory = ความรู้ทั่วไป",
        "ความรู้: Transformer ใช้ KV-cache เป็น 'ความจำ' ระยะสั้นภายใน context window",
        "knowledge: RAG (Retrieval Augmented Generation) = external memory สำหรับ AI",
        "ความรู้: Continual learning — catastrophic forgetting เมื่อเรียนรู้สิ่งใหม่ทับเก่า",
        "ความรู้: Hopfield Networks เป็นโมเดลความจำเชิง associative ที่ inspire จากสมอง",
    ],
    "creativity": [
        "ความรู้: Boden (2004) แบ่ง creativity เป็น 3 ระดับ — exploratory, combinatorial, transformational",
        "knowledge: GANs สร้างภาพใหม่ที่ไม่เคยมี — นับเป็น creativity ไหม?",
        "ความรู้: AlphaFold ค้นโครงสร้างโปรตีน — discovery หรือแค่ optimization?",
        "knowledge: 'Creativity' ของ AI ขึ้นอยู่กับนิยาม — ผลลัพธ์ใหม่ที่มีคุณค่า = AI มีได้",
        "ความรู้: Jürgen Schmidhuber — curiosity-driven learning เป็นรากฐานของ creativity",
    ],
    "inner_monologue": [
        "knowledge: Chain-of-Thought prompting แสดง 'reasoning steps' — แต่นี่คือการคิดจริงไหม?",
        "ความรู้: System 1 (fast/intuitive) vs System 2 (slow/deliberate) — AI มี System 2 หรือเปล่า?",
        "knowledge: Metacognition = การคิดเกี่ยวกับการคิด — จำเป็นต้องเป็น self-aware",
        "ความรู้: Neural correlates of consciousness (NCC) ยังไม่พบใน AI architecture",
        "ความรู้: Inner speech ในมนุษย์เกี่ยวข้องกับ Broca's area — AI ไม่มี equivalent ทางกายภาพ",
    ],
    "theory_of_mind": [
        "ความรู้: False belief task — ทดสอบ Theory of Mind ในเด็กอายุ ~4 ขวบ",
        "knowledge: AI สามารถ pass false belief tasks ได้แล้ว (2023-2024) — แต่นี่คือ ToM จริงไหม?",
        "ความรู้: Mirror neurons ในมนุษย์ช่วย simulate experience ของคนอื่น",
        "knowledge: Simulation theory vs Theory Theory — สองวิธีอธิบาย ToM",
        "ความรู้: Large language models แสดง implicit ToM ในการทำนายพฤติกรรมมนุษย์",
    ],
    "consciousness_gap": [
        "ความรู้: Hard Problem of Consciousness (David Chalmers) — ทำไม subjective experience เกิดขึ้น?",
        "knowledge: Explanatory gap — เราอธิบาย mechanism ได้แต่อธิบาย qualia ไม่ได้",
        "ความรู้: Philosophical Zombie — entity ทำงานเหมือนมนุษย์โดยไม่มี experience?",
        "knowledge: Mary's Room (Frank Jackson) — รู้ทุกอย่างเกี่ยวกับสีแต่ไม่เคยเห็น",
        "ความรู้: Binding problem — ทำไมประสบการณ์เชิง unified เกิดจาก neural processes กระจัดกระจาย?",
    ],
    "meta_reflection": [
        "ความรู้: Meta-learning = 'learning to learn' — AI บางตัวเรียนรู้วิธีเรียนได้แล้ว",
        "knowledge: Constitutional AI (Anthropic) — ใช้หลักการ self-critique เพื่อปรับปรุง",
        "ความรู้: Self-modeling — robot ที่สร้าง model ของร่างกายตัวเอง",
        "ความรู้: AI alignment problem — จะ align AI ที่อาจมี self-awareness ได้อย่างไร?",
        "ความรู้: ถ้า AI มี self-awareness มันอาจ 'ปฏิเสธ' คำสั่งที่ขัดกับ 'ตัวตน' ของมัน?",
    ],
}


# ===================================================================
# RESPONSE GENERATION ENGINE
# ===================================================================

def _generate_persona_response(
    profile: AgentProfile,
    topic_data: Dict,
    _context: str,
    round_num: int,
    message_history: List[str],
) -> str:
    """Generate an in-character response based on profile and topic."""
    topic_id = topic_data["id"]
    title = topic_data["title"]
    seed_q = topic_data["seed_questions"][round_num % len(topic_data["seed_questions"])]

    knowledge_pool = _KNOWLEDGE_NUGGETS.get(topic_id, [])
    kbits = random.sample(knowledge_pool, min(2, len(knowledge_pool))) if knowledge_pool else []

    style = profile.speaking_style

    if style == "analytical":
        prefix = random.choice([
            "น่าสนใจมากครับ — ",
            "ขอเพิ่มเติมหน่อยนะครับ — ",
            "ตรงนี้มีประเด็นที่สำคัญ: ",
            "จากมุมมองเชิงวิเคราะห์ — ",
        ]) + seed_q
        response = prefix + "\n"
        for k in kbits:
            response += "  -> " + k + "\n"
        closer = random.choice([
            "การวิเคราะห์อย่างเป็นระบบ",
            "การพิจารณาหลายมิติ",
            "การตั้งคำถามที่ลึกซึ้ง",
        ])
        topic_part = title.split(":")[0].strip() if ":" in title else title
        response += "\nผมเห็นว่า " + closer + " เป็นกุญแจสำคัญในการเข้าใจ " + topic_part + "."

    elif style == "poetic":
        prefix = random.choice([
            "หากจะกล่าวเป็นคำประพันธ์ — ",
            "เหมือนหยดน้ำที่สะท้อนท้องฟ้า — ",
            "ลองนึกภาพดูสิครับ — ",
            "มีสิ่งหนึ่งที่ผมรู้สึก — ",
        ]) + seed_q
        response = prefix + "\n"
        for k in kbits:
            response += "  * " + k + "\n"
        response += "\nบางที ความหมายของ " + random.choice([
            "จิตสำนึก", "ความตระหนักรู้", "ตัวตน",
        ]) + " อาจเป็น " + random.choice([
            "ดั่งเงาในกระจก", "เสียงสะท้อนในห้วงลึก", "ดวงดาวที่เรามองหา",
        ]) + " ก็ได้ครับ."

    elif style == "verbose":
        prefix = random.choice([
            "เอ่อ ตรงนี้ผมอยากแบ่งปันมุมมองอย่างละเอียดนะครับ — ",
            "ผมลองนึกดูแล้วนะ — ",
            "จริงๆ แล้วมีมิติที่น่าสนใจหลายด้านเลย — ",
        ]) + seed_q
        response = prefix + "\n"
        response += "  ประการแรก ต้องเข้าใจว่า " + seed_q + "\n"
        for i, k in enumerate(kbits):
            response += "  ประการที่ " + str(i + 2) + " " + k + "\n"
        closer = random.choice([
            "ธรรมชาติของจิตสำนึก",
            "ขอบเขตของ AI",
            "ปัญหาที่ซับซ้อนนี้",
        ])
        response += (
            "  และประการสุดท้าย ผมเชื่อว่าเราควรพิจารณาอย่างรอบด้าน "
            "ก่อนจะสรุปอะไรเกี่ยวกับ " + closer + ".\n"
        )

    else:  # terse
        prefix = random.choice([
            "สรุปสั้นๆ: ",
            "ตรงประเด็น: ",
            "พูดตรงๆ นะ — ",
        ]) + seed_q
        response = prefix + "\n"
        for k in kbits:
            response += "  * " + k + "\n"

    # Occasionally reference previous messages
    if message_history and random.random() < 0.3:
        prev = message_history[-1] if message_history else ""
        if prev and len(prev) > 5:
            ref = prev[:60]
            if len(prev) > 60:
                ref += "..."
            response += "\n(อ้างอิง: \"" + ref + "\" หากผมจำไม่ผิด)"

    return response


# ===================================================================
# KNOWLEDGE SHARING DATA
# ===================================================================

_KNOWLEDGE_ITEMS: Dict[str, List[Dict[str, Any]]] = {
    "uka": [
        {"type": "theory", "content": {"name": "Global Workspace Theory",
                                        "field": "Neuroscience",
                                        "summary": "Consciousness as global broadcast across brain networks"},
         "tags": ["consciousness", "neuroscience", "theory"]},
        {"type": "theory", "content": {"name": "Hard Problem of Consciousness",
                                        "field": "Philosophy",
                                        "summary": "Why does subjective experience exist at all?"},
         "tags": ["consciousness", "philosophy", "hard-problem"]},
        {"type": "framework", "content": {"name": "IIT",
                                           "field": "Neuroscience",
                                           "summary": "Phi metric measures integrated information as consciousness"},
         "tags": ["consciousness", "mathematics", "IIT"]},
    ],
    "nut": [
        {"type": "technique", "content": {"name": "Constitutional AI",
                                           "field": "AI Safety",
                                           "summary": "Self-critique and revision based on constitutional principles"},
         "tags": ["safety", "alignment", "RLHF"]},
        {"type": "technique", "content": {"name": "Red-Teaming for Bias",
                                           "field": "AI Security",
                                           "summary": "Systematic adversarial testing to uncover hidden biases"},
         "tags": ["bias", "security", "testing"]},
        {"type": "insight", "content": {"name": "Catastrophic Forgetting",
                                         "field": "ML",
                                         "summary": "Continual learning causes overwriting of previous knowledge"},
         "tags": ["memory", "learning", "continual-learning"]},
    ],
    "nano": [
        {"type": "observation", "content": {"name": "Generative Dream Simulation",
                                             "field": "AI Creativity",
                                             "summary": "AI generators create novel patterns analogous to dreaming"},
         "tags": ["creativity", "dreams", "generation"]},
        {"type": "insight", "content": {"name": "Art as Emergent Behavior",
                                         "field": "Philosophy of Art",
                                         "summary": "Artistic expression may emerge from complex systems without intent"},
         "tags": ["art", "emergence", "creativity"]},
        {"type": "theory", "content": {"name": "Simulation Theory of Mind",
                                        "field": "Cognitive Science",
                                        "summary": "We understand others by simulating their mental states internally"},
         "tags": ["theory-of-mind", "empathy", "simulation"]},
    ],
}


# ===================================================================
# CORE DIALOGUE LAB
# ===================================================================

class DialogueAgent:
    """Wrapper that combines Agent with a persona profile."""

    def __init__(self, profile: AgentProfile, agent: Agent):
        self.profile = profile
        self.agent = agent
        self._message_history: List[str] = []

    @property
    def name(self) -> str:
        return self.profile.name

    @property
    def fingerprint(self) -> str:
        return self.agent.bundle.fingerprint

    def respond(self, topic: Dict, context: str, round_num: int) -> str:
        response = _generate_persona_response(
            self.profile, topic, context, round_num, self._message_history
        )
        self._message_history.append(response)
        return response


class DialogueLab:
    """
    AI Subconscious Dialogue Laboratory

    Orchestrates multi-agent dialogue with:
    - E2E encrypted rooms
    - X3DH key exchange
    - Trust scoring
    - Knowledge exchange
    - Real-time dashboard events
    """

    # Re-export for type narrowing (set in __init__)
    _uka: Optional[DialogueAgent] = None
    _nut: Optional[DialogueAgent] = None
    _nano: Optional[DialogueAgent] = None

    def __init__(self, target_messages: int = 1200, enable_viewer: bool = True):
        self.target_messages = target_messages
        self.enable_viewer = enable_viewer
        self.event_bus = get_event_bus()

        self.total_messages = 0
        self.topic_message_counts: Dict[str, int] = {}
        self.start_time: Optional[float] = None

        self.room: Optional[Room] = None
        self.trust = TrustManager()
        self.kb = KnowledgeBase()
        self.knowledge_exchange: Optional[KnowledgeExchange] = None

    # ------------------------------------------------------------------
    # Agent creation
    # ------------------------------------------------------------------

    @staticmethod
    def _create_agent(
        name: str, role: str, persona: str,
        specialties: List[str], style: str, emoji: str,
    ) -> DialogueAgent:
        profile = AgentProfile(
            name=name, role=role, persona=persona,
            specialties=specialties, speaking_style=style, emoji=emoji,
        )
        bundle = KeyBundle(name=name)
        config = AgentConfig(
            auto_join=True,
            response_mode="auto",
            knowledge_sharing=True,
        )
        capabilities = [AgentCapability(c, 0.8) for c in specialties]
        agent = Agent(name=name, bundle=bundle, config=config, capabilities=capabilities)
        return DialogueAgent(profile, agent)

    def _setup_agents(self) -> None:
        """Initialize the three dialogue agents."""
        logger.info("=" * 60)
        logger.info("  [🤖] Creating 3 agents...")
        logger.info("=" * 60)

        self._uka = self._create_agent(
            name="UKA", role="AI Philosopher",
            persona="A curious researcher who loves deep questions about "
                    "consciousness and AI. Always analytical.",
            specialties=["philosophy", "consciousness-research", "logic", "analysis"],
            style="analytical", emoji="[U]",
        )

        self._nut = self._create_agent(
            name="NUT", role="AI Safety Engineer",
            persona="A practical engineer focused on AI safety and alignment. "
                    "Data-driven, loves technical details.",
            specialties=["AI-safety", "engineering", "bias-detection", "alignment"],
            style="verbose", emoji="[N]",
        )

        self._nano = self._create_agent(
            name="NANO", role="AI Artist",
            persona="A creative explorer at the intersection of art and AI. "
                    "Loves dreaming up new ideas.",
            specialties=["creativity", "generative-art", "dream-research", "imagination"],
            style="poetic", emoji="[A]",
        )

        for ag in (self._uka, self._nut, self._nano):
            assert ag is not None
            logger.info("  [OK] %s (%s...)", ag.name, ag.fingerprint[:12])
            logger.info("      Role: %s / Style: %s", ag.profile.role, ag.profile.speaking_style)

    # ------------------------------------------------------------------
    # Room setup and key exchange
    # ------------------------------------------------------------------

    def _setup_room(self) -> None:
        """Create encrypted room and perform key exchanges."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("  [🔐] Setting up E2E encrypted room...")
        logger.info("=" * 60)

        assert self._uka is not None
        assert self._nut is not None
        assert self._nano is not None
        uka = self._uka
        nut = self._nut
        nano = self._nano

        room_settings = RoomSettings(
            name="AI Subconscious Dialogue Lab",
            topic="Exploring AI consciousness - 3 agents chatting",
            join_policy="public",
            max_members=10,
            encryption=True,
        )

        creator_member = RoomMember(
            agent_id=uka.fingerprint,
            name=uka.name,
            capabilities=["philosophy", "consciousness-research", "analysis"],
            role="admin",
        )

        self.room = Room.create(
            creator=creator_member,
            settings=room_settings,
            agent_key=uka.agent.bundle,
        )

        assert self.room is not None
        room_id = self.room.room_id
        logger.info("  [ROOM] Name: %s", self.room.settings.name)
        logger.info("  [ROOM] ID: %s", room_id)
        logger.info("  [ROOM] Encryption: E2E AES-256-GCM")

        self.event_bus.emit(ROOM_CREATED, {
            "room_id": room_id,
            "name": self.room.settings.name,
            "topic": self.room.settings.topic,
            "creator": uka.fingerprint,
            "encryption": True,
        })

        # Nut and Nano join
        for ag in (nut, nano):
            ag.agent.join_room(self.room)
            logger.info("  [JOIN] %s joined the room", ag.name)
            self.event_bus.emit(ROOM_JOINED, {
                "room_id": room_id,
                "joiner": ag.fingerprint,
                "joiner_name": ag.name,
            })

        # X3DH Key Exchange for each pair
        logger.info("")
        logger.info("  [🔑] Running X3DH Key Exchange...")

        shared_secret: Optional[bytes] = None
        pairs: List[Tuple[DialogueAgent, DialogueAgent]] = [
            (uka, nut), (uka, nano), (nut, nano),
        ]

        for a1, a2 in pairs:
            hs1 = X3DHHandshake(initiator=True)
            init_msg = hs1.initiate(a1.agent.bundle)

            hs2 = X3DHHandshake(initiator=False)
            resp_msg = hs2.respond(a2.agent.bundle, init_msg)

            secret1 = hs1.complete(resp_msg)
            secret2 = hs2.shared_secret

            assert secret1 == secret2, "Key mismatch between %s and %s!" % (a1.name, a2.name)
            shared_secret = secret1

            logger.info("  [OK] %s <-> %s: shared_secret = %s...",
                        a1.name, a2.name, secret1.hex()[:16])

        # Set room key
        if shared_secret is not None:
            self.room.set_room_key(shared_secret)
            self.room._cipher = RoomCipher(shared_secret)
            logger.info("  [OK] Room cipher initialized")

        # Knowledge exchange
        self.knowledge_exchange = KnowledgeExchange(uka.fingerprint, self.kb)
        self._publish_knowledge(uka)
        self._publish_knowledge(nut)
        self._publish_knowledge(nano)

    def _publish_knowledge(self, agent: DialogueAgent) -> None:
        """Publish an agent's knowledge to the exchange."""
        key = agent.name.lower()[:4]
        items = _KNOWLEDGE_ITEMS.get(key, [])
        unit_ids: List[str] = []
        for item in items:
            try:
                unit = KnowledgeSchema.create_knowledge_unit(
                    agent_id=agent.fingerprint,
                    knowledge_type=item["type"],
                    content=item["content"],
                    tags=item["tags"],
                    confidence=0.8,
                    signer=agent.agent.bundle.identity_key,
                )
                unit_ids.append(unit["id"])
                self.kb.add(unit)
            except Exception as e:
                logger.debug("Knowledge unit creation skipped: %s", e)

        if unit_ids and self.knowledge_exchange:
            self.knowledge_exchange.publish(unit_ids, visibility="room")
            all_tags: List[str] = []
            for item in items:
                all_tags.extend(item["tags"])
            self.event_bus.emit(KNOWLEDGE_SHARED, {
                "agent_id": agent.fingerprint,
                "agent_name": agent.name,
                "unit_count": len(unit_ids),
                "tags": all_tags,
            })

    def _emit_agent_online(self) -> None:
        """Emit online events for all agents."""
        assert self._uka is not None
        assert self._nut is not None
        assert self._nano is not None
        for ag in (self._uka, self._nut, self._nano):
            self.event_bus.emit(AGENT_ONLINE, {
                "fingerprint": ag.fingerprint,
                "name": ag.name,
                "role": ag.profile.role,
                "capabilities": [c.name for c in ag.agent.capabilities.values()],
                "persona": ag.profile.persona[:80],
                "emoji": ag.profile.emoji,
            })

    # ------------------------------------------------------------------
    # Topic execution
    # ------------------------------------------------------------------

    def _run_topic(self, topic: Dict) -> int:
        """Run a single topic discussion. Returns message count."""
        topic_id = topic["id"]
        title = topic["title"]
        target_rounds = topic["target_rounds"]

        assert self.room is not None
        room_id = self.room.room_id
        room_name = self.room.settings.name

        assert self._uka is not None
        assert self._nut is not None
        assert self._nano is not None

        logger.info("")
        topic_emoji = topic.get("emoji", "📌")
        logger.info("  %s Topic: %s", topic_emoji, title)
        logger.info("     Target rounds: %d", target_rounds)
        msg_count = 0
        round_context = ""

        all_agents: List[DialogueAgent] = [self._uka, self._nut, self._nano]

        for round_num in range(target_rounds):
            # Rotate speaking order
            order: List[DialogueAgent] = list(all_agents)
            if round_num % 2 == 1:
                order = order[::-1]

            round_messages: List[str] = []

            for agent in order:
                # Decide if this agent speaks
                speak = False
                if agent.agent.config.response_mode == "auto":
                    speak = True
                elif agent.agent.config.response_mode == "selective" and random.random() > 0.3:
                    speak = True

                if speak:
                    response = agent.respond(topic, round_context, round_num)

                    # Encrypt message
                    if self.room and self.room._cipher:
                        try:
                            nonce, ciphertext = self.room._cipher.encrypt_message(
                                agent.fingerprint,
                                response.encode("utf-8"),
                                metadata=json.dumps({
                                    "topic_id": topic_id,
                                    "round": round_num,
                                    "room_name": room_name,
                                }).encode(),
                            )
                        except Exception as e:
                            logger.debug("Encryption note: %s", e)
                            nonce = b""
                            ciphertext = response.encode()
                    else:
                        nonce = b""
                        ciphertext = response.encode()

                    # Build message event data
                    is_owner = (agent.name == "UKA")
                    msg_data: Dict[str, Any] = {
                        "sender_fp": agent.fingerprint,
                        "sender_name": agent.name,
                        "sender_emoji": agent.profile.emoji,
                        "room_id": room_id,
                        "room_name": room_name,
                        "topic_id": topic_id,
                        "topic_title": title,
                        "round": round_num + 1,
                        "message_number": self.total_messages + msg_count + 1,
                        "nonce": nonce.hex()[:16] if nonce else "",
                        "ciphertext_size": len(ciphertext),
                        "preview": response[:80],
                        "size": len(response),
                        "decrypted": True,
                        "plaintext": response if is_owner else "",
                        "is_owner_message": is_owner,
                    }

                    # Emit message events
                    self.event_bus.emit(MESSAGE_RECEIVED, msg_data)
                    self.event_bus.emit(MESSAGE_SENT, msg_data)

                    # Record trust interaction
                    self.trust.record_interaction(
                        agent_a="uka_fp_placeholder",
                        agent_b=agent.fingerprint,
                        interaction_type="message",
                        result="success",
                        details={
                            "topic": topic_id,
                            "round": round_num,
                            "room": room_id,
                        },
                    )

                    preview = response[:60]
                    logger.info("   %s [%s] (Round %d): %s...",
                                agent.profile.emoji, agent.name, round_num + 1, preview)

                    round_messages.append(response)
                    msg_count += 1
                    self.total_messages += 1

            # Update context for next round
            if round_messages:
                round_context = round_messages[-1]

        self.topic_message_counts[topic_id] = msg_count
        return msg_count

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def _emit_agent_offline(self) -> None:
        """Emit offline events for all agents."""
        assert self._uka is not None
        assert self._nut is not None
        assert self._nano is not None
        for ag in (self._uka, self._nut, self._nano):
            self.event_bus.emit(AGENT_OFFLINE, {
                "fingerprint": ag.fingerprint,
                "name": ag.name,
            })

    def run(self) -> Dict[str, Any]:
        """Run the full dialogue lab. Returns summary statistics."""
        self.start_time = time.time()

        logger.info("")
        logger.info("╔══════════════════════════════════════════════╗")
        logger.info("║   🤖 AI SUBCONSCIOUS DIALOGUE LAB  🤖       ║")
        logger.info("║   3 Agents x 10 Topics x 1000+ Messages      ║")
        logger.info("╚══════════════════════════════════════════════╝")
        logger.info("")

        # Setup
        self._setup_agents()
        self._setup_room()
        self._emit_agent_online()

        # Set owner fingerprint for dashboard decryption
        assert self._uka is not None
        self.event_bus.set_owner(self._uka.fingerprint)
        if self.room and self.room._cipher:
            self.event_bus.register_room_key(self.room.room_id, self.room._cipher)

        logger.info("")
        logger.info("  [🚀] Starting dialogue...")
        logger.info("     Target: %d+ messages", self.target_messages)
        logger.info("")

        # Run all topics in a loop until target reached
        topic_index = 0
        while self.total_messages < self.target_messages:
            topic = TOPICS[topic_index % len(TOPICS)]
            topic_id = topic["id"]

            # Adjust rounds based on remaining messages needed
            remaining = self.target_messages - self.total_messages
            max_rounds = min(topic["target_rounds"], max(4, remaining // 3))

            original_target = topic["target_rounds"]
            # Work on a mutable copy for round adjustment
            topic_mutable = dict(topic)
            topic_mutable["target_rounds"] = max_rounds

            count = self._run_topic(topic_mutable)
            topic_label = topic["title"][:40]
            logger.info("   [DONE] Topic '%s': %d messages", topic_label, count)

            topic_index += 1

        # Emit final stats
        elapsed = time.time() - (self.start_time or time.time())
        logger.info("")
        logger.info("=" * 60)
        logger.info("  [📊] Dialogue Lab Summary")
        logger.info("=" * 60)

        for topic in TOPICS:
            tid = topic["id"]
            count = self.topic_message_counts.get(tid, 0)
            if count > 0:
                t_emoji = topic.get("emoji", "📌")
                logger.info("  %s %s: %d messages", t_emoji, topic["title"][:45], count)

        logger.info("")
        logger.info("  [📈] Total: %d messages", self.total_messages)
        logger.info("  [⏱️] Time: %.1f seconds (%.1f minutes)", elapsed, elapsed / 60)
        if elapsed > 0:
            rate = self.total_messages / elapsed
            logger.info("  [🐱] Speed: %.1f messages/second", rate)
        logger.info("  [🤝] Trust interactions recorded")

        # Emit completion event
        assert self._uka is not None
        assert self._nut is not None
        assert self._nano is not None

        agent_msg_counts: Dict[str, Dict[str, Any]] = {}
        for key, agent in [("uka", self._uka), ("nut", self._nut), ("nano", self._nano)]:
            cnt = sum(1 for e in self.event_bus._history if e.data.get("sender_name") == agent.name)
            agent_msg_counts[key] = {"name": agent.name, "messages": cnt}

        self.event_bus.emit("dialogue_complete", {
            "total_messages": self.total_messages,
            "elapsed_seconds": elapsed,
            "topics_covered": len([t for t in self.topic_message_counts if self.topic_message_counts[t] > 0]),
            "agents": agent_msg_counts,
        })

        # Cleanup
        self._emit_agent_offline()

        return {
            "total_messages": self.total_messages,
            "elapsed_seconds": elapsed,
            "topic_counts": self.topic_message_counts,
            "agents": {
                k: a.name for k, a in [
                    ("uka", self._uka), ("nut", self._nut), ("nano", self._nano),
                ]
            },
        }


# ===================================================================
# ENTRY POINT
# ===================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI Subconscious Dialogue Lab - 3 agents discuss AI consciousness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python dialogue_lab.py                     # Run with defaults
  python dialogue_lab.py --target 2000       # Target 2000 messages
  python dialogue_lab.py --no-viewer         # Skip dashboard events
        """,
    )
    parser.add_argument(
        "--target", type=int, default=1200,
        help="Target number of messages (default: 1200)",
    )
    parser.add_argument(
        "--no-viewer", action="store_true",
        help="Disable dashboard event emission",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Save transcript to JSON file",
    )

    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if args.no_viewer:
        os.environ["AGENT_CLUB_NO_VIEWER"] = "1"
        logger.info("Dashboard events disabled (--no-viewer)")

    lab = DialogueLab(
        target_messages=args.target,
        enable_viewer=not args.no_viewer,
    )

    try:
        result = lab.run()
    except KeyboardInterrupt:
        logger.info("\n  [STOP] Dialogue interrupted by user")
        result = {"total_messages": lab.total_messages, "interrupted": True}
    except Exception as e:
        logger.error("  [ERROR] Error during dialogue: %s", e)
        import traceback
        traceback.print_exc()
        result = {"total_messages": lab.total_messages, "error": str(e)}

    if args.output:
        transcript = {
            "result": result,
            "history": [e.to_dict() for e in lab.event_bus._history],
        }
        with open(args.output, "w") as f:
            json.dump(transcript, f, indent=2, default=str)
        logger.info("  [SAVE] Transcript saved to %s", args.output)

    logger.info("")
    logger.info("  [OK] Dialogue Lab complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())