# TTS Feedback Prevention

## Current Implementation

### Approach: Energy Threshold-Based Filtering

The voice assistant currently prevents TTS audio feedback using a **minimum energy threshold** (`min_energy`) in the Voice Activity Detection (VAD) system.

**How it works:**
```cpp
// In whisper.cpp/examples/common.cpp
if (energy_last > vad_thold*energy_all && energy_last > min_energy) {
    return false;  // Speech detected
}
```

**Configuration:**
- Default: `min_energy = 0.0012f`
- Command line: `--min-energy 0.0012` (or `-me`)
- Tunable via command line for different environments

### Rationale

This threshold filters out:
- TTS playback audio (~0.0008 energy)
- Environmental noise (~0.0001-0.0005)
- Keyboard/breathing sounds

While allowing:
- Real human speech (0.001-0.1 energy)

### Additional Protections

**Disabled VAD interrupts during LLM generation:**
- Removed VAD checks that ran every 2 tokens during LLM response generation
- Removed VAD checks after sending TTS chunks
- These were causing premature interruption when TTS audio was detected as "user speech"
- Not present in baseline whisper.cpp (talk-llama-fast addition)

## Limitations

### 1. Stop Command During TTS Playback

**Issue:** If a user says "stop" while TTS is playing loudly, the command may be missed because:
- TTS audio energy (~0.0008) is close to the threshold (0.0012)
- User's voice may be masked by TTS playback
- The threshold filters audio in this energy range

**Impact:** Users may need to wait for TTS to finish or speak very loudly to interrupt.

### 2. Quiet Speech Detection

**Trade-off:** Higher `min_energy` prevents TTS feedback but may miss:
- Quiet speakers
- Distant voice commands
- Speech in noisy environments

**Mitigation:** Tune `--min-energy` parameter based on your environment:
- Lower values (0.0008-0.0010): Better detection, more TTS feedback risk
- Higher values (0.0012-0.0020): Less feedback, may miss quiet speech

### 3. Not a True Echo Cancellation Solution

This approach is a **workaround**, not proper Acoustic Echo Cancellation (AEC). It filters based on energy levels rather than actively removing echo from the signal.

## Potential Improvements

### Option 1: PulseAudio/PipeWire Echo Cancellation (RECOMMENDED)

**Industry Standard:** Used by commercial voice assistants (Alexa, Google Assistant)

**How it works:**
- WebRTC's Acoustic Echo Cancellation digitally removes speaker output from microphone input
- Microphone stays active during TTS playback
- "Stop" commands work anytime, even during loud TTS

**Implementation:**

```bash
# Enable PulseAudio WebRTC echo cancellation
pactl load-module module-echo-cancel \
    aec_method=webrtc \
    source_name=echocancel \
    sink_name=echocancel1

# Configure application to use echo-cancelled devices
# - TTS output: echocancel1 (sink)
# - Mic input: echocancel (source)
```

**Advantages:**
- ✅ Stop commands work during TTS
- ✅ No false positives from TTS audio
- ✅ Better quiet speech detection
- ✅ Industry-standard solution
- ✅ No code changes needed

**Resources:**
- [PulseAudio Echo Cancellation Guide](https://www.linuxuprising.com/2020/09/how-to-enable-echo-noise-cancellation.html)
- [PipeWire Echo Cancel Module](https://docs.pipewire.org/page_module_echo_cancel.html)
- [WebRTC AEC Overview](https://webrtc.github.io/webrtc-org/blog/2011/07/11/webrtc-improvement-optimized-aec-acoustic-echo-cancellation.html)

### Option 2: Dual-Threshold Stop Detection

**Approach:** Dedicated "stop" keyword detector with lower threshold during TTS playback

**How it works:**
```cpp
// Main VAD: high threshold during TTS
float main_threshold = is_tts_playing ? 0.0020f : params.min_energy;

// Stop detector: always uses low threshold + keyword matching
float stop_threshold = 0.0008f;
if (detect_keyword("stop", pcmf32, stop_threshold)) {
    interrupt_tts();
}
```

**Advantages:**
- ✅ Stop works during TTS
- ✅ No external dependencies
- ✅ Custom tuning for stop detection

**Disadvantages:**
- ❌ Requires tracking TTS playback state
- ❌ More complex code
- ❌ Still susceptible to false positives

### Option 3: Microphone Muting with Event Hooks

**Approach:** Pause mic during TTS, but allow wake word detection (like Wyoming Satellite)

**How it works:**
1. When TTS starts: Pause main VAD, keep wake word detector active
2. Wake word detector listens for "stop" with specialized model
3. When TTS ends: Resume normal VAD

**Advantages:**
- ✅ No TTS feedback
- ✅ Stop command still detectable
- ✅ Matches Wyoming Satellite pattern

**Disadvantages:**
- ❌ Requires wake word detection model
- ❌ Complex state management
- ❌ Can't interrupt mid-word

**Resources:**
- [Wyoming Satellite - Microphone Muting](https://github.com/rhasspy/wyoming-satellite/blob/master/CHANGELOG.md)
- [Alexa Barge-in Documentation](https://developer.amazon.com/en-US/docs/alexa/alexa-auto/invoking-alexa.html)

### Option 4: Hardware Solution - 2-Mic Array

**Approach:** Dedicated reference microphone for echo cancellation

**Configuration:**
- Mic 1: Primary input
- Mic 2: Reference signal (near speaker)
- AEC uses Mic 2 to subtract echo from Mic 1

**Advantages:**
- ✅ Best echo cancellation quality
- ✅ Commercial-grade solution
- ✅ Works like Alexa 7-mic array

**Disadvantages:**
- ❌ Requires additional hardware
- ❌ More complex setup
- ❌ Higher cost

**Resources:**
- [Wyoming Satellite 2-Mic Tutorial](https://github.com/rhasspy/wyoming-satellite/blob/master/docs/tutorial_2mic.md)

## Comparison Table

| Solution | Stop During TTS | Code Complexity | External Deps | Quality |
|----------|----------------|-----------------|---------------|---------|
| Current (min_energy) | ❌ May miss | Low | None | Fair |
| PulseAudio AEC | ✅ Always works | None | PulseAudio | Excellent |
| Dual-threshold | ✅ Usually works | Medium | None | Good |
| Event-based muting | ⚠️ Wake word only | High | Wake model | Good |
| 2-mic hardware | ✅ Always works | Medium | Extra mic | Excellent |

## Recommended Path Forward

### Short Term (Current)
- Use `min_energy` threshold approach
- Tune via `--min-energy` parameter for your environment
- Accept limitation that stop may be missed during loud TTS

### Medium Term (Best ROI)
- Implement PulseAudio WebRTC echo cancellation
- Simple configuration, no code changes
- Solves all feedback issues

### Long Term (Best Quality)
- Add 2-microphone array
- Implement beamforming + AEC
- Match commercial assistant quality

## Configuration Guide

### Finding the Right min_energy Value

1. Enable energy printing:
   ```bash
   ./talk-llama-custom --min-energy 0.0012 -pe
   ```

2. Observe energy values during:
   - Normal speech: Should be 0.002-0.1
   - TTS playback: Typically 0.0005-0.0010
   - Background noise: Usually 0.0001-0.0005

3. Set threshold between TTS and speech:
   ```bash
   # If TTS energy is 0.0008 and speech is 0.002
   ./talk-llama-custom --min-energy 0.0012
   ```

### Testing Echo Cancellation

If implementing PulseAudio AEC:

```bash
# 1. Load echo cancellation module
pactl load-module module-echo-cancel aec_method=webrtc

# 2. List sources/sinks to find echo-cancelled devices
pactl list sources short
pactl list sinks short

# 3. Test by playing audio and recording simultaneously
# Should hear no echo in recording
```

## References

### Commercial Systems
- [Alexa Barge-in Documentation](https://developer.amazon.com/en-US/docs/alexa/alexa-auto/invoking-alexa.html) - How Alexa handles TTS interruption
- Alexa uses 7-mic array + beamforming + AEC for barge-in capability

### Open Source Implementations
- [Wyoming Satellite](https://github.com/rhasspy/wyoming-satellite) - Microphone muting during audio playback
- [WebRTC AEC](https://webrtc.github.io/webrtc-org/blog/2011/07/11/webrtc-improvement-optimized-aec-acoustic-echo-cancellation.html) - State-of-the-art echo cancellation
- [PulseAudio Echo Cancel](https://www.linuxuprising.com/2020/09/how-to-enable-echo-noise-cancellation.html) - Linux implementation guide
- [PipeWire Echo Cancel](https://docs.pipewire.org/page_module_echo_cancel.html) - Modern Linux audio

### Academic/Technical
- [WebRTC Audio Processing](https://webrtc.github.io/webrtc-org/) - Full WebRTC audio pipeline
- Typical processing chain: Mic → AEC → Beamforming → Noise Suppression → VAD → ASR

## History

### Evolution of Fixes

1. **Feb 19, 2024**: Added `min_energy = 0.0002f` to prevent environmental noise triggering
2. **Feb 24, 2024**: Increased to `min_energy = 0.0008f` for better noise rejection
3. **Feb 25, 2024**:
   - Fixed Wyoming-Piper TTS output (was outputting "json input")
   - Disabled VAD interrupt checks during LLM generation
   - Increased `min_energy = 0.0012f` to prevent TTS feedback
   - Made min_energy configurable via `--min-energy` parameter

### Original Baseline

Baseline whisper.cpp talk-llama had:
- No `min_energy` threshold at all
- No VAD checks during LLM generation
- Simple VAD: `if (energy_last > vad_thold * energy_all)`

## Contributing

If implementing improvements:

1. **Test with real TTS audio** - Don't just test with silence
2. **Measure energy levels** - Use `-pe` flag to observe actual values
3. **Test interruption** - Verify "stop" works during TTS
4. **Check false positives** - Ensure keyboard/breathing doesn't trigger VAD
5. **Document thresholds** - Record what values work in your environment

## Support

For issues or questions:
- Check energy levels with `--print-energy` flag
- Try adjusting `--min-energy` threshold
- Consider PulseAudio AEC for production use
- See GitHub issues for known problems
