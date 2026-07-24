#!/usr/bin/env bash
set -euo pipefail
rm -f \
  "$HOME/.local/bin/nesus_ai" \
  "$HOME/.local/bin/nesus-ai" \
  "$HOME/.local/bin/nesus-ai-launch" \
  "$HOME/.local/bin/nesus-ai-stop"
echo "Binaries removed. Configuration and secrets preserved."
