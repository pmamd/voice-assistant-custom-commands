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
| **Target machine** | `192.168.86.26` | `amd` | `~/git/voice-assistant-custom-commands` |

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
# Pull code and rebuild (preserves existing NPU build configuration)
ssh amd@192.168.86.26 "cd ~/git/voice-assistant-custom-commands && git pull && cmake --build build -j"

# If CMakeLists.txt changed, reconfigure NPU build
ssh amd@192.168.86.26 "cd ~/git/voice-assistant-custom-commands && rm -rf build && cmake -B build -DWHISPER_SDL2=ON -DWHISPER_VITISAI=ON && cmake --build build -j"
```

## Build Configuration

**CRITICAL: Each machine requires a different build configuration. GPU and NPU cannot be enabled together.**

### Dev Machine (.74) - GPU Build

```bash
cd ~/git/voice-assistant-custom-commands

# Clean build (if switching from NPU build)
rm -rf build

# Configure with GPU support (ROCm/HIP)
cmake -B build -DWHISPER_SDL2=ON -DGGML_HIP=ON

# Build
cmake --build build -j

# Verify GPU support
strings build/bin/talk-llama-custom | grep -i "rocm\|hip"

# Binary at: build/bin/talk-llama-custom
```

Hardware: AMD W6800 GPU (gfx1030), ROCm 7.2.1

### Target Machine (.26) - NPU Build

```bash
# SSH to target
ssh amd@192.168.86.26

cd ~/git/voice-assistant-custom-commands

# Clean build (if switching from GPU build)
rm -rf build

# Configure with NPU support ONLY (no GPU)
cmake -B build -DWHISPER_SDL2=ON -DWHISPER_VITISAI=ON

# Build
cmake --build build -j

# Verify NPU support
strings build/bin/talk-llama-custom | grep -i "vitisai\|flexml"

# Test NPU with environment
export HSA_OVERRIDE_GFX_VERSION=11.0.3
source /opt/xilinx/xrt/setup.sh
./build/bin/whisper-cli -m ./whisper.cpp/models/ggml-base.bin -f tests/audio/inputs/make_it_warmer.wav
```

Hardware: AMD 890M iGPU (gfx1153) + NPU, ROCm 7.1.1, VitisAI/FlexML runtime

**Why separate builds?**

Enabling both `-DGGML_HIP=ON` (GPU) and `-DWHISPER_VITISAI=ON` (NPU) simultaneously causes segfaults. The HIP runtime conflicts with the NPU encoder during Whisper inference. Each machine must choose one acceleration method:

- Dev machine: GPU for Whisper and LLM (faster development, no NPU hardware)
- Target machine: NPU for Whisper encoder (production deployment, low power)

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

# Full reconfigure (use correct flags for the machine)
# Dev machine:
cmake -B build -DWHISPER_SDL2=ON -DGGML_HIP=ON
# Target machine:
cmake -B build -DWHISPER_SDL2=ON -DWHISPER_VITISAI=ON

cmake --build build -j
```

**NPU segfaults on target machine:**
```bash
# Verify build has ONLY NPU support (no GPU)
ssh amd@192.168.86.26 'cat ~/git/voice-assistant-custom-commands/build/CMakeCache.txt | grep -E "(GGML_HIP|WHISPER_VITISAI)"'
# Should show: WHISPER_VITISAI:BOOL=ON
# Should NOT show: GGML_HIP:BOOL=ON

# If GPU is enabled, rebuild:
ssh amd@192.168.86.26 "cd ~/git/voice-assistant-custom-commands && rm -rf build && cmake -B build -DWHISPER_SDL2=ON -DWHISPER_VITISAI=ON && cmake --build build -j"
```

**aplay left running after tests:**
```bash
pkill -9 aplay
```
