#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/nesus-ai"

mkdir -p "$BIN_DIR" "$CONFIG_DIR"
install -m 0755 "$SOURCE_DIR/nesus_ai.py" "$BIN_DIR/nesus_ai"
ln -sfn "$BIN_DIR/nesus_ai" "$BIN_DIR/nesus-ai"

if [[ ! -f "$CONFIG_DIR/config.toml" ]]; then
  install -m 0600 "$SOURCE_DIR/config.example.toml" "$CONFIG_DIR/config.toml"
  echo "Configuration créée: $CONFIG_DIR/config.toml"
else
  echo "Configuration conservée: $CONFIG_DIR/config.toml"
  if ! grep -q 'providers\.codex\.models' "$CONFIG_DIR/config.toml" 2>/dev/null; then
    echo "Note: ancienne configuration détectée. Pour installer le routage multi-modèles et les payload guards:"
    echo "  nesus_ai init --force"
  fi
fi

if [[ ! -f "$CONFIG_DIR/secrets.env" ]]; then
  install -m 0600 "$SOURCE_DIR/secrets.example.env" "$CONFIG_DIR/secrets.env"
  echo "Fichier de secrets créé: $CONFIG_DIR/secrets.env"
else
  chmod 600 "$CONFIG_DIR/secrets.env"
  echo "Fichier de secrets conservé: $CONFIG_DIR/secrets.env"
fi

case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *)
    echo
    echo "Ajoute ceci à ~/.bashrc ou ~/.zshrc :"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
    ;;
esac

echo
echo "1. Renseigne les 7 clés puis adapte les identifiants de modèles si nécessaire dans: $CONFIG_DIR/secrets.env"
echo "2. Vérifie avec: nesus_ai doctor --probe"
echo "3. Mode local strict actif: git push et le CLI gh sont bloqués dans les agents."
