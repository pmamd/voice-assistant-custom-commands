#include "wyoming-client.h"
#include <cstdio>

// Forward declaration of send_tts_async from talk-llama.cpp
extern void send_tts_async(std::string text, std::string speaker_wav, std::string language,
                           std::string tts_url, int reply_part, bool debug);

namespace tool_system {

WyomingClient::WyomingClient(const std::string& base_url)
    : base_url_(base_url) {
}

bool WyomingClient::sendStop(const std::string& voice, const std::string& language) {
    try {
        fprintf(stdout, "[Wyoming Client] Sending stop command\n");
        send_tts_async("stop", voice, language, base_url_, 0, false);
        return true;
    } catch (...) {
        fprintf(stderr, "[Wyoming Client] Failed to send stop command\n");
        return false;
    }
}

void send_wyoming_stop_command(const std::string& voice,
                                 const std::string& language,
                                 const std::string& tts_url,
                                 bool debug) {
    send_tts_async("stop", voice, language, tts_url, 0, debug);
}

} // namespace tool_system
