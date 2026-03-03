#include "wyoming-client.h"
#include <cstdio>
#include <cstring>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <regex>

namespace tool_system {

WyomingClient::WyomingClient(const std::string& host, int port)
    : host_(host), port_(port), socket_fd_(-1), connected_(false) {
}

WyomingClient::~WyomingClient() {
    disconnect();
}

bool WyomingClient::connect() {
    if (connected_) {
        return true;
    }

    // Create socket
    socket_fd_ = socket(AF_INET, SOCK_STREAM, 0);
    if (socket_fd_ < 0) {
        fprintf(stderr, "[Wyoming Client] Failed to create socket: %s\n", strerror(errno));
        return false;
    }

    // Set socket timeout (5 seconds)
    struct timeval timeout;
    timeout.tv_sec = 5;
    timeout.tv_usec = 0;
    setsockopt(socket_fd_, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    setsockopt(socket_fd_, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

    // Resolve hostname
    struct hostent* server = gethostbyname(host_.c_str());
    if (server == nullptr) {
        fprintf(stderr, "[Wyoming Client] Failed to resolve host: %s\n", host_.c_str());
        close(socket_fd_);
        socket_fd_ = -1;
        return false;
    }

    // Setup server address
    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    memcpy(&server_addr.sin_addr.s_addr, server->h_addr, server->h_length);
    server_addr.sin_port = htons(port_);

    // Connect
    if (::connect(socket_fd_, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        fprintf(stderr, "[Wyoming Client] Failed to connect to %s:%d: %s\n",
                host_.c_str(), port_, strerror(errno));
        close(socket_fd_);
        socket_fd_ = -1;
        return false;
    }

    connected_ = true;
    fprintf(stdout, "[Wyoming Client] Connected to %s:%d\n", host_.c_str(), port_);
    return true;
}

void WyomingClient::disconnect() {
    if (socket_fd_ >= 0) {
        close(socket_fd_);
        socket_fd_ = -1;
    }
    connected_ = false;
}

bool WyomingClient::isConnected() const {
    return connected_;
}

bool WyomingClient::sendEvent(const std::string& event_type, const std::string& data_json) {
    // Ensure connection
    if (!connected_ && !connect()) {
        return false;
    }

    // Build Wyoming protocol event: {"type": "...", "data": {...}}\n
    std::string event_json = "{\"type\": \"" + event_type + "\", \"data\": " + data_json + "}\n";

    // Send event
    ssize_t bytes_sent = send(socket_fd_, event_json.c_str(), event_json.length(), 0);
    if (bytes_sent < 0) {
        fprintf(stderr, "[Wyoming Client] Failed to send event '%s': %s\n",
                event_type.c_str(), strerror(errno));
        disconnect();
        return false;
    }

    if ((size_t)bytes_sent != event_json.length()) {
        fprintf(stderr, "[Wyoming Client] Incomplete send for event '%s': %zd/%zu bytes\n",
                event_type.c_str(), bytes_sent, event_json.length());
        disconnect();
        return false;
    }

    fprintf(stdout, "[Wyoming Client] Sent event: %s", event_json.c_str());
    return true;
}

bool WyomingClient::sendAudioStop() {
    // AudioStop event format: {"type": "audio-stop", "data": {"timestamp": null}}
    return sendEvent("audio-stop", "{\"timestamp\": null}");
}

bool WyomingClient::sendAudioPause() {
    // Custom audio-pause event: {"type": "audio-pause", "data": {}}
    return sendEvent("audio-pause", "{}");
}

bool WyomingClient::sendAudioResume() {
    // Custom audio-resume event: {"type": "audio-resume", "data": {}}
    return sendEvent("audio-resume", "{}");
}

bool parseWyomingUrl(const std::string& url, std::string& host, int& port) {
    // Parse URL like "http://localhost:10200/" or "tcp://127.0.0.1:10200"
    // Default port for Wyoming is 10200
    port = 10200;
    host = "localhost";

    // Simple regex to extract host and port
    // Matches: [protocol://]host[:port][/path]
    std::regex url_regex(R"(^(?:[a-z]+://)?([^:/?]+)(?::(\d+))?)", std::regex::icase);
    std::smatch matches;

    if (std::regex_search(url, matches, url_regex)) {
        if (matches.size() >= 2 && matches[1].matched) {
            host = matches[1].str();
        }
        if (matches.size() >= 3 && matches[2].matched) {
            try {
                port = std::stoi(matches[2].str());
            } catch (...) {
                fprintf(stderr, "[Wyoming Client] Invalid port in URL: %s\n", url.c_str());
                return false;
            }
        }
        return true;
    }

    fprintf(stderr, "[Wyoming Client] Failed to parse URL: %s\n", url.c_str());
    return false;
}

} // namespace tool_system
