#!/bin/bash
# Voice Assistant Demo Script
# This script starts the Wyoming-Piper TTS server and the voice assistant

set -e

# Add paths for wyoming-piper-custom and piper libraries
export PATH="$HOME/.local/bin:$PATH"
export LD_LIBRARY_PATH="/opt/piper:$LD_LIBRARY_PATH"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Voice Assistant with Custom Commands"
echo "=========================================="
echo ""

# Configuration - Auto-detect paths
WYOMING_PIPER_CMD="wyoming-piper-custom"
PIPER_VOICE="en_US-lessac-medium"
PIPER_DATA_DIR="./piper-data"
WYOMING_PORT=8020

# Auto-detect Piper binary location
if [ -x "/opt/piper/piper" ]; then
    PIPER_BIN="/opt/piper/piper"
elif [ -x "/usr/local/bin/piper" ]; then
    PIPER_BIN="/usr/local/bin/piper"
elif [ -x "/usr/bin/piper" ]; then
    PIPER_BIN="/usr/bin/piper"
elif [ -x "$HOME/.local/bin/piper" ]; then
    PIPER_BIN="$HOME/.local/bin/piper"
else
    PIPER_BIN="piper"  # Hope it's in PATH
fi

# Model paths - look for common models
WHISPER_MODEL=""
for model in ./whisper.cpp/models/ggml-base.en.bin ./whisper.cpp/models/ggml-tiny.en.bin; do
    if [ -f "$model" ]; then
        WHISPER_MODEL="$model"
        break
    fi
done

LLAMA_MODEL=""
for model in ./models/*.gguf; do
    if [ -f "$model" ]; then
        LLAMA_MODEL="$model"
        break
    fi
done

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

# Check if Wyoming-Piper-Custom is already running
if pgrep -f "wyoming-piper-custom" > /dev/null; then
    echo -e "${YELLOW}⚠ Wyoming-Piper-Custom is already running${NC}"
    read -p "Stop it and restart? (y/N) [default: N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Stopping Wyoming-Piper-Custom..."
        pkill -f "wyoming-piper-custom" || true
        sleep 2
    else
        echo "Continuing with existing Wyoming-Piper-Custom instance..."
    fi
fi

# Start Wyoming-Piper-Custom if not running
if ! pgrep -f "wyoming-piper-custom" > /dev/null; then
    echo -e "${GREEN}Starting Wyoming-Piper-Custom TTS server (custom version with aplay)...${NC}"

    # Create data directory if it doesn't exist
    mkdir -p "$PIPER_DATA_DIR"

    # Start Wyoming-Piper (with custom files installed)
    $WYOMING_PIPER_CMD \
        --piper "$PIPER_BIN" \
        --voice "$PIPER_VOICE" \
        --data-dir "$PIPER_DATA_DIR" \
        --uri "tcp://0.0.0.0:$WYOMING_PORT" \
        > /tmp/wyoming-piper.log 2>&1 &
    
    WYOMING_PID=$!
    echo "Wyoming-Piper-Custom started (PID: $WYOMING_PID)"
    echo "Log: /tmp/wyoming-piper.log"

    # Wait for server to be ready (needs time to download/load voice model)
    echo "Waiting for TTS server to start..."
    echo "(This may take 10-15 seconds for first-time voice model download)"

    # Check if process is still running
    sleep 2
    if ! pgrep -f "wyoming-piper-custom" > /dev/null; then
        echo -e "${RED}✗ Failed to start Wyoming-Piper-Custom${NC}"
        echo "Check log: cat /tmp/wyoming-piper.log"
        exit 1
    fi

    # Wait for port to accept connections (max 30 seconds)
    MAX_WAIT=30
    WAIT_COUNT=0
    while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
        if nc -z localhost $WYOMING_PORT 2>/dev/null; then
            echo -e "${GREEN}✓ TTS server is listening on port $WYOMING_PORT${NC}"
            break
        fi
        sleep 1
        WAIT_COUNT=$((WAIT_COUNT + 1))
        if [ $((WAIT_COUNT % 5)) -eq 0 ]; then
            echo "  Still waiting... ($WAIT_COUNT seconds)"
        fi
    done

    if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
        echo -e "${RED}✗ TTS server did not start within $MAX_WAIT seconds${NC}"
        echo "Check log: cat /tmp/wyoming-piper.log"
        exit 1
    fi

    # Additional wait for voice model to fully load
    echo "Waiting for voice model to load..."
    sleep 3

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
            # Allow setting microphone via environment variable for automation
            if [ -n "$MIC_DEVICE" ]; then
                MIC_CHOICE="$MIC_DEVICE"
                echo "Using microphone $MIC_CHOICE from MIC_DEVICE environment variable"
            else
                read -p "Select microphone [0-$((DEVICE_COUNT - 1))] (default: 0) " -t 10 -r MIC_CHOICE || true
                echo ""
            fi

            # Default to 0 if empty
            if [ -z "$MIC_CHOICE" ]; then
                MIC_CHOICE=0
                echo "No selection made, using default (0)"
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
$TALK_LLAMA_BIN \
    --model-llama "$LLAMA_MODEL" \
    --model-whisper "$WHISPER_MODEL" \
    --xtts-url "http://localhost:$WYOMING_PORT/" \
    --xtts-voice "$PIPER_VOICE" \
    --temp 0.8 \
    -p Georgi

# Cleanup on exit
echo ""
echo "=========================================="
echo "Shutting down..."
echo "=========================================="

# Ask if user wants to stop Wyoming-Piper-Custom
read -p "Stop Wyoming-Piper-Custom TTS server? (y/N) [default: N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Stopping Wyoming-Piper-Custom..."
    pkill -f "wyoming-piper-custom" || true
    echo -e "${GREEN}✓ TTS server stopped${NC}"
else
    echo "Wyoming-Piper-Custom left running in background"
fi

echo "Goodbye!"
