#!/usr/bin/env python3
"""
changelog_manager.py — Kefir Changelog Aggregator

Collects and manages changelogs from GitHub releases (rashevskyv/kefir).

Commands:
  --collect-changelogs  : Fetch all changelogs from GitHub releases (v790 to latest)
  --update-changelog    : Add new version blocks from current changelog to full changelog
  --sort-changelog      : Sort version blocks in full changelog (newest to oldest)

Reads config from .env in the Kefirosphere root.
Works on both Windows (PowerShell) and WSL.

Required .env variables:
  GITHUB_TOKEN       — GitHub Personal Access Token
  KEFIR_ROOT_DIR     — Path to _kefir root (e.g. D:\\git\\dev\\_kefir)
  RELEASE_REPO_OWNER — GitHub username (e.g. rashevskyv)
  RELEASE_REPO_NAME  — Repository name (e.g. kefir)
"""

import os
import sys
import re
import json
import time
from pathlib import Path
from typing import List, Tuple

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
KEFIROSPHERE_DIR = SCRIPT_DIR.parent
ENV_FILE = KEFIROSPHERE_DIR / ".env"

# ─────────────────────────────────────────────────────────────────────────────
# .env loader
# ─────────────────────────────────────────────────────────────────────────────

def load_env():
    """Load .env file and populate os.environ with cross-platform path normalization."""
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

        # Cross-platform path normalization
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

        os.environ[key] = val

    required = ["GITHUB_TOKEN", "KEFIR_ROOT_DIR", "RELEASE_REPO_OWNER", "RELEASE_REPO_NAME"]
    cfg = {}
    for k in required:
        v = os.environ.get(k)
        if not v:
            print(f"[ERROR] Missing required .env variable: {k}", file=sys.stderr)
            sys.exit(1)
        cfg[k] = v

    cfg["KEFIR_ROOT_DIR"] = os.path.normpath(cfg["KEFIR_ROOT_DIR"])
    cfg["REPO"] = f"{cfg['RELEASE_REPO_OWNER']}/{cfg['RELEASE_REPO_NAME']}"
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# GitHub API helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_github_releases(owner: str, repo: str, token: str, min_version: int = 790) -> List[dict]:
    """Fetch all releases from GitHub API starting from min_version."""
    import urllib.request
    import urllib.error

    releases = []
    page = 1
    per_page = 100

    print(f"  Fetching releases from {owner}/{repo} (starting from v{min_version})...")

    while True:
        url = f"https://api.github.com/repos/{owner}/{repo}/releases?page={page}&per_page={per_page}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Kefirosphere-Changelog-Manager"
        }

        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode("utf-8"))

                if not data:
                    break

                for release in data:
                    tag = release.get("tag_name", "")
                    # Extract version number from tag (e.g., "790", "816")
                    version_match = re.search(r"(\d+)", tag)
                    if version_match:
                        version_num = int(version_match.group(1))
                        if version_num >= min_version:
                            releases.append(release)
                            print(f"    Found: {tag}")

                # Check rate limit
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining and int(remaining) < 10:
                    print(f"  [WARN] GitHub API rate limit low: {remaining} requests remaining")

                page += 1
                time.sleep(0.5)  # Be nice to GitHub API

        except urllib.error.HTTPError as e:
            if e.code == 403:
                print(f"[ERROR] GitHub API rate limit exceeded or token invalid", file=sys.stderr)
            else:
                print(f"[ERROR] GitHub API error: {e.code} {e.reason}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Failed to fetch releases: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"  Total releases found: {len(releases)}")
    return releases


def extract_changelog_from_body(body: str) -> Tuple[str, str]:
    """Extract UKR and ENG changelog sections from release body.

    Returns: (ukr_section, eng_section)
    Each section includes preamble + version blocks.
    Filters out Atmosphere details lines.
    """
    if not body:
        return "", ""

    # Find UKR section: from #### **UKR** to #### **ENG** (or end of changelog block)
    ukr_match = re.search(
        r"#### \*\*UKR\*\*(.*?)(?=#### \*\*ENG\*\*|_{4,}|$)",
        body,
        re.DOTALL
    )

    # Find ENG section: from #### **ENG** to separator line or end
    eng_match = re.search(
        r"#### \*\*ENG\*\*(.*?)(?=_{4,}|$)",
        body,
        re.DOTALL
    )

    ukr_section = ukr_match.group(1).strip() if ukr_match else ""
    eng_section = eng_match.group(1).strip() if eng_match else ""

    # Filter out Atmosphere details lines
    ukr_section = filter_atmosphere_details(ukr_section)
    eng_section = filter_atmosphere_details(eng_section)

    return ukr_section, eng_section


# ─────────────────────────────────────────────────────────────────────────────
# Changelog parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_changelog_section(section: str) -> Tuple[str, List[Tuple[int, str]]]:
    """Parse a language section into preamble and version blocks.

    Returns: (preamble, [(version_num, version_text), ...])
    """
    if not section:
        return "", []

    lines = section.split("\n")
    preamble_lines = []
    version_blocks = []
    current_version = None
    current_block = []

    for line in lines:
        # Check if line is a version marker: **123**
        version_match = re.match(r"^\*\*(\d+)\*\*\s*$", line.strip())

        if version_match:
            # Save previous block if exists
            if current_version is not None:
                version_blocks.append((current_version, "\n".join(current_block).strip()))

            # Start new block
            current_version = int(version_match.group(1))
            current_block = [line]
        elif current_version is not None:
            # We're inside a version block
            current_block.append(line)
        else:
            # We're still in preamble
            preamble_lines.append(line)

    # Save last block
    if current_version is not None:
        version_blocks.append((current_version, "\n".join(current_block).strip()))

    preamble = "\n".join(preamble_lines).strip()
    return preamble, version_blocks


def filter_atmosphere_details(text: str) -> str:
    """Remove lines containing Atmosphere details links (UKR/ENG)."""
    lines = text.split("\n")
    filtered = []

    for line in lines:
        # Skip lines with Atmosphere details in both languages
        if "Подробиці про зміни в Atmosphere" in line or \
           "Подробніше про зміни в Atmosphere" in line or \
           "More details about changes in Atmosphere" in line:
            continue
        filtered.append(line)

    return "\n".join(filtered)


def format_changelog_section(preamble: str, version_blocks: List[Tuple[int, str]]) -> str:
    """Format preamble and version blocks back into text."""
    parts = []

    if preamble:
        parts.append(preamble)

    for _, block_text in version_blocks:
        # Filter out Atmosphere details lines
        filtered_text = filter_atmosphere_details(block_text)
        parts.append(filtered_text)

    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Command: collect-changelogs
# ─────────────────────────────────────────────────────────────────────────────

def collect_changelogs(cfg: dict):
    """Fetch all changelogs from GitHub releases and save to changelog_full."""
    kefir_root = Path(cfg["KEFIR_ROOT_DIR"])
    owner = cfg["RELEASE_REPO_OWNER"]
    repo_name = cfg["RELEASE_REPO_NAME"]
    token = cfg["GITHUB_TOKEN"]

    print("\n" + "=" * 60)
    print("  Collecting changelogs from GitHub releases")
    print("=" * 60)

    # Fetch releases
    releases = fetch_github_releases(owner, repo_name, token, min_version=790)

    if not releases:
        print("[ERROR] No releases found", file=sys.stderr)
        sys.exit(1)

    # Aggregate all version blocks
    all_ukr_blocks = []
    all_eng_blocks = []
    latest_ukr_preamble = ""
    latest_eng_preamble = ""

    # Process releases (newest first from API)
    for release in releases:
        tag = release.get("tag_name", "")
        body = release.get("body", "")

        ukr_section, eng_section = extract_changelog_from_body(body)

        if ukr_section:
            preamble, blocks = parse_changelog_section(ukr_section)
            if not latest_ukr_preamble and preamble:
                latest_ukr_preamble = preamble
            all_ukr_blocks.extend(blocks)

        if eng_section:
            preamble, blocks = parse_changelog_section(eng_section)
            if not latest_eng_preamble and preamble:
                latest_eng_preamble = preamble
            all_eng_blocks.extend(blocks)

    # Sort blocks by version (newest first)
    all_ukr_blocks.sort(key=lambda x: x[0], reverse=True)
    all_eng_blocks.sort(key=lambda x: x[0], reverse=True)

    # Remove duplicates (keep first occurrence)
    seen_ukr = set()
    unique_ukr_blocks = []
    for ver, text in all_ukr_blocks:
        if ver not in seen_ukr:
            seen_ukr.add(ver)
            unique_ukr_blocks.append((ver, text))

    seen_eng = set()
    unique_eng_blocks = []
    for ver, text in all_eng_blocks:
        if ver not in seen_eng:
            seen_eng.add(ver)
            unique_eng_blocks.append((ver, text))

    # Build full changelog
    ukr_full = format_changelog_section(latest_ukr_preamble, unique_ukr_blocks)
    eng_full = format_changelog_section(latest_eng_preamble, unique_eng_blocks)

    full_changelog = f"""## Changelog
#### **UKR**
{ukr_full}

____

#### **ENG**
{eng_full}
"""

    # Save to changelog_full
    output_file = kefir_root / "changelog_full"
    output_file.write_text(full_changelog, encoding="utf-8")

    print(f"\n  ✓ Collected {len(unique_ukr_blocks)} UKR versions, {len(unique_eng_blocks)} ENG versions")
    print(f"  ✓ Saved to: {output_file}")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Command: update-changelog
# ─────────────────────────────────────────────────────────────────────────────

def update_changelog(cfg: dict):
    """Add new version blocks from current changelog to changelog_full."""
    kefir_root = Path(cfg["KEFIR_ROOT_DIR"])
    current_file = kefir_root / "changelog"
    full_file = kefir_root / "changelog_full"

    print("\n" + "=" * 60)
    print("  Updating changelog_full with new versions")
    print("=" * 60)

    if not current_file.exists():
        print(f"[ERROR] Current changelog not found: {current_file}", file=sys.stderr)
        sys.exit(1)

    if not full_file.exists():
        print(f"[ERROR] Full changelog not found: {full_file}", file=sys.stderr)
        print("  Run --collect-changelogs first to create it.")
        sys.exit(1)

    # Parse current changelog
    current_content = current_file.read_text(encoding="utf-8")
    current_ukr_match = re.search(r"#### \*\*UKR\*\*(.*?)(?=#### \*\*ENG\*\*|$)", current_content, re.DOTALL)
    current_eng_match = re.search(r"#### \*\*ENG\*\*(.*?)(?=$)", current_content, re.DOTALL)

    current_ukr = current_ukr_match.group(1).strip() if current_ukr_match else ""
    current_eng = current_eng_match.group(1).strip() if current_eng_match else ""

    current_ukr_preamble, current_ukr_blocks = parse_changelog_section(current_ukr)
    current_eng_preamble, current_eng_blocks = parse_changelog_section(current_eng)

    # Parse full changelog
    full_content = full_file.read_text(encoding="utf-8")
    full_ukr_match = re.search(r"#### \*\*UKR\*\*(.*?)(?=____)", full_content, re.DOTALL)
    full_eng_match = re.search(r"#### \*\*ENG\*\*(.*?)$", full_content, re.DOTALL)

    full_ukr = full_ukr_match.group(1).strip() if full_ukr_match else ""
    full_eng = full_eng_match.group(1).strip() if full_eng_match else ""

    full_ukr_preamble, full_ukr_blocks = parse_changelog_section(full_ukr)
    full_eng_preamble, full_eng_blocks = parse_changelog_section(full_eng)

    # Merge blocks (add new ones from current)
    existing_ukr_versions = {ver for ver, _ in full_ukr_blocks}
    existing_eng_versions = {ver for ver, _ in full_eng_blocks}

    new_ukr_count = 0
    for ver, text in current_ukr_blocks:
        if ver not in existing_ukr_versions:
            full_ukr_blocks.append((ver, text))
            new_ukr_count += 1
            print(f"  [UKR] Added version {ver}")

    new_eng_count = 0
    for ver, text in current_eng_blocks:
        if ver not in existing_eng_versions:
            full_eng_blocks.append((ver, text))
            new_eng_count += 1
            print(f"  [ENG] Added version {ver}")

    # Update preambles (use current as latest)
    if current_ukr_preamble:
        full_ukr_preamble = current_ukr_preamble
    if current_eng_preamble:
        full_eng_preamble = current_eng_preamble

    # Sort blocks (newest first)
    full_ukr_blocks.sort(key=lambda x: x[0], reverse=True)
    full_eng_blocks.sort(key=lambda x: x[0], reverse=True)

    # Build updated changelog
    ukr_full = format_changelog_section(full_ukr_preamble, full_ukr_blocks)
    eng_full = format_changelog_section(full_eng_preamble, full_eng_blocks)

    updated_changelog = f"""## Changelog
#### **UKR**
{ukr_full}

____

#### **ENG**
{eng_full}
"""

    # Save
    full_file.write_text(updated_changelog, encoding="utf-8")

    print(f"\n  ✓ Added {new_ukr_count} new UKR versions, {new_eng_count} new ENG versions")
    print(f"  ✓ Total: {len(full_ukr_blocks)} UKR versions, {len(full_eng_blocks)} ENG versions")
    print(f"  ✓ Saved to: {full_file}")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Command: sort-changelog
# ─────────────────────────────────────────────────────────────────────────────

def sort_changelog(cfg: dict):
    """Sort version blocks in changelog_full (newest to oldest)."""
    kefir_root = Path(cfg["KEFIR_ROOT_DIR"])
    full_file = kefir_root / "changelog_full"

    print("\n" + "=" * 60)
    print("  Sorting changelog_full")
    print("=" * 60)

    if not full_file.exists():
        print(f"[ERROR] Full changelog not found: {full_file}", file=sys.stderr)
        sys.exit(1)

    # Parse
    content = full_file.read_text(encoding="utf-8")
    ukr_match = re.search(r"#### \*\*UKR\*\*(.*?)(?=____)", content, re.DOTALL)
    eng_match = re.search(r"#### \*\*ENG\*\*(.*?)$", content, re.DOTALL)

    ukr_section = ukr_match.group(1).strip() if ukr_match else ""
    eng_section = eng_match.group(1).strip() if eng_match else ""

    ukr_preamble, ukr_blocks = parse_changelog_section(ukr_section)
    eng_preamble, eng_blocks = parse_changelog_section(eng_section)

    # Sort
    ukr_blocks.sort(key=lambda x: x[0], reverse=True)
    eng_blocks.sort(key=lambda x: x[0], reverse=True)

    # Rebuild
    ukr_full = format_changelog_section(ukr_preamble, ukr_blocks)
    eng_full = format_changelog_section(eng_preamble, eng_blocks)

    sorted_changelog = f"""## Changelog
#### **UKR**
{ukr_full}

____

#### **ENG**
{eng_full}
"""

    # Save
    full_file.write_text(sorted_changelog, encoding="utf-8")

    print(f"  ✓ Sorted {len(ukr_blocks)} UKR versions, {len(eng_blocks)} ENG versions")
    print(f"  ✓ Saved to: {full_file}")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python changelog_manager.py --collect-changelogs")
        print("  python changelog_manager.py --update-changelog")
        print("  python changelog_manager.py --sort-changelog")
        sys.exit(1)

    command = sys.argv[1]
    cfg = load_env()

    if command == "--collect-changelogs":
        collect_changelogs(cfg)
    elif command == "--update-changelog":
        update_changelog(cfg)
    elif command == "--sort-changelog":
        sort_changelog(cfg)
    else:
        print(f"[ERROR] Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
