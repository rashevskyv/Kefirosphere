#!/usr/bin/env python3
"""Download the latest hekate *_ram8GB.bin from GitHub releases."""

import sys
import os
import urllib.request
import json

GITHUB_API = "https://api.github.com/repos/CTCaer/hekate/releases/latest"


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <destination_path>", file=sys.stderr)
        sys.exit(1)

    dest = sys.argv[1]

    print(f"Fetching latest hekate release info from GitHub...")
    req = urllib.request.Request(GITHUB_API, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        data = json.load(r)

    tag = data.get("tag_name", "unknown")
    print(f"Latest release: {tag}")

    assets = [
        a for a in data["assets"]
        if "ram8GB" in a["name"] and a["name"].endswith(".bin")
    ]

    if not assets:
        print(
            "ERROR: No hekate *_ram8GB.bin asset found in latest release!",
            file=sys.stderr,
        )
        sys.exit(1)

    asset = assets[0]
    print(f"Downloading {asset['name']} -> {dest}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    urllib.request.urlretrieve(asset["browser_download_url"], dest)
    print("Done.")


if __name__ == "__main__":
    main()
