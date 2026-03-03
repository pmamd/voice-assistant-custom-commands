# Wyoming Custom Events for Automotive Voice Assistant

## Overview

Beyond the standard Wyoming protocol `audio-stop` event, we can define custom events for real-time TTS control and automotive-specific commands.

## Standard Wyoming Events We Can Use

### 1. audio-stop ✅
**Status**: Standard Wyoming protocol event
**Purpose**: Immediately stop current audio playback
**Implementation**: Already planned for tool system

```json
{"type": "audio-stop", "data": {}, "payload_length": 0}
```

**Wyoming-Piper Handler**:
```python
if AudioStop.is_type(event.type):
    # Kill all aplay processes
    for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
        aplay_proc.proc.terminate()
```

## Custom Events We Should Add

### 2. audio-pause
**Type**: Custom event
**Purpose**: Pause current audio playback (can be resumed)
**Use case**: "Pause for a moment" while taking a call

```json
{"type": "audio-pause", "data": {}, "payload_length": 0}
```

**Wyoming-Piper Handler**:
```python
if event.type == "audio-pause":
    for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
        # Send SIGSTOP to pause aplay
        aplay_proc.proc.send_signal(signal.SIGSTOP)
        aplay_proc.paused = True
```

**Fast Path Tool**:
```json
{
  "name": "pause_speaking",
  "description": "Pause current speech (can be resumed)",
  "fast_path": true,
  "keywords": ["pause", "hold on"],
  "parameters": {"type": "object", "properties": {}, "required": []}
}
```

### 3. audio-resume
**Type**: Custom event
**Purpose**: Resume paused audio playback
**Use case**: "Continue" or "go ahead" after pausing

```json
{"type": "audio-resume", "data": {}, "payload_length": 0}
```

**Wyoming-Piper Handler**:
```python
if event.type == "audio-resume":
    for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
        if aplay_proc.paused:
            # Send SIGCONT to resume aplay
            aplay_proc.proc.send_signal(signal.SIGCONT)
            aplay_proc.paused = False
```

**Fast Path Tool**:
```json
{
  "name": "resume_speaking",
  "description": "Resume paused speech",
  "fast_path": true,
  "keywords": ["continue", "resume", "go ahead"],
  "parameters": {"type": "object", "properties": {}, "required": []}
}
```

### 4. set-playback-volume
**Type**: Custom event
**Purpose**: Adjust audio playback volume
**Use case**: "Louder" / "Quieter" during speech

```json
{
  "type": "set-playback-volume",
  "data": {
    "level": "louder",  // or "quieter", "normal", or absolute 0-100
    "delta": 10         // optional: adjust by +/- percentage
  },
  "payload_length": 0
}
```

**Wyoming-Piper Handler**:
```python
if event.type == "set-playback-volume":
    level = event.data.get("level")

    if level == "louder":
        # Increase system volume
        subprocess.run(["amixer", "sset", "Master", "10%+"])
    elif level == "quieter":
        subprocess.run(["amixer", "sset", "Master", "10%-"])
    elif level == "normal":
        subprocess.run(["amixer", "sset", "Master", "70%"])
```

**Smart Path Tool** (requires LLM to understand context):
```json
{
  "name": "adjust_volume",
  "description": "Adjust speaking volume during playback",
  "fast_path": false,
  "parameters": {
    "type": "object",
    "properties": {
      "level": {
        "type": "string",
        "enum": ["quieter", "normal", "louder"],
        "description": "Volume adjustment"
      }
    },
    "required": ["level"]
  }
}
```

### 5. set-speech-rate
**Type**: Custom event
**Purpose**: Adjust speaking rate for next synthesis
**Use case**: "Speak faster" / "Slow down"

**Note**: Cannot adjust mid-playback, applies to next synthesis

```json
{
  "type": "set-speech-rate",
  "data": {
    "rate": 1.2  // 0.5 = half speed, 2.0 = double speed
  },
  "payload_length": 0
}
```

**Wyoming-Piper Handler**:
```python
if event.type == "set-speech-rate":
    rate = event.data.get("rate", 1.0)
    # Store in handler state for next synthesis
    self.speech_rate = rate

    # When synthesizing:
    # piper --length_scale {1.0/rate} ...
```

**Smart Path Tool**:
```json
{
  "name": "set_speech_rate",
  "description": "Adjust speaking speed for future responses",
  "fast_path": false,
  "parameters": {
    "type": "object",
    "properties": {
      "rate": {
        "type": "string",
        "enum": ["slower", "normal", "faster"],
        "description": "Speaking rate adjustment"
      }
    },
    "required": ["rate"]
  }
}
```

### 6. change-voice
**Type**: Custom event
**Purpose**: Switch TTS voice for next synthesis
**Use case**: "Use a different voice" / "Switch to Amy"

```json
{
  "type": "change-voice",
  "data": {
    "voice": "en_US-amy-medium"
  },
  "payload_length": 0
}
```

**Wyoming-Piper Handler**:
```python
if event.type == "change-voice":
    voice = event.data.get("voice")
    # Store in handler state for next synthesis
    self.current_voice = voice
```

**Smart Path Tool**:
```json
{
  "name": "change_voice",
  "description": "Switch to a different voice for future responses",
  "fast_path": false,
  "parameters": {
    "type": "object",
    "properties": {
      "voice": {
        "type": "string",
        "enum": ["amy", "lessac", "libritts", "ryan"],
        "description": "Voice name"
      }
    },
    "required": ["voice"]
  }
}
```

### 7. repeat-last
**Type**: Custom event
**Purpose**: Repeat the last utterance
**Use case**: "What was that?" / "Repeat that"

```json
{"type": "repeat-last", "data": {}, "payload_length": 0}
```

**Wyoming-Piper Handler**:
```python
if event.type == "repeat-last":
    if self.last_synthesized_text:
        # Re-synthesize and play last text
        await self._handle_synthesize(self.last_synthesized_text)
```

**Fast Path Tool**:
```json
{
  "name": "repeat_last",
  "description": "Repeat the last thing the assistant said",
  "fast_path": true,
  "keywords": ["repeat", "what", "say that again", "pardon"],
  "parameters": {"type": "object", "properties": {}, "required": []}
}
```

## Summary: Recommended Custom Events

### High Priority (Immediate Use)

| Event | Type | Use Case | Implementation Complexity |
|-------|------|----------|--------------------------|
| **audio-stop** | Standard | Stop speaking | ✅ Simple (already planned) |
| **audio-pause** | Custom | Pause for interruption | ✅ Simple (SIGSTOP to aplay) |
| **audio-resume** | Custom | Resume after pause | ✅ Simple (SIGCONT to aplay) |
| **set-playback-volume** | Custom | Adjust volume | ⚠️ Medium (requires amixer/pactl) |

### Medium Priority (Nice to Have)

| Event | Type | Use Case | Implementation Complexity |
|-------|------|----------|--------------------------|
| **repeat-last** | Custom | Repeat last utterance | ⚠️ Medium (store last text) |
| **set-speech-rate** | Custom | Speak faster/slower | ⚠️ Medium (Piper parameters) |

### Low Priority (Future Enhancement)

| Event | Type | Use Case | Implementation Complexity |
|-------|------|----------|--------------------------|
| **change-voice** | Custom | Switch voices | ⚠️ Medium (voice management) |
| **skip-sentence** | Custom | Skip ahead in speech | ❌ Complex (needs sentence parsing) |

## Implementation Recommendations

### Phase 1: Audio Control (Week 1)
Implement basic playback control:
1. `audio-stop` (standard Wyoming)
2. `audio-pause` (custom)
3. `audio-resume` (custom)

**Tools added to tools.json**:
```json
{
  "tools": [
    {"name": "stop_speaking", "fast_path": true, "keywords": ["stop", "quiet"]},
    {"name": "pause_speaking", "fast_path": true, "keywords": ["pause", "hold on"]},
    {"name": "resume_speaking", "fast_path": true, "keywords": ["continue", "resume"]}
  ]
}
```

### Phase 2: Volume Control (Week 2)
Add volume adjustment:
4. `set-playback-volume` (custom)

**Tool added**:
```json
{
  "name": "adjust_volume",
  "fast_path": false,
  "parameters": {
    "properties": {
      "level": {"enum": ["quieter", "normal", "louder"]}
    }
  }
}
```

### Phase 3: Advanced Features (Future)
Add speech customization:
5. `set-speech-rate`
6. `change-voice`
7. `repeat-last`

## Custom Event Protocol

All custom events follow Wyoming JSON format:

```python
# Sending from talk-llama
{
    "type": "custom-event-name",
    "data": {
        "param1": "value1",
        "param2": "value2"
    },
    "payload_length": 0  # or length of binary payload
}
```

# Receiving in Wyoming-Piper
```python
async def handle_event(self, event: Event) -> bool:
    # Standard events
    if AudioStop.is_type(event.type):
        await handle_audio_stop()

    # Custom events
    elif event.type == "audio-pause":
        await handle_audio_pause()
    elif event.type == "audio-resume":
        await handle_audio_resume()
    elif event.type == "set-playback-volume":
        await handle_volume_change(event.data)
```

## Testing Custom Events

### Test 1: Audio Pause/Resume
```bash
# Pause
python3 -c "
import socket, json
s = socket.socket()
s.connect(('127.0.0.1', 10200))
s.send((json.dumps({'type': 'audio-pause', 'data': {}}) + '\n').encode())
s.close()
"

# Resume
python3 -c "
import socket, json
s = socket.socket()
s.connect(('127.0.0.1', 10200))
s.send((json.dumps({'type': 'audio-resume', 'data': {}}) + '\n').encode())
s.close()
"
```

### Test 2: Volume Control
```bash
python3 -c "
import socket, json
s = socket.socket()
s.connect(('127.0.0.1', 10200))
event = {'type': 'set-playback-volume', 'data': {'level': 'louder'}}
s.send((json.dumps(event) + '\n').encode())
s.close()
"
```

## Benefits of Custom Events

✅ **Protocol compliant** - Wyoming supports custom events
✅ **Extensible** - Easy to add new commands
✅ **Testable** - Can test independently of LLM
✅ **Future-proof** - Can contribute back to Wyoming ecosystem
✅ **Clean separation** - Control plane vs data plane

## Alternative: Direct Tool Execution

For **automotive-specific tools** (temperature, navigation, etc.), we don't need Wyoming events at all:

**Vehicle Control Tools** → Execute directly in tool executor → Send CAN bus / API commands

**Voice Assistant Control Tools** → Send Wyoming custom events → Wyoming-Piper handles

**Example**:
```cpp
if (call.name == "stop_speaking") {
    // Send Wyoming event
    wyoming_client.sendAudioStop();
}
else if (call.name == "set_temperature") {
    // Execute directly (CAN bus, etc.)
    send_can_command(0x3E3, temperature_data);
}
```

## Conclusion

**Wyoming can handle**:
- ✅ `audio-stop` (standard event)
- ✅ Any custom events we define (pause, resume, volume, etc.)

**Wyoming cannot handle** (not designed for):
- ❌ Vehicle-specific commands (temperature, navigation, etc.)
- ❌ General automation beyond voice/audio

**Recommendation**:
1. Use Wyoming events for **voice assistant control** (stop, pause, volume)
2. Use direct tool execution for **automotive control** (climate, navigation)
3. Implement custom Wyoming events for **TTS customization** (rate, voice)

This gives us the best of both worlds: protocol-compliant voice control + flexible automotive integration.
