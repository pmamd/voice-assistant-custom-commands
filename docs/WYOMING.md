# Wyoming Protocol Integration

Documents how the voice assistant uses and extends the Wyoming protocol for TTS control.

## Architecture

Wyoming-Piper acts as the TTS server. talk-llama sends synthesize requests over TCP;
Wyoming-Piper synthesizes audio with Piper and plays it directly via `aplay`.

```
talk-llama  ──synthesize──▶  Wyoming-Piper  ──aplay──▶  Speaker
            ◀─ (no reply) ─                 ──kill──▶   (stop)
```

**Important deviation from standard Wyoming:** The standard protocol has Wyoming-Piper
stream `AudioStart` / `AudioChunk` / `AudioStop` events back to the client, which plays
the audio itself. Our implementation skips that — Wyoming-Piper plays directly via `aplay`
and sends no response back. This reduces latency at the cost of protocol compliance.

## Events We Implement

| Event | Direction | Purpose |
|-------|-----------|---------|
| `synthesize` | talk-llama → Wyoming | Request TTS synthesis and playback |
| `audio-stop` | talk-llama → Wyoming | Kill current aplay process immediately |
| `audio-pause` | talk-llama → Wyoming | Pause current playback |
| `audio-resume` | talk-llama → Wyoming | Resume paused playback |
| `new-response` | talk-llama → Wyoming | Signal start of new user turn; resets `STOP_CMD` so queued chunks play normally |

`new-response` is a custom event specific to this project. It must be sent before the
first TTS chunk of each new response, otherwise the stop state from the previous turn
would silence new audio.

## Control Flow for Stop Command

1. User says "stop" → fast-path matches → `WyomingClient::sendAudioStop()` called
2. talk-llama also sends `new-response` at the start of the **next** generation to reset
   Wyoming-Piper's stop state
3. Wyoming-Piper: `audio-stop` sets `STOP_CMD = True`, kills active aplay, and re-checks
   `STOP_CMD` inside the aplay lock so queued chunks that passed the initial check are
   also silenced

## Standard Wyoming Event Format

All events are newline-delimited JSON:

```
{"type": "synthesize", "data": {"text": "Hello", "voice": {"name": "en_US-lessac-medium"}}}\n
{"type": "audio-stop", "data": {"timestamp": null}}\n
{"type": "new-response", "data": {}}\n
```

For reference, the standard Wyoming TTS flow (not what we implement, but useful context):

```
Client → {"type": "synthesize", "data": {"text": "..."}}
Server → {"type": "audio-start", "data": {"rate": 22050, "width": 2, "channels": 1}}
Server → {"type": "audio-chunk", "payload_length": 8192}  + <binary PCM>
Server → {"type": "audio-stop", "data": {}}
```

## C++ Client

`WyomingClient` (`custom/talk-llama/wyoming-client.h/.cpp`) manages a persistent TCP
connection to Wyoming-Piper and exposes:

```cpp
bool sendNewResponse();  // signal new user turn — reset stop state
bool sendAudioStop();    // kill current playback immediately
bool sendAudioPause();   // pause playback
bool sendAudioResume();  // resume playback
```

The global instance is `tool_system::g_wyoming_client`, initialised at startup from
`--xtts-url`.

## Python Handler (`wyoming-piper/wyoming_piper/handler.py`)

Key state:

```python
STOP_CMD = False              # True after audio-stop, reset by new-response
ACTIVE_APLAY_PROCESSES = []   # Currently playing aplay processes
```

`STOP_CMD` is checked **twice** per synthesize event:
1. Before starting synthesis (fast check)
2. Inside the aplay lock — catches chunks that passed check 1 before the stop arrived

## Future Custom Events

These events are not yet implemented but are natural extensions:

| Event | Purpose | Priority |
|-------|---------|---------|
| `audio-pause` / `audio-resume` | Pause/resume without losing position | High |
| `set-playback-volume` | Adjust speaker volume | Medium |
| `set-speech-rate` | Speed up or slow down speech | Medium |
| `change-voice` | Switch TTS voice mid-conversation | Low |
| `repeat-last` | Re-play the last utterance | Low |

All would follow the same JSON format and handler pattern as `new-response`.

## Home Assistant Integration

Wyoming is the protocol used by Home Assistant voice pipelines. Our implementation is
not currently compatible (we don't stream audio back to the client), but full protocol
compliance would enable:

- HA voice pipeline integration
- Remote Wyoming-Piper servers
- Standard Wyoming satellites

Restoring compliance would require Wyoming-Piper to stream `AudioStart/Chunk/Stop` back
to the client instead of playing locally, and talk-llama to receive and play those chunks.

## Audio Device Configuration

Wyoming-Piper calls `aplay` without specifying a device, so it uses whatever ALSA
selects as the system default. On machines with multiple audio cards (e.g. HDMI + USB),
the default is often HDMI rather than the intended output device.

**Check your default device:**
```bash
aplay -l          # list all playback devices
aplay /usr/share/sounds/alsa/Front_Center.wav   # test default
```

**Set the correct default** by creating `~/.asoundrc`:
```
defaults.pcm.card 1   # replace 1 with the card number of your output device
defaults.ctl.card 1
```

Find the right card number from `aplay -l`. For example, if the MAYA44 USB is
`card 1`, the config above routes all `aplay` output there.

After creating `~/.asoundrc`, restart Wyoming-Piper for the change to take effect.

## References

- [Wyoming Protocol](https://github.com/rhasspy/wyoming)
- [Wyoming-Piper](https://github.com/rhasspy/wyoming-piper)
- [Wyoming Protocol spec](https://github.com/rhasspy/rhasspy3/blob/master/docs/wyoming.md)
