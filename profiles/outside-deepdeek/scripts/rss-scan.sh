#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/bin:$PATH"
python "$SCRIPT_DIR/rss-scanner.py" 2>&1