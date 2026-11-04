#!/usr/bin/env python3
"""节拍网格检测：给真曲量 BPM/拍点/下拍/能量小节/drop 位置，供分镜表钉切点用。
零新依赖（numpy + ffmpeg）。机制（2026-10-27 音效卡点拆解定版）：24 对数频带谱通量 + 低带 kick 通量，
自相关求速度（120BPM 先验 + 倍频程纠错），穷举相位 + 逐拍吸附；另加帧能量门控
（低于全曲中位电平 -20dB 的帧不计通量），压低环境垫/弱电平素材的分析噪声。
用法:
  python3 beats.py track.mp3 --out audio/beats.json [--bpm 96] [--shift 0.5]
输出 JSON: bpm / beats / downbeats / hits / bars / drops / breaks
边界（实测判例 2026-10-27）：本工具给有鼓点的真曲用；无鼓点的环境合成曲（垫+稀疏 thump）
没有可检测的节拍，会锁到假周期——合成曲走 gen-audio.py 的已知网格（80 BPM / 3s 小节），
不要对它跑本工具，用 --bpm 传已知速度时本工具只做相位/吸附/下拍核对。
注意: 检测可能锁到半速/倍速，或落在反拍——与已知 BPM 不符加 --bpm，拍点在反拍加 --shift 0.5。
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

SR = 22050
NFFT, HOP = 1024, 256
FPS = SR / HOP  # 频谱帧率 ≈ 86.13


def die(msg):
    print(f"beats: {msg}", file=sys.stderr)
    sys.exit(1)


def decode(path):
    if not os.path.exists(path):
        die(f"file not found: {path}")
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def stft_mag(y):
    win = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(NFFT) / (NFFT - 1))
    n = 1 + (len(y) - NFFT) // HOP
    if n < 50:
        die("track too short to analyse")
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    frames = y[idx] * win
    return np.abs(np.fft.rfft(frames, axis=1))  # (n, NFFT/2+1)


def onset_envelopes(spec):
    # 帧能量门控：垫底/弱电平帧的正弦拍频会产生假通量，不计入
    edb = 10 * np.log10((spec ** 2).sum(axis=1) + 1e-12)
    gate = (edb > np.median(edb) - 20).astype(float)
    # 24 个对数频带（40Hz–9kHz，每带等权）：hat 不会淹没 kick
    edges = np.maximum(1, np.round(40 * (9000 / 40) ** (np.arange(25) / 24) * NFFT / SR)).astype(int)
    cols = []
    for e0, e1 in zip(edges[:-1], edges[1:]):
        cols.append(np.log1p(10 * spec[:, e0:max(e0 + 1, e1)].mean(axis=1)))
    band = np.stack(cols, axis=1)  # (n, 24)
    d = np.diff(band, axis=0)
    on = np.where(d > 0, d, 0).sum(axis=1) * gate[1:]
    on = np.concatenate([[0], on])
    # 低带（≤180Hz）通量 = kick 专用包络
    k = int(np.ceil(180 * NFFT / SR))
    dl = np.diff(np.log1p(spec[:, 1:k + 1]), axis=0)
    low = np.where(dl > 0, dl, 0).sum(axis=1) * gate[1:]
    low = np.concatenate([[0], low])
    return smooth(on), smooth(low)


def smooth(a):
    c = a.copy()
    a[1:-1] = 0.25 * c[:-2] + 0.5 * c[1:-1] + 0.25 * c[2:]
    return znorm(a)


def znorm(a):
    sd = a.std()
    return (a - a.mean()) / (sd or 1.0)


def autocorr(on, lo, hi):
    # ac(l) = Σ on[i]*on[i+l]，l ∈ [lo, hi]
    n = len(on)
    size = 1 << (2 * n - 1).bit_length()
    f = np.fft.rfft(on, size)
    ac_full = np.fft.irfft(f * np.conj(f), size)[:n]
    return ac_full[lo:hi + 1]


def find_period(on, bpm_override):
    lo = int(np.floor(FPS * 60 / 180))
    hi = int(np.ceil(FPS * 60 / 60))
    ac = autocorr(on, lo, hi)
    lags = np.arange(lo, hi + 1)
    bpm_of = 60 * FPS / lags
    prior = np.exp(-0.5 * (np.log2(bpm_of / 120) / 0.9) ** 2)
    scored = ac * prior
    bi = int(lags[int(np.argmax(scored))])
    if bpm_override:
        return 60 * FPS / bpm_override, ac
    # 倍频程纠错：kick/snare 模式常锁半速，半 lag 支撑够强就倾向更快的读法
    half = round(bi / 2)
    ac_at = lambda l: ac[min(max(l - lo, 0), len(ac) - 1)]
    ac_half = max(ac_at(half - 1), ac_at(half), ac_at(half + 1))
    if 60 * FPS / half <= 185 and ac_half > 0.5 * ac_at(bi):
        bi = max((half - 1, half, half + 1), key=ac_at)
    # 抛物线细化到非整数 lag
    y0, y1, y2 = ac_at(bi - 1), ac_at(bi), ac_at(bi + 1)
    den = y0 - 2 * y1 + y2
    delta = 0.5 * (y0 - y2) / den if den else 0.0
    return bi + float(np.clip(delta, -0.5, 0.5)), ac


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("track")
    ap.add_argument("--out", default=None, help="beats.json 输出路径")
    ap.add_argument("--bpm", type=float, default=None, help="已知 BPM 时强制（跳过自相关）")
    ap.add_argument("--shift", type=float, default=0.0, help="拍点整体偏移（拍为单位，反拍=0.5）")
    args = ap.parse_args()

    y = decode(args.track)
    dur = len(y) / SR
    spec = stft_mag(y)
    on, low = onset_envelopes(spec)
    n = len(on)
    acc = on + 1.5 * low

    period, _ = find_period(on, args.bpm)
    # 相位：穷举网格偏移，取落在格上的 onset 强度和最大的那个
    offsets = np.arange(int(np.ceil(period)))
    scores = [sum(acc[int(o + k * period)] for k in range(int((n - o - 1) // period) + 1)) for o in offsets]
    phase = float(offsets[int(np.argmax(scores))])
    # 逐拍吸附：±10% 周期窗内吸附到局部 onset 峰
    w = max(2, round(period * 0.1))
    idxs, t = [], phase
    while t < n:
        c = int(round(t))
        lo, hi = max(0, c - w), min(n - 1, c + w)
        j = lo + int(np.argmax(acc[lo:hi + 1]))
        idxs.append(j if acc[j] > 0.5 else c)
        t = idxs[-1] + period
    lag = NFFT / 2 / SR + args.shift * period / FPS
    sec = lambda i: round(i / FPS + lag, 3)

    # 下拍：4 拍循环里低带能量最高的相位
    k4 = min(4, len(idxs))
    d0 = max(range(k4), key=lambda k: sum(low[i] for i in idxs[k::4]))
    downs = [sec(i) for i in idxs[d0::4]]
    # hits：全带通量局部峰（≥0.1s 间隔）
    hits, last = [], -10
    for i in range(1, n - 1):
        if on[i] > 2 and on[i] >= on[i - 1] and on[i] >= on[i + 1] and i - last > FPS * 0.1:
            hits.append(sec(i))
            last = i
    # 每小节能量 → drop（突增）/ break（突降）
    bars = []
    for a, b in zip(downs, downs[1:] + [dur]):
        s0, s1 = int(a * SR), min(int(b * SR), len(y))
        if s1 <= s0:
            continue
        p = float((y[s0:s1].astype(np.float64) ** 2).mean())
        bars.append({"t": a, "db": round(10 * np.log10(p + 1e-12), 1)})
    drops = [b["t"] for i, b in enumerate(bars) if i >= 2 and b["db"] - (bars[i - 1]["db"] + bars[i - 2]["db"]) / 2 > 4]
    breaks = [b["t"] for i, b in enumerate(bars[1:], 1) if bars[i - 1]["db"] - b["db"] > 5]

    res = {
        "engine": "numpy", "file": os.path.basename(args.track), "duration": round(dur, 3),
        "bpm": round(60 * FPS / period, 2), "beats": [sec(i) for i in idxs],
        "downbeats": downs, "hits": hits, "bars": bars, "drops": drops, "breaks": breaks,
    }
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    else:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"bpm ≈ {res['bpm']}, {len(res['beats'])} beats, first downbeat {downs[0] if downs else '-'}s, "
          f"{len(hits)} hits, drops at {drops}, breaks at {breaks}"
          + (f" → {args.out}" if args.out else ""), file=sys.stderr)
    print("自查网格：检测可能锁到半速/倍速；与已知 BPM 不符加 --bpm，拍点在反拍加 --shift 0.5", file=sys.stderr)


if __name__ == "__main__":
    main()
