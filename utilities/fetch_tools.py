#!/usr/bin/env python3
"""Modular download script for Kefirosphere tools.

Downloads release assets from GitHub and places them
into the correct locations within the kefir root directory.
"""

import sys
import os
import io
import json
import time
import shutil
import socket
import zipfile
import fnmatch
import urllib.request
import urllib.error
from datetime import datetime

# =====================================================================
# Configuration
# =====================================================================

TOOLS_CONFIG = [
    {
        "id": "HEKATE",
        "repo": "CTCaer/hekate",
        "rules": [
            {
                "match": "hekate_*.zip",
                "exclude": "*ram8GB*",
                "action": "extract_zip",
                "extract": [
                    {"member": "bootloader/*", "dest": "{kefir_root_dir}/{member}"},
                    {"member": "hekate_*.bin", "dest": "{kefir_root_dir}/payload.bin"},
                ],
            },
            {
                "match": "*ram8GB.bin",
                "action": "download_file",
                "dest": "{kef_8gb_dir}/payload.bin",
            },
        ],
        "post": "copy_hekate_payload",
    },
]

# =====================================================================
# .env helpers
# =====================================================================

ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)


def _read_env_lines():
    """Read .env file lines; returns empty list if file does not exist."""
    if not os.path.exists(ENV_PATH):
        return []
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        return f.readlines()


def get_env_var(key):
    for line in _read_env_lines():
        if line.strip().startswith(key + "="):
            return line.strip().split("=", 1)[1].strip()
    return None


def update_env_var(key, value):
    lines = _read_env_lines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(key + "="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


# =====================================================================
# User interaction
# =====================================================================


def ask_user(prompt_text):
    """Prompt user for y/n confirmation via stdin."""
    try:
        print(f"\n{prompt_text} (y/n): ", end="")
        sys.stdout.flush()
        return input().strip().lower() in ("y", "yes")
    except EOFError:
        return False


# =====================================================================
# Network
# =====================================================================

_UA = {"User-Agent": "Mozilla/5.0"}


def fetch_with_retry(url, *, headers=None, retries=3, timeout=15, is_json=False):
    """Fetch URL contents with automatic retries on network errors."""
    hdrs = {**_UA, **(headers or {})}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp) if is_json else resp.read()
        except (urllib.error.URLError, socket.timeout) as exc:
            print(
                f"[ERROR] Attempt {attempt + 1}/{retries} failed ({url}): {exc}",
                file=sys.stderr,
            )
            if attempt < retries - 1:
                time.sleep(3)
            else:
                raise


def fetch_release_data(repo):
    """Fetch latest release metadata from GitHub API."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    print(f"[{repo}] Fetching latest release info...")
    try:
        return fetch_with_retry(url, is_json=True)
    except Exception as exc:
        print(f"[{repo}] Failed to fetch release data: {exc}", file=sys.stderr)
        return None


# =====================================================================
# Asset processors
# =====================================================================


def process_extract_zip(asset, rules_extract, env_vars):
    """Download a ZIP asset and extract matching members."""
    try:
        zip_data = fetch_with_retry(asset["browser_download_url"])
    except Exception as exc:
        print(f"[ERROR] ZIP download failed: {exc}", file=sys.stderr)
        return False

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            for rule in rules_extract:
                if fnmatch.fnmatch(member, rule["member"]):
                    dest = rule["dest"].format(member=member, **env_vars)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                    print(f"  extracted: {member} -> {dest}")
                    break
    return True


def process_download_file(asset, dest_template, env_vars):
    """Download a single file asset to the templated destination."""
    dest = dest_template.format(**env_vars)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        data = fetch_with_retry(asset["browser_download_url"])
        with open(dest, "wb") as f:
            f.write(data)
        print(f"  downloaded: {asset['name']} -> {dest}")
        return True
    except Exception as exc:
        print(f"[ERROR] File download failed: {exc}", file=sys.stderr)
        return False


# =====================================================================
# Post-download hooks
# =====================================================================


def copy_hekate_payload(env_vars):
    """Copy ram8GB payload.bin into bootloader/ and atmosphere/ subdirs."""
    kef_8gb_dir = env_vars["kef_8gb_dir"]
    payload = os.path.join(kef_8gb_dir, "payload.bin")
    if not os.path.exists(payload):
        print(f"[HEKATE] WARNING: {payload} not found, skipping copies.", file=sys.stderr)
        return

    targets = [
        os.path.join(kef_8gb_dir, "bootloader", "update.bin"),
        os.path.join(kef_8gb_dir, "atmosphere", "reboot_payload.bin"),
    ]
    for dest in targets:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(payload, dest)
        print(f"[HEKATE] Copied payload.bin -> {dest}")


# Hook registry — maps config "post" value to callable
_POST_HOOKS = {
    "copy_hekate_payload": copy_hekate_payload,
}

# =====================================================================
# Tool processing
# =====================================================================

_ACTIONS = {
    "extract_zip": lambda asset, rule, env: process_extract_zip(asset, rule["extract"], env),
    "download_file": lambda asset, rule, env: process_download_file(asset, rule["dest"], env),
}


def process_tool(tool_config, env_vars):
    """Download and process all assets for a single tool configuration."""
    tool_id = tool_config["id"]
    repo = tool_config["repo"]
    rules = tool_config.get("rules", [])

    while True:
        data = fetch_release_data(repo)
        if not data:
            if ask_user(f"[{tool_id}] Failed to fetch release. Retry? ('n' to skip)"):
                continue
            return False

        tag = data.get("tag_name", "unknown")

        # Check cached version in .env
        ver_key = f"{tool_id}_LATEST_VERSION"
        date_key = f"{tool_id}_LATEST_DATE"
        cached_ver = get_env_var(ver_key)

        if cached_ver == tag:
            print(f"[{tool_id}] Version ({tag}) matches .env cache. Skipping.")
            return True

        if cached_ver:
            print(f"[{tool_id}] New version found: {cached_ver} -> {tag}")
        else:
            print(f"[{tool_id}] Downloading version: {tag}")

        # Match assets against rules and process
        ok = True
        for asset in data.get("assets", []):
            name = asset["name"]
            matched = None
            for rule in rules:
                if fnmatch.fnmatch(name, rule["match"]):
                    if "exclude" in rule and fnmatch.fnmatch(name, rule["exclude"]):
                        continue
                    matched = rule
                    break
            if not matched:
                continue

            print(f"[{tool_id}] Processing {name}...")
            handler = _ACTIONS.get(matched["action"])
            if handler:
                if not handler(asset, matched, env_vars):
                    ok = False
            else:
                print(f"[{tool_id}] Unknown action: {matched['action']}", file=sys.stderr)
                ok = False

        if not ok:
            if ask_user(f"[{tool_id}] Download errors occurred. Retry? ('n' to keep as-is)"):
                continue
            return False

        # Run post-download hook if configured
        hook_name = tool_config.get("post")
        if hook_name and hook_name in _POST_HOOKS:
            _POST_HOOKS[hook_name](env_vars)

        # Save version to .env
        update_env_var(ver_key, tag)
        update_env_var(date_key, datetime.now().strftime('"%Y-%m-%d %H:%M:%S"'))
        print(f"[{tool_id}] Version {tag} saved to .env")
        return True


# =====================================================================
# Entry point
# =====================================================================


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <kefir_root_dir> [kef_8gb_dir]", file=sys.stderr)
        sys.exit(1)

    kefir_root_dir = sys.argv[1]
    kef_8gb_dir = sys.argv[2] if len(sys.argv) >= 3 else os.path.join(kefir_root_dir, "config", "8gb")

    env_vars = {
        "kefir_root_dir": kefir_root_dir,
        "kef_8gb_dir": kef_8gb_dir,
    }

    for tool in TOOLS_CONFIG:
        process_tool(tool, env_vars)

    print("All tools checked and downloaded successfully.")


if __name__ == "__main__":
    main()
