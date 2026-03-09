# Tool System

The voice assistant uses a dual-mode tool calling system built on Mistral Instruct.
Time-critical commands bypass the LLM entirely (fast path); all other commands are
handled by the LLM using structured tool calls parsed from its output (smart path).

## Architecture

```
User Speech → Whisper STT → text_heard
                                ↓
                    [FAST PATH CHECK]
                    /              \
            Keyword match       No match
                ↓                   ↓
        Execute immediately    LLaMA generation
        Skip LLaMA             (tool defs injected
                                into system prompt)
                                      ↓
                            Token generation loop
                                      ↓
                            [TOOL CALL PARSER]
                                      ↓
                        <tool_call> detected?
                        /                    \
                    Yes                       No
                    ↓                          ↓
            Execute tool               Normal text → TTS
            Continue generation
```

## Core Components

| File | Description |
|------|-------------|
| `custom/talk-llama/tool-system.h/.cpp` | Tool registry, executor plugin system, fast-path keyword matching, Mistral prompt generation |
| `custom/talk-llama/tool-parser.h/.cpp` | Streaming state machine parser for `<tool_call>` blocks — token-by-token, no buffering |
| `custom/talk-llama/wyoming-client.h/.cpp` | Wyoming protocol client — sends stop/pause/resume/new-response events to Wyoming-Piper |
| `custom/talk-llama/tools/tools.json` | JSON tool definitions — add tools here without touching C++ |

## Automotive Tools

| # | Tool | Type | Parameters | Description |
|---|------|------|------------|-------------|
| 1 | `stop_speaking` | Fast path | — | Stop TTS immediately (keywords: stop, quiet, silence, shut up, enough) |
| 2 | `set_temperature` | Smart path | `value` (60–85°F), `zone` (driver/passenger/both) | Adjust climate control |
| 3 | `set_fan_speed` | Smart path | `level` (off/low/medium/high/auto) | Adjust HVAC fan |
| 4 | `enable_defrost` | Smart path | `location` (front/rear/both), `mode` (defrost/defog) | Windshield defrost/defog |
| 5 | `navigate_to` | Smart path | `destination` or `preset` (home/work) | Start navigation |
| 6 | `find_nearby` | Smart path | `category`, `max_distance` | Find nearby POI |
| 7 | `get_eta` | Smart path | — | Estimated arrival time |
| 8 | `check_tire_pressure` | Smart path | — | Tire pressure status |
| 9 | `get_fuel_range` | Smart path | — | Remaining fuel/battery range |
| 10 | `check_vehicle_status` | Smart path | `detail_level` (summary/detailed) | Overall vehicle status |

## Adding a New Tool

**1. Define in `tools/tools.json`:**
```json
{
  "name": "new_tool",
  "description": "What it does",
  "fast_path": false,
  "keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "value": { "type": "string", "description": "..." }
    }
  }
}
```

**2. Implement the executor in `tool-system.cpp`:**
```cpp
namespace executors {
ToolResult new_tool(const json& args) {
    std::string value = args.value("value", "");
    // do something
    return ToolResult(true, "Done");
}
} // namespace executors
```

**3. Register it in `registerBuiltinExecutors()`:**
```cpp
registry.registerExecutor("new_tool", executors::new_tool);
```

**4. Rebuild:**
```bash
ssh paul@192.168.86.74 "cd ~/Projects/git/talk-llama-fast && cmake --build build -j"
```

## Vehicle System Integration

Current executors are mock implementations that log to stdout. For real integration,
replace the executor body with hardware calls.

**CAN bus example:**
```cpp
#include <linux/can.h>
#include <linux/can/raw.h>

ToolResult set_temperature(const json& args) {
    double temp = args["value"].get<double>();

    int s = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    struct can_frame frame;
    frame.can_id = 0x3E3; // HVAC controller
    frame.can_dlc = 2;
    frame.data[0] = 0x01; // set temp command
    frame.data[1] = (uint8_t)temp;
    write(s, &frame, sizeof(struct can_frame));
    close(s);

    return ToolResult(true, "Temperature set to " + std::to_string((int)temp) + "°F");
}
```

## Known Limitations

- **Single tool call per turn** — the parser handles one `<tool_call>` block per generation; extend `ToolCallParser` to support multiple
- **No user confirmation** — all tools execute immediately; safety-critical commands should prompt for confirmation before acting
- **Mock vehicle integration** — no real CAN bus / D-Bus / navigation API connected yet

## Future Enhancements

- Tool chaining — multiple tool calls in a single LLM response
- Confirmation prompts — "Are you sure?" for destructive or safety-critical commands
- Tool history — carry tool context across conversational turns
- Dynamic loading — runtime plugin system so tools can be added without recompiling
- Permissions — per-user tool access control
- Rate limiting — prevent accidental rapid-fire tool invocations

## Troubleshooting

**"Failed to load tools from tools.json"**
→ Verify the file exists at `custom/talk-llama/tools/tools.json` relative to the working directory.

**"Undefined reference to tool_system::ToolRegistry"**
→ Check that `tool-system.cpp`, `tool-parser.cpp`, and `wyoming-client.cpp` are listed in `CMakeLists.txt`.

**"Cannot find json.hpp"**
→ Include path must point to `whisper.cpp/examples/json.hpp`.

**Tools not triggering**
→ Run with `--debug` and look for `[Tool Parser]` messages. Confirm the LLM is outputting `<tool_call>` blocks — this depends on the Mistral Instruct model being used.

**Stop command not silencing all queued chunks**
→ Confirm Wyoming-Piper was restarted after any `handler.py` changes. The `new-response` event must be sent before the first TTS chunk of each turn.

## Related Documentation

- `docs/TOOL_CALLING.md` — full tool system architecture and format reference
- `docs/WYOMING_INTEGRATION.md` — Wyoming-Piper handler and protocol details
- `docs/FUTURE.md` — features considered for future re-implementation
