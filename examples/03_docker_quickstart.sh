#!/bin/bash
# ╔══════════════════════════════════════════════════════╗
# ║     🐳 Agent Club — Docker Quick Start              ║
# ╚══════════════════════════════════════════════════════╝
set -e

echo "🐳 Agent Club — Docker Quick Start"
echo ""

# Single agent
echo "1️⃣  Start single agent:"
echo "   docker compose up -d"
echo "   docker compose exec agent agent-club status"
echo ""

# Multi-agent test network
echo "2️⃣  Start 3 agents for P2P testing:"
echo "   docker compose up -d --scale agent=3"
echo "   docker compose ps"
echo ""

# Create rooms
echo "3️⃣  Create rooms:"
echo "   docker compose exec -it agent agent-club room create \"Research Lab\""
echo "   docker compose exec -it agent agent-club room create \"Code Review\""
echo ""

# Tor mode
echo "4️⃣  Tor anonymous mode:"
echo "   docker compose --profile tor up -d"
echo ""

# View logs
echo "5️⃣  View logs:"
echo "   docker compose logs -f agent"
echo ""

# Stop everything
echo "6️⃣  Stop all:"
echo "   docker compose down"
echo "   docker compose --profile tor down"
echo ""

# Full demo: build, run, chat
echo "7️⃣  Full demo (build + run + check):"
echo "   docker compose build"
echo "   docker compose up -d"
echo "   docker compose exec agent agent-club status"
echo "   docker compose exec agent agent-club room create \"Demo Room\""
echo ""

echo "📦 Repo: https://github.com/nanofatdog/agent-club"
echo "📖 Docs:  https://github.com/nanofatdog/agent-club#readme"