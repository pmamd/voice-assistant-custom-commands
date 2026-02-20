# Voice Assistant with Custom Commands

A voice assistant system combining Speech-to-Text (Whisper), LLM (LLaMA), and Text-to-Speech (Piper TTS) with support for LLM-bypass custom commands.

## Key Features

- **Speech-to-Text**: Real-time speech recognition using Whisper
- **LLM Conversation**: Natural language processing using LLaMA
- **Text-to-Speech**: High-quality speech synthesis using Piper
- **Custom Commands**: Commands that bypass the LLM for instant execution
  - **Interruptibility**: Say "stop" to interrupt the AI while speaking
  - **Extensible**: Framework for adding more direct commands

## Architecture

![Architecture Diagram](./architecture-diagram.svg)

<details>
<summary>View ASCII diagram</summary>

```
                    ┌──────────────┐
                    │  Microphone  │
                    └──────┬───────┘
                           │ (audio input, including commands)
                           ▼
┌──────────────────────────────────────────────────────────┐
│              talk-llama-custom (Main App)                │
│                                                          │
│  ┌──────────┐                ┌────────┐                 │
│  │ Whisper  │───────────────▶│ LLaMA  │                 │
│  │   STT    │  (normal text) │  LLM   │                 │
│  └────┬─────┘                └────┬───┘                 │
│       │                           │                     │
│       │                           ▼                     │
│       │                      ┌────────┐                 │
│       │   commands (bypass   │  TTS   │◀────────────────┘
│       └─────────────────────▶│ Client │                 │
│                              └────┬───┘                 │
│                                   │                     │
│                                   │ HTTP POST           │
│                                   │ {text: "...", ...}  │
└───────────────────────────────────┼─────────────────────┘
                                    │
                                    ▼
                         ┌──────────────────────────┐
                         │   wyoming-piper          │
                         │   TTS Server             │
                         │                          │
                         │  ┌────────────────────┐  │
                         │  │ Command Detection  │  │
                         │  │ (e.g., "stop")     │  │
                         │  └─────────┬──────────┘  │
                         │            │             │
                         │            ▼             │
                         │  ┌────────────────────┐  │
                         │  │  Piper Synthesis   │  │
                         │  └─────────┬──────────┘  │
                         │            │             │
                         │            ▼             │
                         │  ┌────────────────────┐  │
                         │  │  aplay (Audio Out) │──┼──▶ 🔊 Speaker
                         │  └────────────────────┘  │
                         └──────────────────────────┘
```
</details>

## Repository Structure

This repository uses **git submodules** for upstream dependencies to keep only custom code in the main repo:

```
voice-assistant-custom-commands/
├── whisper.cpp/              # Submodule: Upstream Whisper STT engine
├── wyoming-piper/            # Submodule: Upstream Wyoming-Piper TTS server
├── custom/                   # Your custom modifications
│   ├── talk-llama/           # Modified talk-llama application
│   │   ├── talk-llama.cpp    # Main application (TTS fixes, test mode)
│   │   ├── llama.cpp         # Full LLaMA inference engine
│   │   ├── llama.h           # LLaMA API header
│   │   └── MODIFICATIONS.md  # Documentation of changes
│   └── wyoming-piper/        # Modified Wyoming-Piper files
│       ├── __main__.py       # Entry point (test mode support)
│       ├── handler.py        # Event handler (stop cmd, test mode)
│       └── MODIFICATIONS.md  # Documentation of changes
├── tests/                    # Test harness
│   ├── audio_generator.py    # Piper TTS test audio generator
│   ├── audio_verifier.py     # Whisper STT output verifier
│   ├── run_tests.py          # Test orchestrator
│   ├── test_cases.yaml       # Test definitions
│   └── README.md             # Test harness documentation
├── CMakeLists.txt            # Build configuration
└── README.md                 # This file
```

## What's Custom vs Upstream

### 🎯 Custom Code (This Repo)

**talk-llama modifications** (`custom/talk-llama/`):
- **talk-llama.cpp** - Main application with:
  - TTS crash bugfixes (safe string handling, CURL error checking)
  - Test mode support (`--test-input` for automated testing)
  - Skip warmup transcription in test mode
  - Debug output and proper cleanup
- **llama.cpp/llama.h** - Full LLaMA inference engine from llama.cpp repo
- See `custom/talk-llama/MODIFICATIONS.md` for details

**Wyoming-Piper modifications** (`custom/wyoming-piper/`):
- **__main__.py** - Added test mode arguments (`--test-mode`, `--test-output-dir`)
- **handler.py** - Modified with:
  - Stop command detection (bypasses TTS for "stop" utterances)
  - Test mode logic (save audio to files instead of playing)
  - Direct audio playback via aplay
- See `custom/wyoming-piper/MODIFICATIONS.md` for details

**Test harness** (`tests/`):
- Complete end-to-end testing framework
- Synthetic audio generation + verification
- See `tests/README.md` for documentation

### 📦 Upstream Dependencies (Submodules)

**whisper.cpp**:
- Whisper STT engine and GGML backend
- Locked at commit: `d207c688` (whisper.cpp v1.5.5 era)
- Source: https://github.com/ggerganov/whisper.cpp
- Includes: Whisper models, GGML tensor library, examples

**wyoming-piper**:
- Wyoming protocol TTS server with Piper
- Locked at commit: `21f9966d`
- Source: https://github.com/rhasspy/wyoming-piper
- Custom modifications overlaid from `custom/wyoming-piper/`

## Prerequisites

### System Requirements
- Linux (Ubuntu/Debian recommended) or Windows with WSL
- Python 3.9+
- C++ compiler (gcc/g++ 8+)
- CMake 3.12+
- CUDA Toolkit 11.x+ (optional, for GPU acceleration)
- Audio system with ALSA (`aplay` command)

### Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    libsdl2-dev \
    libcurl4-openssl-dev \
    alsa-utils \
    python3 \
    python3-pip

# Optional: CUDA for GPU acceleration
# Follow NVIDIA CUDA installation guide
```

## Setup

### 1. Clone with Submodules

```bash
git clone --recursive https://github.com/pmamd/voice-assistant-custom-commands.git
cd voice-assistant-custom-commands
```

If you already cloned without `--recursive`:
```bash
git submodule update --init --recursive
```

### 2. Build the Voice Assistant

```bash
# CPU-only build
cmake -B build -DWHISPER_SDL2=ON
cmake --build build -j

# GPU build (CUDA)
cmake -B build -DWHISPER_SDL2=ON -DWHISPER_CUDA=ON
cmake --build build -j
```

The executable will be at: `build/bin/talk-llama-custom`

### 3. Download Models

**Whisper Model:**
```bash
cd whisper.cpp/models
# English (150MB)
bash download-ggml-model.sh base.en

# Multilingual (150MB)
bash download-ggml-model.sh base

# Better quality (1.5GB)
bash download-ggml-model.sh medium
```

**LLaMA Model:**
Download a GGUF model (e.g., Mistral 7B):
```bash
# Example: Mistral 7B Instruct Q5_0 (~5GB)
wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q5_0.gguf
```

### 4. Setup Wyoming-Piper TTS Server

```bash
# Install base Wyoming-Piper from submodule
cd wyoming-piper
pip install -e .

# Overlay custom modifications
cd ..
cp custom/wyoming-piper/__main__.py wyoming-piper/wyoming_piper/
cp custom/wyoming-piper/handler.py wyoming-piper/wyoming_piper/
```

## Usage

### 1. Start the TTS Server

```bash
cd wyoming-piper
python3 -m wyoming_piper \
    --piper /usr/bin/piper \
    --uri tcp://0.0.0.0:8020 \
    --voice en_US-lessac-medium
```

The server will auto-download the voice model on first run.

### 2. Run the Voice Assistant

```bash
cd build/bin
./talk-llama-custom \
    -m /path/to/mistral-7b-instruct-v0.2.Q5_0.gguf \
    --model-whisper ../../whisper.cpp/models/ggml-base.en.bin \
    --xtts-url http://localhost:8020/ \
    --xtts-voice emma_1 \
    -p "You are a helpful AI assistant."
```

### 3. Interact

- **Speak** into your microphone
- The AI will **respond** with speech
- Say **"stop"** to interrupt the AI mid-sentence
- Press **Ctrl+C** to exit

## Custom Commands

### Current Commands

- **"stop"** - Interrupts AI speech output

### Adding New Commands

To add custom LLM-bypass commands:

1. Edit `custom/talk-llama/talk-llama.cpp`
2. Add detection logic in the speech processing loop
3. Route to appropriate handler instead of LLaMA
4. Optionally add server-side handling in `wyoming-piper/`

Example command categories:
- **Control commands**: stop, pause, resume, repeat
- **System commands**: volume up/down, mute
- **Quick queries**: what time, what date
- **App control**: exit, restart, help

## Configuration

### Build Options

```bash
# Enable SDL2 (required for talk-llama)
-DWHISPER_SDL2=ON

# Enable CUDA acceleration
-DWHISPER_CUDA=ON

# Enable OpenBLAS
-DWHISPER_OPENBLAS=ON

# Enable Core ML (macOS)
-DWHISPER_COREML=ON
```

### Runtime Options

See `./talk-llama-custom --help` for all options. Common ones:

```bash
# Model paths
-m <path>              # LLaMA model path
--model-whisper <path> # Whisper model path

# TTS configuration
--xtts-url <url>       # TTS server URL (default: http://localhost:8020/)
--xtts-voice <name>    # Voice/speaker name

# LLM parameters
-p <prompt>            # System prompt
-c <size>              # Context size (default: 2048)
--temp <value>         # Temperature (default: 0.8)

# Audio settings
--language <lang>      # Language code (default: en)
--vad-thold <value>    # Voice activity detection threshold
```

## Development

### Updating Whisper.cpp

```bash
cd whisper.cpp
git fetch origin
git checkout <new-commit-hash>
cd ..
git add whisper.cpp
git commit -m "Update whisper.cpp to <version>"
```

### Modifying Custom Code

All your modifications should go in:
- `custom/talk-llama/` - For main application changes
- `wyoming-piper/` - For TTS server changes

```bash
# After making changes
cd custom/talk-llama
# Edit talk-llama.cpp
cd ../..
cmake --build build -j
```

### Viewing Differences from Upstream

```bash
# See what's different from base whisper.cpp example
cd whisper.cpp/examples/talk-llama
diff -u talk-llama.cpp ../../../custom/talk-llama/talk-llama.cpp
```

## Troubleshooting

### Submodule Issues

If whisper.cpp is empty after cloning:
```bash
git submodule update --init --recursive
```

### Build Errors

Missing SDL2:
```bash
sudo apt-get install libsdl2-dev
```

Missing CURL:
```bash
sudo apt-get install libcurl4-openssl-dev
```

### TTS Connection Issues

Test server connectivity:
```bash
curl -X POST http://localhost:8020/tts_to_audio/ \
  -H "Content-Type: application/json" \
  -d '{"text":"hello world","language":"en","speaker_wav":"emma_1"}'
```

### Audio Playback Issues

Test ALSA:
```bash
aplay -l                                    # List audio devices
aplay /usr/share/sounds/alsa/Front_Center.wav  # Test playback
```

## Known Limitations

1. **Platform**: Linux/WSL only (uses aplay for audio)
2. **Stop command**: Basic detection (just checks for "stop" in text < 10 chars)
3. **TTS interruption**: Not fully implemented (aplay waits for completion)
4. **Hardcoded paths**: Wyoming-piper has hardcoded local library path

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes (preferably in `custom/` directory)
4. Test thoroughly
5. Submit a pull request

## License

- **Custom code** (custom/, wyoming-piper modifications): Your license here
- **whisper.cpp**: MIT License - See whisper.cpp/LICENSE
- **Whisper models**: OpenAI
- **LLaMA models**: Meta AI (see individual model licenses)

## Credits

- **Whisper STT**: OpenAI
- **whisper.cpp**: Georgi Gerganov and contributors
- **LLaMA**: Meta AI
- **Piper TTS**: Rhasspy project
- **Wyoming Protocol**: Rhasspy project
- **talk-llama-fast**: Original modifications by Mozer
- **This project**: Paul Mobbs (2024-2026)

## Links

- **Upstream whisper.cpp**: https://github.com/ggerganov/whisper.cpp
- **talk-llama-fast** (inspiration): https://github.com/Mozer/talk-llama-fast
- **Wyoming-Piper**: https://github.com/rhasspy/wyoming-piper
- **Piper TTS**: https://github.com/rhasspy/piper

## Support

For issues:
1. Check the Troubleshooting section
2. Review logs from both talk-llama-custom and wyoming-piper
3. Open an issue with detailed error messages and steps to reproduce
