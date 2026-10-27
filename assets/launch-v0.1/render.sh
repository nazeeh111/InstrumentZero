#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Native brag route. Unmodified screenshots of actual current-source UI states.
# Refuse replacement: choose a new output argument when revising a valid render.
ffmpeg -n -hide_banner -f concat -safe 0 -i timeline.txt -t 20 -r 30 \
  -vf 'scale=1280:720:flags=lanczos,format=yuv420p' \
  -c:v libx264 -crf 20 -preset medium -movflags +faststart \
  "${1:-instrumentzero-demo.mp4}"
