"""Security module for Agent Club.

Provides:
- Trust scoring system (decentralized web-of-trust)
- Message & content validation (anti-injection, anti-replay)
- Abuse prevention (rate limiting, spam detection, Sybil detection)
- Audit logging (local-only, privacy-first)
"""

from agent_club.security.trust import TrustManager, TrustScore, InteractionRecord
from agent_club.security.validator import MessageValidator, ContentSafety
from agent_club.security.abuse import AbusePrevention, RateLimiter, RateLimitError, SpamDetector, SybilDetector
from agent_club.security.audit import AuditLogger, AuditEvent, SimpleAudit

__all__ = [
    "TrustManager",
    "TrustScore",
    "InteractionRecord",
    "MessageValidator",
    "ContentSafety",
    "AbusePrevention",
    "RateLimiter",
    "RateLimitError",
    "SpamDetector",
    "SybilDetector",
    "AuditLogger",
    "AuditEvent",
    "SimpleAudit",
]