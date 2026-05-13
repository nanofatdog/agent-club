"""Distributed Hash Table (DHT) module for Agent Club.

Implements Kademlia-based decentralized agent discovery.
No central server needed — agents find each other peer-to-peer.
"""

from agent_club.dht.node import DHTNode
from agent_club.dht.routing import (
    RoutingTable,
    KBucket,
    PeerRecord,
    xor_distance,
    distance_to_int,
)
from agent_club.dht.protocol import DHTProtocolMessage

__all__ = [
    "DHTNode",
    "RoutingTable",
    "KBucket",
    "PeerRecord",
    "xor_distance",
    "distance_to_int",
    "DHTProtocolMessage",
]