#!/usr/bin/env python3
"""Deploy talk-llama-fast changes to development machine and build/test."""

import paramiko
import sys
import os
from pathlib import Path

# Development machine credentials
HOST = "192.168.86.74"
USER = "paul"
PASSWORD = "amdisthebest"
# Remote machine path (different from local)
REMOTE_BASE = "/home/paul/Projects/git/talk-llama-fast"

# Local base directory
LOCAL_BASE = Path(__file__).parent


def create_ssh_client():
    """Create and return SSH client connection."""
    print(f"Connecting to {USER}@{HOST}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
        print("✓ Connected successfully")
        return client
    except Exception as e:
        print(f"✗ Connection failed: {e}", file=sys.stderr)
        sys.exit(1)


def execute_remote(ssh, command, cwd=None):
    """Execute command on remote machine and return output."""
    if cwd:
        command = f"cd {cwd} && {command}"

    print(f"  $ {command}")
    stdin, stdout, stderr = ssh.exec_command(command)

    output = stdout.read().decode()
    error = stderr.read().decode()
    exit_code = stdout.channel.recv_exit_status()

    if output:
        print(output)
    if error and exit_code != 0:
        print(f"Error: {error}", file=sys.stderr)

    return exit_code, output, error


def sync_files(ssh):
    """Sync changed files to remote dev machine using SFTP."""
    print("\n1. Syncing files to dev machine...")

    # Check if project exists
    exit_code, output, _ = execute_remote(ssh, f"test -f {REMOTE_BASE}/CMakeLists.txt && echo 'exists' || echo 'missing'")
    project_exists = 'exists' in output

    # Create base directory structure
    print("  → Creating remote directories...")
    execute_remote(ssh, f"mkdir -p {REMOTE_BASE}/tests {REMOTE_BASE}/examples/talk-llama {REMOTE_BASE}/.github/workflows {REMOTE_BASE}/ggml/include {REMOTE_BASE}/ggml/src {REMOTE_BASE}/cmake {REMOTE_BASE}/src {REMOTE_BASE}/bindings {REMOTE_BASE}/include")

    # Use SFTP for file transfer
    sftp = ssh.open_sftp()

    def put_dir(local_dir, remote_dir):
        """Recursively upload directory."""
        for item in local_dir.iterdir():
            local_path = str(item)
            remote_path = f"{remote_dir}/{item.name}"

            if item.is_file():
                print(f"    {item.name}")
                sftp.put(local_path, remote_path)
            elif item.is_dir():
                try:
                    sftp.mkdir(remote_path)
                except:
                    pass  # Directory might already exist
                put_dir(item, remote_path)

    # Always sync these changed/test files (even if project exists)
    # Sync test harness
    print("  → Syncing tests/")
    put_dir(LOCAL_BASE / 'tests', f'{REMOTE_BASE}/tests')

    # Sync talk-llama directory (includes TTS socket files and talk-llama.cpp)
    print("  → Syncing talk-llama directory with TTS socket files")
    if (LOCAL_BASE / 'examples' / 'talk-llama').exists():
        execute_remote(ssh, f"mkdir -p {REMOTE_BASE}/examples/talk-llama")
        for item in (LOCAL_BASE / 'examples' / 'talk-llama').iterdir():
            if item.is_file():
                print(f"    {item.name}")
                sftp.put(str(item), f'{REMOTE_BASE}/examples/talk-llama/{item.name}')

    # Sync GitHub workflows
    print("  → Syncing .github/workflows/")
    put_dir(LOCAL_BASE / '.github', f'{REMOTE_BASE}/.github')

    # Sync setup script for external dependencies
    print("  → Syncing setup_external_deps.sh")
    if (LOCAL_BASE / 'setup_external_deps.sh').exists():
        sftp.put(str(LOCAL_BASE / 'setup_external_deps.sh'), f'{REMOTE_BASE}/setup_external_deps.sh')

    # Sync root CMakeLists.txt and essential files if project doesn't exist
    if not project_exists:
        print("  → Syncing CMakeLists.txt and essential build files...")
        essential_files = ['CMakeLists.txt', 'LICENSE', 'README.md']
        for file in essential_files:
            src = LOCAL_BASE / file
            if src.exists():
                print(f"    {file}")
                sftp.put(str(src), f'{REMOTE_BASE}/{file}')

        # Sync include subdirectory (required for build - whisper.h)
        print("  → Syncing include/ directory...")
        if (LOCAL_BASE / 'include').exists():
            put_dir(LOCAL_BASE / 'include', f'{REMOTE_BASE}/include')

        # Sync cmake subdirectory (required for build configuration)
        print("  → Syncing cmake/ directory...")
        if (LOCAL_BASE / 'cmake').exists():
            put_dir(LOCAL_BASE / 'cmake', f'{REMOTE_BASE}/cmake')

        # Sync src subdirectory (required for build)
        print("  → Syncing src/ directory...")
        if (LOCAL_BASE / 'src').exists():
            put_dir(LOCAL_BASE / 'src', f'{REMOTE_BASE}/src')

        # Sync bindings subdirectory (required by CMake)
        print("  → Syncing bindings/ directory...")
        if (LOCAL_BASE / 'bindings').exists():
            put_dir(LOCAL_BASE / 'bindings', f'{REMOTE_BASE}/bindings')

        # Sync ggml subdirectory (required for build)
        print("  → Syncing ggml/ (this may take a moment)...")
        if (LOCAL_BASE / 'ggml').exists():
            put_dir(LOCAL_BASE / 'ggml', f'{REMOTE_BASE}/ggml')

        # Sync entire examples directory (required for talk-llama build)
        print("  → Syncing examples/ directory (this may take a while)...")
        if (LOCAL_BASE / 'examples').exists():
            put_dir(LOCAL_BASE / 'examples', f'{REMOTE_BASE}/examples')

    sftp.close()
    print("✓ Files synced successfully\n")
    return True


def install_dependencies(ssh):
    """Install required dependencies on dev machine."""
    print("\n2. Installing dependencies...")

    # Use echo password | sudo -S to provide password
    commands = [
        f"echo '{PASSWORD}' | sudo -S apt-get update -qq",
        f"echo '{PASSWORD}' | sudo -S apt-get install -y libcjson-dev libsdl2-dev libcurl4-openssl-dev"
    ]

    for cmd in commands:
        exit_code, _, _ = execute_remote(ssh, cmd, cwd=REMOTE_BASE)
        if exit_code != 0:
            print("✗ Dependency installation failed", file=sys.stderr)
            return False

    # Setup external dependencies (piper and voices)
    print("  → Setting up external dependencies...")
    execute_remote(ssh, "chmod +x setup_external_deps.sh", cwd=REMOTE_BASE)
    exit_code, output, error = execute_remote(ssh, "./setup_external_deps.sh", cwd=REMOTE_BASE)
    if exit_code != 0:
        print(f"  ⚠ External dependencies setup had issues: {error}")
        print("  Continuing anyway...")

    # Install Wyoming-Piper if not already installed
    print("  → Installing Wyoming-Piper...")
    exit_code, _, _ = execute_remote(ssh, "pip3 install --user wyoming-piper", cwd=REMOTE_BASE)
    if exit_code == 0:
        print("  ✓ Wyoming-Piper installed")
    else:
        print("  ⚠ Wyoming-Piper installation failed (may already be installed)")

    print("✓ Dependencies installed\n")
    return True


def build_project(ssh):
    """Build the project on dev machine."""
    print("\n3. Building project...")

    # Configure with GPU support
    exit_code, _, _ = execute_remote(ssh,
                                     "cmake -B build -DWHISPER_SDL2=ON -DGGML_HIPBLAS=ON",
                                     cwd=REMOTE_BASE)
    if exit_code != 0:
        print("✗ CMake configuration failed", file=sys.stderr)
        return False

    # Build
    exit_code, _, _ = execute_remote(ssh,
                                     "cmake --build build -j$(nproc)",
                                     cwd=REMOTE_BASE)
    if exit_code != 0:
        print("✗ Build failed", file=sys.stderr)
        return False

    print("✓ Build successful\n")
    return True


def run_tests(ssh):
    """Run test harness on dev machine."""
    print("\n4. Running tests...")

    # Setup test environment
    execute_remote(ssh, "chmod +x tests/setup.sh", cwd=REMOTE_BASE)
    execute_remote(ssh, "./tests/setup.sh", cwd=REMOTE_BASE)

    # Run smoke tests
    exit_code, output, error = execute_remote(ssh,
                                               "python3 tests/run_tests.py --group smoke -v",
                                               cwd=REMOTE_BASE)

    if exit_code == 0:
        print("✓ All tests passed\n")
        return True
    else:
        print("✗ Some tests failed\n", file=sys.stderr)
        return False


def check_wyoming_piper(ssh):
    """Check if Wyoming-Piper is running and optionally start it."""
    print("\n5. Checking Wyoming-Piper status...")

    # Check if running
    exit_code, output, _ = execute_remote(ssh, "ps aux | grep -i wyoming-piper | grep -v grep")

    if output.strip():
        print("✓ Wyoming-Piper is already running:")
        # Extract process info
        lines = [line for line in output.strip().split('\n') if 'wyoming-piper' in line]
        for line in lines[:2]:  # Show first 2 processes
            print(f"  {line}")
        return True
    else:
        print("⚠ Wyoming-Piper not detected.")

        # Check if wyoming-piper is installed
        exit_code, output, _ = execute_remote(ssh, "which wyoming-piper")

        if exit_code == 0:
            print("  Wyoming-Piper is installed but not running.")
            print("  Note: Tests will attempt to auto-start Wyoming-Piper")
            print("  Or start manually with:")
            print("    wyoming-piper --voice en_US-lessac-medium --port 10200 &")
        else:
            print("  Wyoming-Piper not installed.")
            print("  Install with: pip install wyoming-piper")
            print("  Or configure custom TTS in tests/test_cases.yaml")

        return False


def main():
    """Main deployment workflow."""
    print("="*60)
    print("Deploying talk-llama-fast to Development Machine")
    print("="*60)

    ssh = create_ssh_client()

    try:
        # Sync files
        if not sync_files(ssh):
            print("\n" + "="*60)
            print("✗ Project not found on dev machine!")
            print("="*60)
            print("\nPlease set up the project on the dev machine first:")
            print(f"  ssh {USER}@{HOST}")
            print(f"  git clone https://github.com/your-repo/talk-llama-fast.git {REMOTE_BASE}")
            print("\nOr if already exists locally, the path may be different.")
            print(f"Current configured path: {REMOTE_BASE}")
            sys.exit(1)

        # Install dependencies
        if not install_dependencies(ssh):
            sys.exit(1)

        # Build
        if not build_project(ssh):
            sys.exit(1)

        # Run tests
        tests_passed = run_tests(ssh)

        # Check Wyoming-Piper
        check_wyoming_piper(ssh)

        print("\n" + "="*60)
        if tests_passed:
            print("✓ Deployment Complete - All tests passed!")
        else:
            print("⚠ Deployment Complete - Some tests failed")
        print("="*60)

        print("\nTo run on dev machine:")
        print(f"  ssh {USER}@{HOST}")
        print(f"  cd {REMOTE_BASE}")
        print("  ./build/bin/talk-llama -mw models/ggml-base.en.bin -ml models/ggml-llama-7B.bin")

    except KeyboardInterrupt:
        print("\n\n✗ Deployment interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Deployment failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        ssh.close()


if __name__ == '__main__':
    main()
