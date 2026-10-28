#!/usr/bin/env python3
"""音频量化自查：AI 听不见，所以只信测量。
量三样东西（判据移植自 motion-showreel audio.mjs check，响度目标改用本产线 −15±1.5 LUFS）：
  1. drop 呼吸：--drops 声明的每个重拍前，前半拍比前一小节低多少（<4dB=WARN 没有呼吸）、
     重拍比前一小节高多少（<1dB=WARN 不比铺垫响）——这是程序「听」drop 的唯一办法
  2. 响度/真峰值（ffmpeg ebur128，目标 I=-15±1.5 / TP≤-1.5）+ 倍频程能量表（轰头/发闷/单薄/刺耳）
  3. 意外静音段（≥0.6s 低于 -50dB；drop 前刻意留白是例外）
用法:
  python3 check-audio.py bgm.mp3 --drops 30,60,90 --bpm 80 --out qa/audio --premix
  python3 check-audio.py out/final.mp4 --drops 30,60,90            # 成片复测同样适用
有 BPM 数据时优先用 beats.py 的结果传 --bpm；不传默认 0.75s/拍（80 BPM，本产线合成曲网格）。
--premix：gen-audio.py 直出的 BGM 预混低于 -15 LUFS、mp3 解码真峰值超 0 是预期
（assemble.sh 的 loudnorm/限幅链负责响度），此时响度/TP 只提示不 WARN；drop 呼吸与频带照常判。
输出为审片材料（WARN 要在台账里解释或修复）；响度判 FAIL 时退出码 1。
"""
import argparse
import os
import subprocess
import sys

import numpy as np

SR = 48000
OCT = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]


def die(msg):
    print(f"check-audio: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def decode(path):
    if not os.path.exists(path):
        die(f"file not found: {path}")
    # PCM 是二进制，不能走 text=True 的 run()
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True)
    if raw.returncode != 0:
        die(f"decode failed: {raw.stderr.decode(errors='replace').strip().splitlines()[-1] if raw.stderr else 'unknown'}")
    f = np.frombuffer(raw.stdout, dtype=np.float32)
    if f.size < SR:
        die("audio too short")
    return f[0::2].astype(np.float64), f[1::2].astype(np.float64)


def loudness(path):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "info", "-i", path,
             "-vn", "-af", "ebur128=peak=true:framelog=verbose", "-f", "null", "-"])
    if "Summary:" not in r.stderr:
        die("ffmpeg returned no ebur128 summary")
    s = r.stderr[r.stderr.rfind("Summary:"):]
    get = lambda pat: float(np.nan if (m := __import__("re").search(pat, s)) is None else m.group(1))
    i_val, tp = get(r"I:\s+(-?[\d.]+) LUFS"), get(r"Peak:\s+(-?[\d.]+) dBFS")
    if np.isnan(i_val) or np.isnan(tp):
        die("malformed ebur128 summary")
    return i_val, tp


def octave_table(mono):
    # 4096 窗 / 2048 跳，累计功率谱 → 倍频程能量（相对 1kHz，粉噪全 0）
    win = np.hanning(4096)
    n = 1 + (len(mono) - 4096) // 2048
    if n < 1:
        die("audio too short for spectrum")
    idx = np.arange(4096)[None, :] + 2048 * np.arange(n)[:, None]
    spec = np.abs(np.fft.rfft(mono[idx] * win, axis=1)) ** 2
    bins = spec.mean(axis=0)
    def band(a, b):
        k0, k1 = round(a * 4096 / SR), max(round(a * 4096 / SR) + 1, round(b * 4096 / SR))
        return float(bins[k0:k1].sum()) + 1e-20
    ref = band(1000 / np.sqrt(2), 1000 * np.sqrt(2))
    return [round(10 * np.log10(band(c / np.sqrt(2), c * np.sqrt(2)) / ref), 1) for c in OCT]


def silences(mono):
    # 10ms RMS 桶，≥0.6s 低于 -50dB 记为静音段
    bucket = SR // 100
    n = len(mono) // bucket
    rms = np.sqrt((mono[:n * bucket].reshape(n, bucket) ** 2).mean(axis=1))
    db = 10 * np.log10(rms + 1e-12)
    quiet, start = [], None
    for i, v in enumerate(db):
        if v < -50:
            if start is None:
                start = i
        elif start is not None:
            if (i - start) / 100 >= 0.6:
                quiet.append((round(start / 100, 2), round(i / 100, 2)))
            start = None
    if start is not None and (n - start) / 100 >= 0.6:
        quiet.append((round(start / 100, 2), round(n / 100, 2)))
    return quiet


def rms_db(x, a, b):
    # x 是采样数组（不是分桶能量——JS 原版切的是 energies，直移索引公式会量错 100 倍窗）
    i0, i1 = max(0, int(a * SR)), min(len(x), int(b * SR))
    if i1 <= i0:
        return float("nan")
    return 10 * np.log10(float((x[i0:i1] ** 2).mean()) + 1e-12)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--drops", default="", help="逗号分隔的重拍秒，如 30,60,90")
    ap.add_argument("--bpm", type=float, default=80.0, help="拍长换算用（默认 80=合成曲网格）")
    ap.add_argument("--out", default=None, help="qa 图前缀，如 qa/audio")
    ap.add_argument("--premix", action="store_true", help="BGM 预混口径：响度/TP 只提示不 WARN")
    args = ap.parse_args()

    L, R = decode(args.file)
    mono = (L + R) / 2
    dur = len(L) / SR
    i_lufs, tp = loudness(args.file)
    oct_db = octave_table(mono)
    low_db = 10 * np.log10((10 ** (oct_db[0] / 10) + 10 ** (oct_db[1] / 10) + 10 ** (oct_db[2] / 10)) / 3)
    high_db = 10 * np.log10((10 ** (oct_db[7] / 10) + 10 ** (oct_db[8] / 10)) / 2)
    quiet = silences(mono)

    beat = 60 / args.bpm
    drops = sorted(float(x) for x in args.drops.split(",") if x.strip() and 0 < float(x) < dur)
    drop_lines, drop_warn = [], []
    for d in drops:
        breath = rms_db(mono, d - beat / 2, d - 0.01)
        bar = rms_db(mono, d - beat / 2 - 4 * beat, d - beat / 2)
        hit = rms_db(mono, d, d + 2 * beat)
        if not all(np.isfinite(v) for v in (breath, bar, hit)):
            continue
        dip, lift = bar - breath, hit - bar
        dip_txt = f"低 {dip:.1f}dB" if dip >= 0 else f"反而高 {-dip:.1f}dB"
        drop_lines.append(f"drop @{d:.2f}s: 前半拍比前一小节{dip_txt} · 重拍抬升 {lift:+.1f}dB")
        if dip < 4:
            drop_warn.append(f"@{d:.2f}s 重拍前没有呼吸（前半拍比前一小节只{dip_txt}，判据 ≥4）："
                             f"停掉鼓/铺底，最多留 riser 尾巴；若此片不用吸气→爆发曲线，把这个点从 drops 里去掉")
        if lift < 1:
            drop_warn.append(f"@{d:.2f}s 重拍不比前一小节响（{lift:+.1f}dB，判据 ≥1）：削薄铺垫或加重一击")

    warn = []
    note = []
    if not (-16.5 < i_lufs < -13.5):
        msg = f"整体响度 {i_lufs} LUFS 偏离目标（-15±1.5）"
        (note if args.premix else warn).append(msg + ("（--premix：assemble 拉响度，预期内）" if args.premix else ""))
    if tp > -1.5:
        msg = f"真峰值 {tp} dBFS 高于 -1.5（收尾 alimiter 或降母带增益）"
        (note if args.premix else warn).append(msg + ("（--premix：mp3 解码过冲，总装限幅处理，预期内）" if args.premix else ""))
    if low_db > 14:
        warn.append(f"轰头：31–125Hz 比 1kHz 高 {low_db:.1f}dB（典型 +4…+12）：压 sub/bass、缩短 thump 衰减、铺底加 highpass")
    if low_db < 0:
        warn.append(f"单薄：几乎没有低频（{low_db:.1f}dB re 1kHz）——刻意轻盈除外")
    if high_db < -24:
        warn.append(f"发闷：4–8kHz 比 1kHz 低 {-high_db:.1f}dB（典型 -6…-18）：加高频层/更亮音色")
    if high_db > -2:
        warn.append(f"刺耳：4–8kHz 高达 {high_db:.1f}dB re 1kHz：压噪声层/riser")
    if quiet:
        warn.append("静音段: " + ", ".join(f"{a}–{b}s" for a, b in quiet) + "（刻意留白除外）")
    warn += drop_warn
    warn += note

    print(f"{args.file}")
    print(f"  {dur:.2f}s · {i_lufs} LUFS · TP {tp} dBFS · 倍频程(dB re 1kHz): "
          + " · ".join(f"{c:g} {v:+.1f}" for c, v in zip(OCT, oct_db)))
    for line in drop_lines:
        print("  " + line)
    if args.out:
        prefix = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(prefix), exist_ok=True)
        for argv, png in (
            (["-filter_complex", f"showwavespic=s=1600x320:split_channels=1:colors=0x4fd1c5|0xf6ad55", "-frames:v", "1"], f"{prefix}-wave.png"),
            (["-lavfi", "showspectrumpic=s=1600x520:legend=1:scale=log"], f"{prefix}-spectrum.png"),
        ):
            if os.path.exists(png):
                os.remove(png)  # 上一次的旧图不能冒充这次的证据
            r = run(["ffmpeg", "-v", "error", "-y", "-i", args.file, *argv, png])
            if r.returncode != 0 or not os.path.exists(png) or os.path.getsize(png) == 0:
                die(f"could not write {png}")
        print(f"  图: {prefix}-wave.png, {prefix}-spectrum.png")
    print("  WARN\n   - " + "\n   - ".join(warn) if warn else "  OK: 响度、峰值、频带与 drop 呼吸都在判据内")
    sys.exit(0)


if __name__ == "__main__":
    main()
