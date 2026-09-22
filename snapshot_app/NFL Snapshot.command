#!/bin/zsh
set -eu
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ -x /opt/homebrew/bin/python3 ]]; then
  PYTHON=/opt/homebrew/bin/python3
elif [[ -x /usr/local/bin/python3 ]]; then
  PYTHON=/usr/local/bin/python3
else
  echo "Python 3 was not found. Install Python 3 and try again."
  read -k 1 '?Press any key to close.'
  exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/nfl_snapshot_app.py"
