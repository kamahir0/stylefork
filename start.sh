#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m stylekit --workspace "${1:-$PWD/workspace}" serve
