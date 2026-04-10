# NPU Whisper Integration Analysis

## Architecture Overview

### Current NPU Implementation (Python)

**Stack:**
```
Audio WAV → WhisperONNX class → ONNX Runtime → VitisAI Execution Provider → NPU
```

**Key Components:**
1. **ONNX Runtime** - Inference engine with VitisAI EP
2. **VitisAI EP** - Execution provider that compiles/dispatches ops to NPU
3. **Pre-compiled Models** - ONNX format (encoder.onnx, decoder.onnx)
4. **Cached Artifacts** - NPU-compiled binaries in `cache/` directory

**Configuration:**
- `config/vitisai_config_whisper_encoder.json` - NPU compiler settings
- `config/vitisai_config_whisper_decoder.json` - NPU compiler settings
- Cache keys: `whisper_small_encoder`, `whisper_small_decoder`

### Current GPU Implementation (C++)

**Stack:**
```
Audio PCM → whisper.cpp → HIP/ROCm → gfx1153 iGPU
```

**Key Components:**
1. **whisper.cpp** - Native C++ implementation
2. **GGUF models** - Quantized model format
3. **ROCm/HIP** - AMD GPU acceleration layer

## Integration Options

### Option 1: Python Subprocess (Simplest)

**Implementation:**
```cpp
// In talk-llama.cpp
std::string transcribe_npu(const char* wav_file) {
    char cmd[1024];
    snprintf(cmd, sizeof(cmd),
        "cd ~/RyzenAI-SW/Demos/ASR/Whisper && "
        "source /opt/xilinx/xrt/setup.sh && "
        "source ~/RyzenAI-Full/bin/activate && "
        "python run_whisper.py --model-type whisper-small "
        "--device npu --input %s 2>&1", wav_file);

    FILE* pipe = popen(cmd, "r");
    // Parse output for "Transcription: ..."
    // ...
}
```

**Pros:**
- ✓ Minimal code changes
- ✓ No new dependencies
- ✓ Uses existing NPU setup

**Cons:**
- ✗ High overhead (~9s for 1.2s audio)
- ✗ Python environment activation required
- ✗ IPC latency
- ✗ Not suitable for real-time voice commands

**Use Case:** Background/batch transcription only

---

### Option 2: ONNX Runtime C API (Native)

**Implementation:**
```cpp
#include <onnxruntime_c_api.h>

class WhisperNPU {
private:
    OrtSession* encoder_session;
    OrtSession* decoder_session;
    OrtEnv* env;

public:
    WhisperNPU() {
        // Initialize ONNX Runtime
        OrtSessionOptions* options;
        g_ort->CreateSessionOptions(&options);

        // Set VitisAI EP
        OrtSessionOptionsAppendExecutionProvider_VitisAI(
            options,
            "config/vitisai_config_whisper_encoder.json",
            "./cache/",
            "whisper_small_encoder"
        );

        // Load models
        g_ort->CreateSession(env, "encoder.onnx", options, &encoder_session);
        g_ort->CreateSession(env, "decoder.onnx", options, &decoder_session);
    }

    std::string transcribe(const float* audio, size_t samples);
};
```

**Pros:**
- ✓ Native C++ integration
- ✓ Lower overhead than Python
- ✓ Direct NPU control
- ✓ Can share preprocessing code

**Cons:**
- ✗ Complex ONNX Runtime C API
- ✗ Need to port preprocessing (mel spectrograms)
- ✗ Need to handle tokenization
- ✗ Requires VitisAI EP C bindings (check availability)
- ✗ Still slower than GPU for short audio

**Use Case:** If NPU becomes competitive with optimizations

---

### Option 3: Hybrid GPU+NPU (Best of Both?)

**Concept:**
- Use GPU whisper.cpp for encoder (fast, 989ms)
- Use NPU for decoder (offload GPU, TTFT 50ms)

**Challenges:**
- Different model formats (GGUF vs ONNX)
- Need encoder output format compatibility
- Probably not worth the complexity

---

## Recommended Approach

### Phase 1: Benchmark Deep Dive
Before integrating, understand the 9.2s NPU latency:

1. **Profile Python overhead:**
   ```bash
   # Test pure ONNX inference time
   python -c "import time; from run_whisper import *; ..."
   ```

2. **Check model compilation:**
   - First run compiles (~15 min)
   - Subsequent runs use cache
   - Is cache being hit?

3. **Test on longer audio:**
   - NPU may excel on >10s audio
   - RTF 0.64 means good throughput

### Phase 2: Conditional NPU Path
Add NPU as optional backend for specific use cases:

```cpp
enum WhisperBackend {
    WHISPER_GPU,    // whisper.cpp + ROCm (default, fast)
    WHISPER_NPU,    // ONNX + VitisAI (low power, long audio)
};

struct whisper_context {
    WhisperBackend backend;
    // ... GPU state ...
    // ... NPU state ...
};

// Use GPU for voice commands (<5s)
// Use NPU for long-form transcription (>30s)
```

### Phase 3: Power Optimization
For always-on scenarios:
- Voice activity detection on CPU
- Quick commands on GPU
- Background/batch on NPU

## Dependencies Required

### For ONNX Runtime C++ Integration:
```bash
# Install ONNX Runtime
apt-get install libonnxruntime-dev

# VitisAI Execution Provider
# Check if included in RyzenAI SDK or needs separate build
ls /home/amd/Downloads/ryzen_ai-1.6.1/
```

### Check Library Availability:
```bash
ssh amd@192.168.86.22 'find /opt/xilinx -name "*onnxruntime*" -o -name "*vitisai*"'
```

## Next Steps

1. ✅ **Completed:** Performance testing
2. **Investigate:** NPU latency breakdown (where's the 9s?)
3. **Prototype:** Simple Python subprocess wrapper
4. **Evaluate:** ONNX Runtime C API availability on target
5. **Decide:** Is NPU worth it for this use case?

## Conclusion

**For real-time voice assistant:** Stick with GPU whisper.cpp
- 8x faster (1.14s vs 9.2s)
- Already integrated
- Sub-second latency critical

**For future features:**
- Meeting transcription (long audio)
- Multi-user scenarios (NPU frees GPU for LLM)
- Battery-powered mode (NPU more efficient)

The NPU path makes sense as an **optional feature**, not a replacement.
