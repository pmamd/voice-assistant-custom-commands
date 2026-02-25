# Quick Start Guide

## Running the Voice Assistant

### Prerequisites

1. **Models downloaded**:
   - Whisper model: `whisper.cpp/models/ggml-tiny.en.bin`
   - LLaMA model: `models/llama-2-7b-chat.Q4_K_M.gguf`

2. **Wyoming-Piper installed**:
   ```bash
   pip install wyoming-piper
   ```

3. **Voice assistant built**:
   ```bash
   cmake -B build -DWHISPER_SDL2=ON
   cmake --build build -j
   ```

### Easy Start

Simply run:
```bash
./start-assistant.sh
```

This will:
1. Check if Wyoming-Piper TTS server is running (start if needed)
2. Verify all required files exist
3. Start the voice assistant with optimal settings

### Manual Start

If you prefer to start components manually:

**1. Start TTS Server (Terminal 1):**
```bash
# Create data directory for voice models
mkdir -p ./piper-data

wyoming-piper \
    --voice en_US-lessac-medium \
    --data-dir ./piper-data \
    --uri tcp://0.0.0.0:10200
```

**2. Start Voice Assistant (Terminal 2):**
```bash
./build/bin/talk-llama-custom \
    -ml ./models/llama-2-7b-chat.Q4_K_M.gguf \
    -mw ./whisper.cpp/models/ggml-tiny.en.bin \
    --xtts-url http://localhost:10200/ \
    --xtts-voice en_US-lessac-medium \
    --temp 0.5
```

### Usage

- **Speak** into your microphone
- The assistant will **listen**, **process**, and **respond** with speech
- Say **"stop"** to interrupt the AI while it's speaking
- Press **Ctrl+C** to exit

### Configuration Options

Edit `start-assistant.sh` to customize:
- `PIPER_VOICE`: TTS voice (default: en_US-lessac-medium)
- `PIPER_DATA_DIR`: Where Piper stores voice models (default: ./piper-data)
- `WYOMING_PORT`: TTS server port (default: 10200)
- `WHISPER_MODEL`: STT model path
- `LLAMA_MODEL`: LLM model path

For more voice options:
```bash
wyoming-piper --list-voices
```

### Monitoring Wyoming-Piper TTS Server

**View TTS logs in real-time:**
```bash
# In a separate terminal
tail -f /tmp/wyoming-piper.log
```

**Watch TTS requests:**
```bash
# See only synthesis requests and errors
tail -f /tmp/wyoming-piper.log | grep -i 'synthesize\|error'
```

**Check server status:**
```bash
# See if Wyoming-Piper is running
ps aux | grep wyoming-piper

# Check if it's listening on port 10200
netstat -tuln | grep 10200
```

### Troubleshooting

**TTS server won't start:**
```bash
# Check if port is in use
netstat -tuln | grep 10200

# View TTS server logs
cat /tmp/wyoming-piper.log

# Kill existing instance if needed
pkill -f wyoming-piper
```

**No audio output:**
```bash
# Test audio playback
aplay -l  # List devices
aplay /usr/share/sounds/alsa/Front_Center.wav  # Test sound
```

**Microphone not working:**
```bash
# Test microphone
arecord -d 5 test.wav  # Record 5 seconds
aplay test.wav  # Play it back
```

**Model not found:**
- Whisper: `cd whisper.cpp/models && bash download-ggml-model.sh tiny.en`
- LLaMA: Download from Hugging Face and place in `models/` directory

### Running Tests

To run the automated test suite:
```bash
cd tests
python3 run_tests.py --config test_cases.yaml --group all
```

See `tests/README.md` for more details.

### Advanced Usage

**Custom prompt:**
```bash
./build/bin/talk-llama-custom \
    -m ./models/llama-2-7b-chat.Q4_K_M.gguf \
    --model-whisper ./whisper.cpp/models/ggml-tiny.en.bin \
    --xtts-url http://localhost:10200/ \
    -p "You are a pirate. Speak like a pirate in all responses. Arr!"
```

**Lower temperature for more deterministic responses:**
```bash
# Add --temp 0.3 for more consistent responses
# Add --temp 0.8 for more creative responses
```

**Different Whisper model for better accuracy:**
```bash
# Download better model
cd whisper.cpp/models
bash download-ggml-model.sh base.en  # 150MB, better accuracy
bash download-ggml-model.sh medium   # 1.5GB, best accuracy

# Use it
--model-whisper ./whisper.cpp/models/ggml-base.en.bin
```

## Next Steps

- See `README.md` for complete documentation
- See `tests/README.md` for testing documentation
- See `tests/SESSION_STATE_FINAL.md` for test results and known limitations
