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
import re
import urllib.request
import urllib.error
from datetime import datetime

# Load state manager
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from state_manager import state

# =====================================================================
# Configuration
# =====================================================================

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tools_config.json"
)

def load_tools_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"[ERROR] tools_config.json not found at {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

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


def get_kefir_version(kefir_root_dir):
    ver_path = os.path.join(kefir_root_dir, "version")
    if os.path.exists(ver_path):
        with open(ver_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "UNKNOWN"


def get_current_hos_version(atmosphere_dir):
    header_path = os.path.join(atmosphere_dir, "libraries", "libvapours", "include", "vapours", "ams", "ams_api_version.h")
    if not os.path.exists(header_path):
        return None
    with open(header_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    match_maj = re.search(r'#define\s+ATMOSPHERE_SUPPORTED_HOS_VERSION_MAJOR\s+(\d+)', content)
    match_min = re.search(r'#define\s+ATMOSPHERE_SUPPORTED_HOS_VERSION_MINOR\s+(\d+)', content)
    match_mic = re.search(r'#define\s+ATMOSPHERE_SUPPORTED_HOS_VERSION_MICRO\s+(\d+)', content)
    
    if match_maj and match_min and match_mic:
        return f"{match_maj.group(1)}.{match_min.group(1)}.{match_mic.group(1)}"
    return None


def get_current_atmosphere_version(atmosphere_dir):
    header_path = os.path.join(atmosphere_dir, "libraries", "libvapours", "include", "vapours", "ams", "ams_api_version.h")
    if not os.path.exists(header_path):
        return None
    with open(header_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    match_maj = re.search(r'#define\s+ATMOSPHERE_RELEASE_VERSION_MAJOR\s+(\d+)', content)
    match_min = re.search(r'#define\s+ATMOSPHERE_RELEASE_VERSION_MINOR\s+(\d+)', content)
    match_mic = re.search(r'#define\s+ATMOSPHERE_RELEASE_VERSION_MICRO\s+(\d+)', content)
    
    if match_maj and match_min and match_mic:
        return f"{match_maj.group(1)}.{match_min.group(1)}.{match_mic.group(1)}"
    return None


def toggle_missioncontrol(enable, kefir_root_dir):
    install_bat = os.path.join(kefir_root_dir, "kefir", "install.bat")
    update_te = os.path.join(kefir_root_dir, "kefir", "switch", "kefir-updater", "update.te")
    
    if os.path.exists(install_bat):
        with open(install_bat, 'r', encoding='utf-8') as f:
            bat_data = f.read()
        if enable:
            bat_data = re.sub(r'^[ \t]*set missioncontrol=0', r'@REM set missioncontrol=0', bat_data, flags=re.MULTILINE|re.IGNORECASE)
        else:
            bat_data = re.sub(r'^[ \t]*@REM[ \t]*set missioncontrol=0', r'set missioncontrol=0', bat_data, flags=re.MULTILINE|re.IGNORECASE)
        with open(install_bat, 'w', encoding='utf-8') as f:
            f.write(bat_data)
            
    if os.path.exists(update_te):
        with open(update_te, 'r', encoding='utf-8') as f:
            te_data = f.read()
        if enable:
            te_data = re.sub(r'^[ \t]*missioncontrol=0', r'# missioncontrol=0', te_data, flags=re.MULTILINE)
        else:
            te_data = re.sub(r'^[ \t]*#[ \t]*missioncontrol=0', r'missioncontrol=0', te_data, flags=re.MULTILINE)
        with open(update_te, 'w', encoding='utf-8') as f:
            f.write(te_data)


def summarize_with_openai(text):
    api_key = get_env_var("OPENAI_API_KEY")
    if not api_key:
        print("[WARNING] OPENAI_API_KEY not found in .env. Skipping summary.")
        return "Нова версія інструменту.", "New tool version."

    text = text[:2000] if text else "Bugfixes and improvements."
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    prompt = (
        "Translate and summarize the following release changelog into exactly two versions: "
        "one in Ukrainian and one in English. Each version MUST be a single, short sentence describing the most important change. "
        "Do not include the tool name or version in the summary, just the changes. "
        "Format the output exactly like this:\n"
        "UKR: <ukrainian summary>\n"
        "ENG: <english summary>\n\n"
        f"Changelog:\n{text}"
    )
    data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body = json.loads(resp.read().decode('utf-8'))
            reply = resp_body['choices'][0]['message']['content'].strip()
            ukr, eng = "Оновлено інструмент.", "Tool updated."
            for line in reply.split('\n'):
                line = line.strip()
                if line.startswith('UKR:'): ukr = line[4:].strip()
                elif line.startswith('ENG:'): eng = line[4:].strip()
            return ukr, eng
    except Exception as e:
        print(f"[ERROR] OpenAI API request failed: {e}", file=sys.stderr)
        return "Нова версія інструменту.", "New tool version."


def update_changelog_file(changelog_path, tool_id, tool_name, tool_version, release_url, summary_ukr, summary_eng, kefir_ver):
    if not os.path.exists(changelog_path):
        print(f"[{tool_id}] WARNING: Changelog not found at {changelog_path}", file=sys.stderr)
        return
        
    with open(changelog_path, 'r', encoding='utf-8') as f:
        content = f.read()

    entry_ukr = f"* [**Оновлено**] [{tool_name} {tool_version}]({release_url}) — {summary_ukr}"
    entry_eng = f"* [**Updated**] [{tool_name} {tool_version}]({release_url}) — {summary_eng}"

    parts = content.split('#### **ENG**')
    if len(parts) != 2:
        print(f"[{tool_id}] WARNING: Could not find ENG section in changelog.", file=sys.stderr)
        return
        
    ukr_part, eng_part = parts[0], '#### **ENG**' + parts[1]
    
    def inject(text, ver, entry):
        if entry in text:
            return text
        ver_marker = f"**{ver}**"
        if ver_marker in text:
            pattern = re.compile(re.escape(ver_marker) + r'\s*\n')
            match = pattern.search(text)
            if match:
                return text[:match.end()] + entry + "\n" + text[match.end():]
            return text.replace(ver_marker, ver_marker + "\n" + entry)
        match = re.search(r'\*\*\d+\*\*', text)
        if match:
            idx = match.start()
            return text[:idx] + f"{ver_marker}\n{entry}\n\n" + text[idx:]
        return text + f"\n{ver_marker}\n{entry}\n"
            
    new_ukr = inject(ukr_part, kefir_ver, entry_ukr)
    new_eng = inject(eng_part, kefir_ver, entry_eng)
    
    with open(changelog_path, 'w', encoding='utf-8') as f:
        f.write(new_ukr + new_eng)
    print(f"[{tool_id}] Updated changelog for Kefir version {kefir_ver}.")

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
            return False, False

        tag = data.get("tag_name", "unknown")

        # Check cached version in state manager
        ver_key = f"{tool_id}_LATEST_VERSION"
        date_key = f"{tool_id}_LATEST_DATE"
        cached_ver = state.get(ver_key)

        if cached_ver == tag:
            print(f"[{tool_id}] Version ({tag}) matches cache. Skipping.")
            return True, False

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
            return False, False

        # Run post-download hook if configured
        hook_name = tool_config.get("post")
        if hook_name and hook_name in _POST_HOOKS:
            _POST_HOOKS[hook_name](env_vars)

        # Update changelog
        kefir_ver = get_kefir_version(env_vars["kefir_root_dir"])
        if kefir_ver and kefir_ver != "UNKNOWN":
            body = data.get("body", "")
            release_url = data.get("html_url", f"https://github.com/{repo}/releases/tag/{tag}")
            print(f"[{tool_id}] Generating summary via OpenAI...")
            ukr_sum, eng_sum = summarize_with_openai(body)
            changelog_path = os.path.join(env_vars["kefir_root_dir"], "changelog")
            
            tool_name_map = {"HEKATE": "Hekate"}
            display_name = tool_name_map.get(tool_id, tool_id.replace("_", " ").title())
            update_changelog_file(
                changelog_path, tool_id, display_name, tag, release_url,
                ukr_sum, eng_sum, kefir_ver
            )

        # Save version to state manager
        state.set(ver_key, tag)
        state.set(date_key, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        print(f"[{tool_id}] Version {tag} saved to state")
        return True, True


# =====================================================================
# Entry point
# =====================================================================


def main():
    kefir_root_dir = get_env_var("KEFIR_ROOT_DIR")
    if not kefir_root_dir:
        print("[ERROR] KEFIR_ROOT_DIR is not set in .env", file=sys.stderr)
        sys.exit(1)

    kef_8gb_dir = os.path.join(kefir_root_dir, "kefir", "config", "8gb")

    env_vars = {
        "kefir_root_dir": kefir_root_dir,
        "kef_8gb_dir": kef_8gb_dir,
    }

    # -- HOS checks --
    atmosphere_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Atmosphere")
    current_hos = get_current_hos_version(atmosphere_dir)
    cached_hos = state.get("HOS_VERSION")
    
    hos_bumped = False
    if current_hos and cached_hos:
        o_parts = cached_hos.split('.')
        c_parts = current_hos.split('.')
        if len(o_parts) >= 2 and len(c_parts) >= 2:
            if o_parts[0] != c_parts[0] or o_parts[1] != c_parts[1]:
                hos_bumped = True
    elif current_hos and not cached_hos:
        hos_bumped = True

    mc_updated = False

    tools_config = load_tools_config()
    for tool in tools_config:
        ok, downloaded = process_tool(tool, env_vars)
        if tool["id"] == "MISSIONCONTROL" and downloaded:
            mc_updated = True

    # -- MissionControl Toggling --
    if hos_bumped and not mc_updated:
        print(f"[HOS] HOS bumped ({cached_hos} -> {current_hos}) without a MissionControl update. Disabling MissionControl.")
        toggle_missioncontrol(False, kefir_root_dir)
    elif mc_updated:
        print(f"[HOS] MissionControl updated. Enabling MissionControl.")
        toggle_missioncontrol(True, kefir_root_dir)

    if current_hos and hos_bumped:
        state.set("HOS_VERSION", current_hos)
        print(f"[HOS] HOS_VERSION {current_hos} saved to state")

    current_ams = get_current_atmosphere_version(atmosphere_dir)
    if current_ams:
        cached_ams = state.get("ATMOSPHERE_LATEST_VERSION")
        if cached_ams != current_ams:
            state.set("ATMOSPHERE_LATEST_VERSION", current_ams)
            print(f"[AMS] ATMOSPHERE_LATEST_VERSION {current_ams} saved to state")

    print("All tools checked and downloaded successfully.")


if __name__ == "__main__":
    main()
