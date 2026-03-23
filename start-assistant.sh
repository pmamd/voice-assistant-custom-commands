#!/bin/bash
# Voice Assistant Demo Script
# This script starts llama-server, Wyoming-Piper TTS, and the voice assistant

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Voice Assistant with Custom Commands"
echo "=========================================="
echo ""

# Note: HSA_OVERRIDE_GFX_VERSION is intentionally NOT set here.
# talk-llama-custom uses CPU only (no GPU/HIP). llama-server manages
# its own GPU context and must NOT inherit any HSA overrides.

# Configuration
PIPER_VOICE="en_US-lessac-medium"
PIPER_DATA_DIR="./piper-data"  # Where Piper stores voice models
WYOMING_PORT=10200
WHISPER_MODEL="./whisper.cpp/models/ggml-tiny.en.bin"
LLAMA_MODEL="./models/mistral-7b-instruct-v0.2.Q5_0.gguf"
TALK_LLAMA_BIN="./build/bin/talk-llama-custom"

# llama-server configuration
LLAMA_SERVER_PORT=8080
LLAMA_SERVER_URL="http://localhost:${LLAMA_SERVER_PORT}"
# Allow override via environment variable
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-}"

# Find llama-server binary
_find_llama_server() {
    if [[ -n "$LLAMA_SERVER_BIN" && -x "$LLAMA_SERVER_BIN" ]]; then
        echo "$LLAMA_SERVER_BIN"
        return
    fi
    # Check common locations
    for candidate in \
        "$HOME/.local/bin/llama-server" \
        "/usr/local/bin/llama-server" \
        "/usr/bin/llama-server" \
        "./build/bin/llama-server" \
        "./llama-server"; do
        if [[ -x "$candidate" ]]; then
            echo "$candidate"
            return
        fi
    done
    echo ""
}

# Check if talk-llama-custom is already running and kill it
if pgrep -f "talk-llama-custom" > /dev/null; then
    echo -e "${YELLOW}⚠ Found existing talk-llama-custom process(es)${NC}"
    echo "Killing previous instances..."
    pkill -9 -f "talk-llama-custom" || true
    sleep 1
    echo -e "${GREEN}✓ Cleaned up previous instances${NC}"
    echo ""
fi

# Check if Wyoming-Piper is already running
_wyoming_port_listening() {
    ss -tlnp | grep -q ":$WYOMING_PORT "
}

_wyoming_kill_all() {
    # Kill all matching processes by PID (pkill can't kill zombies, but kill -9 on PIDs works)
    for pid in $(pgrep -f "wyoming.piper" 2>/dev/null); do
        kill -9 "$pid" 2>/dev/null || true
    done
    sleep 1
    # Also kill anything still holding the port
    if _wyoming_port_listening; then
        PORT_PIDS=$(ss -tlnp | grep ":$WYOMING_PORT " | grep -oP 'pid=\K[0-9]+')
        for pid in $PORT_PIDS; do kill -9 "$pid" 2>/dev/null || true; done
        sleep 1
    fi
}

if pgrep -f "wyoming.piper" > /dev/null; then
    if ! _wyoming_port_listening; then
        # Process exists but port not listening — zombie or crashed, restart silently
        echo -e "${YELLOW}⚠ Wyoming-Piper process found but port $WYOMING_PORT not listening (zombie/crashed) — restarting${NC}"
        _wyoming_kill_all
    else
        echo -e "${YELLOW}⚠ Wyoming-Piper is already running${NC}"
        read -p "Stop it and restart? (y/N) [default: N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Stopping Wyoming-Piper..."
            _wyoming_kill_all
            if _wyoming_port_listening; then
                echo -e "${RED}✗ Port $WYOMING_PORT still in use — try: kill -9 \$(lsof -ti tcp:$WYOMING_PORT)${NC}"
                exit 1
            fi
        else
            echo "Continuing with existing Wyoming-Piper instance..."
        fi
    fi
fi

# Start Wyoming-Piper if port not listening (use port as truth, not pgrep — zombies fool pgrep)
if ! _wyoming_port_listening; then
    echo -e "${GREEN}Starting Wyoming-Piper TTS server (modified version with tool support)...${NC}"

    # Create data directory if it doesn't exist
    mkdir -p "$PIPER_DATA_DIR"

    # Start Wyoming-Piper using the pipx entry point (works regardless of user/system Python)
    "$HOME/.local/bin/wyoming-piper-custom" \
        --piper "$HOME/.local/bin/piper" \
        --voice "$PIPER_VOICE" \
        --data-dir "$PIPER_DATA_DIR" \
        --uri "tcp://0.0.0.0:$WYOMING_PORT" \
        > /tmp/wyoming-piper.log 2>&1 &

    WYOMING_PID=$!
    echo "Wyoming-Piper started (PID: $WYOMING_PID)"
    echo "Log: /tmp/wyoming-piper.log"

    # Wait for server to be ready
    echo "Waiting for TTS server to start..."
    sleep 3

    if ! _wyoming_port_listening; then
        echo -e "${RED}✗ Failed to start Wyoming-Piper${NC}"
        echo "Check log: cat /tmp/wyoming-piper.log"
        exit 1
    fi

    echo -e "${GREEN}✓ TTS server ready${NC}"
    echo ""
fi

# HTTP check helper — uses curl if available, falls back to Python
_http_ok() {
    local url="$1"
    if command -v curl &>/dev/null; then
        curl -s --connect-timeout 2 "$url" > /dev/null 2>&1
    else
        python3 -c "
import urllib.request, sys
try:
    urllib.request.urlopen('$url', timeout=2)
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null
    fi
}

_llama_start() {
    local bin model port
    bin=$(_find_llama_server)
    model="$LLAMA_MODEL"
    port="$LLAMA_SERVER_PORT"

    if [[ -z "$bin" ]]; then
        echo -e "${RED}✗ llama-server binary not found${NC}"
        echo "  Install llama-server to ~/.local/bin/ or set LLAMA_SERVER_BIN"
        exit 1
    fi
    if [ ! -f "$model" ]; then
        echo -e "${RED}✗ LLaMA model not found at $model${NC}"
        exit 1
    fi

    echo -e "${GREEN}Starting llama-server...${NC}"
    echo "  Binary: $bin"
    echo "  Model:  $model"
    echo "  Port:   $port"

    "$bin" --model "$model" --host 0.0.0.0 --port "$port" -ngl 999 \
        > /tmp/llama-server.log 2>&1 &
    LLAMA_SERVER_PID=$!
    echo "llama-server started (PID: $LLAMA_SERVER_PID), log: /tmp/llama-server.log"

    echo "Waiting for llama-server to load model..."
    for i in $(seq 1 120); do
        if _http_ok "${LLAMA_SERVER_URL}/health"; then
            echo -e "\n${GREEN}✓ llama-server ready${NC}"
            return 0
        fi
        if ! kill -0 "$LLAMA_SERVER_PID" 2>/dev/null; then
            echo -e "\n${RED}✗ llama-server process died — check: cat /tmp/llama-server.log${NC}"
            exit 1
        fi
        printf "\r  Loading model: %ds..." "$i"
        sleep 1
    done
    echo ""
    echo -e "${RED}✗ llama-server failed to start within 120s${NC}"
    exit 1
}

# Check/start llama-server — mirrors Wyoming-Piper logic
if _http_ok "${LLAMA_SERVER_URL}/health"; then
    echo -e "${YELLOW}⚠ llama-server already running at ${LLAMA_SERVER_URL}${NC}"
    read -p "Stop it and restart? (y/N) [default: N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Stopping llama-server..."
        pkill -f "llama-server.*${LLAMA_SERVER_PORT}" || true
        sleep 2
        if _http_ok "${LLAMA_SERVER_URL}/health"; then
            echo -e "${RED}✗ llama-server still running — kill it manually${NC}"
            exit 1
        fi
        _llama_start
    else
        echo "Continuing with existing llama-server..."
    fi
else
    _llama_start
fi

# Check required files
echo "Checking required files..."

if [ ! -f "$TALK_LLAMA_BIN" ]; then
    echo -e "${RED}✗ Error: talk-llama-custom not found at $TALK_LLAMA_BIN${NC}"
    echo "Please build it with: cmake -B build -DWHISPER_SDL2=ON && cmake --build build"
    exit 1
fi

if [ ! -f "$WHISPER_MODEL" ]; then
    echo -e "${RED}✗ Error: Whisper model not found at $WHISPER_MODEL${NC}"
    echo "Please download it with: cd whisper.cpp/models && bash download-ggml-model.sh tiny.en"
    exit 1
fi

echo -e "${GREEN}✓ All required files found${NC}"
echo ""

# Detect available microphones
echo "Detecting audio devices..."
CAPTURE_DEVICE="-1"  # Default: use default device

# Get list of capture devices using SDL
if ! command -v arecord &> /dev/null; then
    echo -e "${RED}✗ arecord not found — install alsa-utils: sudo apt-get install alsa-utils${NC}"
    exit 1
fi

DEVICE_LIST=$(arecord -l 2>/dev/null | grep "^card" | sed 's/card \([0-9]\+\).*device \([0-9]\+\).*/hw:\1,\2/' || echo "")

if [ -z "$DEVICE_LIST" ]; then
    echo -e "${RED}✗ No audio capture devices found — plug in a microphone and try again${NC}"
    exit 1
fi

if [ -n "$DEVICE_LIST" ]; then
        DEVICE_COUNT=$(echo "$DEVICE_LIST" | wc -l)

        if [ "$DEVICE_COUNT" -gt 1 ]; then
            echo ""
            echo "Multiple microphones detected:"

            # Build array of device names for display
            DEVICE_NAMES=()
            DEVICE_NUM=0
            while IFS= read -r device; do
                # Convert hw:X,Y format to grep pattern for card X, device Y
                CARD_NUM=$(echo "$device" | sed 's/hw:\([0-9]\+\),.*/\1/')
                DEV_NUM=$(echo "$device" | sed 's/hw:[0-9]\+,\([0-9]\+\)/\1/')

                # Extract card name and device name from arecord -l output (extract bracketed names)
                DEVICE_NAME=$(arecord -l 2>/dev/null | grep -E "card $CARD_NUM:.*device $DEV_NUM:" | sed 's/card [0-9]\+: [^ ]* \[\([^]]*\)\], device [0-9]\+: [^[]*\[\([^]]*\)\].*/\1 - \2/')
                DEVICE_NAMES+=("$DEVICE_NAME")
                echo "$DEVICE_NUM: $DEVICE_NAME"
                DEVICE_NUM=$((DEVICE_NUM + 1))
            done <<< "$DEVICE_LIST"

            echo ""
            read -p "Select microphone [0-$((DEVICE_COUNT - 1))] (default: 0) " -r MIC_CHOICE
            echo ""

            # Default to 0 if empty
            if [ -z "$MIC_CHOICE" ]; then
                MIC_CHOICE=0
            fi

            if [[ "$MIC_CHOICE" =~ ^[0-9]+$ ]] && [ "$MIC_CHOICE" -ge 0 ] && [ "$MIC_CHOICE" -lt "$DEVICE_COUNT" ]; then
                # SDL uses the device index directly (0-indexed)
                CAPTURE_DEVICE="$MIC_CHOICE"
                echo -e "${GREEN}✓ Using microphone $MIC_CHOICE: ${DEVICE_NAMES[$MIC_CHOICE]}${NC}"
            else
                echo -e "${YELLOW}⚠ Invalid selection, using default (0)${NC}"
                CAPTURE_DEVICE="0"
            fi
        else
            echo -e "${GREEN}✓ Using default microphone${NC}"
        fi
    fi

echo ""

# Instructions
echo "=========================================="
echo "Starting Voice Assistant"
echo "=========================================="
echo ""
echo "Controls:"
echo "  - Speak into your microphone to interact"
echo "  - Say 'stop' to interrupt AI speech"
echo "  - Press Ctrl+C to exit (now with graceful shutdown!)"
echo ""
echo "Services:"
echo "  - Whisper:       $WHISPER_MODEL"
echo "  - LLM server:    $LLAMA_SERVER_URL"
echo "  - LLM model:     $LLAMA_MODEL"
echo "  - TTS Voice:     $PIPER_VOICE"
echo ""
echo "Monitoring:"
echo "  - Wyoming-Piper log:  tail -f /tmp/wyoming-piper.log"
echo "  - llama-server log:   tail -f /tmp/llama-server.log"
echo "  - To watch TTS requests in another terminal:"
echo "    tail -f /tmp/wyoming-piper.log | grep -i 'synthesize\\|error'"
echo ""
echo "=========================================="
echo ""

# Start the voice assistant
$TALK_LLAMA_BIN \
    -mw "$WHISPER_MODEL" \
    --llama-url "$LLAMA_SERVER_URL" \
    --xtts-url "http://localhost:$WYOMING_PORT/" \
    --xtts-voice "$PIPER_VOICE" \
    --temp 0.5 \
    -vth 1.2 \
    -n 300 \
    --allow-newline \
    -c "$CAPTURE_DEVICE"

# Cleanup on exit
echo ""
echo "=========================================="
echo "Shutting down..."
echo "=========================================="

# Ask if user wants to stop services
read -p "Stop llama-server? (y/N) [default: N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Stopping llama-server..."
    pkill -f "llama-server.*${LLAMA_SERVER_PORT}" || true
    echo -e "${GREEN}✓ llama-server stopped${NC}"
else
    echo "llama-server left running in background"
fi

read -p "Stop Wyoming-Piper TTS server? (y/N) [default: N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Stopping Wyoming-Piper..."
    pkill -f "wyoming.piper" || true
    echo -e "${GREEN}✓ TTS server stopped${NC}"
else
    echo "Wyoming-Piper left running in background"
fi

echo "Goodbye!"
