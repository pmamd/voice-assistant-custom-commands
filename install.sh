#!/bin/bash
# Voice Assistant Installer
# Sets up a new target board with the pre-built binary and all dependencies.
#
# Usage: ./install.sh
# Requirements: Ubuntu/Debian, x86-64, AMD GPU (gfx1153 / RDNA3)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- colours ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${CYAN}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; exit 1; }

prompt_yes_no() {
    local question="$1"
    local default="${2:-n}"
    local yn_hint
    [[ "$default" == "y" ]] && yn_hint="Y/n" || yn_hint="y/N"
    read -r -p "$question [$yn_hint] " answer
    answer="${answer:-$default}"
    [[ "$answer" =~ ^[Yy]$ ]]
}

echo ""
echo "=========================================="
echo " Voice Assistant — Installer"
echo "=========================================="
echo ""

# ---------------------------------------------------------------------------
# 0. Python version check (wyoming-piper requires >= 3.9)
# ---------------------------------------------------------------------------
info "Checking Python version..."

PYTHON_BIN="$(command -v python3 2>/dev/null)" || fail "python3 not found. Install it first: sudo apt-get install python3"

PYTHON_MAJOR=$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.minor)')

if [[ "$PYTHON_MAJOR" -lt 3 ]] || { [[ "$PYTHON_MAJOR" -eq 3 ]] && [[ "$PYTHON_MINOR" -lt 9 ]]; }; then
    fail "Python 3.9+ required (found $PYTHON_MAJOR.$PYTHON_MINOR). Upgrade Python before running this installer."
fi

ok "Python $PYTHON_MAJOR.$PYTHON_MINOR"

# ---------------------------------------------------------------------------
# 0b. AMD GPU driver check
# ---------------------------------------------------------------------------
info "Checking AMD GPU driver..."

AMDGPU_LIBDRM="/opt/amdgpu/lib/x86_64-linux-gnu/libdrm.so.2"

if [[ ! -f "$AMDGPU_LIBDRM" ]]; then
    fail "AMD GPU driver not found ($AMDGPU_LIBDRM missing). Install the amdgpu driver stack before running this installer."
fi

if ! lsmod | grep -q "^amdgpu"; then
    warn "amdgpu kernel module is not loaded. The binary may not run correctly."
else
    ok "AMD GPU driver present (amdgpu module loaded, libdrm found)"
fi

# ---------------------------------------------------------------------------
# 1. Verify pre-built binaries are present
# ---------------------------------------------------------------------------
info "Checking pre-built binaries..."

DIST_BIN="$SCRIPT_DIR/dist/bin/talk-llama-custom"
DIST_LIBWHISPER="$SCRIPT_DIR/dist/lib/libwhisper.so.1.6.2"
DIST_LIBGGML="$SCRIPT_DIR/dist/lib/libggml.so"

[[ -f "$DIST_BIN" ]]        || fail "dist/bin/talk-llama-custom not found. Is the repo up to date?"
[[ -f "$DIST_LIBWHISPER" ]] || fail "dist/lib/libwhisper.so.1.6.2 not found."
[[ -f "$DIST_LIBGGML" ]]    || fail "dist/lib/libggml.so not found."
ok "Pre-built binaries present"

# ---------------------------------------------------------------------------
# 2. System packages
# ---------------------------------------------------------------------------
info "Installing runtime system packages..."

sudo apt-get update -qq
sudo apt-get install -y \
    libsdl2-2.0-0 \
    libcurl4 \
    libcjson1 \
    alsa-utils \
    python3 \
    pipx

ok "System packages installed"

# ---------------------------------------------------------------------------
# 3. Install the binary and shared libraries
# ---------------------------------------------------------------------------
info "Installing binary to build/bin/..."

mkdir -p "$SCRIPT_DIR/build/bin"
cp "$DIST_BIN" "$SCRIPT_DIR/build/bin/talk-llama-custom"
chmod +x "$SCRIPT_DIR/build/bin/talk-llama-custom"
ok "Binary installed → build/bin/talk-llama-custom"

info "Installing shared libraries to /usr/local/lib/..."
sudo cp "$DIST_LIBWHISPER" /usr/local/lib/libwhisper.so.1.6.2
sudo ln -sf /usr/local/lib/libwhisper.so.1.6.2 /usr/local/lib/libwhisper.so.1
sudo ln -sf /usr/local/lib/libwhisper.so.1.6.2 /usr/local/lib/libwhisper.so
sudo cp "$DIST_LIBGGML" /usr/local/lib/libggml.so
sudo ldconfig
ok "Shared libraries installed and ldconfig updated"

info "Verifying binary links cleanly..."
MISSING=$(ldd "$SCRIPT_DIR/build/bin/talk-llama-custom" 2>&1 | grep "not found" || true)
if [[ -n "$MISSING" ]]; then
    fail "Binary has unresolved library dependencies:\n$MISSING\nInstall the missing libraries and re-run."
fi
ok "All binary dependencies satisfied"

# ---------------------------------------------------------------------------
# 4. Piper TTS (Python package, exact version required)
# ---------------------------------------------------------------------------
info "Installing Piper TTS..."

export PATH="$HOME/.local/bin:$PATH"

if pipx list 2>/dev/null | grep -q "piper-tts"; then
    ok "piper-tts already installed"
else
    pipx install 'piper-tts==1.4.1'
    ok "piper-tts installed"
fi

if pipx runpip piper-tts show pathvalidate &>/dev/null; then
    ok "pathvalidate already present"
else
    pipx inject piper-tts pathvalidate
    ok "pathvalidate injected"
fi

# Verify it's the Python version not the C++ binary (pipx installs a symlink
# to a Python script, so use file -L to follow the symlink; check it's NOT ELF)
PIPER_PATH="$(command -v piper 2>/dev/null || echo "$HOME/.local/bin/piper")"
if file -L "$PIPER_PATH" 2>/dev/null | grep -q "ELF"; then
    fail "piper at $PIPER_PATH is a C++ binary, not piper-tts. Remove it and re-run:\n  sudo rm -f $(which piper)\n  pipx install piper-tts==1.4.1"
else
    ok "Piper is the correct Python version (not C++ binary)"
fi

# ---------------------------------------------------------------------------
# 5. Wyoming-Piper (custom version from repo submodule)
# ---------------------------------------------------------------------------
info "Installing Wyoming-Piper (custom version)..."

WYOMING_DIR="$SCRIPT_DIR/wyoming-piper"
[[ -d "$WYOMING_DIR" ]] || fail "wyoming-piper/ directory not found. Did you clone with --recursive?"

# Check if already installed AND pointing to the correct directory.
# pipx editable installs record their source path in direct_url.json — if it
# points somewhere else (e.g. a previous installation), force reinstall.
WYOMING_DIRECT_URL=$(find "$HOME/.local/share/pipx/venvs/wyoming-piper-custom" \
    -name "direct_url.json" 2>/dev/null | xargs cat 2>/dev/null)
WYOMING_INSTALLED_PATH=$(echo "$WYOMING_DIRECT_URL" | grep -o '"url":"[^"]*"' | grep -o 'file://.*' | sed 's|file://||')

if [[ "$WYOMING_INSTALLED_PATH" == "$WYOMING_DIR" ]]; then
    ok "wyoming-piper-custom already installed (correct path)"
else
    if [[ -n "$WYOMING_INSTALLED_PATH" ]]; then
        info "wyoming-piper-custom installed but points to wrong path:"
        info "  installed: $WYOMING_INSTALLED_PATH"
        info "  expected:  $WYOMING_DIR"
        info "Reinstalling..."
    fi
    cd "$WYOMING_DIR"
    pipx install --force -e .
    cd "$SCRIPT_DIR"
    ok "wyoming-piper-custom installed"
fi

# ---------------------------------------------------------------------------
# 6. PATH
# ---------------------------------------------------------------------------
if ! grep -q 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    ok "Added ~/.local/bin to PATH in .bashrc"
else
    ok "PATH already includes ~/.local/bin"
fi

# ---------------------------------------------------------------------------
# 7. Whisper model
# ---------------------------------------------------------------------------
echo ""
WHISPER_MODEL="$SCRIPT_DIR/whisper.cpp/models/ggml-tiny.en.bin"
if [[ -f "$WHISPER_MODEL" ]]; then
    ok "Whisper model already present: ggml-tiny.en.bin"
else
    if prompt_yes_no "Download Whisper model (ggml-tiny.en, ~75MB)?" "y"; then
        mkdir -p "$SCRIPT_DIR/whisper.cpp/models"
        wget --show-progress -O "$SCRIPT_DIR/whisper.cpp/models/ggml-tiny.en.bin" \
            "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
        ok "Whisper model downloaded"
    else
        warn "Whisper model not downloaded. Place ggml-tiny.en.bin in whisper.cpp/models/ before running."
    fi
fi

# ---------------------------------------------------------------------------
# 8. LLM model
# ---------------------------------------------------------------------------
echo ""
MISTRAL_MODEL="$SCRIPT_DIR/models/mistral-7b-instruct-v0.2.Q5_0.gguf"
LLAMA_MODEL="$SCRIPT_DIR/models/llama-2-7b-chat.Q4_K_M.gguf"
mkdir -p "$SCRIPT_DIR/models"

if [[ -f "$MISTRAL_MODEL" ]]; then
    ok "Mistral 7B model already present"
elif prompt_yes_no "Download Mistral 7B Instruct Q5_0 (~4.6GB, recommended)?" "y"; then
    info "Downloading Mistral 7B..."
    wget --show-progress -P "$SCRIPT_DIR/models" \
        "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q5_0.gguf"
    ok "Mistral 7B downloaded"
else
    warn "No LLM model downloaded."
    if [[ ! -f "$LLAMA_MODEL" ]]; then
        if prompt_yes_no "Download LLaMA-2 7B Chat Q4_K_M instead (~3.8GB)?" "n"; then
            wget --show-progress -P "$SCRIPT_DIR/models" \
                "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf"
            ok "LLaMA-2 7B downloaded"
        else
            warn "No LLM model downloaded. Place a .gguf model in models/ and update start-assistant.sh."
        fi
    else
        ok "LLaMA-2 7B model already present"
    fi
fi

# ---------------------------------------------------------------------------
# 9. Voice data directory
# ---------------------------------------------------------------------------
mkdir -p "$SCRIPT_DIR/piper-data"
ok "piper-data/ directory ready (voice model downloaded on first use)"

# ---------------------------------------------------------------------------
# 10. Final verification
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo " Verification"
echo "=========================================="

ERRORS=0

check() {
    local label="$1"; local path="$2"
    if [[ -e "$path" ]]; then
        ok "$label"
    else
        warn "MISSING: $label ($path)"
        ERRORS=$((ERRORS + 1))
    fi
}

check "Binary"           "$SCRIPT_DIR/build/bin/talk-llama-custom"
check "libwhisper.so.1"  "/usr/local/lib/libwhisper.so.1"
check "libggml.so"       "/usr/local/lib/libggml.so"
check "piper"            "$HOME/.local/bin/piper"
check "wyoming-piper-custom" "$HOME/.local/bin/wyoming-piper-custom"
[[ -f "$WHISPER_MODEL" ]] && check "Whisper model" "$WHISPER_MODEL" || warn "Whisper model not present yet"
ls "$SCRIPT_DIR"/models/*.gguf &>/dev/null && ok "LLM model present" || warn "No .gguf model in models/ yet"

echo ""
if [[ $ERRORS -eq 0 ]]; then
    echo -e "${GREEN}=========================================="
    echo " Installation complete"
    echo -e "==========================================${NC}"
    echo ""
    echo "Start the assistant:"
    echo "  ./start-assistant.sh"
else
    echo -e "${YELLOW}=========================================="
    echo " Installation complete with $ERRORS warning(s)"
    echo -e "==========================================${NC}"
    echo ""
    echo "Resolve warnings above before running ./start-assistant.sh"
fi
echo ""
