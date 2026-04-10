# NPU Whisper Investigation Summary

## Performance Testing Results

### Test Audio
- File: "Tell me a story" (1.2 seconds)
- Expected: "Tell me a story"
- Both transcribed: "Tell me the story."

### NPU (whisper-small ONNX + VitisAI)
- **Total time:** 9.2 seconds
- **TTFT:** 50ms
- **RTF:** 0.64
- **Implementation:** Python + ONNX Runtime 1.23.3

### GPU (whisper.cpp base.en + ROCm)
- **Total time:** 1.14 seconds  
- **Encode:** 989ms
- **Decode:** 43ms
- **Implementation:** C++ + HIP

### Verdict: GPU is 8x faster for voice commands

## NPU Implementation Analysis

### What We Found

**ONNX Runtime + VitisAI Available:**
- ✓ ONNX Runtime 1.23.3.dev20260320
- ✓ VitisAIExecutionProvider available
- ✓ Shared libraries: `libonnxruntime.so.1.23.3`
- ✓ VitisAI EP: `libonnxruntime_vitisai_ep.so` (41MB)
- ✓ Pre-compiled NPU cache: `whisper_small_encoder.rai` (108MB)

**Integration Paths:**

1. **Python Subprocess (Easiest)**
   - Call `run_whisper.py` from C++
   - Pros: Zero code changes
   - Cons: 9.2s latency unacceptable for real-time

2. **ONNX Runtime C API (Native)**
   - Link against `libonnxruntime.so`
   - Pros: Lower overhead, native C++
   - Cons: Need C headers (not found yet), complex API
   
3. **Hybrid GPU+NPU (Future)**
   - GPU encoder + NPU decoder
   - Complexity not worth it currently

### Key Files Created

- `WHISPER_NPU_PERFORMANCE.md` - Performance comparison
- `NPU_INTEGRATION_ANALYSIS.md` - Technical deep dive

## Recommendation

**Keep GPU whisper.cpp for voice assistant**
- Sub-second latency is critical
- Already integrated with C++ codebase  
- 8x faster than NPU

**Consider NPU for future features:**
- Long-form transcription (meetings, podcasts)
- Batch processing
- Power-constrained scenarios
- When GPU is busy with LLM

## Branch Status

- ✅ Created `whisper-npu` branch
- ✅ Performance testing complete
- ✅ NPU implementation explored
- ✅ Integration paths documented

**Next:** Decide whether to:
1. Keep this as documentation only
2. Prototype Python subprocess wrapper
3. Investigate ONNX Runtime C++ headers for native integration
