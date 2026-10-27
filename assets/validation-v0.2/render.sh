#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Unaltered actual Lab screenshots; no physical experiment footage is implied.
ffmpeg -n -hide_banner -f concat -safe 0 -i timeline.txt -t 20 \
  -vf 'fps=30,format=yuv420p' -c:v libx264 -crf 20 -preset medium \
  -movflags +faststart "${1:-instrumentzero-validation-demo.mp4}"
