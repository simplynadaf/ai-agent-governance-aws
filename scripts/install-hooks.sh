#!/usr/bin/env bash
# Install the repo's git hooks. Git does not clone hooks, so each contributor
# runs this once after cloning.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
src="$root/scripts/pre-commit-secrets.sh"
dest="$root/.git/hooks/pre-commit"

chmod +x "$src"
cp "$src" "$dest"
chmod +x "$dest"
echo "✅ Installed pre-commit secret-guard -> $dest"
echo "   It runs automatically on every 'git commit'."
