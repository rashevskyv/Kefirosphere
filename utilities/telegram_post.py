#!/usr/bin/env python3
"""
telegram_post.py — Kefirosphere Telegram Notifier

Posts release updates to Telegram channels.
- @kf4fr: UKR + ENG changelogs.
- @kefir_ukr: UKR changelog only.

Uses Telegram Bot API (HTML mode).
Handles message splitting (Captions < 1024 chars).
"""

import os
import sys
import re
import requests
import json
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR       = Path(__file__).resolve().parent
KEFIROSPHERE_DIR = SCRIPT_DIR.parent
ENV_FILE         = KEFIROSPHERE_DIR / ".env"

# ─────────────────────────────────────────────────────────────────────────────
# .env loader
# ─────────────────────────────────────────────────────────────────────────────

def load_env():
    if not ENV_FILE.exists():
        print(f"[ERROR] .env not found at {ENV_FILE}", file=sys.stderr)
        sys.exit(1)

    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip("\"'")
        
        # Cross-platform path normalization:
        if sys.platform == "win32":
            # WSL (/mnt/d/...) -> Windows (D:\...)
            if val.startswith("/mnt/"):
                parts = val.split("/")
                if len(parts) >= 3:
                    val = parts[2].upper() + ":\\" + "\\".join(parts[3:])
        else:
            # Windows (D:\...) -> WSL (/mnt/d/...)
            if ":" in val and (val[1:3] == ":\\" or val[1:3] == ":/"):
                drive = val[0].lower()
                path = val[3:].replace("\\", "/")
                val = f"/mnt/{drive}/{path}"

        # Use simple assignment to overwrite existing environment variables
        os.environ[key] = val

    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_GLOBAL", "TELEGRAM_CHAT_UKR", "KEFIR_ROOT_DIR"]
    cfg = {}
    for k in required:
        v = os.environ.get(k)
        if not v:
            print(f"[ERROR] Missing required .env variable: {k}", file=sys.stderr)
            sys.exit(1)
        cfg[k] = v
    
    # Optional threads
    cfg["TELEGRAM_THREAD_GLOBAL"] = os.environ.get("TELEGRAM_THREAD_GLOBAL")
    cfg["TELEGRAM_THREAD_UKR"]    = os.environ.get("TELEGRAM_THREAD_UKR")
    
    cfg["KEFIR_ROOT_DIR"] = os.path.normpath(cfg["KEFIR_ROOT_DIR"])
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Changelog Parser (Localized)
# ─────────────────────────────────────────────────────────────────────────────

def get_current_kefir_version(kefir_root: str) -> str:
    ver_file = Path(kefir_root) / "version"
    if not ver_file.exists():
        print(f"[ERROR] version file not found at {ver_file}", file=sys.stderr)
        sys.exit(1)
    return ver_file.read_text(encoding="utf-8").strip()

def parse_localized_changelog(kefir_root: str, version: str):
    """
    Extracts UKR and ENG blocks for the specific version from 'changelog' file,
    including any 'Support' headers above it.
    """
    changelog_path = Path(kefir_root) / "changelog"
    if not changelog_path.exists():
        return "", ""
    
    content = changelog_path.read_text(encoding="utf-8")
    
    def extract_section(section_name: str):
        # Find section start (e.g. #### **UKR**) until next section or end
        pattern = rf"#### \*\*{section_name}\*\*(.*?)(?=#### \*\*|$)"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return ""
        
        section_content = match.group(1).strip()
        
        # We want everything from the start of the section 
        # down to the end of the current version block.
        
        # Find the version line start (handles both ver and **ver**)
        ver_pattern = rf"(^|\n)\**{version}\**"
        ver_match = re.search(ver_pattern, section_content)
        if not ver_match:
            return ""
        
        # Find where this version block ends (start of NEXT version number)
        # Next version number is \n**\d+** or \n\d+
        next_ver_pattern = r"\n\**\d+\**"
        next_ver_match = re.search(next_ver_pattern, section_content[ver_match.end():])
        
        if next_ver_match:
            end_pos = ver_match.end() + next_ver_match.start()
            needed_text = section_content[:end_pos].strip()
        else:
            needed_text = section_content.strip()
            
        return needed_text

    ukr_part = extract_section("UKR")
    eng_part = extract_section("ENG")
    
    return ukr_part, eng_part

def md_to_html(text: str) -> str:
    """Convert subset of Markdown to Telegram HTML (v2 improved)."""
    if not text:
        return ""
    
    # 1. Escape HTML special chars FIRST
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 2. Monospaced text: `text` or 'text' -> <code>text</code>
    # We use a non-greedy regex to match content inside quotes/backticks
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # For single quotes, we only target paths/filenames (usually have / or .)
    # to avoid mess with possessive apostrophes if any.
    text = re.sub(r"'([^']*/[^']+)'|'([^']+\.[^']+)'", 
                  lambda m: f"<code>{m.group(1) or m.group(2)}</code>", text)
    
    # 3. Bold: **text** -> <b>text</b>
    # Specifically handle cases like [**Word**] to become [<b>Word</b>]
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    
    # 4. Links: [text](url) -> [<a href="url">text</a>]
    # Brackets are plain text, content inside is the link.
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'[<a href="\2">\1</a>]', text)

    
    # 5. Bullets: * -> •
    text = text.replace("* ", "• ")
    
    return text.strip()




# ─────────────────────────────────────────────────────────────────────────────
# Telegram API
# ─────────────────────────────────────────────────────────────────────────────

def send_to_telegram(token: str, chat_id: str, photo_path: Path, caption: str, follow_up: str = None, thread_id: str = None):
    """
    Sends a photo with a caption. Supports Topics via thread_id.
    """
    base_url = f"https://api.telegram.org/bot{token}"
    
    # 1. Send Photo
    current_caption = caption
    next_messages = []
    
    if len(caption) > 1024:
        title_lines = caption.split("\n", 2)
        current_caption = "\n".join(title_lines[:2])
        next_messages.append(caption)
    
    payload = {
        "chat_id": chat_id,
        "caption": current_caption,
        "parse_mode": "HTML"
    }
    if thread_id:
        payload["message_thread_id"] = thread_id
    
    with open(photo_path, "rb") as f:
        res = requests.post(f"{base_url}/sendPhoto", data=payload, files={"photo": f})

    
    photo_res = res.json()
    if not photo_res.get("ok"):
        print(f"[ERROR] sendPhoto failed for {chat_id}: {photo_res.get('description')}")
        return
    
    message_id = photo_res["result"]["message_id"]
    print(f"  [OK] Photo sent to {chat_id} (ID: {message_id})")

    # 2. Send follow-up messages
    all_followups = next_messages
    if follow_up:
        all_followups.append(follow_up)
    
    for msg in all_followups:
        # Split msg if > 4090
        chunks = [msg[i:i+4090] for i in range(0, len(msg), 4090)]
        for chunk in chunks:
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "reply_to_message_id": message_id
            }
            if thread_id:
                payload["message_thread_id"] = thread_id
                
            requests.post(f"{base_url}/sendMessage", data=payload)
            print(f"  [OK] Follow-up sent to {chat_id}")

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # Force UTF-8 for console output to avoid encoding errors on Windows
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        except:
            pass
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", help="Send to test channel", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("  Kefirosphere - Telegram Release Post")
    print("=" * 60)

    cfg = load_env()
    ver = get_current_kefir_version(cfg["KEFIR_ROOT_DIR"])
    ukr_raw, eng_raw = parse_localized_changelog(cfg["KEFIR_ROOT_DIR"], ver)
    
    if not ukr_raw:
        print(f"[ERROR] Could not find changelog for version {ver}")
        sys.exit(1)

    ukr_html = md_to_html(ukr_raw)
    eng_html = md_to_html(eng_raw)
    
    photo_path = Path(cfg["KEFIR_ROOT_DIR"]) / "kefir.png"
    release_url = f"https://github.com/rashevskyv/kefir/releases/tag/{ver}"
    
    if args.test:
        test_chat = "@test123testtest123were"
        print(f"  [TEST MODE] Sending BOTH variants to {test_chat} ...")
        
        # 1. Test Global (Smart Split)
        ukr_part = f'<b><a href="{release_url}">СКАЧАТИ</a></b>\n\n{ukr_html}'
        eng_part = f'<b><a href="{release_url}">DOWNLOAD</a></b>\n\n{eng_html}'
        combined = f'<b><a href="{release_url}">СКАЧАТИ</a> | <a href="{release_url}">DOWNLOAD</a></b>\n\n{ukr_html}\n____\n{eng_html}'
        
        print("  [TEST: GLOBAL]")
        if len(combined) <= 1024:
            send_to_telegram(cfg["TELEGRAM_BOT_TOKEN"], test_chat, photo_path, combined)
        else:
            send_to_telegram(cfg["TELEGRAM_BOT_TOKEN"], test_chat, photo_path, ukr_part, follow_up=eng_part)
        
        # 2. Test UKR Only
        print("  [TEST: UKR ONLY]")
        ukr_only = f'<b><a href="{release_url}">СКАЧАТИ</a></b>\n\n{ukr_html}'
        send_to_telegram(cfg["TELEGRAM_BOT_TOKEN"], test_chat, photo_path, ukr_only)
        
        print("  [TEST MODE] Done.")
        return

    # ── Channel 1: Global (UKR + ENG with Smart Split) ───────────────────────
    ukr_part = f'<b><a href="{release_url}">СКАЧАТИ</a></b>\n\n{ukr_html}'
    eng_part = f'<b><a href="{release_url}">DOWNLOAD</a></b>\n\n{eng_html}'
    combined = f'<b><a href="{release_url}">СКАЧАТИ</a> | <a href="{release_url}">DOWNLOAD</a></b>\n\n{ukr_html}\n____\n{eng_html}'

    print(f"  Posting to Global Chat {cfg['TELEGRAM_CHAT_GLOBAL']} ...")
    if len(combined) <= 1024:
        send_to_telegram(
            token=cfg["TELEGRAM_BOT_TOKEN"],
            chat_id=cfg["TELEGRAM_CHAT_GLOBAL"],
            thread_id=cfg["TELEGRAM_THREAD_GLOBAL"],
            photo_path=photo_path,
            caption=combined
        )
    else:
        send_to_telegram(
            token=cfg["TELEGRAM_BOT_TOKEN"],
            chat_id=cfg["TELEGRAM_CHAT_GLOBAL"],
            thread_id=cfg["TELEGRAM_THREAD_GLOBAL"],
            photo_path=photo_path,
            caption=ukr_part,
            follow_up=eng_part
        )

    # ── Channel 2: UKR Only ──────────────────────────────────────────────────
    ukr_only = f'<b><a href="{release_url}">СКАЧАТИ</a></b>\n\n{ukr_html}'
    
    print(f"  Posting to UKR Chat {cfg['TELEGRAM_CHAT_UKR']} ...")
    send_to_telegram(
        token=cfg["TELEGRAM_BOT_TOKEN"],
        chat_id=cfg["TELEGRAM_CHAT_UKR"],
        thread_id=cfg["TELEGRAM_THREAD_UKR"],
        photo_path=photo_path,
        caption=ukr_only
    )


    print("=" * 60)
    print("  Done!")
    print("=" * 60)

if __name__ == "__main__":
    main()

