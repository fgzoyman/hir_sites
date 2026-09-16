#!/usr/bin/env bash
# run_pipeline.sh
# Kényelmi indítószkript a virtuális környezetből

cd "$(dirname "$0")"
.venv/bin/python run_pipeline.py "$@"
