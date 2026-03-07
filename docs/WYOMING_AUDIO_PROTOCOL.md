# Wyoming Audio Protocol - Current vs Standard Implementation

## Overview

This document explains how our modified Wyoming-Piper implementation differs from the standard Wyoming protocol, why those modifications were made, and what would be needed to restore full protocol compliance.

## Standard Wyoming TTS Flow

According to the [Wyoming Protocol specification](https://github.com/rhasspy/wyoming), a standard TTS interaction should work like this:

### Client → Server (talk-llama → Wyoming-Piper)

**1. Synthesize Request**
```json
{"type": "synthesize", "version": "1.5.3", "data_length": 62}
{"text": "Hello world", "voice": {"name": "en_US-amy-medium"}}
```

### Server → Client (Wyoming-Piper → talk-llama)

**2. AudioStart Event**
```json
{"type": "audio-start", "data": {"rate": 22050, "width": 2, "channels": 1}}
```

**3. AudioChunk Events** (multiple)
```json
{"type": "audio-chunk", "data": {"rate": 22050, "width": 2, "channels": 1}, "payload_length": 8192}
<binary audio data>
```

**4. AudioStop Event**
```json
{"type": "audio-stop", "data": {}}
```

### Client Responsibility
- Receive audio chunks
- Decode PCM audio
- Play through speakers or process further

## Our Modified Implementation

### What We Changed (2024)

**Modification #5 in MODIFICATIONS.md**: Direct Audio Playback

Instead of following the standard Wyoming protocol, we:

1. **Wyoming-Piper**: Plays audio directly with `aplay` subprocess
2. **Wyoming-Piper**: Does NOT send `AudioStart`, `AudioChunk`, `AudioStop` back to client
3. **talk-llama**: Closes socket immediately after sending synthesize request
4. **talk-llama**: Does NOT wait for or process audio response

### Why We Did This

**Purpose**: Lower latency

**From MODIFICATIONS.md**:
> **Purpose**: Bypass Wyoming protocol audio streaming for direct playback.
> **Result**: Significantly reduced TTS playback latency.

**Performance Benefit**:
- **Standard**: talk-llama → Wyoming → audio chunks → talk-llama → decode → play
- **Modified**: talk-llama → Wyoming → direct aplay (cuts out network round-trips)

### Current Code Flow

#### talk-llama.cpp (Client Side)

**File**: `custom/talk-llama/talk-llama.cpp`

```cpp
void send_tts_async(std::string text, std::string speaker_wav, ...) {
    // ... text preprocessing ...

    // Create Wyoming synthesize request
    char *json = TTS_RequestEncode(text.c_str());  // Creates {"type":"synthesize",...}

    // Connect to Wyoming-Piper
    hSocket = TTS_SocketCreate();
    TTS_SocketConnect(hSocket);  // Connect to 127.0.0.1:10200

    // Send request
    TTS_SocketSend(hSocket, json, strlen(json));
    free(json);

    // Close immediately - DON'T wait for response
    close(hSocket);
    shutdown(hSocket, 0);
}
```

**Key Point**: talk-llama **does not receive** any audio data. It just sends text and disconnects.

#### Wyoming-Piper (Server Side)

**File**: `wyoming-piper/wyoming_piper/handler.py`

```python
async def _handle_event(self, event: Event) -> bool:
    synthesize = Synthesize.from_event(event)
    raw_text = synthesize.text

    # Generate audio with Piper
    piper_proc.proc.stdin.write((text + "\n").encode("utf-8"))

    # Read output path from Piper stderr
    output_path = parse_piper_output()  # Gets /tmp/piper_XXXX.wav

    # Play directly with aplay (NOT sent back to client!)
    aplay_proc = await self.process_manager.get_aplay_process(output_path)
    await aplay_proc.proc.wait()

    # Clean up
    os.unlink(output_path)

    return True
```

**Key Point**: Wyoming-Piper **does not send** `AudioStart`, `AudioChunk`, `AudioStop` events. Audio plays locally on the Wyoming-Piper machine via `aplay`.

## Comparison: Standard vs Modified

| Aspect | Standard Wyoming | Our Modified Version |
|--------|-----------------|---------------------|
| **Audio Transport** | Network (Wyoming protocol) | Local (aplay subprocess) |
| **Client Receives** | AudioStart, AudioChunk, AudioStop | Nothing (socket closes immediately) |
| **Playback Location** | Client machine (talk-llama host) | Server machine (Wyoming-Piper host) |
| **Latency** | Higher (network encoding/decoding) | Lower (direct playback) |
| **Deployment** | Client and server can be different machines | Must be same machine or shared audio device |
| **Protocol Compliance** | ✅ Full Wyoming protocol | ❌ Violates protocol (no audio response) |

## Why This Matters for Tool System

### Current Limitation

With our modified approach, we can't send Wyoming events from talk-llama to Wyoming-Piper **and get responses back** because:

1. talk-llama closes socket immediately after sending
2. Wyoming-Piper doesn't send responses anyway

### Impact on AudioStop Event

When we want to send `AudioStop` event:

**Problem**:
```cpp
// In talk-llama.cpp
WyomingClient client("127.0.0.1", 10200);
client.sendAudioStop();  // Sends {"type": "audio-stop", ...}
client.disconnect();     // Closes immediately

// Wyoming-Piper receives event, but...
// talk-llama has already disconnected and isn't listening
```

**Result**: One-way communication works, but we can't get acknowledgments or responses.

## Solutions

### Option 1: Keep Modified Approach (Current)

**Use for**: Direct aplay control commands

**Works for**:
- `AudioStop` - Kill aplay processes
- Custom tool events - Direct server-side actions

**Implementation**:
```cpp
// Wyoming client sends event and disconnects
client.sendAudioStop();

// Wyoming-Piper handles event locally
// (kills aplay, adjusts volume, etc.)
```

**Pros**:
- Simple, low latency
- Works for our automotive tool commands
- No changes to talk-llama needed

**Cons**:
- Not protocol-compliant
- Can't receive responses/acknowledgments
- Wyoming-Piper must be on same machine as speakers

### Option 2: Implement Full Wyoming Protocol (Future)

**Use for**: Distributed systems, protocol compliance

**Requires**:

1. **Wyoming-Piper**: Restore audio streaming
   ```python
   # Send audio chunks back to client
   await self.write_event(AudioStart(rate=22050, width=2, channels=1).event())

   with wave.open(output_path, 'rb') as wav_file:
       while True:
           chunk = wav_file.readframes(samples_per_chunk)
           if not chunk:
               break
           await self.write_event(AudioChunk(
               rate=22050, width=2, channels=1,
               audio=chunk
           ).event())

   await self.write_event(AudioStop().event())
   ```

2. **talk-llama**: Add audio receiver
   ```cpp
   void send_tts_async(...) {
       // Send synthesize request
       TTS_SocketSend(hSocket, json, strlen(json));

       // NEW: Receive and process audio chunks
       while (true) {
           WyomingEvent event = receiveEvent(hSocket);

           if (event.type == "audio-start") {
               initAudioPlayback(event.rate, event.width, event.channels);
           }
           else if (event.type == "audio-chunk") {
               playAudioChunk(event.payload);
           }
           else if (event.type == "audio-stop") {
               break;
           }
       }

       close(hSocket);
   }
   ```

3. **talk-llama**: Add audio playback
   - Use ALSA/PulseAudio/SDL2 for audio output
   - Buffer and decode PCM audio chunks
   - Handle playback control (pause, resume, stop)

**Pros**:
- Full Wyoming protocol compliance
- Can run Wyoming-Piper on different machine
- Can get responses and acknowledgments
- Can pipe audio through processing

**Cons**:
- Higher latency (network encoding/decoding)
- More complex implementation
- Requires audio playback in talk-llama

### Option 3: Hybrid Approach (Recommended)

**Use both approaches based on use case**:

**For TTS Synthesis** (current modified):
- talk-llama → synthesize → Wyoming-Piper → aplay (local)
- Fast, low latency

**For Control Commands** (Wyoming events):
- talk-llama → audio-stop/tool-command → Wyoming-Piper → action
- Protocol-compliant for control plane

**Implementation**:
```cpp
// Two socket connections:

// 1. TTS connection (fire-and-forget, modified protocol)
void send_tts_async(text) {
    int sock = connect_wyoming();
    send_synthesize(sock, text);
    close(sock);  // Don't wait for response
}

// 2. Control connection (persistent, full protocol)
class WyomingControlClient {
    int control_sock;  // Keep alive

    void sendAudioStop() {
        send_event(control_sock, audio_stop_event);
        // Can optionally wait for acknowledgment
    }
};
```

## What Wyoming-Piper Responses Look Like

If we restored standard protocol, Wyoming-Piper would send:

### AudioStart
```json
{"type": "audio-start", "data": {"rate": 22050, "width": 2, "channels": 1}, "payload_length": 0}
```

### AudioChunk (example)
```json
{"type": "audio-chunk", "data": {"rate": 22050, "width": 2, "channels": 1}, "payload_length": 8192}
<8192 bytes of PCM audio data>
```

### AudioStop
```json
{"type": "audio-stop", "data": {}, "payload_length": 0}
```

### Format Details

**Audio Format** (from Piper default):
- **Sample Rate**: 22050 Hz
- **Bit Depth**: 16-bit (width=2 bytes)
- **Channels**: 1 (mono)
- **Encoding**: Signed 16-bit PCM, little-endian

**Chunk Size**: Configurable via `samples_per_chunk` parameter (default: typically 1024-4096 samples)

## Changes Needed for Full Protocol Support

### 1. Wyoming-Piper Handler Changes

**File**: `wyoming-piper/wyoming_piper/handler.py`

**Add audio streaming** (replace lines 171-186):

```python
async def _handle_event(self, event: Event) -> bool:
    synthesize = Synthesize.from_event(event)

    # Generate audio
    output_path = await generate_with_piper(synthesize.text)

    # Read WAV file
    with wave.open(output_path, 'rb') as wav_file:
        rate = wav_file.getframerate()
        width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()

        # Send start event
        await self.write_event(AudioStart(
            rate=rate, width=width, channels=channels
        ).event())

        # Stream chunks
        samples_per_chunk = 1024
        while True:
            chunk = wav_file.readframes(samples_per_chunk)
            if not chunk:
                break

            await self.write_event(AudioChunk(
                rate=rate, width=width, channels=channels,
                audio=chunk
            ).event())

        # Send stop event
        await self.write_event(AudioStop().event())

    os.unlink(output_path)
    return True
```

### 2. talk-llama Changes

**File**: `custom/talk-llama/talk-llama.cpp`

**Add Wyoming event receiver**:

```cpp
struct WyomingEvent {
    std::string type;
    json data;
    std::vector<uint8_t> payload;
};

WyomingEvent receiveWyomingEvent(int sock) {
    char buffer[4096];
    int bytes = recv(sock, buffer, sizeof(buffer), 0);

    // Parse JSON header
    json header = json::parse(std::string(buffer, bytes));

    WyomingEvent event;
    event.type = header["type"];
    event.data = header.value("data", json::object());

    // Read payload if present
    int payload_length = header.value("payload_length", 0);
    if (payload_length > 0) {
        event.payload.resize(payload_length);
        int total_read = 0;
        while (total_read < payload_length) {
            int n = recv(sock, event.payload.data() + total_read,
                        payload_length - total_read, 0);
            total_read += n;
        }
    }

    return event;
}

void send_tts_async_with_audio(std::string text, ...) {
    // Send synthesize
    char *json = TTS_RequestEncode(text.c_str());
    hSocket = TTS_SocketCreate();
    TTS_SocketConnect(hSocket);
    TTS_SocketSend(hSocket, json, strlen(json));
    free(json);

    // Initialize audio playback (SDL2, ALSA, etc.)
    AudioPlayer player;

    // Receive and play audio
    while (true) {
        WyomingEvent event = receiveWyomingEvent(hSocket);

        if (event.type == "audio-start") {
            player.init(event.data["rate"], event.data["width"],
                       event.data["channels"]);
        }
        else if (event.type == "audio-chunk") {
            player.play(event.payload);
        }
        else if (event.type == "audio-stop") {
            break;
        }
    }

    close(hSocket);
}
```

**Add audio playback** (using SDL2, already linked):

```cpp
class AudioPlayer {
    SDL_AudioDeviceID device;

public:
    void init(int rate, int width, int channels) {
        SDL_AudioSpec spec;
        spec.freq = rate;
        spec.format = (width == 2) ? AUDIO_S16LSB : AUDIO_S8;
        spec.channels = channels;
        spec.samples = 1024;
        // ...

        device = SDL_OpenAudioDevice(NULL, 0, &spec, NULL, 0);
        SDL_PauseAudioDevice(device, 0);
    }

    void play(const std::vector<uint8_t>& audio) {
        SDL_QueueAudio(device, audio.data(), audio.size());
    }

    ~AudioPlayer() {
        SDL_CloseAudioDevice(device);
    }
};
```

## Recommendations

### Short Term (Current Tool System)

**Keep modified approach** for automotive tool commands:

1. Use one-way Wyoming events for control (AudioStop, custom tool events)
2. Wyoming-Piper handles events locally (kill aplay, adjust settings)
3. No need for talk-llama to receive responses
4. Simple, fast, works for current use case

### Long Term (Future Enhancement)

**Implement full protocol** for distributed deployment:

1. Restore audio streaming in Wyoming-Piper
2. Add audio receiver in talk-llama
3. Support both local and remote Wyoming servers
4. Enable advanced features (audio processing, cloud TTS, etc.)

## Testing Full Protocol

If implementing full protocol, test with:

```bash
# Start Wyoming-Piper with audio streaming enabled
wyoming-piper-custom --stream-audio \
    --piper /usr/bin/piper \
    --voice en_US-amy-medium \
    --uri tcp://0.0.0.0:10200

# Test with simple Python client
python3 << 'EOF'
import socket
import json
import wave

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('127.0.0.1', 10200))

# Send synthesize
header = {"type": "synthesize", "version": "1.5.3", "data_length": 20}
data = {"text": "Hello world"}
sock.send((json.dumps(header) + "\n" + json.dumps(data)).encode())

# Receive audio chunks
wav = wave.open('output.wav', 'wb')

while True:
    event_line = b''
    while True:
        char = sock.recv(1)
        if char == b'\n':
            break
        event_line += char

    event = json.loads(event_line)

    if event['type'] == 'audio-start':
        wav.setnchannels(event['data']['channels'])
        wav.setsampwidth(event['data']['width'])
        wav.setframerate(event['data']['rate'])
    elif event['type'] == 'audio-chunk':
        payload_len = event['payload_length']
        audio_data = sock.recv(payload_len)
        wav.writeframes(audio_data)
    elif event['type'] == 'audio-stop':
        break

wav.close()
sock.close()
print("Saved to output.wav")
EOF
```

## Summary

Our modified Wyoming-Piper implementation:

**✅ Pros**:
- Low latency (direct aplay)
- Simple implementation
- Works great for our automotive use case

**❌ Cons**:
- Not Wyoming protocol compliant
- No audio responses sent back
- Can't use remote Wyoming servers
- One-way communication only

**For our tool system**: The modified approach is sufficient. We can send control events (AudioStop, tool commands) one-way, and Wyoming-Piper handles them locally.

**For future**: If we need distributed deployment or want to contribute back to upstream, we should implement full Wyoming protocol with audio streaming.

---

**References**:
- [Wyoming Protocol Repository](https://github.com/rhasspy/wyoming)
- [Wyoming-Piper Server](https://github.com/rhasspy/wyoming-piper)
- [Wyoming Protocol Documentation](https://github.com/rhasspy/rhasspy3/blob/master/docs/wyoming.md)
