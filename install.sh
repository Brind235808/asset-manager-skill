#!/usr/bin/env bash
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="${1:-/d/ASSETS}"
SYSTEM="$LIB/_SYSTEM"

echo "Installing asset-manager into $LIB"
mkdir -p "$SYSTEM/logs" "$SYSTEM/thumbs" "$SYSTEM/backups"
cp "$SKILL_ROOT"/scripts/*.py "$SYSTEM/"
cp "$SKILL_ROOT"/scripts/requirements.txt "$SYSTEM/"

if [ ! -f "$SYSTEM/config.json" ]; then
  cp "$SKILL_ROOT/config/config.example.json" "$SYSTEM/config.json"
  echo "Created config: $SYSTEM/config.json"
else
  echo "Keeping existing config: $SYSTEM/config.json"
fi

python "$SYSTEM/assets.py" init

echo
echo "Installed. Next:"
echo "  python \"$SYSTEM/assets.py\" analyze \"<path>\""
echo "  python \"$SYSTEM/assets.py\" ingest \"<path>\" --apply"
echo "  python -m pip install -r \"$SYSTEM/requirements.txt\""
