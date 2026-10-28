#!/usr/bin/env python3
"""Parameterized ambient BGM + SFX generator for vibe-film.
80 BPM, bar=3.0s, Am-F-C-G loop, deterministic (seeded).
Usage:
  python3 gen-audio.py --dur 135 --impacts 9,45,69,102 --heavy 102 --riser 99 \
      --swells 45,69,102,123 --out bgm-sfx-80bpm-135s.mp3 --seed 202610251
Impacts: white-flash turns (heavy=biggest, gets big_impact + riser 3s before).
曲线一「吸气→静音→撞击」：whoosh 峰在撞击前 0.45s（呼吸窗起点）、riser 提前 0.3s 收口、
铺垫最后 0.55s 压 ~10dB——撞击是静音后的第一个声音（check-audio.py 量 dip ≥4dB / lift ≥1dB）。
"""
import argparse
import os
import subprocess
import numpy as np
import wave

# SFX 原语与 gen-sfx.py（CUES 事件层）共用 sfx_lib —— 单一实现防漂移
from sfx_lib import SR, env_ar, impact, big_impact, whoosh, riser

ap = argparse.ArgumentParser()
ap.add_argument("--dur", type=float, required=True, help="duration in seconds (3s multiples)")
ap.add_argument("--impacts", required=True, help="comma seconds, e.g. 9,45,69,102")
ap.add_argument("--heavy", type=float, default=None, help="heaviest impact second (big_impact)")
ap.add_argument("--riser", type=float, default=None, help="riser start second (3s long)")
ap.add_argument("--swells", default="", help="comma seconds for BGM swells")
ap.add_argument("--out", required=True, help="output mp3 path")
ap.add_argument("--seed", type=int, default=20261025)
args = ap.parse_args()

HERE = os.path.dirname(os.path.abspath(args.out)) or "."
SR = 44100
DUR = float(args.dur)
assert DUR % 3.0 == 0, "fail fast: duration must be a multiple of 3s (bar grid)"
BAR = 3.0
BARS = int(DUR / BAR)
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(args.seed)

OUT = []

def add(sig, gain=1.0):
    OUT.append(sig * gain)

# 1) pad chords: Am-F-C-G 4-bar groups over 28 bars, final 2 bars Am sustain
_CYCLE = [
    [110.0, 130.81, 164.81, 220.0],    # Am
    [87.31, 110.0, 130.81, 174.61],    # F
    [130.81, 164.81, 196.0, 261.63],   # C
    [98.0, 123.47, 146.83, 196.0],     # G
]
_group_len = 12.0
_n_full = int(DUR // _group_len)
PAD_GROUPS = [(i * _group_len, (i + 1) * _group_len, _CYCLE[i % 4]) for i in range(_n_full)]
if DUR > _n_full * _group_len:
    PAD_GROUPS.append((_n_full * _group_len, DUR, [110.0, 164.81, 220.0]))  # Am end
pad = np.zeros(N)
for gi, (start, end, freqs) in enumerate(PAD_GROUPS):
    s0, s1 = int(start * SR), min(int(end * SR), N)
    n = s1 - s0
    tt = t[:n]
    seg = np.zeros(n)
    gain_i = 1.0 + (0.15 if gi >= 4 else 0.0)  # 后半段（金）更亮
    for f in freqs:
        vib = 1 + 0.002 * np.sin(2 * np.pi * 0.13 * tt + f)
        seg += np.sin(2 * np.pi * f * vib * tt) + 0.35 * np.sin(2 * np.pi * f * 2 * tt)
    seg *= env_ar(n, 2.0, 2.0, sus=1.0) * gain_i
    pad[s0:s1] += seg
for seam in tuple(g[0] for g in PAD_GROUPS[1:]):
    a, b = int((seam - 1.0) * SR), int((seam + 1.0) * SR)
    if a < N:
        ramp = np.linspace(1, 0, b - a)
        pad[a:b] *= np.minimum(1.0, 0.4 + 0.6 * ramp)
add(pad, 0.045)

# 2) low drone
drone = (np.sin(2 * np.pi * 55.0 * t) + np.sin(2 * np.pi * 55.4 * t)) \
    * (0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t))
add(drone, 0.055)

# 3) bar thumps, accents on turns (bars 3/10/14/18/25 → 9s/30s/42s/54s/75s)
ACCENT = {0, 3, 7, 10, 15, 18, 21, 23, 27, 30, 34, 38, 41}
thump = np.zeros(N)
for bar in range(BARS):
    start = bar * BAR
    if bar in ACCENT:
        for off in (0.0, 1.5):
            s0 = int((start + off) * SR)
            n = int(0.55 * SR)
            if s0 + n > N:
                n = N - s0
            if n <= 0:
                continue
            tt = np.arange(n) / SR
            f = 58 * np.exp(-tt * 3.0) + 38
            k = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 6.0)
            thump[s0:s0 + n] += k * (1.0 if off == 0.0 else 0.6)
    else:
        s0 = int(start * SR)
        n = int(0.5 * SR)
        if s0 + n > N:
            n = N - s0
        if n <= 0:
            continue
        tt = np.arange(n) / SR
        f = 55 * np.exp(-tt * 3.5) + 38
        thump[s0:s0 + n] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 7.0) * 0.8
add(thump, 0.16)

# 4) pentatonic shimmer
NOTES = [440.0, 523.25, 587.33, 659.25, 783.99]
shimmer = np.zeros(N)
for i in range(90):
    start = i * 1.5 + (0.75 if i % 2 else 0.0)
    if start >= DUR - 1.0:
        break
    f = NOTES[int(rng.integers(0, len(NOTES)))]
    s0 = int(start * SR)
    n = int(1.8 * SR)
    if s0 + n > N:
        n = max(0, N - s0)
    if n <= 0:
        continue
    tt = np.arange(n) / SR
    tone = np.sin(2 * np.pi * f * tt) * env_ar(n, 0.05, 1.4, sus=0.35)
    pan = 0.5 + 0.4 * np.sin(i * 1.7)
    shimmer[s0:s0 + n] += tone * (1.0 - pan) * 0.7
add(shimmer, 0.05)

# 5) swells（--swells 参数化；缺省保持历史配方 45,69,102,123）
swell = np.zeros(N)
for center in sorted(float(x) for x in args.swells.split(",") if x.strip()):
    s0 = int((center - 2.0) * SR)
    n = int(3.5 * SR)
    if s0 + n > N:
        n = max(0, N - s0)
    if n <= 0:
        continue
    tt = np.arange(n) / SR
    swell[s0:s0 + n] += np.sin(2 * np.pi * 110.0 * tt) * env_ar(n, 2.2, 1.0, sus=0.9)
add(swell, 0.06)

mix = np.zeros(N)
for sig in OUT:
    mix += sig

# --- SFX ---------------------------------------------------------------------
# impact / big_impact / whoosh / riser 来自 sfx_lib（与 gen-sfx.py 共用，rng 传入保持确定性）
WHOOSH_PEAK = 0.72  # 同 sfx_lib：whoosh 峰在 0.72×dur，放置 = 事件秒 − 0.72×dur

def place(dst, sig, at, gain=1.0):
    s0 = int(at * SR)
    n = min(len(sig), len(dst) - s0)
    if n > 0:
        dst[s0:s0 + n] += sig[:n] * gain

sfx = np.zeros(N)
impacts = sorted(float(x) for x in args.impacts.split(",") if x.strip())
# 吸气→静音→撞击（sound.md §5 曲线一）：whoosh 是落点前的吸气（峰在呼吸窗起点），
# riser 提前收口，撞击落在白闪帧上、是静音后的第一个声音——旧版 whoosh 峰在切点前 0.35s
# 且垫底不停，压住了 drop 前的呼吸（check-audio 实测 dip<4dB，2026-10-27《伪》判例）
GAP = 0.45          # 呼吸窗长度（≈80BPM 的 0.6 拍）
BREATH_GAIN = 0.3   # 呼吸窗内铺垫压到的电平（≈ −10.5dB）
for at in impacts:
    place(sfx, whoosh(rng), max(0.0, at - GAP - 0.7 * WHOOSH_PEAK), 0.55)
    if args.heavy is not None and abs(at - args.heavy) < 0.01:
        if args.riser is not None:
            # riser 在呼吸窗前 0.5s 收完（内部自带 0.3s 快淡出），吸气段不压住呼吸窗
            place(sfx, riser(rng, max(0.5, at - args.riser - 0.5)), args.riser, 0.5)
        place(sfx, whoosh(rng, 1.0), max(0.0, at - GAP - 1.0 * WHOOSH_PEAK), 0.6)
        place(sfx, big_impact(rng), at, 1.0)
    else:
        place(sfx, impact(rng), at, 0.8)

# drop 呼吸：每个 impact 前最后 0.55s 把铺垫压下 ~10dB，撞击后 0.25s 内放回
duck = np.ones(N)
for at in impacts:
    a0, a1 = int(max(0.0, at - 0.55) * SR), int(at * SR)
    att, rel = int(0.15 * SR), int(0.25 * SR)
    duck[a0:a0 + att] = np.minimum(duck[a0:a0 + att], np.linspace(1.0, BREATH_GAIN, att))
    duck[a0 + att:a1] = np.minimum(duck[a0 + att:a1], BREATH_GAIN)
    duck[a1:a1 + rel] = np.minimum(duck[a1:a1 + rel], np.linspace(BREATH_GAIN, 1.0, rel))

final = np.tanh(mix * duck + sfx * 0.9)
peak = np.max(np.abs(final))
if peak > 0:
    final *= 0.85 / peak
stereo = np.stack([final, np.roll(final, int(0.0004 * SR))], axis=1)

mp3_path = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
wav_path = mp3_path[:-4] + ".wav"
pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
with wave.open(wav_path, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(pcm.tobytes())

subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav_path,
                "-b:a", "192k", mp3_path], check=True)
os.remove(wav_path)
print("OK", mp3_path)
