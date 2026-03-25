#include "tool-system.h"
#include "wyoming-client.h"
#include <fstream>
#include <algorithm>
#include <cctype>
#include <sstream>
#include <cstdio>

namespace tool_system {

// Global Wyoming client pointer (set by main program)
WyomingClient* g_wyoming_client = nullptr;

// Track whether Wyoming audio is currently paused
std::atomic<bool> g_wyoming_paused{false};

// Singleton instance
ToolRegistry& ToolRegistry::getInstance() {
    static ToolRegistry instance;
    return instance;
}

// Load tools from JSON file
bool ToolRegistry::loadFromFile(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) {
        fprintf(stderr, "[Tool System] Failed to open tools file: %s\n", filepath.c_str());
        return false;
    }

    try {
        json j;
        file >> j;

        if (!j.contains("tools") || !j["tools"].is_array()) {
            fprintf(stderr, "[Tool System] Invalid tools.json format\n");
            return false;
        }

        tools_.clear();
        for (const auto& tool_json : j["tools"]) {
            ToolDefinition tool;
            tool.name = tool_json.value("name", "");
            tool.description = tool_json.value("description", "");
            tool.fast_path = tool_json.value("fast_path", false);

            if (tool_json.contains("keywords") && tool_json["keywords"].is_array()) {
                for (const auto& kw : tool_json["keywords"]) {
                    tool.keywords.push_back(kw.get<std::string>());
                }
            }

            if (tool_json.contains("parameters")) {
                tool.parameters_schema = tool_json["parameters"];
            }

            tools_.push_back(tool);
        }

        fprintf(stdout, "[Tool System] Loaded %zu tools from %s\n", tools_.size(), filepath.c_str());
        return true;

    } catch (const std::exception& e) {
        fprintf(stderr, "[Tool System] Error parsing tools.json: %s\n", e.what());
        return false;
    }
}

// Register executor
void ToolRegistry::registerExecutor(const std::string& tool_name, ToolExecutor executor) {
    executors_[tool_name] = executor;
}

// Normalize text for matching (lowercase, trim)
std::string ToolRegistry::normalizeText(const std::string& text) const {
    std::string result = text;

    // Convert to lowercase
    std::transform(result.begin(), result.end(), result.begin(),
        [](unsigned char c) { return std::tolower(c); });

    // Trim whitespace
    result.erase(result.begin(), std::find_if(result.begin(), result.end(),
        [](unsigned char c) { return !std::isspace(c); }));
    result.erase(std::find_if(result.rbegin(), result.rend(),
        [](unsigned char c) { return !std::isspace(c); }).base(), result.end());

    return result;
}

// Match fast path keywords
std::pair<bool, ToolDefinition> ToolRegistry::matchFastPath(const std::string& text) const {
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

// Execute tool
ToolResult ToolRegistry::execute(const std::string& tool_name, const json& arguments) {
    auto it = executors_.find(tool_name);
    if (it == executors_.end()) {
        return ToolResult(false, "Tool executor not found: " + tool_name);
    }

    try {
        return it->second(arguments);
    } catch (const std::exception& e) {
        return ToolResult(false, std::string("Tool execution error: ") + e.what());
    }
}

// Get tool definition
const ToolDefinition* ToolRegistry::getTool(const std::string& name) const {
    for (const auto& tool : tools_) {
        if (tool.name == name) {
            return &tool;
        }
    }
    return nullptr;
}

// Generate Mistral tool calling prompt
std::string ToolRegistry::getToolsPrompt() const {
    std::ostringstream oss;

    oss << "You have access to the following tools:\n\n";

    for (const auto& tool : tools_) {
        oss << "## " << tool.name << "\n";
        oss << tool.description << "\n";

        if (!tool.parameters_schema.empty() &&
            tool.parameters_schema.contains("properties") &&
            !tool.parameters_schema["properties"].empty()) {

            oss << "Parameters:\n";
            for (auto& [param_name, param_def] : tool.parameters_schema["properties"].items()) {
                oss << "- " << param_name;

                if (param_def.contains("type")) {
                    oss << " (" << param_def["type"].get<std::string>() << ")";
                }

                if (param_def.contains("description")) {
                    oss << ": " << param_def["description"].get<std::string>();
                }

                if (param_def.contains("enum")) {
                    oss << " [";
                    bool first = true;
                    for (const auto& val : param_def["enum"]) {
                        if (!first) oss << ", ";
                        oss << val.get<std::string>();
                        first = false;
                    }
                    oss << "]";
                }

                oss << "\n";
            }
        } else {
            oss << "No parameters required.\n";
        }

        oss << "\n";
    }

    oss << "To use a tool, output ONLY the tool call with no preamble or explanation:\n";
    oss << "<tool_call>{\"name\": \"tool_name\", \"arguments\": {...}, \"id\": \"unique_id\"}</tool_call>\n";
    oss << "Call tools immediately when requested. Do not say 'I'm sorry' or 'I didn't understand' — just execute the tool.\n";

    return oss.str();
}

// ===== BUILT-IN EXECUTORS =====

namespace executors {

ToolResult stop_speaking(const json& args) {
    fprintf(stdout, "[Tool] stop_speaking executed\n");

    if (g_wyoming_client == nullptr) {
        fprintf(stderr, "[Tool] ERROR: Wyoming client not initialized\n");
        return ToolResult(false, "Wyoming client not available");
    }

    g_wyoming_paused = false;
    if (g_wyoming_client->sendAudioStop()) {
        return ToolResult(true, "Okay.");
    } else {
        return ToolResult(false, "Failed to send stop command");
    }
}

ToolResult pause_speaking(const json& args) {
    fprintf(stdout, "[Tool] pause_speaking executed\n");

    if (g_wyoming_client == nullptr) {
        fprintf(stderr, "[Tool] ERROR: Wyoming client not initialized\n");
        return ToolResult(false, "Wyoming client not available");
    }

    if (g_wyoming_client->sendAudioPause()) {
        g_wyoming_paused = true;
        return ToolResult(true, "Paused.");
    } else {
        return ToolResult(false, "Failed to send pause command");
    }
}

ToolResult resume_speaking(const json& args) {
    fprintf(stdout, "[Tool] resume_speaking executed\n");

    if (g_wyoming_client == nullptr) {
        fprintf(stderr, "[Tool] ERROR: Wyoming client not initialized\n");
        return ToolResult(false, "Wyoming client not available");
    }

    if (g_wyoming_client->sendAudioResume()) {
        g_wyoming_paused = false;
        return ToolResult(true, "Resuming.");
    } else {
        return ToolResult(false, "Failed to send resume command");
    }
}

ToolResult set_temperature(const json& args) {
    if (!args.contains("value")) {
        return ToolResult(false, "Missing 'value' parameter");
    }

    double temp = args["value"].get<double>();
    std::string zone = args.value("zone", "both");

    // Validate range
    if (temp < 60.0 || temp > 85.0) {
        return ToolResult(false, "Temperature must be between 60 and 85 degrees");
    }

    fprintf(stdout, "[Tool] set_temperature: %.1f°F (%s)\n", temp, zone.c_str());

    json result_data;
    result_data["temperature"] = temp;
    result_data["zone"] = zone;

    return ToolResult(true, "Temperature set to " + std::to_string((int)temp) + " degrees", result_data);
}

ToolResult set_fan_speed(const json& args) {
    if (!args.contains("level")) {
        return ToolResult(false, "Missing 'level' parameter");
    }

    std::string level = args["level"].get<std::string>();
    fprintf(stdout, "[Tool] set_fan_speed: %s\n", level.c_str());

    json result_data;
    result_data["fan_level"] = level;

    return ToolResult(true, "Fan speed set to " + level, result_data);
}

ToolResult enable_defrost(const json& args) {
    if (!args.contains("location")) {
        return ToolResult(false, "Missing 'location' parameter");
    }

    std::string location = args["location"].get<std::string>();
    std::string mode = args.value("mode", "defrost");

    fprintf(stdout, "[Tool] enable_defrost: %s %s\n", location.c_str(), mode.c_str());

    json result_data;
    result_data["location"] = location;
    result_data["mode"] = mode;

    return ToolResult(true, location + " windshield " + mode + " activated", result_data);
}

ToolResult navigate_to(const json& args) {
    std::string dest;

    if (args.contains("preset")) {
        dest = args["preset"].get<std::string>();
        fprintf(stdout, "[Tool] navigate_to: preset '%s'\n", dest.c_str());
    } else if (args.contains("destination")) {
        dest = args["destination"].get<std::string>();
        fprintf(stdout, "[Tool] navigate_to: '%s'\n", dest.c_str());
    } else {
        return ToolResult(false, "Missing 'destination' or 'preset' parameter");
    }

    json result_data;
    result_data["destination"] = dest;

    return ToolResult(true, "Navigation started to " + dest, result_data);
}

ToolResult find_nearby(const json& args) {
    if (!args.contains("category")) {
        return ToolResult(false, "Missing 'category' parameter");
    }

    std::string category = args["category"].get<std::string>();
    double max_dist = args.value("max_distance", 5.0);

    fprintf(stdout, "[Tool] find_nearby: %s within %.1f miles\n", category.c_str(), max_dist);

    // Mock result - in real implementation, would query POI database
    json result_data;
    result_data["category"] = category;
    result_data["max_distance"] = max_dist;
    result_data["results_found"] = 3;  // Mock

    return ToolResult(true, "Found 3 nearby " + category + " locations", result_data);
}

ToolResult get_eta(const json& args) {
    fprintf(stdout, "[Tool] get_eta executed\n");

    // Mock result - in real implementation, would query navigation system
    json result_data;
    result_data["eta_minutes"] = 15;
    result_data["distance_miles"] = 8.5;

    return ToolResult(true, "ETA: 15 minutes, 8.5 miles remaining", result_data);
}

ToolResult check_tire_pressure(const json& args) {
    fprintf(stdout, "[Tool] check_tire_pressure executed\n");

    // Mock result - in real implementation, would read from vehicle CAN bus
    json result_data;
    result_data["front_left"] = 35;
    result_data["front_right"] = 35;
    result_data["rear_left"] = 33;
    result_data["rear_right"] = 34;
    result_data["status"] = "normal";

    return ToolResult(true, "All tire pressures normal", result_data);
}

ToolResult get_fuel_range(const json& args) {
    fprintf(stdout, "[Tool] get_fuel_range executed\n");

    // Mock result
    json result_data;
    result_data["range_miles"] = 285;
    result_data["fuel_percent"] = 65;

    return ToolResult(true, "Fuel range: 285 miles remaining", result_data);
}

ToolResult check_vehicle_status(const json& args) {
    std::string detail = args.value("detail_level", "summary");
    fprintf(stdout, "[Tool] check_vehicle_status: %s\n", detail.c_str());

    // Mock result
    json result_data;
    result_data["warnings"] = 0;
    result_data["maintenance_due"] = false;
    result_data["status"] = "all_ok";

    return ToolResult(true, "All vehicle systems normal, no warnings", result_data);
}

} // namespace executors

// Register all built-in executors
void registerBuiltinExecutors(ToolRegistry& registry) {
    registry.registerExecutor("stop_speaking", executors::stop_speaking);
    registry.registerExecutor("pause_speaking", executors::pause_speaking);
    registry.registerExecutor("resume_speaking", executors::resume_speaking);
    registry.registerExecutor("set_temperature", executors::set_temperature);
    registry.registerExecutor("set_fan_speed", executors::set_fan_speed);
    registry.registerExecutor("enable_defrost", executors::enable_defrost);
    registry.registerExecutor("navigate_to", executors::navigate_to);
    registry.registerExecutor("find_nearby", executors::find_nearby);
    registry.registerExecutor("get_eta", executors::get_eta);
    registry.registerExecutor("check_tire_pressure", executors::check_tire_pressure);
    registry.registerExecutor("get_fuel_range", executors::get_fuel_range);
    registry.registerExecutor("check_vehicle_status", executors::check_vehicle_status);
}

} // namespace tool_system
