#!/usr/bin/env python3
"""
Wrapper script to run changelog_manager.py --collect-changelogs
Fetches all changelogs from GitHub releases (v790 to latest) and saves to changelog_full.
"""

import sys
import subprocess
from pathlib import Path

def main():
    script_dir = Path(__file__).resolve().parent
    manager_script = script_dir / "changelog_manager.py"

    result = subprocess.run(
        [sys.executable, str(manager_script), "--collect-changelogs"],
        cwd=script_dir.parent
    )

    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
