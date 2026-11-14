#!/bin/sh
set -eu
if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  echo 'Usage: sh start.sh /path/to/creation-project' >&2
  exit 2
fi
kit_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -B "$kit_dir/run.py" --workspace "$1" init
exec python3 -B "$kit_dir/run.py" --workspace "$1" serve
