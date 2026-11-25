#!/usr/bin/env bash
# 总装：N 段拼接 → 混音（BGM + 可选 CUES 事件层）→ 钳瞬态 → 两遍响度规整（线性增益）→ 48kHz → 收尾限幅 → 编码前低通 → faststart
# 用法: sh assemble.sh --segs 4 --audio assets/bgm.mp3 --out "out/final.mp4"
#       [--prefix seg] [--title 片名] [SFX=audio/sfx.wav] [SFX_GAIN=0.9] [PRE_LIMIT=0.32] [FINAL_LIMIT=0.5] [ENCODE_LP=19000]
# SFX = gen-sfx.py 出的事件层音效轨（CUES 音画同表，见 audio.md）；混在 BGM 底上。
# v1.8.1 起不再用单遍 loudnorm：它是动态模式，像自动增益，遇到重拍就把前后几秒压下去，
# 编曲里「重拍后那一小节更响」被抹平（实测：配乐里 +2dB，成片 −1dB）。
# 配方与踩过的坑见 audio.md「总装响度配方」；重拍加重这类逐片处理不在这个模板里。
set -euo pipefail
cd "$(dirname "$0")/.."

SEGN=4; AUDIO=""; OUT="out/final.mp4"; PREFIX="seg"; TITLE="final"
SFX="${SFX:-}"; SFX_GAIN="${SFX_GAIN:-0.9}"
PRE_LIMIT="${PRE_LIMIT:-0.32}"       # 钳瞬态天花板。线性成立的条件是「预混真峰值 + 抬升量 ≤ −1.5dBFS」，不够就再调低
FINAL_LIMIT="${FINAL_LIMIT:-0.5}"    # 收尾限幅：−6dBFS
ENCODE_LP="${ENCODE_LP:-19000}"      # 编码前低通：方顶波经 AAC 重建会过冲（实测不加 +2.0dBFS，加了与编码前一致）
LN="loudnorm=I=-15:TP=-1.5:LRA=11"
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

echo "== 预混：配乐（+ 事件层）→ 钳瞬态 =="
if [ -n "$SFX" ]; then
  ffmpeg -y -v error -i out/merged-silent.mp4 -i "$AUDIO" -i "$SFX" \
    -filter_complex "[2:a]volume=${SFX_GAIN}[sx];[1:a][sx]amix=inputs=2:normalize=0,alimiter=limit=${PRE_LIMIT}:attack=1:release=25:level=disabled[a]" \
    -map "[a]" -c:a pcm_s24le out/premix.wav
  SFX_NOTE=" · SFX=$SFX gain=$SFX_GAIN"
else
  ffmpeg -y -v error -i out/merged-silent.mp4 -i "$AUDIO" \
    -filter_complex "[1:a]alimiter=limit=${PRE_LIMIT}:attack=1:release=25:level=disabled[a]" \
    -map "[a]" -c:a pcm_s24le out/premix.wav
  SFX_NOTE=""
fi

echo "== 响度规整：第一遍测量 =="
# 测量结果是一个 JSON 对象，夹在 ffmpeg 的其它日志行中间，只截最外层的那对花括号
MEAS=$(ffmpeg -hide_banner -nostats -i out/premix.wav -af "${LN}:print_format=json" -f null - 2>&1 | sed -n '/^{/,/^}/p')
jget() { printf '%s\n' "$MEAS" | sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1; }
I=$(jget input_i); TP=$(jget input_tp); LRA=$(jget input_lra); TH=$(jget input_thresh); OFF=$(jget target_offset)
for v in "$I" "$TP" "$LRA" "$TH" "$OFF"; do
  [ -n "$v" ] || { echo "fail fast: loudnorm 第一遍没有给出测量结果："; printf '%s\n' "$MEAS"; exit 1; }
done
echo "I ${I} LUFS · 真峰值 ${TP} dBFS · LRA ${LRA} LU · 阈值 ${TH} LUFS"

echo "== 响度规整：第二遍（线性增益）→ 48kHz → 收尾限幅 → 低通 =="
# linear=true 在条件不满足时会静默降级回 dynamic：把模式读出来，不是 Linear 就判失败
SUMMARY=$(ffmpeg -y -v info -nostats -i out/premix.wav \
  -af "${LN}:measured_I=${I}:measured_TP=${TP}:measured_LRA=${LRA}:measured_thresh=${TH}:offset=${OFF}:linear=true:print_format=summary,aresample=48000,alimiter=limit=${FINAL_LIMIT}:attack=1:release=25:level=disabled,lowpass=f=${ENCODE_LP}" \
  -c:a pcm_s24le out/mix.wav 2>&1)
TYPE=$(printf '%s\n' "$SUMMARY" | sed -n 's/.*Normalization Type:[[:space:]]*//p' | tr -d '[:space:]')
[ "$TYPE" = "Linear" ] || { echo "fail fast: 响度规整没有走线性模式（读到：${TYPE:-未知}），动态会被压平——把 PRE_LIMIT 调低后重跑"; exit 1; }
echo "线性（动态保住了）"

ffmpeg -y -v error -i out/merged-silent.mp4 -i out/mix.wav \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart -shortest "$OUT"

ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$OUT"
echo "OK $OUT ($TITLE) · PRE_LIMIT=$PRE_LIMIT FINAL_LIMIT=$FINAL_LIMIT LP=${ENCODE_LP}Hz$SFX_NOTE"
echo "下一步：对成片跑 check-audio.py（响度 / 真峰值 / drop 呼吸），WARN 要解释或修复"
