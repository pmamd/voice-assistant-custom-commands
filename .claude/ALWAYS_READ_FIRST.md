# ⚠️ CRITICAL: READ THIS FIRST ON EVERY SESSION ⚠️

## Dev Machine Connection (NEVER FORGET!)

**ALWAYS check this file:**
- At the start of EVERY conversation continuation
- After EVERY compaction event (when you see a summary)
- When asked to build/test
- Before making assumptions about configuration

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
- ✅ **DO**: Test EVERYTHING before asking user to test
- ✅ **DO**: Only merge to main after testing confirms it works
- ❌ **DON'T**: Forget this setup exists
- ❌ **DON'T**: Try to build locally in WSL
- ❌ **DON'T**: Use direct SSH commands
- ❌ **DON'T**: Ask user to test untested code
- ❌ **DON'T**: Ask user to approve commits to main that haven't been tested

### Testing Workflow (CRITICAL - NEVER SKIP)

**BEFORE asking user to test:**
1. ✅ Build succeeds on dev machine
2. ✅ Run automated tests (at least 30 seconds runtime to get past initialization)
3. ✅ Check logs for expected output (Wyoming test, energy output, VAD triggers if possible)
4. ✅ Verify no errors or crashes
5. ✅ Document what was tested and what still needs manual verification

**BEFORE merging to main:**
1. ✅ All automated tests pass
2. ✅ User has manually tested and confirmed it works
3. ✅ No known issues or regressions
4. ✅ Changes are committed to feature branch first

**NEVER:**
- ❌ Ask user to test code that hasn't been built
- ❌ Ask user to test code that hasn't run through automated tests
- ❌ Propose merging untested code to main
- ❌ Skip testing "because it looks right"

## Current Project State

**Active Branch**: vad-fixes
**Recent Fixes**:
- VAD timestamp precision: microseconds + double (not milliseconds + float)
- VAD minimum energy threshold: 0.0008 (prevents noise triggers)
- Wyoming-Piper TTS connection test with microphone pause (prevents feedback loop)
- Custom Wyoming-Piper with aplay support (committed to custom/wyoming-piper/)
- Signal handler for Ctrl+C
- Energy output formatting

**Models Location** (on dev machine):
- Whisper: `~/Projects/git/talk-llama-fast/whisper.cpp/models/ggml-tiny.en.bin`
- LLaMA: `~/Projects/git/talk-llama-fast/models/llama-2-7b-chat.Q4_K_M.gguf`
  - ⚠️ **CRITICAL**: ALWAYS use the 7B model for testing, NEVER use tiny LLaMA!

**Wyoming-Piper Configuration**:
- Port: 10200
- Custom files: `custom/wyoming-piper/` (handler.py, process.py, __main__.py)
- Features: Local aplay playback, stop command detection, test mode support

---

**Last Updated**: 2026-02-24
**Purpose**: Never forget dev machine setup again!
