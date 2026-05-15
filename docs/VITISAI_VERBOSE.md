# VitisAI NPU Verbose Output

## Issue

When using VitisAI NPU acceleration, you'll see this message on every inference:
```
whisper_vitisai_encode: Vitis AI model inference completed.
```

This happens multiple times per second during voice activity and cannot be disabled via compile flags.

## Why Can't It Be Disabled?

The message is in AMD's whisper.cpp fork at `external/whisper.cpp/src/vitisai/whisper-vitisai-encoder.cpp:197`

It uses raw `fprintf(stdout, ...)` instead of the whisper logging system, so there's no flag like `-DWHISPER_NO_LOGS` or similar to control it.

## How to Silence It (Optional)

If the noise bothers you, manually edit the submodule:

1. Edit `external/whisper.cpp/src/vitisai/whisper-vitisai-encoder.cpp`
2. Go to line 197 and comment out:
   ```cpp
   // std::fprintf(stdout, "%s: Vitis AI model inference completed.\n", __func__);
   ```
3. Rebuild:
   ```bash
   cmake --build build -j
   ```

**Note:** This change is local to your machine and will be lost if you run `git submodule update`.

## Future Fix

The proper fix would be to:
1. Fork AMD's whisper.cpp
2. Change line 197 to use `WHISPER_LOG_DEBUG()` instead of raw fprintf
3. Point our submodule to the fork

But for now, the manual edit approach is simplest.
