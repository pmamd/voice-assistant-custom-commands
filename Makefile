.PHONY: all clean submodules talk-llama test help

# Default target - builds everything
all: submodules talk-llama
	@echo "Building Piper TTS from submodule..."
	@./scripts/build_piper.sh

help:
	@echo "Voice Assistant Build System"
	@echo ""
	@echo "Targets:"
	@echo "  all          - Build everything (default)"
	@echo "  talk-llama   - Build talk-llama-custom (main executable)"
	@echo "  test         - Run test suite"
	@echo "  clean        - Clean build artifacts"
	@echo "  clean-all    - Clean everything including submodules"
	@echo ""
	@echo "Example:"
	@echo "  make all       # Build everything"
	@echo "  make clean     # Clean build"
	@echo "  make test      # Run tests"
	@echo ""
	@echo "Note: 'make all' builds talk-llama and Piper TTS"
	@echo "      Whisper.cpp is built automatically by CMake"

# Initialize and update git submodules
submodules:
	@echo "Initializing git submodules..."
	@git submodule update --init --recursive

# Build talk-llama-custom using CMake
talk-llama: submodules
	@echo "Building talk-llama-custom..."
	@cmake -B build -DWHISPER_SDL2=ON
	@cmake --build build -j

# Run test suite
test: talk-llama
	@echo "Running test suite..."
	@cd tests && python3 run_tests.py --config test_cases.yaml --group smoke

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf build

# Clean everything including submodule builds
clean-all: clean
	@echo "Cleaning all build artifacts including submodules..."
	@rm -rf external/piper/.venv
	@rm -rf whisper.cpp/build
