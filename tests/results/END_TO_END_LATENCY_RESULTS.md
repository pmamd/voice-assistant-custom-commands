# End-to-End Latency Test Results

**Date:** 2026-04-17
**Test:** True end-to-end with TTS synthesis measurement
**Method:** Wyoming-Piper test mode (saves WAV files instead of playing)

---

## Dev Machine (192.168.86.74) - CPU Baseline

**Hardware:**
- CPU: AMD Ryzen with W6800 GPU (gfx1030)
- GPU: Used for LLM (Mistral 7B, 33/33 layers offloaded)
- Whisper: CPU only (ggml-base.en.bin)

**Results:**
```
Whisper transcription:     162 ms
LLM generation:           3930 ms
TTS synthesis:            4226 ms
─────────────────────────────────
TOTAL END-TO-END:         8318 ms
```

**Breakdown by %:**
- Whisper: 1.9%
- LLM: 47.2%
- TTS: 50.8%

**TTS Output:**
- 4 WAV files generated
- Total size: ~194 KB
- Represents chunked response synthesis

---

## Target Board (192.168.86.26) - Test Results

### Internal Latency (from latency_benchmark.sh)

Measured VAD → LLM completion (no TTS):

#### CPU Baseline
```
Whisper:             1737 ms
LLM generation:      7133 ms
─────────────────────────────
Total (VAD→LLM):     8871 ms
```

#### NPU + GPU
```
Whisper:              165 ms  ← NPU (10.5x faster)
LLM generation:      2630 ms  ← GPU (2.7x faster)
─────────────────────────────
Total (VAD→LLM):     2795 ms  (3.2x faster)
```

### Full End-to-End with TTS

**Not yet measured** - Wyoming-Piper not installed on .26

**Estimated based on dev machine ratio:**
- CPU baseline: ~8871ms (VAD→LLM) + ~4200ms (TTS) = **~13,000ms**
- NPU + GPU: ~2795ms (VAD→LLM) + ~4200ms (TTS) = **~7,000ms**

*Note: TTS synthesis time should be similar across machines (same Piper model)*

---

## Key Findings

### 1. TTS is a Major Component
On the dev machine, TTS synthesis takes **50.8%** of total time (4.2s out of 8.3s). This is comparable to LLM generation time.

### 2. NPU Provides Dramatic Whisper Speedup
- **10.5x faster** transcription (1737ms → 165ms)
- Whisper drops from 19.6% to 5.9% of total pipeline

### 3. GPU Accelerates LLM
- **2.7x faster** generation (7133ms → 2630ms)
- All 33/33 layers offloaded to iGPU

### 4. Combined NPU + GPU
- **3.2x faster** for Whisper + LLM combined
- Estimated **~46% faster end-to-end** including TTS (13s → 7s)

### 5. TTS Becomes the Bottleneck
With NPU + GPU:
- TTS: ~60% of total time
- LLM: ~38% of total time
- Whisper: ~2% of total time

---

## Optimization Priorities

Given the latency breakdown, priority order for optimization:

### 1. TTS Optimization (~4.2s → target <2s)
- **Higher priority** - now the dominant cost
- Options:
  - Faster TTS model (StyleTTS2, XTTS)
  - Streaming TTS (start playback before full synthesis)
  - Pre-warming TTS engine
  - Parallel synthesis for multi-sentence responses

### 2. LLM Optimization (~2.6s → target <1.5s)
- **Medium priority** - still significant
- Options:
  - Smaller model (3B instead of 7B)
  - Better quantization (Q3_K_S)
  - Speculative decoding
  - Context caching

### 3. Whisper Optimization (~165ms → target <100ms)
- **Lower priority** - already very fast with NPU
- Further gains minimal impact on total latency

---

## Test Infrastructure

### Wyoming-Piper Test Mode
The key to accurate TTS measurement is Wyoming-Piper's `--test-mode`:

```bash
wyoming-piper-custom \
    --piper ~/.local/bin/piper \
    --voice en_US-lessac-medium \
    --uri tcp://0.0.0.0:10200 \
    --test-mode \
    --test-output-dir ./audio/outputs/e2e_test
```

**How it works:**
1. TTS synthesis runs normally
2. Instead of playing audio, WAV files are saved
3. Test measures wall time until WAV files are written
4. Captures synthesis time without playback time

### Running the Test

**Dev machine (.74):**
```bash
python3 tests/end_to_end_latency.py           # CPU baseline
python3 tests/end_to_end_latency.py --npu     # With NPU
```

**Target board (.26):**
```bash
# First install Wyoming-Piper
# Then run same commands
```

---

## Architecture

See `docs/latency-test-architecture.svg` for visual diagram of test flow.

**Pipeline:**
```
Audio → talk-llama-custom → Whisper → LLM → Wyoming-Piper → WAV files
 (t=0)                                                          (t=end)
```

**What is measured:**
- **Whisper**: Transcription time (logged internally)
- **LLM**: Generation time (logged internally)
- **TTS**: Wall time - (Whisper + LLM)
- **Total**: Wall time from process start to WAV file written

---

## Next Steps

1. **Install Wyoming-Piper on .26** for full end-to-end testing
2. **Baseline NPU end-to-end** on target board
3. **Investigate TTS optimization** (now the bottleneck)
4. **Test with different LLM models** (3B vs 7B)
5. **Implement streaming TTS** if feasible

---

## References

- Internal latency: `tests/results/LATENCY_BREAKDOWN.md`
- Test architecture: `docs/latency-test-architecture.svg`
- Benchmark script: `tests/latency_benchmark.sh`
- End-to-end test: `tests/end_to_end_latency.py`
- NPU deployment: commit 885011b9
