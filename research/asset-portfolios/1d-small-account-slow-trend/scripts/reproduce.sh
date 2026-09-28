#!/usr/bin/env sh
set -eu
sast_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"${SAST_PYTHON:-python3}" "$sast_dir/run_research.py"
"${SAST_PYTHON:-python3}" "$sast_dir/supplementary_audit.py"
