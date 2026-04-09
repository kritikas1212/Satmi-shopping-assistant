#!/usr/bin/env bash
set -euo pipefail

blocked_file_regex='(^|/)(\.env(\..*)?$|.*-firebase-adminsdk-.*\.json$|.*\.(pem|p12|key)$)'
secret_content_regex='BEGIN[[:space:]]+PRIVATE[[:space:]]+KEY|AIza[0-9A-Za-z_\-]{35}|shpat_[0-9A-Za-z]+'

failed=0

# Read staged file paths and scan the staged content to prevent accidental secret commits.
while IFS= read -r path; do
  if [[ "$path" =~ $blocked_file_regex ]]; then
    echo "[secret-scan] blocked file in commit: $path"
    failed=1
    continue
  fi

  # Skip deleted files.
  if ! git cat-file -e ":$path" 2>/dev/null; then
    continue
  fi

  # Scan staged blob content for common credential patterns.
  if git show ":$path" | grep -E -q "$secret_content_regex"; then
    echo "[secret-scan] possible secret pattern detected in: $path"
    failed=1
  fi
done < <(git diff --cached --name-only)

if [[ "$failed" -ne 0 ]]; then
  cat <<'EOF'
[secret-scan] commit blocked.
Remove secrets from staged files, or move credentials to local env/config files that are gitignored.
EOF
  exit 1
fi

exit 0
