#!/usr/bin/env bash
# 总装：N 段拼接 → 混音（BGM + 可选 CUES 事件层）→ 响度规整 → faststart
# 用法: sh assemble.sh --segs 4 --audio assets/bgm.mp3 --out "out/final.mp4"
#       [--prefix seg] [--title 片名] [SFX=audio/sfx.wav] [SFX_GAIN=0.9]
# SFX = gen-sfx.py 出的事件层音效轨（CUES 音画同表，见 audio.md）；混在 BGM 底上。
# impact 瞬态片的响度配方（两级 alimiter + loudnorm）见 audio.md「总装响度配方」——
# 本模板是基础链路，瞬态片按那个配方替换 -af。
set -euo pipefail
cd "$(dirname "$0")/.."

SEGN=4; AUDIO=""; OUT="out/final.mp4"; PREFIX="seg"; TITLE="final"
SFX="${SFX:-}"; SFX_GAIN="${SFX_GAIN:-0.9}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --segs) SEGN="$2"; shift 2;;
    --audio) AUDIO="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --prefix) PREFIX="$2"; shift 2;;
    --title) TITLE="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 1;;
  esac
done
[ -f "$AUDIO" ] || { echo "fail fast: audio not found: $AUDIO"; exit 1; }
[ -z "$SFX" ] || [ -f "$SFX" ] || { echo "fail fast: SFX not found: $SFX"; exit 1; }
mkdir -p "$(dirname "$OUT")"

echo "== 段规格检查（帧数必须严格相等，否则 -c copy 会错位） =="
LIST=$(mktemp)
for i in $(seq 1 "$SEGN"); do
  f="${PREFIX}${i}/out/${PREFIX}${i}-silent.mp4"
  [ -f "$f" ] || { echo "fail fast: missing $f"; exit 1; }
  ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$f"
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$f"
  echo "file '$PWD/$f'" >> "$LIST"
done

ffmpeg -y -v error -f concat -safe 0 -i "$LIST" -c copy out/merged-silent.mp4
if [ -n "$SFX" ]; then
  ffmpeg -y -v error -i out/merged-silent.mp4 -i "$AUDIO" -i "$SFX" \
    -filter_complex "[2:a]volume=${SFX_GAIN}[sx];[1:a][sx]amix=inputs=2:normalize=0,loudnorm=I=-15:TP=-1.5:LRA=11[a]" \
    -map 0:v:0 -map "[a]" -c:v copy -c:a aac -b:a 192k \
    -movflags +faststart -shortest "$OUT"
  SFX_NOTE=" · SFX=$SFX gain=$SFX_GAIN"
else
  ffmpeg -y -v error -i out/merged-silent.mp4 -i "$AUDIO" \
    -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k \
    -af "loudnorm=I=-15:TP=-1.5:LRA=11" \
    -movflags +faststart -shortest "$OUT"
  SFX_NOTE=""
fi

ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$OUT"
echo "OK $OUT ($TITLE)$SFX_NOTE"
