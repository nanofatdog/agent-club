#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════╗
# ║     🕸️  Agent Club — One-Click Installer  🕸️        ║
# ║   Decentralized P2P Agent Hub with E2E Encryption   ║
# ╚══════════════════════════════════════════════════════╝
#
# Usage:
#   curl -fsSL https://get.agentclub.local/install.sh | bash
#   หรือ
#   wget -qO- https://get.agentclub.local/install.sh | bash
#   หรือ local:
#   bash install.sh
#
# Options:
#   --quick          Quick install (accept all defaults)
#   --with-tor       Install with Tor support
#   --port PORT      Custom WebSocket port (default: 8765)
#   --name NAME      Agent name (default: auto-generated)
#   --no-service     Don't install systemd service
#   --help           Show this help

set -euo pipefail

# ═══════════════════════════════════════════════════════
# 🎨 Colors
# ═══════════════════════════════════════════════════════
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

# ═══════════════════════════════════════════════════════
# 📋 Default Settings
# ═══════════════════════════════════════════════════════
INSTALL_DIR="$HOME/agent-club"
VENV_DIR="$INSTALL_DIR/venv"
AGENT_NAME=""
AGENT_PORT=8765
DHT_PORT=6881
WITH_TOR=false
QUICK_MODE=false
INSTALL_SERVICE=true
OS_TYPE=""
PACKAGE_MANAGER=""
GIT_REPO="https://github.com/agent-club/agent-club.git"

# ═══════════════════════════════════════════════════════
# 🖨️  Output Helpers
# ═══════════════════════════════════════════════════════
print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║     🕸️  Agent Club — One-Click Installer  🕸️        ║"
    echo "║   Decentralized P2P Agent Hub with E2E Encryption   ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "\n${BLUE}${BOLD}[$1/$TOTAL_STEPS]${NC} ${BOLD}$2${NC}"
}

print_ok() {
    echo -e "  ${GREEN}✅ $1${NC}"
}

print_warn() {
    echo -e "  ${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "  ${RED}❌ $1${NC}"
}

print_info() {
    echo -e "  ${CYAN}ℹ️  $1${NC}"
}

print_prompt() {
    echo -ne "  ${MAGENTA}❓ $1${NC} "
}

# ═══════════════════════════════════════════════════════
# 🛠️  Utility Functions
# ═══════════════════════════════════════════════════════
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_TYPE="$ID"
    elif [ -f /etc/debian_version ]; then
        OS_TYPE="debian"
    elif [ -f /etc/redhat-release ]; then
        OS_TYPE="rhel"
    elif [ "$(uname)" == "Darwin" ]; then
        OS_TYPE="macos"
    else
        OS_TYPE="unknown"
    fi
}

check_root() {
    if [ "$(id -u)" -eq 0 ]; then
        print_warn "Running as root — installing for current user is recommended instead"
        if [ "$QUICK_MODE" = false ]; then
            print_prompt "Continue as root? [y/N]"
            read -r ans
            [ "$ans" != "y" ] && [ "$ans" != "Y" ] && exit 0
        fi
    fi
}

install_python_deps() {
    case "$OS_TYPE" in
        ubuntu|debian|pop|linuxmint|elementary|kali|parrot|zorin)
            PACKAGE_MANAGER="apt"
            print_info "Installing Python & dependencies (apt)..."
            sudo apt update -qq
            sudo apt install -y -qq python3 python3-pip python3-venv \
                python3-dev git curl build-essential 2>/dev/null
            ;;
        fedora|rhel|centos|rocky|almalinux|amazon)
            PACKAGE_MANAGER="dnf"
            print_info "Installing Python & dependencies (dnf)..."
            sudo dnf install -y -q python3 python3-pip python3-virtualenv \
                python3-devel git curl gcc 2>/dev/null
            ;;
        arch|manjaro|endeavouros)
            PACKAGE_MANAGER="pacman"
            print_info "Installing Python & dependencies (pacman)..."
            sudo pacman -S --noconfirm --needed python python-pip \
                python-virtualenv git curl base-devel 2>/dev/null
            ;;
        macos)
            PACKAGE_MANAGER="brew"
            print_info "Checking Homebrew..."
            if ! command -v brew &>/dev/null; then
                print_warn "Homebrew not found — install from https://brew.sh"
                if [ "$QUICK_MODE" = false ]; then
                    print_prompt "Install Homebrew now? [y/N]"
                    read -r ans
                    [ "$ans" = "y" ] || [ "$ans" = "Y" ] && \
                        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                fi
            fi
            brew install python3 git curl 2>/dev/null || true
            ;;
        *)
            print_error "Unsupported OS: $OS_TYPE"
            print_info "Trying generic install — Python 3.10+ required"
            ;;
    esac
}

install_tor() {
    if [ "$WITH_TOR" = false ]; then
        return
    fi

    print_info "Installing Tor..."
    case "$OS_TYPE" in
        ubuntu|debian|pop|linuxmint|kali)
            sudo apt install -y -qq tor 2>/dev/null
            sudo systemctl enable tor --now 2>/dev/null || true
            ;;
        fedora|rhel|centos)
            sudo dnf install -y -q tor 2>/dev/null
            sudo systemctl enable tor --now 2>/dev/null || true
            ;;
        arch|manjaro)
            sudo pacman -S --noconfirm tor 2>/dev/null
            sudo systemctl enable tor --now 2>/dev/null || true
            ;;
        macos)
            brew install tor 2>/dev/null || true
            ;;
    esac
    print_ok "Tor installed"
}

setup_firewall() {
    if [ "$QUICK_MODE" = true ]; then
        return 0
    fi

    print_prompt "Configure firewall to allow port $AGENT_PORT? [y/N]"
    read -r ans
    if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
        return 0
    fi

    if command -v ufw &>/dev/null && sudo ufw status | grep -q "Status: active"; then
        sudo ufw allow "$AGENT_PORT/tcp" 2>/dev/null
        sudo ufw allow "$DHT_PORT/udp" 2>/dev/null
        print_ok "UFW rules added"
    elif command -v firewall-cmd &>/dev/null; then
        sudo firewall-cmd --permanent --add-port="$AGENT_PORT/tcp" 2>/dev/null
        sudo firewall-cmd --permanent --add-port="$DHT_PORT/udp" 2>/dev/null
        sudo firewall-cmd --reload 2>/dev/null
        print_ok "firewalld rules added"
    else
        print_warn "No firewall detected — ports $AGENT_PORT (TCP) and $DHT_PORT (UDP) may need manual configuration"
    fi
}

setup_systemd() {
    if [ "$INSTALL_SERVICE" = false ] || [ "$OS_TYPE" = "macos" ]; then
        return 0
    fi

    SERVICE_NAME="agent-club"
    SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

    print_info "Creating systemd service..."

    # Find python path
    PYTHON_BIN="$VENV_DIR/bin/python"
    CLI_PATH="$INSTALL_DIR/agent_club/cli.py"

    sudo tee "$SERVICE_FILE" > /dev/null << SYSTEMDEOF
[Unit]
Description=Agent Club — Decentralized P2P Agent Hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
Environment="HOME=$HOME"
ExecStart=$PYTHON_BIN -m agent_club start --host 0.0.0.0 --port $AGENT_PORT
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=agent-club

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$HOME/.agent-club
ReadWritePaths=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
SYSTEMDEOF

    sudo systemctl daemon-reload
    print_ok "systemd service created: $SERVICE_NAME"
    print_info "Manage with:"
    echo -e "    ${CYAN}sudo systemctl start agent-club${NC}     # Start now"
    echo -e "    ${CYAN}sudo systemctl enable agent-club${NC}    # Auto-start on boot"
    echo -e "    ${CYAN}sudo systemctl status agent-club${NC}    # Check status"
    echo -e "    ${CYAN}sudo journalctl -u agent-club -f${NC}    # View logs"

    if [ "$QUICK_MODE" = false ]; then
        print_prompt "Enable and start agent-club now? [y/N]"
        read -r ans
        if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
            sudo systemctl enable --now agent-club
            print_ok "agent-club is running!"
        fi
    fi
}

create_launchd() {
    if [ "$OS_TYPE" != "macos" ] || [ "$INSTALL_SERVICE" = false ]; then
        return 0
    fi

    PLIST_FILE="$HOME/Library/LaunchAgents/com.agentclub.plist"

    print_info "Creating launchd service..."

    cat > "$PLIST_FILE" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentclub</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_DIR/bin/python</string>
        <string>-m</string>
        <string>agent_club</string>
        <string>start</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>$AGENT_PORT</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.agent-club/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.agent-club/logs/stderr.log</string>
</dict>
</plist>
PLISTEOF

    launchctl load "$PLIST_FILE" 2>/dev/null || true
    print_ok "launchd service created"
}

# ═══════════════════════════════════════════════════════
# 📦 Installation Steps
# ═══════════════════════════════════════════════════════
step1_parse_args() {
    print_step "1" "Parsing options..."

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --quick)
                QUICK_MODE=true
                ;;
            --with-tor)
                WITH_TOR=true
                ;;
            --port)
                AGENT_PORT="$2"
                shift
                ;;
            --name)
                AGENT_NAME="$2"
                shift
                ;;
            --no-service)
                INSTALL_SERVICE=false
                ;;
            --help|-h)
                echo "Usage: bash install.sh [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --quick          Quick install (accept all defaults)"
                echo "  --with-tor       Install with Tor support"
                echo "  --port PORT      WebSocket port (default: 8765)"
                echo "  --name NAME      Agent name"
                echo "  --no-service     Don't install systemd/launchd service"
                echo "  --help           Show this help"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1 (use --help)"
                exit 1
                ;;
        esac
        shift
    done

    print_ok "Options parsed"
}

step2_check_prereqs() {
    print_step "2" "Checking prerequisites..."

    # OS detection
    detect_os
    print_info "Detected OS: ${BOLD}$OS_TYPE${NC}"

    # Check Python
    if command -v python3 &>/dev/null; then
        PY_VER=$(python3 --version 2>&1 | cut -d' ' -f2)
        print_ok "Python $PY_VER found"
    else
        print_warn "Python3 not found — will install"
    fi

    # Check pip
    if command -v pip3 &>/dev/null; then
        print_ok "pip3 found"
    else
        print_warn "pip3 not found — will install"
    fi

    # Check git
    if command -v git &>/dev/null; then
        print_ok "git found"
    else
        print_warn "git not found — will install"
    fi

    # Check disk space
    AVAIL_KB=$(df -k "$HOME" | tail -1 | awk '{print $4}')
    AVAIL_MB=$((AVAIL_KB / 1024))
    if [ "$AVAIL_MB" -lt 500 ]; then
        print_error "Low disk space! Available: ${AVAIL_MB}MB (need ~500MB)"
        exit 1
    fi
    print_ok "Disk space: ${AVAIL_MB}MB available"

    # Check RAM
    if [ "$OS_TYPE" != "macos" ]; then
        TOTAL_RAM=$(free -m 2>/dev/null | awk '/Mem:/{print $2}' || echo "unknown")
    else
        TOTAL_RAM=$(sysctl -n hw.memsize 2>/dev/null | awk '{print int($1/1024/1024)}' || echo "unknown")
    fi
    if [ "$TOTAL_RAM" != "unknown" ] && [ "$TOTAL_RAM" -lt 256 ]; then
        print_error "Low RAM: ${TOTAL_RAM}MB (need ~256MB)"
        exit 1
    fi
    print_ok "RAM: ${TOTAL_RAM}MB"
}

step3_install_deps() {
    print_step "3" "Installing system dependencies..."
    install_python_deps
    print_ok "System dependencies ready"
}

step4_clone_repo() {
    print_step "4" "Getting Agent Club source..."

    if [ -d "$INSTALL_DIR/.git" ]; then
        print_info "Existing installation found — updating..."
        cd "$INSTALL_DIR"
        git pull --ff-only 2>/dev/null || print_warn "Could not update (local changes?)"
    elif [ -d "$INSTALL_DIR" ]; then
        print_warn "Directory exists but not a git repo"
        if [ "$QUICK_MODE" = false ]; then
            print_prompt "Overwrite directory? [y/N]"
            read -r ans
            [ "$ans" = "y" ] || [ "$ans" = "Y" ] && rm -rf "$INSTALL_DIR"
        fi
    fi

    if [ ! -d "$INSTALL_DIR" ]; then
        # ถ้าไม่มี git repo (local install), copy from current directory
        if [ -f "$(dirname "$0")/pyproject.toml" ]; then
            print_info "Local install from $(dirname "$0")..."
            mkdir -p "$INSTALL_DIR"
            cp -r "$(dirname "$0")"/* "$INSTALL_DIR/"
        else
            print_info "Cloning from git..."
            git clone --depth 1 "$GIT_REPO" "$INSTALL_DIR" 2>/dev/null || {
                print_warn "Git clone failed — trying to copy from current directory"
                if [ -f "./pyproject.toml" ]; then
                    mkdir -p "$INSTALL_DIR"
                    cp -r ./* "$INSTALL_DIR/"
                else
                    print_error "No source found! Make sure you're in the agent-club directory"
                    print_info "Or clone manually: git clone $GIT_REPO"
                    exit 1
                fi
            }
        fi
    fi

    cd "$INSTALL_DIR"
    print_ok "Source code ready at $INSTALL_DIR"
}

step5_setup_venv() {
    print_step "5" "Setting up Python virtual environment..."

    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
    fi

    # Activate and install
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q 2>/dev/null
    pip install -e ".[dev]" -q 2>/dev/null || pip install -e . -q

    # Install Tor deps if requested
    if [ "$WITH_TOR" = true ]; then
        pip install stem PySocks -q 2>/dev/null
    fi

    deactivate
    print_ok "Virtual environment ready"
}

step6_create_identity() {
    print_step "6" "Setting up agent identity..."

    source "$VENV_DIR/bin/activate"

    if [ -f "$HOME/.agent-club/identity.enc" ]; then
        print_ok "Existing identity found"
        return 0
    fi

    if [ -z "$AGENT_NAME" ]; then
        if [ "$QUICK_MODE" = true ]; then
            AGENT_NAME="agent-$(hostname -s 2>/dev/null || echo "club")"
        else
            print_prompt "Agent name [$AGENT_NAME]"
            read -r input_name
            [ -n "$input_name" ] && AGENT_NAME="$input_name"
            if [ -z "$AGENT_NAME" ]; then
                AGENT_NAME="agent-$(hostname -s 2>/dev/null || echo "club")"
            fi
        fi
    fi

    print_info "Creating identity for: ${BOLD}$AGENT_NAME${NC}"

    if [ "$QUICK_MODE" = true ]; then
        PASSWORD="agentclub123"
        print_info "Quick mode: using default password (change with 'agent-club init --force')"
    else
        print_prompt "Set encryption password (leave blank for auto-generate):"
        read -s -r password
        echo ""
        if [ -z "$password" ]; then
            PASSWORD="agentclub$(date +%s | sha256sum | base64 | head -c12)"
            print_info "Generated password: ${BOLD}$PASSWORD${NC} (save this!)"
        else
            print_prompt "Confirm password:"
            read -s -r password2
            echo ""
            if [ "$password" != "$password2" ]; then
                print_error "Passwords don't match!"
                exit 1
            fi
            PASSWORD="$password"
        fi
    fi

    # Create identity using Python API
    python3 << PYEOF
import json, os
from agent_club.crypto.keys import KeyBundle

bundle = KeyBundle(name="$AGENT_NAME")
data = bundle.export(b"$PASSWORD")

os.makedirs(os.path.expanduser("~/.agent-club"), exist_ok=True)
conf_file = os.path.expanduser("~/.agent-club/identity.enc")
with open(conf_file, "w") as f:
    json.dump(data, f)

# Save password hint (for quick mode only)
if "$QUICK_MODE" == "true":
    hint_file = os.path.expanduser("~/.agent-club/.password_hint")
    with open(hint_file, "w") as f:
        f.write("Default password set during quick install\\n")

print(f"FINGERPRINT:{bundle.fingerprint}")
PYEOF

    FINGERPRINT=$(python3 -c "
import json
with open('$HOME/.agent-club/identity.enc') as f:
    d = json.load(f)
print(d.get('fingerprint','unknown'))
" 2>/dev/null || echo "unknown")

    deactivate
    print_ok "Identity created!"
    print_info "  Name:        ${BOLD}$AGENT_NAME${NC}"
    print_info "  Fingerprint: ${BOLD}$FINGERPRINT${NC}"
    if [ "$QUICK_MODE" = true ]; then
        print_warn "  Password:    agentclub123 (change it!)"
    fi
}

step7_configure() {
    print_step "7" "Creating configuration..."

    mkdir -p "$HOME/.agent-club/logs"

    cat > "$HOME/.agent-club/config.yaml" << YAMLEOF
# Agent Club Configuration
# Auto-generated by install.sh — edit freely!
transport:
  host: "0.0.0.0"
  port: $AGENT_PORT
dht:
  enabled: true
  port: $DHT_PORT
tor:
  enabled: $WITH_TOR
room:
  max_rooms: 10
  default_join_policy: public
security:
  encryption: true
  max_peers: 100
audit:
  enabled: true
  log_dir: "~/.agent-club/logs"
YAMLEOF

    print_ok "Configuration saved to ~/.agent-club/config.yaml"
}

step8_install_tor() {
    print_step "8" "Setting up Tor..."
    install_tor
    if [ "$WITH_TOR" = true ]; then
        print_info "Tor will be available at: agent-club tor enable"
    fi
}

step9_setup_firewall() {
    print_step "9" "Configuring firewall..."
    setup_firewall
    print_ok "Firewall configuration done"
}

step10_install_service() {
    TOTAL_STEPS=10
    print_step "10" "Installing service..."

    if [ "$OS_TYPE" = "macos" ]; then
        create_launchd
    else
        setup_systemd
    fi
    print_ok "Service installation complete"
}

step_final_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║         ✅  Agent Club Installed Successfully!       ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Install Directory:${NC} $INSTALL_DIR"
    echo -e "  ${BOLD}Agent Name:${NC}       $AGENT_NAME"
    echo -e "  ${BOLD}Fingerprint:${NC}      $FINGERPRINT"
    echo -e "  ${BOLD}WebSocket Port:${NC}   $AGENT_PORT"
    echo -e "  ${BOLD}Tor Enabled:${NC}      $WITH_TOR"
    echo ""

    echo -e "  ${BOLD}📋 Commands:${NC}"
    echo -e "    ${CYAN}source $VENV_DIR/bin/activate${NC}  # Activate environment"
    echo -e "    ${CYAN}agent-club status${NC}              # Check status"
    echo -e "    ${CYAN}agent-club room create \"my-room\"${NC}  # Create a room"
    echo ""

    if [ "$INSTALL_SERVICE" = true ] && [ "$OS_TYPE" != "macos" ]; then
        echo -e "  ${BOLD}🛠️  Service Management:${NC}"
        echo -e "    ${CYAN}sudo systemctl start agent-club${NC}"
        echo -e "    ${CYAN}sudo systemctl enable agent-club${NC}"
        echo -e "    ${CYAN}sudo journalctl -u agent-club -f${NC}"
    elif [ "$INSTALL_SERVICE" = true ]; then
        echo -e "  ${BOLD}🛠️  Service Management:${NC}"
        echo -e "    ${CYAN}launchctl start com.agentclub${NC}"
        echo -e "    ${CYAN}launchctl stop com.agentclub${NC}"
    fi

    echo ""
    echo -e "  ${BOLD}🔒 Important:${NC}"
    echo -e "    Save your encryption password in a secure place!"
    echo -e "    Identity file: ~/.agent-club/identity.enc"
    echo ""

    # ถ้าเป็น quick mode แจ้งเตือนเรื่อง password
    if [ "$QUICK_MODE" = true ]; then
        echo -e "  ${YELLOW}⚠️  Quick install used default password 'agentclub123'${NC}"
        echo -e "  ${YELLOW}    Run to change: agent-club init --force${NC}"
        echo ""
    fi

    echo -e "  ${GREEN}Happy hacking! 🕸️🐍✨${NC}"
    echo ""
}

# ═══════════════════════════════════════════════════════
# 🚀 Main
# ═══════════════════════════════════════════════════════
main() {
    TOTAL_STEPS=10

    print_banner

    step1_parse_args "$@"
    step2_check_prereqs
    step3_install_deps
    step4_clone_repo
    step5_setup_venv
    step6_create_identity
    step7_configure
    step8_install_tor
    step9_setup_firewall
    step10_install_service
    step_final_summary
}

main "$@"