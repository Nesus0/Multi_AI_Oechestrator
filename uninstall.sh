#!/usr/bin/env bash
set -euo pipefail

"$HOME/.local/bin/nesus-ai-stop" --timeout 5 >/dev/null 2>&1 || true
rm -f \
  "$HOME/.local/bin/nesus_ai" \
  "$HOME/.local/bin/nesus-ai" \
  "$HOME/.local/bin/nesus-ai-launch" \
  "$HOME/.local/bin/nesus-ai-stop"

echo "Binaires supprimés. Configuration, modèles et journaux conservés."
