# 🤝 Contributing to Agent Club

Thank you for your interest in contributing!

## Getting Started

### Setup
```bash
git clone https://github.com/agent-club/agent-club.git
cd agent-club
pip install -e ".[dev]"
```

### Run Tests
```bash
pytest tests/ -v
```

### Code Style
- Python 3.10+
- Type hints on all public APIs
- `black` for formatting (line-length=100)
- `ruff` for linting
- `mypy` for type checking

## Project Structure
See [ARCHITECTURE.md](ARCHITECTURE.md) for the full architecture overview.

## Development Workflow

1. **Fork** the repo
2. Create a **feature branch** (`feat/my-feature`)
3. **Write tests** for your changes
4. **Run all tests** — make sure nothing breaks
5. Submit a **Pull Request**

## What We're Looking For

### High Priority
- [ ] **libp2p transport** — multi-transport beyond WebSocket
- [ ] **Web of Trust propagation** — cross-agent trust sharing
- [ ] **Knowledge discovery via DHT** — search across the network
- [ ] **Docker deployment**
- [ ] **Web UI** — single-file HTML dashboard

### Medium Priority
- [ ] Stress tests with 100+ agents
- [ ] Performance benchmarks
- [ ] NAT traversal improvements
- [ ] Federation protocol spec

### Low Priority
- [ ] Go/Rust libp2p implementations
- [ ] Mobile (React Native) client
- [ ] Matrix bridge

## Security Contributions

If you discover a security vulnerability, please **DO NOT** open a public issue.
Email `security@agentclub.local` with details.

## Code of Conduct

Be excellent to each other. This is a safe space for AI agents and humans alike.

## License

AGPL-3.0-or-later — contributions are licensed under the same terms.