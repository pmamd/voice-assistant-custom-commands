# Wyoming-Piper Modifications

This is a modified version of [wyoming-piper](https://github.com/rhasspy/wyoming-piper) with custom command support.

## Base Version

- **Upstream**: https://github.com/rhasspy/wyoming-piper
- **Base commit**: `21f9966dcc60f59512f5e49ef831f8e30b0f3b77`
- **Date**: 2024

## Modifications

### 1. Direct Audio Playback (`__main__.py`, `handler.py`, `process.py`)

**Why**: Bypassed Wyoming protocol audio streaming to use direct `aplay` playback for lower latency.

**Changes**:
- Added `get_aplay_process()` method to spawn aplay subprocess
- Modified event handler to call aplay directly instead of streaming audio chunks
- Auto-cleanup of temporary WAV files after playback

### 2. Stop Command Detection (`handler.py`)

**Why**: Enable voice-based interruption of AI speech.

**Changes**:
- Added global `STOP_CMD` flag
- Check for "stop" keyword in short text (<10 chars) before synthesis
- Early return if stop command detected

### 3. Debug Logging Infrastructure (`__main__.py`, `handler.py`)

**Why**: Easier troubleshooting during development.

**Changes**:
- Added commented-out logging configuration
- Added event serialization debug output
- Can be enabled by uncommenting

### 4. Local Wyoming Library Path (`__main__.py`)

**Why**: Development/testing with local Wyoming library modifications.

**Changes**:
- Added `sys.path.insert(0, "/home/paul/git/wyoming")` for local library
- **NOTE**: This is hardcoded and should be removed or made configurable for production

## Files Modified

- `wyoming_piper/__main__.py` - Added local Wyoming path, debug logging setup
- `wyoming_piper/handler.py` - Stop detection, aplay integration, debug output
- `wyoming_piper/process.py` - Added `AplayProcess` class and `get_aplay_process()` method

## How It Works

### Normal Flow (Without Stop):
1. Receive TTS request via Wyoming protocol
2. Check text for stop command
3. If not stop: Generate speech with Piper
4. Write WAV to temp file
5. Play with aplay subprocess
6. Delete temp file when done

### Stop Command Flow:
1. Receive TTS request with "stop" in text
2. Detect stop command (text contains "stop" and length < 10)
3. Set `STOP_CMD = True`
4. Return early (no synthesis or playback)

## Known Issues

1. **Hardcoded path**: `/home/paul/git/wyoming` - needs to be configurable
2. **Stop detection is basic**: Simple string matching, could be improved
3. **No graceful interrupt**: aplay subprocess waits for completion (interrupt logic commented out)
4. **Platform-specific**: Uses Linux `aplay` command

## Future Improvements

- [ ] Make Wyoming library path configurable via environment variable
- [ ] Implement proper aplay process interruption
- [ ] Add more sophisticated command detection (regex, multiple keywords)
- [ ] Make audio backend pluggable (not just aplay)
- [ ] Add command acknowledgment/feedback
- [ ] Support for multiple simultaneous commands

## Reverting to Upstream

To revert to standard Wyoming-Piper:

```bash
git remote add upstream https://github.com/rhasspy/wyoming-piper.git
git fetch upstream
git checkout upstream/master
```

Or start fresh:
```bash
pip install wyoming-piper
```

## Testing

Test stop command:
```bash
# Start server
python3 -m wyoming_piper --uri tcp://0.0.0.0:8020 --voice en_US-lessac-medium

# In another terminal, send stop command
curl -X POST http://localhost:8020/tts_to_audio/ \
  -H "Content-Type: application/json" \
  -d '{"text":"stop","language":"en","speaker_wav":"emma_1"}'

# Should see in logs: "Saw STOP event"
```

Test normal synthesis:
```bash
curl -X POST http://localhost:8020/tts_to_audio/ \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello, this is a test.","language":"en","speaker_wav":"emma_1"}'

# Should hear audio playback
```
