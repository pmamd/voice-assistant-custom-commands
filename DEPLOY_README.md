# Deployment to Dev Machine - Quick Start

## 🚀 One-Command Deploy

```bash
./deploy.sh
```

This will:
1. Setup Python venv with paramiko (if needed)
2. Sync all files to dev machine (192.168.86.74)
3. Install dependencies
4. Build the project
5. Run smoke tests
6. Check Wyoming-Piper status

## Manual Steps

### First Time Setup

```bash
# 1. Setup deployment environment
./setup_deployment.sh

# 2. Activate virtual environment
source venv/bin/activate

# 3. Deploy
python3 deploy_to_dev.py
```

### Subsequent Deployments

```bash
source venv/bin/activate
python3 deploy_to_dev.py
```

## Dev Machine Info

- **Host:** 192.168.86.74
- **User:** paul
- **Password:** amdisthebest
- **Project Path:** /home/paul/Projects/git/talk-llama-fast

## SSH Access

```bash
ssh paul@192.168.86.74
# Password: amdisthebest

cd /home/paul/Projects/git/talk-llama-fast
```

## Files Synced

The deployment script syncs:
- ✅ Test harness (`tests/`)
- ✅ TTS socket files (`tts-socket.*`, `tts-request.*`)
- ✅ Updated `talk-llama.cpp`
- ✅ GitHub workflows (`.github/`)

## What Gets Built

1. **Dependencies installed:**
   - libcjson-dev (for TTS socket JSON)
   - libsdl2-dev (for audio)
   - libcurl4-openssl-dev (for networking)

2. **Build process:**
   ```bash
   cmake -B build -DWHISPER_SDL2=ON
   cmake --build build -j$(nproc)
   ```

3. **Tests run:**
   ```bash
   ./tests/setup.sh
   python3 tests/run_tests.py --group smoke -v
   ```

## Troubleshooting

### Cannot connect to dev machine
```bash
# Test connectivity
ping 192.168.86.74

# Test SSH
ssh paul@192.168.86.74 whoami
```

### Python venv issues
```bash
# Remove and recreate
rm -rf venv
./setup_deployment.sh
```

### Build fails on dev machine
```bash
# SSH to dev machine and check logs
ssh paul@192.168.86.74
cd /home/paul/Projects/git/talk-llama-fast
cat build/CMakeFiles/CMakeError.log
```

### Tests fail
```bash
# SSH and run tests manually with verbose output
ssh paul@192.168.86.74
cd /home/paul/Projects/git/talk-llama-fast
python3 tests/run_tests.py --group smoke -v
```

## Project Structure After Deployment

```
/home/paul/Projects/git/talk-llama-fast/
├── build/
│   └── bin/
│       ├── talk-llama          ← Main binary
│       └── main                ← Whisper binary
├── examples/talk-llama/
│   ├── talk-llama.cpp          ← With TTS socket + test mode
│   ├── tts-socket.{h,c}        ← Socket communication
│   └── tts-request.{h,c}       ← Wyoming protocol
├── tests/
│   ├── audio_generator.py
│   ├── audio_verifier.py
│   ├── run_tests.py
│   ├── test_cases.yaml
│   └── setup.sh
└── models/
    ├── ggml-base.en.bin        ← Whisper model
    └── ggml-llama-7B.bin       ← LLaMA model
```

## Running on Dev Machine

### Via SSH Command
```bash
ssh paul@192.168.86.74 "cd /home/paul/Projects/git/talk-llama-fast && ./build/bin/talk-llama -mw models/ggml-base.en.bin -ml models/ggml-llama-7B.bin"
```

### Interactive Session
```bash
ssh paul@192.168.86.74
cd /home/paul/Projects/git/talk-llama-fast

# Run normally
./build/bin/talk-llama -mw models/ggml-base.en.bin -ml models/ggml-llama-7B.bin

# Run with test input
./build/bin/talk-llama --test-input tests/audio/inputs/greeting.wav -mw models/ggml-base.en.bin -ml models/ggml-llama-7B.bin
```

## Wyoming-Piper Integration

Make sure Wyoming-Piper is running on dev machine (port 10200):

```bash
ssh paul@192.168.86.74

# Check if running
ps aux | grep piper

# If not running, start it
# (Use your specific Wyoming-Piper command)
```

## Full Workflow Example

```bash
# 1. Make changes locally in your editor

# 2. Deploy to dev machine
./deploy.sh

# 3. SSH to dev machine (if tests passed)
ssh paul@192.168.86.74

# 4. Run the application
cd /home/paul/Projects/git/talk-llama-fast
./build/bin/talk-llama -mw models/ggml-base.en.bin -ml models/ggml-llama-7B.bin
```

## Security Note

⚠️ **Files containing credentials:**
- `DEV_SETUP.md`
- `deploy_to_dev.py`
- `setup_deployment.sh`
- `deploy.sh`
- `DEPLOY_README.md` (this file)

These are in `.gitignore` and should **NOT** be committed to version control.
