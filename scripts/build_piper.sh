#!/bin/bash
#
# Build Piper TTS from the git submodule
# Creates a self-contained installation in external/piper/.venv
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIPER_DIR="$REPO_ROOT/external/piper"

echo "Building Piper TTS from submodule..."
echo "Piper directory: $PIPER_DIR"

# Check if piper submodule exists
if [ ! -d "$PIPER_DIR" ]; then
    echo "Error: Piper submodule not found at $PIPER_DIR"
    echo "Run: git submodule update --init --recursive"
    exit 1
fi

# Check system dependencies
echo "Checking system dependencies..."
if ! command -v cmake &> /dev/null; then
    echo "Error: cmake not found. Install with: sudo apt-get install cmake"
    exit 1
fi

if ! command -v ninja &> /dev/null; then
    echo "Warning: ninja-build not found. Install with: sudo apt-get install ninja-build"
    echo "Continuing anyway..."
fi

# Create virtual environment for piper
cd "$PIPER_DIR"

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing build dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -e .[dev]

echo "Building Piper extension..."
python3 setup.py build_ext --inplace

echo ""
echo "✅ Piper built successfully!"
echo ""
echo "Piper binary location: $PIPER_DIR/.venv/bin/piper"
echo "Or run with: python3 -m piper"
echo ""
echo "To use in tests, update test_cases.yaml:"
echo "  piper_bin: \"$PIPER_DIR/.venv/bin/piper\""
echo ""
