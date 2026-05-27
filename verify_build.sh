#!/usr/bin/env bash
# Verify built MathBot.app exists and run self-test if possible
set -euo pipefail

APP="dist/MathBot.app"
BIN="$APP/Contents/MacOS/MathBot"

if [[ ! -d "$APP" ]]; then
  echo "Missing $APP — run ./build.sh first"
  exit 1
fi

echo "=== MathBot build verification ==="
echo "Found: $APP"

if [[ -x "$BIN" ]]; then
  echo "Running self-test via bundled binary…"
  "$BIN" --self-test || {
    echo "Self-test failed (Ollama must be running for full pass)."
    exit 1
  }
else
  echo "Binary not found at $BIN"
  exit 1
fi

echo "Verification complete."
