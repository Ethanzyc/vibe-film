#!/usr/bin/env python3
"""对标片节拍网格：量参考视频的剪点落在什么网格上。
机制移植自 motion-showreel inspect.mjs grid / frames.mjs fitGrid（2026-10-27 调研）：
帧差找剪点（局部中位数基线 2.5 倍 + 0.2s 防抖）→ 圆统计拟合网格（atan2 相位 + ±1.5 帧内点，
取能容纳 ≥80% 剪点的最大步长）→ BPM 候选表。
用法:
  python3 fit-grid.py 对标.mp4 [--thresh 5] [--tol 1.5] [--out qa/grid.json]
读法：
  - 「每段占几步」数字递减 = 切速在加快而拍速不变
  - BPM 候选按「一步=16分/8分/1拍/半小节/1小节」给出，60–200 过滤；与对标曲 audio 节拍网格应一致
  - 剪点 <4 个或没有步长能容纳 80% → 无稳定网格（它是按乐句/语义切的，不是按拍）
"""
import argparse
import json
import os
import statistics
import subprocess
import sys

import numpy as np

PIX = 12  # 灰度差超过此值算「变了」（编码噪声低于此）


def die(msg):
    print(f"fit-grid: {msg}", file=sys.stderr)
    sys.exit(1)


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die(f"cannot read {path}")
    import json as j
    vs = next((s for s in j.loads(r.stdout)["streams"] if s["codec_type"] == "video"), None)
    if vs is None:
        die("no video stream")
    num, den = vs["r_frame_rate"].split("/")
    return float(num) / float(den), int(vs["width"]), int(vs["height"])


def gray_frames(path, w, h):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-an", "-vf", f"scale={w}:{h}:flags=area,format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    if p.returncode != 0:
        die(f"decode failed: {p.stderr.decode(errors='replace').strip().splitlines()[-1:]}")
    size = w * h
    buf = p.stdout
    n = len(buf) // size
    return np.frombuffer(buf[:n * size], dtype=np.uint8).reshape(n, size)


def diff_profile(frames):
    a, b = frames[:-1], frames[1:]
    changed = (np.abs(a.astype(np.int16) - b.astype(np.int16)) > PIX).mean(axis=1)
    mean = np.abs(a.astype(np.int16) - b.astype(np.int16)).mean(axis=1)
    return changed, mean.astype(float)


def find_starts(mean, fps, thresh, debounce):
    out, last = [], -10**9
    half = max(1, round(fps / 2))
    for i in range(len(mean)):
        local = statistics.median(mean[max(0, i - half):i]) if i > 0 else 0.0
        if mean[i] > thresh and mean[i] > 2.5 * local + 1 and i - last >= debounce * fps:
            out.append(i + 1)  # 第一张变化的帧
            last = i
    return out


def eval_step(starts, s, tol):
    ang = 2 * np.pi * np.asarray(starts) / s
    o = (np.arctan2(np.sin(ang).sum(), np.cos(ang).sum()) / (2 * np.pi) * s + s) % s
    res = lambda x: min((x - o) % s, (o - x) % s)
    inl = [x for x in starts if res(x) <= tol]
    if inl:
        o = statistics.median([(x - round((x - o) / s) * s) % s for x in inl])
        inl = [x for x in starts if res(x) <= tol]
    return s, o, inl, res


def fit_grid(starts, fps, tol, need=0.8):
    if len(starts) < 4:
        return None
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    lo, hi = max(4 * tol, 2), max(gaps) + tol
    top = None
    s = lo
    while s <= hi:
        _, _, inl, _ = eval_step(starts, s, tol)
        if len(inl) / len(starts) >= need:
            top = s
        s += 0.05
    if top is None:
        return None
    # 大步长倾向偏长：在 0.97×top 附近按「内点最多、残差最小」二次细化
    best, best_err = None, None
    s = top * 0.97
    while s <= top + 1e-9:
        _, o, inl, res = eval_step(starts, s, tol)
        if len(inl) / len(starts) >= need:
            err = sum(res(x) ** 2 for x in inl) / len(inl)
            if best is None or len(inl) > len(best[2]) or (len(inl) == len(best[2]) and err < best_err):
                best, best_err = (s, o, inl, res), err
        s += 0.01
    s, o, inl, res = best
    sec = s / fps
    cands = []
    for u, label in ((0.25, "16分"), (0.5, "8分"), (1, "1拍"), (2, "半小节"), (4, "1小节")):
        bpm = 60 * u / sec
        if 60 <= bpm <= 200:
            cands.append({"step": label, "bpm": round(bpm, 1)})
    return {
        "stepFrames": round(s, 2), "stepSec": round(sec, 4), "offsetSec": round(o / fps, 3),
        "inliers": len(inl), "total": len(starts),
        "outliers": [round(x / fps, 3) for x in starts if x not in inl],
        "maxResidualFrames": round(max(res(x) for x in inl), 2),
        "unitsPerSegment": [round(g / s, 1) for g in gaps],
        "bpmCandidates": cands,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--thresh", type=float, default=5)
    ap.add_argument("--tol", type=float, default=1.5)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.video):
        die(f"file not found: {args.video}")
    fps, w, h = probe(args.video)
    gw = 160
    gh = max(2, round(gw * h / w / 2) * 2)
    frames = gray_frames(args.video, gw, gh)
    if len(frames) < fps * 3:
        die("video too short to analyse")
    _, mean = diff_profile(frames)
    starts = find_starts(mean, fps, args.thresh, 0.2)
    sec = [round(f / fps, 3) for f in starts]
    fit = fit_grid(starts, fps, args.tol)

    res = {"video": os.path.basename(args.video), "fps": round(fps, 3),
           "starts": sec, "grid": fit}
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"{len(starts)} 个剪点/转场起点: {', '.join(f'{t:.2f}' for t in sec) or '无'}")
    if fit:
        print(f"网格: 一步 = {fit['stepFrames']} 帧 ({fit['stepSec']}s)，首个格点 {fit['offsetSec']}s；"
              f"{fit['inliers']}/{fit['total']} 剪点落在格上（最大偏差 {fit['maxResidualFrames']} 帧）")
        print("  BPM 候选（一步按…读）: " + (" · ".join(f"{c['step']}: {c['bpm']}" for c in fit["bpmCandidates"]) or "无 60–200 内读法"))
        print(f"  每段占几步: {' '.join(str(u) for u in fit['unitsPerSegment'])}  （数字递减=切速加快、拍速不变）")
        if fit["outliers"]:
            print(f"  网格外剪点: {', '.join(f'{t}s' for t in fit['outliers'])}（误检或刻意的反拍切）")
        print("  有曲子时用 beats.py 交叉验证：画面网格与节拍网格应一致")
    else:
        print("无稳定网格：剪点 <4 个，或没有步长能容纳 80%（它按乐句/语义切，不按固定拍）")


if __name__ == "__main__":
    main()
