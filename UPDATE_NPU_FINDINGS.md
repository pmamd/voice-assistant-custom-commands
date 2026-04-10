# IMPORTANT UPDATE: AMD whisper.cpp Fork with NPU Support

## Critical Discovery

There IS an AMD fork of whisper.cpp with NPU support!

**Repository:** https://github.com/amd/whisper.cpp

## Key Information

### What It Is
- **C++ implementation** of Whisper with VitisAI NPU acceleration
- Uses FlexMLClient runtime (same as ONNX Runtime backend)
- Offloads **encoder only** to NPU
- Works with GGML/GGUF model format

### Current Status
**Windows:** ✅ Fully supported (as of now)
**Linux:** ⚠️ Code is present, but officially "Windows only" 

### Linux Support Investigation

**The code HAS Linux support built-in:**
```cpp
// From whisper-vitisai-encoder.cpp line 62-86
#else
    // Open the file
    FILE * fd = fopen(path, "rb");
    // ... Linux mmap implementation ...
    *buffer = (uint8_t *)mmap(nullptr, st.st_size, PROT_READ, MAP_SHARED, fileno(fd), 0);
#endif // _WIN32
```

**The Linux code paths exist!** The `#else` branches handle:
- Linux file I/O
- mmap for .rai files  
- munmap cleanup

### Why "Windows Only"?

Possible reasons Linux isn't officially supported yet:
1. **FlexMLClient runtime** - May not have Linux builds yet for flexmlrt 1.7.0
2. **Driver availability** - NPU drivers .280+ may be Windows-only currently
3. **Testing** - AMD may not have validated Linux yet
4. **XRT integration** - Needs coordination with XRT (which we have on .22)

### Architecture

```
whisper.cpp (C++) → VitisAI encoder backend → FlexMLClient → NPU
                  ↓ decoder stays on CPU
```

**Components:**
- `src/vitisai/whisper-vitisai-encoder.h` - Header
- `src/vitisai/whisper-vitisai-encoder.cpp` - Implementation  
- Uses `FlexMLClient.h` from FlexML runtime
- Loads `.rai` pre-compiled cache files (same as ONNX!)

### Build Configuration

```bash
cmake -B build -DWHISPER_VITISAI=1
cmake --build build -j --config Release
```

### Model Requirements

- Download `.rai` cache files from HuggingFace
- Place alongside GGML model files
- Naming: `ggml-<model>-encoder-vitisai.rai`
- Example: `ggml-small-encoder-vitisai.rai` + `ggml-small.bin`

### Performance Claims

"Significant speedup compared to CPU-only" with encoder on NPU.

### Comparison to ONNX Python Implementation

| Feature | AMD whisper.cpp | ONNX Python |
|---------|----------------|-------------|
| Language | C++ | Python |
| Encoder | NPU | NPU |
| Decoder | CPU | NPU (93.4%) |
| Format | GGML/GGUF | ONNX |
| Integration | Native | Subprocess/IPC |
| Linux | Code present, unofficial | Working |

## Potential Path Forward

### Option A: Try Building on Linux (Worth Testing!)

Even though docs say "Windows only", the code has Linux support:

```bash
# On .22
cd ~/test-whisper-npu
git clone https://github.com/amd/whisper.cpp
cd whisper.cpp

# Try building with VitisAI
cmake -B build -DWHISPER_VITISAI=1
cmake --build build -j --config Release
```

**Requirements (to investigate):**
- FlexMLClient library for Linux
- May be in RyzenAI SDK 1.7.1 already?
- Check `/home/amd/RyzenAI-Full/lib/` for FlexML libs

### Option B: Ask AMD / File Issue

The Linux code exists but may be:
- Untested
- Missing runtime dependencies
- Waiting for driver release

Could file GitHub issue asking about Linux status.

### Option C: Wait for Official Support

README says "Linux support is planned for upcoming releases"

## Why This Matters

If we can get AMD's whisper.cpp working on Linux:

**Advantages over ONNX Python:**
1. ✅ Native C++ integration (no subprocess)
2. ✅ Same GGUF models as GPU version
3. ✅ Encoder-only NPU (decoder stays fast on CPU)
4. ✅ Should be faster than full ONNX approach

**Advantages over current GPU:**
1. ⚠️ Potentially lower latency IF encoder NPU < 989ms GPU
2. ✅ Frees GPU for LLM
3. ✅ Lower power

## Action Items

1. ☐ Check if FlexMLClient libs exist on .22
   ```bash
   find /home/amd/RyzenAI-Full -name "*FlexML*" -o -name "*flexml*"
   ```

2. ☐ Try building AMD whisper.cpp on .22
   
3. ☐ Check for .rai model files for base.en
   - HuggingFace: https://huggingface.co/collections/amd/ryzen-ai-16-whisper-npu-optimized-onnx-models
   
4. ☐ Test if it works despite "Windows only" label

5. ☐ If not working, identify missing dependency

## Updated Recommendation

**Before:**
- NPU = Python ONNX only (9.2s)
- Not worth integrating

**Now:**
- AMD whisper.cpp may work on Linux
- Could be faster than Python approach
- Native C++ integration possible
- **Worth investigating!**

The existence of Linux code paths in the source suggests this may already work or be close to working.
