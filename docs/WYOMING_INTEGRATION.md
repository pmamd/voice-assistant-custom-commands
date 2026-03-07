# Wyoming-Piper Integration for Tool System

## Overview

This document describes the final step needed to complete the tool calling system: updating Wyoming-Piper to properly handle stop commands sent via the Wyoming protocol instead of relying on hardcoded text detection.

## Current Implementation (Problematic)

**File**: `wyoming-piper/wyoming_piper/handler.py` (Lines 59-77)

The current implementation uses hardcoded text detection:

```python
# CURRENT PROBLEMATIC CODE (to be removed)
if ("stop" in raw_text.lower()) and (len(raw_text) < 10):
    _LOGGER.debug(f"Detected STOP command in text: {raw_text}")

    for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
        try:
            if aplay_proc.proc.returncode is None:
                aplay_proc.proc.terminate()
                ACTIVE_APLAY_PROCESSES.remove(aplay_proc)
                _LOGGER.debug(f"Terminated aplay process: {aplay_proc.proc.pid}")
        except Exception as e:
            _LOGGER.warning(f"Error terminating aplay: {e}")

    # Send empty audio response to acknowledge stop
    await self.write_event(AudioStop().event())
    return
```

**Problems**:
1. **Inflexible**: Hardcoded "stop" keyword
2. **Error-prone**: Can trigger on legitimate text containing "stop" (e.g., "Don't stop at the gas station")
3. **Unmaintainable**: Requires code changes to add new fast-path commands
4. **Bypasses Protocol**: Doesn't use proper Wyoming event system

## Proposed Implementation (Clean)

### Option 1: Wyoming Protocol Stop Event (Preferred)

Modify `handler.py` to handle explicit stop events:

```python
# In PiperEventHandler class

async def handle_event(self, event: Event) -> bool:
    """Handle incoming Wyoming protocol events"""

    # Handle TTS stop events
    if event.type == "tts-stop":
        _LOGGER.debug("Received TTS stop event from client")

        # Terminate all active aplay processes
        for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
            try:
                if aplay_proc.proc.returncode is None:
                    aplay_proc.proc.terminate()
                    ACTIVE_APLAY_PROCESSES.remove(aplay_proc)
                    _LOGGER.debug(f"Terminated aplay process: {aplay_proc.proc.pid}")
            except Exception as e:
                _LOGGER.warning(f"Error terminating aplay: {e}")

        # Send acknowledgment
        await self.write_event(AudioStop().event())
        return True

    # Handle normal synthesis events
    if Synthesize.is_type(event.type):
        synthesize = Synthesize.from_event(event)

        # Remove old hardcoded stop detection here
        raw_text = synthesize.text

        # Normal synthesis flow continues...
        _LOGGER.debug("Synthesizing: %s", raw_text)
        # ...

    return True
```

**Pros**:
- Clean protocol separation
- Extensible to other Wyoming events
- No text parsing hacks

**Cons**:
- Requires Wyoming protocol extension (custom event type)

### Option 2: Special Text Marker (Simpler, Backwards Compatible)

Keep text-based approach but make it explicit:

```python
async def handle_event(self, event: Event) -> bool:
    if Synthesize.is_type(event.type):
        synthesize = Synthesize.from_event(event)
        raw_text = synthesize.text

        # Check for special command markers
        if raw_text.strip() == "__STOP__":
            _LOGGER.debug("Received STOP command via special marker")

            for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
                try:
                    if aplay_proc.proc.returncode is None:
                        aplay_proc.proc.terminate()
                        ACTIVE_APLAY_PROCESSES.remove(aplay_proc)
                except Exception as e:
                    _LOGGER.warning(f"Error terminating aplay: {e}")

            await self.write_event(AudioStop().event())
            return True

        # Normal synthesis
        _LOGGER.debug("Synthesizing: %s", raw_text)
        # ...
```

Update `tool-system.cpp` to send marker:

```cpp
ToolResult stop_speaking(const json& args) {
    // This will be sent to Wyoming-Piper as special marker
    fprintf(stdout, "[Tool] stop_speaking executed (will send __STOP__)\n");
    return ToolResult(true, "Stopping speech");
}
```

Update `wyoming-client.cpp`:

```cpp
bool WyomingClient::sendStop(const std::string& voice, const std::string& language) {
    try {
        fprintf(stdout, "[Wyoming Client] Sending stop marker\n");
        send_tts_async("__STOP__", voice, language, base_url_, 0, false);
        return true;
    } catch (...) {
        fprintf(stderr, "[Wyoming Client] Failed to send stop command\n");
        return false;
    }
}
```

**Pros**:
- Simple implementation
- No Wyoming protocol changes
- Backwards compatible
- Won't false-trigger on user text

**Cons**:
- Still uses text channel for commands (less clean)

## Recommended Approach

**Use Option 2 (Special Marker)** for initial implementation because:

1. **Simplest**: No Wyoming protocol modifications needed
2. **Safe**: `__STOP__` won't appear in natural user text
3. **Tested Path**: Uses existing `send_tts_async` infrastructure
4. **Extensible**: Can add more markers (`__PAUSE__`, `__RESUME__`, etc.)

Later, migrate to Option 1 (Protocol Events) for production.

## Implementation Steps

### Step 1: Update Wyoming-Piper Handler

**File**: `wyoming-piper/wyoming_piper/handler.py`

**Line 59-77**: Replace with:

```python
async def handle_event(self, event: Event) -> bool:
    if Synthesize.is_type(event.type):
        synthesize = Synthesize.from_event(event)
        raw_text = synthesize.text

        # Handle special command markers from tool system
        if raw_text.strip() == "__STOP__":
            _LOGGER.debug("Received STOP command marker from tool system")

            # Terminate all active aplay processes
            for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
                try:
                    if aplay_proc.proc.returncode is None:
                        aplay_proc.proc.terminate()
                        ACTIVE_APLAY_PROCESSES.remove(aplay_proc)
                        _LOGGER.debug(f"Terminated aplay process: {aplay_proc.proc.pid}")
                except Exception as e:
                    _LOGGER.warning(f"Error terminating aplay: {e}")

            # Send acknowledgment
            await self.write_event(AudioStop().event())
            return True

        elif raw_text.strip() == "__PAUSE__":
            # Future: pause playback
            _LOGGER.debug("Received PAUSE command marker")
            return True

        elif raw_text.strip() == "__RESUME__":
            # Future: resume playback
            _LOGGER.debug("Received RESUME command marker")
            return True

        # Normal synthesis
        _LOGGER.debug("Synthesizing: %s", raw_text)

        # ... rest of synthesis code ...
```

### Step 2: Update wyoming-client.cpp

**File**: `custom/talk-llama/wyoming-client.cpp`

Update `sendStop`:

```cpp
bool WyomingClient::sendStop(const std::string& voice, const std::string& language) {
    try {
        fprintf(stdout, "[Wyoming Client] Sending __STOP__ marker\n");
        send_tts_async("__STOP__", voice, language, base_url_, 0, false);
        return true;
    } catch (...) {
        fprintf(stderr, "[Wyoming Client] Failed to send stop command\n");
        return false;
    }
}
```

### Step 3: Update stop_speaking Executor

**File**: `custom/talk-llama/tool-system.cpp`

Current implementation already correct (uses Wyoming client):

```cpp
ToolResult stop_speaking(const json& args) {
    fprintf(stdout, "[Tool] stop_speaking executed\n");
    return ToolResult(true, "Stopping speech");
}
```

The actual stop is sent in talk-llama.cpp when handling the tool result.

### Step 4: Test

**On Dev Machine**:

```bash
# Rebuild talk-llama
cd ~/Projects/git/talk-llama-fast
cmake --build build -j

# Restart Wyoming-Piper with updated handler
# (if running as service)
sudo systemctl restart wyoming-piper

# Or manually
cd wyoming-piper
python3 -m wyoming_piper \
    --piper /usr/local/bin/piper \
    --voice en_US-lessac-medium \
    --port 10200

# Run talk-llama
./build/bin/talk-llama-custom \
    -m models/mistral-7b.gguf \
    --model-whisper models/ggml-base.en.bin

# Test: Say "stop" while assistant is speaking
# Expected:
#   - [Fast Path Tool: stop_speaking]
#   - [Wyoming Client] Sending __STOP__ marker
#   - Wyoming-Piper logs: "Received STOP command marker from tool system"
#   - Audio playback stops immediately
```

### Step 5: Verify Logs

**Wyoming-Piper logs**:
```
DEBUG:wyoming_piper.handler:Received STOP command marker from tool system
DEBUG:wyoming_piper.handler:Terminated aplay process: 12345
```

**talk-llama logs**:
```
[Fast Path Tool: stop_speaking]
[Wyoming Client] Sending __STOP__ marker
Stopped speaking
```

## Testing Scenarios

### Test 1: Fast Path Stop
```
User: "stop"
Expected: Immediate stop via fast path, no LLaMA processing
```

### Test 2: Stop During Long Response
```
User: "tell me a long story"
Assistant: "Once upon a time in a land far away there was..."
User: "stop"
Expected: Story cuts off immediately
```

### Test 3: No False Positives
```
User: "don't stop at the gas station"
Expected: Normal TTS, no stop triggered
```

### Test 4: Tool-Driven Stop
```
User: "stop talking and set temperature to 70"
Expected:
  - LLaMA generates: <tool_call>{"name":"stop_speaking",...}</tool_call><tool_call>{"name":"set_temperature","arguments":{"value":70},...}</tool_call>
  - Both tools execute
  - No further speech
```

## Future Extensions

### Additional Command Markers

Add to `handler.py`:

```python
COMMAND_MARKERS = {
    "__STOP__": handle_stop,
    "__PAUSE__": handle_pause,
    "__RESUME__": handle_resume,
    "__FASTER__": handle_speed_up,
    "__SLOWER__": handle_speed_down,
    "__LOUDER__": handle_volume_up,
    "__QUIETER__": handle_volume_down,
}

async def handle_event(self, event: Event) -> bool:
    if Synthesize.is_type(event.type):
        raw_text = synthesize.text.strip()

        # Check for command markers
        if raw_text in COMMAND_MARKERS:
            await COMMAND_MARKERS[raw_text](self)
            return True

        # Normal synthesis...
```

### Wyoming Protocol Extension (Future)

Define custom event types:

```python
# wyoming_protocol_extension.py
from dataclasses import dataclass
from wyoming.event import Event

@dataclass
class TTSControl(Event):
    """Custom control event for TTS"""
    action: str  # stop, pause, resume, faster, slower

    @staticmethod
    def is_type(event_type: str) -> bool:
        return event_type == "tts-control"

    def event(self) -> Event:
        return Event(
            type="tts-control",
            data={"action": self.action}
        )
```

Update client to send proper events:

```cpp
// In future wyoming-client.cpp with protocol support
bool WyomingClient::sendControl(const std::string& action) {
    json event = {
        {"type", "tts-control"},
        {"data", {{"action", action}}}
    };

    // Send JSON event over Wyoming websocket/TCP connection
    return sendWyomingEvent(event);
}
```

## Troubleshooting

### Stop Not Working

**Check 1**: Verify `__STOP__` is being sent
```bash
# Add debug print in send_tts_async
# Check network traffic
tcpdump -i lo port 10200 -A | grep STOP
```

**Check 2**: Verify Wyoming-Piper receives it
```bash
# Check Wyoming-Piper logs
journalctl -u wyoming-piper -f | grep STOP
```

**Check 3**: Verify aplay processes exist
```bash
ps aux | grep aplay
```

### Stop Too Slow

**Cause**: Network latency or aplay buffering

**Fix**:
- Reduce aplay buffer size in handler.py
- Use UDP instead of TCP for low-latency
- Implement direct signal to aplay process

### Multiple Stops Queueing

**Cause**: Tool system sending multiple __STOP__ markers

**Fix**: Add debouncing in tool system:

```cpp
static auto last_stop_time = std::chrono::steady_clock::now();
auto now = std::chrono::steady_clock::now();
auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - last_stop_time).count();

if (elapsed < 500) { // Debounce 500ms
    return ToolResult(true, "Stop already sent recently");
}
last_stop_time = now;
```

## Related Files

- `wyoming-piper/wyoming_piper/handler.py` - Main handler (needs modification)
- `custom/talk-llama/wyoming-client.cpp` - Client sending __STOP__
- `custom/talk-llama/tool-system.cpp` - stop_speaking executor

## Summary

1. **Current**: Hardcoded "stop" text detection (unreliable)
2. **Proposed**: Special marker `__STOP__` (simple, safe)
3. **Future**: Wyoming protocol events (clean, extensible)

The special marker approach provides an immediate working solution while keeping the door open for a cleaner protocol-based implementation later.
