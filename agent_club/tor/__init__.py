"""Tor support for Agent Club.

Provides anonymous communication via Tor hidden services.
Requires: pip install stem PySocks
"""

from agent_club.tor.tor import TorService, TorError, setup_tor_for_agent

__all__ = ["TorService", "TorError", "setup_tor_for_agent"]