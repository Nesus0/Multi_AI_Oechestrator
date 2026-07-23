#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/nesus-ai"

mkdir -p "$BIN_DIR" "$CONFIG_DIR"
install -m 0755 "$SOURCE_DIR/nesus_ai.py" "$BIN_DIR/nesus_ai"
ln -sfn "$BIN_DIR/nesus_ai" "$BIN_DIR/nesus-ai"
install -m 0755 "$SOURCE_DIR/launch.py" "$BIN_DIR/nesus-ai-launch"
install -m 0755 "$SOURCE_DIR/stop.py" "$BIN_DIR/nesus-ai-stop"
install -m 0755 "$SOURCE_DIR/manager.py" "$BIN_DIR/nesus-ai-manager"
install -m 0644 "$SOURCE_DIR/instructions.md" "$CONFIG_DIR/instructions.md"

if [[ ! -f "$CONFIG_DIR/config.toml" ]]; then
  install -m 0600 "$SOURCE_DIR/config.example.toml" "$CONFIG_DIR/config.toml"
else
  echo "Configuration conservée: $CONFIG_DIR/config.toml"
fi

if [[ ! -f "$CONFIG_DIR/secrets.env" ]]; then
  install -m 0600 "$SOURCE_DIR/secrets.example.env" "$CONFIG_DIR/secrets.env"
else
  chmod 600 "$CONFIG_DIR/secrets.env"
fi

if [[ ! -f "$CONFIG_DIR/local.env" ]]; then
  install -m 0600 "$SOURCE_DIR/local.example.env" "$CONFIG_DIR/local.env"
  echo "Configuration manager créée: $CONFIG_DIR/local.env"
else
  chmod 600 "$CONFIG_DIR/local.env"
  echo "Configuration manager conservée: $CONFIG_DIR/local.env"
fi

case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *) echo 'Ajoute: export PATH="$HOME/.local/bin:$PATH"' ;;
esac

echo "Instructions permanentes: $CONFIG_DIR/instructions.md"
echo "Configure les health/recovery commands dans: $CONFIG_DIR/local.env"
echo "Démarrer: nesus-ai-launch"
echo "Statut:    nesus-ai-launch --status"
echo "Arrêter:   nesus-ai-stop"
