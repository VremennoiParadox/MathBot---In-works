#!/usr/bin/env bash
# MathBot development setup (macOS 13+, Python 3.11+)
set -euo pipefail

echo "=== MathBot Setup (macOS) ==="

OS_VER=$(sw_vers -productVersion)
MAJOR=$(echo "$OS_VER" | cut -d. -f1)
if [[ "$MAJOR" -lt 13 ]]; then
  echo "ERROR: macOS 13+ required. Found: $OS_VER"
  exit 1
fi
echo "macOS $OS_VER OK"

if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install: brew install python@3.12"
  exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python $PY_VER OK"

if ! command -v ollama &>/dev/null; then
  echo "Ollama not found. Install from https://ollama.com"
  exit 1
fi
echo "Ollama: $(which ollama)"

if ! curl -sf http://localhost:11434/ &>/dev/null; then
  echo "Starting ollama serve in background…"
  ollama serve &
  sleep 3
fi

cat <<'EOF'

Recommended models (pull manually):
  ollama pull moondream:v2
  ollama pull qwen2.5:7b
  ollama pull qwen2.5vl:7b

EOF

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

python3 -c "from memory import MemoryStore; MemoryStore()"
echo "Database schema OK."

echo ""
echo "Run MathBot:"
echo "  source .venv/bin/activate && python main.py"
echo ""
echo "Permissions: Screen Recording + Accessibility for Terminal."
echo "Templates: see templates/README.md"
echo "=== Setup complete ==="
