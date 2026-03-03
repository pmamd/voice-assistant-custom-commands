# Voice Assistant Deployment Quick Start

This is a condensed deployment guide focusing on the most critical steps and common pitfalls.

## ⚠️ Critical Requirements

**DO NOT SKIP THESE**:

1. **Piper TTS Version**: Must be piper-tts 1.4.1 (Python), NOT the C++ binary (1.2.0)
2. **Version Matching**: Dev and target machines must have matching Piper versions
3. **Port Number**: Use port 10200 (not 8020)
4. **System Package**: Install `libcjson-dev` (often forgotten, causes build failure)

## Quick Install (Ubuntu/Debian)

```bash
# 1. Clone repository
git clone --recursive https://github.com/YOUR_USERNAME/voice-assistant-custom-commands.git
cd voice-assistant-custom-commands

# 2. Install system dependencies
sudo apt-get update && sudo apt-get install -y \
    build-essential cmake git \
    libsdl2-dev libcurl4-openssl-dev libcjson-dev \
    alsa-utils python3 python3-pip pipx

# 3. Build application
cmake -B build -DWHISPER_SDL2=ON
cmake --build build -j

# 4. Install Piper TTS 1.4.1 (CRITICAL: Use exact version)
pipx install piper-tts==1.4.1
pipx inject piper-tts pathvalidate

# 5. Install Wyoming-Piper-Custom
cd wyoming-piper
pipx install -e .
cd ..

# 6. Add to PATH
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# 7. Download models
cd whisper.cpp/models
bash download-ggml-model.sh base.en
cd ../..

mkdir -p models
cd models
wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q5_0.gguf
cd ..

# 8. Start the voice assistant
./start-assistant.sh
```

## Verify Installation

Run these checks BEFORE starting the voice assistant:

```bash
# Check Piper version (MUST be Python version 1.4.1)
which piper                    # Should be ~/.local/bin/piper
file $(which piper)            # Should say "Python script"
pipx list | grep piper-tts     # Should show version 1.4.1

# Check Wyoming-Piper
wyoming-piper-custom --version # Should be 2.2.2

# Check builds
ls -lh build/bin/talk-llama-custom
ls -lh whisper.cpp/models/*.bin
ls -lh models/*.gguf
```

## Common Issues and Fixes

### ❌ FileNotFoundError in Wyoming-Piper logs

**Symptom**:
```
FileNotFoundError: [Errno 2] No such file or directory:
'[2026-03-03 11:46:23.441] [piper] [info] Loaded voice...'
```

**Cause**: Wrong Piper version (using C++ binary instead of Python)

**Fix**:
```bash
# Remove old binary
sudo rm -f /opt/piper/piper /usr/local/bin/piper

# Install correct version
pipx install --force piper-tts==1.4.1
pipx inject piper-tts pathvalidate

# Verify
file $(which piper)  # Must show "Python script"
```

### ❌ Wyoming-Piper doesn't show "Ready"

**Symptom**: Wyoming-Piper exits immediately or no "Ready" in logs

**Fix**:
```bash
# Start with debug to see error
wyoming-piper-custom \
    --piper ~/.local/bin/piper \
    --voice en_US-lessac-medium \
    --data-dir ./piper-data \
    --uri tcp://0.0.0.0:10200 \
    --debug

# Should see:
# INFO:wyoming_piper.__main__:Ready
```

### ❌ Build fails with "cJSON.h not found"

**Fix**:
```bash
sudo apt-get install libcjson-dev
cmake --build build -j
```

### ❌ "wyoming-piper-custom: command not found"

**Fix**:
```bash
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Version Matching Checklist

**On Dev Machine**:
```bash
piper --help | head -1
wyoming-piper-custom --version
python3 --version
```

**On Target Machine** (must match dev):
```bash
piper --help | head -1         # Output should match dev
wyoming-piper-custom --version # Should be same as dev
python3 --version              # Should be 3.10+
```

## Start-Up Sequence

The `./start-assistant.sh` script handles everything automatically:

1. ✓ Checks for running processes
2. ✓ Starts Wyoming-Piper on port 10200
3. ✓ Waits for "Ready" message
4. ✓ Auto-detects Piper binary location
5. ✓ Auto-detects available models
6. ✓ Auto-detects microphones
7. ✓ Starts talk-llama voice assistant
8. ✓ Handles Ctrl+C gracefully

**Expected startup output**:
```
==========================================
Voice Assistant with Custom Commands
==========================================

Starting Wyoming-Piper-Custom TTS server...
✓ TTS server is listening on port 10200
✓ TTS server ready

Checking required files...
✓ All required files found

Detecting audio devices...
✓ Using microphone 0: Blue Snowball

==========================================
Starting Voice Assistant
==========================================
```

## Testing

1. **Say "Hello"** → AI should respond
2. **Say "What is two plus two"** → Should answer "four"
3. **Say "Stop"** → Should interrupt AI mid-speech
4. **Press Ctrl+C** → Should exit cleanly

## Support

If issues persist after following this guide:

1. Check full README.md for detailed troubleshooting
2. Verify all checklist items in "Deployment Checklist" section
3. Compare `which piper` output between dev and target machines
4. Check logs: `/tmp/wyoming-piper.log` and console output

## Critical Files

- `start-assistant.sh` - Main startup script (use this!)
- `/tmp/wyoming-piper.log` - TTS server logs
- `~/.local/bin/piper` - Piper TTS binary (must be Python script)
- `~/.local/bin/wyoming-piper-custom` - TTS server executable
