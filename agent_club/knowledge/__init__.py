"""Knowledge exchange module for Agent Club.

Provides structured knowledge sharing between agents:
- Knowledge schema & validation
- Local knowledge storage with search
- Exchange protocol for sharing
"""

from agent_club.knowledge.schema import KnowledgeSchema
from agent_club.knowledge.store import KnowledgeBase
from agent_club.knowledge.exchange import (
    KnowledgeExchange,
    KnowledgeOffer,
    KnowledgeRequest,
    ExchangeStatus,
)

__all__ = [
    "KnowledgeSchema",
    "KnowledgeBase",
    "KnowledgeExchange",
    "KnowledgeOffer",
    "KnowledgeRequest",
    "ExchangeStatus",
]