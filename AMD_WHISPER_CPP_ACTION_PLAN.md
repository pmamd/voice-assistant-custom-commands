# AMD whisper.cpp NPU Integration - Action Plan

## Summary

Found AMD's fork of whisper.cpp with VitisAI NPU support:
- **Repo:** https://github.com/amd/whisper.cpp
- **Status:** Windows official, Linux code present but untested
- **Runtime:** FlexML 1.7.1 ✅ CONFIRMED on .22

## Why This Could Be Ideal

### Advantages Over Python ONNX
- ✅ Native C++ (no subprocess/Python overhead)
- ✅ Same GGUF model format (drop-in replacement)
- ✅ Encoder-only NPU (decoder stays fast on CPU)
- ✅ Should be faster than 9.2s Python approach

### Advantages Over GPU Only
- ✅ Frees GPU for LLM inference
- ✅ Lower power consumption
- ⚠️ *May* be faster if NPU encoder < 989ms GPU

## Current Status

**FlexML Runtime Found:**
```
Location: /home/amd/RyzenAI-Full/deployment/lib/libflexmlrt.so (4.1MB)
Headers: /home/amd/RyzenAI-Full/lib/python3.12/site-packages/flexmlrt/include/FlexMLClient.h
Version: flexmlrt 1.7.1
```

**Source Code:**
```
Local clone: /tmp/amd-whisper.cpp
Linux support: Code present (mmap, file I/O implemented)
Official status: "Windows only" (but worth trying!)
```

## Step-by-Step Plan

### Phase 1: Build Test (30 minutes)

**On .22, attempt build:**

```bash
ssh amd@192.168.86.26

# Create test directory
mkdir -p ~/whisper-npu-test
cd ~/whisper-npu-test

# Clone AMD fork
git clone https://github.com/amd/whisper.cpp
cd whisper.cpp

# Set up build with VitisAI support
export FLEXMLRT_ROOT=/home/amd/RyzenAI-Full
export CMAKE_PREFIX_PATH=$FLEXMLRT_ROOT/lib/python3.12/site-packages/flexmlrt:$FLEXMLRT_ROOT/deployment

cmake -B build \
  -DWHISPER_VITISAI=1 \
  -DCMAKE_C_FLAGS="-I$FLEXMLRT_ROOT/lib/python3.12/site-packages/flexmlrt/include" \
  -DCMAKE_CXX_FLAGS="-I$FLEXMLRT_ROOT/lib/python3.12/site-packages/flexmlrt/include" \
  -DCMAKE_EXE_LINKER_FLAGS="-L$FLEXMLRT_ROOT/deployment/lib -lflexmlrt"

cmake --build build -j
```

**Expected outcomes:**

✅ **Success:** Binary at `build/bin/whisper-cli`
- Proceed to Phase 2

⚠️ **Partial:** Builds but missing FlexML at runtime
- Check `LD_LIBRARY_PATH`, add `/home/amd/RyzenAI-Full/deployment/lib`

❌ **Failure:** FlexMLClient.h not found
- Need to investigate header path
- May need to copy headers to standard location

❌ **Failure:** Linking errors
- May need Windows-specific FlexML API
- Could require patching for Linux

### Phase 2: Download Models (15 minutes)

**Get .rai cache files:**

```bash
cd ~/whisper-npu-test/whisper.cpp

# Check HuggingFace collection
# https://huggingface.co/collections/amd/ryzen-ai-16-whisper-npu-optimized-onnx-models

# Download base.en model + .rai cache
# Look for: ggml-base.en.bin + ggml-base.en-encoder-vitisai.rai

# Place in models/
mkdir -p models
cd models

# Download from HuggingFace (exact URLs TBD)
# May need: huggingface-cli download amd/whisper-base-npu-rai
```

**Alternative if .rai not available:**
- Try with existing `ggml-base.en.bin`
- May auto-compile on first run (like ONNX)
- Could take ~15 minutes initial compilation

### Phase 3: Test Run (5 minutes)

```bash
cd ~/whisper-npu-test/whisper.cpp

# Set library path
export LD_LIBRARY_PATH=/home/amd/RyzenAI-Full/deployment/lib:$LD_LIBRARY_PATH

# Source XRT (NPU drivers)
source /opt/xilinx/xrt/setup.sh

# Test with sample audio
./build/bin/whisper-cli \
  -m models/ggml-base.en.bin \
  -f /tmp/test_voice_command.wav

# Look for:
# - VitisAI initialization messages
# - NPU encoder execution
# - Transcription output
# - Timing information
```

**Success indicators:**
- No "VitisAI not found" errors
- Encoder runs on NPU
- Transcription matches expected
- Total time < 9s (better than Python ONNX)

### Phase 4: Benchmark (10 minutes)

**Compare all three approaches:**

```bash
# 1. AMD whisper.cpp NPU
time ./build/bin/whisper-cli \
  -m models/ggml-base.en.bin \
  -f /tmp/test_voice_command.wav

# 2. GPU whisper.cpp (current)
time ~/voice-assistant-custom-commands/build/bin/main \
  -m ~/voice-assistant-custom-commands/whisper.cpp/models/ggml-base.en.bin \
  -f /tmp/test_voice_command.wav

# 3. Python ONNX NPU (baseline)
cd ~/RyzenAI-SW/Demos/ASR/Whisper
source ~/RyzenAI-Full/bin/activate
time python run_whisper.py \
  --model-type whisper-small \
  --device npu \
  --input /tmp/test_voice_command.wav
```

**Record:**
- Total time
- Transcription accuracy
- Any errors/warnings

### Phase 5: Integration Decision

**If AMD whisper.cpp works:**

**Scenario A: NPU faster than GPU (unlikely but possible)**
- Total time < 1.14s
- **Action:** Replace GPU whisper.cpp with NPU version
- Update `talk-llama` to use NPU binary

**Scenario B: NPU slower but acceptable (1-3s range)**
- Total time 1-3s
- **Action:** Add as optional backend
- Use GPU for real-time, NPU for batch

**Scenario C: NPU slower than Python ONNX (>9s)**
- Something wrong with build/config
- **Action:** Debug or wait for official Linux support

**If AMD whisper.cpp doesn't work:**
- Document blockers
- File GitHub issue with AMD
- Wait for official Linux release

## Troubleshooting Guide

### Build Errors

**"FlexMLClient.h: No such file"**
```bash
# Find the header
find /home/amd/RyzenAI-Full -name "FlexMLClient.h"

# Add to CMake
-DCMAKE_C_FLAGS="-I/path/to/include"
```

**"undefined reference to flexmlrt::*"**
```bash
# Check library exists
ls -la /home/amd/RyzenAI-Full/deployment/lib/libflexmlrt.so

# Add to linker
-DCMAKE_EXE_LINKER_FLAGS="-L/home/amd/RyzenAI-Full/deployment/lib -lflexmlrt -Wl,-rpath,/home/amd/RyzenAI-Full/deployment/lib"
```

### Runtime Errors

**"libflexmlrt.so: cannot open shared object file"**
```bash
export LD_LIBRARY_PATH=/home/amd/RyzenAI-Full/deployment/lib:$LD_LIBRARY_PATH
```

**"VitisAI backend not available"**
- Check XRT sourced: `source /opt/xilinx/xrt/setup.sh`
- Check NPU drivers: `xrt-smi examine`

**"No .rai cache file found"**
- Download from HuggingFace
- Place in models/ directory
- Match naming: `ggml-<model>-encoder-vitisai.rai`

## Success Criteria

**Minimum (worth pursuing):**
- ✅ Builds on Linux
- ✅ Runs without errors
- ✅ Produces correct transcription
- ✅ Time < 9s (better than Python)

**Ideal (production ready):**
- ✅ Time < 2s (competitive with GPU)
- ✅ Native integration (no LD_LIBRARY_PATH hacks)
- ✅ Stable across reboots
- ✅ No Python dependency

**Stretch goal:**
- ✅ Time < 1.14s (faster than GPU!)
- ✅ Drop-in replacement for current setup

## Timeline Estimate

| Phase | Time | Risk |
|-------|------|------|
| Build test | 30 min | Medium - may need CMake tweaks |
| Download models | 15 min | Low - straightforward |
| Test run | 5 min | Low - either works or doesn't |
| Benchmark | 10 min | Low - simple timing |
| **Total** | **~1 hour** | **Worth the investment!** |

## Recommendation

**✅ Proceed with testing!**

Reasons:
1. FlexML runtime confirmed present on .22
2. Linux code paths exist in source
3. Only 1 hour time investment
4. Potential for significant improvement
5. Even if slower than GPU, frees GPU for LLM

The worst case is we confirm it needs official Linux support and wait.
The best case is we get native C++ NPU integration working today!

## Next Actions

1. **Immediate:** Try Phase 1 build on .22
2. **If successful:** Complete phases 2-4
3. **Report findings:** Update this document with results
4. **Decide:** Integration path based on benchmark

Ready to proceed? 🚀
