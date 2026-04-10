# NPU Quiet Mode Patch

## Issue

AMD whisper.cpp fork prints noisy debug messages on every NPU inference:
```
whisper_vitisai_encode: Vitis AI model inference completed.
```

This floods the output during continuous voice operation.

## Solution

Comment out line 197 in `whisper.cpp/src/vitisai/whisper-vitisai-encoder.cpp`:

```bash
sed -i 's|std::fprintf(stdout, "%s: Vitis AI model inference completed|// &  // Suppressed: too noisy|' \
  whisper.cpp/src/vitisai/whisper-vitisai-encoder.cpp
```

Then rebuild:
```bash
cmake --build build -j
```

## Applied To

- ✅ Dev machine (.74): ~/git/voice-assistant-custom-commands
- ✅ Target machine (.22): ~/voice-assistant-custom-commands

## Note

This is a local patch to the AMD submodule. It will be reset if you run `git submodule update --force`.
To reapply after submodule updates:
```bash
sed -i '197s|std::fprintf(stdout, "%s: Vitis AI model inference completed|// &  // Suppressed: too noisy|' \
  whisper.cpp/src/vitisai/whisper-vitisai-encoder.cpp
cmake --build build -j
```
