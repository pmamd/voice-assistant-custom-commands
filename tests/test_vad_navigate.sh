#!/bin/bash
# Test VAD with "Navigate to Starbucks" audio injection
# Verifies no multiple partial transcriptions occur

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== VAD Navigate to Starbucks Test ==="
echo

# Generate audio if needed
AUDIO_FILE="tests/audio/inputs/navigate_to_starbucks.wav"

if [[ ! -f "$AUDIO_FILE" ]]; then
    echo "Generating test audio..."
    PIPER_BIN="$HOME/.local/bin/piper"
    PIPER_DATA="$PROJECT_ROOT/piper-data"
    MODEL=$(find "$PIPER_DATA" -name "*.onnx" | grep "en_US-lessac" | head -1)

    if [[ -z "$MODEL" ]]; then
        fail "Piper voice model not found"
    fi

    echo "Navigate to Starbucks" | "$PIPER_BIN" --model "$MODEL" --output_file "$AUDIO_FILE" 2>/dev/null

    # Resample to 16kHz
    if command -v ffmpeg &>/dev/null; then
        ffmpeg -i "$AUDIO_FILE" -ar 16000 -ac 1 -y "${AUDIO_FILE}.tmp" 2>/dev/null && mv "${AUDIO_FILE}.tmp" "$AUDIO_FILE"
    fi

    pass "Generated audio: $AUDIO_FILE"
fi

echo "Testing voice-assistant with audio injection..."
echo

# Check services are running
if ! curl -s -m 2 http://localhost:8080/health | grep -q "ok"; then
    fail "llama-server not running on port 8080"
fi

if ! ss -tlnp 2>/dev/null | grep -q ":10200"; then
    fail "Wyoming-Piper not running on port 10200"
fi

pass "Services running (llama-server, Wyoming-Piper)"

# Run voice-assistant with test audio
OUTPUT_FILE="/tmp/vad_test_output_$$.txt"

timeout 45 ./build/bin/voice-assistant \
    -mw ./external/whisper.cpp/models/ggml-base.bin \
    --llama-url http://localhost:8080 \
    --xtts-url http://localhost:10200/ \
    --xtts-voice en_US-lessac-medium \
    --temp 0.5 \
    -vth 1.2 \
    --vad-last-ms 700 \
    -n 300 \
    -p Driver \
    -c -1 \
    --test-input "$AUDIO_FILE" \
    --language en \
    > "$OUTPUT_FILE" 2>&1 || true

echo "Analyzing output..."
echo "---"
cat "$OUTPUT_FILE"
echo "---"
echo

# Check for issues
DRIVER_COUNT=$(grep -c "^Driver:" "$OUTPUT_FILE" || echo "0")
HAS_NAVIGATE=$(grep -i "navigate" "$OUTPUT_FILE" || echo "")
HAS_STARBUCKS=$(grep -i "starbucks" "$OUTPUT_FILE" || echo "")

# Check for partial transcriptions (bad)
HAS_PARTIAL_TO=$(grep "^Driver: to Starbucks" "$OUTPUT_FILE" || echo "")
HAS_PARTIAL_NAV=$(grep "^Driver: Navigate to$" "$OUTPUT_FILE" || echo "")

echo "Analysis:"
echo "  Driver prompts: $DRIVER_COUNT"
echo "  Contains 'navigate': $(if [[ -n "$HAS_NAVIGATE" ]]; then echo "yes"; else echo "no"; fi)"
echo "  Contains 'starbucks': $(if [[ -n "$HAS_STARBUCKS" ]]; then echo "yes"; else echo "no"; fi)"
echo

# Evaluation
PASS=true

if [[ $DRIVER_COUNT -gt 2 ]]; then
    fail "Too many Driver prompts ($DRIVER_COUNT) - indicates multiple VAD triggers"
    PASS=false
fi

if [[ -n "$HAS_PARTIAL_TO" ]] || [[ -n "$HAS_PARTIAL_NAV" ]]; then
    fail "Found partial transcriptions - VAD cutoff occurred"
    PASS=false
fi

if [[ -z "$HAS_NAVIGATE" ]] || [[ -z "$HAS_STARBUCKS" ]]; then
    fail "Complete phrase not found in output"
    PASS=false
fi

# Clean up
rm -f "$OUTPUT_FILE"

if $PASS; then
    pass "VAD test PASSED - no cutoff detected"
    echo
    echo "✓ Single VAD trigger"
    echo "✓ No partial transcriptions"
    echo "✓ Complete phrase transcribed"
    exit 0
else
    exit 1
fi
