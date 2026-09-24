#!/usr/bin/env bash
# Secret-guard pre-commit hook for ai-agent-observability-aws.
#
# Blocks a commit if any STAGED change looks like a real credential or a real
# AWS account identifier. This repo is public and ships a demo, so the only
# secrets that should ever appear are documented placeholders. This hook is the
# safety net behind that promise.
#
# Install once per clone:   bash scripts/install-hooks.sh
# Bypass in a true emergency: git commit --no-verify   (avoid this)

set -euo pipefail

# Only scan what is actually staged (added/copied/modified), text diff only.
staged="$(git diff --cached --name-only --diff-filter=ACM)"
[ -z "$staged" ] && exit 0

fail=0
report() { echo "  ✗ $1"; fail=1; }

echo "🔒 secret-guard: scanning staged changes…"

# Grep the staged patch (added lines only: lines starting with '+').
added="$(git diff --cached --diff-filter=ACM -U0 | grep '^+' | grep -v '^+++' || true)"

# 1. AWS long-term / temporary access keys.
if echo "$added" | grep -Eq 'A(KIA|SIA)[A-Z0-9]{16}'; then
  report "AWS access key (AKIA/ASIA…) detected in staged changes."
fi

# 2. AWS secret access key assignment (40-char base64-ish after the key name).
if echo "$added" | grep -Eiq 'aws_secret_access_key\s*[=:]\s*[A-Za-z0-9/+]{40}'; then
  report "AWS secret access key value detected."
fi

# 3. Private keys.
if echo "$added" | grep -Eq -- '-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----'; then
  report "Private key block detected."
fi

# 4. A real Traccia API key (anything after the '=' that is NOT the placeholder
#    and is not commented out).
if echo "$added" | grep -Eq '^\+[^#]*TRACCIA_API_KEY\s*=\s*[A-Za-z0-9._-]{12,}' \
   && ! echo "$added" | grep -Eq 'your_traccia_api_key_here'; then
  report "A non-placeholder TRACCIA_API_KEY value looks committed."
fi

# 5. Generic high-entropy secret assignments (token/secret/password = long value).
if echo "$added" | grep -Eiq '(secret|password|passwd|api[_-]?key|token)\s*[=:]\s*["'"'"']?[A-Za-z0-9._/+-]{20,}' \
   && ! echo "$added" | grep -Eiq 'your_traccia_api_key_here|example|placeholder|xxxx|<[a-z_]+>'; then
  report "A generic secret-like assignment with a long value was found. Review it."
fi

# 6. A real 12-digit AWS account id (block, but allow the documented example ids).
#    (?<![0-9]) style boundaries via grep -oE then filter; timestamps are 19 digits so
#    they won't match a clean 12-digit boundary here.)
if echo "$added" | grep -oE '\b[0-9]{12}\b' | grep -vqE '111122223333|123456789012|000000000000'; then
  report "A 12-digit value that could be a real AWS account id was found (allowed examples: 111122223333, 123456789012)."
fi

# 7. The repo ships a .env with keys COMMENTED OUT (one true filename, no .env.example).
#    Allow committing .env ONLY if it carries no real (uncommented) key; still block
#    machine-local .env.local / .env.*.local entirely.
if echo "$staged" | grep -qxE '\.env\.local|\.env\..*\.local'; then
  report "A machine-local .env.local file is staged. Never commit it."
fi
if echo "$staged" | grep -qxE '\.env'; then
  # Inspect the staged .env content: an UNCOMMENTED TRACCIA_API_KEY / TRACCIA_ENDPOINT
  # with a non-placeholder value is a real secret -> block. Commented (#...) lines are fine.
  env_added="$(git diff --cached -- .env | grep -E '^\+' | grep -vE '^\+\+\+')"
  if echo "$env_added" | grep -qE '^\+[[:space:]]*TRACCIA_API_KEY=.+' \
     && ! echo "$env_added" | grep -qiE 'your_traccia_api_key_here|example|placeholder'; then
    report "The staged .env contains a REAL (uncommented) TRACCIA_API_KEY. Comment it out before committing."
  fi
fi

if [ "$fail" -ne 0 ]; then
  echo ""
  echo "❌ commit blocked by secret-guard. Remove the flagged content and re-commit."
  echo "   If this is a false positive, review carefully, then: git commit --no-verify"
  exit 1
fi

echo "✅ secret-guard: no secrets detected."
exit 0
