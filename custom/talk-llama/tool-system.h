#pragma once

#include <string>
#include <vector>
#include <map>
#include <functional>
#include <memory>
#include "../../whisper.cpp/examples/json.hpp"

using json = nlohmann::json;

namespace tool_system {

// Result of tool execution
struct ToolResult {
    bool success;
    std::string message;
    json data;  // Additional data (e.g., temperature value, tire pressures)

    ToolResult() : success(false) {}
    ToolResult(bool s, const std::string& msg = "", const json& d = json::object())
        : success(s), message(msg), data(d) {}
};

// Tool definition loaded from JSON
struct ToolDefinition {
    std::string name;
    std::string description;
    bool fast_path;  // Execute immediately on keyword match (pre-LLaMA)
    std::vector<std::string> keywords;  // For fast path matching
    json parameters_schema;  // JSON schema for parameters

    ToolDefinition() : fast_path(false) {}
};

// Function type for tool executors
using ToolExecutor = std::function<ToolResult(const json& args)>;

// Tool registry - manages tool definitions and execution
class ToolRegistry {
public:
    static ToolRegistry& getInstance();

    // Load tools from JSON file
    bool loadFromFile(const std::string& filepath);

    // Register a tool executor function
    void registerExecutor(const std::string& tool_name, ToolExecutor executor);

    // Check if text matches a fast-path tool keyword
    std::pair<bool, ToolDefinition> matchFastPath(const std::string& text) const;

    // Execute a tool by name
    ToolResult execute(const std::string& tool_name, const json& arguments);

    // Get all tools as Mistral-formatted prompt text
    std::string getToolsPrompt() const;

    // Get tool definition by name
    const ToolDefinition* getTool(const std::string& name) const;

    // Get all tool definitions
    const std::vector<ToolDefinition>& getAllTools() const { return tools_; }

private:
    ToolRegistry() = default;
    ToolRegistry(const ToolRegistry&) = delete;
    ToolRegistry& operator=(const ToolRegistry&) = delete;

    std::vector<ToolDefinition> tools_;
    std::map<std::string, ToolExecutor> executors_;

    // Helper: normalize text for keyword matching
    std::string normalizeText(const std::string& text) const;
};

// Built-in tool executors
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

// Helper function to register all built-in executors
void registerBuiltinExecutors(ToolRegistry& registry);

} // namespace tool_system
