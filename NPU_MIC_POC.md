# NPU Whisper Microphone POC

## TL;DR: Super Easy! 🎤

The NPU Whisper implementation **already has microphone support built-in** using sounddevice. A POC is literally one command.

---

## Option 1: Test Existing Mic Support (30 seconds) ⚡

**Easiest POC - Just run it:**

```bash
ssh amd@192.168.86.22
source /opt/xilinx/xrt/setup.sh
source /home/amd/RyzenAI-Full/bin/activate
cd ~/RyzenAI-SW/Demos/ASR/Whisper

# Continuous mic transcription
python run_whisper.py \
  --model-type whisper-small \
  --device npu \
  --input mic \
  --duration 0
```

**What it does:**
- Captures 2-second audio chunks via sounddevice
- Transcribes each chunk on NPU
- Prints transcription continuously
- Stops on 5 seconds of silence (or Ctrl+C)

**Expected behavior:**
```
🎤 Real-time Transcription. Start Speaking ..

Hello, how are you doing today?
I'm testing the NPU whisper microphone.
This is pretty cool!
🔕 Silence detected. Stopping transcription.
```

**Limitations:**
- 2-second buffering means ~2s delay
- Plus 9s NPU inference = **~11s total latency** 😬
- Not usable for real-time voice assistant

---

## Option 2: Integrate with talk-llama (1-2 hours) 🔧

Create a simple Python subprocess wrapper in your C++ code.

### Implementation

**Add to custom/talk-llama/whisper-npu.cpp:**
```cpp
#include <stdio.h>
#include <string>
#include <sstream>

std::string transcribe_npu_from_mic(int duration_ms = 2000) {
    // Buffer audio for duration_ms, then transcribe
    char cmd[2048];
    snprintf(cmd, sizeof(cmd),
        "ssh amd@192.168.86.22 '"
        "source /opt/xilinx/xrt/setup.sh && "
        "source /home/amd/RyzenAI-Full/bin/activate && "
        "cd ~/RyzenAI-SW/Demos/ASR/Whisper && "
        "timeout %d python run_whisper.py "
        "--model-type whisper-small --device npu --input mic "
        "--duration %f 2>&1'",
        (duration_ms / 1000) + 15,  // timeout
        duration_ms / 1000.0
    );

    FILE* pipe = popen(cmd, "r");
    if (!pipe) return "";

    std::stringstream result;
    char buffer[256];
    while (fgets(buffer, sizeof(buffer), pipe)) {
        // Parse for actual transcription (skip debug output)
        if (strstr(buffer, "Real-time") ||
            strstr(buffer, "Performance") ||
            strstr(buffer, "🎤")) {
            continue;
        }
        result << buffer;
    }

    pclose(pipe);
    return result.str();
}
```

**Usage in talk-llama.cpp:**
```cpp
// In main loop
if (use_npu_whisper) {
    std::string transcription = transcribe_npu_from_mic(2000);
    if (!transcription.empty()) {
        printf("NPU: %s\n", transcription.c_str());
        // Send to LLM...
    }
}
```

**Pros:**
- Minimal code (~50 lines)
- No new dependencies
- Tests NPU in real workflow

**Cons:**
- SSH overhead
- Python activation overhead
- ~11s latency unusable

---

## Option 3: Local NPU Python Service (4-6 hours) 🚀

Run NPU Whisper as a local service on .22, talk-llama connects via socket.

### Architecture
```
talk-llama (local mic) → Unix socket → npu_whisper_service.py (on .22) → NPU
                                    ← transcription ←
```

### Implementation

**1. Create service on .22:**

`~/voice-assistant-custom-commands/npu_whisper_service.py`:
```python
#!/usr/bin/env python3
"""NPU Whisper transcription service."""

import socket
import os
import sys
import numpy as np
from run_whisper import WhisperONNX, load_provider_options

SOCKET_PATH = "/tmp/npu_whisper.sock"
SAMPLE_RATE = 16000

def main():
    # Load NPU model
    config = load_config()
    encoder_opts, decoder_opts = load_provider_options(config, "whisper-small", "npu")

    model = WhisperONNX(
        "encoder_model.onnx",
        "decoder_model.onnx",
        "whisper-small",
        encoder_opts,
        decoder_opts
    )

    # Create Unix socket
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_PATH)
    sock.listen(1)

    print(f"NPU Whisper service listening on {SOCKET_PATH}")

    while True:
        conn, _ = sock.accept()

        # Receive audio data (raw PCM 16kHz float32)
        size_bytes = conn.recv(4)
        if not size_bytes:
            continue

        size = int.from_bytes(size_bytes, 'little')
        audio_bytes = conn.recv(size)

        # Convert to numpy array
        audio = np.frombuffer(audio_bytes, dtype=np.float32)

        # Transcribe on NPU
        text, _ = model.transcribe(audio)

        # Send back result
        result = text.encode('utf-8')
        conn.send(len(result).to_bytes(4, 'little'))
        conn.send(result)
        conn.close()

if __name__ == "__main__":
    main()
```

**2. Client in talk-llama.cpp:**
```cpp
std::string transcribe_npu_service(const float* audio, size_t samples) {
    int sock = socket(AF_UNIX, SOCK_STREAM, 0);
    struct sockaddr_un addr;
    addr.sun_family = AF_UNIX;
    strcpy(addr.sun_path, "/tmp/npu_whisper.sock");

    if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("connect");
        return "";
    }

    // Send audio size
    uint32_t size = samples * sizeof(float);
    send(sock, &size, 4, 0);

    // Send audio data
    send(sock, audio, size, 0);

    // Receive transcription
    uint32_t result_size;
    recv(sock, &result_size, 4, 0);

    char* buffer = new char[result_size + 1];
    recv(sock, buffer, result_size, 0);
    buffer[result_size] = '\0';

    std::string result(buffer);
    delete[] buffer;
    close(sock);

    return result;
}
```

**Pros:**
- No SSH overhead
- Service stays loaded (no Python startup)
- Cleaner architecture

**Cons:**
- Still ~9s NPU latency
- More complex setup
- Need to manage service lifecycle

---

## Option 4: Hybrid VAD + NPU (8-12 hours) 🎯

Use CPU VAD for voice detection, NPU only for transcription.

### Architecture
```
Mic → CPU VAD → detect speech → buffer audio → NPU transcribe → result
           ↓ no speech
        discard
```

This is what your current system does with whisper.cpp.

### Implementation Outline

1. **Keep existing VAD** (already working in talk-llama)
2. **After VAD triggers**, instead of whisper.cpp:
   - Save buffered audio to temp file
   - Call NPU via subprocess/service
   - Parse result
3. **Keep GPU path as fallback**

**Pros:**
- Efficient (NPU only when speaking detected)
- Can compare GPU vs NPU in real usage

**Cons:**
- Still 9s latency when NPU used
- Complex dual-path logic

---

## Recommended POC Path

### Phase 1: Validate (30 min)
```bash
# Test existing mic support
ssh amd@192.168.86.22
cd ~/RyzenAI-SW/Demos/ASR/Whisper
python run_whisper.py --model-type whisper-small --device npu --input mic --duration 0
```

✓ Confirms NPU + mic working
✓ Measures real-world latency
✓ Tests accuracy on your voice

### Phase 2: Prototype (2 hours)
Create simple wrapper script:

`test_npu_mic.sh`:
```bash
#!/bin/bash
# Quick POC wrapper

ssh amd@192.168.86.22 << 'ENDSSH'
source /opt/xilinx/xrt/setup.sh
source /home/amd/RyzenAI-Full/bin/activate
cd ~/RyzenAI-SW/Demos/ASR/Whisper

echo "🎤 Speak for 3 seconds..."
timeout 5 python run_whisper.py \
  --model-type whisper-small \
  --device npu \
  --input mic \
  --duration 3 2>&1 | grep -v "^[🎤\[]" | tail -1
ENDSSH
```

Call from anywhere:
```bash
./test_npu_mic.sh
# [speak]
# Output: "hello this is a test"
```

### Phase 3: Decide
Based on latency in Phase 1:
- **If <2s:** Worth integrating further
- **If >8s:** Keep as documentation only

---

## Expected Latency Breakdown

**NPU mic → transcription:**
```
Mic buffer (2s)           2000ms
Python startup              500ms
Model load (cached)        1000ms
NPU encode                 4000ms
NPU decode                 3000ms
Total:                   ~10500ms (10.5 seconds)
```

**GPU mic → transcription:**
```
Mic buffer (VAD)            ~300ms
GPU encode                  ~989ms
GPU decode                  ~43ms
Total:                    ~1332ms (1.3 seconds)
```

**Verdict:** NPU is **8x slower** even with mic input.

---

## When NPU Mic POC Makes Sense

❌ **NOT for real-time voice assistant**
- 10.5s latency unacceptable
- GPU already working at 1.3s

✅ **YES for these use cases:**
1. **Meeting recorder** - continuous long-form, latency OK
2. **Voice notes** - speak, walk away, read later
3. **Batch transcription** - record first, transcribe later
4. **Power testing** - measure NPU vs GPU battery impact

---

## Summary

### Difficulty Rating

| Option | Difficulty | Time | Latency | Value for Voice Assistant |
|--------|-----------|------|---------|---------------------------|
| Test existing | ⭐ | 30 min | 10.5s | Validation only |
| Python subprocess | ⭐⭐ | 2 hours | 11s | POC only |
| Local service | ⭐⭐⭐ | 6 hours | 9s | Better POC |
| Hybrid VAD+NPU | ⭐⭐⭐⭐ | 12 hours | 9s | Production-ish |

### Recommendation

**Start with Option 1 (30 minutes):**
```bash
ssh amd@192.168.86.22
cd ~/RyzenAI-SW/Demos/ASR/Whisper
source /opt/xilinx/xrt/setup.sh && source /home/amd/RyzenAI-Full/bin/activate
python run_whisper.py --model-type whisper-small --device npu --input mic --duration 0
```

**If latency is acceptable**, proceed to Option 3 (local service).

**If latency is still 9-11s**, keep GPU for voice assistant, document NPU for future batch use cases.

---

## Quick Start POC Script

Want to test RIGHT NOW? Run this:

```bash
#!/bin/bash
# Quick NPU mic POC - run from local machine

echo "Testing NPU Whisper with microphone..."
echo ""

ssh amd@192.168.86.22 'bash -s' << 'ENDSSH'
source /opt/xilinx/xrt/setup.sh
source /home/amd/RyzenAI-Full/bin/activate
cd ~/RyzenAI-SW/Demos/ASR/Whisper

echo "🎤 Speak a short phrase (will transcribe after 5 seconds of silence)..."
echo ""

timeout 30 python run_whisper.py \
  --model-type whisper-small \
  --device npu \
  --input mic \
  --duration 0 2>&1
ENDSSH

echo ""
echo "Done! Check the transcription above."
```

Save as `test-npu-mic-poc.sh`, chmod +x, and run!
