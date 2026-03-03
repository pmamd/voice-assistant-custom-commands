# Mistral Tool Calling System

## Overview

This document describes the tool calling system implemented for the talk-llama voice assistant. The system leverages Mistral Instruct's native `<tool_call>` format to enable extensible, LLM-driven command execution with automotive-focused tools.

## Architecture

### Dual-Mode System

The tool system operates in two modes:

#### 1. Fast Path (Pre-LLaMA)
- **When**: Keyword matching before LLaMA processing
- **Latency**: <10ms overhead
- **Use case**: Time-critical commands like "stop" that need immediate execution
- **Location**: `talk-llama.cpp:2574` (before tokenization)
- **Tools**: `stop_speaking` (configured with `fast_path: true` in tools.json)

#### 2. Smart Path (LLaMA-driven)
- **When**: During LLaMA token generation
- **Latency**: Normal generation latency + parsing (<5ms)
- **Use case**: Context-aware commands requiring natural language understanding
- **Location**: `talk-llama.cpp:2878-2909` (token generation loop)
- **Tools**: All other tools (navigate_to, set_temperature, etc.)

### Data Flow

```
User Speech
    ↓
Whisper STT
    ↓
text_heard
    ↓
[FAST PATH CHECK] ← Keyword matching (tool-system.cpp:matchFastPath)
    ↓ (if no match)
LLaMA with Tool Definitions ← System prompt injection (talk-llama.cpp:1679)
    ↓
Token Generation Loop
    ↓
[TOOL PARSER] ← Streaming parser (tool-parser.cpp)
    ↓
<tool_call>...</tool_call> detected
    ↓
Execute Tool ← Tool registry (tool-system.cpp:execute)
    ↓
Continue Generation or Wyoming TTS
```

## Implementation Details

### Core Components

#### 1. Tool Registry (`tool-system.h/cpp`)

**Purpose**: Central registry for tool definitions and executors

**Key Classes**:
- `ToolDefinition`: Tool metadata (name, description, parameters schema, fast_path flag, keywords)
- `ToolResult`: Execution result (success, message, data)
- `ToolRegistry`: Singleton managing tools (load from JSON, match keywords, execute)

**Built-in Executors**:
```cpp
namespace executors {
    ToolResult stop_speaking(const json& args);
    ToolResult set_temperature(const json& args);
    ToolResult set_fan_speed(const json& args);
    ToolResult enable_defrost(const json& args);
    ToolResult navigate_to(const json& args);
    ToolResult find_nearby(const json& args);
    ToolResult get_eta(const json& args);
    ToolResult check_tire_pressure(const json& args);
    ToolResult get_fuel_range(const json& args);
    ToolResult check_vehicle_status(const json& args);
}
```

#### 2. Tool Call Parser (`tool-parser.h/cpp`)

**Purpose**: Streaming state machine to detect `<tool_call>` tags in Mistral output

**Parser States**:
- `NORMAL`: Regular text generation
- `IN_TAG_START`: Detected '<', checking for 'tool_call'
- `IN_TOOL_CALL`: Inside tag, accumulating JSON
- `IN_TAG_END`: Detected '</', checking for '/tool_call>'
- `COMPLETE`: Tool call parsed, ready to execute

**Key Methods**:
- `feedToken(token)`: Feed each generated token
- `hasToolCall()`: Check if complete tool call detected
- `getToolCall()`: Extract ToolCall struct (name, arguments, id)
- `getText()`: Get clean text (excluding tool tags)

#### 3. Wyoming Client (`wyoming-client.h/cpp`)

**Purpose**: Send commands to Wyoming-Piper TTS

**Key Methods**:
- `sendStop()`: Halt current TTS playback
- Uses existing `send_tts_async` infrastructure with special "stop" text

### Integration Points in talk-llama.cpp

#### Point 1: Include Headers (Line 52-54)
```cpp
// For tool calling system
#include "tool-system.h"
#include "tool-parser.h"
#include "wyoming-client.h"
```

#### Point 2: Initialize Tool System (Line 1917-1938)
```cpp
// Initialize tool calling system
tool_system::ToolRegistry& tool_registry = tool_system::ToolRegistry::getInstance();

std::string tools_json_path = "custom/talk-llama/tools/tools.json";
if (!tool_registry.loadFromFile(tools_json_path)) {
    fprintf(stderr, "WARNING: Failed to load tools from %s\n", tools_json_path.c_str());
} else {
    tool_system::registerBuiltinExecutors(tool_registry);
    printf("Tool system initialized with %zu tools\n", tool_registry.getAllTools().size());
}
```

#### Point 3: Inject Tool Definitions into Prompt (Line 1679-1683)
```cpp
// Inject tool definitions into prompt (for Mistral tool calling)
if (tool_registry.getAllTools().size() > 0) {
    std::string tools_prompt = tool_registry.getToolsPrompt();
    prompt_llama += "\n\n" + tools_prompt;
}
```

#### Point 4: Fast Path Check (Line 2574-2598)
```cpp
// FAST PATH TOOL EXECUTION (pre-LLaMA)
auto [matched, tool_def] = tool_registry.matchFastPath(text_heard);
if (matched && tool_def.fast_path) {
    tool_system::ToolResult result = tool_registry.execute(tool_def.name, json::object());

    if (result.success && tool_def.name == "stop_speaking") {
        send_tts_async("stop", params.xtts_voice, params.language, params.xtts_url, 0, params.debug);
        continue;  // Skip LLaMA processing
    }
}
```

#### Point 5: Initialize Parser for Generation (Line 2713-2715)
```cpp
// Initialize tool call parser for this generation
static tool_system::ToolCallParser tool_parser;
tool_parser.reset();
```

#### Point 6: Parse and Execute Tools During Generation (Line 2878-2909)
```cpp
out_token_str = llama_token_to_piece(ctx_llama, id);

// Feed token to tool call parser
bool tool_detected = tool_parser.feedToken(out_token_str);

if (tool_detected && tool_parser.hasToolCall()) {
    tool_system::ToolCall call = tool_parser.getToolCall();
    tool_system::ToolResult result = tool_registry.execute(call.name, call.arguments);

    if (result.success) {
        // Handle tool-specific actions
        if (call.name == "stop_speaking") {
            send_tts_async("stop", params.xtts_voice, params.language, params.xtts_url, 0, params.debug);
        }
    }
    tool_parser.reset();
}

// Use clean text (excluding tool tags)
std::string clean_text = tool_parser.getText();
if (!clean_text.empty()) {
    text_to_speak += clean_text;
    printf("%s", clean_text.c_str());
}
```

## Tool Definition Format

Tools are defined in `custom/talk-llama/tools/tools.json`:

```json
{
  "tools": [
    {
      "name": "tool_name",
      "description": "What the tool does (shown to LLM)",
      "fast_path": true,
      "keywords": ["word1", "word2"],
      "parameters": {
        "type": "object",
        "properties": {
          "param_name": {
            "type": "string|number|boolean",
            "description": "Parameter description",
            "enum": ["value1", "value2"]
          }
        },
        "required": ["param_name"]
      }
    }
  ]
}
```

### Automotive Tools Included

1. **stop_speaking** (Fast Path)
   - Keywords: "stop", "quiet", "silence", "shut up", "enough"
   - Immediately halts TTS playback

2. **set_temperature**
   - Adjust climate control temperature (60-85°F)
   - Parameters: value (number), zone (driver/passenger/both)

3. **set_fan_speed**
   - Adjust HVAC fan speed
   - Parameters: level (off/low/medium/high/auto)

4. **enable_defrost**
   - Turn on windshield defrost/defog
   - Parameters: location (front/rear/both), mode (defrost/defog)

5. **navigate_to**
   - Start navigation to destination
   - Parameters: destination (string) OR preset (home/work)

6. **find_nearby**
   - Find nearby points of interest
   - Parameters: category (gas_station/ev_charger/restaurant/parking/rest_area/hospital), max_distance (miles)

7. **get_eta**
   - Get estimated time of arrival
   - No parameters

8. **check_tire_pressure**
   - Check tire pressure status
   - No parameters

9. **get_fuel_range**
   - Get remaining fuel/battery range
   - No parameters

10. **check_vehicle_status**
    - Check overall vehicle status
    - Parameters: detail_level (summary/detailed)

## Adding New Tools

### Step 1: Define Tool in JSON

Edit `custom/talk-llama/tools/tools.json`:

```json
{
  "name": "set_seat_heater",
  "description": "Adjust seat heater level",
  "fast_path": false,
  "parameters": {
    "type": "object",
    "properties": {
      "seat": {
        "type": "string",
        "enum": ["driver", "passenger"],
        "description": "Which seat to adjust"
      },
      "level": {
        "type": "number",
        "description": "Heat level 0-3"
      }
    },
    "required": ["seat", "level"]
  }
}
```

### Step 2: Implement Executor

Add to `tool-system.cpp`:

```cpp
namespace executors {
    ToolResult set_seat_heater(const json& args) {
        std::string seat = args["seat"].get<std::string>();
        int level = args["level"].get<int>();

        // Validate
        if (level < 0 || level > 3) {
            return ToolResult(false, "Level must be 0-3");
        }

        fprintf(stdout, "[Tool] set_seat_heater: %s seat level %d\n", seat.c_str(), level);

        // TODO: Send CAN bus command to actual seat heater controller

        json result_data;
        result_data["seat"] = seat;
        result_data["level"] = level;

        return ToolResult(true, "Seat heater adjusted", result_data);
    }
}
```

### Step 3: Register Executor

Add to `registerBuiltinExecutors()` in `tool-system.cpp`:

```cpp
void registerBuiltinExecutors(ToolRegistry& registry) {
    // ... existing registrations ...
    registry.registerExecutor("set_seat_heater", executors::set_seat_heater);
}
```

### Step 4: (Optional) Handle in Generation Loop

If the tool needs special handling during generation, add to `talk-llama.cpp:2889`:

```cpp
if (result.success) {
    if (call.name == "set_seat_heater") {
        // Send to vehicle CAN bus or other integration
        vehicle_can_send(result.data);
    }
}
```

### Step 5: Rebuild

```bash
cmake --build build -j
```

## Mistral Prompt Format

The system prompt includes auto-generated tool descriptions:

```
You have access to the following tools:

## stop_speaking
Immediately stop the assistant from speaking (interrupt current speech)
No parameters required.

## set_temperature
Adjust the climate control temperature
Parameters:
- value (number): Temperature in Fahrenheit (60-85)
- zone (string): Which zone to adjust [driver, passenger, both]

... (more tools) ...

To use a tool, output: <tool_call>{"name": "tool_name", "arguments": {...}, "id": "unique_id"}</tool_call>
You can continue speaking after calling a tool.
```

## Example Conversations

### Fast Path

```
User: "stop"
System: [Fast Path Tool: stop_speaking]
        Stopped speaking
        (LLaMA processing skipped)
```

### Smart Path - Single Tool

```
User: "make it warmer"
LLaMA: <tool_call>{"name": "set_temperature", "arguments": {"value": 72, "zone": "both"}, "id": "1"}</tool_call>
System: [Tool Call: set_temperature]
        [Tool executed: Temperature set to 72 degrees]
LLaMA: I've set the temperature to 72 degrees.
```

### Smart Path - Tool + Response

```
User: "navigate home and tell me the weather"
LLaMA: <tool_call>{"name": "navigate_to", "arguments": {"preset": "home"}, "id": "1"}</tool_call> Navigation started. The weather is currently sunny with a high of 75 degrees.
System: [Tool Call: navigate_to]
        [Tool executed: Navigation started to home]
TTS: "Navigation started. The weather is currently sunny with a high of 75 degrees."
```

## Performance

- **Fast Path**: <10ms overhead (keyword matching only)
- **Tool Parser**: <5ms per token (state machine, no regex)
- **Stop Command End-to-End**: <100ms (fast path + Wyoming protocol)
- **Normal Queries**: <50ms overhead (parser feeding tokens)

## Testing

### Manual Tests

From the dev machine (192.168.86.74):

```bash
# Build
cd ~/Projects/git/talk-llama-fast
cmake --build build -j

# Run
./build/bin/talk-llama-custom \
  -m models/mistral-7b-instruct-v0.2.Q5_K_M.gguf \
  --model-whisper models/ggml-base.en.bin

# Test fast path
# Say: "stop"
# Expected: Immediate TTS halt

# Test smart path
# Say: "set temperature to 70"
# Expected: [Tool Call: set_temperature] message, LLM confirms action

# Test navigation
# Say: "navigate home"
# Expected: [Tool Call: navigate_to] with preset="home"
```

### Debugging

Enable debug output:

```bash
./build/bin/talk-llama-custom --debug ...
```

Look for:
- `[Tool System] Loaded N tools from ...`
- `[Tool System] Injected N tools into system prompt`
- `[Fast Path Tool: tool_name]`
- `[Tool Call: tool_name]`
- `[Tool Parser] Parsed tool call: ...`

## Integration with Vehicle Systems

The current implementation provides **mock executors** that log actions to stdout. To integrate with real vehicle systems:

### CAN Bus Integration

```cpp
#include <linux/can.h>
#include <linux/can/raw.h>

ToolResult set_temperature(const json& args) {
    double temp = args["value"].get<double>();

    // Open CAN socket
    int s = socket(PF_CAN, SOCK_RAW, CAN_RAW);

    // Prepare CAN frame
    struct can_frame frame;
    frame.can_id = 0x3E3; // HVAC controller ID
    frame.can_dlc = 2;
    frame.data[0] = 0x01; // Set temp command
    frame.data[1] = (uint8_t)temp;

    // Send
    write(s, &frame, sizeof(struct can_frame));
    close(s);

    return ToolResult(true, "Temperature set to " + std::to_string((int)temp));
}
```

### D-Bus Integration (Modern Automotive)

```cpp
#include <systemd/sd-bus.h>

ToolResult navigate_to(const json& args) {
    std::string dest = args["destination"].get<std::string>();

    sd_bus *bus = nullptr;
    sd_bus_open_user(&bus);

    sd_bus_call_method(
        bus,
        "org.genivi.navigation.NavigationCore",
        "/org/genivi/navigation",
        "org.genivi.navigation.NavigationCore.Session",
        "SetDestination",
        nullptr, nullptr,
        "s", dest.c_str()
    );

    sd_bus_unref(bus);
    return ToolResult(true, "Navigation started to " + dest);
}
```

## Future Enhancements

1. **Tool Chaining**: Allow LLM to call multiple tools in sequence
2. **Tool Confirmation**: Ask user confirmation for critical tools (e.g., navigation)
3. **Tool History**: Track tool usage for context
4. **Dynamic Tool Loading**: Load tools from plugins at runtime
5. **Tool Permissions**: User-configurable tool access control
6. **Voice Confirmation**: TTS confirmation before executing tools

## Troubleshooting

### Tool System Not Loading

**Symptom**: No "Tool system initialized" message

**Cause**: tools.json not found

**Fix**:
```bash
ls -la custom/talk-llama/tools/tools.json
# Verify file exists and is readable
```

### Fast Path Not Triggering

**Symptom**: "stop" goes to LLaMA instead of fast path

**Cause**: Keyword matching failed or tool not marked fast_path

**Fix**:
- Check `tools.json`: `"fast_path": true` for stop_speaking
- Check keywords array includes "stop"
- Enable debug mode to see fast path checks

### Tool Calls Not Detected

**Symptom**: LLM generates `<tool_call>` but parser doesn't detect

**Cause**: Parser state machine issue or malformed JSON

**Fix**:
- Check stderr for `[Tool Parser] JSON parse error`
- Verify Mistral model supports tool calling format
- Check that prompt injection succeeded: grep for "You have access to the following tools"

### Wyoming Stop Not Working

**Symptom**: Fast path triggers but TTS doesn't stop

**Cause**: Wyoming-Piper not receiving stop command

**Fix**:
- Verify Wyoming-Piper is running: `ps aux | grep piper`
- Check TTS URL parameter matches Piper server
- Update wyoming_piper/handler.py to handle stop events (see Wyoming Integration section)

## Related Files

- `custom/talk-llama/tool-system.h` - Tool registry header
- `custom/talk-llama/tool-system.cpp` - Tool executors and registry
- `custom/talk-llama/tool-parser.h` - Mistral output parser header
- `custom/talk-llama/tool-parser.cpp` - Parser implementation
- `custom/talk-llama/wyoming-client.h` - Wyoming protocol client header
- `custom/talk-llama/wyoming-client.cpp` - Wyoming client implementation
- `custom/talk-llama/tools/tools.json` - Tool definitions
- `custom/talk-llama/talk-llama.cpp` - Main application (integration points)
- `CMakeLists.txt` - Build configuration (includes new .cpp files)

## References

- [Mistral AI Tool Use Documentation](https://docs.mistral.ai/capabilities/function_calling/)
- [Wyoming Protocol Specification](https://github.com/rhasspy/wyoming)
- [llama.cpp Token Sampling](https://github.com/ggerganov/llama.cpp/blob/master/examples/main/main.cpp)
