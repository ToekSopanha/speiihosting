#!/bin/sh
set -eu

# Run from a checkout: sh scripts/install.sh [package-or-checkout]
# Dependencies go into a private venv; never modify a system Python environment.
speii_python=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3,10))'; then
    speii_python="$candidate"
    break
  fi
done
if [ -z "$speii_python" ]; then
  if command -v brew >/dev/null 2>&1; then
    brew install python
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip
  else
    echo 'Install Python 3.10+ and rerun this installer.' >&2
    exit 1
  fi
  speii_python=python3
fi
speii_source="${1:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
speii_home="${SPEIIHOSTING_HOME:-$HOME/.speiihosting}"
speii_environment="$speii_home/cli-venv"
speii_bin="${SPEIIHOSTING_BIN:-$HOME/.local/bin}"
"$speii_python" -m venv "$speii_environment"
"$speii_environment/bin/python" -m pip install --upgrade "$speii_source"
mkdir -p "$speii_bin"
ln -sf "$speii_environment/bin/speiihos" "$speii_bin/speiihos"
ln -sf "$speii_environment/bin/speiihosting" "$speii_bin/speiihosting"
printf 'Installed. Add %s to PATH, then run speiihos init.\n' "$speii_bin"
