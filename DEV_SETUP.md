# Development Environment Setup

This document describes how to set up your development environment for working on this project.

## Prerequisites

### System Dependencies

- **CMake** (>= 3.12)
- **SDL2** development libraries
- **CURL** development libraries
- **Git**
- **Python 3** (for build/test scripts)

Install on Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install -y cmake libsdl2-dev libcurl4-openssl-dev git python3 python3-venv build-essential ninja-build
```

### For Piper TTS (optional - only if building from submodule)
```bash
sudo apt-get install -y build-essential cmake ninja-build
```

## WSL Python Environment

The build and deployment scripts use Python with SSH/SFTP capabilities. Since WSL uses an externally-managed Python environment, you need to use a virtual environment.

### Create and Activate Virtual Environment

```bash
# Create virtual environment (one-time setup)
cd /tmp
python3 -m venv build-venv

# Activate virtual environment
source /tmp/build-venv/bin/activate

# Install required packages
pip install paramiko
```

### Using the Scripts

Always activate the venv before running build/test scripts:

```bash
# Activate venv
source /tmp/build-venv/bin/activate

# Run your script
python3 /tmp/test_build_fixed.py

# Deactivate when done (optional)
deactivate
```

## Building the Project

### Local Build

```bash
# Clone with submodules
git clone --recursive https://github.com/pmamd/voice-assistant-custom-commands-clean.git
cd voice-assistant-custom-commands-clean

# Configure
cmake -B build -DWHISPER_SDL2=ON

# Build
cmake --build build -j

# Executable will be at: build/bin/talk-llama-custom
```

### Remote Build (Development Machine)

Use the provided Python scripts in `/tmp/` to test builds on the remote development machine:

```bash
# Make sure venv is activated
source /tmp/build-venv/bin/activate

# Run build test
python3 /tmp/test_build_fixed.py
```

## Git Submodules

This project uses git submodules for whisper.cpp and Piper TTS.

### Initialize submodules after cloning:
```bash
git submodule update --init --recursive
```

### Building Piper TTS (Optional - for self-contained setup)

The project includes Piper TTS as a submodule. You can build it locally for a fully self-contained setup:

```bash
# Build Piper from submodule
./scripts/build_piper.sh
```

This creates a Python virtual environment at `external/piper/.venv` with Piper installed.

**Using the built Piper:**
```bash
# Direct execution
external/piper/.venv/bin/piper --help

# Or activate venv
source external/piper/.venv/bin/activate
python3 -m piper --help
```

**Update test configuration** (test_cases.yaml):
```yaml
config:
  audio_generator:
    piper_bin: "./external/piper/.venv/bin/piper"
    model_dir: "./external/piper-voices"  # Download voices separately
```

### Update submodule to latest upstream:
```bash
cd whisper.cpp
git checkout d207c6882247984689091ae9d780d2e51eab1df7
cd ..
git add whisper.cpp
git commit -m "Update whisper.cpp submodule"
```

## Project Structure

```
.
├── custom/
│   └── talk-llama/           # Custom modified talk-llama files
│       ├── talk-llama.cpp    # Main application (CURL-based TTS)
│       ├── llama.cpp         # Standalone llama.cpp inference engine
│       ├── llama.h
│       ├── console.cpp
│       ├── console.h
│       ├── unicode.cpp
│       ├── unicode-data.cpp
│       ├── unicode.h
│       ├── unicode-data.h
│       └── MODIFICATIONS.md  # Detailed modification notes
├── wyoming-piper/            # Modified Wyoming-Piper TTS server
├── whisper.cpp/              # Upstream whisper.cpp (git submodule)
├── CMakeLists.txt            # Root build configuration
└── DEV_SETUP.md             # This file
```

## Common Issues

### SDL2 Not Found
```
CMake Error: Could NOT find SDL2
```
**Solution**: Install SDL2 development package
```bash
sudo apt-get install libsdl2-dev
```

### Wrong llama.h Found
```
error: 'llama_eval' was not declared in this scope
```
**Solution**: This is fixed in CMakeLists.txt by using `BEFORE PRIVATE` in include directories to prioritize local headers over system headers.

### Multiple Definition Errors
If you see errors like:
```
multiple definition of 'console::init(bool, bool)'
```
**Solution**: Make sure `console.cpp` is NOT `#include`d in talk-llama.cpp. It should only be listed in CMakeLists.txt as a separate source file.

## Testing

**IMPORTANT**: All tests must be run on the development machine (192.168.86.74), not on WSL. The dev machine has Piper TTS, models, and all required dependencies installed.

### Running Tests on Dev Machine

**From WSL**, use the Python venv with paramiko to execute commands on the dev machine:

```bash
# Activate venv (required for paramiko)
source /tmp/build-venv/bin/activate

# Use Python scripts with paramiko to run tests remotely
# Example script structure:
import paramiko

hostname = "192.168.86.74"
username = "paul"
password = "amdisthebest"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname, username=username, password=password)

# Execute test commands
stdin, stdout, stderr = client.exec_command(
    "cd ~/Projects/git/talk-llama-fast/tests && python3 run_tests.py --config test_cases.yaml --group smoke"
)
print(stdout.read().decode())
client.close()
```

**Do NOT use direct SSH commands** - always use paramiko from the venv as shown above.

### Manual Testing

After building, test the executable:

```bash
# Check help output
./build/bin/talk-llama-custom --help

# Run with models (requires model files)
./build/bin/talk-llama-custom \
  -m /path/to/llama-model.gguf \
  --model-whisper /path/to/whisper-model.bin
```

## Next Steps

- See `custom/talk-llama/MODIFICATIONS.md` for details on code modifications
- See `README.md` for usage instructions
- See Wyoming-Piper documentation for TTS server setup
