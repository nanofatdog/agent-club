# syntax=docker/dockerfile:1

# ─── Agent Club Docker Image ──────────────────────────
# Multi-stage build for minimal size with full security

FROM python:3.12-slim-bookworm AS builder

# Build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies in a virtualenv
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ─── Final stage ────────────────────────────────────
FROM python:3.12-slim-bookworm

# Runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd --create-home --shell /bin/bash agent && \
    mkdir -p /home/agent/.agent-club /home/agent/knowledge /home/agent/logs && \
    chown -R agent:agent /home/agent

WORKDIR /home/agent

# Copy application
COPY agent_club/ ./agent_club/
COPY pyproject.toml ./

# Install the package itself
RUN pip install --no-cache-dir -e .

# Expose WebSocket + DHT ports
EXPOSE 8765 6881

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.connect(('127.0.0.1',8765)); s.close()" || exit 1

USER agent
ENV HOME=/home/agent

# Default: run agent server
ENTRYPOINT ["python", "-m", "agent_club"]
CMD ["start", "--host", "0.0.0.0", "--port", "8765"]