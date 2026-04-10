# NPU Whisper Integration Plan

## Overview

Replace GPU whisper.cpp with AMD's NPU-enabled fork for 2x+ performance improvement.

**Current:** whisper.cpp with ROCm/HIP (GPU) - 1140ms
**Target:** whisper.cpp with VitisAI (NPU) - 500ms

---

## Prerequisites ✅

- ✅ NPU whisper.cpp built and tested on .22
- ✅ FlexML runtime 1.7.1 available
- ✅ XRT drivers functional
- ✅ Performance validated (2x faster than GPU)
- ✅ Model compatibility confirmed

---

## Phase 1: Integrate AMD Fork (Dev Machine)

### 1.1 Replace whisper.cpp Submodule

**Current state:**
```bash
git submodule status
# whisper.cpp @ some commit from ggerganov/whisper.cpp
```

**Action:**
```bash
cd ~/git/voice-assistant-custom-commands

# Remove current submodule
git submodule deinit whisper.cpp
git rm whisper.cpp
rm -rf .git/modules/whisper.cpp

# Add AMD fork as submodule
git submodule add https://github.com/amd/whisper.cpp whisper.cpp
cd whisper.cpp
git checkout master  # or specific stable tag if available
cd ..

git add .gitmodules whisper.cpp
git commit -m "Replace whisper.cpp with AMD fork for NPU support"
```

**Estimated time:** 15 minutes

### 1.2 Update CMakeLists.txt

**File:** `CMakeLists.txt` (root)

**Find section:**
```cmake
add_subdirectory(whisper.cpp)
```

**Replace with:**
```cmake
# AMD whisper.cpp with VitisAI NPU support
option(WHISPER_VITISAI "Enable VitisAI NPU backend" OFF)

if(WHISPER_VITISAI)
    # FlexML runtime paths for .22 target
    set(FLEXMLRT_ROOT "/home/amd/RyzenAI-Full" CACHE PATH "FlexML runtime root")
    set(CMAKE_PREFIX_PATH "${FLEXMLRT_ROOT}/lib/python3.12/site-packages/flexmlrt;${FLEXMLRT_ROOT}/deployment")

    # Include FlexML headers
    include_directories("${FLEXMLRT_ROOT}/lib/python3.12/site-packages/flexmlrt/include")

    # Link FlexML library
    link_directories("${FLEXMLRT_ROOT}/deployment/lib")
endif()

add_subdirectory(whisper.cpp)

if(WHISPER_VITISAI)
    target_link_libraries(whisper PRIVATE flexmlrt)
    # Add rpath so runtime can find libflexmlrt.so
    set_target_properties(whisper PROPERTIES
        INSTALL_RPATH "${FLEXMLRT_ROOT}/deployment/lib"
        BUILD_RPATH "${FLEXMLRT_ROOT}/deployment/lib"
    )
endif()
```

**Estimated time:** 20 minutes

### 1.3 Download NPU Models

**Action on .22:**
```bash
ssh amd@192.168.86.22 'bash -s' << 'ENDSSH'
cd ~/Projects/git/talk-llama-fast/whisper.cpp/models

# Download base model (multilingual, required for NPU)
./download-ggml-model.sh base

# Download NPU cache from HuggingFace
wget https://huggingface.co/amd/whisper-base-onnx-npu/resolve/main/ggml-base-encoder-vitisai.rai

# Verify
ls -lh ggml-base.bin ggml-base-encoder-vitisai.rai
ENDSSH
```

**Expected output:**
```
-rw-rw-r-- 1 amd amd 142M ggml-base.bin
-rw-rw-r-- 1 amd amd  25M ggml-base-encoder-vitisai.rai
```

**Estimated time:** 10 minutes (download)

### 1.4 Test Build on Dev Machine

**Note:** Dev machine (.74) doesn't have NPU, so build WITHOUT VitisAI:

```bash
cd ~/git/voice-assistant-custom-commands

# Configure without NPU (dev machine doesn't have FlexML)
cmake -B build -DWHISPER_SDL2=ON -DWHISPER_VITISAI=OFF

# Build
cmake --build build -j

# Verify binary still works
./build/bin/talk-llama-custom --help
```

**Expected:** Builds successfully, no VitisAI dependency on dev machine.

**Estimated time:** 5 minutes

---

## Phase 2: Build and Test on Target (.22)

### 2.1 Deploy to Target

```bash
# From dev machine
cd ~/git/voice-assistant-custom-commands
git push

# On target
ssh amd@192.168.86.22 'bash -s' << 'ENDSSH'
cd ~/Projects/git/talk-llama-fast
git pull

# Configure WITH VitisAI
export FLEXMLRT_ROOT=/home/amd/RyzenAI-Full
cmake -B build -DWHISPER_SDL2=ON -DWHISPER_VITISAI=ON

# Build
cmake --build build -j
ENDSSH
```

**Expected output:**
```
-- Whisper VitisAI: Enabled
-- Found FlexML runtime at /home/amd/RyzenAI-Full
...
[100%] Built target talk-llama-custom
```

**Estimated time:** 10 minutes

### 2.2 Test NPU Inference

```bash
ssh amd@192.168.86.22 'bash -s' << 'ENDSSH'
cd ~/Projects/git/talk-llama-fast

# Set up environment
export LD_LIBRARY_PATH=/home/amd/RyzenAI-Full/deployment/lib:$LD_LIBRARY_PATH
source /opt/xilinx/xrt/setup.sh

# Test with base model
./build/bin/talk-llama-custom \
  --model models/mistral-7b-instruct-v0.2.Q5_0.gguf \
  --whisper-model whisper.cpp/models/ggml-base.bin \
  --prompt "Test NPU whisper"
ENDSSH
```

**Expected output:**
```
whisper_init_state: Vitis AI model loaded
whisper_vitisai_encode: Vitis AI model inference completed.
[speak something]
[correct transcription in ~500ms]
```

**Estimated time:** 5 minutes

### 2.3 Benchmark Comparison

**Create benchmark script:** `benchmark_whisper_npu.sh`

```bash
#!/bin/bash
# Compare GPU vs NPU whisper performance

cd ~/Projects/git/talk-llama-fast

# Create test audio
echo "Recording 2 seconds of audio..."
arecord -d 2 -f S16_LE -r 16000 /tmp/benchmark_audio.wav

echo ""
echo "=== GPU Benchmark (current build) ==="
# Use current binary (if still have GPU build)
time ./build/bin/talk-llama-custom \
  --whisper-model whisper.cpp/models/ggml-base.en.bin \
  -f /tmp/benchmark_audio.wav 2>&1 | grep "encode time"

echo ""
echo "=== NPU Benchmark (new build) ==="
export LD_LIBRARY_PATH=/home/amd/RyzenAI-Full/deployment/lib:$LD_LIBRARY_PATH
source /opt/xilinx/xrt/setup.sh
time ./build/bin/talk-llama-custom \
  --whisper-model whisper.cpp/models/ggml-base.bin \
  -f /tmp/benchmark_audio.wav 2>&1 | grep "encode time"
```

**Run:**
```bash
ssh amd@192.168.86.22 'bash benchmark_whisper_npu.sh'
```

**Expected:** NPU ~500ms, confirms 2x improvement

**Estimated time:** 10 minutes

---

## Phase 3: Update Runtime Configuration

### 3.1 Update Startup Scripts

**File:** Startup script or systemd service on .22

**Add environment setup:**
```bash
# NPU Whisper runtime
export LD_LIBRARY_PATH=/home/amd/RyzenAI-Full/deployment/lib:$LD_LIBRARY_PATH
source /opt/xilinx/xrt/setup.sh

# Run talk-llama
./build/bin/talk-llama-custom \
  --model models/mistral-7b-instruct-v0.2.Q5_0.gguf \
  --whisper-model whisper.cpp/models/ggml-base.bin \
  ...
```

**Estimated time:** 10 minutes

### 3.2 Update Documentation

**Files to update:**
- `DEV_SETUP.md` - Add NPU build instructions
- `README.md` - Update requirements section
- `CLAUDE.md` - Document NPU dependency

**Key points:**
- FlexML runtime required on target
- XRT must be sourced
- LD_LIBRARY_PATH must include FlexML
- Use ggml-base.bin (not base.en) with NPU

**Estimated time:** 15 minutes

### 3.3 Update Tests

**Files:** `tests/test_*.py`

**Change:**
```python
# Old
self.whisper_model = project_root / "whisper.cpp/models/ggml-base.en.bin"

# New (for NPU target)
self.whisper_model = project_root / "whisper.cpp/models/ggml-base.bin"
```

**Note:** Tests run on dev machine (.74) which doesn't have NPU, so they'll use CPU fallback with ggml-base.bin. This is acceptable.

**Estimated time:** 10 minutes

---

## Phase 4: Optimization (Future)

### 4.1 Test Small Model

**Try ggml-small.bin for better accuracy:**
```bash
# Download model
./models/download-ggml-model.sh small

# Download .rai cache
wget https://huggingface.co/amd/whisper-small-onnx-npu/resolve/main/ggml-small-encoder-vitisai.rai

# Test
./build/bin/talk-llama-custom --whisper-model whisper.cpp/models/ggml-small.bin ...
```

**Expected:** Better accuracy, possibly still faster than current GPU base.en

**Estimated time:** 30 minutes

### 4.2 Profile Power Consumption

**Use AMD's tools to measure NPU vs GPU power:**
```bash
# NPU power
amd-smi power --watch 1  # or equivalent tool

# Compare to GPU power measurements
```

**Goal:** Quantify power savings

**Estimated time:** 1 hour

### 4.3 Test Long Audio

**Benchmark with 30s, 60s, 5min audio:**
```bash
# Generate long test audio
ffmpeg -f lavfi -i "sine=frequency=1000:duration=60" -ar 16000 test_60s.wav

# Benchmark NPU
time ./build/bin/talk-llama-custom --whisper-model ggml-base.bin -f test_60s.wav
```

**Goal:** Confirm NPU scales well with longer audio

**Estimated time:** 30 minutes

---

## Rollback Plan

### If NPU Integration Fails

**Option 1: Quick Rollback**
```bash
git checkout master
git submodule update --init --recursive
cmake --build build -j
```

**Option 2: Keep Both Builds**
```cmake
# Add build option
option(USE_NPU_WHISPER "Use NPU for Whisper" ON)

if(USE_NPU_WHISPER)
    # NPU path
else()
    # GPU path (existing)
endif()
```

**Option 3: Runtime Selection**
```bash
# Use GPU
./talk-llama-custom --whisper-backend gpu --whisper-model ggml-base.en.bin

# Use NPU
./talk-llama-custom --whisper-backend npu --whisper-model ggml-base.bin
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Build fails on .74 | Low | Low | Use -DWHISPER_VITISAI=OFF on dev machine |
| Runtime crash on .22 | Low | Medium | Keep GPU build as backup |
| Model incompatibility | Low | Low | Already tested, ggml-base.bin works |
| Performance regression | Very Low | Medium | Benchmarked at 2x improvement |
| FlexML dependency issues | Low | Medium | Runtime already installed and tested |

**Overall risk:** Low - NPU already proven working

---

## Success Criteria

### Minimum (Production Ready)
- ✅ Builds on both .74 (dev) and .22 (target)
- ✅ NPU inference works on .22
- ✅ Transcription accuracy matches GPU
- ✅ Performance >= GPU (currently 2x better)
- ✅ No crashes or errors
- ✅ Tests pass

### Ideal (Full Integration)
- ✅ All of minimum criteria
- ✅ Documentation updated
- ✅ Startup scripts configured
- ✅ Power consumption measured
- ✅ Long audio tested

### Stretch (Enhanced)
- Test ggml-small.bin for better accuracy
- Profile power vs GPU
- Compare thermal behavior
- Add runtime backend selection

---

## Timeline

| Phase | Tasks | Estimated Time | Cumulative |
|-------|-------|----------------|------------|
| **Phase 1** | Replace submodule, update CMake, download models, test build | 50 min | 50 min |
| **Phase 2** | Deploy, build on .22, test NPU, benchmark | 25 min | 1h 15m |
| **Phase 3** | Update scripts, docs, tests | 35 min | 1h 50m |
| **Phase 4** | Optimization (optional) | 2 hours | 3h 50m |
| **Total (core)** | Phases 1-3 only | **~2 hours** | |
| **Total (full)** | All phases | **~4 hours** | |

---

## Checklist

### Phase 1: Dev Machine Integration
- [ ] Replace whisper.cpp submodule with AMD fork
- [ ] Update CMakeLists.txt for VitisAI option
- [ ] Download models on .22 (ggml-base.bin + .rai)
- [ ] Test build on .74 (without NPU)
- [ ] Commit changes

### Phase 2: Target Testing
- [ ] Push to git
- [ ] Pull on .22
- [ ] Build with -DWHISPER_VITISAI=ON
- [ ] Test NPU inference
- [ ] Run benchmark comparison
- [ ] Verify 2x performance improvement

### Phase 3: Configuration
- [ ] Update startup scripts with env vars
- [ ] Update DEV_SETUP.md
- [ ] Update README.md
- [ ] Update CLAUDE.md
- [ ] Update test files to use ggml-base.bin
- [ ] Run tests on dev machine
- [ ] Commit configuration changes

### Phase 4: Optimization (Optional)
- [ ] Test ggml-small.bin
- [ ] Measure power consumption
- [ ] Test long audio files
- [ ] Document findings

---

## Next Steps

1. **Immediate:** Review this plan
2. **Start Phase 1:** Replace whisper.cpp submodule
3. **Test:** Build on both machines
4. **Validate:** Confirm NPU performance on .22
5. **Deploy:** Update production configuration

**Ready to begin integration!** 🚀
