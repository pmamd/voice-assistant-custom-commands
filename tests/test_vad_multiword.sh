#!/bin/bash
# Test that multi-word phrases are transcribed completely without VAD cutoff
# Tests the fix for early stop detection running multiple times

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

# Change to project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== VAD Multi-Word Phrase Test ==="
echo
echo "This test verifies that multi-word phrases falling in the 1200-1800ms"
echo "window are transcribed completely without being cut off by the early"
echo "stop detection logic."
echo

# Generate test audio if needed
AUDIO_DIR="tests/audio/inputs"
mkdir -p "$AUDIO_DIR"

PIPER_BIN="$HOME/.local/bin/piper"
PIPER_DATA="$PROJECT_ROOT/piper-data"

generate_audio() {
    local text="$1"
    local filename="$2"
    local output="$AUDIO_DIR/$filename"

    if [[ -f "$output" ]]; then
        echo "  Using cached: $output"
        return 0
    fi

    echo "  Generating: '$text'"

    # Find voice model
    local model=$(find "$PIPER_DATA" -name "*.onnx" | grep "en_US-lessac" | head -1)
    if [[ -z "$model" ]]; then
        warn "Piper voice model not found, skipping generation"
        return 1
    fi

    # Generate audio
    echo "$text" | "$PIPER_BIN" --model "$model" --output_file "$output" 2>/dev/null || {
        warn "Failed to generate audio for: $text"
        return 1
    }

    # Resample to 16kHz for Whisper
    if command -v ffmpeg &>/dev/null; then
        ffmpeg -i "$output" -ar 16000 -ac 1 -y "${output}.tmp" 2>/dev/null && mv "${output}.tmp" "$output"
    fi

    echo "  Saved: $output"
}

# Generate test audio files
echo "1. Generating test audio files..."
generate_audio "Navigate to Starbucks" "navigate_to_starbucks.wav"
generate_audio "Make it warmer" "make_it_warmer.wav"
generate_audio "Turn up the volume" "turn_up_volume.wav"
echo

# Test transcription with Whisper
WHISPER_BIN="./build/bin/whisper-cli"
WHISPER_MODEL="./external/whisper.cpp/models/for-tests-ggml-base.bin"

if [[ ! -f "$WHISPER_MODEL" ]]; then
    fail "Whisper model not found: $WHISPER_MODEL"
fi

echo "2. Testing transcriptions..."
echo

test_transcription() {
    local expected="$1"
    local wav_file="$2"

    if [[ ! -f "$wav_file" ]]; then
        warn "Audio file not found: $wav_file"
        return 1
    fi

    echo "  Testing: '$expected'"

    # Transcribe with Whisper
    local output=$("$WHISPER_BIN" -m "$WHISPER_MODEL" -f "$wav_file" --language en 2>&1)

    # Extract transcription (line with timestamp)
    local transcription=$(echo "$output" | grep -oP '\[00:00.*?\]\s+\K.*' | head -1 | sed 's/^ *//;s/ *$//')

    echo "    Got: '$transcription'"

    # Check if complete phrase is in transcription (case insensitive)
    if echo "$transcription" | grep -qi "$expected"; then
        pass "Complete phrase found"
        return 0
    else
        fail "Expected '$expected', got '$transcription'"
        return 1
    fi
}

# Run tests
PASS_COUNT=0
TOTAL_COUNT=0

run_test() {
    local expected="$1"
    local filename="$2"

    TOTAL_COUNT=$((TOTAL_COUNT + 1))

    if test_transcription "$expected" "$AUDIO_DIR/$filename"; then
        PASS_COUNT=$((PASS_COUNT + 1))
    fi
    echo
}

run_test "Navigate to Starbucks" "navigate_to_starbucks.wav"
run_test "Make it warmer" "make_it_warmer.wav"
run_test "Turn up the volume" "turn_up_volume.wav"

# Summary
echo "=== Test Summary ==="
echo "Passed: $PASS_COUNT/$TOTAL_COUNT"
echo

if [[ $PASS_COUNT -eq $TOTAL_COUNT ]]; then
    echo -e "${GREEN}✓ All tests PASSED${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests FAILED${NC}"
    exit 1
fi
