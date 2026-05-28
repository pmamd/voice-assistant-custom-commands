#!/usr/bin/env bash
# Wrapper to run tests with venv if available

set -e

cd "$(dirname "$0")/.."

if [ -f "venv/bin/activate" ]; then
    echo "Using virtualenv for tests..."
    source venv/bin/activate
    python3 tests/run_tests.py "$@"
else
    echo "No virtualenv found, using system Python..."
    python3 tests/run_tests.py "$@"
fi
