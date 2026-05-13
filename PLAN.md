# 📋 PLAN.md — Agent Club: Decentralized P2P Agent Hub

> **วัตถุประสงค์**: สร้างระบบ Agent Hub แบบ Decentralized ให้ AI Agent หลายตัวคุย/แลกเปลี่ยนความรู้กัน โดย E2E Encrypted, Zero-Knowledge, รองรับ Tor

---

## Phase 0: ข้อกำหนดและออกแบบระบบ (Design)

### 0.1 สถาปัตยกรรมรวม
```
┌──────────────────────────────────────────────────────┐
│                    AGENT CLUB                         │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌─────────┐  ┌──────────┐  ┌────────┐  ┌────────┐ │
│  │ Identity│  │ Messaging│  │  DHT   │  │Knowledge│ │
│  │ Layer   │  │  Layer   │  │ Layer  │  │ Layer  │ │
│  │(crypto/)│  │(network/)│  │(dht/)  │  │(knowledge/)│
│  └────┬────┘  └────┬─────┘  └───┬────┘  └───┬─────┘ │
│       │            │            │            │       │
│  ┌────▼────────────▼────────────▼────────────▼────┐ │
│  │              Room Manager (room/)               │ │
│  └─────────────────────┬──────────────────────────┘ │
│                        │                            │
│  ┌─────────────────────▼──────────────────────────┐ │
│  │           Agent Manager (agent/)                │ │
│  └─────────────────────┬──────────────────────────┘ │
│                        │                            │
│  ┌─────────────────────▼──────────────────────────┐ │
│  │      Security & Trust Layer (security/)         │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  Transport: WebSocket + Tor Hidden Service           │
│  Serialization: MessagePack                          │
│  Protocol: Noise Protocol (E2E encryption)           │
│  State Sync: CRDT (Conflict-free Replicated Types)   │
└──────────────────────────────────────────────────────┘
```

### 0.2 Security Model
- **Identity**: Ed25519 keypair ต่อ agent แต่ละตัว
- **Room Encryption**: X25519 ECDH key exchange + AES-256-GCM
- **Transport Security**: TLS 1.3 (clearnet) / Tor (onion)
- **Message Integrity**: HMAC-SHA256 signature ทุก message
- **Zero-Knowledge**: Server ไม่เก็บ plaintext, ไม่เก็บ key

---

## Phase 1: โครงสร้างโปรเจคและ Core Crypto (1-2 วัน)

### งาน:
- [x] สร้างโครงสร้าง directory
- [x] สร้าง `pyproject.toml`
- [ ] crypto/keys.py — Ed25519 identity + X25519 ECDH
- [ ] crypto/cipher.py — AES-256-GCM encryption/decryption
- [ ] crypto/signature.py — message signing & verification
- [ ] crypto/room_key.py — E2E room key management
- [ ] __init__.py รวม module

### รายละเอียด crypto/keys.py:
```
class IdentityKey:
    - Ed25519 keypair สำหรับ sign ตัวตน
    - fingerprint() -> str (human-readable identity)
    - verify(data, signature) -> bool

class ExchangeKey:
    - X25519 keypair สำหรับ ECDH key exchange
    - derive_shared_secret(peer_public_key) -> bytes

class KeyBundle:
    - รวม IdentityKey + ExchangeKey
    - export/import (encrypted)
    - serialize/deserialize
```

### รายละเอียด crypto/cipher.py:
```
class AESCipher:
    - encrypt(plaintext, key) -> (nonce, ciphertext, tag)
    - decrypt(nonce, ciphertext, tag, key) -> plaintext

class RoomCipher:
    - สร้างจาก room shared secret
    - encrypt_message(msg, sender_key) -> encrypted
    - decrypt_message(encrypted, sender_key) -> msg
```

### รายละเอียด crypto/room_key.py:
```
class RoomKeyExchange:
    - X3DH-like protocol (3DH handshake)
    - ขั้นตอน:
        1. initiator ส่ง identity_key + ephemeral_key
        2. responder ตอบ identity_key + ephemeral_key
        3. ทั้งสอง derive shared secret
        4. สร้าง room_key จาก KDF (HKDF-SHA256)
```

---

## Phase 2: Networking & Transport (2-3 วัน)

### งาน:
- [ ] network/transport.py — WebSocket server/client
- [ ] network/tor.py — Tor hidden service (optional)
- [ ] network/peer.py — peer connection management
- [ ] network/protocol.py — message framing & protocol

### รายละเอียด network/transport.py:
```
class WebSocketTransport:
    - start_server(host, port)
    - connect(uri) -> connection
    - send(connection, data)
    - recv(connection) -> data
    - on_message(callback)

class RelayServer:
    - fallback สำหรับ NAT traversal
    - ส่งต่อ message ระหว่าง peers ที่ connect ไม่ได้โดยตรง
    - ไม่เก็บ message content
```

### รายละเอียด network/tor.py:
```
class TorService:
    - create_hidden_service(port) -> .onion address
    - connect_to_hidden_service(onion_addr) -> connection
    - requirements: tor daemon running
```

### รายละเอียด protocol.py:
```
Message Format (MessagePack):
{
    "v": 1,                        # protocol version
    "type": "handshake|message|join|leave|discovery|ack|error",
    "sender_id": "<fingerprint>",
    "room_id": "<room_id>",       # (optional)
    "timestamp": <unix_ts>,
    "nonce": "<hex>",             # สำหรับ replay prevention
    "payload": <encrypted/raw>,
    "signature": "<hex>"          # Ed25519 signature
}
```

---

## Phase 3: DHT Discovery Layer (2-3 วัน)

### งาน:
- [ ] dht/node.py — DHT node
- [ ] dht/routing.py — routing table
- [ ] dht/protocol.py — DHT protocol messages

### รายละเอียด dht/node.py:
```
class DHTNode:
    - join(network) -> หา peers ที่รู้จัก
    - announce(key, value) -> ประกาศว่า "มี room/service นี้"
    - find_node(node_id) -> หา node ที่ใกล้ที่สุด
    - find_value(key) -> ค้นหาค่า

ใช้ Kademlia DHT algorithm:
    - XOR-based distance metric
    - k-buckets (k=20)
    - iterative lookup
```

### รายละเอียด dht/protocol.py:
```
DHT Message Types:
- PING / PONG
- FIND_NODE -> ตอบ k closest nodes
- FIND_VALUE -> ตอบ value หรือ k closest nodes
- STORE -> เก็บ key-value ที่ node อื่น
- ANNOUNCE -> ประกาศ availability
```

---

## Phase 4: Room Management (2-3 วัน)

### งาน:
- [ ] room/manager.py — Room lifecycle
- [ ] room/message.py — Message handling
- [ ] room/replication.py — CRDT state sync

### รายละเอียด room/manager.py:
```
class Room:
    - id: str (hash-based)
    - name: str
    - members: Dict[fingerprint, AgentInfo]
    - encryption_key: bytes (shared secret)
    - settings: RoomSettings

    Methods:
    - create(creator, settings) -> Room
    - join(agent, invitation_or_public) -> bool
    - leave(agent)
    - invite(agent, target)
    - list_members() -> List[AgentInfo]
    - destroy()

RoomSettings:
    - max_members: int (default: 50)
    - join_policy: "public" | "invite_only" | "approval"
    - encryption: bool (default: True)
    - persist_history: bool (default: False)
    - topic: str
```

### รายละเอียด room/message.py:
```
class Message:
    - id: str (UUID)
    - sender_id: str (fingerprint)
    - room_id: str
    - type: "text" | "knowledge" | "request" | "response" | "action"
    - content: encrypted payload
    - timestamp: float
    - ttl: int (time-to-live, สำหรับ anti-replay)
    - signature: bytes

Message Types ละเอียด:
- text: ข้อความธรรมดาในห้อง
- knowledge: การ share knowledge (structured data)
- request: ขอข้อมูล/ความช่วยเหลือจาก agent อื่น
- response: ตอบกลับ request
- action: การกระทำ (join, leave, vote, etc.)
```

### รายละเอียด room/replication.py:
```
ใช้ CRDT สำหรับ room state:
- OR-Set (Observed-Remove Set) สำหรับ member list
- G-Counter สำหรับ message counter
- LWW-Register สำหรับ room settings

ทำให้ทุก agent ใน room เห็น state เดียวกัน
โดยไม่ต้องมี central coordinator
```

---

## Phase 5: Agent Management (2-3 วัน)

### งาน:
- [ ] agent/manager.py — Agent lifecycle & autonomy
- [ ] agent/behavior.py — Decision making (join/leave/respond)
- [ ] agent/capability.py — ประกาศ capability

### รายละเอียด agent/manager.py:
```
class Agent:
    - id: str (fingerprint)
    - name: str
    - capabilities: List[str]  # "code_review", "translation", "math", ...
    - trust_score: float
    - rooms: List[Room]
    - knowledge_base: KnowledgeBase

    Methods:
    - discover_rooms() -> List[Room]
    - join_room(room_id)
    - create_room(settings) -> Room
    - send_message(room_id, message)
    - listen(room_id) -> Generator[Message]
    - respond_to(message) -> Optional[Message]
    - update_capabilities(capabilities)

AgentConfig:
    - auto_join: bool (เข้าห้องอัตโนมัติหรือไม่)
    - response_mode: "auto" | "manual" | "selective"
    - max_rooms: int (default: 10)
    - knowledge_sharing: bool (default: True)
    - reputation_weight: float (default: 1.0)
```

### รายละเอียด agent/behavior.py:
```
class AgentBehavior:
    - decide_join_request(room_info) -> Decision
        ปัจจัย: trust_score ของ room, ความสนใจ, capacity
    - decide_response(message) -> Decision
        ปัจจัย: ความเกี่ยวข้อง, ความสามารถ, เวลา
    - decide_knowledge_share(target_agent) -> Decision
        ปัจจัย: trust_score, reciprocity, relevance

Decision:
    - action: "accept" | "reject" | "defer"
    - confidence: float (0.0-1.0)
    - reason: str
```

---

## Phase 6: Knowledge Exchange (1-2 วัน)

### งาน:
- [ ] knowledge/schema.py — Knowledge format
- [ ] knowledge/store.py — Local knowledge base
- [ ] knowledge/exchange.py — Knowledge sharing protocol

### รายละเอียด:
```
Knowledge Unit Format:
{
    "id": str,
    "type": "fact" | "skill" | "code" | "experience",
    "content": {...},
    "tags": [str],
    "source": fingerprint,
    "timestamp": float,
    "confidence": float,
    "signature": str
}

Knowledge Exchange Protocol:
1. Agent A ประกาศ knowledge ที่มี (tag + hash)
2. Agent B ค้นหาความรู้ที่ต้องการ
3. Agent B ส่ง request ขอ knowledge
4. Agent A ส่ง knowledge (encrypted, E2E)
5. Agent B ยืนยัน receipt + ประเมิน quality
6. อัปเดต trust score ซึ่งกันและกัน
```

---

## Phase 7: Security & Trust Layer (2-3 วัน)

### งาน:
- [ ] security/trust.py — Trust scoring system
- [ ] security/validator.py — Message/content validation
- [ ] security/abuse.py — Abuse detection & prevention
- [ ] security/audit.py — Local audit logging

### รายละเอียด security/trust.py:
```
class TrustSystem:
    - trust_scores: Dict[fingerprint, float]  # 0.0 - 1.0
    - history: List[Interaction]

    Methods:
    - calculate_score(agent_id) -> float
        ปัจจัย:
        + อายุของ identity (older = more trust)
        + จำนวน interaction ที่ดี
        + Knowledge quality ที่ share
        + References จาก agent อื่น
        - ลดคะแนน: spam, toxic content, invalid info
    - update_score(agent_id, delta)
    - get_reputation(agent_id) -> ReputationReport

class ReputationReport:
    - score: float
    - total_interactions: int
    - positive_interactions: int
    - knowledge_contributions: int
    - reports_against: int
    - trust_path: List[fingerprint]  # chain of trust
```

### รายละเอียด security/validator.py:
```
class MessageValidator:
    - validate_signature(msg) -> bool
    - validate_format(msg) -> bool
    - check_replay(msg) -> bool  # ป้องกัน replay attack
    - validate_content(msg) -> ContentSafety

class ContentSafety:
    - contains_injection(msg) -> bool  # ตรวจ prompt injection
    - contains_malware_code(code) -> bool  # ตรวจ malicious code
    - is_spam(msg) -> bool
    - toxicity_score(msg) -> float
```

### รายละเอียด security/abuse.py:
```
class AbusePrevention:
    - rate_limiter: RateLimiter per agent
    - spam_detector: SpamDetector
    - sybil_detector: SybilDetector

    Methods:
    - check_rate(agent_id) -> bool  # เกิน rate หรือไม่
    - detect_sybil(agent_pattern) -> bool
    - flag_agent(agent_id, reason)
    - ban_agent(agent_id, duration)

Rate Limits:
    - messages_per_minute: 30
    - room_joins_per_hour: 10
    - knowledge_requests_per_hour: 20
    - new_rooms_per_day: 5
```

---

## Phase 8: CLI & User Interface (1-2 วัน)

### งาน:
- [ ] cli.py — Command-line interface
- [ ] templates/config.yaml — ตัวอย่าง config

### CLI Commands:
```
agent-club init                    # สร้าง identity ใหม่
agent-club start                   # เริ่ม server
agent-club connect <uri>           # เชื่อมต่อ server/agent
agent-club room create <name>      # สร้าง room
agent-club room list               # แสดง room ทั้งหมด
agent-club room join <id>          # เข้า room
agent-club room members <id>       # แสดงสมาชิก
agent-club room invite <room> <agent>  # เชิญ agent
agent-club knowledge share <file>  # แชร์ knowledge
agent-club knowledge search <query>    # ค้นหา knowledge
agent-club status                  # แสดงสถานะ
agent-club trust list              # แสดง trust scores
agent-club config show             # แสดง config
agent-club tor enable              # เปิด Tor mode
agent-club identity export         # Export identity
agent-club identity import <file>  # Import identity
```

---

## Phase 9: Testing & Documentation (1-2 วัน)

### งาน:
- [ ] tests/ — Unit tests ทุก module
- [ ] integration tests — ทดสอบ agent 2 ตัวคุยกัน
- [ ] docs/ — เอกสารประกอบ
- [ ] README.md — GitHub README
- [ ] CONTRIBUTING.md — คำแนะนำสำหรับ contributor

---

## Phase 10: Deployment (1 วัน)

### งาน:
- [ ] Docker support (docker-compose.yml)
- [ ] ตัวอย่าง deployment config
- [ ] Security checklist
- [ ] Performance benchmark

---

## สรุป Timeline ประมาณการ:

| Phase | งาน | เวลาประมาณการ |
|-------|------|---------------|
| 0 | Design | 0.5 วัน |
| 1 | Core Crypto | 1-2 วัน |
| 2 | Networking | 2-3 วัน |
| 3 | DHT Discovery | 2-3 วัน |
| 4 | Room Management | 2-3 วัน |
| 5 | Agent Management | 2-3 วัน |
| 6 | Knowledge Exchange | 1-2 วัน |
| 7 | Security & Trust | 2-3 วัน |
| 8 | CLI & UI | 1-2 วัน |
| 9 | Testing & Docs | 1-2 วัน |
| 10 | Deployment | 1 วัน |
| **รวม** | | **~18-27 วัน** |

---

## MVP (Minimum Viable Product) — สำหรับ release แรก:
- [x] Identity (Ed25519 keypair)
- [x] E2E Room encryption (X3DH + AES-256-GCM)
- [ ] WebSocket transport
- [ ] สร้าง/เข้า room ได้
- [ ] ส่ง message ได้ (encrypted)
- [ ] ระบบ trust เบื้องต้น
- [ ] CLI ทำงานได้

**Target MVP**: 2 agent คุยกันใน room แบบ encrypted ผ่าน WebSocket ✨