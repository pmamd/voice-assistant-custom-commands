# VAD Split-Utterance Systematic Debug Plan

**Goal**: Root cause the VAD split-utterance bug using automated testing with real hardware.

**No human involvement required** - all tests run automatically using:
- Wyoming-Piper to play test audio through speakers
- Blue Snowball microphone to capture audio
- Automated log analysis to detect patterns

---

## Phase 1: Add Instrumentation (15 min)

### 1.1 Enable VAD Energy Logging
**File**: `src/voice-assistant.cpp` around line 1993

Add after vad_simple call:
```cpp
bool is_speech = !::vad_simple(pcmf32_cur, WHISPER_SAMPLE_RATE,
                                params.vad_last_ms, params.vad_thold,
                                params.freq_thold, true); // Force verbose

fprintf(stderr, "[VAD-DEBUG] t=%.3f is_speech=%d prev=%d buf_samples=%zu (%.2fs)\n",
        get_current_time_ms(), is_speech, vad_result_prev,
        pcmf32_cur.size(), pcmf32_cur.size() / (float)WHISPER_SAMPLE_RATE);
```

### 1.2 Log When VAD Triggers End-of-Speech
**File**: `src/voice-assistant.cpp` around line 2055

Add before transcription starts:
```cpp
if (vad_result >= 2 && vad_result_prev == 1) {
    fprintf(stderr, "\n=== VAD TRIGGERED END-OF-SPEECH ===\n");
    fprintf(stderr, "[SPLIT-DEBUG] Timestamp: %.3f\n", get_current_time_ms());
    fprintf(stderr, "[SPLIT-DEBUG] Speech duration: %.0fms\n",
            get_current_time_ms() - speech_start_ms);
    fprintf(stderr, "[SPLIT-DEBUG] Buffer size: %zu samples (%.2fs)\n",
            pcmf32.size(), pcmf32.size() / (float)WHISPER_SAMPLE_RATE);
    fprintf(stderr, "[SPLIT-DEBUG] vad_result: %d -> 2 (END)\n", vad_result_prev);
    fprintf(stderr, "===================================\n\n");
}
```

### 1.3 Log Early Stop Detector
**File**: `src/voice-assistant.cpp` around line 2012

Already logs when triggered. Add logging when NOT triggered:
```cpp
if (speech_duration_ms >= 300.0 && speech_duration_ms <= 600.0 && recent_energy > 0.01f) {
    early_trigger = true;
    if (params.print_energy) {
        fprintf(stderr, "\n[EARLY-STOP] TRIGGERED: dur=%.0fms, energy=%.6f\n",
                speech_duration_ms, recent_energy);
    }
} else if (is_speech && speech_duration_ms < 1000.0) {
    // Log why early stop didn't trigger for short utterances
    fprintf(stderr, "[EARLY-STOP] Not triggered: dur=%.0fms, energy=%.6f\n",
            speech_duration_ms, recent_energy);
}
```

### 1.4 Save Audio When Splits Occur
**File**: `src/voice-assistant.cpp` around line 2055

```cpp
// Save audio for post-analysis when we detect short speech (potential split)
if (vad_result >= 2 && vad_result_prev == 1 && speech_len < 2.0) {
    static int split_counter = 0;
    char wav_filename[256];
    snprintf(wav_filename, sizeof(wav_filename),
             "tests/audio/debug/split_%03d_dur%.0fms.wav",
             split_counter++, speech_len * 1000);

    // Write WAV file
    FILE* f = fopen(wav_filename, "wb");
    if (f) {
        // WAV header
        fwrite("RIFF", 1, 4, f);
        uint32_t chunk_size = 36 + pcmf32.size() * 2;
        fwrite(&chunk_size, 4, 1, f);
        fwrite("WAVE", 1, 4, f);
        fwrite("fmt ", 1, 4, f);
        uint32_t subchunk1_size = 16;
        fwrite(&subchunk1_size, 4, 1, f);
        uint16_t audio_format = 1;
        fwrite(&audio_format, 2, 1, f);
        uint16_t num_channels = 1;
        fwrite(&num_channels, 2, 1, f);
        uint32_t sample_rate = WHISPER_SAMPLE_RATE;
        fwrite(&sample_rate, 4, 1, f);
        uint32_t byte_rate = WHISPER_SAMPLE_RATE * 2;
        fwrite(&byte_rate, 4, 1, f);
        uint16_t block_align = 2;
        fwrite(&block_align, 2, 1, f);
        uint16_t bits_per_sample = 16;
        fwrite(&bits_per_sample, 2, 1, f);
        fwrite("data", 1, 4, f);
        uint32_t subchunk2_size = pcmf32.size() * 2;
        fwrite(&subchunk2_size, 4, 1, f);

        // Convert float to int16 and write
        for (float sample : pcmf32) {
            int16_t s = (int16_t)(sample * 32767.0f);
            fwrite(&s, 2, 1, f);
        }
        fclose(f);
        fprintf(stderr, "[SPLIT-DEBUG] Saved audio to %s\n", wav_filename);
    }
}
```

### 1.5 Create Debug Output Directory
```bash
mkdir -p tests/audio/debug
```

**Build**:
```bash
cd /home/paul/git/voice-assistant-custom-commands
cmake --build build -j
```

---

## Phase 2: Automated Test Execution (5 min)

### 2.1 Update VAD Test for Debug Mode

**File**: `tests/run_vad_test.sh`

Add debug flags:
```bash
# Enable all debug output
$TALK_LLAMA_BIN \
    -mw "$WHISPER_MODEL" \
    --llama-url "$LLAMA_SERVER_URL" \
    --xtts-url "http://localhost:$WYOMING_PORT/" \
    --xtts-voice "$PIPER_VOICE" \
    --temp 0.5 \
    -vth 1.2 \
    -n 300 \
    --allow-newline \
    -p Driver \
    -c "$CAPTURE_DEVICE" \
    --language en \
    --print-energy \
    --debug \
    --test-input "$TEST_AUDIO" \
    > "$TEST_OUTPUT" 2>&1 &
```

### 2.2 Run Test
```bash
cd /home/paul/git/voice-assistant-custom-commands
bash tests/run_vad_test.sh 2>&1 | tee tests/audio/debug/vad_test_log.txt
```

This will:
1. Play "Navigate to the closest Starbucks near me" through speakers
2. Capture via Blue Snowball mic
3. Log all VAD energy values
4. Save audio chunks when splits occur
5. Output detailed timing information

---

## Phase 3: Automated Log Analysis (10 min)

### 3.1 Create Log Parser Script

**File**: `tests/analyze_vad_logs.py`

```python
#!/usr/bin/env python3
"""
Parse VAD debug logs to identify split patterns.
"""
import re
import sys
from pathlib import Path

def parse_vad_log(log_file):
    """Extract VAD events from log file."""
    with open(log_file) as f:
        content = f.read()

    # Find all VAD debug entries
    vad_entries = re.findall(
        r'\[VAD-DEBUG\] t=([\d.]+) is_speech=(\d) prev=(\d) buf_samples=(\d+) \(([\d.]+)s\)',
        content
    )

    # Find vad_simple energy values
    energy_entries = re.findall(
        r'vad_simple: energy_all: ([\d.]+), energy_last: ([\d.]+), vad_thold: ([\d.]+)',
        content
    )

    # Find split events
    splits = re.findall(
        r'=== VAD TRIGGERED END-OF-SPEECH ===.*?'
        r'Speech duration: ([\d.]+)ms.*?'
        r'Buffer size: (\d+) samples',
        content,
        re.DOTALL
    )

    # Find early stop triggers
    early_stops = re.findall(
        r'\[EARLY-STOP\] (TRIGGERED|Not triggered): dur=([\d.]+)ms, energy=([\d.]+)',
        content
    )

    # Find transcriptions
    transcriptions = re.findall(
        r'Georgi: (.+?)(?:\n|$)',
        content
    )

    return {
        'vad_entries': vad_entries,
        'energy_entries': energy_entries,
        'splits': splits,
        'early_stops': early_stops,
        'transcriptions': transcriptions
    }

def analyze_splits(data):
    """Analyze split patterns."""
    print("\n=== SPLIT ANALYSIS ===\n")
    print(f"Total transcriptions detected: {len(data['transcriptions'])}")
    print(f"Total VAD end-of-speech events: {len(data['splits'])}")
    print(f"Early stop triggers: {sum(1 for e in data['early_stops'] if e[0] == 'TRIGGERED')}")

    if len(data['transcriptions']) > 1:
        print(f"\n⚠️  SPLIT DETECTED - {len(data['transcriptions'])} separate prompts:")
        for i, text in enumerate(data['transcriptions'], 1):
            print(f"  {i}. '{text}'")

    print("\n=== VAD STATE TRANSITIONS ===\n")
    prev_state = None
    for t, is_speech, prev, buf_samples, buf_sec in data['vad_entries']:
        curr_state = 'SPEECH' if is_speech == '1' else 'SILENCE'
        if prev_state != curr_state:
            print(f"t={t}s: {prev_state or 'START'} -> {curr_state} (buffer: {buf_sec}s)")
            prev_state = curr_state

    print("\n=== ENERGY ANALYSIS ===\n")
    for i, (e_all, e_last, threshold) in enumerate(data['energy_entries']):
        ratio = float(e_last) / float(e_all) if float(e_all) > 0 else 0
        threshold_val = float(threshold)
        silence_detected = ratio <= threshold_val
        print(f"Sample {i}: energy_all={e_all}, energy_last={e_last}, "
              f"ratio={ratio:.3f}, threshold={threshold_val}, "
              f"{'SILENCE' if silence_detected else 'SPEECH'}")

    print("\n=== SPLIT EVENTS ===\n")
    for duration, buf_size in data['splits']:
        print(f"VAD triggered after {duration}ms, buffer had {buf_size} samples")

    print("\n=== EARLY STOP EVENTS ===\n")
    for status, duration, energy in data['early_stops']:
        print(f"{status}: duration={duration}ms, energy={energy}")

if __name__ == '__main__':
    log_file = sys.argv[1] if len(sys.argv) > 1 else 'tests/audio/debug/vad_test_log.txt'

    print(f"Analyzing {log_file}...")
    data = parse_vad_log(log_file)
    analyze_splits(data)

    # Summary
    print("\n" + "="*60)
    if len(data['transcriptions']) == 1:
        print("✅ NO SPLIT - Single transcription detected")
    else:
        print(f"❌ SPLIT DETECTED - {len(data['transcriptions'])} transcriptions")
    print("="*60)
```

### 3.2 Run Analysis
```bash
cd /home/paul/git/voice-assistant-custom-commands
python3 tests/analyze_vad_logs.py tests/audio/debug/vad_test_log.txt
```

---

## Phase 4: Root Cause Identification (iterative)

Based on analysis output, check these conditions:

### 4.1 Early Stop Detector Interference
**If**: `[EARLY-STOP] TRIGGERED` appears in logs during split
**Then**: Early stop is firing incorrectly
**Fix**: Disable or adjust early stop window (currently 300-600ms)

### 4.2 Energy Ratio Near Threshold
**If**: `ratio` values hover around 0.6 during natural speech
**Then**: Threshold too sensitive to normal speech dynamics
**Fix**: Increase vad_thold to 0.7 or 0.8, or add hysteresis

### 4.3 Buffer Too Small
**If**: VAD triggers when buffer < 2 seconds
**Then**: Not enough context for reliable detection
**Fix**: Increase audio buffer size or require minimum speech duration

### 4.4 Natural Pause Detection
**If**: Saved audio files show actual pauses at split points
**Then**: VAD is working correctly but too sensitive to normal pauses
**Fix**: Add hysteresis - require N consecutive silence frames before triggering

### 4.5 Timing Race Condition
**If**: VAD triggers within 100ms of new audio arriving
**Then**: Timing issue between capture and processing
**Fix**: Add look-ahead buffer - wait 200ms after VAD trigger before transcribing

---

## Phase 5: Implement Fix Based on Data

### Strategy A: Add Hysteresis
Require 2-3 consecutive silence detections before triggering:

```cpp
static int silence_frame_count = 0;
const int SILENCE_FRAMES_REQUIRED = 3;

if (is_speech) {
    silence_frame_count = 0;
    vad_result = 1;
} else {
    silence_frame_count++;
    if (silence_frame_count >= SILENCE_FRAMES_REQUIRED && vad_result_prev == 1) {
        vad_result = 2; // Only trigger after consistent silence
    } else {
        vad_result = (vad_result_prev == 1) ? 1 : 0; // Stay in speech state
    }
}
```

### Strategy B: Add Confidence Window
Wait after VAD trigger to confirm silence:

```cpp
static double vad_trigger_time = -1;
const double CONFIRMATION_WINDOW_MS = 200;

if (vad_result == 2 && vad_trigger_time < 0) {
    vad_trigger_time = get_current_time_ms();
    vad_result = 1; // Don't trigger yet, wait for confirmation
} else if (vad_trigger_time > 0) {
    if (is_speech) {
        vad_trigger_time = -1; // Speech resumed, cancel trigger
        vad_result = 1;
    } else if (get_current_time_ms() - vad_trigger_time >= CONFIRMATION_WINDOW_MS) {
        vad_result = 2; // Confirmed silence, trigger now
        vad_trigger_time = -1;
    }
}
```

### Strategy C: Adjust Parameters
Based on energy analysis, tune:
- `vad_thold`: Increase from 0.6 to 0.7-0.8
- `vad_last_ms`: Increase from 700 to 1000-1500
- Early stop: Disable or adjust window

### Strategy D: Minimum Speech Duration
Don't trigger if speech < 1 second:

```cpp
if (vad_result == 2 && vad_result_prev == 1) {
    double speech_duration = get_current_time_ms() - speech_start_ms;
    if (speech_duration < 1000.0) {
        fprintf(stderr, "[VAD-DEBUG] Ignoring short speech: %.0fms\n", speech_duration);
        vad_result = 1; // Keep in speech state
    }
}
```

---

## Phase 6: Verify Fix (5 min)

### 6.1 Rebuild and Test
```bash
cmake --build build -j
bash tests/run_vad_test.sh 2>&1 | tee tests/audio/debug/vad_test_fixed.txt
```

### 6.2 Analyze Fixed Results
```bash
python3 tests/analyze_vad_logs.py tests/audio/debug/vad_test_fixed.txt
```

### 6.3 Success Criteria
- ✅ Single transcription: "Navigate to the closest Starbucks near me"
- ✅ No split events during natural speech
- ✅ Energy logs show stable detection

### 6.4 If Still Failing
- Compare before/after logs
- Identify what changed and what didn't
- Iterate with different strategy

---

## Execution Timeline

1. **Phase 1** (15 min): Add all instrumentation, rebuild
2. **Phase 2** (5 min): Run automated test
3. **Phase 3** (10 min): Analyze logs automatically
4. **Phase 4** (5 min): Identify root cause from data
5. **Phase 5** (10 min): Implement targeted fix
6. **Phase 6** (5 min): Verify fix works

**Total**: ~50 minutes to root cause and fix

---

## Rollback Strategy

If fix doesn't work:
```bash
git reset --hard vad-debug-baseline
git clean -fd tests/audio/debug/
```

All debug output goes to `tests/audio/debug/` for easy cleanup.

---

## Success Metrics

**Before**: 2-8 separate transcriptions for single phrase
**After**: 1 transcription for complete phrase
**Data**: Energy logs and saved audio show why fix works
