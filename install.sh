#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/nesus-ai"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: python3 is required." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import tomllib' >/dev/null 2>&1; then
  if ! "$PYTHON_BIN" -c 'import tomli' >/dev/null 2>&1; then
    echo "Python < 3.11 detected: installing tiny TOML compatibility package (tomli)..."
    if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
      echo "Error: pip is missing. Install python3-pip, then rerun ./install.sh" >&2
      exit 1
    fi
    "$PYTHON_BIN" -m pip install --user --quiet tomli
  fi
fi

mkdir -p "$BIN_DIR" "$CONFIG_DIR"
install -m 0755 "$SOURCE_DIR/nesus_ai.py" "$BIN_DIR/nesus_ai"
ln -sfn "$BIN_DIR/nesus_ai" "$BIN_DIR/nesus-ai"
install -m 0755 "$SOURCE_DIR/launch.py" "$BIN_DIR/nesus-ai-launch"
install -m 0755 "$SOURCE_DIR/stop.py" "$BIN_DIR/nesus-ai-stop"
install -m 0755 "$SOURCE_DIR/update_from_repo.sh" "$BIN_DIR/nesus-ai-update"
[[ -f "$CONFIG_DIR/config.toml" ]] || install -m 0600 "$SOURCE_DIR/config.example.toml" "$CONFIG_DIR/config.toml"
[[ -f "$CONFIG_DIR/secrets.env" ]] || install -m 0600 "$SOURCE_DIR/secrets.example.env" "$CONFIG_DIR/secrets.env"
[[ -f "$CONFIG_DIR/instructions.md" ]] || install -m 0600 "$SOURCE_DIR/instructions.md" "$CONFIG_DIR/instructions.md"
chmod 600 "$CONFIG_DIR/secrets.env" "$CONFIG_DIR/config.toml" "$CONFIG_DIR/instructions.md"
echo "Installed. Configure keys in: $CONFIG_DIR/secrets.env"
echo "Then run: nesus_ai doctor"
echo "Add Google/proxy: nesus_ai add-provider"
echo "Future updates: nesus-ai-update"
