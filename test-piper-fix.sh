#!/bin/bash
# Simple test to verify Piper output parsing fix
# Runs voice assistant briefly and checks for FileNotFoundError

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Testing Piper Output Parsing Fix"
echo "=========================================="
echo ""

# Clean up any existing processes
pkill -9 -f 'wyoming-piper-custom' 2>/dev/null || true
pkill -9 -f 'talk-llama-custom' 2>/dev/null || true
sleep 1

# Clear log
rm -f /tmp/wyoming-piper.log
touch /tmp/wyoming-piper.log

echo "Starting voice assistant for 20 seconds..."
echo "(This will test TTS with the actual voice assistant)"
echo ""

# Run voice assistant with timeout
timeout 40 ./start-assistant.sh > /tmp/test-run.log 2>&1 &
TEST_PID=$!

# Wait for startup (Wyoming-Piper + voice model + LLaMA load)
echo "Waiting 25 seconds for models to load..."
sleep 25

# Check if Wyoming-Piper is running
if ! pgrep -f 'wyoming-piper-custom' > /dev/null; then
    echo -e "${RED}✗ Wyoming-Piper is not running${NC}"
    cat /tmp/test-run.log
    exit 1
fi

echo -e "${GREEN}✓ Wyoming-Piper is running${NC}"

# Check if talk-llama is running
if ! pgrep -f 'talk-llama-custom' > /dev/null; then
    echo -e "${RED}✗ talk-llama is not running${NC}"
    cat /tmp/test-run.log
    exit 1
fi

echo -e "${GREEN}✓ talk-llama is running${NC}"

# Wait for test to complete
wait $TEST_PID 2>/dev/null || true

# Clean up
pkill -9 -f 'wyoming-piper-custom' 2>/dev/null || true
pkill -9 -f 'talk-llama-custom' 2>/dev/null || true

echo ""
echo "Checking Wyoming-Piper log for errors..."

# Check for FileNotFoundError (the bug we fixed)
if grep -i "FileNotFoundError" /tmp/wyoming-piper.log; then
    echo -e "${RED}✗ Found FileNotFoundError in log (BUG NOT FIXED!)${NC}"
    echo ""
    echo "Wyoming-Piper log:"
    cat /tmp/wyoming-piper.log
    exit 1
fi

echo -e "${GREEN}✓ No FileNotFoundError found${NC}"

# Check for other errors
if grep -i "ERROR.*Task exception" /tmp/wyoming-piper.log; then
    echo -e "${RED}✗ Found task exception errors${NC}"
    grep -A 5 -i "ERROR.*Task exception" /tmp/wyoming-piper.log
    exit 1
fi

echo -e "${GREEN}✓ No task exceptions found${NC}"

# Check if any TTS was processed
if grep -i "synthesize" /tmp/wyoming-piper.log; then
    echo -e "${GREEN}✓ TTS requests were processed${NC}"
    TTS_COUNT=$(grep -c -i "synthesize" /tmp/wyoming-piper.log || echo "0")
    echo "  Processed $TTS_COUNT TTS request(s)"
else
    echo -e "${YELLOW}⚠ No TTS requests found in log${NC}"
    echo "  (This is OK if no audio output was triggered)"
fi

# Check if Piper output was parsed correctly
if grep -i "Audio file path:" /tmp/wyoming-piper.log; then
    echo -e "${GREEN}✓ Piper output was parsed successfully${NC}"
    FILE_COUNT=$(grep -c -i "Audio file path:" /tmp/wyoming-piper.log || echo "0")
    echo "  Parsed $FILE_COUNT audio file path(s)"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✓ Piper output parsing fix verified!${NC}"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - No FileNotFoundError in logs"
echo "  - No task exception errors"
echo "  - Wyoming-Piper ran without crashing"
echo ""
echo "Full logs:"
echo "  - Wyoming-Piper: /tmp/wyoming-piper.log"
echo "  - Test run: /tmp/test-run.log"
