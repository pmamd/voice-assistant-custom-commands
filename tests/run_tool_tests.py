import os
#!/usr/bin/env python3
"""
Tool System Test Runner

Focused test runner for tool system functionality.
Tests fast path tools, Wyoming events, and basic LLM tool calling.
"""

import asyncio
import json
import socket
import subprocess
import sys
import time
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ToolSystemTestRunner:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.binary = project_root / "build/bin/talk-llama-custom"
        self.wyoming_port = 10200
        self.results = []

    def check_wyoming_running(self) -> bool:
        """Check if Wyoming-Piper is running."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "wyoming-piper"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except:
            return False

    def send_wyoming_event(self, event_type: str, data: Dict = None) -> bool:
        """Send a Wyoming protocol event."""
        if data is None:
            data = {}

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(('localhost', self.wyoming_port))

            event = json.dumps({
                'type': event_type,
                'data': data
            }) + '\n'

            sock.send(event.encode('utf-8'))
            sock.close()
            return True
        except Exception as e:
            print(f"  Error sending Wyoming event: {e}")
            return False

    def test_wyoming_client(self) -> Tuple[bool, str]:
        """Test Wyoming client can send events."""
        print("\nTEST: Wyoming Client Communication")
        print("-" * 60)

        if not self.check_wyoming_running():
            return False, "Wyoming-Piper not running"

        # Test with our C++ client
        wyoming_test = self.project_root / "build/bin/test-wyoming-client"
        if not wyoming_test.exists():
            return False, "test-wyoming-client binary not found"

        try:
            result = subprocess.run(
                [str(wyoming_test), "localhost", "10200"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.project_root
            )

            output = result.stdout + result.stderr

            checks = [
                "audio-stop sent successfully",
                "audio-pause sent successfully",
                "audio-resume sent successfully"
            ]

            passed = all(check in output for check in checks)

            for check in checks:
                status = "✓" if check in output else "✗"
                print(f"  {status} {check}")

            return passed, output if not passed else ""

        except Exception as e:
            return False, str(e)

    def test_tool_initialization(self) -> Tuple[bool, str]:
        """Test tool system initializes correctly."""
        print("\nTEST: Tool System Initialization")
        print("-" * 60)

        try:
            # Start talk-llama and capture initialization
            proc = subprocess.Popen(
                [
                    str(self.binary),
                    "--llama-url", os.environ.get("LLAMA_URL", "http://127.0.0.1:8083"),
                    "-mw", "./whisper.cpp/models/ggml-tiny.en.bin",
                    "--xtts-url", "http://localhost:10200/",
                    "--xtts-voice", "en_US-lessac-medium",
                    "--temp", "0.5",
                    "-vth", "1.2",
                    "-c", "-1"
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.project_root
            )

            print("  Waiting for initialization (60s timeout)...")
            output_lines = []
            start_time = time.time()

            while time.time() - start_time < 60:
                line = proc.stdout.readline()
                if line:
                    output_lines.append(line)
                    if "Start speaking" in line or "Georgi:" in line:
                        break

            # Kill process
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except:
                proc.kill()

            output = "".join(output_lines)

            # Check for required initialization
            checks = {
                "Tool registry loaded": "[Tool System] Loaded 12 tools",
                "Wyoming client init": "[Wyoming Client] Initialized",
                "Tools injected": "[Tool System] Injected 12 tools",
            }

            results = {}
            for name, pattern in checks.items():
                found = pattern in output
                results[name] = found
                status = "✓" if found else "✗"
                print(f"  {status} {name}")

            passed = all(results.values())

            if not passed:
                error_lines = [line for line in output_lines if "Tool" in line or "Wyoming" in line or "ERROR" in line]
                return False, "\n".join(error_lines[:10])

            return True, ""

        except Exception as e:
            return False, str(e)

    def test_fast_path_keywords(self) -> Tuple[bool, str]:
        """Test fast path keyword matching."""
        print("\nTEST: Fast Path Keyword Matching")
        print("-" * 60)

        # For this test, we check the tools.json configuration
        tools_json = self.project_root / "custom/talk-llama/tools/tools.json"

        if not tools_json.exists():
            return False, "tools.json not found"

        try:
            with open(tools_json) as f:
                data = json.load(f)

            tools = data.get('tools', [])
            fast_path_tools = [t for t in tools if t.get('fast_path')]

            expected_fast_path = {
                'stop_speaking': ['stop', 'quiet', 'silence'],
                'pause_speaking': ['pause', 'hold on', 'wait'],
                'resume_speaking': ['resume', 'continue', 'go ahead']
            }

            passed = True
            for tool in fast_path_tools:
                name = tool.get('name')
                keywords = tool.get('keywords', [])

                if name in expected_fast_path:
                    expected_keywords = expected_fast_path[name]
                    has_keywords = any(kw in keywords for kw in expected_keywords)

                    status = "✓" if has_keywords else "✗"
                    print(f"  {status} {name}: {len(keywords)} keywords")

                    if not has_keywords:
                        passed = False

            print(f"  Total fast path tools: {len(fast_path_tools)}")

            return passed, ""

        except Exception as e:
            return False, str(e)

    def test_text_output_no_duplication(self) -> Tuple[bool, str]:
        """Test that text output doesn't duplicate (regression test for getText() bug)."""
        print("\nTEST: Text Output (No Duplication)")
        print("-" * 60)

        # This is a simple check - we verify the getText() function clears the buffer
        tool_parser_h = self.project_root / "custom/talk-llama/tool-parser.h"

        if not tool_parser_h.exists():
            return False, "tool-parser.h not found"

        try:
            with open(tool_parser_h) as f:
                content = f.read()

            # Check that getText() clears normal_text_
            has_clear = 'normal_text_ = ""' in content and 'getText()' in content

            status = "✓" if has_clear else "✗"
            print(f"  {status} getText() clears buffer to prevent duplication")

            return has_clear, "getText() doesn't clear buffer" if not has_clear else ""

        except Exception as e:
            return False, str(e)

    def test_tools_json_structure(self) -> Tuple[bool, str]:
        """Test tools.json has correct structure."""
        print("\nTEST: tools.json Structure")
        print("-" * 60)

        tools_json = self.project_root / "custom/talk-llama/tools/tools.json"

        try:
            with open(tools_json) as f:
                data = json.load(f)

            tools = data.get('tools', [])

            checks = {
                "12 tools defined": len(tools) == 12,
                "3 fast path tools": len([t for t in tools if t.get('fast_path')]) == 3,
                "stop_speaking exists": any(t.get('name') == 'stop_speaking' for t in tools),
                "pause_speaking exists": any(t.get('name') == 'pause_speaking' for t in tools),
                "resume_speaking exists": any(t.get('name') == 'resume_speaking' for t in tools),
                "set_temperature exists": any(t.get('name') == 'set_temperature' for t in tools),
            }

            passed = all(checks.values())

            for name, result in checks.items():
                status = "✓" if result else "✗"
                print(f"  {status} {name}")

            return passed, ""

        except Exception as e:
            return False, str(e)

    def test_wyoming_handler_events(self) -> Tuple[bool, str]:
        """Test Wyoming-Piper handler has event handlers."""
        print("\nTEST: Wyoming-Piper Event Handlers")
        print("-" * 60)

        handler_py = self.project_root / "wyoming-piper/wyoming_piper/handler.py"

        if not handler_py.exists():
            return False, "handler.py not found"

        try:
            with open(handler_py) as f:
                content = f.read()

            checks = {
                "AudioStop handler": 'AudioStop.is_type(event.type)' in content,
                "audio-pause handler": 'event.type == "audio-pause"' in content,
                "audio-resume handler": 'event.type == "audio-resume"' in content,
                "SIGSTOP for pause": 'signal.SIGSTOP' in content,
                "SIGCONT for resume": 'signal.SIGCONT' in content,
                "No hardcoded stop": 'stop" in raw_text' not in content,
            }

            passed = all(checks.values())

            for name, result in checks.items():
                status = "✓" if result else "✗"
                print(f"  {status} {name}")

            return passed, ""

        except Exception as e:
            return False, str(e)

    def test_no_old_stop_code(self) -> Tuple[bool, str]:
        """Verify old hardcoded stop detection has been removed."""
        print("\nTEST: No Old Stop Code (Regression)")
        print("-" * 60)

        talk_llama_cpp = self.project_root / "custom/talk-llama/talk-llama.cpp"

        if not talk_llama_cpp.exists():
            return False, "talk-llama.cpp not found"

        try:
            with open(talk_llama_cpp) as f:
                content = f.read()

            # Check for old patterns that should NOT exist
            old_patterns = {
                '[Stopped!]': r'printf.*\[Stopped!\]',
                'hardcoded stop check': r'if\s*\(\s*user_command\s*==\s*["\']stop["\'].*\)\s*\{[^}]*printf',
            }

            found_issues = []
            for name, pattern in old_patterns.items():
                if re.search(pattern, content):
                    found_issues.append(name)
                    print(f"  ✗ Found old code: {name}")

            if found_issues:
                return False, f"Old stop code still exists: {', '.join(found_issues)}"

            print("  ✓ No old hardcoded stop patterns found")
            return True, ""

        except Exception as e:
            return False, str(e)

    def test_pause_resume_state_management(self) -> Tuple[bool, str]:
        """Verify Wyoming-Piper properly manages pause/resume state."""
        print("\nTEST: Pause/Resume State Management")
        print("-" * 60)

        handler_py = self.project_root / "wyoming-piper/wyoming_piper/handler.py"

        if not handler_py.exists():
            return False, "handler.py not found"

        try:
            with open(handler_py) as f:
                content = f.read()

            # Check critical patterns for proper state management
            checks = {
                "Initialize paused=False when created": r'aplay_proc\.paused\s*=\s*False.*ACTIVE_APLAY_PROCESSES\.append',
                "Set paused=True in pause handler": r'event\.type.*audio-pause.*aplay_proc\.paused\s*=\s*True',
                "Check paused in resume handler": r'aplay_proc\.paused.*SIGCONT',
                "Set paused=False in resume handler": r'SIGCONT.*aplay_proc\.paused\s*=\s*False',
            }

            all_passed = True
            for check_name, pattern in checks.items():
                if re.search(pattern, content, re.DOTALL):
                    print(f"  ✓ {check_name}")
                else:
                    print(f"  ✗ {check_name}")
                    all_passed = False

            if all_passed:
                return True, ""
            else:
                return False, "State management patterns incomplete"

        except Exception as e:
            return False, str(e)

    def run_all_tests(self) -> int:
        """Run all tool system tests."""
        print("=" * 60)
        print("TOOL SYSTEM TEST SUITE")
        print("=" * 60)

        tests = [
            ("tools.json Structure", self.test_tools_json_structure),
            ("Fast Path Keywords", self.test_fast_path_keywords),
            ("Wyoming Handler Events", self.test_wyoming_handler_events),
            ("Text Output Fix", self.test_text_output_no_duplication),
            ("Wyoming Client", self.test_wyoming_client),
            ("Tool Initialization", self.test_tool_initialization),
            ("No Old Stop Code (Regression)", self.test_no_old_stop_code),
            ("Pause/Resume State Management", self.test_pause_resume_state_management),
        ]

        results = []
        for name, test_func in tests:
            try:
                passed, error = test_func()
                results.append((name, passed, error))

                if error and not passed:
                    print(f"\n  Error details: {error[:200]}")

            except Exception as e:
                print(f"\n  Exception: {e}")
                results.append((name, False, str(e)))

        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        passed_count = sum(1 for _, passed, _ in results if passed)
        total_count = len(results)

        for name, passed, error in results:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"{status}: {name}")
            if error and not passed:
                print(f"         {error[:100]}")

        print()
        print(f"Total: {passed_count}/{total_count} passed")
        print()

        if passed_count == total_count:
            print("✓ All tests passed!")
            return 0
        else:
            print(f"✗ {total_count - passed_count} test(s) failed")
            return 1


def main():
    """Main entry point."""
    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    print(f"Project root: {project_root}")
    print(f"Running from: {Path.cwd()}")
    print()

    runner = ToolSystemTestRunner(project_root)
    return runner.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
