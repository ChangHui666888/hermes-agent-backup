#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==== DEBUG ===="
echo "SCRIPT_DIR=$SCRIPT_DIR"
echo "HOME=$HOME"
echo "PWD=$(pwd)"

which python
python --version


echo "Running..."

python "$SCRIPT_DIR/news-pipeline.py"

echo "EXIT=$?"