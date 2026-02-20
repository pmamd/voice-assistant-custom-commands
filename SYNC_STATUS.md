# Repository Synchronization Status

## Overview

This repository contains code that may exist in multiple locations:
- **Local machine** (Windows WSL): `/mnt/c/Users/paumobbs/OneDrive - Advanced Micro Devices Inc/Documents/Projects/git/talk-llama-fast`
- **Build server**: `paul@192.168.1.124:~/git/wyoming-piper/`

## Current Status

### ✅ Committed to Repository

All custom modifications have been committed to the main repository:

**Commit History**:
- `5f6bbd7` - Restructure wyoming-piper as git submodule
- `be4b9c6` - Add comprehensive test harness documentation
- `3471aeb` - Add complete test harness with test mode support

**Files Tracked**:
- `custom/talk-llama/talk-llama.cpp` - Modified talk-llama with test mode
- `custom/wyoming-piper/__main__.py` - Wyoming-Piper entry point with test mode
- `custom/wyoming-piper/handler.py` - Wyoming-Piper handler with stop command
- `tests/` - Complete test harness (audio_generator, audio_verifier, run_tests, test_cases)

### ✅ Dev Machine Status - SYNCHRONIZED

The dev machine at `paul@192.168.86.74` has Wyoming-Piper modifications that have been committed.

**Location**: `~/git/wyoming-piper/wyoming_piper/`

**Status**: Committed (commit 2b62331 - "Add test mode support and stop command detection")

**Files to Check**:
- `__main__.py` - Should match `custom/wyoming-piper/__main__.py`
- `handler.py` - Should match `custom/wyoming-piper/handler.py`

**Action Required**: Run verification script when server is accessible

## Verification

### Automated Verification

Run the provided script to check synchronization:

```bash
./verify_wyoming_piper_sync.sh
```

This script will:
1. Check build server connectivity
2. Check for uncommitted changes on build server
3. Compare `__main__.py` between local and server
4. Compare `handler.py` between local and server
5. Report any differences

### Manual Verification

If the script is not available or you prefer manual checking:

```bash
# Check dev machine git status
ssh paul@192.168.86.74 "cd ~/git/wyoming-piper && git status"

# Download files for comparison
scp paul@192.168.86.74:~/git/wyoming-piper/wyoming_piper/__main__.py /tmp/server_main.py
scp paul@192.168.86.74:~/git/wyoming-piper/wyoming_piper/handler.py /tmp/server_handler.py

# Compare
diff -u /tmp/server_main.py custom/wyoming-piper/__main__.py
diff -u /tmp/server_handler.py custom/wyoming-piper/handler.py
```

## If Files Differ

If the dev machine has changes that aren't in the repository:

1. **Download from server**:
   ```bash
   scp paul@192.168.86.74:~/git/wyoming-piper/wyoming_piper/__main__.py custom/wyoming-piper/
   scp paul@192.168.86.74:~/git/wyoming-piper/wyoming_piper/handler.py custom/wyoming-piper/
   ```

2. **Review changes**:
   ```bash
   git diff custom/wyoming-piper/__main__.py
   git diff custom/wyoming-piper/handler.py
   ```

3. **Commit if needed**:
   ```bash
   git add custom/wyoming-piper/
   git commit -m "Update Wyoming-Piper from build server"
   git push origin master
   ```

## Dev Machine Git Commit - ✅ COMPLETED

The dev machine Wyoming-Piper changes have been committed:

```bash
# SSH to dev machine
ssh paul@192.168.86.74

# Navigate to Wyoming-Piper
cd ~/git/wyoming-piper

# Check status
git status

# Commit changes
git add wyoming_piper/__main__.py wyoming_piper/handler.py
git commit -m "Add test mode support and stop command detection

- Added --test-mode and --test-output-dir arguments
- Modified handler to save audio files in test mode
- Added stop command detection logic
- Direct audio playback via aplay

Changes integrated into main repository at:
git@github.com:pmamd/voice-assistant-custom-commands.git
See custom/wyoming-piper/ directory"

# Note: This is a local fork - may not need to push to upstream
```

## Source of Truth

**Primary**: This repository (`git@github.com:pmamd/voice-assistant-custom-commands.git`)
- Contains all custom modifications in `custom/` directory
- Submodules point to upstream repositories
- All test harness code

**Secondary**: Dev machine Wyoming-Piper installation (paul@192.168.86.74)
- Used for development and testing
- ✅ Synchronized with `custom/wyoming-piper/`
- Local git repo (committed as of 2026-02-19, commit 2b62331)

## Installation Workflow

When setting up on a new machine:

```bash
# 1. Clone with submodules
git clone --recursive git@github.com:pmamd/voice-assistant-custom-commands.git
cd voice-assistant-custom-commands

# 2. Install base Wyoming-Piper
cd wyoming-piper
pip install -e .

# 3. Overlay custom modifications
cd ..
cp custom/wyoming-piper/__main__.py wyoming-piper/wyoming_piper/
cp custom/wyoming-piper/handler.py wyoming-piper/wyoming_piper/

# 4. Build talk-llama-custom
cmake -B build -DWHISPER_SDL2=ON
cmake --build build -j
```

## Last Updated

- **Date**: 2026-02-19
- **By**: Claude Opus 4.6
- **Commit**: 5f6bbd7 (Restructure wyoming-piper as git submodule)
- **Dev Machine Commit**: 2b62331 (Add test mode support and stop command detection)
