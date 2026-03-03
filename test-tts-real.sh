#!/bin/bash
# Real TTS test that actually triggers Wyoming-Piper
set -e

# Clean up
pkill -9 -f 'wyoming|talk-llama' 2>/dev/null || true
sleep 2
rm -f /tmp/wyoming-piper.log

echo "Starting Wyoming-Piper with debug logging..."
export PATH="$HOME/.local/bin:$PATH"
wyoming-piper-custom \
    --piper /opt/piper/piper \
    --voice en_US-lessac-medium \
    --data-dir ./piper-data \
    --uri "tcp://0.0.0.0:10200" \
    --debug \
    > /tmp/wyoming-piper.log 2>&1 &

WYOMING_PID=$!
echo "Wyoming-Piper PID: $WYOMING_PID"

# Wait for startup
sleep 15

# Check if running
if ! kill -0 $WYOMING_PID 2>/dev/null; then
    echo "ERROR: Wyoming-Piper died during startup"
    cat /tmp/wyoming-piper.log
    exit 1
fi

echo "Wyoming-Piper is running"
echo ""
echo "Now run the voice assistant in another terminal and trigger TTS"
echo "Watch the log with: tail -f /tmp/wyoming-piper.log"
echo ""
echo "When you're done testing, press Enter to stop Wyoming-Piper"
read

kill $WYOMING_PID 2>/dev/null || true

echo ""
echo "=== Wyoming-Piper Log ==="
cat /tmp/wyoming-piper.log
