#!/usr/bin/env bash
# Lanza el reproductor FLAC.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 main.py "$@"
