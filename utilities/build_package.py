#!/usr/bin/env python3
"""
Build and package Kefir distribution.
Replaces the legacy ___build.bat script with Python implementation.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Literal

# Detect if running in WSL and convert paths accordingly
def normalize_path(path_str):
    """Convert between Windows and WSL paths."""
    path = Path(path_str)

    # If running in WSL and path looks like Windows path
    if sys.platform == "linux" and ":" in str(path):
        # D:/git/dev -> /mnt/d/git/dev
        parts = str(path).replace("\\", "/").split("/")
        if len(parts) >= 1 and ":" in parts[0]:
            drive = parts[0].rstrip(":").lower()
            rest = "/".join(parts[1:])
            return Path(f"/mnt/{drive}/{rest}")

    # If running on Windows and path looks like WSL path
    if sys.platform == "win32" and str(path).startswith("/mnt/"):
        # /mnt/d/git/dev -> D:/git/dev
        parts = str(path).split("/")
        if len(parts) >= 3:
            drive = parts[2].upper()
            rest = "/".join(parts[3:])
            return Path(f"{drive}:/{rest}")

    return path

# Configuration
WORKING_DIR = normalize_path("D:/git/dev")
KEFIR_SOURCE = WORKING_DIR / "_kefir" / "kefir"
BUILD_DIR = WORKING_DIR / "_kefir" / "build"
RELEASE_DIR = WORKING_DIR / "_kefir" / "release"
TEST_DIR = WORKING_DIR / "_kefir" / "test"
SITE_DIR = normalize_path("D:/git/site/switch")
SEVEN_ZIP = normalize_path("E:/Switch/7zip/7za.exe")

# Files/dirs to exclude from archive
EXCLUDE_PATTERNS = [
    ".gitignore",
    "kefir_installer",
    "desktop.ini",
    "___build.bat",
    "hekate_ctcaer_*.bin",
    "kefir.png",
    "___build_test.bat",
    "install1.bat",
    "release",
    "release_test",
    ".git",
    "build",
    "emu.cmd",
    "version",
    "changelog*",
    "README.md",
]

# Directories to fix attributes for
ATTRIB_DIRS = [
    "atmosphere",
    "atmosphere/titles",
    "sept",
    "bootloader",
    "config",
    "switch",
    "tinfoil",
    "games",
    "themes",
    "emuiibo",
    "_backup",
    "sxos",
    "pegascape",
    "switch/fakenews-injector",
]

# Files to fix attributes for
ATTRIB_FILES = [
    "hbmenu.nro",
    "keys.dat",
    "boot.dat",
    "payload.bin",
]


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def read_version() -> str:
    """Read version from version file."""
    version_file = WORKING_DIR / "_kefir" / "version"
    if not version_file.exists():
        print(f"Error: Version file not found at {version_file}")
        sys.exit(1)

    version = version_file.read_text(encoding="utf-8").strip()
    print(f"Building version: {version}")
    return version


def prompt_build_type() -> Literal["release", "test"]:
    """Prompt user for build type."""
    print_section("Build Type Selection")
    print("  1. Release")
    print("  2. Test")
    print("\n" + "=" * 70)

    while True:
        choice = input("Select build type (1 or 2): ").strip()
        if choice == "1":
            return "release"
        elif choice == "2":
            return "test"
        else:
            print("Invalid choice. Please enter 1 or 2.")


def clean_build_dir():
    """Remove existing build directory."""
    if BUILD_DIR.exists():
        print(f"Cleaning build directory: {BUILD_DIR}")
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)


def copy_kefir_files():
    """Copy Kefir source files to build directory."""
    print_section("Copying Kefir Files")

    if not KEFIR_SOURCE.exists():
        print(f"Error: Kefir source directory not found: {KEFIR_SOURCE}")
        sys.exit(1)

    print(f"Copying from: {KEFIR_SOURCE}")
    print(f"Copying to: {BUILD_DIR}")

    # Copy all files
    shutil.copytree(KEFIR_SOURCE, BUILD_DIR, dirs_exist_ok=True)

    # Copy payload.bin specifically (if exists)
    payload = KEFIR_SOURCE / "payload.bin"
    if payload.exists():
        shutil.copy2(payload, BUILD_DIR / "payload.bin")

    # Remove old hekate ini files
    bootloader_dir = BUILD_DIR / "bootloader"
    if bootloader_dir.exists():
        for ini_file in bootloader_dir.glob("hekate_ipl_*.ini"):
            print(f"Removing old ini: {ini_file.name}")
            ini_file.unlink()

    print("Files copied successfully.")


def fix_attributes():
    """Fix file attributes (remove archive bit)."""
    print_section("Fixing File Attributes")

    if os.name != 'nt':
        print("Skipping attribute fix (not on Windows)")
        return

    # Fix directory attributes
    for dir_path in ATTRIB_DIRS:
        full_path = BUILD_DIR / dir_path
        if full_path.exists():
            try:
                subprocess.run(
                    ["attrib", "-A", "/S", "/D", str(full_path / "*")],
                    check=False,
                    capture_output=True
                )
                subprocess.run(
                    ["attrib", "-A", str(full_path)],
                    check=False,
                    capture_output=True
                )
                print(f"Fixed attributes: {dir_path}")
            except Exception as e:
                print(f"Warning: Could not fix attributes for {dir_path}: {e}")

    # Fix file attributes
    for file_name in ATTRIB_FILES:
        full_path = BUILD_DIR / file_name
        if full_path.exists():
            try:
                subprocess.run(
                    ["attrib", "-A", str(full_path)],
                    check=False,
                    capture_output=True
                )
                print(f"Fixed attributes: {file_name}")
            except Exception as e:
                print(f"Warning: Could not fix attributes for {file_name}: {e}")

    # Set archive attribute for mercury (special case)
    mercury_path = BUILD_DIR / "switch" / "mercury"
    if mercury_path.exists():
        try:
            subprocess.run(
                ["attrib", "+A", str(mercury_path)],
                check=False,
                capture_output=True
            )
            print("Set archive attribute: switch/mercury")
        except Exception as e:
            print(f"Warning: Could not set attribute for mercury: {e}")

    # Fix build directory itself
    try:
        subprocess.run(
            ["attrib", "-A", "/S", "/D", str(BUILD_DIR / "*")],
            check=False,
            capture_output=True
        )
        subprocess.run(
            ["attrib", "-A", str(BUILD_DIR)],
            check=False,
            capture_output=True
        )
    except Exception as e:
        print(f"Warning: Could not fix build directory attributes: {e}")


def copy_metadata_files(build_type: str):
    """Copy version and changelog files to release directory."""
    print_section("Copying Metadata Files")

    output_dir = TEST_DIR if build_type == "test" else RELEASE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Clean output directory
    for item in output_dir.iterdir():
        if item.is_file():
            item.unlink()

    source_dir = WORKING_DIR / "_kefir"

    # Copy changelog files
    for changelog in source_dir.glob("changelog*"):
        shutil.copy2(changelog, output_dir / changelog.name)
        print(f"Copied: {changelog.name}")

    # Copy version file
    version_file = source_dir / "version"
    if version_file.exists():
        shutil.copy2(version_file, output_dir / "version")
        print(f"Copied: version")

    # Copy to site directories (only for release builds)
    if build_type == "release" and SITE_DIR.exists():
        site_inc = SITE_DIR / "_includes" / "inc" / "kefir"
        site_files = SITE_DIR / "files"

        for target_dir in [site_inc, site_files]:
            if target_dir.exists():
                if version_file.exists():
                    shutil.copy2(version_file, target_dir / "version")

                changelog = source_dir / "changelog"
                if changelog.exists():
                    shutil.copy2(changelog, target_dir / "changelog")

                print(f"Copied to site: {target_dir}")


def create_archive(version: str, build_type: str) -> Path:
    """Create ZIP archive of the build."""
    print_section("Creating Archive")

    if not SEVEN_ZIP.exists():
        print(f"Error: 7-Zip not found at {SEVEN_ZIP}")
        sys.exit(1)

    output_dir = TEST_DIR if build_type == "test" else RELEASE_DIR
    suffix = "_test" if build_type == "test" else ""
    archive_name = f"kefir{version}{suffix}.zip"
    archive_path = output_dir / archive_name

    # Build 7-Zip command
    cmd = [
        str(SEVEN_ZIP),
        "a",  # Add to archive
        "-tzip",  # ZIP format
        "-mx9",  # Maximum compression
        "-r0",  # Recurse subdirectories
        "-ssw",  # Compress files open for writing
    ]

    # Add exclusions
    for pattern in EXCLUDE_PATTERNS:
        cmd.extend(["-xr!" + pattern])

    cmd.append(str(archive_path))
    cmd.append(str(KEFIR_SOURCE / "*"))

    print(f"Creating archive: {archive_name}")
    print(f"Output: {archive_path}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        print(f"\nArchive created successfully: {archive_path}")
        return archive_path
    except subprocess.CalledProcessError as e:
        print(f"Error creating archive: {e}")
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr)
        sys.exit(1)


def git_commit_and_push(version: str, build_type: str):
    """Commit and push changes to git (release only)."""
    if build_type == "test":
        print("\nSkipping git operations for test build.")
        return

    print_section("Git Operations")

    suffix = "_test" if build_type == "test" else ""
    commit_msg = f"kefir{version}{suffix}"

    try:
        print("Adding files to git...")
        subprocess.run(["git", "add", "."], check=True)

        print(f"Creating commit: {commit_msg}")
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)

        print("Pushing to remote...")
        subprocess.run(["git", "push"], check=True)

        print("Git operations completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Git operation failed: {e}")
        print("Continuing anyway...")


def main():
    """Main build process."""
    print_section("Kefir Build Script")

    # Read version
    version = read_version()

    # Prompt for build type
    build_type = prompt_build_type()

    # Update version file in kefir-updater
    print_section("Updating Version File")
    version_source = WORKING_DIR / "_kefir" / "version"
    version_dest = KEFIR_SOURCE / "switch" / "kefir-updater" / "version"
    if version_source.exists() and version_dest.parent.exists():
        shutil.copy2(version_source, version_dest)
        print(f"Updated: {version_dest}")

    # Clean and prepare build directory
    clean_build_dir()

    # Copy files
    copy_kefir_files()

    # Fix attributes
    fix_attributes()

    # Copy metadata
    copy_metadata_files(build_type)

    # Create archive
    archive_path = create_archive(version, build_type)

    # Clean build directory
    if BUILD_DIR.exists():
        print(f"\nCleaning up build directory...")
        shutil.rmtree(BUILD_DIR)

    # Git operations (release only)
    git_commit_and_push(version, build_type)

    # Done
    print_section("Build Complete")
    print(f"Archive: {archive_path}")
    print(f"Build type: {build_type}")
    print(f"Version: {version}")

    # For release builds, mention PowerShell script
    if build_type == "release":
        ps_script = Path("D:/git/scripts/build_kefir.ps1")
        if ps_script.exists():
            print(f"\nNote: Legacy PowerShell script exists at {ps_script}")
            print("Consider running it manually if needed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBuild cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
