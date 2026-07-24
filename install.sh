#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/nesus-ai"
CONFIG_FILE="${CONFIG_DIR}/config.toml"
SECRETS_FILE="${CONFIG_DIR}/secrets.env"
INSTRUCTIONS_FILE="${CONFIG_DIR}/instructions.md"
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
[[ -f "$INSTRUCTIONS_FILE" ]] || install -m 0600 "$SOURCE_DIR/instructions.md" "$INSTRUCTIONS_FILE"

ask() {
  local prompt="$1" default="${2:-}" value
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " value
    printf '%s' "${value:-$default}"
  else
    read -r -p "$prompt: " value
    printf '%s' "$value"
  fi
}

ask_secret() {
  local prompt="$1" value
  read -r -s -p "$prompt: " value
  printf '\n' >&2
  printf '%s' "$value"
}

slugify() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_-]+/_/g; s/^_+|_+$//g'
}

upper_env() {
  printf '%s' "$1" | tr '[:lower:]-' '[:upper:]_' | sed -E 's/[^A-Z0-9_]+/_/g'
}

write_setup() {
  local tmp_config tmp_secrets provider_count=0 add_more="y"
  local -a provider_names=()
  tmp_config="$(mktemp)"
  tmp_secrets="$(mktemp)"
  trap 'rm -f "$tmp_config" "$tmp_secrets"' RETURN

  cat >"$tmp_config" <<'EOF'
[general]
provider_order = [__PROVIDER_ORDER__]
timeout_seconds = 90
max_attempts = 16
max_models_per_provider = 3
max_prompt_chars = 24000
models_cache_seconds = 600
EOF

  cat >"$tmp_secrets" <<'EOF'
# Generated locally by install.sh. Never commit this file.
# chmod 600 ~/.config/nesus-ai/secrets.env
EOF

  echo
  echo "Configure at least two API accesses. You can add unlimited keys/providers."
  echo "Known direct providers: Groq, Cerebras, OpenRouter, Google Gemini, OpenAI, Anthropic Claude."

  while [[ "$provider_count" -lt 2 || "$add_more" =~ ^([yY]|yes|oui|o)$ ]]; do
    echo
    echo "Access $((provider_count + 1))"
    echo "  1) Groq direct"
    echo "  2) Cerebras direct"
    echo "  3) OpenRouter direct"
    echo "  4) Google Gemini direct (fixed gemini-3.5-flash-lite)"
    echo "  5) OpenAI direct"
    echo "  6) Anthropic Claude direct"
    echo "  7) OpenAI-compatible proxy"
    echo "  8) Claude-compatible proxy"

    local choice label base protocol model auth auth_header key env_name instance default_name
    choice="$(ask 'Provider choice' '1')"
    auth_header=""

    case "$choice" in
      1) label="groq"; base="https://api.groq.com/openai/v1"; protocol="openai"; model="auto"; auth="bearer" ;;
      2) label="cerebras"; base="https://api.cerebras.ai/v1"; protocol="openai"; model="auto"; auth="bearer" ;;
      3) label="openrouter"; base="https://openrouter.ai/api/v1"; protocol="openai"; model="auto"; auth="bearer" ;;
      4) label="google"; base="https://generativelanguage.googleapis.com/v1beta/openai"; protocol="openai"; model="gemini-3.5-flash-lite"; auth="bearer" ;;
      5) label="openai"; base="https://api.openai.com/v1"; protocol="openai"; model="auto"; auth="bearer" ;;
      6) label="anthropic"; base="https://api.anthropic.com"; protocol="anthropic"; model="auto"; auth="header"; auth_header="x-api-key" ;;
      7)
        label="$(ask 'Proxy name' 'openai_proxy')"
        base="$(ask 'Proxy base URL')"
        protocol="openai"; model="auto"; auth="bearer"
        ;;
      8)
        label="$(ask 'Proxy name' 'claude_proxy')"
        base="$(ask 'Proxy base URL')"
        protocol="anthropic"; model="auto"; auth="header"; auth_header="x-api-key"
        ;;
      *) echo "Invalid choice." >&2; continue ;;
    esac

    default_name="$(slugify "$label")_$((provider_count + 1))"
    instance="$(slugify "$(ask 'Access name' "$default_name")")"
    if [[ -z "$instance" ]]; then
      echo "Invalid access name." >&2
      continue
    fi
    if printf '%s\n' "${provider_names[@]:-}" | grep -Fxq "$instance"; then
      echo "Access name already exists: $instance" >&2
      continue
    fi

    if [[ "$choice" == "7" || "$choice" == "8" ]]; then
      model="$(ask 'Fixed model, or auto discovery' 'auto')"
    fi

    env_name="$(upper_env "$instance")_API_KEY"
    key="$(ask_secret "API key for $instance")"
    if [[ -z "$key" ]]; then
      echo "API key cannot be empty." >&2
      continue
    fi

    provider_names+=("$instance")
    provider_count=$((provider_count + 1))

    {
      echo
      echo "[providers.$instance]"
      echo "enabled = true"
      printf 'protocol = "%s"\n' "$protocol"
      printf 'base_url = "%s"\n' "${base%/}"
      printf 'model = "%s"\n' "$model"
      printf 'auth = "%s"\n' "$auth"
      printf 'key_env = "%s"\n' "$env_name"
      [[ -n "$auth_header" ]] && printf 'auth_header = "%s"\n' "$auth_header"
      [[ "$label" == "openrouter" ]] && echo 'headers = { X-OpenRouter-Title = "nesus_ai" }'
    } >>"$tmp_config"
    printf '%s=%q\n' "$env_name" "$key" >>"$tmp_secrets"

    if [[ "$provider_count" -ge 2 ]]; then
      add_more="$(ask 'Add another API access? y/N' 'n')"
    else
      echo "At least $((2 - provider_count)) more API access is required."
      add_more="y"
    fi
  done

  local order="" name
  for name in "${provider_names[@]}"; do
    [[ -n "$order" ]] && order+=", "
    order+="\"$name\""
  done
  sed -i "s/__PROVIDER_ORDER__/$order/" "$tmp_config"

  if [[ -f "$CONFIG_FILE" ]]; then
    cp -a "$CONFIG_FILE" "$CONFIG_FILE.backup-$(date +%Y%m%d-%H%M%S)"
  fi
  if [[ -f "$SECRETS_FILE" ]]; then
    cp -a "$SECRETS_FILE" "$SECRETS_FILE.backup-$(date +%Y%m%d-%H%M%S)"
  fi
  install -m 0600 "$tmp_config" "$CONFIG_FILE"
  install -m 0600 "$tmp_secrets" "$SECRETS_FILE"
  echo "Configured $provider_count API accesses."
}

configure="y"
if [[ -s "$CONFIG_FILE" && -s "$SECRETS_FILE" ]]; then
  if [[ -t 0 ]]; then
    configure="$(ask 'Existing API configuration found. Keep it? Y/n' 'y')"
    if [[ "$configure" =~ ^([yY]|yes|oui|o)$ ]]; then
      configure="n"
    else
      configure="y"
    fi
  else
    configure="n"
  fi
fi

if [[ "$configure" == "y" ]]; then
  if [[ ! -t 0 ]]; then
    echo "Error: first installation requires an interactive terminal to configure at least two API accesses." >&2
    exit 1
  fi
  write_setup
else
  echo "Keeping existing API configuration."
fi

chmod 600 "$SECRETS_FILE" "$CONFIG_FILE" "$INSTRUCTIONS_FILE"
rm -f "$CONFIG_DIR/models-cache.json"

echo
echo "Installation complete."
echo "Config: $CONFIG_FILE"
echo "Secrets: $SECRETS_FILE"
echo "Add more providers later: nesus_ai add-provider"
echo "Future updates: nesus-ai-update"
echo
"$BIN_DIR/nesus_ai" doctor || true
