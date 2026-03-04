# Development Setup Guide

**NOTE: DO NOT RENAME THIS FILE.** This file is referenced in Claude Code's custom summarization instructions and must remain as `DEV_SETUP.md` to ensure proper context restoration after compaction events.

---

This guide will help you set up your development environment and understand the project structure.

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
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    libsdl2-dev \
    libcurl4-openssl-dev \
    libcjson-dev \
    alsa-utils \
    python3 \
    python3-pip \
    pipx
```

## Building the Project

### Local Build

```bash
# Clone with submodules
git clone --recursive https://github.com/YOUR_USERNAME/voice-assistant-custom-commands.git
cd voice-assistant-custom-commands

# Configure
cmake -B build -DWHISPER_SDL2=ON

# Build
cmake --build build -j

# Executable will be at: build/bin/talk-llama-custom
```

### GPU Build (Optional - AMD ROCm)

For AMD GPU acceleration:
```bash
cmake -B build -DWHISPER_SDL2=ON -DGGML_HIPBLAS=ON
cmake --build build -j
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
│       ├── talk-llama.cpp    # Main application with tool system
│       ├── tool-system.cpp   # Tool registry and executors
│       ├── tool-system.h     # Tool framework
│       ├── tool-parser.cpp   # Mistral tool call parser
│       ├── tool-parser.h     # Parser interface
│       ├── wyoming-client.cpp # Wyoming protocol client
│       ├── wyoming-client.h  # Client interface
│       ├── tools/
│       │   └── tools.json    # Tool definitions (12 tools)
│       ├── llama.cpp         # Standalone llama.cpp inference engine
│       ├── llama.h
│       ├── console.cpp       # Console handling
│       ├── console.h
│       ├── unicode.cpp       # Unicode support
│       ├── unicode-data.cpp
│       ├── unicode.h
│       ├── unicode-data.h
│       ├── tts-request.c     # TTS request handling
│       ├── tts-request.h
│       ├── tts-socket.c      # TTS socket communication
│       ├── tts-socket.h
│       └── MODIFICATIONS.md  # Detailed modification notes
├── wyoming-piper/            # Modified Wyoming-Piper TTS server
│   └── wyoming_piper/
│       └── handler.py        # Event handlers (stop/pause/resume)
├── whisper.cpp/              # Upstream whisper.cpp (git submodule)
├── tests/                    # Test infrastructure
│   ├── run_tests.py          # Main test runner
│   ├── run_tool_tests.py     # Tool system test runner
│   ├── test_tool_system.py   # Tool integration tests
│   ├── test_tool_audio.py    # Audio-based tool tests
│   ├── audio_generator.py    # Piper TTS audio generation
│   ├── audio_verifier.py     # Whisper STT verification
│   ├── test_cases.yaml       # Original test specifications
│   ├── test_cases_tool_system.yaml # Tool system test specs (31 tests)
│   ├── TEST_INFRASTRUCTURE.md # Test infrastructure docs
│   ├── README.md             # Test harness overview
│   └── README_TOOL_TESTS.md  # Tool test documentation
├── docs/                     # Additional documentation
├── scripts/                  # Build and utility scripts
├── external/                 # External dependencies (git submodules)
├── CMakeLists.txt            # Root build configuration
├── DEV_SETUP.md              # This file (DO NOT RENAME)
├── README.md                 # User-facing documentation
├── TOOL_SYSTEM_IMPLEMENTATION.md # Tool system architecture
├── TOOL_SYSTEM_TEST_RESULTS.md   # Test results
└── start-assistant.sh        # Launch script
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

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname, username=username)  # Uses SSH key authentication

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
- See `wyoming-piper/MODIFICATIONS.md` for TTS modifications
- See `README.md` for usage instructions

## Making Contributions

### Workflow

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone --recursive https://github.com/YOUR_USERNAME/voice-assistant-custom-commands.git
   cd voice-assistant-custom-commands
   ```
3. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Make your changes** in the appropriate directory:
   - Talk-llama changes: `custom/talk-llama/`
   - Wyoming-Piper changes: `wyoming-piper/wyoming_piper/`
   - Tests: `tests/`
5. **Test thoroughly**:
   ```bash
   # Build
   cmake --build build -j

   # Run tests (if available)
   make test
   ```
6. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Description of your changes"
   ```
7. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
8. **Submit a pull request** on GitHub

### Code Style

- **C/C++**: Follow existing code style in the project
- **Python**: Follow PEP 8
- **Commit messages**: Clear, descriptive messages in imperative mood

### Areas for Contribution

- **Custom commands**: Add more LLM-bypass commands beyond "stop"
- **Test coverage**: Expand test harness with more test cases
- **Documentation**: Improve setup guides and troubleshooting
- **Performance**: Optimize audio processing or TTS latency
- **Platform support**: macOS or Windows compatibility
- **Bug fixes**: Check issues on GitHub

### Documentation

If you add features, please update:
- `README.md` - User-facing documentation
- `MODIFICATIONS.md` - Technical changes in modified files
- Code comments - For complex logic

### Questions?

Open an issue on GitHub for:
- Feature requests
- Bug reports
- Setup help
- General questions
