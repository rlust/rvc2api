#!/usr/bin/env python3
"""
Frontend build script wrapper that allows invoking the frontend builder as a Python module.

This script is a thin wrapper around the shell-based build-frontend.sh script that
allows it to be called as a Python module or installed as an entry point via Poetry.
"""

import os
import subprocess
import sys


def main():
    """Run the frontend build script with any provided arguments."""
    # Find the root directory of the project
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # Path to the shell script
    shell_script = os.path.join(project_root, "scripts", "build-frontend.sh")

    # Make sure the script is executable
    if not os.access(shell_script, os.X_OK):
        os.chmod(shell_script, 0o755)

    # Forward any command line arguments to the shell script
    cmd = [shell_script] + sys.argv[1:]

    # Run the shell script
    try:
        result = subprocess.run(cmd, check=True)
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        print(f"Error: Frontend build script failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except FileNotFoundError:
        print(f"Error: Could not find the frontend build script at {shell_script}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
