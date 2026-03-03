# Wyoming Protocol Proper Implementation for Tool System

## Overview

**IMPORTANT**: This document supersedes the `__STOP__` marker approach in `WYOMING_INTEGRATION.md`.

Wyoming is a comprehensive protocol for voice assistants that supports multiple event types. We should use proper Wyoming events instead of text-based hacks.

## Wyoming Protocol Event Types (Relevant to Our Use Case)

Based on the [Wyoming Protocol specification](https://github.com/rhasspy/wyoming), these events are relevant:

### Audio Control Events
- `audio-start`: Begin audio stream
- `audio-stop`: End audio stream
- `audio-chunk`: Audio data

### TTS Events
- `synthesize`: Request TTS (what we currently use)
- `synthesize-stopped`: Confirm TTS completion

### Custom Events
Wyoming supports custom event types for extensibility

## Current Wyoming-Piper Implementation

Looking at `wyoming_piper/handler.py`:

**Currently handles**:
- `Describe` - Service discovery
- `Synthesize` - TTS requests

**Currently imports from wyoming**:
```python
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler
from wyoming.tts import Synthesize
```

## Proper Implementation Approaches

### Option 1: Use AudioStop Event (Recommended)

Wyoming already has `AudioStop` event - we should use it properly!

#### Modify Wyoming-Piper Handler

**File**: `wyoming-piper/wyoming_piper/handler.py`

```python
async def handle_event(self, event: Event) -> bool:
    # Handle service discovery
    if Describe.is_type(event.type):
        await self.write_event(self.wyoming_info_event)
        _LOGGER.debug("Sent info")
        return True

    # Handle audio stop requests
    if AudioStop.is_type(event.type):
        _LOGGER.debug("Received AudioStop event - terminating all active aplay processes")

        global ACTIVE_APLAY_PROCESSES
        for aplay_proc in ACTIVE_APLAY_PROCESSES[:]:
            try:
                if aplay_proc.proc.returncode is None:
                    _LOGGER.debug(f"Terminating aplay process {aplay_proc.proc.pid}")
                    aplay_proc.proc.terminate()
                    ACTIVE_APLAY_PROCESSES.remove(aplay_proc)
            except Exception as e:
                _LOGGER.warning(f"Error terminating aplay: {e}")

        # Acknowledge the stop
        await self.write_event(AudioStop().event())
        return True

    # Handle TTS synthesis
    if not Synthesize.is_type(event.type):
        _LOGGER.warning("Unexpected event: %s", event)
        return True

    # Remove the hardcoded "stop" text detection (lines 59-77)
    # Just process normally
    try:
        return await self._handle_event(event)
    except Exception as err:
        await self.write_event(
            Error(text=str(err), code=err.__class__.__name__).event()
        )
        raise err
```

#### Update Wyoming Client in talk-llama

**File**: `custom/talk-llama/wyoming-client.h`

```cpp
#pragma once

#include <string>
#include "../../whisper.cpp/examples/json.hpp"

using json = nlohmann::json;

namespace tool_system {

// Wyoming protocol client for sending events to Wyoming-Piper
class WyomingClient {
public:
    WyomingClient(const std::string& host, int port);
    ~WyomingClient();

    // Send AudioStop event to halt current TTS playback
    bool sendAudioStop();

    // Send custom tool event (for future use)
    bool sendToolEvent(const std::string& tool_name, const json& args);

private:
    std::string host_;
    int port_;
    int sock_fd_;

    // Connect to Wyoming server
    bool connect();

    // Send Wyoming event (JSON + optional payload)
    bool sendEvent(const json& event);

    // Close connection
    void disconnect();
};

} // namespace tool_system
```

**File**: `custom/talk-llama/wyoming-client.cpp`

```cpp
#include "wyoming-client.h"
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <cstdio>

namespace tool_system {

WyomingClient::WyomingClient(const std::string& host, int port)
    : host_(host), port_(port), sock_fd_(-1) {
}

WyomingClient::~WyomingClient() {
    disconnect();
}

bool WyomingClient::connect() {
    sock_fd_ = socket(AF_INET, SOCK_STREAM, 0);
    if (sock_fd_ < 0) {
        fprintf(stderr, "[Wyoming Client] Failed to create socket\n");
        return false;
    }

    struct sockaddr_in serv_addr;
    memset(&serv_addr, 0, sizeof(serv_addr));
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(port_);

    if (inet_pton(AF_INET, host_.c_str(), &serv_addr.sin_addr) <= 0) {
        fprintf(stderr, "[Wyoming Client] Invalid address: %s\n", host_.c_str());
        close(sock_fd_);
        sock_fd_ = -1;
        return false;
    }

    if (::connect(sock_fd_, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0) {
        fprintf(stderr, "[Wyoming Client] Connection failed to %s:%d\n", host_.c_str(), port_);
        close(sock_fd_);
        sock_fd_ = -1;
        return false;
    }

    fprintf(stdout, "[Wyoming Client] Connected to %s:%d\n", host_.c_str(), port_);
    return true;
}

void WyomingClient::disconnect() {
    if (sock_fd_ >= 0) {
        close(sock_fd_);
        sock_fd_ = -1;
    }
}

bool WyomingClient::sendEvent(const json& event) {
    if (sock_fd_ < 0) {
        if (!connect()) {
            return false;
        }
    }

    // Wyoming protocol: JSON event followed by newline
    std::string event_str = event.dump() + "\n";

    ssize_t sent = send(sock_fd_, event_str.c_str(), event_str.length(), 0);
    if (sent < 0) {
        fprintf(stderr, "[Wyoming Client] Failed to send event\n");
        disconnect();
        return false;
    }

    fprintf(stdout, "[Wyoming Client] Sent event: %s", event_str.c_str());
    return true;
}

bool WyomingClient::sendAudioStop() {
    // Create AudioStop event according to Wyoming protocol
    json event = {
        {"type", "audio-stop"},
        {"data", json::object()},
        {"payload", nullptr}
    };

    fprintf(stdout, "[Wyoming Client] Sending AudioStop event\n");
    return sendEvent(event);
}

bool WyomingClient::sendToolEvent(const std::string& tool_name, const json& args) {
    // Custom event for future tool commands
    json event = {
        {"type", "tool-command"},
        {"data", {
            {"tool", tool_name},
            {"arguments", args}
        }},
        {"payload", nullptr}
    };

    fprintf(stdout, "[Wyoming Client] Sending tool event: %s\n", tool_name.c_str());
    return sendEvent(event);
}

} // namespace tool_system
```

#### Update stop_speaking Executor

**File**: `custom/talk-llama/tool-system.cpp`

```cpp
ToolResult stop_speaking(const json& args) {
    fprintf(stdout, "[Tool] stop_speaking executed\n");

    // The actual Wyoming event will be sent in talk-llama.cpp
    // when handling this tool result

    return ToolResult(true, "Stopping speech");
}
```

#### Update talk-llama.cpp Integration

**Fast path handler** (Line ~2587):

```cpp
if (matched && tool_def.fast_path) {
    fprintf(stdout, "\n[Fast Path Tool: %s]\n", tool_def.name.c_str());

    tool_system::ToolResult result = tool_registry.execute(tool_def.name, json::object());

    if (result.success) {
        if (tool_def.name == "stop_speaking") {
            // Send proper Wyoming AudioStop event
            tool_system::WyomingClient wyoming_client("0.0.0.0", 10200);
            wyoming_client.sendAudioStop();
            fprintf(stdout, "Sent AudioStop event to Wyoming\n");
        }

        // Skip LLaMA processing
        audio.clear();
        g_hotkey_pressed = "";
        test_audio_injected = false;
        continue;
    }
}
```

**Smart path handler** (Line ~2896):

```cpp
if (tool_detected && tool_parser.hasToolCall()) {
    tool_system::ToolCall call = tool_parser.getToolCall();
    fprintf(stdout, "\n[Tool Call: %s]\n", call.name.c_str());

    tool_system::ToolResult result = tool_registry.execute(call.name, call.arguments);

    if (result.success) {
        if (call.name == "stop_speaking") {
            tool_system::WyomingClient wyoming_client("0.0.0.0", 10200);
            wyoming_client.sendAudioStop();
        } else if (call.name == "set_temperature") {
            fprintf(stdout, "[Tool executed: %s]\n", result.message.c_str());
        }
        // ... other tools
    }

    tool_parser.reset();
}
```

### Option 2: Define Custom Wyoming Events (Future)

For more complex commands beyond audio control, we can define custom Wyoming events:

```python
# In wyoming_piper/handler.py

async def handle_event(self, event: Event) -> bool:
    # ... existing handlers ...

    # Handle custom tool commands
    if event.type == "tool-command":
        tool_name = event.data.get("tool")
        arguments = event.data.get("arguments", {})

        _LOGGER.debug(f"Received tool command: {tool_name}")

        # Dispatch to appropriate handler
        if tool_name == "set_volume":
            await self.handle_set_volume(arguments)
        elif tool_name == "set_speed":
            await self.handle_set_speed(arguments)

        return True
```

## Implementation Steps (Proper Approach)

### Step 1: Update wyoming-client (C++)

Replace the simple wrapper with a proper socket-based Wyoming client:

```bash
# Files to modify on dev machine:
custom/talk-llama/wyoming-client.h    (Complete rewrite)
custom/talk-llama/wyoming-client.cpp  (Complete rewrite)
```

### Step 2: Update Wyoming-Piper Handler

```bash
# File to modify:
wyoming-piper/wyoming_piper/handler.py

# Changes:
1. Add AudioStop event handler (lines ~55)
2. Remove hardcoded "stop" text detection (lines 59-77)
```

### Step 3: Update talk-llama.cpp

```bash
# File to modify:
custom/talk-llama/talk-llama.cpp

# Changes:
1. Create WyomingClient instance with proper host/port
2. Call sendAudioStop() instead of send_tts_async("stop", ...)
```

### Step 4: Test

```bash
# On dev machine:
cd ~/Projects/git/talk-llama-fast

# Rebuild
cmake --build build -j

# Test Wyoming event
python3 -c "
import socket
import json

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('0.0.0.0', 10200))

event = {'type': 'audio-stop', 'data': {}, 'payload': None}
s.send((json.dumps(event) + '\n').encode())
s.close()
print('Sent AudioStop event')
"

# Run full test
./build/bin/talk-llama-custom -m models/mistral.gguf --model-whisper models/ggml-base.en.bin
# Say "stop" during speech -> should send AudioStop event
```

## Benefits of Proper Wyoming Implementation

1. **Protocol Compliance**: Uses Wyoming as designed
2. **Extensibility**: Easy to add new event types
3. **Reliability**: No text parsing hacks
4. **Home Automation Ready**: Wyoming is designed for HA integration
5. **Future-Proof**: Can leverage new Wyoming features

## Wyoming Protocol Resources

- **Main Repository**: [github.com/rhasspy/wyoming](https://github.com/rhasspy/wyoming)
- **Wyoming-Piper**: [github.com/rhasspy/wyoming-piper](https://github.com/rhasspy/wyoming-piper)
- **Protocol Documentation**: [Wyoming Protocol Specification](https://github.com/rhasspy/rhasspy3/blob/master/docs/wyoming.md)
- **Home Assistant Integration**: Wyoming is used extensively in HA voice pipelines

## Migration Path

1. **Phase 1** (Current): Text-based `send_tts_async("stop", ...)` - WORKING NOW
2. **Phase 2** (Next): Implement proper Wyoming socket client in C++
3. **Phase 3**: Send `AudioStop` events instead of text
4. **Phase 4**: Add custom events for other tools (volume, speed, etc.)
5. **Phase 5**: Full Home Assistant integration

## Comparison: Text Hack vs Proper Events

### Current Approach (Text Hack)
```
talk-llama → send_tts_async("stop") → Wyoming → text contains "stop"? → kill aplay
```
❌ Unreliable (false positives)
❌ Not protocol-compliant
❌ Limited to TTS channel

### Proper Approach (Wyoming Events)
```
talk-llama → WyomingClient.sendAudioStop() → Wyoming → AudioStop event → kill aplay
```
✅ Reliable (no false positives)
✅ Protocol-compliant
✅ Supports all Wyoming event types
✅ Ready for Home Assistant

## Next Steps

1. Implement proper `WyomingClient` with socket communication
2. Update Wyoming-Piper to handle `AudioStop` events
3. Test end-to-end with proper events
4. Document for future Home Assistant integration
5. Consider contributing improvements back to wyoming-piper project

---

**Sources**:
- [Wyoming Protocol Repository](https://github.com/rhasspy/wyoming)
- [Wyoming-Piper Server](https://github.com/rhasspy/wyoming-piper)
- [Wyoming Protocol Documentation](https://github.com/rhasspy/rhasspy3/blob/master/docs/wyoming.md)
- [Wyoming Satellite](https://github.com/rhasspy/wyoming-satellite)
