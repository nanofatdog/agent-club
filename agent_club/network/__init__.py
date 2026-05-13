"""Network module for Agent Club.

Provides:
- WebSocket-based P2P transport
- Tor hidden service support
- Peer connection management
- Protocol message definitions
"""

from agent_club.network.transport import WebSocketTransport, RelayTransport, ConnectionError
from agent_club.network.peer import PeerManager, PeerInfo
from agent_club.network.protocol import (
    ProtocolMessage,
    MessageBuilder,
    PROTOCOL_VERSION,
    MSG_HANDSHAKE_INIT,
    MSG_HANDSHAKE_RESPONSE,
    MSG_JOIN_REQUEST,
    MSG_JOIN_ACCEPT,
    MSG_JOIN_REJECT,
    MSG_LEAVE,
    MSG_TEXT,
    MSG_KNOWLEDGE,
    MSG_REQUEST,
    MSG_RESPONSE,
    MSG_PING,
    MSG_PONG,
    MSG_ACK,
    MSG_ERROR,
    MSG_DISCOVERY_QUERY,
    MSG_DISCOVERY_RESPONSE,
    MSG_ROOM_LIST,
    MSG_ROOM_STATE,
    MSG_INVITE,
    MSG_VOTE,
)

__all__ = [
    "WebSocketTransport",
    "RelayTransport",
    "ConnectionError",
    "PeerManager",
    "PeerInfo",
    "ProtocolMessage",
    "MessageBuilder",
    "PROTOCOL_VERSION",
]