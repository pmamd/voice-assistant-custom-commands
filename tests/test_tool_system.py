import os
#!/usr/bin/env python3
"""
Tool System Integration Test

Tests the Mistral tool calling implementation including:
- Tool registry initialization
- Wyoming client communication
- Fast path keyword matching
- Tool execution
"""

import subprocess
import sys
import time
from pathlib import Path


class ToolSystemTester:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.binary = self.project_root / "build/bin/talk-llama-custom"
        self.wyoming_test = self.project_root / "build/bin/test-wyoming-client"
        self.tools_json = self.project_root / "custom/talk-llama/tools/tools.json"

    def test_files_exist(self):
        """Test that all required files exist."""
        print("TEST: Required files exist")
        print("-" * 50)

        tests = [
            (self.binary, "talk-llama-custom binary"),
            (self.wyoming_test, "test-wyoming-client binary"),
            (self.tools_json, "tools.json config"),
        ]

        all_passed = True
        for path, name in tests:
            exists = path.exists()
            status = "✓ PASS" if exists else "✗ FAIL"
            print(f"  {status}: {name}")
            if not exists:
                print(f"         Missing: {path}")
                all_passed = False

        print()
        return all_passed

    def test_wyoming_client(self):
        """Test Wyoming client can send events."""
        print("TEST: Wyoming client communication")
        print("-" * 50)

        try:
            result = subprocess.run(
                [str(self.wyoming_test), "localhost", "10200"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10
            )

            # Check for success indicators
            output = result.stdout + result.stderr
            checks = [
                ("audio-stop sent successfully", "audio-stop event"),
                ("audio-pause sent successfully", "audio-pause event"),
                ("audio-resume sent successfully", "audio-resume event"),
                ("Connected to localhost:10200", "Wyoming connection"),
            ]

            all_passed = True
            for substring, test_name in checks:
                passed = substring in output
                status = "✓ PASS" if passed else "✗ FAIL"
                print(f"  {status}: {test_name}")
                if not passed:
                    all_passed = False

            if not all_passed:
                print("\nOutput:")
                print(output)

            print()
            return all_passed

        except subprocess.TimeoutExpired:
            print("  ✗ FAIL: Wyoming client test timed out")
            print()
            return False
        except Exception as e:
            print(f"  ✗ FAIL: {e}")
            print()
            return False

    def test_tool_system_init(self):
        """Test that tool system initializes correctly."""
        print("TEST: Tool system initialization")
        print("-" * 50)

        try:
            # Run talk-llama briefly to capture initialization output
            proc = subprocess.Popen(
                [
                    str(self.binary),
                    "--llama-url", os.environ.get("LLAMA_URL", "http://127.0.0.1:8083"),
                    "-mw", "./whisper.cpp/models/ggml-base.en.bin",
                    "--xtts-url", "http://localhost:10200/",
                    "--xtts-voice", "en_US-lessac-medium",
                    "--temp", "0.5",
                    "-vth", "1.2",
                    "-c", "-1"
                ],
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            # Wait for initialization (up to 60 seconds)
            print("  Waiting for initialization (this may take a minute)...")
            output_lines = []
            start_time = time.time()
            timeout = 60

            while time.time() - start_time < timeout:
                line = proc.stdout.readline()
                if line:
                    output_lines.append(line)
                    # Check if we've reached the "Start speaking" prompt
                    if "Start speaking" in line or "Georgi:" in line:
                        break

            # Kill the process
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

            output = "".join(output_lines)

            # Check for tool system initialization
            checks = [
                ("[Tool System] Loaded 12 tools", "Tool registry loaded"),
                ("[Wyoming Client] Initialized", "Wyoming client initialized"),
                ("[Tool System] Injected 12 tools into system prompt", "Tools injected into prompt"),
            ]

            all_passed = True
            for substring, test_name in checks:
                passed = substring in output
                status = "✓ PASS" if passed else "✗ FAIL"
                print(f"  {status}: {test_name}")
                if not passed:
                    all_passed = False

            if not all_passed:
                print("\nRelevant output:")
                for line in output_lines:
                    if "Tool" in line or "Wyoming" in line:
                        print(f"    {line.strip()}")

            print()
            return all_passed

        except Exception as e:
            print(f"  ✗ FAIL: {e}")
            print()
            return False

    def test_tools_json(self):
        """Test that tools.json is valid and has expected tools."""
        print("TEST: tools.json configuration")
        print("-" * 50)

        try:
            import json

            with open(self.tools_json) as f:
                data = json.load(f)

            checks = []

            # Check structure
            if "tools" in data:
                checks.append((True, "tools array exists"))
                tools = data["tools"]

                # Check tool count
                tool_count = len(tools)
                checks.append((tool_count == 12, f"12 tools defined (found {tool_count})"))

                # Check for specific tools
                tool_names = [t.get("name") for t in tools]
                expected_tools = [
                    "stop_speaking",
                    "pause_speaking",
                    "resume_speaking",
                    "set_temperature",
                    "navigate_to"
                ]

                for tool_name in expected_tools:
                    checks.append((tool_name in tool_names, f"'{tool_name}' tool exists"))

                # Check fast path tools
                fast_path_tools = [t for t in tools if t.get("fast_path")]
                checks.append((len(fast_path_tools) == 3, f"3 fast path tools (found {len(fast_path_tools)})"))

            else:
                checks.append((False, "tools array exists"))

            all_passed = True
            for passed, test_name in checks:
                status = "✓ PASS" if passed else "✗ FAIL"
                print(f"  {status}: {test_name}")
                if not passed:
                    all_passed = False

            print()
            return all_passed

        except Exception as e:
            print(f"  ✗ FAIL: {e}")
            print()
            return False

    def run_all_tests(self):
        """Run all tests and return overall result."""
        print("=" * 60)
        print("TOOL SYSTEM INTEGRATION TESTS")
        print("=" * 60)
        print()

        results = []

        # Run tests in order
        results.append(("Files Exist", self.test_files_exist()))
        results.append(("tools.json Valid", self.test_tools_json()))
        results.append(("Wyoming Client", self.test_wyoming_client()))
        results.append(("Tool System Init", self.test_tool_system_init()))

        # Summary
        print("=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        passed_count = sum(1 for _, passed in results if passed)
        total_count = len(results)

        for test_name, passed in results:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"{status}: {test_name}")

        print()
        print(f"Total: {passed_count}/{total_count} passed")
        print()

        if passed_count == total_count:
            print("✓ All tests passed!")
            return 0
        else:
            print(f"✗ {total_count - passed_count} test(s) failed")
            return 1


if __name__ == "__main__":
    tester = ToolSystemTester()
    sys.exit(tester.run_all_tests())
