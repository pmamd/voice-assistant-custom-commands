# Development Setup Guide

**NOTE: DO NOT RENAME THIS FILE.** Claude Code reads this file at session start and after compaction to restore context.

---

## Runtime Context

**Claude Code runs directly on the dev machine (192.168.86.74).**

There is no WSL intermediary. Edit, build, and test all happen locally. No SSH, no scp, no paramiko needed for dev work.

## Machines

| Role | Address | User | Project path |
|------|---------|------|-------------|
| **Dev machine** (here) | `192.168.86.74` | `paul` | `~/git/voice-assistant-custom-commands` |
| **Target machine** | `192.168.86.26` | `amd` | `~/Projects/git/talk-llama-fast` |

## Development Workflow

```
Edit file
    │
    ▼
cmake --build build -j          ← run directly, no SSH
    │
    ▼
python3 -m unittest tests.X -v  ← run directly, no SSH
    │
    ▼
Tests pass → commit → push → deploy to target
```

### Deploy to target after tests pass

```bash
ssh amd@192.168.86.26 "cd ~/Projects/git/talk-llama-fast && git pull && cmake --build build -j"
```

## Build

```bash
cd ~/git/voice-assistant-custom-commands

# Configure (only needed once or after CMakeLists changes)
cmake -B build -DWHISPER_SDL2=ON

# Build
cmake --build build -j

# Binary at: build/bin/talk-llama-custom
```

## Test

Wyoming-Piper must be running before running tests:

```bash
# Start Wyoming-Piper (if not already running)
$HOME/.local/bin/wyoming-piper-custom \
    --piper $HOME/.local/bin/piper \
    --voice en_US-lessac-medium \
    --data-dir ~/git/voice-assistant-custom-commands/piper-data \
    --uri tcp://0.0.0.0:10200 >> /tmp/wyoming-piper.log 2>&1 &

# Run tests
cd ~/git/voice-assistant-custom-commands
python3 -m unittest tests.test_real_interrupt.TestWyomingStopMechanics -v
python3 -m unittest tests.test_wyoming_piper_unit.TestLLMOutputQuality -v

# Run both together
python3 -m unittest tests.test_real_interrupt.TestWyomingStopMechanics \
                    tests.test_wyoming_piper_unit.TestLLMOutputQuality -v
```

## Key Paths on Dev Machine

| Item | Path |
|------|------|
| Project | `~/git/voice-assistant-custom-commands/` |
| Binary | `~/git/voice-assistant-custom-commands/build/bin/talk-llama-custom` |
| LLM model | `~/git/voice-assistant-custom-commands/models/mistral-7b-instruct-v0.2.Q5_0.gguf` |
| Whisper model | `~/git/voice-assistant-custom-commands/whisper.cpp/models/ggml-tiny.en.bin` |
| Piper binary | `~/.local/bin/piper` |
| Wyoming-Piper | `~/.local/bin/wyoming-piper-custom` |
| TTS log | `/tmp/wyoming-piper.log` |
| Piper data | `~/git/voice-assistant-custom-commands/piper-data/` |

## Testing Discipline

- **Never** claim something works without running tests
- **Never** ask the user to test code that hasn't been built and tested locally first
- **Never** merge untested code to main
- Only after `python3 -m unittest` shows all green is it valid to claim it works

## Common Issues

**Wyoming-Piper not running:**
```bash
pgrep -fa wyoming_piper | grep -v grep
ss -tuln | grep 10200
```

**Port 10200 already in use:**
```bash
kill $(lsof -ti tcp:10200) && sleep 1
# then restart Wyoming-Piper
```

**Build fails:**
```bash
# Check for errors
cmake --build build -j 2>&1 | grep "error:"

# Full reconfigure if needed
cmake -B build -DWHISPER_SDL2=ON
cmake --build build -j
```

**aplay left running after tests:**
```bash
pkill -9 aplay
```
