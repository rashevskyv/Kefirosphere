#!/usr/bin/env python3
"""
Wrapper script to run changelog_manager.py --update-changelog
Adds new version blocks from current changelog to changelog_full.
"""

import sys
import subprocess
from pathlib import Path

def main():
    script_dir = Path(__file__).resolve().parent
    manager_script = script_dir / "changelog_manager.py"

    result = subprocess.run(
        [sys.executable, str(manager_script), "--update-changelog"],
        cwd=script_dir.parent
    )

    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
