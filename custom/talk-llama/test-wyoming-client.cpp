#include "wyoming-client.h"
#include <cstdio>
#include <unistd.h>

int main(int argc, char** argv) {
    std::string host = "localhost";
    int port = 10200;

    if (argc >= 2) {
        host = argv[1];
    }
    if (argc >= 3) {
        port = std::stoi(argv[2]);
    }

    fprintf(stdout, "Testing Wyoming Client\n");
    fprintf(stdout, "Connecting to %s:%d\n\n", host.c_str(), port);

    tool_system::WyomingClient client(host, port);

    // Test 1: Send audio-stop
    fprintf(stdout, "Test 1: Sending audio-stop event...\n");
    if (client.sendAudioStop()) {
        fprintf(stdout, "✓ audio-stop sent successfully\n");
    } else {
        fprintf(stderr, "✗ Failed to send audio-stop\n");
    }
    sleep(1);

    // Test 2: Send audio-pause
    fprintf(stdout, "\nTest 2: Sending audio-pause event...\n");
    if (client.sendAudioPause()) {
        fprintf(stdout, "✓ audio-pause sent successfully\n");
    } else {
        fprintf(stderr, "✗ Failed to send audio-pause\n");
    }
    sleep(1);

    // Test 3: Send audio-resume
    fprintf(stdout, "\nTest 3: Sending audio-resume event...\n");
    if (client.sendAudioResume()) {
        fprintf(stdout, "✓ audio-resume sent successfully\n");
    } else {
        fprintf(stderr, "✗ Failed to send audio-resume\n");
    }

    fprintf(stdout, "\nAll tests completed!\n");
    return 0;
}
