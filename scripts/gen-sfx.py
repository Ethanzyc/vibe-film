#!/usr/bin/env python3
"""CUES 事件层 SFX 生成器：把分镜/段码里声明的事件表渲染成一条音效轨。
与 check-build.py --export-cues 配套（同一份 CUES 数据：画面读它做点亮脉冲，本工具出声）——
音画同表，一处声明两边用。

工作流（无口播片）：
  Step 4  gen-audio.py 出 BGM+impact 骨架（转折秒，音频先行）
  Step 6  段码 timeline.js 写 CUES = [{t, sfx, gain?, pan?, note?}]（画面同读）
  Step 7  check-build.py <项目> --export-cues audio/cues.json   ← 审计+导出同一解析器
          python3 gen-sfx.py --cues audio/cues.json --dur <总秒> --out audio/sfx.wav
          SFX=audio/sfx.wav sh assemble.sh …（BGM 底上混事件层）

词表（材质对得上，见 audio.md 音效对照表）：
  impact/big_impact/boom = 转折/落版 · whoosh = 甩镜/穿越（峰自动对位：放置 = t−0.72×dur）
  riser = 蓄力 · downlifter = 消散 · bell = 点亮/金句 · tick = 知识星/数字跳动
  pop = 元素弹出 · click = 点击/吸附 · swipe = 滑过 · shimmer = 全亮/聚合/成功
用法:
  python3 gen-sfx.py --cues cues.json --dur 50 --out audio/sfx.wav [--seed 20261027]
cue 字段: t(必) sfx(必) gain(0-1,缺省按词表) pan(-1..1) note(频率 Hz 或 MIDI, bell/pop 用)
"""
import argparse
import json
import wave

import numpy as np

from sfx_lib import (SR, WHOOSH_PEAK, bell, big_impact, boom, click, downlifter,
                     impact, place, pop, riser, shimmer, swipe, tick, whoosh)

WORDS = {"impact", "big_impact", "boom", "whoosh", "riser", "downlifter",
         "bell", "tick", "pop", "click", "swipe", "shimmer"}

# 词表缺省增益（对照表原则：材质对得上，重音只给最重要的 1-2 处）
DEFAULT_GAIN = {
    "impact": 0.8, "big_impact": 1.0, "boom": 0.85, "whoosh": 0.55, "riser": 0.5,
    "downlifter": 0.4, "bell": 0.42, "tick": 0.3, "pop": 0.5, "click": 0.4,
    "swipe": 0.35, "shimmer": 0.45,
}
# whoosh/riser 是"事件前"的声音：whoosh 峰对位公式内建；riser 默认 3s 结束于事件
LEAD = {"whoosh": lambda d: -WHOOSH_PEAK * 0.7, "riser": lambda d: -min(3.0, d)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cues", required=True, help="check-build --export-cues 导出的事件表 JSON")
    ap.add_argument("--dur", type=float, required=True, help="总时长秒")
    ap.add_argument("--out", required=True, help="输出 wav 路径（绝对路径）")
    ap.add_argument("--seed", type=int, default=20261027)
    args = ap.parse_args()

    cues = json.load(open(args.cues, encoding="utf-8"))
    if not isinstance(cues, list):
        raise SystemExit(f"gen-sfx: {args.cues} 应为 cue 数组（check-build --export-cues 产物）")
    N = int(SR * args.dur)
    L, R = np.zeros(N), np.zeros(N)
    rng = np.random.default_rng(args.seed)

    placed, skipped = 0, []
    for c in cues:
        word = (c.get("sfx") or "").strip()
        # 多段工程必须用绝对秒（export-cues 同时给段内 t 与 abs_t；单段工程两者相等）
        t = float(c.get("abs_t", c["t"]))
        if word not in WORDS:
            skipped.append(f"t={t}: 未知词 '{word}'（词表: {'/'.join(sorted(WORDS))}）")
            continue
        at = t + LEAD.get(word, lambda d: 0.0)(args.dur)
        gain = float(c.get("gain", DEFAULT_GAIN[word]))
        pan = float(c.get("pan", 0.0))
        note = c.get("note")
        if word == "impact":
            sig = impact(rng)
        elif word == "big_impact":
            sig = big_impact(rng)
        elif word == "boom":
            sig = boom(rng)
        elif word == "whoosh":
            sig = whoosh(rng)
        elif word == "riser":
            sig = riser(rng, min(3.0, max(0.5, t)))
        elif word == "downlifter":
            sig = downlifter(rng)
        elif word == "bell":
            sig = bell(rng, note if note is not None else 1244.5)  # 缺省 D#6 玻璃感
        elif word == "tick":
            sig = tick()
        elif word == "pop":
            sig = pop(rng, f0=note if note is not None else 1046.5)
        elif word == "click":
            sig = click(rng)
        elif word == "swipe":
            sig = swipe(rng)
        else:  # shimmer
            sig = shimmer(rng)
        if 0 <= at < args.dur:
            place((L, R), sig, max(0.0, at), gain, pan)
            placed += 1
        else:
            skipped.append(f"t={t} ({word}): 事件秒在片外")

    peak = max(np.max(np.abs(L)), np.max(np.abs(R)))
    if peak > 0:
        L, R = L * (0.85 / peak), R * (0.85 / peak)
    import os
    out = args.out if os.path.isabs(args.out) else os.path.join(os.getcwd(), args.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    pcm = (np.clip(np.stack([L, R], axis=1), -1, 1) * 32767).astype(np.int16)
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"OK {out} · {len(cues)} cues → {placed} placed, {len(skipped)} skipped · {args.dur}s")
    for s in skipped:
        print(f"  SKIP {s}")


if __name__ == "__main__":
    main()
