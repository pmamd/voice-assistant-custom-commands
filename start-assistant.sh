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
WYOMING_PIPER_CMD="/home/paul/.local/bin/wyoming-piper"
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
    read -p "Stop it and restart? (y/n) " -n 1 -r
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
    echo -e "${GREEN}Starting Wyoming-Piper TTS server...${NC}"
    
    if [ ! -x "$WYOMING_PIPER_CMD" ]; then
        echo -e "${RED}✗ Error: Wyoming-Piper not found at $WYOMING_PIPER_CMD${NC}"
        echo "Please install it with: pip install wyoming-piper"
        exit 1
    fi
    
    # Create data directory if it doesn't exist
    mkdir -p "$PIPER_DATA_DIR"

    # Start Wyoming-Piper in background with custom handler
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
    -pe

# Cleanup on exit
echo ""
echo "=========================================="
echo "Shutting down..."
echo "=========================================="

# Ask if user wants to stop Wyoming-Piper
read -p "Stop Wyoming-Piper TTS server? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Stopping Wyoming-Piper..."
    pkill -f "wyoming-piper" || true
    echo -e "${GREEN}✓ TTS server stopped${NC}"
else
    echo "Wyoming-Piper left running in background"
fi

echo "Goodbye!"
