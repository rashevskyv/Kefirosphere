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
import subprocess
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
            val = line.strip().split("=", 1)[1].strip()
            # Normalize path if it looks like WSL /mnt/d/...
            if key.endswith("_DIR") or key.endswith("_PATH"):
                if sys.platform == "win32" and val.startswith("/mnt/"):
                    parts = val.split("/")
                    if len(parts) >= 3:
                        drive = parts[2].upper()
                        val = drive + ":" + "\\" + "\\".join(parts[3:])
                val = os.path.normpath(val)
            return val
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

_UA = {"User-Agent": "Kefirosphere-build/1.0"}


def _github_headers():
    """Build GitHub API request headers, including auth token if available."""
    hdrs = dict(_UA)
    token = get_env_var("GITHUB_TOKEN")
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    return hdrs


def fetch_with_retry(url, *, headers=None, retries=3, timeout=15, is_json=False):
    """Fetch URL contents with automatic retries on network/transient errors.
    
    Rate-limit (HTTP 403/429) errors are NOT retried — caller must handle them.
    """
    hdrs = {**_UA, **(headers or {})}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp) if is_json else resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                # Rate limit — no point retrying immediately
                retry_after = exc.headers.get("Retry-After") or exc.headers.get("X-RateLimit-Reset")
                raise urllib.error.HTTPError(
                    exc.url, exc.code,
                    f"rate limit exceeded (Retry-After: {retry_after})",
                    exc.headers, exc.fp
                ) from None
            print(
                f"[ERROR] Attempt {attempt + 1}/{retries} failed ({url}): HTTP {exc.code}",
                file=sys.stderr,
            )
            if attempt < retries - 1:
                time.sleep(3)
            else:
                raise
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
        return fetch_with_retry(url, headers=_github_headers(), is_json=True)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            print(f"[{repo}] GitHub rate limit exceeded. Add GITHUB_TOKEN to .env to increase limits (5000 req/hr vs 60).", file=sys.stderr)
        else:
            print(f"[{repo}] Failed to fetch release data: HTTP {exc.code}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[{repo}] Failed to fetch release data: {exc}", file=sys.stderr)
        return None


def fetch_tag_message(repo, tag):
    """Fetch tag annotation message or commit message (fallback for empty release body)."""
    try:
        # 1. Get the tag ref to find the object URL
        ref_url = f"https://api.github.com/repos/{repo}/git/refs/tags/{tag}"
        ref_data = fetch_with_retry(ref_url, headers=_github_headers(), is_json=True)
        
        if not ref_data or "object" not in ref_data:
            return None

        obj_type = ref_data["object"]["type"]
        obj_url = ref_data["object"]["url"]

        # 2. Fetch the object (either a 'tag' or a 'commit')
        obj_data = fetch_with_retry(obj_url, headers=_github_headers(), is_json=True)
        if obj_data and obj_data.get("message"):
            return obj_data["message"].strip()
            
    except Exception:
        pass
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


def summarize_with_openai(text, tool_id="?"):
    api_key = get_env_var("OPENAI_API_KEY")
    if not api_key:
        print(f"[{tool_id}] WARNING: OPENAI_API_KEY not found in .env. Skipping summary.")
        return "Нова версія інструменту."

    if not text or not text.strip():
        print(f"[{tool_id}] Release body and name are both empty, using fallback summary.")
        return "Оновлено до нової версії."

    clipped = text[:4000]
    print(f"[{tool_id}] --- GitHub release body (first 500 chars sent to AI) ---")
    print(clipped[:500].strip())
    print(f"[{tool_id}] --- end ({len(clipped)} chars total) ---")

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    prompt = (
        "You are a changelog summarizer for a Nintendo Switch custom firmware project.\n"
        "Summarize the following GitHub release notes into exactly ONE short sentence in Ukrainian:\n"
        "Rules:\n"
        "- Be specific: mention actual features, fixes, or platform support from the text.\n"
        "- Do NOT write vague phrases like 'bug fixes and improvements' or 'new version' unless that is truly all the changelog says.\n"
        "- Do NOT include the tool name or version number in the summary.\n"
        "- Output ONLY the Ukrainian sentence, nothing else.\n\n"
        f"Release notes:\n{clipped}"
    )
    data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(data, ensure_ascii=False).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body = json.loads(resp.read().decode('utf-8'))
            reply = resp_body['choices'][0]['message']['content'].strip()
            if reply.startswith('UKR:'): reply = reply[4:].strip()
            
            safe_reply = reply.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
            sys.stdout.buffer.write(f"[{tool_id}] AI response: {safe_reply}\n".encode('utf-8'))
            sys.stdout.flush()
            return reply
    except Exception as e:
        print(f"[{tool_id}] ERROR: OpenAI API request failed: {e}", file=sys.stderr)
        return "Оновлено до нової версії."


def translate_block_with_openai(ukr_block_text):
    api_key = get_env_var("OPENAI_API_KEY")
    if not api_key or not ukr_block_text.strip():
        return ""
    
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    prompt = (
        "Translate the following changelog block into English.\n"
        "Rules:\n"
        "- Output ONLY the translated text.\n"
        "- Preserve all markdown formatting, including asterisks, list markers, and brackets.\n"
        "- Do NOT translate tool names (e.g., 'Atmosphere', 'Mission Control').\n"
        "- Translate 'Оновлено' to 'Updated', 'Додано' to 'Added'.\n\n"
        f"Block:\n{ukr_block_text}"
    )
    data = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
    try:
        req = urllib.request.Request(url, data=json.dumps(data, ensure_ascii=False).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp_body = json.loads(resp.read().decode('utf-8'))
            return resp_body['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"[ERROR] AI block translation failed: {e}", file=sys.stderr)
        return ""


def update_changelog_file(changelog_path, tool_id, tool_name, tool_version, release_url, summary_ukr, eng_sum_unused, kefir_ver, hos_version=None):
    if not os.path.exists(changelog_path):
        print(f"[{tool_id}] WARNING: Changelog not found at {changelog_path}", file=sys.stderr)
        return
        
    with open(changelog_path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_entry_ukr = f"* [**Оновлено**] [{tool_name} {tool_version}]({release_url}) — {summary_ukr}"

    parts = content.split('#### **ENG**')
    if len(parts) != 2:
        print(f"[{tool_id}] WARNING: Could not find ENG section in changelog.", file=sys.stderr)
        return
        
    ukr_part, eng_part = parts[0], '#### **ENG**' + parts[1]
    
    def extract_and_update_block(part_text, ver, entry, t_name):
        ver_marker = f"**{ver}**"
        pattern = re.compile(re.escape(ver_marker) + r'(.*?)(?=\*\*[\d]+\*\*|\Z)', re.DOTALL)
        match = pattern.search(part_text)
        
        if match:
            block = match.group(1)
            lines = block.split('\n')
            new_lines = []
            for line in lines:
                if line.strip().startswith('*') and f"[{t_name} " in line:
                    continue
                new_lines.append(line)
            
            first_idx = -1
            for i, l in enumerate(new_lines):
                if l.strip().startswith('*'):
                    first_idx = i
                    break
            
            if first_idx != -1:
                new_lines.insert(first_idx, entry)
            else:
                new_lines.append(entry)
                
            new_block = "\n".join(new_lines)
            
            updated_part = part_text[:match.start()] + ver_marker + new_block + part_text[match.end():]
            return updated_part, new_block.strip()
        else:
            match = re.search(r'\*\*\d+\*\*', part_text)
            new_block = f"\n{entry}\n\n"
            if match:
                idx = match.start()
                updated_part = part_text[:idx] + f"{ver_marker}{new_block}" + part_text[idx:]
            else:
                updated_part = part_text + f"\n{ver_marker}{new_block}"
            return updated_part, entry
            
    new_ukr_part, ukr_block_clean = extract_and_update_block(ukr_part, kefir_ver, new_entry_ukr, tool_name)
    
    ver_marker = f"**{kefir_ver}**"
    pattern = re.compile(re.escape(ver_marker) + r'(.*?)(?=\*\*[\d]+\*\*|\Z)', re.DOTALL)
    match_eng = pattern.search(eng_part)
    
    eng_block_clean = ""
    if match_eng:
        eng_block_clean = match_eng.group(1).strip()
        
    ukr_tool_count = len([l for l in ukr_block_clean.split('\n') if l.strip().startswith('*')])
    eng_tool_count = len([l for l in eng_block_clean.split('\n') if l.strip().startswith('*')])
    
    new_eng_part = eng_part
    
    if ukr_tool_count == eng_tool_count and eng_tool_count > 0:
        print(f"[{tool_id}] Tool counts match ({ukr_tool_count}) in UKR and ENG for v{kefir_ver}. Skipping translation.")
    else:
        print(f"[{tool_id}] Tool counts differ (UKR: {ukr_tool_count}, ENG: {eng_tool_count}) or missing. Translating UKR block to ENG...")
        translated_block = translate_block_with_openai(ukr_block_clean)
        
        if match_eng:
            new_eng_part = eng_part[:match_eng.start()] + ver_marker + "\n" + translated_block + "\n\n" + eng_part[match_eng.end():]
        else:
            match = re.search(r'\*\*\d+\*\*', eng_part)
            if match:
                idx = match.start()
                new_eng_part = eng_part[:idx] + f"{ver_marker}\n{translated_block}\n\n" + eng_part[idx:]
            else:
                new_eng_part = eng_part + f"\n{ver_marker}\n{translated_block}\n"
    
    full_content = new_ukr_part + new_eng_part
    
    with open(changelog_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
        
    sync_hos_in_changelog(changelog_path, hos_version)
    
    print(f"[{tool_id}] Updated changelog for Kefir version {kefir_ver}.")

def sync_hos_in_changelog(changelog_path, hos_version):
    if not hos_version or not os.path.exists(changelog_path):
        return
        
    with open(changelog_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Match both old all-caps UKR and proper-case ENG variants
    ukr_pattern = r'\*\*[Пп][Оо][Вв][Нн][Аа] [Пп][Іі][Дд][Тт][Рр][Ии][Мм][Кк][Аа] [\d.]+\*\*'
    eng_pattern = r'\*\*Full support for [\d.]+\*\*'
    
    new_content = re.sub(ukr_pattern,
                         lambda m: f"**Повна підтримка {hos_version}**",
                         content)
    new_content = re.sub(eng_pattern,
                         lambda m: f"**Full support for {hos_version}**",
                         new_content, flags=re.IGNORECASE)
    
    if new_content != content:
        with open(changelog_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"[HOS] Synced HOS version to {hos_version} in changelog.")

# =====================================================================
# Changelog integrity check
# =====================================================================


def _extract_tool_names_from_block(block_text):
    """Return a sorted list of tool names found in bullet lines of a changelog block."""
    names = []
    for line in block_text.split('\n'):
        line = line.strip()
        if not line.startswith('*'):
            continue
        # Match [Tool Name version](url) pattern
        m = re.search(r'\[([^\]]+)\]\(', line)
        if m:
            # Strip the version part: keep only the tool name (first word(s) before last token)
            label = m.group(1)  # e.g. "Hekate v6.5.2" or "Mission Control v0.15.1"
            # Drop the last whitespace-separated token if it looks like a version
            parts = label.rsplit(' ', 1)
            if len(parts) == 2 and re.match(r'^[vV]?[\d]', parts[1]):
                names.append(parts[0].strip().lower())
            else:
                names.append(label.strip().lower())
    return sorted(names)


def check_and_force_sync_eng_block(changelog_path, kefir_ver):
    """Compare UKR and ENG changelog blocks for kefir_ver.
    
    If tool count or tool names differ, force-translate the UKR block to ENG.
    """
    if not os.path.exists(changelog_path):
        return

    with open(changelog_path, 'r', encoding='utf-8') as f:
        content = f.read()

    parts = content.split('#### **ENG**')
    if len(parts) != 2:
        return

    ukr_part, eng_raw = parts[0], '#### **ENG**' + parts[1]
    ver_marker = f"**{kefir_ver}**"
    pattern = re.compile(re.escape(ver_marker) + r'(.*?)(?=\*\*[\d]+\*\*|\Z)', re.DOTALL)

    ukr_match = pattern.search(ukr_part)
    eng_match = pattern.search(eng_raw)

    ukr_block = ukr_match.group(1).strip() if ukr_match else ""
    eng_block = eng_match.group(1).strip() if eng_match else ""

    ukr_count = len([l for l in ukr_block.split('\n') if l.strip().startswith('*')])
    eng_count = len([l for l in eng_block.split('\n') if l.strip().startswith('*')])

    ukr_names = _extract_tool_names_from_block(ukr_block)
    eng_names = _extract_tool_names_from_block(eng_block)

    if ukr_count == eng_count and ukr_names == eng_names:
        print(f"[CHANGELOG] ENG block for v{kefir_ver} is in sync ({ukr_count} entries). OK.")
        return

    print(
        f"[CHANGELOG] ENG block for v{kefir_ver} is OUT OF SYNC "
        f"(UKR: {ukr_count} entries {ukr_names}, ENG: {eng_count} entries {eng_names}). "
        f"Forcing translation..."
    )

    if not ukr_block:
        print("[CHANGELOG] UKR block is empty, nothing to translate.")
        return

    translated = translate_block_with_openai(ukr_block)
    if not translated:
        print("[CHANGELOG] Translation returned empty result, skipping update.", file=sys.stderr)
        return

    if eng_match:
        new_eng = eng_raw[:eng_match.start()] + ver_marker + "\n" + translated + "\n\n" + eng_raw[eng_match.end():]
    else:
        first_ver = re.search(r'\*\*\d+\*\*', eng_raw)
        if first_ver:
            new_eng = eng_raw[:first_ver.start()] + f"{ver_marker}\n{translated}\n\n" + eng_raw[first_ver.start():]
        else:
            new_eng = eng_raw + f"\n{ver_marker}\n{translated}\n"

    with open(changelog_path, 'w', encoding='utf-8') as f:
        f.write(ukr_part + new_eng)

    print(f"[CHANGELOG] ENG block for v{kefir_ver} updated successfully.")


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
                    is_excluded = False
                    if "exclude" in rule:
                        exclude_patterns = rule["exclude"]
                        if isinstance(exclude_patterns, str):
                            exclude_patterns = [exclude_patterns]
                        for ep in exclude_patterns:
                            if fnmatch.fnmatch(member, ep) or fnmatch.fnmatch(os.path.basename(member), ep):
                                is_excluded = True
                                break
                    
                    if is_excluded:
                        break

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
# Mission Control Custom Build
# =====================================================================

def build_mission_control_custom(tool_id, tag, env_vars):
    """Clone, patch, build, and distribute MissionControl."""
    build_dir = get_env_var("MISSION_CONTROL_BUILD_DIR")
    patch_path = get_env_var("MISSION_CONTROL_PATCH_PATH")
    kefir_root = get_env_var("KEFIR_ROOT_DIR")
    
    if not all([build_dir, patch_path, kefir_root]):
        print(f"[{tool_id}] ERROR: Missing MC build config in .env (BUILD_DIR, PATCH_PATH, or KEFIR_ROOT_DIR)", file=sys.stderr)
        return False

    repo_url = "https://github.com/ndeadly/MissionControl.git"
    
    # We need to run these in WSL
    # Convert windows paths to wsl paths for the commands
    try:
        def to_wsl(win_path):
             # Simple conversion for C: or D: drives
             p = win_path.replace('\\', '/')
             if len(p) > 1 and p[1] == ':':
                 drive = p[0].lower()
                 return f"/mnt/{drive}/{p[3:]}"
             return p

        # If they are already /mnt/ paths from .env, use them as is
        wsl_build_dir = build_dir if build_dir.startswith('/') else to_wsl(build_dir)
        wsl_patch_path = patch_path if patch_path.startswith('/') else to_wsl(patch_path)
        wsl_kefir_root = kefir_root if kefir_root.startswith('/') else to_wsl(kefir_root)

        print(f"[{tool_id}] Preparing custom build in {wsl_build_dir}...")
        
        # Build a single bash command string to ensure context persistence (cd etc)
        # 1. Clean old build
        # 2. Clone specific tag with submodules
        # 3. Apply patch
        # 4. Build
        # 5. Distribute
        bash_cmds = [
            f"rm -rf \"{wsl_build_dir}\"",
            f"echo \"[{tool_id}] Cloning repository...\"",
            f"git clone --depth 1 --recurse-submodules --shallow-submodules -b \"{tag}\" \"{repo_url}\" \"{wsl_build_dir}\" > /dev/null 2>&1",
            f"cd \"{wsl_build_dir}\"",
            f"echo \"[{tool_id}] Applying patch: {os.path.basename(wsl_patch_path)}\"",
            f"git apply --verbose --ignore-whitespace \"{wsl_patch_path}\"",
            f"echo \"[{tool_id}] Files modified by patch:\"",
            f"git status --porcelain",
            f"echo \"[{tool_id}] Starting build (using all cores)...\"",
            f"make dist -j$(nproc)",
            f"echo \"[{tool_id}] Distributing files...\"",
            f"rsync -av \"dist/atmosphere/\" \"{wsl_kefir_root}/atmosphere/\" > /dev/null",
            f"rsync -av \"dist/config/\" \"{wsl_kefir_root}/config/\" > /dev/null"
        ]
        
        full_bash = " && ".join(bash_cmds)
        
        if os.name == 'nt':
            cmd = ["wsl", "bash", "-c", full_bash]
            print(f"[{tool_id}] Executing build pipeline via WSL...")
        else:
            cmd = ["bash", "-c", full_bash]
            print(f"[{tool_id}] Executing build pipeline (Direct Bash)...")
        
        subprocess.run(cmd, check=True)
        print(f"[{tool_id}] Custom build and distribution successful.")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"[{tool_id}] ERROR: Build pipeline failed.", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[{tool_id}] ERROR: Unexpected error during build: {e}", file=sys.stderr)
        return False

# =====================================================================
# Tool processing
# =====================================================================

_ACTIONS = {
    "extract_zip": lambda asset, rule, env: process_extract_zip(asset, rule["extract"], env),
    "download_file": lambda asset, rule, env: process_download_file(asset, rule["dest"], env),
}


def process_tool(tool_config, env_vars, hos_version=None):
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
        if tool_id == "MISSIONCONTROL":
            ok = build_mission_control_custom(tool_id, tag, env_vars)
        else:
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
            release_name = data.get("name", "") or ""
            body = data.get("body", "") or ""
            
            # If body is empty, try to fetch the tag message (like in sys-patch)
            if not body.strip():
                tag_msg = fetch_tag_message(repo, tag)
                if tag_msg:
                    body = tag_msg

            # Combine name + body so release title is included
            release_text = f"{release_name}\n\n{body}".strip()
            release_url = data.get("html_url", f"https://github.com/{repo}/releases/tag/{tag}")
            print(f"[{tool_id}] Generating summary via OpenAI...")
            ukr_sum = summarize_with_openai(release_text, tool_id)
            changelog_path = os.path.join(env_vars["kefir_root_dir"], "changelog")
            
            tool_name_map = {"HEKATE": "Hekate"}
            display_name = tool_name_map.get(tool_id, tool_id.replace("_", " ").title())
            update_changelog_file(
                changelog_path, tool_id, display_name, tag, release_url,
                ukr_sum, None, kefir_ver, hos_version
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

    # -- HOS checks --
    atmosphere_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Atmosphere")
    current_hos = get_current_hos_version(atmosphere_dir)

    env_vars = {
        "kefir_root_dir": kefir_root_dir,
        "kef_8gb_dir": kef_8gb_dir,
        # hos_version for changelog headers taken ONLY from .env (manual control)
        "hos_version": get_env_var("HOS_VERSION"),
    }
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

    hos_version = env_vars.get("hos_version")
    changelog_path = os.path.join(kefir_root_dir, "changelog")
    sync_hos_in_changelog(changelog_path, hos_version)

    # Check ENG/UKR sync before processing tools
    kefir_ver = get_kefir_version(kefir_root_dir)
    if kefir_ver and kefir_ver != "UNKNOWN":
        check_and_force_sync_eng_block(changelog_path, kefir_ver)

    tools_config = load_tools_config()
    for tool in tools_config:
        ok, downloaded = process_tool(tool, env_vars, hos_version)
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
