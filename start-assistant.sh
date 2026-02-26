#!/bin/bash
# Voice Assistant Demo Script
# This script starts the Wyoming-Piper TTS server and the voice assistant

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

# Configuration
# Use system Wyoming-Piper (patched with queue depth logging)
WYOMING_PIPER_CMD="/home/paul/.local/bin/wyoming-piper"
WYOMING_PIPER_DIR=""  # Not needed for system installation
PIPER_VOICE="en_US-lessac-medium"
PIPER_DATA_DIR="./piper-data"  # Where Piper stores voice models
WYOMING_PORT=10200
WHISPER_MODEL="./whisper.cpp/models/ggml-tiny.en.bin"
LLAMA_MODEL="./models/llama-2-7b-chat.Q4_K_M.gguf"
TALK_LLAMA_BIN="./build/bin/talk-llama-custom"

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
if pgrep -f "wyoming-piper" > /dev/null; then
    echo -e "${YELLOW}⚠ Wyoming-Piper is already running${NC}"
    read -p "Stop it and restart? (y/N) [default: N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Stopping Wyoming-Piper..."
        pkill -f "wyoming-piper" || true
        sleep 2
    else
        echo "Continuing with existing Wyoming-Piper instance..."
    fi
fi

# Start Wyoming-Piper if not running
if ! pgrep -f "wyoming-piper" > /dev/null; then
    echo -e "${GREEN}Starting Wyoming-Piper TTS server (patched with queue logging)...${NC}"

    # Create data directory if it doesn't exist
    mkdir -p "$PIPER_DATA_DIR"

    # Start system Wyoming-Piper (patched with queue depth logging)
    $WYOMING_PIPER_CMD \
        --piper /home/paul/.local/bin/piper \
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
    
    if ! pgrep -f "wyoming-piper" > /dev/null; then
        echo -e "${RED}✗ Failed to start Wyoming-Piper${NC}"
        echo "Check log: cat /tmp/wyoming-piper.log"
        exit 1
    fi
    
    echo -e "${GREEN}✓ TTS server ready${NC}"
    echo ""
fi

# Check required files
echo "Checking required files..."

if [ ! -f "$TALK_LLAMA_BIN" ]; then
    echo -e "${RED}✗ Error: talk-llama-custom not found at $TALK_LLAMA_BIN${NC}"
    echo "Please build it with: cmake -B build && cmake --build build"
    exit 1
fi

if [ ! -f "$WHISPER_MODEL" ]; then
    echo -e "${RED}✗ Error: Whisper model not found at $WHISPER_MODEL${NC}"
    echo "Please download it with: cd whisper.cpp/models && bash download-ggml-model.sh tiny.en"
    exit 1
fi

if [ ! -f "$LLAMA_MODEL" ]; then
    echo -e "${RED}✗ Error: LLaMA model not found at $LLAMA_MODEL${NC}"
    echo "Please download a GGUF model and place it at: $LLAMA_MODEL"
    exit 1
fi

echo -e "${GREEN}✓ All required files found${NC}"
echo ""

# Detect available microphones
echo "Detecting audio devices..."
CAPTURE_DEVICE="-1"  # Default: use default device

# Get list of capture devices using SDL
if command -v arecord &> /dev/null; then
    # Get list of ALSA capture devices
    DEVICE_LIST=$(arecord -l 2>/dev/null | grep "^card" | sed 's/card \([0-9]\+\).*device \([0-9]\+\).*/hw:\1,\2/' || echo "")

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
echo "Models:"
echo "  - Whisper: $WHISPER_MODEL"
echo "  - LLaMA: $LLAMA_MODEL"
echo "  - TTS Voice: $PIPER_VOICE"
echo ""
echo "Monitoring:"
echo "  - Wyoming-Piper log: tail -f /tmp/wyoming-piper.log"
echo "  - To watch TTS requests in another terminal:"
echo "    tail -f /tmp/wyoming-piper.log | grep -i 'synthesize\\|error'"
echo ""
echo "=========================================="
echo ""

# Start the voice assistant
# VAD threshold lowered to 0.30 for better voice detection
# Print energy enabled to help debug audio issues
$TALK_LLAMA_BIN \
    -ml "$LLAMA_MODEL" \
    -mw "$WHISPER_MODEL" \
    --xtts-url "http://localhost:$WYOMING_PORT/" \
    --xtts-voice "$PIPER_VOICE" \
    --temp 0.5 \
    -vth 1.2 \
    -c "$CAPTURE_DEVICE" \
    -pe

# Cleanup on exit
echo ""
echo "=========================================="
echo "Shutting down..."
echo "=========================================="

# Ask if user wants to stop Wyoming-Piper
read -p "Stop Wyoming-Piper TTS server? (y/N) [default: N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Stopping Wyoming-Piper..."
    pkill -f "wyoming-piper" || true
    echo -e "${GREEN}✓ TTS server stopped${NC}"
else
    echo "Wyoming-Piper left running in background"
fi

echo "Goodbye!"
