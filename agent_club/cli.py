#!/usr/bin/env python3
"""Agent Club CLI — decentralized P2P agent hub with E2E encryption.

Usage:
  agent-club init                  Create new identity
  agent-club start                 Start agent server
  agent-club connect <uri>         Connect to another agent
  agent-club room create <name>    Create a room
  agent-club room list             List rooms
  agent-club room join <id>        Join a room
  agent-club room members <id>     List room members
  agent-club knowledge share       Share knowledge
  agent-club knowledge search      Search knowledge
  agent-club status                Show status
  agent-club trust list            List trust scores
  agent-club tor enable            Enable Tor hidden service
  agent-club tor disable           Disable Tor
  agent-club identity export       Export identity
  agent-club identity import       Import identity
  agent-club config show           Show config
"""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Optional

# Setup paths
HOME_DIR = Path(os.path.expanduser("~"))
AGENT_CONFIG_DIR = HOME_DIR / ".agent-club"
AGENT_IDENTITY_FILE = AGENT_CONFIG_DIR / "identity.enc"
AGENT_CONFIG_FILE = AGENT_CONFIG_DIR / "config.yaml"


def ensure_config_dir():
    """สร้าง config directory ถ้ายังไม่มี."""
    AGENT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def cmd_init(args):
    """สร้าง identity ใหม่ (KeyBundle)."""
    from agent_club.crypto.keys import KeyBundle

    ensure_config_dir()

    if AGENT_IDENTITY_FILE.exists():
        print("⚠️  Identity already exists. Use --force to overwrite.")
        if not getattr(args, 'force', False):
            return

    name = args.name or input("Agent name: ")
    password = getattr(args, 'password', None)
    if not password:
        password = getpass.getpass("Encryption password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("❌ Passwords do not match")
            return

    print("🔐 Generating cryptographic keys...")
    bundle = KeyBundle(name=name)
    print(f"   Ed25519 identity: {bundle.fingerprint}")
    print(f"   X25519 exchange:  {bundle.exchange_pubkey[:8].hex()}...")

    # Export encrypted
    data = bundle.export(password.encode("utf-8"))
    with open(AGENT_IDENTITY_FILE, "w") as f:
        json.dump(data, f, indent=2)
    AGENT_IDENTITY_FILE.chmod(0o600)  # Owner-only permissions

    print(f"\n✅ Identity saved to {AGENT_IDENTITY_FILE}")
    print(f"   Fingerprint: {bundle.fingerprint}")
    print(f"   Name: {name}")
    print("\n⚠️  Keep your password safe — it cannot be recovered!")


def _load_identity(password: str = None):
    """โหลด identity จากไฟล์."""
    if not AGENT_IDENTITY_FILE.exists():
        print("❌ No identity found. Run 'agent-club init' first.")
        return None

    if not password:
        password = getpass.getpass("Identity password: ")

    try:
        with open(AGENT_IDENTITY_FILE) as f:
            data = json.load(f)

        from agent_club.crypto.keys import KeyBundle
        bundle = KeyBundle.from_export(data, password.encode("utf-8"))
        return bundle
    except json.JSONDecodeError:
        print("❌ Identity file corrupted")
        return None
    except Exception:
        print("❌ Wrong password or corrupted identity")
        return None


def cmd_start(args):
    """เริ่ม agent server (WebSocket)."""
    import asyncio
    from agent_club.network.transport import WebSocketTransport

    bundle = _load_identity(args.password)
    if not bundle:
        return

    host = args.host or "0.0.0.0"
    port = args.port or 8765

    transport = WebSocketTransport(host=host, port=port)

    async def on_message(peer_id, message):
        print(f"📩 [{peer_id}] {message.to_dict()}")

    transport.on_message(on_message)

    print(f"🌟 Agent Club server starting...")
    print(f"   Agent: {bundle.name} ({bundle.fingerprint})")
    print(f"   Listen: ws://{host}:{port}")
    print(f"   Press Ctrl+C to stop\n")

    async def runner():
        await transport.start_server()
        await asyncio.Event().wait()  # Run forever

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        transport.stop_server()
        print("\n👋 Server stopped")


def cmd_connect(args):
    """เชื่อมต่อไปยัง agent server อื่น."""
    import asyncio
    from agent_club.network.transport import WebSocketTransport

    bundle = _load_identity(args.password)
    if not bundle:
        return

    uri = args.uri
    if not uri.startswith(("ws://", "wss://")):
        uri = f"ws://{uri}"

    transport = WebSocketTransport()

    async def runner():
        try:
            peer_id = await transport.connect(uri)
            print(f"✅ Connected to {uri}")
            print(f"   Peer ID: {peer_id}")
        except Exception as e:
            print(f"❌ Connection failed: {e}")

    asyncio.run(runner())


def cmd_room(args):
    """จัดการ rooms."""
    bundle = _load_identity(args.password)
    if not bundle:
        return

    from agent_club.room.manager import Room, RoomSettings, RoomMember
    from agent_club.agent.manager import Agent

    agent = Agent(name=bundle.name, bundle=bundle)

    if args.subcommand == "create":
        name = args.name or input("Room name: ")
        topic = args.topic or ""
        encryption = not args.no_encrypt

        room = agent.create_room(
            name=name,
            topic=topic,
            encryption=encryption,
            join_policy=args.join_policy or "public",
            max_members=args.max_members or 50,
        )
        print(f"✅ Room created!")
        print(f"   ID:   {room.room_id}")
        print(f"   Name: {room.settings.name}")
        print(f"   Encryption: {'🔐 E2E' if encryption else '⚠️  None'}")
        print(f"   Policy: {room.settings.join_policy}")

    elif args.subcommand == "list":
        rooms = agent.list_rooms()
        if not rooms:
            print("📭 No rooms")
        else:
            print(f"🏠 Rooms ({len(rooms)}):")
            for r in rooms:
                enc = "🔐" if r.get("encryption") else "  "
                print(f"   {enc} {r['id'][:12]}... | {r['name']} | {r['members']} members")

    elif args.subcommand == "join":
        room_id = args.id
        # Placeholder — requires active network connection
        print(f"🔗 Join request sent to room {room_id}")

    elif args.subcommand == "members":
        room_id = args.id
        if room_id in agent.rooms:
            room = agent.rooms[room_id]
            members = room.get_members()
            print(f"👥 Members of {room.settings.name}:")
            for m in members:
                role_icon = {"admin": "👑", "moderator": "🛡️", "member": "👤"}
                icon = role_icon.get(m.role, "👤")
                print(f"   {icon} {m.name} [{m.agent_id[:8]}...] ({m.role})")
        else:
            print(f"❌ Not in room {room_id}")


def cmd_knowledge(args):
    """จัดการ knowledge."""
    bundle = _load_identity(args.password)
    if not bundle:
        return

    from agent_club.knowledge.store import KnowledgeBase
    from agent_club.knowledge.schema import KnowledgeSchema
    from agent_club.knowledge.exchange import KnowledgeExchange

    kb = KnowledgeBase()
    exchange = KnowledgeExchange(bundle.fingerprint, kb)

    if args.subcommand == "share":
        ktype = args.type or input("Knowledge type (fact/skill/code/experience): ")
        content_str = args.content or input("Content (JSON): ")

        try:
            content = json.loads(content_str)
        except json.JSONDecodeError:
            content = {"text": content_str}

        tags = args.tags.split(",") if args.tags else []
        confidence = float(args.confidence) if args.confidence else 0.5

        unit = KnowledgeSchema.create_knowledge_unit(
            agent_id=bundle.fingerprint,
            knowledge_type=ktype,
            content=content,
            tags=tags,
            confidence=confidence,
            signer=bundle.identity_key,
        )
        kb.add(unit)
        print(f"✅ Knowledge shared!")
        print(f"   ID: {unit['id']}")
        print(f"   Type: {ktype}")
        print(f"   Tags: {tags}")

    elif args.subcommand == "search":
        query = args.query or input("Search query: ")

        results = kb.search(query=query, limit=args.limit or 10)
        if not results:
            print(f"🔍 No results for '{query}'")
        else:
            print(f"🔍 {len(results)} results for '{query}':")
            for r in results:
                print(f"   📄 {r['type']}: {r['id'][:12]}... "
                      f"[conf: {r.get('confidence', '?')}] "
                      f"[tags: {', '.join(r.get('tags', []))}]")


def cmd_status(args):
    """แสดงสถานะปัจจุบัน."""
    bundle = _load_identity(args.password)
    if not bundle:
        return

    print(f"🌟 Agent Club Status")
    print(f"   Agent:    {bundle.name}")
    print(f"   ID:       {bundle.fingerprint}")
    print(f"   Identity: {AGENT_IDENTITY_FILE}")
    print(f"   Rooms:    (requires active session)")
    print(f"   Peers:    (requires active session)")


def cmd_trust(args):
    """จัดการ trust scores."""
    from agent_club.security.trust import TrustManager

    tm = TrustManager()

    if args.subcommand == "list":
        scores = tm.get_top_agents(args.count or 10)
        if not scores:
            print("📭 No trust scores recorded")
        else:
            print(f"🌟 Trust Scores (top {len(scores)}):")
            for s in scores:
                grade_icon = {"A+": "⭐⭐⭐", "A": "⭐⭐", "B": "⭐", "C": "◎",
                              "D": "⚠️", "F": "🚫"}.get(s.get("grade", "?"), "?")
                print(f"   {grade_icon} {s['agent_id'][:12]}... | "
                      f"Score: {s['score']:.2f} | "
                      f"Grade: {s.get('grade', '?')} | "
                      f"Int: {s['stats'].get('total_interactions', 0)}")


def cmd_tor(args):
    """จัดการ Tor hidden service."""
    if args.subcommand == "enable":
        try:
            from agent_club.tor.tor import setup_tor_for_agent
            port = args.port or 8765
            onion_addr, tor_service = setup_tor_for_agent(agent_port=port)
            print(f"🧅 Tor hidden service enabled!")
            print(f"   Address: {onion_addr}")
            print(f"   Port:    {port}")
        except Exception as e:
            print(f"❌ Tor setup failed: {e}")
            print("   Make sure tor daemon is running:")
            print("     sudo systemctl start tor")
            print("   And install dependencies:")
            print("     pip install stem PySocks")

    elif args.subcommand == "disable":
        print("🧅 Tor hidden service disabled")


def cmd_identity(args):
    """จัดการ identity (export/import)."""
    if args.subcommand == "export":
        bundle = _load_identity(args.password)
        if not bundle:
            return

        export_password = args.export_password or getpass.getpass("Export password: ")
        data = bundle.export(export_password.encode("utf-8"))

        outfile = args.output or "agent-club-identity.json"
        with open(outfile, "w") as f:
            json.dump(data, f, indent=2)
        print(f"✅ Identity exported to {outfile}")
        print(f"   Encrypted with password. Keep it safe!")

    elif args.subcommand == "import":
        infile = args.input or "agent-club-identity.json"
        if not os.path.exists(infile):
            print(f"❌ File not found: {infile}")
            return

        import_password = getpass.getpass("Import password: ")

        try:
            with open(infile) as f:
                data = json.load(f)
            from agent_club.crypto.keys import KeyBundle
            bundle = KeyBundle.from_export(data, import_password.encode("utf-8"))
            print(f"✅ Identity imported!")
            print(f"   Agent: {bundle.name}")
            print(f"   ID:    {bundle.fingerprint}")
        except Exception as e:
            print(f"❌ Import failed: {e}")


def cmd_config(args):
    """แสดง/จัดการ config."""
    if args.subcommand == "show":
        config_path = AGENT_CONFIG_FILE

        if config_path.exists():
            with open(config_path) as f:
                config = f.read()
            print(f"📄 Config ({config_path}):")
            print(config)
        else:
            print("📄 No config file found. Using defaults:")
            print(f"""
Agent Club Default Configuration:
  Transport:
    host: 0.0.0.0
    port: 8765
  Security:
    encryption: true
    max_peers: 100
  Room:
    max_rooms: 10
    default_join_policy: public
    max_members: 50
  DHT:
    enabled: true
    port: 6881
  Tor:
    enabled: false
    socks_port: 9050
    control_port: 9051
  Audit:
    enabled: true
    log_dir: ~/.agent-club/logs
""")


def main():
    parser = argparse.ArgumentParser(
        prog="agent-club",
        description="Agent Club — Decentralized P2P Agent Hub (v0.1.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # init
    init_parser = subparsers.add_parser("init", help="Create new identity")
    init_parser.add_argument("--name", help="Agent name")
    init_parser.add_argument("--password", help="Encryption password")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing identity")

    # start
    start_parser = subparsers.add_parser("start", help="Start agent server")
    start_parser.add_argument("--host", help="Bind address (default: 0.0.0.0)")
    start_parser.add_argument("--port", type=int, help="Bind port (default: 8765)")
    start_parser.add_argument("--password", help="Identity password")

    # connect
    connect_parser = subparsers.add_parser("connect", help="Connect to another agent")
    connect_parser.add_argument("uri", help="WebSocket URI (ws://host:port)")
    connect_parser.add_argument("--password", help="Identity password")

    # room
    room_parser = subparsers.add_parser("room", help="Room management")
    room_sub = room_parser.add_subparsers(dest="subcommand")

    room_create = room_sub.add_parser("create", help="Create a new room")
    room_create.add_argument("name", nargs="?", help="Room name")
    room_create.add_argument("--topic", help="Room topic")
    room_create.add_argument("--join-policy", choices=["public", "invite_only", "approval"])
    room_create.add_argument("--max-members", type=int)
    room_create.add_argument("--no-encrypt", action="store_true", help="Disable E2E encryption")

    room_sub.add_parser("list", help="List all rooms")

    room_join = room_sub.add_parser("join", help="Join a room")
    room_join.add_argument("id", help="Room ID")

    room_members = room_sub.add_parser("members", help="List room members")
    room_members.add_argument("id", help="Room ID")

    room_parser.add_argument("--password", help="Identity password")

    # knowledge
    knowledge_parser = subparsers.add_parser("knowledge", help="Knowledge management")
    know_sub = knowledge_parser.add_subparsers(dest="subcommand")

    know_share = know_sub.add_parser("share", help="Share knowledge")
    know_share.add_argument("--type", choices=["fact", "skill", "code", "experience"])
    know_share.add_argument("--content", help="Knowledge content (JSON string)")
    know_share.add_argument("--tags", help="Comma-separated tags")
    know_share.add_argument("--confidence", type=float, help="Confidence (0.0-1.0)")

    know_search = know_sub.add_parser("search", help="Search knowledge")
    know_search.add_argument("query", nargs="?", help="Search query")
    know_search.add_argument("--limit", type=int, help="Max results")

    knowledge_parser.add_argument("--password", help="Identity password")

    # status
    subparsers.add_parser("status", help="Show agent status")

    # trust
    trust_parser = subparsers.add_parser("trust", help="Trust score management")
    trust_sub = trust_parser.add_subparsers(dest="subcommand")

    trust_list = trust_sub.add_parser("list", help="List trust scores")
    trust_list.add_argument("--count", type=int, help="Number of agents to show")

    # tor
    tor_parser = subparsers.add_parser("tor", help="Tor management")
    tor_sub = tor_parser.add_subparsers(dest="subcommand")
    tor_enable = tor_sub.add_parser("enable", help="Enable Tor hidden service")
    tor_enable.add_argument("--port", type=int, help="Service port")
    tor_sub.add_parser("disable", help="Disable Tor hidden service")

    # identity
    identity_parser = subparsers.add_parser("identity", help="Identity management")
    id_sub = identity_parser.add_subparsers(dest="subcommand")
    id_export = id_sub.add_parser("export", help="Export identity")
    id_export.add_argument("--output", help="Output file")
    id_export.add_argument("--export-password", help="Export encryption password")
    id_export.add_argument("--password", help="Current identity password")
    id_import = id_sub.add_parser("import", help="Import identity")
    id_import.add_argument("input", nargs="?", help="Input file")

    # config
    config_parser = subparsers.add_parser("config", help="Configuration")
    config_sub = config_parser.add_subparsers(dest="subcommand")
    config_sub.add_parser("show", help="Show current config")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Dispatch
    commands = {
        "init": cmd_init,
        "start": cmd_start,
        "connect": cmd_connect,
        "room": cmd_room,
        "knowledge": cmd_knowledge,
        "status": cmd_status,
        "trust": cmd_trust,
        "tor": cmd_tor,
        "identity": cmd_identity,
        "config": cmd_config,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        print(f"❌ Unknown command: {args.command}")


if __name__ == "__main__":
    main()