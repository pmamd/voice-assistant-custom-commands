#!/bin/bash
# Run VAD test with LIVE AUDIO (speakers + microphone) and capture all debug output
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "=== VAD Live Audio Debug Test ==="
echo ""
echo "This test will:"
echo "  1. Play test audio through speakers"
echo "  2. Capture via Blue Snowball microphone"
echo "  3. Log all VAD debug output"
echo ""

# Configuration
WHISPER_MODEL="./external/whisper.cpp/models/ggml-base.en.bin"
LLAMA_URL="http://localhost:8080"
WYOMING_PORT=10200
PIPER_VOICE="en_US-lessac-medium"
CAPTURE_DEVICE="0"  # Realtek USB Audio Front Mic
TEST_AUDIO="tests/audio/inputs/vad_split_utterance_input.wav"
OUTPUT_LOG="tests/audio/debug/vad_live_debug.txt"

# Generate test audio if needed
if [ ! -f "$TEST_AUDIO" ]; then
    echo "Generating test audio..."
    python3 -c "
import sys
sys.path.insert(0, 'tests')
from audio_generator import AudioGenerator
gen = AudioGenerator(
    piper_bin='$HOME/.local/bin/piper',
    model_dir='./piper-data',
    output_dir='tests/audio/inputs'
)
gen.generate('Navigate to the closest Starbucks near me', output_name='vad_split_utterance_input')
"
fi

# Start voice assistant with live microphone
echo "Starting voice assistant (will auto-exit after processing)..."
echo "Playing audio through speakers, capturing with microphone..."
echo ""

# Play audio in background while voice assistant is running
(
    sleep 2  # Wait for voice assistant to start
    echo "[AUDIO] Playing test phrase through speakers..."
    aplay -D plughw:1,0 "$TEST_AUDIO" 2>/dev/null
    echo "[AUDIO] Playback complete"
) &

# Run voice assistant with all debug output
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

# Wait for test to complete (max 15 seconds)
echo "Waiting for voice assistant to process audio..."
for i in {1..30}; do
    if ! ps -p $ASSISTANT_PID > /dev/null 2>&1; then
        echo "Voice assistant exited"
        break
    fi
    sleep 0.5
done

# Kill if still running
if ps -p $ASSISTANT_PID > /dev/null 2>&1; then
    echo "Timeout - killing voice assistant..."
    kill $ASSISTANT_PID 2>/dev/null || true
    sleep 1
    kill -9 $ASSISTANT_PID 2>/dev/null || true
fi

echo ""
echo "=== Results ==="
echo ""
echo "Debug log saved to: $OUTPUT_LOG"
echo ""

# Count number of "Georgi:" prompts
PROMPT_COUNT=$(grep -c "Georgi:" "$OUTPUT_LOG" 2>/dev/null || echo "0")
echo "Number of user prompts detected: $PROMPT_COUNT"

if [ "$PROMPT_COUNT" -eq 1 ]; then
    echo -e "${GREEN}✓ PASS${NC} - Single utterance processed correctly"
else
    echo -e "${RED}✗ FAIL${NC} - Split detected ($PROMPT_COUNT prompts instead of 1)"
fi

echo ""
echo "To analyze VAD behavior:"
echo "  grep -E 'VAD-DEBUG|vad_simple|SPLIT-DEBUG|EARLY-STOP' $OUTPUT_LOG"
echo ""
echo "To view saved audio chunks:"
echo "  ls -lh tests/audio/debug/split_*.wav"
echo ""
