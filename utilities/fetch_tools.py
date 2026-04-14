#!/usr/bin/env python3
"""Modular download script for Kefirosphere tools."""

import sys
import os
import io
import zipfile
import urllib.request
import urllib.error
import json
import time
import socket
import fnmatch
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
                    # matching files dynamically to destination
                    {"member": "bootloader/*", "dest": "{kefir_root_dir}/{member}"},
                    {"member": "hekate_*.bin", "dest": "{kefir_root_dir}/payload.bin"}
                ]
            },
            {
                "match": "*ram8GB.bin",
                "action": "download_file",
                "dest": "{kefir_root_dir}/config/8gb/payload.bin"
            }
        ]
    }
]

# =====================================================================

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

def get_env_var(key):
    if not os.path.exists(ENV_PATH):
        return None
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith(key + "="):
                return line.strip().split("=", 1)[1].strip()
    return None

def update_env_var(key, value):
    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    for i, line in enumerate(lines):
        if line.strip().startswith(key + "="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
            
    if not found:
        lines.append(f"{key}={value}\n")
        
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

def ask_user(prompt_text):
    try:
        with open("/dev/tty", "w") as tty_out, open("/dev/tty", "r") as tty_in:
            tty_out.write(f"\n{prompt_text} (y/n): ")
            tty_out.flush()
            ans = tty_in.readline().strip().lower()
            return ans in ["y", "yes"]
    except Exception:
        pass
    try:
        print(f"\n{prompt_text} (y/n): ", end="")
        sys.stdout.flush()
        ans = input().strip().lower()
        return ans in ["y", "yes"]
    except EOFError:
        return False

def fetch_with_retry(url, headers=None, retries=3, timeout=10, is_json=False):
    if headers is None:
        headers = {}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if is_json:
                    return json.load(r)
                else:
                    return r.read()
        except (urllib.error.URLError, socket.timeout) as e:
            print(f"[Помилка] Спроба {attempt+1}/{retries} не вдалася ({url}): {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(3)
            else:
                raise e

def fetch_release_data(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    print(f"[{repo}] Завантаження інформації про реліз...")
    try:
        data = fetch_with_retry(url, headers={"User-Agent": "Mozilla/5.0"}, is_json=True)
        return data
    except Exception as e:
        print(f"[{repo}] Помилка отримання даних про реліз: {e}", file=sys.stderr)
        return None

def process_extract_zip(asset_data, rules_extract, env_vars):
    try:
        zip_data = fetch_with_retry(asset_data["browser_download_url"])
    except Exception as e:
        print(f"Помилка завантаження ZIP: {e}", file=sys.stderr)
        return False

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        members = zf.namelist()
        for member in members:
            # Перевіряємо правила для розпакування
            for ex_rule in rules_extract:
                if fnmatch.fnmatch(member, ex_rule["member"]):
                    if member.endswith("/"):
                        continue
                        
                    # Формуємо шлях з підстановкою змінних (kefir_root_dir, member)
                    dest = ex_rule["dest"].format(member=member, **env_vars)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                    
                    break
    return True

def process_download_file(asset_data, dest_template, env_vars):
    dest = dest_template.format(**env_vars)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        data = fetch_with_retry(asset_data["browser_download_url"])
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"Помилка завантаження файлу: {e}", file=sys.stderr)
        return False

def process_tool(tool_config, env_vars):
    tool_id = tool_config["id"]
    repo = tool_config["repo"]
    rules = tool_config.get("rules", [])
    
    while True:
        data = fetch_release_data(repo)
        if not data:
            if ask_user(f"[{tool_id}] Помилка завантаження інформації про реліз. Спробувати ще раз? (Якщо 'n' - пропускаємо)"):
                continue
            return False
            
        assets = data.get("assets", [])
        tag = data.get("tag_name", "unknown")
        
        ver_key = f"{tool_id}_LATEST_VERSION"
        date_key = f"{tool_id}_LATEST_DATE"
        
        current_ver = get_env_var(ver_key)
        if current_ver and current_ver == tag:
            print(f"[{tool_id}] Версія ({tag}) збігається зі збереженою в .env. Пропускаємо.")
            return True

        if current_ver:
            print(f"[{tool_id}] Знайдено нову версію: {current_ver} -> {tag}")
        else:
            print(f"[{tool_id}] Починаємо завантаження версії: {tag}")
            
        success_all = True
        
        for asset in assets:
            name = asset["name"]
            matched_rule = None
            for rule in rules:
                if fnmatch.fnmatch(name, rule["match"]):
                    if "exclude" in rule and fnmatch.fnmatch(name, rule["exclude"]):
                        continue
                    matched_rule = rule
                    break
            
            if not matched_rule:
                continue
                
            print(f"[{tool_id}] Обробка {name}...")
            
            action = matched_rule["action"]
            if action == "extract_zip":
                ok = process_extract_zip(asset, matched_rule["extract"], env_vars)
                if not ok: success_all = False
            elif action == "download_file":
                ok = process_download_file(asset, matched_rule["dest"], env_vars)
                if not ok: success_all = False
                
        if not success_all:
            if ask_user(f"[{tool_id}] Під час завантаження сталася помилка. Спробувати ще раз? (Якщо 'n' - лишаємо як є)"):
                continue
            return False
            
        # Успіх
        update_env_var(ver_key, tag)
        update_env_var(date_key, datetime.now().strftime('"%Y-%m-%d %H:%M:%S"'))
        print(f"[{tool_id}] Версію {tag} збережено у .env")
        return True

def main():
    if len(sys.argv) < 2:
        print(f"Використання: {sys.argv[0]} <kefir_root_dir>", file=sys.stderr)
        sys.exit(1)

    kefir_root_dir = sys.argv[1]
    
    # Змінні для підстановки у конфіг-правила (str.format)
    env_vars = {
        "kefir_root_dir": kefir_root_dir
    }

    for tool in TOOLS_CONFIG:
        process_tool(tool, env_vars)
        
    print("Всі утиліти успішно перевірені та завантажені.")

if __name__ == "__main__":
    main()
