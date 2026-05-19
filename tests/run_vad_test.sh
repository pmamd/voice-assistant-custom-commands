#!/bin/bash
# Run the VAD split-utterance test using the refactored test infrastructure
# This replaces the standalone test_vad_split.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

echo "=== VAD Split-Utterance Test (Refactored) ==="
echo

# Check services
if ! curl -s -m 2 http://localhost:8080/health | grep -q "ok"; then
    fail "llama-server not running"
fi

if ! ss -tlnp 2>/dev/null | grep -q ":10200"; then
    fail "Wyoming-Piper not running"
fi

pass "Services running"

# Run the VAD validation test
echo
echo "Running VAD validation test via test framework..."
echo

python3 tests/run_tests.py --group vad

# Check exit code
if [ $? -eq 0 ]; then
    pass "VAD test PASSED - no split detected"
    echo "  Test framework validated VAD behavior correctly"
else
    fail "VAD test FAILED - check output above for details"
fi
