#!/usr/bin/env python3
"""
Setup Git credentials using GitHub token from .env
Configures git to use token for HTTPS authentication.
"""

import os
import sys
import subprocess
from pathlib import Path


def load_env():
    """Load .env file."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        print(f"Error: .env not found at {env_file}")
        sys.exit(1)

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ[key.strip()] = val.strip().strip("\"'")


def setup_git_credentials():
    """Configure git to use GitHub token for authentication."""
    token = os.environ.get("GITHUB_TOKEN")
    owner = os.environ.get("RELEASE_REPO_OWNER", "rashevskyv")
    repo = os.environ.get("RELEASE_REPO_NAME", "kefir")

    if not token:
        print("Error: GITHUB_TOKEN not found in .env")
        sys.exit(1)

    print("Setting up Git credentials...")

    # Configure git credential helper to use store
    subprocess.run(["git", "config", "--global", "credential.helper", "store"], check=True)

    # Create credentials file
    home = Path.home()
    git_credentials = home / ".git-credentials"

    # Read existing credentials
    existing_lines = []
    if git_credentials.exists():
        existing_lines = git_credentials.read_text(encoding="utf-8").splitlines()

    # Remove old github.com entries
    new_lines = [line for line in existing_lines if "github.com" not in line]

    # Add new GitHub credential
    new_lines.append(f"https://{owner}:{token}@github.com")

    # Write back
    git_credentials.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    git_credentials.chmod(0o600)  # Secure permissions

    print(f"✓ Git credentials configured for {owner}@github.com")
    print(f"✓ Credentials stored in {git_credentials}")
    print("\nYou can now push/pull without entering password!")


def main():
    load_env()
    setup_git_credentials()


if __name__ == "__main__":
    main()
