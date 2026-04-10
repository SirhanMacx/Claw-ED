#!/usr/bin/env bash
#
# EDUagent one-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/eduagent/eduagent/main/scripts/install.sh | bash
#
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}==>${NC} ${BOLD}$*${NC}"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}!${NC} $*"; }
err()   { echo -e "${RED}✗${NC} $*" >&2; }

echo ""
echo -e "${BOLD}EDUagent Installer${NC}"
echo "Your teaching files → your AI co-teacher."
echo ""

# ── Detect OS ──────────────────────────────────────────────────────────────────

OS="$(uname -s)"
case "$OS" in
    Darwin) PLATFORM="mac" ;;
    Linux)  PLATFORM="linux" ;;
    *)
        err "Unsupported OS: $OS"
        echo "EDUagent supports macOS and Linux. On Windows, use WSL or Docker."
        exit 1
        ;;
esac
ok "Detected: $PLATFORM"

# ── Check/install Python ──────────────────────────────────────────────────────

install_python_mac() {
    if command -v brew &>/dev/null; then
        info "Installing Python via Homebrew..."
        brew install python@3.12
    else
        info "Installing Homebrew first..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Add Homebrew to PATH for Apple Silicon
        if [[ -f /opt/homebrew/bin/brew ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
        brew install python@3.12
    fi
}

install_python_linux() {
    info "Installing Python..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq python3 python3-pip python3-venv
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3 python3-pip
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm python python-pip
    else
        err "Could not detect package manager. Install Python 3.10+ manually, then re-run."
        exit 1
    fi
}

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 10 ]]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    warn "Python 3.10+ not found."
    if [[ "$PLATFORM" == "mac" ]]; then
        install_python_mac
    else
        install_python_linux
    fi
    # Re-detect
    for candidate in python3 python; do
        if command -v "$candidate" &>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    done
    if [[ -z "$PYTHON" ]]; then
        err "Python installation failed. Install Python 3.10+ manually and re-run."
        exit 1
    fi
fi
ok "Python: $($PYTHON --version)"

# ── Install EDUagent ──────────────────────────────────────────────────────────

info "Installing EDUagent with Telegram support..."
$PYTHON -m pip install --quiet --upgrade pip
$PYTHON -m pip install --quiet 'eduagent[telegram]'

if ! command -v eduagent &>/dev/null; then
    # pip installed to a path not in PATH — common on Mac
    warn "eduagent not found in PATH. Checking pip location..."
    PIPPATH=$($PYTHON -m pip show eduagent 2>/dev/null | grep Location | cut -d' ' -f2 || true)
    if [[ -n "$PIPPATH" ]]; then
        BINDIR=$(dirname "$PIPPATH")/bin
        if [[ -f "$BINDIR/eduagent" ]]; then
            warn "Add this to your shell profile: export PATH=\"$BINDIR:\$PATH\""
        fi
    fi
fi
ok "EDUagent installed"

# ── Config directory ──────────────────────────────────────────────────────────

CONFIG_DIR="$HOME/.eduagent"
CONFIG_FILE="$CONFIG_DIR/config.json"
mkdir -p "$CONFIG_DIR"

# ── API key setup ─────────────────────────────────────────────────────────────

echo ""
info "LLM Backend Setup"
echo ""
echo "EDUagent needs an AI model to generate lessons. Pick one:"
echo ""
echo "  1) Anthropic (Claude) — best quality, pay per use"
echo "  2) OpenAI (GPT-4o) — great quality, pay per use"
echo "  3) Ollama — free, runs locally on your machine"
echo ""

read -rp "Choice [1/2/3]: " llm_choice

MODEL_PROVIDER=""
API_KEY_VAR=""
API_KEY_VAL=""

case "${llm_choice:-1}" in
    1)
        MODEL_PROVIDER="anthropic"
        echo ""
        echo "Get your API key at: https://console.anthropic.com/"
        read -rp "Anthropic API key (sk-ant-...): " API_KEY_VAL
        API_KEY_VAR="ANTHROPIC_API_KEY"
        ;;
    2)
        MODEL_PROVIDER="openai"
        echo ""
        echo "Get your API key at: https://platform.openai.com/"
        read -rp "OpenAI API key (sk-...): " API_KEY_VAL
        API_KEY_VAR="OPENAI_API_KEY"
        ;;
    3)
        MODEL_PROVIDER="ollama"
        echo ""
        if ! command -v ollama &>/dev/null; then
            warn "Ollama not found. Install it from https://ollama.com then run: ollama pull llama3.2"
        else
            ok "Ollama found"
            echo "Make sure you've pulled a model: ollama pull llama3.2"
        fi
        ;;
    *)
        warn "Invalid choice, defaulting to Anthropic"
        MODEL_PROVIDER="anthropic"
        read -rp "Anthropic API key (sk-ant-...): " API_KEY_VAL
        API_KEY_VAR="ANTHROPIC_API_KEY"
        ;;
esac

# Export the key for the current session
if [[ -n "$API_KEY_VAR" && -n "$API_KEY_VAL" ]]; then
    export "$API_KEY_VAR=$API_KEY_VAL"
    ok "API key set for this session"

    # Suggest adding to shell profile
    SHELL_RC=""
    case "$SHELL" in
        */zsh)  SHELL_RC="$HOME/.zshrc" ;;
        */bash) SHELL_RC="$HOME/.bashrc" ;;
    esac
    if [[ -n "$SHELL_RC" ]]; then
        echo ""
        warn "To keep this key across terminal sessions, add to $SHELL_RC:"
        echo "  export $API_KEY_VAR=$API_KEY_VAL"
    fi
fi

# ── Telegram bot token ───────────────────────────────────────────────────────

echo ""
info "Telegram Bot Setup (optional)"
echo ""
echo "To use EDUagent as a Telegram bot:"
echo "  1. Open Telegram, search for @BotFather"
echo "  2. Send /newbot and follow the prompts"
echo "  3. Copy the token BotFather gives you"
echo ""
read -rp "Telegram bot token (or press Enter to skip): " BOT_TOKEN

TELEGRAM_OK=false
if [[ -n "$BOT_TOKEN" ]]; then
    info "Testing Telegram token..."
    RESPONSE=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getMe" 2>/dev/null || echo '{"ok":false}')
    if echo "$RESPONSE" | grep -q '"ok":true'; then
        BOT_NAME=$(echo "$RESPONSE" | $PYTHON -c "import sys,json; print(json.load(sys.stdin)['result']['username'])" 2>/dev/null || echo "your bot")
        ok "Token valid! Bot: @$BOT_NAME"
        TELEGRAM_OK=true
    else
        warn "Token didn't work. Double-check it with @BotFather. You can set it later."
    fi
fi

# ── Write config ──────────────────────────────────────────────────────────────

TELEGRAM_TOKEN_JSON="null"
if [[ "$TELEGRAM_OK" == true ]]; then
    TELEGRAM_TOKEN_JSON="\"$BOT_TOKEN\""
fi

OLLAMA_BASE_URL_JSON="\"http://localhost:11434\""

cat > "$CONFIG_FILE" <<JSONEOF
{
  "provider": "$MODEL_PROVIDER",
  "ollama_base_url": $OLLAMA_BASE_URL_JSON,
  "telegram_bot_token": $TELEGRAM_TOKEN_JSON,
  "output_dir": "./eduagent_output"
}
JSONEOF

mkdir -p "$HOME/.eduagent/data"
ok "Config written to $CONFIG_FILE"

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}EDUagent is ready!${NC}"
echo ""
echo "Try these commands:"
echo ""
echo "  eduagent chat                 # Start a conversation"
echo "  eduagent demo                 # See example output (no API key needed)"
echo "  eduagent ingest ~/Teaching/   # Learn from your lesson plans"
echo "  eduagent serve                # Open web dashboard"
if [[ "$TELEGRAM_OK" == true ]]; then
echo "  eduagent bot --token '...'    # Start Telegram bot"
fi
echo ""
echo "Full docs: https://github.com/eduagent/eduagent"
echo ""
