#!/bin/bash
# Test VAD with REAL acoustic feedback - microphone WILL hear TTS from speakers
# This reproduces the original bug where acoustic feedback causes multiple prompts

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== VAD Acoustic Feedback Test ==="
echo ""
echo "This test INTENTIONALLY allows acoustic feedback:"
echo "  1. User prompt played through speakers via aplay"
echo "  2. Microphone captures the audio"
echo "  3. LLM generates response"
echo "  4. Response plays through speakers"
echo "  5. Check if microphone hearing TTS causes additional false prompts"
echo ""

# Kill any existing voice-assistant
pkill -9 -f "voice-assistant" 2>/dev/null || true
sleep 1

# Configuration
WHISPER_MODEL="./external/whisper.cpp/models/ggml-base.en.bin"
LLAMA_URL="http://localhost:8080"
WYOMING_PORT=10200
PIPER_VOICE="en_US-lessac-medium"
CAPTURE_DEVICE="0"  # Realtek USB Audio
TEST_AUDIO="tests/audio/inputs/vad_split_utterance_input.wav"
OUTPUT_LOG="tests/audio/debug/acoustic_feedback_test.txt"

# Check services
if ! curl -s -m 2 http://localhost:8080/health > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} llama-server not running at port 8080"
    exit 1
fi

if ! ss -tlnp 2>/dev/null | grep -q ":10200"; then
    echo -e "${RED}✗${NC} Wyoming-Piper not running at port 10200"
    exit 1
fi

echo -e "${GREEN}✓${NC} Services running"
echo ""

# Start voice assistant in background
echo "Starting voice assistant..."
./build/bin/voice-assistant \
    -mw "$WHISPER_MODEL" \
    --llama-url "$LLAMA_URL" \
    --xtts-url "http://localhost:$WYOMING_PORT/" \
    --xtts-voice "$PIPER_VOICE" \
    --temp 0.5 \
    -vth 1.2 \
    --vad-last-ms 700 \
    -n 300 \
    --allow-newline \
    -p Driver \
    -c "$CAPTURE_DEVICE" \
    --language en \
    > "$OUTPUT_LOG" 2>&1 &

ASSISTANT_PID=$!
echo "Voice assistant PID: $ASSISTANT_PID"

# Wait for initialization
echo "Waiting for voice assistant to initialize..."
sleep 3

# Play the test audio through speakers to trigger the test
echo ""
echo "Playing user prompt through speakers: 'Navigate to the closest Starbucks near me'"
aplay -D plughw:1,0 "$TEST_AUDIO" 2>/dev/null

echo "Waiting for processing (LLM + TTS + potential feedback loops)..."
sleep 10

# Kill voice assistant
echo ""
echo "Stopping voice assistant..."
kill $ASSISTANT_PID 2>/dev/null || true
sleep 2
kill -9 $ASSISTANT_PID 2>/dev/null || true

echo ""
echo "=== Analysis ==="
echo ""

# Count Georgi: prompts
PROMPT_COUNT=$(grep -c "^Georgi:" "$OUTPUT_LOG" 2>/dev/null || echo "0")
echo "User prompts detected: $PROMPT_COUNT"

if [ "$PROMPT_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}!${NC} No prompts detected - microphone may not have captured audio"
    echo "   Check: $OUTPUT_LOG"
elif [ "$PROMPT_COUNT" -eq 1 ]; then
    echo -e "${GREEN}✓ PASS${NC} - Single prompt, no acoustic feedback loop"
else
    echo -e "${RED}✗ FAIL${NC} - Multiple prompts detected (acoustic feedback)"
    echo ""
    echo "Detected prompts:"
    grep "^Georgi:" "$OUTPUT_LOG" | nl
fi

echo ""
echo "VAD debug log: $OUTPUT_LOG"
echo ""
echo "To see VAD state transitions:"
echo "  grep -E 'SPLIT-DEBUG|EARLY-STOP' $OUTPUT_LOG"
echo ""

# Show any splits
if grep -q "=== VAD TRIGGERED END-OF-SPEECH ===" "$OUTPUT_LOG"; then
    echo "VAD triggers found:"
    grep -A3 "=== VAD TRIGGERED END-OF-SPEECH ===" "$OUTPUT_LOG"
fi
