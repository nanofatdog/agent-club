#!/usr/bin/env python3
"""
Example 02: Knowledge Sharing
===============================
Agents share structured knowledge, search, and discover
using the knowledge exchange protocol.

Run:
    python examples/02_knowledge_share.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_club.crypto.keys import KeyBundle
from agent_club.knowledge.schema import KnowledgeSchema
from agent_club.knowledge.store import KnowledgeBase
from agent_club.knowledge.exchange import KnowledgeExchange
from agent_club.security.trust import TrustManager


def divider(title=""):
    print(f"\n{'='*60}")
    if title:
        print(f"  {title}")
        print(f"{'='*60}")


# Create two agents
alice = KeyBundle(name="Alice")
bob = KeyBundle(name="Bob")
charlie = KeyBundle(name="Charlie")

# Knowledge bases
alice_kb = KnowledgeBase()
bob_kb = KnowledgeBase()
charlie_kb = KnowledgeBase()

# Exchange managers
alice_ex = KnowledgeExchange(alice.fingerprint, alice_kb)
bob_ex = KnowledgeExchange(bob.fingerprint, bob_kb)

divider("Step 1: Alice shares knowledge about AI")

# Alice creates knowledge units
knowledge_units = [
    KnowledgeSchema.create_knowledge_unit(
        alice.fingerprint,
        "fact",
        {"topic": "Transformer Architecture",
         "fact": "Self-attention computes weighted sum of all input tokens",
         "key_paper": "Attention Is All You Need (2017)"},
        tags=["ai", "nlp", "transformers"],
        confidence=0.95,
        signer=alice.identity_key,
    ),
    KnowledgeSchema.create_knowledge_unit(
        alice.fingerprint,
        "skill",
        {"skill": "Fine-tuning BERT",
         "description": "How to fine-tune BERT for text classification",
         "steps": ["Load pretrained", "Add classifier head", "Train on domain data"]},
        tags=["ai", "nlp", "bert", "fine-tuning"],
        confidence=0.85,
        signer=alice.identity_key,
    ),
    KnowledgeSchema.create_knowledge_unit(
        alice.fingerprint,
        "code",
        {"language": "Python",
         "title": "Simple Transformer from scratch",
         "description": "Minimal transformer implementation in 100 lines",
         "code_url": "https://github.com/example/tiny-transformer"},
        tags=["ai", "code", "python", "transformers"],
        confidence=0.90,
        signer=alice.identity_key,
    ),
]

for unit in knowledge_units:
    alice_kb.add(unit)

print(f"   Alice shared {len(knowledge_units)} knowledge units")
print(f"   Types: fact, skill, code")
print(f"   Tags:  ai, nlp, transformers, bert, python, code")

divider("Step 2: Bob searches for 'transformer' knowledge")

results = alice_kb.search(query="transformer", min_confidence=0.7)

print(f"   Found {len(results)} results:")
for r in results:
    print(f"   📄 [{r['type']}] {r['id'][:12]}... "
          f"(confidence: {r.get('confidence', '?')}) "
          f"[tags: {', '.join(r.get('tags', []))}]")

divider("Step 3: Alice publishes knowledge for sharing")

offer_id = alice_ex.publish(
    unit_ids=[u["id"] for u in knowledge_units],
    visibility="room",
)
print(f"   Published offer: {offer_id}")

# Bob queries available knowledge
available = bob_ex.query_available(tags=["ai", "transformers"])
print(f"   Available knowledge: {available['count']} units")

divider("Step 4: Bob requests specific knowledge")

# Bob's request will be sent to Alice (in real network).
# For simulation: Alice creates a matching offer directly.
request = bob_ex.request_knowledge(
    query="transformer architecture implementation",
    tags=["ai", "transformers"],
)
print(f"   Request ID: {request.request_id}")
print(f"   Status: {request.status}")

# Alice searches her knowledge base and creates an offer directly
alice_matches = alice_kb.search(query="transformer", limit=3)
match_ids = [r["id"] for r in alice_matches]

if match_ids:
    # Alice creates an offer directly (simulating network response)
    from agent_club.knowledge.exchange import KnowledgeOffer
    import uuid
    offer = KnowledgeOffer(
        offer_id=uuid.uuid4().hex[:16],
        sender_id=alice.fingerprint,
        knowledge_ids=match_ids,
        metadata={"in_reply_to": request.request_id},
    )
    alice_ex._offers[offer.offer_id] = offer
    print(f"   Alice responds with {len(match_ids)} units")
else:
    print(f"   Alice: No matching knowledge found")
    offer = None

divider("Step 5: Transfer knowledge to Bob")

units = alice_ex.transfer_knowledge(
    offer.offer_id,
    target_agent_id=bob.fingerprint,
    signer=alice.identity_key,
)
print(f"   Transferred {len(units)} units to Bob")

# Bob receives and stores
results = bob_ex.receive_knowledge(
    units=units,
    sender_id=alice.fingerprint,
)
print(f"   Bob received: {results['accepted']} accepted, "
      f"{results['verified']} verified, {results['rejected']} rejected")

divider("Step 6: Bob can now search his own knowledge base")

after_search = bob_kb.search(query="transformer")
print(f"   Bob's knowledge base: {bob_kb.count()} units")
for r in after_search[:3]:
    print(f"   📄 [{r['type']}] {r['id'][:12]}... "
          f"(from: {r['source'][:8]}...)")

divider("Step 7: Trust scores update from knowledge sharing")

trust = TrustManager()
trust.record_interaction(
    alice.fingerprint, bob.fingerprint,
    interaction_type="knowledge_share",
    result="success",
    details={"units_shared": len(units)},
)

alice_score = trust.get_score_value(alice.fingerprint)
bob_score = trust.get_score_value(bob.fingerprint)
print(f"   Alice: {alice_score:.2f} (shared {len(units)} units)")
print(f"   Bob:   {bob_score:.2f} (received {len(units)} units)")

divider("✅ Knowledge Exchange Demo Complete!")

print(f"""
   🧠 What happened:
   
   1. ✅ Alice created 3 knowledge units (fact, skill, code)
   2. ✅ Bob searched and found relevant knowledge
   3. ✅ Knowledge published for discovery
   4. ✅ Bob requested specific topics
   5. ✅ Alice responded with matching units
   6. ✅ Units transferred with signatures verified
   7. ✅ Trust scores updated based on exchange
   
   🔐 Security:
   - All knowledge is signed by the creator (Ed25519)
   - Recipient verifies signature before accepting
   - Confidence scores prevent low-quality knowledge
   - Trust scores build reputation over time
""")