#!/bin/bash
# Latency Benchmark - Compare NPU vs Baseline Whisper
# Measures end-to-end latency on target board (.26)

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_AUDIO="$PROJECT_ROOT/tests/audio/inputs/make_it_warmer.wav"
BINARY="$PROJECT_ROOT/build/bin/talk-llama-custom"
RESULTS_DIR="$PROJECT_ROOT/tests/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "LATENCY BENCHMARK"
echo "=========================================="
echo "Target Board: amd@192.168.86.26"
echo "Test Audio: $TEST_AUDIO"
echo "Timestamp: $TIMESTAMP"
echo ""

# Check if test audio exists
if [ ! -f "$TEST_AUDIO" ]; then
    echo "Error: Test audio not found at $TEST_AUDIO"
    echo "Generating test audio..."
    python3 "$PROJECT_ROOT/tests/audio_generator.py" \
        --text "Make it warmer" \
        --output "$TEST_AUDIO" \
        --piper-bin ~/.local/bin/piper
fi

mkdir -p "$RESULTS_DIR"

run_test() {
    local test_name="$1"
    local whisper_args="$2"
    local result_file="$RESULTS_DIR/latency_${test_name}_${TIMESTAMP}.log"

    echo -e "${YELLOW}Running: $test_name${NC}"
    echo "Whisper args: $whisper_args"
    echo "Output: $result_file"
    echo ""

    # Run the test with HSA override for gfx1153 (890M iGPU)
    HSA_OVERRIDE_GFX_VERSION=11.5.1 $BINARY \
        --test-input "$TEST_AUDIO" \
        --llama-url http://localhost:8080 \
        -mw ./whisper.cpp/models/ggml-base.en.bin \
        $whisper_args \
        --xtts-url http://localhost:10200/ \
        --xtts-voice en_US-lessac-medium \
        --temp 0.5 \
        -vth 1.2 \
        -c -1 \
        --debug \
        2>&1 | tee "$result_file"

    # Extract latency metrics
    echo ""
    echo -e "${GREEN}=== Latency Metrics: $test_name ===${NC}"
    grep "\[LATENCY\]" "$result_file" || echo "No latency data found"
    echo ""
}

# Test 1: CPU Baseline
echo "Test 1: CPU Baseline (no GPU)"
echo "----------------------------------------"
run_test "cpu_baseline" "--no-gpu"
sleep 2

# Test 2: GPU Baseline
echo "Test 2: GPU Baseline (ROCm iGPU)"
echo "----------------------------------------"
run_test "gpu_baseline" ""
sleep 2

# Test 3: NPU (if available)
if [ -f "$PROJECT_ROOT/whisper.cpp/models/ggml-base.en.bin" ]; then
    echo "Test 3: NPU (VitisAI)"
    echo "----------------------------------------"
    # Note: NPU support requires specific whisper.cpp build
    # and XRT environment from start-assistant.sh
    if grep -q "WHISPER_VITISAI" "$BINARY" 2>/dev/null; then
        run_test "npu" ""
    else
        echo "NPU not available in this build"
    fi
    sleep 2
fi

# Generate summary report
SUMMARY_FILE="$RESULTS_DIR/latency_summary_${TIMESTAMP}.txt"

echo "=========================================="
echo "GENERATING SUMMARY REPORT"
echo "=========================================="

{
    echo "LATENCY BENCHMARK SUMMARY"
    echo "Date: $(date)"
    echo "Board: amd@192.168.86.26 (890M iGPU)"
    echo "Test Audio: make_it_warmer.wav"
    echo ""
    echo "========================================"

    for test in cpu_baseline gpu_baseline npu; do
        log_file="$RESULTS_DIR/latency_${test}_${TIMESTAMP}.log"
        if [ -f "$log_file" ]; then
            echo ""
            echo "--- $test ---"
            grep "\[LATENCY\]" "$log_file" | sed 's/\[LATENCY\] /  /'
        fi
    done

    echo ""
    echo "========================================"
    echo "Individual logs saved in: $RESULTS_DIR"
    echo "========================================"

} | tee "$SUMMARY_FILE"

echo ""
echo -e "${GREEN}Summary saved to: $SUMMARY_FILE${NC}"
echo ""
echo "To run on target board (.26):"
echo "  scp tests/latency_benchmark.sh amd@192.168.86.26:~/git/voice-assistant-custom-commands/tests/"
echo "  ssh amd@192.168.86.26 'cd ~/git/voice-assistant-custom-commands && ./tests/latency_benchmark.sh'"
