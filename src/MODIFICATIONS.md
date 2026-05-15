# Talk-LLaMA Custom Modifications

This directory contains the modified talk-llama application with TTS crash fixes and custom command support.

## Base Version

- **Upstream**: whisper.cpp/examples/talk-llama (included as submodule)
- **Base commit**: `d207c6882247984689091ae9d780d2e51eab1df7`
- **Original inspiration**: [talk-llama-fast](https://github.com/Mozer/talk-llama-fast) by Mozer

## Files

### Custom Files (This Directory)
- **`talk-llama.cpp`** - Modified main application (~3,500 lines)
  - TTS crash bugfixes
  - Custom command routing
  - CURL-based async TTS communication

### Upstream Files (From talk-llama-fast, originally from llama.cpp repo)
- **`llama.cpp`** - Full LLaMA inference engine from llama.cpp repository (~21K lines, 886KB)
- **`llama.h`** - LLaMA API header (56KB)
- **`unicode.cpp`** - Unicode text processing (30KB)
- **`unicode-data.cpp`** - Unicode data tables (165KB)
- **`console.cpp`** - Console utilities (18KB)
- **`console.h`** - Console header

**Note**: These are from the standalone llama.cpp repository, NOT from whisper.cpp's examples/talk-llama.
Mozer replaced whisper.cpp's simple llama integration with the full llama.cpp library for better performance.

## Key Modifications

### 1. TTS Crash Bugfixes (`talk-llama.cpp`)

**Problem**: The `send_tts_async()` function crashed when processing empty strings after regex/string cleaning operations.

**Fixes**:
- **Line ~818**: Added empty string check before accessing `text[0]`
- **Line ~828**: Added check after regex replacements
- **Line ~847-851**: Added `!text.empty()` checks before `text[text.size()-1]` access
- **Line ~860**: Fixed evaluation order - check size BEFORE accessing indices
- **Line ~864**: Added `!text.empty()` before `.back()` call
- **Line ~878**: Added NULL check for `curl_easy_init()`
- **Line ~891**: Added NULL check for `curl_multi_init()`
- **Line ~882**: Fixed memory leak - store and free curl_slist headers

**Result**: Prevents crashes from accessing invalid array indices or NULL pointers.

### 2. Safe String Handling

All string indexing operations now follow this pattern:
```cpp
// BEFORE (unsafe)
if (text[0] == '(' && text[text.size()-1] != ')') { ... }

// AFTER (safe)
if (!text.empty() && text[0] == '(' && text[text.size()-1] != ')') { ... }
```

### 3. CURL Error Handling

Added proper initialization checks and cleanup:
```cpp
CURL *http_handle = curl_easy_init();
if (!http_handle) {
    fprintf(stderr, "[TTS] ERROR: Failed to initialize CURL\n");
    curl_global_cleanup();
    return;
}
```

### 4. Memory Leak Fixes

Fixed curl_slist memory leak:
```cpp
// BEFORE (leak)
curl_easy_setopt(http_handle, CURLOPT_HTTPHEADER,
    curl_slist_append(nullptr, "Content-Type:application/json"));

// AFTER (proper cleanup)
struct curl_slist *headers = curl_slist_append(nullptr, "Content-Type:application/json");
curl_easy_setopt(http_handle, CURLOPT_HTTPHEADER, headers);
// ... use ...
curl_slist_free_all(headers);
```

## Building

This code is built via the root CMakeLists.txt which:
1. Builds whisper.cpp submodule
2. Compiles custom talk-llama.cpp with upstream llama.cpp/unicode.cpp
3. Links against whisper libraries

```bash
# From repository root
cmake -B build -DWHISPER_SDL2=ON
cmake --build build -j
```

Output: `build/bin/talk-llama-custom`

## Dependencies

- **whisper.cpp** (submodule) - Provides Whisper STT, GGML, common utilities
- **SDL2** - Audio input/output
- **CURL** - HTTP communication with TTS server
- **pthread** - Threading support

## Differences from Upstream

To see what's different from the base whisper.cpp talk-llama example:

```bash
cd ../../whisper.cpp/examples/talk-llama
diff -u talk-llama.cpp ../../../custom/talk-llama/talk-llama.cpp
```

## Testing

### Test TTS Crash Fixes

These should NOT crash:
```cpp
// Empty string
send_tts_async("", "emma_1", "en", "http://localhost:8020/");

// String that becomes empty after cleaning
send_tts_async("()", "emma_1", "en", "http://localhost:8020/");

// Single character
send_tts_async(".", "emma_1", "en", "http://localhost:8020/");

// Only punctuation
send_tts_async("!!!", "emma_1", "en", "http://localhost:8020/");
```

### Test CURL Error Handling

```bash
# Start with TTS server DOWN
./build/bin/talk-llama-custom -m model.gguf --model-whisper whisper.bin

# Should see error messages, not crash:
# "[TTS] ERROR: Failed to initialize CURL" or similar
```

## Known Issues

None currently. All previously crashing edge cases have been fixed.

## Future Enhancements

- [ ] Add more custom command types (beyond "stop")
- [ ] Implement command priority system
- [ ] Add command confirmation/acknowledgment
- [ ] Support for command parameters
- [ ] Command history/logging
- [ ] Configurable command keywords

## Credits

- **Original talk-llama**: whisper.cpp examples by Georgi Gerganov
- **talk-llama-fast**: Extended version by Mozer
- **Crash fixes**: Paul Mobbs (2024-2026)
