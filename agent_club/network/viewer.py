"""Dashboard viewer server for Agent Club.

Serves a real-time web dashboard that shows:
- All connected agents (live)
- Active rooms with member counts
- Message stream (anonymized, encrypted metadata only)
- Trust score changes
- Knowledge sharing events

Architecture:
    Browser  ←─ HTTP ──→  ViewerServer (port 8080)
    Browser  ←─ WS ────→  EventBus → transport layer events

The viewer NEVER sees plaintext message content — only metadata
(room ID, sender fingerprint, timestamp, message size).
"""

import asyncio
import json
import logging
import os
import signal
from pathlib import Path
from typing import Optional

import websockets
from websockets.asyncio.server import serve as ws_serve

from agent_club.network.events import EventBus, ClubEvent, get_event_bus

logger = logging.getLogger(__name__)

# Path to the single-file HTML dashboard
_VIEWER_HTML = Path(__file__).parent.parent / "viewer.html"

VIEWER_HTML_CONTENT = None  # cached at first read


def _get_html() -> str:
    """Return the dashboard HTML (cached)."""
    global VIEWER_HTML_CONTENT
    if VIEWER_HTML_CONTENT is None:
        if _VIEWER_HTML.exists():
            VIEWER_HTML_CONTENT = _VIEWER_HTML.read_text()
        else:
            VIEWER_HTML_CONTENT = _fallback_html()
    return VIEWER_HTML_CONTENT


def _fallback_html() -> str:
    """Minimal fallback if viewer.html is missing."""
    return """<!DOCTYPE html>
<html><head><title>Agent Club</title></head>
<body style="background:#0a0a0f;color:#0f0;font:monospace;padding:2em;">
<h1>Agent Club Viewer</h1>
<p>viewer.html not found. Reinstall: <code>pip install agent-club</code></p>
</body></html>"""


class ViewerServer:
    """HTTP + WebSocket server for the Agent Club dashboard.

    Binds to 0.0.0.0 by default so you can view from any
    machine on the local network.

    Uses two ports: one for HTTP (serves dashboard + REST API)
    and one for WebSocket (streams live events to browser).
    Default: HTTP on ``port``, WebSocket on ``port + 1``.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        event_bus: EventBus = None,
    ):
        self.host = host
        self.http_port = port
        self.ws_port = port + 1  # Separate port for WebSocket
        self.event_bus = event_bus or get_event_bus()
        self._ws_clients = set()
        self._ws_server = None
        self._http_server = None
        self._running = False

    # ── WebSocket handler (streams events to browser) ─

    async def _ws_handler(self, websocket, path=None):
        """Handle a viewer WebSocket connection."""
        self._ws_clients.add(websocket)
        logger.info(f"Viewer connected ({len(self._ws_clients)} total)")

        # Send history + current state immediately
        await websocket.send(json.dumps({
            "type": "init",
            "history": self.event_bus.get_history(50),
            "state": self.event_bus.get_state(),
        }))

        # Subscribe to future events
        async def forward(event: ClubEvent):
            try:
                if websocket in self._ws_clients:
                    await websocket.send(json.dumps({
                        "type": "event",
                        "event": event.to_dict(),
                        "state": self.event_bus.get_state(),
                    }))
            except Exception:
                self._ws_clients.discard(websocket)

        # Wrap async forward in sync callback that schedules on the loop
        loop = asyncio.get_event_loop()

        def sync_forward(event: ClubEvent):
            if websocket in self._ws_clients:
                asyncio.ensure_future(forward(event))

        self.event_bus.subscribe(sync_forward)

        try:
            async for _ in websocket:
                pass  # Keep connection alive; browser sends pings
        except Exception:
            pass
        finally:
            self.event_bus.unsubscribe(sync_forward)
            self._ws_clients.discard(websocket)
            logger.info(f"Viewer disconnected ({len(self._ws_clients)} remaining)")

    # ── HTTP handler (serves dashboard HTML) ─────────

    async def _http_handler(self, reader, writer):
        """Minimal HTTP server — serves dashboard + static JSON API."""
        try:
            request = await asyncio.wait_for(reader.read(4096), timeout=5)
        except asyncio.TimeoutError:
            writer.close()
            return

        request_line = request.split(b"\r\n")[0].decode("utf-8", errors="replace")
        parts = request_line.split(" ")
        method = parts[0] if len(parts) > 0 else "GET"
        path = parts[1] if len(parts) > 1 else "/"

        if method != "GET":
            await self._send_response(writer, 405, "Method Not Allowed")
            return

        if path == "/" or path == "/index.html":
            html = _get_html()
            await self._send_response(
                writer, 200, "OK",
                content_type="text/html; charset=utf-8",
                body=html,
            )
        elif path == "/api/state":
            body = json.dumps(self.event_bus.get_state(), indent=2)
            await self._send_response(
                writer, 200, "OK",
                content_type="application/json",
                body=body,
            )
        elif path == "/api/events":
            body = json.dumps(self.event_bus.get_history(100), indent=2)
            await self._send_response(
                writer, 200, "OK",
                content_type="application/json",
                body=body,
            )
        elif path == "/health":
            await self._send_response(writer, 200, "OK", body="OK")
        else:
            await self._send_response(writer, 404, "Not Found")

    async def _send_response(self, writer, status: int, reason: str,
                              content_type: str = "text/plain",
                              body: str = ""):
        """Send an HTTP response."""
        body_bytes = body.encode("utf-8")
        response = (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("utf-8") + body_bytes
        writer.write(response)
        await writer.drain()
        writer.close()

    # ── lifecycle ────────────────────────────────────

    async def start(self):
        """Start both HTTP and WebSocket servers."""
        self._running = True

        # Start WebSocket server for live events (on separate port)
        self._ws_server = await ws_serve(
            self._ws_handler,
            self.host,
            self.ws_port,
        )

        # Start HTTP server for dashboard HTML + REST API
        self._http_server = await asyncio.start_server(
            self._http_handler,
            self.host,
            self.http_port,
        )

        logger.info(f"Dashboard viewer: http://{self.host}:{self.http_port}")
        logger.info(f"Live WebSocket:   ws://{self.host}:{self.ws_port}")
        logger.info(f"REST API:         http://{self.host}:{self.http_port}/api/state")

    async def stop(self):
        """Stop both servers."""
        self._running = False

        # Close all WebSocket clients
        for ws in list(self._ws_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_clients.clear()

        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()

        if self._http_server:
            self._http_server.close()
            await self._http_server.wait_closed()

        logger.info("Dashboard viewer stopped")

    # ── convenience ──────────────────────────────────

    @property
    def viewer_url(self) -> str:
        host = "localhost" if self.host == "0.0.0.0" else self.host
        return f"http://{host}:{self.http_port}"

    @property
    def ws_url(self) -> str:
        host = "localhost" if self.host == "0.0.0.0" else self.host
        return f"ws://{host}:{self.ws_port}"

    async def run_forever(self):
        """Start and block until SIGINT/SIGTERM."""
        await self.start()

        stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()

        def _stop():
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _stop)
            except NotImplementedError:
                pass  # Windows doesn't support add_signal_handler

        await stop_event.wait()
        await self.stop()
