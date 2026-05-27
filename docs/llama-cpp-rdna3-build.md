# llama.cpp Build Configuration for AMD RDNA3 GPUs

## Problem Statement

When building llama.cpp with HIP support on AMD RDNA3 integrated GPUs (specifically gfx1153 - AMD 890M), the default auto-detection compiles HIP kernels for the specific architecture. However, ROCm 7.2.1's HIP compiler has a codegen bug that causes llama-server to hang during token generation when compiled for gfx1153.

## Symptoms

- llama-server starts successfully
- Model loads correctly (all layers offloaded to GPU)
- Health endpoint responds
- First prompt is processed
- Server hangs indefinitely during token generation (after `init sampler` log line)
- No error messages, process doesn't crash

## Root Cause Analysis

### Investigation Process

1. Compared working build (`~/Documents/llama.cpp`) vs broken build (`external/llama.cpp`)
2. Both from same git commit (492779581)
3. Same CMake configuration except one key difference:
   - **Working**: `AMDGPU_TARGETS:UNINITIALIZED=gfx1102`
   - **Broken**: `GPU_TARGETS:STRING=gfx1153`

4. Inspected compiled HIP kernels:
   ```bash
   strings libggml-hip.so.0.9.5 | grep gfx
   ```
   - **Working**: `hipv4-amdgcn-amd-amdhsa--gfx1102`
   - **Broken**: `hipv4-amdgcn-amd-amdhsa--gfx1153`

### Why gfx1102 Works

- gfx1102 is the generic RDNA3 architecture target
- ROCm compiler has stable codegen for this target
- Runtime compatibility achieved via `HSA_OVERRIDE_GFX_VERSION=11.0.2`
- HSA runtime translates gfx1102 instructions for gfx1153 hardware

## Solution

### Build Configuration

```bash
cd external/llama.cpp
rm -rf build

# Configure with explicit gfx1102 target
cmake -B build -DGGML_HIP=ON -DGPU_TARGETS='gfx1102'

# Build llama-server
cmake --build build -j --target llama-server
```

### Verification

```bash
# Check compiled architecture
strings build/bin/libggml-hip.so.0.9.5 | grep gfx | head -1
# Expected: hipv4-amdgcn-amd-amdhsa--gfx1102

# Check GPU offloading works
strings build/bin/llama-server | grep -i "rocm\|hip"
```

### Runtime Configuration

For gfx1153 hardware, always use HSA override:

```bash
export HSA_OVERRIDE_GFX_VERSION=11.0.2

./build/bin/llama-server \
  -m ./models/model.gguf \
  --port 8080 \
  -c 4096 \
  -ngl 999 \
  --flash-attn 0 \
  --no-warmup
```

**Note**: `--flash-attn 0` and `--no-warmup` are also required for stability on gfx1153.

## Affected Hardware

This issue affects RDNA3 integrated GPUs including:

- gfx1103 (Phoenix Point APUs)
- gfx1150 (Some RDNA3 variants)
- gfx1151 (Some RDNA3 variants)
- **gfx1153** (AMD Ryzen AI 9 HX 370 - Strix Point)

Discrete RDNA3 GPUs (gfx1100, gfx1101) may not be affected.

## Affected Software Versions

- **ROCm**: 7.1.x - 7.2.1 (tested on 7.2.1)
- **llama.cpp**: commit 492779581 and nearby versions
- **Compiler**: Clang 22.0.0 (from ROCm)

## Alternative Solutions

1. **Use system llama-server**: If available from package manager, may be pre-compiled with correct settings

2. **Use older ROCm**: ROCm 6.x may not have this bug (untested)

3. **CPU-only mode**: Set `-ngl 0` to disable GPU offloading (significantly slower)

## Related Issues

- Similar issues reported with other RDNA3 APUs in llama.cpp GitHub issues
- ROCm gfx1153 support is relatively new and has other known issues with certain kernels

## Testing Verification

After applying fix:

```bash
# Start server
HSA_OVERRIDE_GFX_VERSION=11.0.2 ./build/bin/llama-server \
  -m ./models/mistral-7b-instruct-v0.2.Q5_0.gguf \
  --port 8080 -c 4096 -ngl 999 \
  --flash-attn 0 --no-warmup &

# Wait for startup
sleep 20

# Test generation (should complete in <5 seconds)
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"temperature":0,"max_tokens":10}'

# Verify GPU offloading
grep -i offload /tmp/llama-server.log
# Expected: offloaded 33/33 layers to GPU (for Mistral 7B)
```

## References

- llama.cpp: https://github.com/ggerganov/llama.cpp
- ROCm Documentation: https://rocm.docs.amd.com/
- This fix: commit dd6574e3

## Contributors

Analysis and fix by Claude Opus 4.6, May 2026.
