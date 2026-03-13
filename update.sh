#!/bin/bash
# Pull latest changes and update the installed binary.
# For first-time setup use install.sh instead.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${CYAN}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }

echo ""
echo "=========================================="
echo " Voice Assistant — Update"
echo "=========================================="
echo ""

info "Pulling latest changes..."
git -C "$SCRIPT_DIR" pull
echo ""

# Binary
info "Updating binary..."
mkdir -p "$SCRIPT_DIR/build/bin"
cp "$SCRIPT_DIR/dist/bin/talk-llama-custom" "$SCRIPT_DIR/build/bin/talk-llama-custom"
chmod +x "$SCRIPT_DIR/build/bin/talk-llama-custom"
ok "Binary updated"

# Shared libs — only reinstall if they differ from what's in /usr/local/lib
NEEDS_LDCONFIG=0

for LIB in libwhisper.so.1.6.2 libggml.so; do
    SRC="$SCRIPT_DIR/dist/lib/$LIB"
    DST="/usr/local/lib/$LIB"
    if [[ ! -f "$DST" ]] || ! cmp -s "$SRC" "$DST"; then
        info "Updating $LIB..."
        sudo cp "$SRC" "$DST"
        NEEDS_LDCONFIG=1
    fi
done

if [[ $NEEDS_LDCONFIG -eq 1 ]]; then
    sudo ln -sf /usr/local/lib/libwhisper.so.1.6.2 /usr/local/lib/libwhisper.so.1
    sudo ln -sf /usr/local/lib/libwhisper.so.1.6.2 /usr/local/lib/libwhisper.so
    sudo ldconfig
    ok "Shared libraries updated"
else
    ok "Shared libraries unchanged"
fi

echo ""
ok "Done. Run ./start-assistant.sh to start."
echo ""
