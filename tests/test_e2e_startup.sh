#!/bin/bash
# End-to-end startup test for voice assistant
# Based on kitt2k manual_smoke_test.sh pattern

set -e

# Change to project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

echo "=== Voice Assistant E2E Startup Test ==="
echo

# Test 1: Check llama-server
echo "1. Checking llama-server..."
pgrep -f llama-server > /dev/null && pass "llama-server process running" || fail "llama-server not running"
curl -s -m 2 http://localhost:8080/health 2>&1 | grep -q "ok" && pass "llama-server responding" || fail "llama-server not responding"
echo

# Test 2: Check Wyoming-Piper
echo "2. Checking Wyoming-Piper..."
pgrep -f "wyoming.*piper" > /dev/null && pass "Wyoming-Piper process running" || fail "Wyoming-Piper not running"
ss -tlnp 2>/dev/null | grep -q ":10200" && pass "Wyoming-Piper listening on port 10200" || fail "Wyoming-Piper not listening"
echo

# Test 3: Check build artifacts
echo "3. Checking build artifacts..."
if test -f ./build/bin/talk-llama-custom; then
    pass "talk-llama-custom binary exists"
elif test -f ./build/bin/talk-llama; then
    pass "talk-llama binary exists"
else
    fail "binary not found"
fi
test -f ./whisper.cpp/models/ggml-base.en.bin && pass "Whisper model exists" || fail "Whisper model not found"
test -f ./models/mistral-7b-instruct-v0.2.Q5_0.gguf && pass "LLM model exists" || fail "LLM model not found"
test -f ./custom/talk-llama/tools/tools.json && pass "tools.json exists" || fail "tools.json not found"
echo

# Test 4: Test llama-server completion
echo "4. Testing llama-server completion..."
RESPONSE=$(timeout 10 curl -s http://localhost:8080/completion \
  -H "Content-Type: application/json" \
  -d '{"prompt":"User: Hello\nAssistant:","temperature":0.7,"max_tokens":20,"stop":["\n"]}' 2>&1)

if echo "$RESPONSE" | grep -q "content"; then
    pass "LLM completion successful"
else
    fail "LLM completion failed: $RESPONSE"
fi
echo

# Test 5: Verify llama-server still alive after completion
echo "5. Verifying llama-server stability..."
sleep 1
pgrep -f llama-server > /dev/null && pass "llama-server survived completion request" || fail "llama-server crashed during completion"
echo

echo -e "${GREEN}=== All Tests Passed ===${NC}"
echo
echo "Services verified:"
echo "  ✓ llama-server running and stable"
echo "  ✓ Wyoming-Piper running"
echo "  ✓ All build artifacts present"
echo "  ✓ LLM completion working"
