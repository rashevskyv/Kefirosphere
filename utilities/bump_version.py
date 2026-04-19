#!/usr/bin/env python3
import os
import sys
import subprocess
import logging
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_FILE = SCRIPT_DIR / "bump_version.log"

# Logging setup
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
_fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
_ch = logging.StreamHandler(sys.stdout)
_fh.setFormatter(_fmt); _ch.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_fh, _ch])
log = logging.getLogger("bump-version")

def run(cmd, *, cwd=None, check=True):
    res = subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and res.returncode != 0:
        parts = []
        if res.stdout.strip(): parts.append("--- stdout ---\n" + res.stdout.strip())
        if res.stderr.strip(): parts.append("--- stderr ---\n" + res.stderr.strip())
        raise subprocess.CalledProcessError(
            res.returncode, cmd, "\n".join(parts) or "(no output)", res.stderr)
    return res

def git(*args, cwd=None, check=True):
    return run(["git"] + list(args), cwd=cwd, check=check)

def load_env():
    env_file = SCRIPT_DIR.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip("\"'"))
    
    kefir_root = os.environ.get("KEFIR_ROOT_DIR")
    if not kefir_root:
        log.error("Required env variable 'KEFIR_ROOT_DIR' is not set — check your .env")
        sys.exit(1)
    return kefir_root

def bump_version(kefir_root: str) -> int:
    """Increment version file and commit changes. Returns new version."""
    version_file = Path(kefir_root) / "version"
    try:
        current = int(version_file.read_text().strip())
    except Exception:
        current = 0
    new_ver = current + 1
    version_file.write_text(str(new_ver))
    log.info("Version bumped: %d -> %d", current, new_ver)

    # Commit kefir_root branch
    try:
        git("add", "version", cwd=kefir_root)
        git("commit", "-m", f"build: bump version to {new_ver}", cwd=kefir_root)
        log.info("Kefir root version committed: %d", new_ver)
    except subprocess.CalledProcessError as e:
        log.warning("Could not commit Kefir root directory:\n%s", e.stdout)

    # Commit Kefirosphere
    try:
        git("add", "-A", cwd=SCRIPT_DIR)
        git("commit", "-m", f"build: bump version to {new_ver}", cwd=SCRIPT_DIR)
        log.info("Kefirosphere committed: build %d", new_ver)
    except subprocess.CalledProcessError as e:
        log.warning("Could not commit Kefirosphere:\n%s", e.stdout)

    return new_ver

def main():
    log.info("=" * 60)
    log.info("Kefirosphere Maint — Bump Version")
    log.info("=" * 60)
    kefir_root = load_env()
    bump_version(kefir_root)

if __name__ == "__main__":
    main()
