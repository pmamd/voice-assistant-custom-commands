#!/bin/bash
# Install Wyoming-Piper with custom modifications
# This makes the project self-contained by installing from the submodule

set -e

echo "========================================================================"
echo "Installing Wyoming-Piper with Custom Modifications"
echo "========================================================================"

cd "$(dirname "$0")"

# Step 1: Install Wyoming-Piper-Custom from submodule (if not already installed)
echo ""
echo "1. Checking Wyoming-Piper-Custom installation..."

# Check if already installed
if pipx list 2>/dev/null | grep -q wyoming-piper-custom || pip show wyoming-piper-custom >/dev/null 2>&1; then
    echo "   Wyoming-Piper-Custom already installed"
else
    echo "   Installing Wyoming-Piper-Custom..."
    # Try pipx first (recommended for CLI tools)
    if command -v pipx &> /dev/null; then
        echo "   Using pipx for installation..."
        cd wyoming-piper
        pipx install -e . || {
            echo "   ⚠ pipx install failed, trying pip..."
            pip install -e . 2>/dev/null || {
                echo "   ⚠ pip install also failed (externally-managed-environment)"
                echo "   File overlay will still work if Wyoming-Piper is already installed"
            }
        }
        cd ..
    else
        echo "   pipx not found, trying pip..."
        cd wyoming-piper
        pip install -e . || {
            echo "   ⚠ pip install failed (externally-managed-environment?)"
            echo "   Consider installing pipx: sudo apt install pipx"
        }
        cd ..
    fi
fi

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
echo "Wyoming-Piper-Custom is now installed with custom modifications:"
echo "  - Uses aplay for local audio playback (no streaming)"
echo "  - Supports --piper flag to specify piper binary"
echo "  - Supports stop command detection"
echo "  - Installs as 'wyoming-piper-custom' (won't conflict with standard)"
echo ""
echo "You can now run: ./start-assistant.sh"
echo ""
