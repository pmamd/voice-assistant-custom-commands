#!/bin/bash
# Test script for VAD fixes
# This script builds and tests the vad-fixes branch

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "=========================================="
echo "VAD Fixes Test Script"
echo "=========================================="
echo ""

# Step 1: Check we're on vad-fixes branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "vad-fixes" ]; then
    echo -e "${YELLOW}Current branch: $CURRENT_BRANCH${NC}"
    echo -e "${YELLOW}Switching to vad-fixes branch...${NC}"
    git checkout vad-fixes
fi

# Step 2: Pull latest changes
echo -e "${BLUE}Pulling latest changes from origin/vad-fixes...${NC}"
git pull origin vad-fixes

# Step 3: Show what changed
echo ""
echo "=========================================="
echo "Recent Changes:"
echo "=========================================="
git log --oneline -5
echo ""

# Step 4: Build
echo -e "${BLUE}Building talk-llama-custom...${NC}"
cmake --build build --target talk-llama-custom

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Build failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Build successful${NC}"
echo ""

# Step 5: Run automated test
echo "=========================================="
echo "Running Automated Test"
echo "=========================================="
echo ""
echo "This test will:"
echo "  1. Start the assistant"
echo "  2. Test Wyoming-Piper TTS connection"
echo "  3. Monitor VAD for 10 seconds"
echo "  4. Check for energy output"
echo "  5. Verify signal handling (Ctrl+C)"
echo ""
read -p "Press Enter to start test..."

# Create test log file
TEST_LOG="/tmp/vad-test-$(date +%s).log"
echo "Logging to: $TEST_LOG"

# Start the assistant in background
timeout 10s ./build/bin/talk-llama-custom \
    -ml "./models/llama-2-7b-chat.Q4_K_M.gguf" \
    -mw "./whisper.cpp/models/ggml-tiny.en.bin" \
    --xtts-url "http://localhost:10200/" \
    --xtts-voice "en_US-lessac-medium" \
    --temp 0.5 \
    -vth 1.2 \
    -pe \
    > "$TEST_LOG" 2>&1 &

TEST_PID=$!
echo "Started test (PID: $TEST_PID)"

# Wait for initialization
sleep 3

# Check if still running
if ! kill -0 $TEST_PID 2>/dev/null; then
    echo -e "${RED}✗ Process died during initialization${NC}"
    echo "Last 30 lines of log:"
    tail -30 "$TEST_LOG"
    exit 1
fi

echo -e "${GREEN}✓ Process initialized successfully${NC}"

# Monitor for 7 more seconds
echo ""
echo "Monitoring for VAD activity..."
echo "(Speak into microphone or make noise)"
sleep 7

# Graceful shutdown
echo ""
echo "Sending Ctrl+C (SIGINT) to test graceful shutdown..."
kill -INT $TEST_PID

# Wait for process to exit
sleep 2

if kill -0 $TEST_PID 2>/dev/null; then
    echo -e "${YELLOW}⚠ Process still running, forcing shutdown${NC}"
    kill -9 $TEST_PID
else
    echo -e "${GREEN}✓ Process exited gracefully${NC}"
fi

# Analyze results
echo ""
echo "=========================================="
echo "Test Results"
echo "=========================================="

# Check for Wyoming test
if grep -q "Testing Wyoming-Piper TTS Connection" "$TEST_LOG"; then
    echo -e "${GREEN}✓ Wyoming connection test found${NC}"
    grep -A 5 "Testing Wyoming-Piper" "$TEST_LOG"
else
    echo -e "${RED}✗ Wyoming connection test missing${NC}"
fi

echo ""

# Check for energy output
ENERGY_LINES=$(grep -c "energy_all:" "$TEST_LOG" || echo "0")
if [ "$ENERGY_LINES" -gt 5 ]; then
    echo -e "${GREEN}✓ Energy output present ($ENERGY_LINES lines)${NC}"
    echo "Sample energy values:"
    grep "energy_all:" "$TEST_LOG" | tail -5
else
    echo -e "${RED}✗ No energy output found (expected continuous updates)${NC}"
fi

echo ""

# Check for VAD triggers
if grep -q "found vad length" "$TEST_LOG"; then
    echo -e "${GREEN}✓ VAD triggered!${NC}"
    grep "found vad length" "$TEST_LOG"
else
    echo -e "${YELLOW}⚠ No VAD triggers (expected if no speech/audio)${NC}"
fi

echo ""

# Check for signal handling
if grep -q "Caught signal" "$TEST_LOG" || grep -q "Signal received" "$TEST_LOG"; then
    echo -e "${GREEN}✓ Signal handler working${NC}"
    grep -E "Caught signal|Signal received" "$TEST_LOG"
else
    echo -e "${YELLOW}⚠ No signal handler output (might be in stderr)${NC}"
fi

echo ""
echo "=========================================="
echo "Full test log saved to:"
echo "$TEST_LOG"
echo ""
echo "To view:"
echo "  cat $TEST_LOG"
echo "  grep energy_all $TEST_LOG | tail -20"
echo "=========================================="
echo ""

# Summary
echo "Test Summary:"
echo "- Wyoming test: $(grep -q 'Testing Wyoming-Piper' "$TEST_LOG" && echo '✓' || echo '✗')"
echo "- Energy output: $([ "$ENERGY_LINES" -gt 5 ] && echo '✓' || echo '✗')"
echo "- VAD triggers: $(grep -q 'found vad length' "$TEST_LOG" && echo '✓' || echo '⚠ none')"
echo "- Signal handling: $(grep -qE 'Caught signal|Signal received' "$TEST_LOG" && echo '✓' || echo '⚠')"
echo ""
echo "Next: Try speaking into microphone during the test to verify VAD detection"
