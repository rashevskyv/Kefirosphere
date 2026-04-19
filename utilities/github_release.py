#!/usr/bin/env python3
"""
github_release.py — Kefirosphere GitHub Deploy Script

Uploads release files to GitHub (rashevskyv/kefir).
Decision logic:
  - If Atmosphere version has changed since last deploy → create NEW release.
  - Otherwise → edit the LATEST release.

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
import subprocess
import json
from pathlib import Path

# Force UTF-8 output on Windows (avoids CP1252 encoding errors)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR       = Path(__file__).resolve().parent
KEFIROSPHERE_DIR = SCRIPT_DIR.parent
STATE_FILE       = SCRIPT_DIR / "build_state.json"
ENV_FILE         = KEFIROSPHERE_DIR / ".env"
ATMOSPHERE_DIR   = (KEFIROSPHERE_DIR / ".." / "Atmosphere").resolve()
AMS_VERSION_H    = ATMOSPHERE_DIR / "libraries" / "libvapours" / "include" / "vapours" / "ams" / "ams_api_version.h"

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
# State manager (build_state.json)
# ─────────────────────────────────────────────────────────────────────────────

def read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_state(data: dict):
    current = read_state()
    current.update(data)
    STATE_FILE.write_text(
        json.dumps(current, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Version readers
# ─────────────────────────────────────────────────────────────────────────────

def get_atmosphere_version() -> str | None:
    """Read current Atmosphere version from ams_api_version.h."""
    if not AMS_VERSION_H.exists():
        print(f"[WARN] ams_api_version.h not found at {AMS_VERSION_H}", file=sys.stderr)
        return None
    content = AMS_VERSION_H.read_text(encoding="utf-8")
    maj = re.search(r"#define\s+ATMOSPHERE_RELEASE_VERSION_MAJOR\s+(\d+)", content)
    minn = re.search(r"#define\s+ATMOSPHERE_RELEASE_VERSION_MINOR\s+(\d+)", content)
    mic = re.search(r"#define\s+ATMOSPHERE_RELEASE_VERSION_MICRO\s+(\d+)", content)
    if maj and minn and mic:
        return f"{maj.group(1)}.{minn.group(1)}.{mic.group(1)}"
    return None


def get_kefir_version(kefir_root: str) -> str:
    """Read current Kefir version number from _kefir/version."""
    ver_file = Path(kefir_root) / "version"
    if not ver_file.exists():
        print(f"[ERROR] version file not found at {ver_file}", file=sys.stderr)
        sys.exit(1)
    return ver_file.read_text(encoding="utf-8").strip()


def get_hekate_version() -> str:
    """Read cached hekate version from build_state.json."""
    state = read_state()
    ver = state.get("HEKATE_LATEST_VERSION", "")
    # Strip leading 'v' if present
    return ver.lstrip("v") if ver else "?"


# ─────────────────────────────────────────────────────────────────────────────
# Changelog parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_full_changelog(kefir_root: str) -> str:
    """Extract the entire UKR + ENG changelog block (all versions, raw)."""
    changelog_path = Path(kefir_root) / "changelog"
    if not changelog_path.exists():
        print(f"[WARN] changelog not found at {changelog_path}", file=sys.stderr)
        return ""
    content = changelog_path.read_text(encoding="utf-8")
    # Strip the leading "## Changelog" header — we'll add it in the template
    # Return everything after the first "#### **UKR**"
    match = re.search(r"(#### \*\*UKR\*\*.*)", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Release body builder
# ─────────────────────────────────────────────────────────────────────────────

RELEASE_BODY_TEMPLATE = """\
# [KEFIR {ver} ![GitHub Downloads (specific asset, all releases)](https://img.shields.io/github/downloads/{owner}/{repo}/kefir{ver}.zip)](https://github.com/{owner}/{repo}/releases/download/{ver}/kefir{ver}.zip)

<img width="1280" height="720" alt="kefir" src="https://github.com/{owner}/{repo}/releases/download/{ver}/kefir.png" />


## Changelog 
{changelog_body}

______

![telegram](https://github.com/user-attachments/assets/da539e4c-322e-4ba7-b191-01056246cc36)
https://t.me/kefir_ukr

Це збірка, яка складається з модифікованої Atmosphere, необхідних програм та скриптів, які все це встановлюють правильним чином. Її було придумано для полегшення встановлення та обслуговування програмного забезпечення на взломаній Nintendo Switch. Зміни, внесені в Atmosphere направлені на збільшення якості досвіду користування самою системою.

**Зміни відносно ванільної Atmosphere**:

* Версії кефіру біля версії системи
* Встановлення певного драйверу карти пам'яті за замовчуванням при оновленні системи
* Видалення перевірки ACID-підпису для використання хомбрю без патчів
* Видалення логіювання всього системою для запобігання засмітнення картки пам'яті та надмірного її використання
* Перенаправлення сейвів з внутрішньої пам'яті на карту пам'яті при використанні емунанду, щоб зменшити вірогідність їх втрати при виходу емунанду з ладу (опційно)
* Вбудовані сігпатчі

**English**:

This is a bundle that consists of a modified Atmosphere, necessary programs and scripts that all install correctly. It was designed to make it easier to install and maintain software on a hacked Nintendo Switch. The changes made to Atmosphere are aimed at improving the quality of the user experience.

**Kefirosphere features**:

* Updating the firmware version to match the system version
* Installing a specific memory card driver by default when updating the system
* Removing the ACID signature check for using homebrew without patches
* Removing system logging to prevent cluttering the memory card and excessive use
* Redirecting saves from internal memory to the memory card when using the emuNAND command to reduce the likelihood of losing them when exiting the emuNAND command (optional)
* Built-in sigpatches

[Склад / Consistent](https://switch.customfw.xyz/kefir#%D1%81%D0%BE%D1%81%D1%82%D0%B0%D0%B2-kefir)

___

## Як встановити або оновити кефір / How to install or update kefir

**Встановлення та оновлення кефіру відбувається однаково!**

_Якщо ви є користувачем MacOS, використовуйте [ці рекомендації](https://switch.customfw.xyz/sd-macos), щоб уникнути проблем з картою пам'яті_

**Щоб потрапити в hekate прошитій приставці, перезавантажте консоль, на заставці кефіра натисніть кнопку зниження гучності.** Попавши в hekate, можете витягувати карту пам'яті. Після того як ви знову вставите картку в консоль, запустіть прошивку через меню Launch -> Atmosphere.

**English**:

**Installing and updating kefir is done the same way!**

_If you are a MacOS user, use [these recommendations](https://switch.customfw.xyz/sd-macos) to avoid problems with the memory card_

**To get into hekate on a firmware-flashed device, reboot the console, on the kefir splash screen press the volume down button.** Once in hekate, you can extract the memory card. After reinserting the card into the console, launch the firmware through the menu Launch -> Atmosphere.

___

### Для всіх ОС / For all OS

1. Скопіюйте в корінь карти пам'яті **вміст архіву** `kefir.zip`
    * **НЕ САМ АРХІВ, ЙОГО ВМІСТЬ!**
2. Вставте картку пам'яті назад у Switch
3. У **hekate** виберіть `More configs` -> `Update Kefir`
4. Після закінчення встановлення приставка запуститься у прошивку

**English**:

1. Copy the contents of the `kefir.zip` archive **to the root** of the memory card
    * **NOT THE ARCHIVE ITSELF, ITS CONTENTS!**
2. Insert the memory card back into the Switch
3. In **hekate** select `More configs` -> `Update Kefir`
4. After installation is complete, the device will boot into the firmware

### Тільки для Windows, також якщо попередній метод не спрацював / Only for Windows, also if the previous method did not work

1. Розпакуйте на ПК архів `kefir.zip`
2. Запустіть `install.bat` з розпакованого архіву та дотримуйтесь вказівок на екрані
3. Коли ви побачите на екрані напис "**All Done**", вставте картку пам'яті назад у консоль і запустіть прошивку

**English**:

1. Extract the `kefir.zip` archive on your PC
2. Run `install.bat` from the extracted archive and follow the on-screen instructions
3. When you see the message "**All Done**" on the screen, insert the memory card back into the console and start the firmware

## Можливі помилки / Possible errors

* У разі виникнення помилки "**Is BEK missing**" вимкніть приставку та увімкніть заново
* У разі виникнення помилки "**[NOFAT]**" при оновленні кефіру через гекату, оновіть його за допомогою `install.bat`
* У разі виникнення помилки "**Failed to match warmboot with fuses**", перезагрузіть консоль в **hekate** -> **More configs** -> **Full Stock**, або оновіть emunand до останньої версії
* Якщо виникають будь-які інші помилки, зверніться до розділу "[Проблеми та рішення посібника](https://switch.customfw.xyz/troubleshooting)"

**English**:

* In case of the "**Is BEK missing**" error, turn off the console and turn it on again
* In case of the "**[NOFAT]**" error when updating kefir through hekate, update it using `install.bat`
* If you receive the error "**Failed to match warmboot with fuses**" when launching Emunand, reboot the console in **hekate** -> **More configs** -> **Full Stock** or update the Emunand to the latest version.
* If any other errors occur, please refer to the "[Troubleshootings](https://switch.customfw.xyz/troubleshooting)" section of the guide
"""


def build_release_body(ver: str, owner: str, repo: str, atmo_ver: str,
                       hekate_ver: str, changelog_body: str) -> str:
    return RELEASE_BODY_TEMPLATE.format(
        ver=ver,
        owner=owner,
        repo=repo,
        atmo_ver=atmo_ver,
        hekate_ver=hekate_ver,
        changelog_body=changelog_body,
    )


def build_release_title(ver: str, atmo_ver: str, hekate_ver: str) -> str:
    return f"KEFIR {ver}, Atmosphere {atmo_ver}, hekate {hekate_ver}"


# ─────────────────────────────────────────────────────────────────────────────
# gh CLI runner
# ─────────────────────────────────────────────────────────────────────────────

def run_gh(*args, check=True) -> subprocess.CompletedProcess:
    """Run a gh CLI command, handling Windows/WSL differences."""
    import shutil
    
    # Check if we are in WSL
    is_wsl = False
    if sys.platform != "win32":
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    is_wsl = True
        except:
            pass

    cmd_name = "gh"
    if sys.platform != "win32":
        if not shutil.which("gh") and shutil.which("gh.exe"):
            cmd_name = "gh.exe"

    # Convert paths if using gh.exe in WSL
    final_args = []
    for arg in args:
        processed_arg = arg
        if is_wsl and cmd_name == "gh.exe":
            # If it's an absolute path or relative path to a file/dir
            if arg.startswith("/") or arg.startswith("./") or arg.startswith("../") or os.path.exists(arg):
                try:
                    processed_arg = subprocess.check_output(["wslpath", "-w", arg], text=True).strip()
                except:
                    pass
        final_args.append(processed_arg)

    cmd = [cmd_name] + final_args
    print(f"  [{cmd_name}] {' '.join(final_args)}")
    
    # We must pass the GITHUB_TOKEN if it's in the environment
    env = os.environ.copy()
    
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    
    if check and res.returncode != 0:
        print(f"[ERROR] {cmd_name} command failed:\n{res.stderr}", file=sys.stderr)
        sys.exit(1)
    return res




def get_latest_release_tag(repo: str) -> str | None:
    """Return tag name of the latest release, or None if no releases exist."""
    res = run_gh("release", "list", "--repo", repo, "--limit", "1",
                 "--json", "tagName", "--jq", ".[0].tagName", check=False)
    tag = res.stdout.strip()
    return tag if tag and tag != "null" else None


# ─────────────────────────────────────────────────────────────────────────────
# Collect files to upload
# ─────────────────────────────────────────────────────────────────────────────

def collect_assets(kefir_root: str) -> list[Path]:
    """Return list of file paths to upload as release assets.

    Scans the release/ subdirectory and picks up every file found there
    (zip, version, changelog — whatever was placed there by the build).
    Also adds kefir.png from the kefir root as the cover image.
    """
    root = Path(kefir_root)
    assets = []

    # All files from the release/ folder
    release_dir = root / "release"
    if not release_dir.exists():
        print(f"[ERROR] release/ directory not found: {release_dir}", file=sys.stderr)
        sys.exit(1)

    release_files = sorted(f for f in release_dir.iterdir() if f.is_file())
    if not release_files:
        print(f"[ERROR] release/ directory is empty: {release_dir}", file=sys.stderr)
        sys.exit(1)

    for f in release_files:
        print(f"  [asset] {f.name}")
        assets.append(f)

    # Cover image lives in kefir root (not in release/)
    logo_file = root / "kefir.png"
    if logo_file.exists():
        print(f"  [asset] {logo_file.name}")
        assets.append(logo_file)
    else:
        print(f"[WARN] kefir.png not found at {logo_file} - skipping image upload")

    return assets



# ─────────────────────────────────────────────────────────────────────────────
# Main deploy logic
# ─────────────────────────────────────────────────────────────────────────────

def delete_all_assets(repo: str, tag: str):
    """List all assets in a release and delete them one by one."""
    print(f"  Cleaning up existing assets for tag '{tag}' …")
    res = run_gh("release", "view", tag, "--repo", repo, "--json", "assets", check=False)
    if res.returncode != 0:
        return

    try:
        data = json.loads(res.stdout)
        assets = data.get("assets", [])
        for a in assets:
            name = a["name"]
            print(f"    [delete] {name}")
            run_gh("release", "delete-asset", tag, name, "--repo", repo, "-y")
    except (json.JSONDecodeError, KeyError):
        pass


def deploy(cfg: dict):
    kefir_root  = cfg["KEFIR_ROOT_DIR"]
    repo        = cfg["REPO"]
    owner       = cfg["RELEASE_REPO_OWNER"]
    repo_name   = cfg["RELEASE_REPO_NAME"]

    # ── Gather versions ───────────────────────────────────────────────────────
    ver        = get_kefir_version(kefir_root)
    atmo_live  = get_atmosphere_version()
    atmo_state = read_state().get("ATMOSPHERE_LATEST_VERSION")
    hekate_ver = get_hekate_version()

    print(f"\n  Kefir version    : {ver}")
    print(f"  Atmosphere live  : {atmo_live  or 'N/A'}")
    print(f"  Atmosphere state : {atmo_state or 'N/A (first deploy)'}")
    print(f"  Hekate version   : {hekate_ver}")

    # ── Determine release mode ────────────────────────────────────────────────
    atmo_changed = (atmo_live is not None) and (atmo_live != atmo_state)
    if atmo_changed:
        mode = "new"
        print(f"\n  [!] Atmosphere updated ({atmo_state} -> {atmo_live}): CREATE new release\n")
    else:
        mode = "edit"
        latest_tag = get_latest_release_tag(repo)
        if not latest_tag:
            print("  [!] No existing release found, creating new one anyway.\n")
            mode = "new"
        else:
            print(f"  [*] Atmosphere unchanged: EDIT latest release (tag: {latest_tag})\n")

    # ── Build body ────────────────────────────────────────────────────────────
    changelog_body = parse_full_changelog(kefir_root)
    title          = build_release_title(ver, atmo_live or "?", hekate_ver)
    body           = build_release_body(ver, owner, repo_name,
                                        atmo_live or "?", hekate_ver,
                                        changelog_body)

    # Write body to a temp file (avoids shell escaping issues)
    body_file = SCRIPT_DIR / "_release_body.md"
    body_file.write_text(body, encoding="utf-8")

    # ── Collect assets ────────────────────────────────────────────────────────
    assets = collect_assets(kefir_root)
    asset_paths = [str(a) for a in assets]

    try:
        if mode == "new":
            # Create new release: tag = kefir version number
            print(f"  Creating release {ver} …")
            run_gh(
                "release", "create", ver,
                "--repo",   repo,
                "--title",  title,
                "--notes-file", str(body_file),
                *asset_paths,
            )
            print(f"  ✓ New release '{title}' created.")

        else:  # edit
            latest_tag = get_latest_release_tag(repo)

            # Edit title + body AND update the tag to current version
            print(f"  Updating release tag '{latest_tag}' -> '{ver}' and body …")
            run_gh(
                "release", "edit", latest_tag,
                "--repo",   repo,
                "--tag",    ver,
                "--title",  title,
                "--notes-file", str(body_file),
            )

            # Delete old assets before uploading new ones
            delete_all_assets(repo, ver)  # Use the new tag name for asset cleanup/upload

            # Upload assets
            print(f"  Uploading {len(assets)} new asset(s) …")
            run_gh(
                "release", "upload", ver,
                "--repo", repo,
                "--clobber",
                *asset_paths,
            )
            print(f"  ✓ Release '{title}' updated (tag moved to {ver}).")



    finally:
        # Clean up temp body file
        if body_file.exists():
            body_file.unlink()

    # ── Update state ──────────────────────────────────────────────────────────
    if atmo_live:
        write_state({"ATMOSPHERE_LATEST_VERSION": atmo_live})
    print(f"\n  build_state.json updated (ATMOSPHERE_LATEST_VERSION = {atmo_live})\n")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Kefirosphere - GitHub Release Deploy")
    print("=" * 60)

    cfg = load_env()
    print(f"  Repo  : {cfg['REPO']}")
    print(f"  Token : {'*' * 4}{cfg['GITHUB_TOKEN'][-4:]}")

    deploy(cfg)

    print("=" * 60)
    print("  Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
