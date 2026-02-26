#!/bin/bash
# Install Wyoming-Piper with custom modifications
# This makes the project self-contained by installing from the submodule

set -e

echo "========================================================================"
echo "Installing Wyoming-Piper with Custom Modifications"
echo "========================================================================"

cd "$(dirname "$0")"

# Step 1: Install Wyoming-Piper from submodule
echo ""
echo "1. Installing Wyoming-Piper from submodule..."
cd wyoming-piper
pip install -e .
cd ..

# Step 2: Overlay custom files
echo ""
echo "2. Overlaying custom modifications..."
cp custom/wyoming-piper/__main__.py wyoming-piper/wyoming_piper/
cp custom/wyoming-piper/handler.py wyoming-piper/wyoming_piper/
cp custom/wyoming-piper/process.py wyoming-piper/wyoming_piper/

# Step 3: Verify
echo ""
echo "3. Verifying installation..."
HAS_PIPER=$(grep -c '"--piper"' wyoming-piper/wyoming_piper/__main__.py || echo 0)
HAS_APLAY=$(grep -c 'aplay' wyoming-piper/wyoming_piper/handler.py || echo 0)

if [ "$HAS_PIPER" -gt 0 ] && [ "$HAS_APLAY" -gt 0 ]; then
    echo "   ✓ Custom modifications confirmed"
    echo "     --piper arg: $HAS_PIPER instances"
    echo "     aplay code: $HAS_APLAY instances"
else
    echo "   ✗ Custom modifications NOT found!"
    exit 1
fi

echo ""
echo "========================================================================"
echo "✓ Installation Complete"
echo "========================================================================"
echo ""
echo "Wyoming-Piper is now installed with custom modifications:"
echo "  - Uses aplay for local audio playback (no streaming)"
echo "  - Supports --piper flag to specify piper binary"
echo "  - Supports stop command detection"
echo ""
echo "You can now run: ./start-assistant.sh"
echo ""
