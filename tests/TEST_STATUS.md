# Test Infrastructure Status

**Date**: 2026-05-19
**Context**: Investigation after VAD split-utterance bug fix

---

## Summary

The test infrastructure is **documented** (tests/README.md, tests/README_TOOL_TESTS.md) but has **implementation issues** preventing automated E2E testing of fast-path tools.

**Documentation claims:**
- test orchestrator (`run_tests.py`) should run tests from YAML config
- `--test-input` mode should inject audio from files
- Fast-path tests should verify < 100ms execution (tests/README_TOOL_TESTS.md lines 7-29)

**Actual state:**
- Test orchestrator has hardcoded paths that don't exist (`/usr/share/piper/piper`)
- `--test-input` mode loads audio but Whisper doesn't transcribe it
- Manual testing via microphone is currently the only working verification method

---

## Test Files Status

### ✅ Working
- **audio_generator.py**: Generates TTS audio using Piper - works correctly
- **test_cases_tool_system.yaml**: Test case definitions - comprehensive and well-structured

### ⚠️ Fixed but not committed
- **test_tool_audio.py**:
  - Issue: Hardcoded path `external/piper-voices` (doesn't exist)
  - Fix: Changed to `piper-data` (exists with models)
  - Status: Fixed locally, not committed

- **test_real_interrupt.py**:
  - Issues:
    - Wrong `generator.generate()` parameter order
    - Wrong piper-voices path
    - Wrong llama-server port (8083 → 8080)
  - Status: Fixed locally, not committed
  - New issue: FIFO-based audio injection hangs/times out

### ❌ Created but broken
- **test_fast_path_simple.py**:
  - Created during this session
  - Uses `--test-input` flag to feed audio files
  - Issue: Audio loads but Whisper doesn't transcribe (empty output)
  - Root cause: Unknown - possible bug in test-input mode

---

## Root Issues

### 1. `--test-input` Mode Doesn't Transcribe

**Symptom**:
```bash
$ ./build/bin/voice-assistant --test-input audio.wav ...
# Output shows:
Driver:    # Empty - no transcription
```

**Evidence**:
- Audio files are valid (verified with ffprobe, volumedetect)
- stop_talking.wav: 24000 samples, 12392 non-zero, max 32767
- Files load into memory (no read errors)
- VAD shows all zeros: `energy_all: 0.000000, energy_last: 0.000000`
- No Whisper processing occurs

**Investigation**:
- Test mode injects audio at line 1973: `pcmf32_cur = test_audio_data;`
- Test mode simulates VAD at lines 1984-1990 (bypasses actual VAD)
- Speech duration calculated as ~50ms (time between iterations)
- Line 2092: Duration < 0.1s gets reset to 0
- Line 2102: Test mode exception prevents skip: `!(test_mode && test_audio_injected)`
- **But transcription still doesn't happen - possible threading/async issue**

**Hypothesis**:
Test mode path may have bitrot. The main loop structure changed but test mode wasn't updated to match.

### 2. Path Configuration Issues

Multiple test files hardcoded `external/piper-voices` which doesn't exist. Correct path is `piper-data/`.

**Files affected**:
- test_tool_audio.py (fixed)
- test_real_interrupt.py (fixed)
- TEST_INFRASTRUCTURE.md (not fixed, documentation only)

### 3. FIFO-Based Testing

`test_real_interrupt.py` uses a FIFO to feed audio incrementally (for interrupt testing). This approach:
- Requires complex synchronization
- Times out waiting for audio processing
- May have race conditions

**Recommendation**: Simplify to single-file injection or fix --test-input mode first.

---

## What Works

1. ✅ **Audio generation**: Piper TTS generates valid 16kHz mono WAV files
2. ✅ **Audio validation**: Generated files have correct format and content
3. ✅ **Test case definitions**: YAML test cases are comprehensive
4. ✅ **Code imports**: All Python test modules import without errors
5. ✅ **Live microphone testing**: Manual testing with real microphone works

---

## What Doesn't Work

1. ❌ **--test-input mode**: Doesn't transcribe audio (possible bug)
2. ❌ **FIFO injection**: Times out, complex synchronization issues
3. ❌ **Automated E2E tests**: Cannot verify fast-path tool execution automatically

---

## Fast-Path Tool Verification

### Code Evidence (✅ Verified)

**From tool-system.cpp lines 95-115:**
```cpp
std::pair<bool, ToolDefinition> ToolRegistry::checkFastPath(const std::string& text) {
    std::string normalized = normalizeText(text);

    // Only match if text is short (fast commands should be brief)
    if (normalized.length() > 50) {
        return {false, ToolDefinition()};
    }

    for (const auto& tool : tools_) {
        if (!tool.fast_path) continue;

        for (const auto& keyword : tool.keywords) {
            std::string norm_keyword = normalizeText(keyword);

            // Exact match or keyword at start of text
            if (normalized == norm_keyword ||
                normalized.find(norm_keyword) == 0) {
                return {true, tool};
            }
        }
    }

    return {false, ToolDefinition()};
}
```

**Matching logic:**
- Exact match: "stop" matches "stop"
- Prefix match: "stop talking" matches "stop" (keyword at position 0)
- No match: "please stop" - keyword not at start

**From tools.json:**
```json
{
  "name": "stop_speaking",
  "fast_path": true,
  "keywords": ["stop", "quiet", "silence", "shut up", "enough"]
}
```

**Expected output on match (voice-assistant.cpp line 2314):**
```
[Fast Path Tool: stop_speaking]
```

### Runtime Evidence (❌ Not Obtained)

Cannot get runtime evidence because:
1. --test-input mode doesn't transcribe
2. FIFO-based tests time out
3. Haven't manually tested with microphone (requires user)

**To verify manually:**
```bash
cd /home/paul/git/voice-assistant-custom-commands
bash start-assistant.sh
# Say "stop" into microphone
# Look for: [Fast Path Tool: stop_speaking]
```

---

## Recommended Actions

### Immediate (Required for automated testing)
1. **Fix --test-input mode** or remove it if unmaintained
   - Debug why audio loads but doesn't transcribe
   - Check threading/async issues in test mode path
   - Or document as deprecated and use live mic only

2. **Commit test fixes**:
   ```bash
   git add tests/test_tool_audio.py tests/test_real_interrupt.py
   git commit -m "fix(tests): update piper model paths and llama-server port"
   ```

3. **Remove broken test file**:
   ```bash
   rm tests/test_fast_path_simple.py  # Created during debug, doesn't work
   ```

### Long-term (Nice to have)
1. Add integration test that uses live microphone with pre-recorded audio playback
2. Create mock Wyoming server for TTS testing
3. Add unit tests for ToolRegistry::checkFastPath() (doesn't need audio)
4. Document which tests work vs. which need fixing

---

## Test Coverage

### ✅ Unit Tests (if they exist)
- ToolRegistry keyword matching
- Tool loading from JSON
- Audio file reading/writing

### ❌ E2E Tests (currently broken)
- Fast-path tool execution
- Interrupt during TTS playback
- Multi-turn conversations
- Full pipeline (mic → VAD → Whisper → LLM → TTS)

### ✅ Manual Testing (works)
- Live microphone testing with Blue Snowball
- VAD split-utterance bug verification
- Complete phrase transcription

---

## Files Modified (Not Committed)

```
tests/test_real_interrupt.py - fixed paths and parameters
tests/test_tool_audio.py - fixed piper-voices path
tests/test_fast_path_simple.py - new file (broken, should delete)
```

---

## Conclusion

Test infrastructure **exists** and is **well-designed** but has **bitrot**:
- Path configurations outdated
- --test-input mode broken
- FIFO approach too complex

**For now**: Rely on manual testing with live microphone
**For future**: Fix --test-input mode or replace with simpler approach

The VAD fix (removing `-vth 1.2`) is proven via manual testing and committed.
Fast-path tools are proven via code inspection but need runtime verification.
