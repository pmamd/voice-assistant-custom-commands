# Build Scripts

Utility scripts for building project dependencies.

## build_piper.sh

Builds Piper TTS from the git submodule for a self-contained setup.

**Usage:**
```bash
./scripts/build_piper.sh
```

**What it does:**
1. Creates Python virtual environment at `external/piper/.venv`
2. Installs Piper and its dependencies
3. Builds the C extension for espeak-ng integration
4. Creates executable at `external/piper/.venv/bin/piper`

**Requirements:**
- Python 3.8+
- cmake
- build-essential
- ninja-build (recommended)

**After building:**
```bash
# Test it works
external/piper/.venv/bin/piper --help

# Or activate venv
source external/piper/.venv/bin/activate
python3 -m piper --help
```

**Use in tests:**
Update `test_cases.yaml`:
```yaml
config:
  audio_generator:
    piper_bin: "../external/piper/.venv/bin/piper"
```
