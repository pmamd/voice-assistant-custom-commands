# Voice Assistant End-to-End Latency Breakdown

**Date:** 2026-04-16
**Target:** amd@192.168.86.26 (890M iGPU, gfx1153)
**Test Audio:** make_it_warmer.wav (1.5s duration)

---

## Current Measurements (Test Mode)

### CPU Baseline
```
Whisper (transcription):     1737 ms
LLM generation:              7133 ms
─────────────────────────────────────
Total (VAD end → LLM):       8871 ms
```

### NPU (VitisAI) - **10.5x Faster Whisper, 3.2x Faster End-to-End**
```
Whisper (transcription):      165 ms  ← NPU-accelerated encoder
LLM generation:              2630 ms  ← GPU-accelerated (all 33/33 layers on iGPU)
─────────────────────────────────────
Total (VAD end → LLM):       2795 ms
```

**Speedups:**
- **Whisper: 10.5x** (1737ms → 165ms)
- **LLM: 2.7x** (7133ms → 2630ms)
- **End-to-End: 3.2x** (8871ms → 2795ms)

---

## What Runs Where

### NPU (VitisAI):
✅ **Whisper Encoder** (~164ms with NPU vs ~1680ms CPU)
  - Mel spectrogram processing
  - Audio feature extraction
  - Convolution layers
  - Transformer encoder blocks
  - Model: `ggml-base.bin` (multilingual)
  - .rai file: `ggml-base-encoder-vitisai.rai` (25MB)

### CPU:
✅ **Whisper Decoder** (included in 164ms)
  - Autoregressive token generation
  - Language model decoding

❌ **LLM (llama-server)** - NOT using GPU
  - Runs with `-ngl 0` (0 GPU layers)
  - gfx1153 iGPU cannot offload layers
  - Model: mistral-7b-instruct-v0.2.Q5_0

❌ **TTS (Wyoming-Piper)** - CPU only
  - No GPU acceleration available

❌ **VAD (Voice Activity Detection)** - CPU
  - Energy-based detection

---

## Full End-to-End Pipeline (Actual Measurements)

Based on latency benchmark run on 2026-04-17:

| Stage | CPU Baseline | NPU + GPU | Speedup | Notes |
|-------|--------------|-----------|---------|-------|
| **VAD** | 50ms | 50ms | 1.0x | Energy threshold detection (test mode bypasses real-time VAD) |
| **Whisper** | 1737ms | 165ms | **10.5x** | NPU-accelerated encoder |
| **LLM** | 7133ms | 2630ms | **2.7x** | GPU-accelerated (33/33 layers on iGPU) |
| **TTS** | *N/A* | *N/A* | - | Not measured yet (async) |
| **Total (VAD→LLM)** | 8871ms | 2795ms | **3.2x** | Measured end-to-end |

### Breakdown by %:

**CPU Baseline:**
- VAD: 0.6%
- Whisper: 19.6%
- LLM: 80.4%
- TTS: *not measured*

**With NPU + GPU:**
- VAD: 1.8%
- Whisper: 5.9% ← **Drastically reduced**
- LLM: 94.1% ← **Now the bottleneck**
- TTS: *not measured*

---

## Critical Configuration

### NPU Requirements:
```bash
# Model (MUST match)
-mw ./whisper.cpp/models/ggml-base.bin  # multilingual, NOT .en

# Environment
export XLNX_VART_FIRMWARE=/opt/xilinx/overlaybins/xclbins
export HSA_OVERRIDE_GFX_VERSION=11.0.3  # per ryzenai-embedded-eval-kit

# Build flags
cmake -B build -DWHISPER_SDL2=ON -DGGML_HIP=ON -DWHISPER_VITISAI=ON
```

### ❌ Common Mistakes:
- Using `ggml-base.en.bin` with NPU → garbage transcription
- Wrong HSA override (11.0.0 or 11.5.1) → crashes
- Missing XRT environment → NPU not loaded

---

## GPU Status (gfx1153 890M iGPU)

### Whisper:
❌ **Crashes** - rocBLAS doesn't support gfx1153
```
rocBLAS error: Cannot read TensileLibrary.dat: Illegal seek for GPU arch: gfx1153
Segmentation fault (core dumped)
```

### Llama:
✅ **Working with GPU acceleration**
- Offloads all 33/33 layers to iGPU (ROCm0)
- 2.7x speedup (7133ms CPU → 2630ms GPU)
- Important: Works WITHOUT HSA_OVERRIDE (llama-server manages its own GPU context)

**Conclusion:** gfx1153 has working GPU support for LLM, but Whisper GPU crashes. Use NPU for Whisper + GPU for LLM for best performance.

---

## Next Steps for Further Optimization

1. **Reduce LLM latency** (now 72% of total):
   - Smaller model (3B instead of 7B)
   - Better quantization (Q4_K_M → Q3_K_S)
   - Context caching
   - Speculative decoding

2. **Reduce VAD threshold** (currently 700ms):
   - Requires implementing AEC (Acoustic Echo Cancellation)
   - Could drop to 200ms with proper feedback prevention
   - See: docs/TTS_FEEDBACK_PREVENTION.md

3. **GPU offloading** (if hardware permits):
   - Consider different iGPU or discrete GPU
   - gfx1153 not production-ready for ROCm

4. **TTS optimization**:
   - Consider faster TTS model
   - Pre-warm TTS engine

---

## Test Mode vs Live Mode

**Current measurements use `--test-input` mode which:**
- ✅ Accurately measures Whisper transcription
- ✅ Accurately measures LLM generation (now waits for completion)
- ✅ Bypasses real-time VAD (loads audio directly, shows minimal 50ms)
- ⚠️ TTS timing added but measures request send only (async, not synthesis time)

**For complete end-to-end measurement:**
- TTS synthesis time: Need to track Wyoming-Piper processing completion
- TTS playback time: Need to track audio playback duration
- Real VAD timing: Run without `--test-input` to measure actual VAD threshold wait time

---

## References

- NPU deployment success: commit 885011b9
- Eval kit docs: ~/git/ryzenai-embedded-eval-kit/LLAMA_CPP_IGPU_BUILD.md
- HSA override: commit 0a94b1c0
- Previous end-to-end tests: tests/results/test_report_20260316_155905.txt
