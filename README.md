# Interruptible Voice Chatbot

An interruptible voice chatbot system combining Speech-to-Text (Whisper), LLM (LLaMA), and Text-to-Speech (Piper TTS) with the ability to interrupt speech and handle voice commands.

## Overview

This project integrates two modified components to create an interruptible voice assistant:

- **talk-llama-fast**: Main chat application (Whisper STT + LLaMA LLM + TTS client)
- **wyoming-piper**: TTS server with interruptibility support

The key innovation is using socket-based communication between the chat client and TTS server, allowing the chat application to continue listening for voice input (like "stop") even while the TTS is generating speech.

## Architecture

```
                    ┌──────────────┐
                    │  Microphone  │
                    └──────┬───────┘
                           │ (audio input, including "stop")
                           ▼
┌──────────────────────────────────────────────────────────┐
│              talk-llama-fast (Main App)                  │
│                                                          │
│  ┌──────────┐                ┌────────┐                 │
│  │ Whisper  │───────────────▶│ LLaMA  │                 │
│  │   STT    │  (normal text) │  LLM   │                 │
│  └────┬─────┘                └────┬───┘                 │
│       │                           │                     │
│       │                           ▼                     │
│       │                      ┌────────┐                 │
│       │   "stop" (bypasses   │  TTS   │◀────────────────┘
│       └─────────────────────▶│ Client │                 │
│                              └────┬───┘                 │
│                                   │                     │
│                                   │ HTTP POST           │
│                                   │ {text: "stop", ...} │
└───────────────────────────────────┼─────────────────────┘
                                    │
                                    ▼
                         ┌──────────────────────────┐
                         │   wyoming-piper          │
                         │   TTS Server             │
                         │                          │
                         │  ┌────────────────────┐  │
                         │  │ Stop Detection     │  │
                         │  │ (if "stop" in text)│  │
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

## Features

- **Speech-to-Text**: Real-time speech recognition using Whisper
- **LLM Conversation**: Natural language understanding and generation using LLaMA
- **Text-to-Speech**: High-quality speech synthesis using Piper
- **Interruptible Output**: Say "stop" to interrupt the AI while it's speaking
- **Voice Commands**: Ability to handle commands that bypass the LLM (future enhancement)
- **Non-blocking Architecture**: Socket-based IPC allows simultaneous listening and speaking

## Repository Structure

```
interruptible-chatbot/
├── talk-llama-fast/          # Modified Whisper + LLaMA chat client
│   └── [custom-modifications branch with TTS bugfixes]
├── wyoming-piper/            # Modified Piper TTS server
│   └── [custom-modifications branch with interruptibility]
└── README.md                 # This file
```

## Modifications

### talk-llama-fast

**Base version**: `54da0a2a770ef602b9966171caeff53cc12f8054`
**Branch**: `custom-modifications`

**Changes**:
- Fixed crash bugs in `send_tts_async()` function (examples/talk-llama/talk-llama.cpp)
  - Added empty string validation before array access
  - Safe string indexing with bounds checking
  - NULL pointer checks for CURL initialization
  - Memory leak fix for curl_slist headers
  - Proper error handling and cleanup

**Original upstream**: https://github.com/Mozer/talk-llama-fast

### wyoming-piper

**Base version**: `21f9966dcc60f59512f5e49ef831f8e30b0f3b77`
**Branch**: `custom-modifications`

**Changes**:
- Added direct audio playback via `aplay` instead of streaming via Wyoming protocol
- Added stop command detection (detects "stop" in short text inputs)
- Added `get_aplay_process()` method to process manager
- Bypassed Wyoming audio chunk streaming for lower latency
- Auto-cleanup of temporary WAV files after playback
- Debug logging infrastructure (commented out, available for troubleshooting)

**Original upstream**: https://github.com/rhasspy/wyoming-piper

## Prerequisites

### System Requirements

- Linux (tested on Ubuntu/Debian)
- Python 3.9+
- C++ compiler (gcc/g++)
- CMake
- CUDA (optional, for GPU acceleration)
- Audio system with ALSA (`aplay` command)

### Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    libsdl2-dev \
    libcurl4-openssl-dev \
    alsa-utils \
    python3 \
    python3-pip \
    git

# Optional: CUDA for GPU acceleration
# Follow NVIDIA CUDA installation guide
```

## Setup

### 1. Clone this repository

```bash
git clone <your-repo-url> interruptible-chatbot
cd interruptible-chatbot
```

### 2. Build talk-llama-fast

```bash
cd talk-llama-fast

# For CPU-only build
cmake -B build
cmake --build build

# For CUDA build (if you have NVIDIA GPU)
cmake -B build -DWHISPER_CUDA=ON
cmake --build build
```

Download Whisper and LLaMA models:
```bash
# Download Whisper model (e.g., base.en)
bash ./models/download-ggml-model.sh base.en

# Download LLaMA model
# See talk-llama-fast/README.md for model download instructions
```

### 3. Setup wyoming-piper

```bash
cd ../wyoming-piper

# Install Python dependencies
pip install -r requirements.txt

# The server will auto-download voice models on first use
```

## Usage

### 1. Start the Wyoming-Piper TTS Server

```bash
cd wyoming-piper
python3 -m wyoming_piper \
    --piper /path/to/piper/binary \
    --uri tcp://0.0.0.0:8020 \
    --voice en_US-lessac-medium
```

**Note**: The first run will download the voice model automatically.

### 2. Run the Chat Application

```bash
cd talk-llama-fast/build/bin
./talk-llama \
    -m /path/to/llama-model.gguf \
    --model-whisper /path/to/whisper-base.en.bin \
    --xtts-url http://localhost:8020/ \
    --xtts-voice emma_1
```

### 3. Interact

- Speak into your microphone
- The AI will respond with speech
- Say "stop" (or any short phrase containing "stop") to interrupt the AI mid-sentence
- Press Ctrl+C to exit

## Configuration

### TTS Server Settings

- **Host**: `localhost` (127.0.0.1)
- **Port**: `8020`
- **Protocol**: HTTP POST to `/tts_to_audio/`
- **Payload**: JSON with `text`, `language`, `speaker_wav`, `reply_part`

### talk-llama Parameters

See `talk-llama --help` for full options. Key parameters:

- `--xtts-url`: TTS server URL (default: http://localhost:8020/)
- `--xtts-voice`: Voice/speaker name
- `-m`: Path to LLaMA model
- `--model-whisper`: Path to Whisper model
- `--language`: Language code (default: en)

## Development

### Making Changes

Both components are on the `custom-modifications` branch:

```bash
# For talk-llama-fast
cd talk-llama-fast
git checkout custom-modifications
# Make changes
git add -A
git commit -m "Description of changes"

# For wyoming-piper
cd ../wyoming-piper
git checkout custom-modifications
# Make changes
git add -A
git commit -m "Description of changes"
```

### Viewing Modifications

To see what was changed from upstream:

```bash
# talk-llama-fast changes
cd talk-llama-fast
git diff 54da0a2a770ef602b9966171caeff53cc12f8054 custom-modifications

# wyoming-piper changes
cd ../wyoming-piper
git diff 21f9966dcc60f59512f5e49ef831f8e30b0f3b77 custom-modifications
```

## Troubleshooting

### TTS Server Connection Issues

1. Verify server is running:
```bash
curl -X POST http://localhost:8020/tts_to_audio/ \
  -H "Content-Type: application/json" \
  -d '{"text":"hello world","language":"en","speaker_wav":"emma_1"}'
```

2. Check firewall settings
3. Ensure port 8020 is not in use by another application

### Audio Playback Issues

1. Test ALSA:
```bash
aplay /usr/share/sounds/alsa/Front_Center.wav
```

2. Check audio device:
```bash
aplay -l
```

3. Set correct ALSA device in wyoming-piper if needed

### Crashes in talk-llama

The bugfixes applied should prevent most crashes. If crashes still occur:

1. Check that you're on the `custom-modifications` branch
2. Verify the bugfix patch was applied:
```bash
cd talk-llama-fast
git log --oneline | head -5
# Should show: "Fix TTS crash bugs in send_tts_async()"
```

### Stop Command Not Working

1. Ensure wyoming-piper is on `custom-modifications` branch
2. The stop command only works with short phrases (< 10 characters)
3. Check server logs for "Saw STOP event" message

## Known Limitations

1. **Stop command detection is basic**: Currently just checks if "stop" appears in text < 10 chars
2. **Hardcoded aplay**: Audio playback uses system `aplay`, not cross-platform
3. **No graceful interrupt**: aplay process waits for completion (interrupt logic commented out)
4. **Local path dependency**: wyoming-piper has hardcoded path to local Wyoming library

## Future Enhancements

- [ ] Implement proper interrupt handling for aplay process
- [ ] Add more sophisticated command word detection
- [ ] Support custom wake words
- [ ] Cross-platform audio playback
- [ ] Voice activity detection during TTS playback
- [ ] Multi-client support for TTS server
- [ ] Configuration file support
- [ ] Docker containerization

## License

This project combines components with different licenses:

- **talk-llama-fast**: See [talk-llama-fast/LICENSE](talk-llama-fast/LICENSE)
- **wyoming-piper**: MIT License (see [wyoming-piper/LICENSE](wyoming-piper/LICENSE))

## Credits

- **talk-llama-fast**: Original by [Mozer](https://github.com/Mozer) and contributors
- **wyoming-piper**: Original by [Rhasspy](https://github.com/rhasspy) project
- **Whisper**: OpenAI
- **LLaMA**: Meta AI
- **Piper TTS**: Rhasspy project
- **Modifications**: Paul Mobbs (2024-2026)

## Contributing

This is a personal project, but suggestions and improvements are welcome:

1. Fork this repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request with detailed description

## Support

For issues:
1. Check the Troubleshooting section above
2. Review logs from both talk-llama and wyoming-piper
3. Open an issue with detailed error messages and steps to reproduce
