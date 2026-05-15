# Wyoming-Piper Custom Modifications

This is a custom fork of Wyoming-Piper with support for custom commands and test mode, packaged as **wyoming-piper-custom** to avoid conflicts with standard wyoming-piper installations.

## Base Version

- **Upstream**: https://github.com/rhasspy/wyoming-piper
- **Original base commit**: `21f9966dcc60f59512f5e49ef831f8e30b0f3b77`
- **Status**: Now maintained as regular files in this repository (converted from submodule in Feb 2026)

## Repository Structure

This directory (`wyoming-piper/`) contains the complete Wyoming-Piper codebase with custom modifications already applied. It is **not** a git submodule - all files are tracked directly in the main repository.

**Modified files**:
- `wyoming_piper/__main__.py` - Main entry point with test mode arguments
- `wyoming_piper/handler.py` - Event handler with stop command and test mode
- `wyoming_piper/process.py` - Process manager with aplay support
- `pyproject.toml` - Package renamed to "wyoming-piper-custom"
- `wyoming_piper/__init__.py` - Version string updated for custom package

**Unmodified files**: All other Wyoming-Piper files remain as-is from upstream.

## Key Modifications

### 1. Package Naming (`pyproject.toml`, `__init__.py`)

**Added in**: Feb 2026 for isolation

**Purpose**: Allow wyoming-piper-custom to coexist with standard wyoming-piper installation.

**Changes in `pyproject.toml`**:
```toml
[project]
name = "wyoming-piper-custom"  # Changed from "wyoming-piper"
version = "2.2.2"

[project.scripts]
wyoming-piper-custom = "wyoming_piper.__main__:run"  # Changed command name
```

**Changes in `__init__.py`**:
```python
# Fallback to handle both package names
try:
    __version__ = version("wyoming-piper-custom")
except:
    __version__ = version("wyoming-piper")
```

**Result**: Installs as separate package/command, preventing conflicts.

### 2. Reduced Logging Verbosity (`__main__.py`)

**Added in**: Feb 2026 for cleaner output

**Purpose**: Reduce log spam in production use.

**Changes**:
```python
# Line 103: Changed default log level from INFO to WARNING
logging.basicConfig(
    level=logging.DEBUG if args.debug else logging.WARNING,
    format=args.log_format
)
```

**Result**: INFO messages no longer clutter logs unless `--debug` is specified.

### 3. Test Mode Support (`__main__.py`, `handler.py`)

**Added in**: Feb 2026 for automated testing

**Purpose**: Enable automated end-to-end testing by saving TTS output to files instead of playing through speakers.

**Changes in `__main__.py`**:
```python
# Lines 70-80: Added test mode arguments
parser.add_argument(
    "--test-mode",
    action="store_true",
    help="Enable test mode: save audio to files instead of playing"
)
parser.add_argument(
    "--test-output-dir",
    type=str,
    default="./tests/audio/outputs",
    help="Directory to save test audio files (default: ./tests/audio/outputs)"
)
```

**Changes in `handler.py`**:
```python
# Lines 42-43: Added test output counter
self.test_output_counter = 0

# Lines 165-185: Test mode logic
if test_mode and test_output_dir:
    # Create output directory
    test_output_dir_path.mkdir(parents=True, exist_ok=True)

    # Save timestamped file
    timestamp = int(time.time())
    self.test_output_counter += 1
    test_output_path = test_output_dir_path / f"output_{timestamp}_{self.test_output_counter}.wav"
    shutil.copy(output_path, test_output_path)

    # Create symlink to latest
    latest_link = test_output_dir_path / "output.wav"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(test_output_path.name)
```

**Result**: TTS output is saved to files for verification instead of being played immediately and deleted.

### 4. Stop Command Detection (`handler.py`)

**Added in**: 2024 for voice interruption

**Purpose**: Enable voice-based interruption of AI speech mid-sentence.

**Changes**:
```python
# Lines 115-121: Stop command detection
if ("stop" in raw_text.lower()) and (len(raw_text) < 10):
    _LOGGER.debug("Saw STOP event")
    STOP_CMD = True
    return True
```

**Result**: Short utterances containing "stop" bypass TTS generation and signal interruption.

### 5. Direct Audio Playback (`handler.py`, `process.py`)

**Added in**: 2024 for lower latency

**Purpose**: Bypass Wyoming protocol audio streaming for direct playback.

**Changes**:
- Added `get_aplay_process()` method in `process.py` to spawn aplay subprocess
- Modified event handler to call aplay directly instead of streaming audio chunks
- Auto-cleanup of temporary WAV files after playback

**Result**: Significantly reduced TTS playback latency.

### 6. Local Wyoming Library Path (`__main__.py`)

**Added in**: 2024 for development

**Purpose**: Development/testing with local Wyoming library modifications.

**Changes**:
```python
# Lines 11-12: Local library path
import sys
sys.path.insert(0, "/home/paul/git/wyoming")
```

**⚠️ NOTE**: This is hardcoded for development and should be removed or made configurable for production.

### 7. Debug Logging Infrastructure (`__main__.py`)

**Added in**: 2024 for troubleshooting

**Purpose**: Easier debugging during development.

**Changes**:
```python
# Lines 23-36: Commented-out logging setup
# _LOGGER.setLevel(logging.DEBUG)
# fh = logging.FileHandler('wyoming_piper.log')
# fh.setLevel(logging.DEBUG)
# ... etc
```

**Result**: Can be easily enabled by uncommenting for verbose debugging.

## Installation

Install using pipx (recommended) or pip:

```bash
# Using install script (recommended)
./install-wyoming.sh

# Or manually with pipx
cd wyoming-piper
pipx install -e .

# Or manually with pip
cd wyoming-piper
pip install -e .
```

**Verify installation**:
```bash
which wyoming-piper-custom
wyoming-piper-custom --version
```

**Important**: The command is `wyoming-piper-custom`, not `wyoming-piper`.

## Usage

### Normal Mode
```bash
wyoming-piper-custom \
    --piper /usr/bin/piper \
    --voice en_US-lessac-medium \
    --uri tcp://0.0.0.0:8020
```

### Test Mode
```bash
wyoming-piper-custom \
    --piper /usr/bin/piper \
    --voice en_US-lessac-medium \
    --uri tcp://0.0.0.0:8020 \
    --test-mode \
    --test-output-dir ./tests/audio/outputs
```

Test mode will:
- Save TTS output to `./tests/audio/outputs/output_<timestamp>_<counter>.wav`
- Create symlink `./tests/audio/outputs/output.wav` → latest file
- Skip audio playback via aplay

### With Debug Logging
```bash
wyoming-piper-custom --debug \
    --piper /usr/bin/piper \
    --voice en_US-lessac-medium \
    --uri tcp://0.0.0.0:8020
```

## Testing

See `../tests/README.md` for complete test harness documentation.

**Quick test**:
```bash
# Start Wyoming-Piper in test mode
wyoming-piper-custom --test-mode --test-output-dir /tmp/test-output \
    --piper /usr/bin/piper --voice en_US-lessac-medium \
    --uri tcp://0.0.0.0:8020 &

# Send test request via talk-llama with --test-input
cd build/bin
./talk-llama-custom --test-input test_audio.wav ...

# Check output
ls -l /tmp/test-output/
ffplay /tmp/test-output/output.wav
```

## Differences from Upstream

To compare with upstream Wyoming-Piper:

```bash
# Clone upstream
git clone https://github.com/rhasspy/wyoming-piper upstream-wyoming-piper
cd upstream-wyoming-piper
git checkout 21f9966dcc60f59512f5e49ef831f8e30b0f3b77

# Compare files
diff -u upstream-wyoming-piper/wyoming_piper/__main__.py wyoming-piper/wyoming_piper/__main__.py
diff -u upstream-wyoming-piper/wyoming_piper/handler.py wyoming-piper/wyoming_piper/handler.py
diff -u upstream-wyoming-piper/wyoming_piper/process.py wyoming-piper/wyoming_piper/process.py
diff -u upstream-wyoming-piper/pyproject.toml wyoming-piper/pyproject.toml
```

## Known Issues

1. **Hardcoded Wyoming Path**: Line 12 of `__main__.py` has hardcoded path `/home/paul/git/wyoming`
   - **Impact**: May cause import errors on other systems
   - **Fix**: Remove or make configurable via environment variable

2. **Global STOP_CMD Flag**: Uses global variable for stop command signaling
   - **Impact**: Not thread-safe for parallel requests
   - **Fix**: Use per-session state or message passing

3. **Stop Command Detection**: Very basic (just checks for "stop" in text < 10 chars)
   - **Impact**: May miss variations or trigger false positives
   - **Fix**: More sophisticated NLP-based detection

## Future Enhancements

- [ ] Make Wyoming library path configurable via environment variable
- [ ] Thread-safe stop command handling
- [ ] Test mode: configurable filename patterns
- [ ] Test mode: optional audio metadata in output filenames
- [ ] Stop command: configurable keywords and length threshold
- [ ] Performance metrics logging (latency, throughput)
- [ ] Upstream merge: Contribute test mode back to upstream Wyoming-Piper

## Version History

- **2.2.2-custom**: Current version
  - Package renamed to wyoming-piper-custom
  - Reduced default logging verbosity (WARNING instead of INFO)
  - Converted from git submodule to regular files in repo

- **2.2.2**: Original upstream version
  - Base commit: 21f9966dcc60f59512f5e49ef831f8e30b0f3b77

## Credits

- **Original Wyoming-Piper**: Rhasspy project (https://github.com/rhasspy/wyoming-piper)
- **Wyoming Protocol**: Rhasspy project (https://github.com/rhasspy/wyoming)
- **Piper TTS**: Rhasspy project (https://github.com/rhasspy/piper)
- **Modifications**: Paul Mobbs (2024-2026)
- **Test Mode Implementation**: Claude Opus 4.6 (2026)
