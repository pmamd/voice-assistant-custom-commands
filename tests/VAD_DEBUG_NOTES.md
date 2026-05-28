# VAD Split-Utterance Bug - Debug Notes

**Issue**: Single spoken phrases are being split into multiple LLM prompts during live audio capture.

**Example**: User says "Navigate to the closest Starbucks near me" but system processes it as 2-3 separate prompts.

---

## The VAD Algorithm (vad_simple)

Located: `external/whisper.cpp/examples/common.cpp:610`

```
Compares energy in last N milliseconds vs whole buffer:
- energy_last > vad_thold * energy_all  →  still speaking (vad_result = 1)
- energy_last <= vad_thold * energy_all →  silence detected (vad_result = 2, triggers transcription)
```

**Current Settings**:
- `vad_last_ms = 700` (looking at last 700ms of audio)
- `vad_thold = 0.6` (last 700ms must have >60% of average energy to be considered "still speaking")
- Audio captured in 1-second chunks (`audio.get(1000, pcmf32_cur)`)

**Transcription Trigger**: Line 2055 in voice-assistant.cpp
```cpp
if (vad_result >= 2 && vad_result_prev == 1 || force_speak || user_typed.size())
```

---

## Root Cause Hypothesis

**NOT acoustic feedback** (microphone hearing speakers) - hardware test confirmed mic works correctly.

**Actual problem**: VAD is detecting false "end-of-speech" during natural pauses in speaking.

### The Flow
1. User starts speaking: "Navigate to the closest..."
2. Natural pause in speech (breath, thinking)
3. Energy in last 700ms drops below threshold
4. VAD triggers `vad_result = 2` (speech ended)
5. System immediately transcribes partial phrase → sends to LLM
6. User continues: "...Starbucks near me"
7. VAD detects new speech start → triggers AGAIN
8. Second transcription → second LLM call

**Key insight**: System doesn't wait to confirm silence - it trusts VAD immediately and proceeds with partial text while user is still speaking.

---

## What's Been Tried (All Failed)

### 1. Disabled early stop detection
- **Commit**: 7607e648
- **Result**: Did not fix - still getting splits

### 2. Increased vad-last-ms to 1500
- **Commit**: 89675ee8 (reverted in 8077bcfb)
- **Result**: Did not fix

### 3. Hard-coded delays after generation
- **Attempts**: 3s, 5s, 10s cooldown periods
- **Commits**: 053c2b15, c07ebb9a, d955515b (all rolled back)
- **Result**: Trying to solve acoustic feedback (wrong problem)

### 4. Pausing microphone during TTS
- **Commit**: 97cbbebc (rolled back)
- **Result**: Wrong problem - was addressing TTS feedback, not initial split

### 5. Continuous buffer clearing during cooldown
- **Commit**: c07ebb9a (rolled back)
- **Result**: Fluctuating results, not reliable

### 6. Tested different vad_thold values
- **Tested**: 0.4, 0.5, 0.7
- **Result**: Did not prevent splits

**Conclusion**: All attempts addressed symptoms (TTS feedback, timing) rather than root cause (VAD sensitivity to natural speech pauses).

---

## Debug Plan - Get Data First

Before trying more fixes, we need to understand EXACTLY what's happening at the moment of the split.

### 1. Add VAD Energy Logging
**Goal**: See actual energy values when VAD triggers

Add to voice-assistant.cpp around line 1993:
```cpp
bool is_speech = !::vad_simple(pcmf32_cur, WHISPER_SAMPLE_RATE,
                                params.vad_last_ms, params.vad_thold,
                                params.freq_thold, params.print_energy);

// ADD THIS:
if (params.debug || params.print_energy) {
    fprintf(stderr, "[VAD] is_speech=%d, vad_result_prev=%d, timestamp=%.3f\n",
            is_speech, vad_result_prev, get_current_time_ms());
}
```

Enable vad_simple verbose output (line 637-639 in common.cpp already logs energy_all, energy_last)

### 2. Log Audio Buffer State
**Goal**: See how much audio is queued when transcription starts

Add before transcription (around line 2055):
```cpp
if (vad_result >= 2 && vad_result_prev == 1) {
    fprintf(stderr, "[SPLIT-DEBUG] VAD triggered end-of-speech:\n");
    fprintf(stderr, "  - Audio buffer size: %zu samples (%.2fs)\n",
            pcmf32_cur.size(), pcmf32_cur.size() / (float)WHISPER_SAMPLE_RATE);
    fprintf(stderr, "  - Speech length: %.2fs\n", speech_len);
    fprintf(stderr, "  - Time since speech start: %.0fms\n",
            get_current_time_ms() - speech_start_ms);
}
```

### 3. Save Audio Chunks During Splits
**Goal**: Analyze actual waveform when splits occur

Add WAV export when split is detected:
```cpp
// Save audio chunk for analysis
static int split_counter = 0;
char wav_filename[256];
snprintf(wav_filename, sizeof(wav_filename),
         "tests/audio/debug/split_%03d_%.0fms.wav",
         split_counter++, get_current_time_ms());
// TODO: Add WAV export function
```

### 4. Log Early Stop Detector State
**Goal**: Is the 300-600ms burst detector interfering?

Around line 2012 (early stop logic):
```cpp
if (speech_duration_ms >= 300.0 && speech_duration_ms <= 600.0 && recent_energy > 0.01f) {
    early_trigger = true;
    // ALREADY HAS: fprintf for early stop trigger
    // ADD: Log when early stop is NOT triggered but speech is short
} else if (speech_duration_ms < 600.0) {
    fprintf(stderr, "[EARLY-STOP] Not triggered: dur=%.0fms, energy=%.6f (threshold: 0.01)\n",
            speech_duration_ms, recent_energy);
}
```

---

## Key Questions to Answer

1. **Is early stop firing incorrectly?**
   - Check logs: Are we seeing `[Early Stop Trigger]` messages during splits?

2. **What's the timing between VAD trigger and next audio?**
   - Log timestamps: How long after `vad_result=2` does next audio chunk arrive?

3. **Is 700ms window catching mid-phrase pauses?**
   - Analyze saved WAV files: Is there actually silence at split point?

4. **What's the energy drop pattern?**
   - Compare energy_last vs energy_all at split points
   - Is the ratio consistently near 0.6 threshold?

---

## Next Steps

1. Add instrumentation (sections 1-4 above)
2. Run VAD test: `bash tests/run_vad_test.sh`
3. Analyze logs and saved audio
4. Based on data, consider:
   - Hysteresis: Require X consecutive frames of silence before triggering
   - Confidence threshold: Wait for energy to drop below threshold for Y milliseconds
   - Look-ahead: After VAD triggers, wait 200ms to see if user continues
   - Adjust vad_last_ms window based on actual speech patterns

---

## Baseline

**Tag**: `vad-debug-baseline`
**Commit**: ad2fe3a7
**State**: Clean baseline with working hardware test, all acoustic feedback fixes rolled back

To return to baseline:
```bash
git checkout vad-debug-baseline
```
