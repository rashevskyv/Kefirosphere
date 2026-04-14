#!/usr/bin/env bash
# Kefirosphere Build Launcher
# Run this script from WSL to build all Kefirosphere variants.
# Usage: bash build.sh [--help]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file not found at $ENV_FILE" >&2
    echo "Please copy .env and fill in your machine-specific paths." >&2
    exit 1
fi

# Source .env, stripping Windows carriage returns (\r) if present
set -a
# shellcheck disable=SC1090
source <(sed 's/\r//' "$ENV_FILE")
set +a

# ---------------------------------------------------------------------------
# Export KEFIROSPHERE_DIR so build.py and Makefile can use it
# ---------------------------------------------------------------------------

export KEFIROSPHERE_DIR="$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Validate critical variables early
# ---------------------------------------------------------------------------

errors=0
for var in KEFIR_ROOT_DIR SPLASH_LOGO_PATH SPLASH_BMP_PATH; do
    if [[ -z "${!var:-}" ]]; then
        echo "ERROR: '$var' is not set in .env" >&2
        errors=$((errors + 1))
    fi
done
if [[ $errors -gt 0 ]]; then
    echo "Please fix your .env file and retry." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Run the Python build script
# ---------------------------------------------------------------------------

echo "============================================================"
echo " Kefirosphere Build — $(date '+%Y-%m-%d %H:%M:%S')"
echo " KEFIROSPHERE_DIR : $KEFIROSPHERE_DIR"
echo " KEFIR_ROOT_DIR   : $KEFIR_ROOT_DIR"
echo " SPLASH_LOGO_PATH : $SPLASH_LOGO_PATH"
echo " SPLASH_BMP_PATH  : $SPLASH_BMP_PATH"
echo "============================================================"

python3 "$SCRIPT_DIR/build.py" "$@"
