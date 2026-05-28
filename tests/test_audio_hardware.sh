#!/bin/bash
# Simple hardware test for microphone and speaker setup
# Uses aplay to play audio and arecord to capture from mic

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== Audio Hardware Test ==="
echo ""
echo "This test will:"
echo "  1. Play a test phrase through speakers using aplay"
echo "  2. Record from microphone using arecord"
echo "  3. Save the recording for analysis"
echo ""

# Generate test audio if needed
TEST_INPUT="tests/audio/inputs/hardware_test_input.wav"
TEST_OUTPUT="tests/audio/outputs/hardware_test_output.wav"

mkdir -p tests/audio/inputs tests/audio/outputs

if [[ ! -f "$TEST_INPUT" ]]; then
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
gen.generate('Navigate to the closest Starbucks near me', output_name='hardware_test_input')
"
fi

# Get audio file duration
DURATION=$(ffprobe -i "$TEST_INPUT" -show_entries format=duration -v quiet -of csv="p=0" 2>/dev/null)
echo -e "${GREEN}✓${NC} Test audio ready: ${DURATION}s"
echo ""

# Determine recording device (Blue Snowball is usually hw:3,0)
MIC_DEVICE="hw:3,0"
SPEAKER_DEVICE="plughw:1,0"

echo "Microphone device: $MIC_DEVICE (Blue Snowball)"
echo "Speaker device: $SPEAKER_DEVICE (default output)"
echo ""

# Calculate recording duration (add 1 second buffer)
REC_DURATION=$(printf "%.0f" "$(echo "$DURATION + 1" | bc)")

echo "Starting recording in 2 seconds..."
sleep 2

# Start recording in background
echo "Starting arecord..."
arecord -D "$MIC_DEVICE" -f S16_LE -r 16000 -c 1 -d "$REC_DURATION" "$TEST_OUTPUT" 2>&1 &
RECORD_PID=$!

# Wait a moment for recording to start
sleep 0.5

# Play the test audio
echo "Playing test audio..."
aplay -D "$SPEAKER_DEVICE" "$TEST_INPUT" 2>&1

# Wait for recording to finish
wait $RECORD_PID

echo ""
echo -e "${GREEN}✓${NC} Recording complete"
echo ""
echo "=== Results ==="
echo "Input file:  $TEST_INPUT"
echo "Output file: $TEST_OUTPUT"
echo ""
echo "To analyze the recording, you can:"
echo "  1. Play it back: aplay $TEST_OUTPUT"
echo "  2. Transcribe it with Whisper:"
echo "     ./build/bin/main -m external/whisper.cpp/models/ggml-base.en.bin -f $TEST_OUTPUT"
echo ""

# Optional: transcribe with Whisper if available
if [[ -f "./build/bin/main" ]]; then
    echo "Transcribing with Whisper..."
    TRANSCRIPTION=$(./build/bin/main -m external/whisper.cpp/models/ggml-base.en.bin -f "$TEST_OUTPUT" 2>/dev/null | grep -A1 "\\[00:00:00.000" | tail -1 | sed 's/^\s*//')
    echo ""
    echo "=== Transcription ==="
    echo "$TRANSCRIPTION"
    echo ""
    
    # Check if it heard the expected phrase
    if echo "$TRANSCRIPTION" | grep -qi "starbucks"; then
        echo -e "${GREEN}✓${NC} Microphone successfully captured 'Starbucks'"
    elif echo "$TRANSCRIPTION" | grep -qi "navigate"; then
        echo -e "${YELLOW}!${NC} Heard 'navigate' but not 'Starbucks' - partial capture"
    else
        echo -e "${RED}✗${NC} Did not hear expected phrase"
        echo "  Expected: 'Navigate to the closest Starbucks near me'"
        echo "  Got: $TRANSCRIPTION"
    fi
fi
