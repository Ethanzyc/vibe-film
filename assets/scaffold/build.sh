#!/usr/bin/env bash
# 段级构建：frames → mp4（无声，音频总装统一加）。用法: sh build.sh <工程目录>
set -euo pipefail
d="${1:?usage: build.sh <dir>}"
FPS=30; CRF=18
ffmpeg -y -v error -framerate $FPS -i "$d/frames/f%05d.png" \
  -c:v libx264 -crf $CRF -pix_fmt yuv420p "$d/out/seg-silent.mp4"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 "$d/out/seg-silent.mp4"
