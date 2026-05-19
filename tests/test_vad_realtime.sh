#!/bin/bash
# Test VAD with real-time audio playback using aplay
# This simulates actual microphone input timing

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== VAD Real-Time Audio Test ==="
echo

# Check services
if ! curl -s -m 2 http://localhost:8080/health | grep -q "ok"; then
    fail "llama-server not running"
fi

if ! ss -tlnp 2>/dev/null | grep -q ":10200"; then
    fail "Wyoming-Piper not running"
fi

pass "Services running"

# Generate audio if needed
AUDIO_FILE="tests/audio/inputs/navigate_to_starbucks.wav"
if [[ ! -f "$AUDIO_FILE" ]]; then
    warn "Audio file not found, generating..."
    python3 -c "
import sys
sys.path.insert(0, 'tests')
from audio_generator import AudioGenerator
gen = AudioGenerator()
gen.generate('Navigate to Starbucks', output_name='navigate_to_starbucks')
"
fi

# Kill any stale processes
pkill -9 aplay 2>/dev/null || true
pkill -9 voice-assistant 2>/dev/null || true
sleep 1

echo "Starting voice-assistant in background..."

# Start voice-assistant with microphone capture
timeout 30 ./build/bin/voice-assistant \
    -mw ./external/whisper.cpp/models/ggml-base.bin \
    --llama-url http://localhost:8080 \
    --xtts-url http://localhost:10200/ \
    --xtts-voice en_US-lessac-medium \
    --temp 0.5 \
    -vth 1.2 \
    --vad-last-ms 700 \
    -n 300 \
    -p Driver \
    -c 0 \
    --language en \
    > /tmp/vad_realtime_test.log 2>&1 &

VA_PID=$!
echo "Voice assistant PID: $VA_PID"

# Wait for initialization
sleep 5

echo "Playing audio via aplay (real-time streaming to microphone)..."

# Play audio - this streams to the microphone in real-time
aplay -D default "$AUDIO_FILE" &
APLAY_PID=$!

echo "Audio playing (PID: $APLAY_PID)"

# Wait for processing
sleep 10

# Stop voice-assistant
kill $VA_PID 2>/dev/null || true
wait $VA_PID 2>/dev/null || true

# Kill aplay if still running
kill $APLAY_PID 2>/dev/null || true

echo
echo "Analyzing output..."
echo "---"
cat /tmp/vad_realtime_test.log
echo "---"
echo

# Analysis
DRIVER_COUNT=$(grep -c "^Driver:" /tmp/vad_realtime_test.log || echo "0")
OUTPUT=$(cat /tmp/vad_realtime_test.log)

# Check for the split-utterance bug
HAS_NAVIGATE_TO_START=$(echo "$OUTPUT" | grep -i "navigate to start" || echo "")
HAS_NAVIGATE_TO_STARBUCKS=$(echo "$OUTPUT" | grep -i "navigate to starbucks" || echo "")
HAS_TOOL_CALL=$(echo "$OUTPUT" | grep "\[Tool" || echo "")

echo "Results:"
echo "  Driver prompts: $DRIVER_COUNT"
echo "  Has 'navigate to start': $(if [[ -n "$HAS_NAVIGATE_TO_START" ]]; then echo "YES (BAD)"; else echo "no"; fi)"
echo "  Has 'navigate to starbucks': $(if [[ -n "$HAS_NAVIGATE_TO_STARBUCKS" ]]; then echo "YES"; else echo "no"; fi)"
echo "  Has tool call: $(if [[ -n "$HAS_TOOL_CALL" ]]; then echo "YES"; else echo "no"; fi)"
echo

if [[ $DRIVER_COUNT -gt 2 ]]; then
    fail "Multiple Driver prompts detected ($DRIVER_COUNT) - utterance was split"
fi

if [[ -n "$HAS_NAVIGATE_TO_START" ]]; then
    fail "Partial transcription detected: 'navigate to start' - VAD cut off mid-phrase"
fi

if [[ -z "$HAS_NAVIGATE_TO_STARBUCKS" ]] && [[ -z "$HAS_TOOL_CALL" ]]; then
    fail "No complete transcription found"
fi

pass "VAD test PASSED - no mid-phrase cutoff detected"
