# Project Context - Voice Assistant Custom Commands

## ⚠️ CRITICAL WORKFLOW REQUIREMENTS

### Building & Testing - MUST READ EVERY TIME

1. **This project CANNOT be built in WSL** - no cmake available
2. **ALL builds/tests MUST run on dev machine**: 192.168.86.74
3. **Connection method**: Python with paramiko (NOT direct SSH)
4. **Required**: Activate `/tmp/build-venv` before any remote commands

### Standard Build Procedure

```bash
# Step 1: Activate venv
source /tmp/build-venv/bin/activate

# Step 2: Run Python script with paramiko
python3 /tmp/build_and_test_vad_fixes.py
```

See `.claude/ALWAYS_READ_FIRST.md` for complete details.

## Project Structure

- `custom/talk-llama/` - Custom voice assistant code
- `whisper.cpp/` - STT (submodule)
- `wyoming-piper/` - TTS server (modified)
- `models/` - LLaMA models (on dev machine only)

## Current Work

**Branch**: vad-fixes
**Status**: Testing VAD state machine improvements
**Key Files Modified**:
- custom/talk-llama/talk-llama.cpp (VAD logic, signal handler, Wyoming test)
- start-assistant.sh (VAD threshold 1.2, -pe flag)

## Git Workflow

- Work on feature branches (e.g., vad-fixes)
- Test on dev machine before merging to main
- Never lose changes by checking out without committing

## Common Commands (via paramiko)

```python
# Build
"cd ~/Projects/git/talk-llama-fast && cmake --build build -j4"

# Test VAD
"cd ~/Projects/git/talk-llama-fast && ./start-assistant.sh"

# Check logs
"tail -50 /tmp/wyoming-piper.log"
```

## Dev Machine Details

- IP: 192.168.86.74
- User: paul
- Has: All models, Piper TTS, build tools
- Wyoming-Piper: Port 10200

---

**Auto-reminder**: Read `.claude/ALWAYS_READ_FIRST.md` before building/testing!
