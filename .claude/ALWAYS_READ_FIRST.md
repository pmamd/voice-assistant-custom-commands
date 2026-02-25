# ⚠️ CRITICAL: READ THIS FIRST ON EVERY SESSION ⚠️

## Dev Machine Connection (NEVER FORGET!)

**ALWAYS check this file at the start of EVERY conversation continuation or when asked to build/test.**

### Connection Details
- **Hostname**: 192.168.86.74
- **Username**: paul
- **Password**: amdisthebest
- **Method**: Python with paramiko (NEVER use direct SSH - WSL doesn't have SSH access)

### Build/Test Workflow

**STEP 1**: Activate Python venv (REQUIRED for paramiko)
```bash
source /tmp/build-venv/bin/activate
```

**STEP 2**: Use Python script with paramiko to connect and execute commands

**Example**:
```python
import paramiko

hostname = "192.168.86.74"
username = "paul"
password = "amdisthebest"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname, username=username, password=password)

# Execute build command
stdin, stdout, stderr = client.exec_command(
    "cd ~/Projects/git/talk-llama-fast && cmake --build build -j4"
)
print(stdout.read().decode())
client.close()
```

### Quick Reference Scripts

Located in /tmp/:
- `/tmp/build_and_test_vad_fixes.py` - Full build and test automation
- `/tmp/build-venv/` - Python virtual environment with paramiko

### WHY This Matters

- ❌ **CANNOT** build in WSL - no cmake available
- ❌ **CANNOT** use direct `ssh` command - connection refused on localhost:22
- ✅ **MUST** use Python venv + paramiko to connect to 192.168.86.74
- ✅ **MUST** run all tests on dev machine (has models, Piper TTS, etc.)

### When to Use This

**EVERY TIME** the user asks to:
- Build the project
- Test changes
- Run the voice assistant
- Verify fixes
- Deploy changes

**BEFORE** doing anything else:
1. Read this file
2. Activate /tmp/build-venv
3. Use paramiko to connect to 192.168.86.74
4. Execute commands remotely

### Reminders

- ✅ **DO**: Always check DEV_SETUP.md for full details
- ✅ **DO**: Activate venv before using paramiko
- ✅ **DO**: Use 192.168.86.74 for builds/tests
- ❌ **DON'T**: Forget this setup exists
- ❌ **DON'T**: Try to build locally in WSL
- ❌ **DON'T**: Use direct SSH commands

## Current Project State

**Active Branch**: vad-fixes
**Recent Fixes**:
- VAD state machine (0/1/2 states)
- Wyoming-Piper TTS connection test
- Signal handler for Ctrl+C
- Energy output formatting

**Models Location** (on dev machine):
- Whisper: `~/Projects/git/talk-llama-fast/whisper.cpp/models/ggml-tiny.en.bin`
- LLaMA: `~/Projects/git/talk-llama-fast/models/llama-2-7b-chat.Q4_K_M.gguf`

**Wyoming-Piper**: Running on port 10200

---

**Last Updated**: 2026-02-24
**Purpose**: Never forget dev machine setup again!
