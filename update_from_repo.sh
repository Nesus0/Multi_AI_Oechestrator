#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/nesus-ai"
BACKUP_ROOT="${HOME}/.local/state/nesus-ai/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/${STAMP}"

cd "$REPO_DIR"

if ! command -v git >/dev/null 2>&1; then
  echo "Error: git is required." >&2
  exit 1
fi

if [[ ! -d .git ]]; then
  echo "Error: $REPO_DIR is not a Git repository." >&2
  exit 1
fi

REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "$REMOTE_URL" ]]; then
  echo "Error: origin remote is missing." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
if [[ -d "$CONFIG_DIR" ]]; then
  cp -a "$CONFIG_DIR" "$BACKUP_DIR/config"
  echo "Local configuration backed up to: $BACKUP_DIR/config"
fi

CURRENT_BRANCH="$(git symbolic-ref --short -q HEAD || true)"
echo "Repository: $REPO_DIR"
echo "Origin: $REMOTE_URL"
echo "Current branch: ${CURRENT_BRANCH:-detached}"
echo "Fetching latest origin/main..."

git fetch --prune origin main

echo "Forcing local repository to origin/main..."
git checkout -f -B main origin/main
git reset --hard origin/main
git clean -fd

chmod +x install.sh uninstall.sh launch.py stop.py nesus_ai.py update_from_repo.sh

./install.sh

rm -f "$CONFIG_DIR/models-cache.json"

printf '\nUpdate complete.\n'
printf 'Commit: %s\n' "$(git rev-parse --short HEAD)"
printf 'Run: nesus_ai doctor\n'
printf 'Models: nesus_ai models --refresh\n'
