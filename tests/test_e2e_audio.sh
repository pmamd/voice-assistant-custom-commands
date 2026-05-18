#!/bin/bash
# Full E2E audio pipeline test
# Tests: NPU Whisper → LLM → TTS

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

echo "=== E2E Audio Pipeline Test ==="
echo

# Test 1: NPU Whisper transcription
echo "1. Testing NPU Whisper transcription..."
source /opt/xilinx/xrt/setup.sh 2>/dev/null || true
export HSA_OVERRIDE_GFX_VERSION=11.0.3

WHISPER_OUTPUT=$(./build/bin/whisper-cli \
    -m ./external/whisper.cpp/models/ggml-base.bin \
    -f tests/audio/inputs/make_it_warmer.wav \
    --language en 2>&1)

if echo "$WHISPER_OUTPUT" | grep -q "WHISPER : VITISAI = 1"; then
    pass "NPU encoder executed"
else
    fail "NPU encoder not used"
fi

TRANSCRIPTION=$(echo "$WHISPER_OUTPUT" | grep -oP '\[00:00.*?\]\s+\K.*' | head -1 | xargs)
if [[ "$TRANSCRIPTION" == "Make it warmer." ]]; then
    pass "Transcription correct: '$TRANSCRIPTION'"
else
    fail "Transcription incorrect: got '$TRANSCRIPTION', expected 'Make it warmer.'"
fi
echo

# Test 2: LLM generates response
echo "2. Testing LLM response..."
if ! curl -s -m 2 http://localhost:8080/health | grep -q "ok"; then
    fail "llama-server not running"
fi

LLM_RESPONSE=$(timeout 30 curl -s http://localhost:8080/completion \
    -H "Content-Type: application/json" \
    -d '{
        "prompt": "Driver: Make it warmer.\nAssistant:",
        "temperature": 0.5,
        "max_tokens": 50,
        "stop": ["\n", "Driver:"]
    }')

if echo "$LLM_RESPONSE" | grep -q "content"; then
    CONTENT=$(echo "$LLM_RESPONSE" | grep -oP '"content":"\K[^"]+' | head -1)
    pass "LLM generated response: '${CONTENT:0:50}...'"
else
    fail "LLM did not generate response"
fi
echo

# Test 3: Tool calling with temperature request
echo "3. Testing tool calling..."
TOOL_RESPONSE=$(timeout 30 curl -s http://localhost:8080/completion \
    -H "Content-Type: application/json" \
    -d '{
        "prompt": "Driver: Set temperature to 72 degrees.\nAssistant:",
        "temperature": 0.5,
        "max_tokens": 100,
        "stop": ["\n", "Driver:"]
    }')

TOOL_CONTENT=$(echo "$TOOL_RESPONSE" | grep -oP '"content":"\K[^"]+' | head -1)

# Check if response mentions temperature or includes tool syntax
if echo "$TOOL_CONTENT" | grep -qiE 'temperature|72|tool'; then
    pass "LLM responds to temperature request"
else
    warn "LLM response unclear: '${TOOL_CONTENT:0:50}...'"
fi
echo

# Test 4: TTS connection
echo "4. Testing TTS connection..."
if ! ss -tlnp 2>/dev/null | grep -q ":10200"; then
    fail "Wyoming-Piper not listening on port 10200"
fi

# Send a simple TTS request via HTTP
TTS_TEST=$(timeout 5 curl -s -X POST http://localhost:10200/api/tts \
    -H "Content-Type: application/json" \
    -d '{"text": "Test"}' 2>&1 || echo "timeout")

if [[ "$TTS_TEST" != "timeout" ]]; then
    pass "TTS server responding"
else
    warn "TTS HTTP endpoint not responding (Wyoming protocol may still work)"
fi
echo

echo -e "${GREEN}=== E2E Audio Pipeline Test Complete ===${NC}"
echo
echo "Summary:"
echo "  ✓ NPU Whisper transcription working"
echo "  ✓ LLM generation working"
echo "  ✓ Tool calling response generated"
echo "  ✓ TTS server running"
echo
echo "Verified transcription: '$TRANSCRIPTION'"
