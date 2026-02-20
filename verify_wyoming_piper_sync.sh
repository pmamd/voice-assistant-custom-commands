#!/bin/bash
# Verification script: Check Wyoming-Piper synchronization between local and build server
# Run this when the build server is accessible

set -e

BUILD_SERVER="paul@192.168.86.74"
SERVER_PATH="~/git/wyoming-piper/wyoming_piper"
LOCAL_CUSTOM="custom/wyoming-piper"

echo "=================================================="
echo "Wyoming-Piper Synchronization Verification"
echo "=================================================="
echo ""

# Check if build server is accessible
echo "1. Checking build server connectivity..."
if ! ssh -o ConnectTimeout=5 "$BUILD_SERVER" "echo 'Connected'" > /dev/null 2>&1; then
    echo "   ❌ Build server not accessible at $BUILD_SERVER"
    echo "   Please ensure server is running and SSH keys are set up"
    exit 1
fi
echo "   ✓ Build server accessible"
echo ""

# Check git status on build server
echo "2. Checking git status on build server..."
SERVER_STATUS=$(ssh "$BUILD_SERVER" "cd ~/git/wyoming-piper && git status --short")
if [ -n "$SERVER_STATUS" ]; then
    echo "   ⚠️  Uncommitted changes found on build server:"
    echo "$SERVER_STATUS" | sed 's/^/      /'
    echo ""
else
    echo "   ✓ No uncommitted changes on build server"
    echo ""
fi

# Compare __main__.py
echo "3. Comparing __main__.py..."
TEMP_DIR=$(mktemp -d)
scp -q "$BUILD_SERVER:$SERVER_PATH/__main__.py" "$TEMP_DIR/server_main.py"

if diff -q "$LOCAL_CUSTOM/__main__.py" "$TEMP_DIR/server_main.py" > /dev/null 2>&1; then
    echo "   ✓ __main__.py is synchronized"
else
    echo "   ⚠️  __main__.py differs between local and server"
    echo "   Showing differences:"
    diff -u "$TEMP_DIR/server_main.py" "$LOCAL_CUSTOM/__main__.py" | head -50 | sed 's/^/      /'
    echo ""
    echo "   To update local from server:"
    echo "   scp $BUILD_SERVER:$SERVER_PATH/__main__.py $LOCAL_CUSTOM/"
fi
echo ""

# Compare handler.py
echo "4. Comparing handler.py..."
scp -q "$BUILD_SERVER:$SERVER_PATH/handler.py" "$TEMP_DIR/server_handler.py"

if diff -q "$LOCAL_CUSTOM/handler.py" "$TEMP_DIR/server_handler.py" > /dev/null 2>&1; then
    echo "   ✓ handler.py is synchronized"
else
    echo "   ⚠️  handler.py differs between local and server"
    echo "   Showing differences:"
    diff -u "$TEMP_DIR/server_handler.py" "$LOCAL_CUSTOM/handler.py" | head -50 | sed 's/^/      /'
    echo ""
    echo "   To update local from server:"
    echo "   scp $BUILD_SERVER:$SERVER_PATH/handler.py $LOCAL_CUSTOM/"
fi
echo ""

# Cleanup
rm -rf "$TEMP_DIR"

echo "=================================================="
echo "Summary"
echo "=================================================="
if [ -n "$SERVER_STATUS" ]; then
    echo "⚠️  Build server has uncommitted changes - consider committing them"
else
    echo "✓ Build server repository is clean"
fi
echo ""
echo "Next steps if files differ:"
echo "1. Copy newer version from server: scp $BUILD_SERVER:$SERVER_PATH/FILE $LOCAL_CUSTOM/"
echo "2. Review changes: git diff $LOCAL_CUSTOM/FILE"
echo "3. Commit and push: git add $LOCAL_CUSTOM/ && git commit -m 'Update from build server'"
echo ""
