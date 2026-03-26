#!/usr/bin/env python3
"""Download the latest hekate release assets from GitHub releases.

Downloads:
  - hekate_*.zip  -> extract bootloader/ to KEFIR_ROOT_DIR,
                     rename hekate_*.bin inside zip to KEFIR_ROOT_DIR/payload.bin
  - hekate*_ram8GB.bin -> KEF_8GB_DIR/payload.bin
"""

import sys
import os
import io
import zipfile
import urllib.request
import json

GITHUB_API = "https://api.github.com/repos/CTCaer/hekate/releases/latest"


def fetch_release_data():
    print("Fetching latest hekate release info from GitHub...")
    req = urllib.request.Request(GITHUB_API, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    tag = data.get("tag_name", "unknown")
    print(f"Latest release: {tag}")
    return data


def download_zip(assets, kefir_root_dir):
    """Download hekate_*.zip and extract to kefir_root_dir."""
    zip_assets = [
        a for a in assets
        if a["name"].startswith("hekate_") and a["name"].endswith(".zip")
        and "ram8GB" not in a["name"]
    ]
    if not zip_assets:
        print("ERROR: No hekate_*.zip asset found in latest release!", file=sys.stderr)
        sys.exit(1)

    asset = zip_assets[0]
    print(f"Downloading {asset['name']}...")

    with urllib.request.urlopen(asset["browser_download_url"]) as r:
        zip_data = r.read()

    print(f"Extracting to {kefir_root_dir}...")
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        for member in zf.namelist():
            # Extract bootloader/ folder
            if member.startswith("bootloader/"):
                dest_path = os.path.join(kefir_root_dir, member)
                if member.endswith("/"):
                    os.makedirs(dest_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    with zf.open(member) as src, open(dest_path, "wb") as dst:
                        dst.write(src.read())
                    print(f"  extracted: {member}")

            # Rename hekate_*.bin (top-level) to payload.bin
            elif (
                member.startswith("hekate_")
                and member.endswith(".bin")
                and "/" not in member
            ):
                dest_path = os.path.join(kefir_root_dir, "payload.bin")
                with zf.open(member) as src, open(dest_path, "wb") as dst:
                    dst.write(src.read())
                print(f"  extracted: {member} -> payload.bin")

    print("ZIP extraction done.")


def download_ram8gb(assets, dest):
    """Download hekate*_ram8GB.bin to dest."""
    ram_assets = [
        a for a in assets
        if "ram8GB" in a["name"] and a["name"].endswith(".bin")
    ]
    if not ram_assets:
        print(
            "ERROR: No hekate *_ram8GB.bin asset found in latest release!",
            file=sys.stderr,
        )
        sys.exit(1)

    asset = ram_assets[0]
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"Downloading {asset['name']} -> {dest}")
    urllib.request.urlretrieve(asset["browser_download_url"], dest)
    print("ram8GB download done.")


def main():
    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.argv[0]} <kefir_root_dir> <ram8gb_dest>",
            file=sys.stderr,
        )
        print(
            "  kefir_root_dir : KEFIR_ROOT_DIR (zip extracted here)",
            file=sys.stderr,
        )
        print(
            "  ram8gb_dest    : destination path for hekate*_ram8GB.bin (e.g. KEF_8GB_DIR/payload.bin)",
            file=sys.stderr,
        )
        sys.exit(1)

    kefir_root_dir = sys.argv[1]
    ram8gb_dest = sys.argv[2]

    data = fetch_release_data()
    assets = data["assets"]

    download_zip(assets, kefir_root_dir)
    download_ram8gb(assets, ram8gb_dest)

    print("All done.")


if __name__ == "__main__":
    main()
