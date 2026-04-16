# Commented-Out Features Reference

Features that were removed from `talk-llama.cpp` during the cleanup pass but are worth
considering for future re-implementation, along with any known issues that caused their
original removal.

---

## Voice Commands (Old Hardcoded System)

The original assistant had voice commands implemented directly in the main loop via
string matching. These were replaced by the tool system, but only `stop` has been
re-implemented so far. The others are candidates for tool system integration.

### Regenerate (`user_command == "regenerate"`)

Triggered by: "regenerate", "try again" (also Russian equivalents)

Rolled back the last LLM reply from `embd_inp`, re-used the previous user input
(`text_heard_prev`), and let the LLM generate a fresh response to the same prompt.
TTS spoke "Regenerating" to confirm.

Key logic:
- Erased tokens from `embd_inp` back to `n_past_prev`
- Reset `n_past = n_past_prev`
- Re-injected `text_heard_prev` as the new prompt
- Played a confirmation TTS response

Re-implementation note: straightforward to add as a tool executor. Needs access to
`n_past_prev` and `text_heard_prev` state, which are already tracked.

---

### Delete (`user_command == "delete"`)

Triggered by: "delete", "delete two messages", "delete three messages"
(also Russian: "удали", "удали два сообщения", "удали три сообщения")

Removed the last 1, 2, or 3 user/assistant message pairs from the context.
TTS spoke "Deleted" or "Nothing to delete more".

Key logic:
- Maintained `past_prev_arr[]` tracking `n_past` before each user turn
- Rolled back `embd_inp` and `n_past` by N exchanges
- Handled edge case where there is nothing left to delete

Re-implementation note: requires the `past_prev_arr` state (already maintained in the
code). A natural fit for a tool executor that takes a `count` argument.

---

### Reset (`user_command == "reset"`)

Triggered by: "reset" (also Russian: "очисти")

Cleared the entire conversation history back to the initial system prompt, then
re-evaluated the prompt in batches. TTS spoke "Reset whole context" or
"Nothing to reset more".

Key logic:
- Erased all of `embd_inp` down to `n_keep` (the system prompt token count)
- Re-evaluated the system prompt in `n_batch`-sized chunks
- Reset `n_past = n_keep`
- Handled edge case where context is already at minimum

Re-implementation note: simplest of the conversation management commands to re-implement.

---

### Google/Search (`user_command == "google"`)

Triggered by: "google [query]", "search [query]"

Extracted a search query from the user's utterance, sent it to a langchain server
endpoint (`params.xtts_url + "search/"`), received the result, truncated to 200
characters, prepended "Google: ", injected into the LLM context as grounding, and
TTS-played the result.

Key logic:
- `ParseCommandAndGetKeyword(text_heard, "google")` extracted the query
- HTTP GET to langchain endpoint
- Result truncated at word boundary around 200 chars
- Injected as `"Google: " + result + "."` into the conversation

Re-implementation note: requires a search backend. Could be re-implemented as a tool
that calls any search API. The context injection pattern is worth reusing.

---

### Call / Persona Switch (`user_command == "call"`)

Triggered by: "call [name]"

Extracted a name from the utterance and set it as the active bot persona
(`params.bot_name = name`). Effectively switched the character the LLM was roleplaying.

Key logic:
- `ParseCommandAndGetKeyword(text_heard, "call")` extracted the name
- Set `params.bot_name` for subsequent generation

Re-implementation note: simple tool executor. The name would need to be injected into
the prompt appropriately.

---

## Audio / Speech Features

### Audio Buffer Trimming Before Whisper

**Why removed:** Uncertain — the code was disabled, possibly because `speech_len`
calculation wasn't reliable enough.

Trimmed `pcmf32_cur` to only the last N samples matching the detected speech duration,
giving Whisper a tighter audio window.

```cpp
// len_in_samples = (int)(WHISPER_SAMPLE_RATE * speech_len);
// if (len_in_samples && len_in_samples < pcmf32_cur.size()) {
//     std::vector<float> temp(pcmf32_cur.end() - len_in_samples, pcmf32_cur.end());
//     pcmf32_cur.assign(temp.begin(), temp.end());
// }
```

Re-implementation note: this could improve Whisper accuracy in noisy environments by
reducing irrelevant audio. Would need to be tested against the current 2s/10s windowed
approach.

---

### VAD Interrupt During LLM Generation

**Why removed:** TTS audio from the speaker bleeds into the microphone and falsely
triggers the VAD, interrupting generation at random. Needs acoustic echo cancellation
(AEC) or a hardware push-to-talk switch to work reliably.

Checked every 2 tokens whether the user had started speaking (or pressed a hotkey),
then set `done = true` to break out of the generation loop. A second instance ran after
each TTS chunk was dispatched.

```cpp
// if (!test_mode && new_tokens % 2 == 0) {
//     audio.get(2000, pcmf32_cur);
//     int vad_result = ::vad_simple(pcmf32_cur, WHISPER_SAMPLE_RATE, params.vad_last_ms,
//                                   params.vad_thold, params.freq_thold, params.print_energy);
//     if (!params.push_to_talk && vad_result == 1 ||
//         g_hotkey_pressed == "Ctrl+Space" || g_hotkey_pressed == "Alt") {
//         llama_interrupted = 1;
//         done = true;
//         break;
//     }
// }
```

Re-implementation note: The threading refactor (background generation + main thread
listens) makes this less necessary — the main thread now listens while generation runs.
The remaining latency is the Whisper transcription window. If sub-second interrupt is
needed, hardware PTT or AEC would be required.

---

## Known Threading Issue (input_queue mutex)

The `input_queue` (keyboard input) is written by `input_thread_func()` and read by
the main loop without any synchronization. A mutex was attempted but removed because
it caused blocking:

```cpp
// std::mutex input_mutex;  // line ~1264, function scope
// std::lock_guard<std::mutex> lock(input_mutex);  // in input_thread_func (line ~1285)
// std::lock_guard<std::mutex> lock(input_mutex);  // in main loop (line ~2015)
```

The TODO comment noted this should be revisited. In practice it may be benign (small
strings, unlikely race window) but is technically undefined behaviour. If keyboard
input becomes unreliable, adding back a `std::mutex` or switching to a lock-free queue
(`std::atomic`, `std::condition_variable`) would fix it.

---

## TTS Engine Upgrades

**Current:** Piper TTS via Wyoming protocol (~3.7/5.0 MOS, CPU-friendly, fast)

**Quality Measurement:** TTS quality is measured using MOS (Mean Opinion Score) - listeners rate speech 1-5 on naturalness, where 5.0 is indistinguishable from human and 4.5-4.7 is typical human speech quality.

### Available Local TTS Options

| TTS Engine | Quality (MOS) | Speed (GPU) | VRAM Min | VRAM Recommended | Voice Cloning | Existing Wrappers | Maturity |
|------------|---------------|-------------|----------|------------------|---------------|-------------------|----------|
| **Piper** (current) | ~3.7/5.0 | 50-150ms | CPU-only | 0.5GB (optional) | ❌ No | Wyoming-Piper | Excellent |
| **XTTS v2** | ~4.4/5.0 | 500ms-1.5s | 4GB (small) | 6-8GB | ✅ Yes (6s sample) | xtts-api-server, AllTalk | Excellent |
| **Bark** | ~4.2/5.0 | 3-8s | 4GB (small) | 8-12GB | ⚠️ Limited | bark-server | Good |
| **StyleTTS2** | ~4.5/5.0 | 1-3s | 4GB | 6-8GB | ✅ Yes (zero-shot) | Need custom | Fair |
| **F5-TTS** | ~4.4/5.0 | 500ms-1s | 4GB | 6GB | ✅ Yes (zero-shot) | Need custom | New (2024) |
| **Kokoro TTS** | ~4.0/5.0 | 200-600ms | 1GB | 2-4GB | ❌ No | kokoro-onnx | New (2024) |

### Quality Comparison

**What the MOS scores mean:**
- **Piper (3.7)**: Clear, understandable TTS. Obviously synthetic, somewhat monotone. Good for notifications. Similar to early Google Assistant.
- **XTTS (4.4)**: Natural conversational speech. Still detectably synthetic on close listen. Good emotional range. Similar to current Alexa/ElevenLabs.
- **Bark (4.2)**: Can be nearly indistinguishable from human. Occasional artifacts. Best emotion/laughter. Like human podcaster when it works well.
- **StyleTTS2 (4.5)**: Near human-level quality. Very natural prosody. Best zero-shot voice cloning.

**Quality improvement from Piper to XTTS:**
- MOS: +0.7 points (19% improvement on absolute scale)
- Noticeable: More natural prosody, better emotional expression, fewer robotic artifacts
- Still clearly synthetic (both are)
- Trade-off: ~3-10x slower, ~12x more VRAM

### Integration Complexity

| Engine | VRAM | Quality Gain | Integration Effort | Ready to Use? |
|--------|------|--------------|-------------------|---------------|
| XTTS + xtts-api-server | 6-8GB | +0.7 MOS | ⭐ Low | ✅ Yes - 1 hour |
| XTTS + Wyoming bridge | 6-8GB | +0.7 MOS | ⭐⭐ Medium | ✅ Yes - 2 hours |
| Kokoro | 2-4GB | +0.3 MOS | ⭐⭐ Medium | ✅ Yes - community |
| StyleTTS2 | 6-8GB | +0.8 MOS | ⭐⭐⭐ High | ❌ No - custom server |
| F5-TTS | 6GB | +0.7 MOS | ⭐⭐⭐ High | ❌ No - custom server |
| Bark | 8-12GB | +0.5 MOS | ⭐⭐ Medium | ✅ Yes - bark-server |

### Recommended: XTTS v2 with xtts-api-server

**Priority:** Medium - Significant quality improvement with reasonable integration effort

**Why XTTS:**
- ✅ Best quality-to-integration-effort ratio
- ✅ Proven to work with talk-llama design (Mozer/talk-llama-fast used it)
- ✅ Ready-to-use server wrapper (xtts-api-server)
- ✅ 500ms-1s latency acceptable for conversational AI
- ✅ Voice cloning capability (clone your own voice from 6-second sample)
- ✅ Active community, well-maintained
- ✅ Can create Wyoming bridge with ~100 lines of Python

**Hardware requirements:**
- Machine .74 (W6800, 32GB VRAM): ✅ Can run XTTS comfortably
- Machine .26 (890M iGPU, ~2GB shared): ❌ Stick with Piper CPU mode

**Implementation Options:**

**Option A: HTTP Direct (like Mozer)**
```bash
# Install and run XTTS server
pip install xtts-api-server
xtts-api-server --port 8020 --device cuda

# Modify talk-llama Wyoming client to HTTP client
# Change send_tts_async() to POST to http://localhost:8020/tts_to_audio
```

**Option B: Wyoming Bridge (no talk-llama changes)**
```python
# wyoming_xtts_bridge.py - forward Wyoming events to XTTS HTTP API
import requests
from wyoming.server import AsyncEventHandler

class XTTSBridge(AsyncEventHandler):
    async def handle_event(self, event):
        if Synthesize.is_type(event.type):
            response = requests.post(
                "http://localhost:8020/tts_to_audio",
                json={"text": event.data["text"]}
            )
            # Stream back via Wyoming protocol
            await self.stream_audio(response.content)
```

**Option C: Native Wyoming-XTTS Server**
Write full Wyoming protocol handler with XTTS backend (most work, best integration).

**Voice Cloning Setup:**
```bash
# Record 6-10 second reference sample
arecord -f S16_LE -r 22050 -c 1 reference.wav

# Configure XTTS to use it
# Place in xtts-api-server speakers/ directory
```

**Resources:**
- [xtts-api-server](https://github.com/daswer123/xtts-api-server)
- [Coqui TTS](https://github.com/coqui-ai/TTS)
- [Mozer's fork](https://github.com/Mozer/xtts-api-server) - Modified for streaming

---

## Acoustic Echo Cancellation (AEC)

**Current State:** Using energy threshold workaround (`--min-energy 0.0012f`) to filter TTS feedback. This is documented in `TTS_FEEDBACK_PREVENTION.md` but proper AEC is not yet implemented.

**Problem:** The current approach can miss "stop" commands during loud TTS playback because user voice may be masked by speaker output.

### Recommended: PulseAudio/PipeWire WebRTC AEC

**Priority:** High - Enables proper barge-in capability (interrupting TTS mid-sentence)

**Implementation:**
```bash
# Enable WebRTC echo cancellation
pactl load-module module-echo-cancel \
    aec_method=webrtc \
    source_name=echocancel \
    sink_name=echocancel1

# Configure talk-llama to use echo-cancelled devices:
# - TTS output: echocancel1 (sink)
# - Mic input: echocancel (source)
```

**Benefits:**
- ✅ Zero code changes needed
- ✅ Industry-standard solution (same as Alexa, Google Assistant)
- ✅ Stop commands work during TTS playback
- ✅ Re-enables VAD interrupt during generation (currently disabled due to echo)
- ✅ Improves quiet speech detection

**Once AEC is working, can re-enable:**
- VAD interrupt every 2 tokens during LLM generation (lines 140-151 above)
- Achieves ~200ms interrupt latency like Mozer/talk-llama-fast
- Currently commented out because TTS feedback triggers false interrupts

**Resources:**
- See `TTS_FEEDBACK_PREVENTION.md` for full documentation
- [PulseAudio Echo Cancel Guide](https://www.linuxuprising.com/2020/09/how-to-enable-echo-noise-cancellation.html)
- [PipeWire Echo Cancel Module](https://docs.pipewire.org/page_module_echo_cancel.html)

**Alternative Approaches:**
1. **Dual-threshold stop detection** - Lower threshold for "stop" keyword during TTS
2. **2-mic array with hardware AEC** - Reference mic near speaker (Wyoming Satellite has tutorial)
3. **Event-based microphone muting** - Like Wyoming Satellite, wake word detector during TTS

---

## Wyoming Protocol Improvements

### Streaming Control Enhancements

**Priority:** Medium - Better control over TTS playback quality and behavior

**Configurable Parameters to Add:**

1. **Audio Chunk Size Control**
   - Expose Wyoming-Piper chunk size configuration
   - Currently hardcoded, should be tunable via `--tts-chunk-size`
   - Smaller chunks = lower latency, larger = better quality

2. **Playback Queue Management**
   - Implement `--stream-play-sync` flag (from Mozer's design)
   - Prevents overlapping audio when responses arrive quickly
   - Queue vs immediate playback modes

3. **Voice Quality Settings**
   - Configurable Piper sample rate (currently fixed at 22050Hz)
   - Voice speed adjustment (--speech-rate parameter)
   - Volume control via Wyoming events

**New Wyoming Events to Implement:**

```json
{"type": "set-playback-volume", "data": {"level": 0.8}}
{"type": "set-speech-rate", "data": {"rate": 1.2}}
{"type": "change-voice", "data": {"name": "en_US-danny-low"}}
{"type": "repeat-last", "data": {}}
```

**Implementation Notes:**
- Follow same pattern as `new-response` custom event
- Add handlers in `wyoming_piper/handler.py`
- Expose C++ API in `WyomingClient` class
- Could be triggered by voice commands or tool calls

### Server Health Monitoring

**Priority:** Low - Nice-to-have for production deployments

**Features:**
- Periodic health checks to Wyoming-Piper and llama-server
- Auto-restart on server failure
- Connection pooling for HTTP requests
- Configurable timeout/retry logic
- Warning messages when servers become unresponsive

**Implementation:**
```cpp
// In main loop or background thread
if (!wyoming_client->healthCheck() && ++failures > 3) {
    fprintf(stderr, "WARNING: Wyoming-Piper not responding, attempting restart...\n");
    restartWyomingServer();
}
```

---

## Performance and Latency Improvements

### Expose Split-After Parameter

**Current State:** `--split-after N` parameter exists but may not be fully functional

**Purpose:** Split TTS dispatch after first N tokens for faster perceived response time

**Implementation:**
- Verify `params.split_after` is actually used in streaming callback
- Test with different values (10, 20, 50 tokens)
- Document optimal settings for different models

### Configurable Streaming Parameters

**From Mozer/talk-llama-fast design:**

```bash
# Expose these parameters:
--wav-chunk-size N      # Audio chunk size for TTS streaming
--batch-size N          # LLM batch size (VRAM vs latency trade-off)
--vad-last-ms 200       # Reduce from 700ms for faster interrupt (needs AEC)
```

### Better Context Management Tools

**Priority:** Medium - User-requested features from original design

Re-implement as tool system commands (removed during cleanup):

```json
{
  "name": "regenerate_response",
  "description": "Regenerate the last assistant response with a different answer",
  "fast_path": true,
  "keywords": ["regenerate", "try again"],
  "parameters": {"type": "object", "properties": {}, "required": []}
}
```

```json
{
  "name": "delete_messages",
  "description": "Remove the last N conversation exchanges from context",
  "fast_path": false,
  "parameters": {
    "type": "object",
    "properties": {
      "count": {"type": "integer", "description": "Number of exchanges to delete (1-3)"}
    },
    "required": []
  }
}
```

```json
{
  "name": "reset_conversation",
  "description": "Clear entire conversation history back to system prompt",
  "fast_path": true,
  "keywords": ["reset", "clear history"],
  "parameters": {"type": "object", "properties": {}, "required": []}
}
```

**Implementation Notes:**
- State tracking already exists (`n_past_prev`, `past_prev_arr`, `n_keep`)
- Need to expose via tool executor functions
- LLM context manipulation requires careful token accounting

---

## Russian Language Support Notes

- `LowerCase()` does not work with UTF-8 non-Latin characters. The `tolower()` approach
  was used instead. Keep this in mind for any case-insensitive matching of non-ASCII input.
- Russian name declension in the "call" command: genitive case ending (e.g. "Олега" → "Олег")
  was partially handled but the extra rule was disabled. If Russian call support is re-added,
  test with genitive case names.
