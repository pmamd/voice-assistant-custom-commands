# Quick Start

## Critical Requirements

Before you begin:

- **Piper TTS version**: must be `piper-tts==1.4.1` (Python package via pipx), **not** the C++ binary
- **Port**: Wyoming-Piper listens on **10200** (not 8020)
- **System package**: `libcjson-dev` — often forgotten, causes build failure

---

## Installation

```bash
# 1. Clone repository
git clone --recursive https://github.com/pmamd/voice-assistant-custom-commands.git
cd voice-assistant-custom-commands

# 2. System dependencies
sudo apt-get update && sudo apt-get install -y \
    build-essential cmake git \
    libsdl2-dev libcurl4-openssl-dev libcjson-dev \
    alsa-utils python3 python3-pip pipx

# 3. Build
cmake -B build -DWHISPER_SDL2=ON
cmake --build build -j

# 4. Install Piper TTS (exact version required)
pipx install piper-tts==1.4.1
pipx inject piper-tts pathvalidate

# 5. Install Wyoming-Piper (custom version from this repo)
cd wyoming-piper
pipx install -e .
cd ..

# 6. Add pipx binaries to PATH
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# 7. Download Whisper model
cd whisper.cpp/models && bash download-ggml-model.sh tiny.en && cd ../..

# 8. Download LLM (Mistral recommended)
mkdir -p models
wget -P models https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q5_0.gguf
```

---

## Verify Before Starting

```bash
# Piper must be the Python version, not C++ binary
file $(which piper)            # → "Python script" (not "ELF")
pipx list | grep piper-tts    # → version 1.4.1

# Builds present
ls build/bin/talk-llama-custom
ls whisper.cpp/models/*.bin
ls models/*.gguf
```

---

## Starting the Assistant

```bash
./start-assistant.sh
```

The script handles everything: starts Wyoming-Piper on port 10200, waits for it to be ready, detects available microphones, and launches the voice assistant. Press **Ctrl+C** to exit cleanly.

**Expected output:**
```
==========================================
Voice Assistant with Custom Commands
==========================================
Starting Wyoming-Piper TTS server...
✓ TTS server ready

✓ All required files found
✓ Using microphone 0: ...

==========================================
Start speaking or type your message...
```

---

## Manual Start

If you need to start components separately:

**Terminal 1 — TTS server:**
```bash
cd wyoming-piper
python3 -m wyoming_piper \
    --piper ~/.local/bin/piper \
    --voice en_US-lessac-medium \
    --data-dir ../piper-data \
    --uri tcp://0.0.0.0:10200
```

**Terminal 2 — Voice assistant:**
```bash
./build/bin/talk-llama-custom \
    -ml ./models/mistral-7b-instruct-v0.2.Q5_0.gguf \
    -mw ./whisper.cpp/models/ggml-tiny.en.bin \
    --xtts-url http://localhost:10200/ \
    --xtts-voice en_US-lessac-medium \
    --temp 0.5 \
    -n 300 \
    --allow-newline
```

---

## Usage

| Action | How |
|--------|-----|
| Ask something | Speak into your microphone |
| Interrupt the AI | Say **"stop"** while it's talking |
| Exit | Press **Ctrl+C** |

---

## Configuration

Edit `start-assistant.sh` to change:

| Variable | Default | Description |
|----------|---------|-------------|
| `PIPER_VOICE` | `en_US-lessac-medium` | TTS voice |
| `PIPER_DATA_DIR` | `./piper-data` | Voice model cache |
| `WYOMING_PORT` | `10200` | TTS server port |
| `WHISPER_MODEL` | `ggml-tiny.en.bin` | STT model |
| `LLAMA_MODEL` | *(set in script)* | LLM model path |

**Better Whisper accuracy** (larger model, slower):
```bash
cd whisper.cpp/models && bash download-ggml-model.sh base.en
# Then update WHISPER_MODEL in start-assistant.sh
```

**Custom system prompt:**
```bash
./build/bin/talk-llama-custom ... -p "You are a helpful driving assistant. Be concise."
```

---

## Monitoring

```bash
# TTS server logs
tail -f /tmp/wyoming-piper.log

# TTS requests only
tail -f /tmp/wyoming-piper.log | grep -i 'synthesize\|error'

# Check Wyoming-Piper is running
pgrep -fa wyoming_piper

# Check port
ss -tuln | grep 10200
```

---

## Troubleshooting

**Wrong Piper version** — logs show `FileNotFoundError` with a timestamp as the path:
```bash
sudo rm -f /usr/local/bin/piper /opt/piper/piper   # remove C++ binary
pipx install --force piper-tts==1.4.1
pipx inject piper-tts pathvalidate
file $(which piper)   # must say "Python script"
```

**Build fails: `cJSON.h not found`:**
```bash
sudo apt-get install libcjson-dev
cmake --build build -j
```

**`wyoming-piper: command not found`:**
```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
```

**Wyoming-Piper exits immediately:**
```bash
cd wyoming-piper
python3 -m wyoming_piper --piper ~/.local/bin/piper \
    --voice en_US-lessac-medium --data-dir ../piper-data \
    --uri tcp://0.0.0.0:10200 --debug
# Look for the error in the output
```

**No audio output:**
```bash
aplay -l                                          # list devices
aplay /usr/share/sounds/alsa/Front_Center.wav     # test playback
```

**Microphone not detected:**
```bash
arecord -d 3 test.wav && aplay test.wav           # record and play back
```

---

## Running Tests

```bash
# Wyoming stop mechanics
python3 -m unittest tests.test_real_interrupt.TestWyomingStopMechanics -v

# LLM output quality (requires models and Wyoming-Piper running)
python3 tests/test_wyoming_piper_unit.py

# Full test suite
python3 tests/run_tests.py --config tests/test_cases.yaml --group all
```
