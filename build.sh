#!/usr/bin/env bash
# Build MathBot.app with PyInstaller (macOS)
set -euo pipefail

echo "=== MathBot PyInstaller Build ==="

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: build.sh is intended for macOS only."
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Run ./setup.sh first to create .venv"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q pyinstaller>=6.3.0
pip install -q -r requirements.txt

rm -rf build dist

if [[ -f MathBot.spec ]]; then
  pyinstaller MathBot.spec
else
  echo "MathBot.spec not found"
  exit 1
fi

APP_RESOURCES="dist/MathBot.app/Contents/Resources"
mkdir -p "$APP_RESOURCES"
cp -f config.json.default "$APP_RESOURCES/config.json.default"

echo ""
echo "Built: dist/MathBot.app — zip this folder to distribute"
echo "Run ./verify_build.sh before releasing"
