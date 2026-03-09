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

## Russian Language Support Notes

- `LowerCase()` does not work with UTF-8 non-Latin characters. The `tolower()` approach
  was used instead. Keep this in mind for any case-insensitive matching of non-ASCII input.
- Russian name declension in the "call" command: genitive case ending (e.g. "Олега" → "Олег")
  was partially handled but the extra rule was disabled. If Russian call support is re-added,
  test with genitive case names.
