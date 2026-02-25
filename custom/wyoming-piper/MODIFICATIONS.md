# Wyoming-Piper Custom Modifications

This directory contains modified Wyoming-Piper files with custom command support and test mode.

## Base Version

- **Upstream**: https://github.com/rhasspy/wyoming-piper (included as submodule)
- **Base commit**: `21f9966dcc60f59512f5e49ef831f8e30b0f3b77`
- **Date**: 2024

## Files

### Custom Files (This Directory)
- **`__main__.py`** - Modified main entry point with test mode arguments
- **`handler.py`** - Modified event handler with stop command and test mode
- **`process.py`** - Modified process manager with aplay support for local audio playback

### Upstream Files (From Submodule)
All other files are used unmodified from the wyoming-piper submodule.

## Key Modifications

### 1. Test Mode Support (`__main__.py`, `handler.py`)

**Added in**: 2026-02 for automated testing

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

### 2. Stop Command Detection (`handler.py`)

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

### 3. Direct Audio Playback (`handler.py`, `process.py`)

**Added in**: 2024 for lower latency

**Purpose**: Bypass Wyoming protocol audio streaming for direct playback.

**Changes**:
- Added `get_aplay_process()` method in `process.py` to spawn aplay subprocess
- Modified event handler to call aplay directly instead of streaming audio chunks
- Auto-cleanup of temporary WAV files after playback

**Result**: Significantly reduced TTS playback latency.

### 4. Local Wyoming Library Path (`__main__.py`)

**Added in**: 2024 for development

**Purpose**: Development/testing with local Wyoming library modifications.

**Changes**:
```python
# Lines 11-12: Local library path
import sys
sys.path.insert(0, "/home/paul/git/wyoming")
```

**⚠️ NOTE**: This is hardcoded for development and should be removed or made configurable for production.

### 5. Debug Logging Infrastructure (`__main__.py`)

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

These custom files need to be installed over the base Wyoming-Piper installation:

### Option 1: Direct Overlay (Development)
```bash
# Install base Wyoming-Piper
cd wyoming-piper
pip install -e .

# Overlay custom files
cp custom/wyoming-piper/__main__.py wyoming-piper/wyoming_piper/
cp custom/wyoming-piper/handler.py wyoming-piper/wyoming_piper/
cp custom/wyoming-piper/process.py wyoming-piper/wyoming_piper/
```

### Option 2: Build Script (Production)
```bash
# CMakeLists.txt or install script handles overlay automatically
cmake --build build --target install-wyoming-piper
```

## Usage

### Normal Mode
```bash
wyoming-piper \
    --piper ./piper/piper \
    --voice en_US-lessac-medium \
    --data-dir ./piper-voices \
    --uri tcp://0.0.0.0:10200
```

### Test Mode
```bash
wyoming-piper \
    --piper ./piper/piper \
    --voice en_US-lessac-medium \
    --data-dir ./piper-voices \
    --uri tcp://0.0.0.0:10200 \
    --test-mode \
    --test-output-dir ./tests/audio/outputs
```

Test mode will:
- Save TTS output to `./tests/audio/outputs/output_<timestamp>_<counter>.wav`
- Create symlink `./tests/audio/outputs/output.wav` → latest file
- Skip audio playback via aplay

## Testing

See `tests/README.md` for complete test harness documentation.

**Quick test**:
```bash
# Start Wyoming-Piper in test mode
wyoming-piper --test-mode --test-output-dir /tmp/test-output \
    --piper ./piper/piper --voice en_US-lessac-medium \
    --data-dir ./piper-voices --uri tcp://0.0.0.0:10200 &

# Send test request (requires Wyoming client)
echo '{"text": "Hello world"}' | \
    wyoming-client tcp://localhost:10200

# Check output
ls -l /tmp/test-output/
ffplay /tmp/test-output/output.wav
```

## Differences from Upstream

To see what's different from base Wyoming-Piper:

```bash
# Compare __main__.py
diff -u wyoming-piper/wyoming_piper/__main__.py custom/wyoming-piper/__main__.py

# Compare handler.py
diff -u wyoming-piper/wyoming_piper/handler.py custom/wyoming-piper/handler.py
```

## Known Issues

1. **Hardcoded Wyoming Path**: Line 12 of `__main__.py` has hardcoded path `/home/paul/git/wyoming`
   - **Impact**: May cause import errors on other systems
   - **Fix**: Remove or make configurable via environment variable

2. **Global STOP_CMD Flag**: Uses global variable for stop command signaling
   - **Impact**: Not thread-safe for parallel requests
   - **Fix**: Use per-session state or message passing

## Future Enhancements

- [ ] Make Wyoming library path configurable via environment variable
- [ ] Thread-safe stop command handling
- [ ] Test mode: configurable filename patterns
- [ ] Test mode: optional audio metadata in output filenames
- [ ] Stop command: configurable keywords and length threshold
- [ ] Performance metrics logging (latency, throughput)

## Credits

- **Original Wyoming-Piper**: Rhasspy project (https://github.com/rhasspy/wyoming-piper)
- **Modifications**: Paul Mobbs (2024-2026)
- **Test Mode Implementation**: Claude Opus 4.6 (2026)
