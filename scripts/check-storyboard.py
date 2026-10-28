#!/usr/bin/env python3
"""Validate a vibe-film storyboard markdown table (九列逐镜表).

Checks:
  1. Table parses with exactly 9 columns
  2. Time column: contiguous, starts at 0, ends at declared duration, and either
     - 3s multiples (合成曲模式，默认；2s/4s 变奏 WARN), or
     - on the beat grid of a beats.json (--grid，真曲模式：2026-10-27 定版，
       真曲片时间列基准 = beats.py 检测网格；边界距最近下拍 ≤ --grid-tol，首镜 0 豁免)
  3. 中文字幕: non-empty, ≤2 行 (sentences ≤18 chars each, hard-fail >24)
  4. EN subtitle non-empty (双语字幕硬规则)
  5. 微文案/前景 non-empty (每镜≥1 处等宽微文案)
  6. 转场/情绪色 non-empty
  7. 金句帧 count ≥2, 献给/文献卡 exists near the end
  8. 镜头类型 from the 8-type menu (warn on unknown)

Usage: python3 check-storyboard.py <storyboard.md> [--dur 135] [--grid audio/beats.json] [--grid-tol 0.06]
Exit 0 = pass; exit 1 = any FAIL. WARNs don't fail.
"""
import json
import re
import sys

MENU = {"钩子", "标题卡", "介绍卡", "关系网络", "思维树", "粒子材料", "数据叙事", "数据可视化",
        "隐喻", "金句", "献给", "文献", "彩蛋", "概念", "生活域", "转折", "和解", "指令",
        "收束", "续", "延续", "高潮", "收", "起", "前奏", "具象锚点", "锚点"}

def parse_args():
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--dur", type=float, default=None, help="declared total seconds")
    ap.add_argument("--grid", default=None, help="beats.json（beats.py 产物）：真曲模式，边界对齐检测下拍而非 3s 小节线")
    ap.add_argument("--grid-tol", type=float, default=0.06, help="节拍网格对齐容差秒（默认 0.06 ≈ 2 帧 @30fps）")
    return ap.parse_args()

def main():
    args = parse_args()
    text = open(args.storyboard, encoding="utf-8").read()
    fails, warns = [], []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= {"-", " ", ":"}:
            continue
        if cells[0] in ("时间", "时间 "):
            continue
        if re.match(r"^\d+(?:\.\d+)?(-|–|~)\d+(?:\.\d+)?$", cells[0]):
            if len(cells) != 9:
                fails.append(f"行 {cells[0]}: 列数 {len(cells)} ≠ 9")
                continue
            rows.append(cells)

    if not rows:
        fails.append("没解析到任何逐镜表行（时间列格式应为 0-3 / 3-6 …）")

    t0, prev_end = 0.0, 0.0
    types = []
    boundaries = []
    for i, c in enumerate(rows, 1):
        m = re.match(r"^(\d+(?:\.\d+)?)(-|–|~)(\d+(?:\.\d+)?)$", c[0])
        if not m:
            fails.append(f"镜{i}: 时间格式不合法 '{c[0]}'")
            continue
        a, b = float(m.group(1)), float(m.group(3))
        if i == 1 and a != 0:
            fails.append(f"镜{i}: 起始时间 {a} ≠ 0")
        if abs(a - prev_end) > 1e-6:
            fails.append(f"镜{i}: 时间不连续 {prev_end:g} → {a:g}")
        if b <= a:
            fails.append(f"镜{i}: 时长 {b-a}s 非正数")
        elif args.grid:
            boundaries.append(b)  # 真曲模式：时长由网格自由决定，边界统一在循环后对齐校验
        elif (b - a) % 3 != 0:
            if (b - a) in (2.0, 4.0):
                warns.append(f"镜{i}: 时长 {b-a:.0f}s 变奏（小节线漂移，确认是否有意）")
            else:
                fails.append(f"镜{i}: 时长 {b-a}s 不是 3s 正倍数也不是 2s/4s 变奏")
        prev_end = b

        zh = re.sub(r"⟨[^⟩]*⟩", "", c[2]).strip()
        if not zh or zh in ("—", "（无字幕，音乐留白）", "（无字幕）"):
            pass  # 留白帧合法
        else:
            for sent in [x for x in re.split(r"[。？！]", zh) if x]:
                w = sum(1.0 if ord(ch) > 0x2E80 else 0.5 for ch in sent)  # CJK=1 拉丁=0.5 视宽
                if w > 24:
                    fails.append(f"镜{i}: 中文字幕句超宽({w:.0f}字当量): {sent[:20]}…")
                elif w > 16:
                    warns.append(f"镜{i}: 中文字幕句 {w:.0f} 字当量（推荐 8-16）: {sent}")
        if not c[3] and zh and "无字幕" not in zh:
            fails.append(f"镜{i}: 缺英文译文（双语字幕硬规则）")
        if not c[6] or c[6] in ("—",):
            warns.append(f"镜{i}: 前景/微文案为空（每镜≥1 处等宽微文案）")
        if not c[7]:
            fails.append(f"镜{i}: 缺转场")
        if not c[8]:
            fails.append(f"镜{i}: 缺情绪色")
        types.append(c[1])

    for i, t in enumerate(types):
        if not any(k in t for k in MENU):
            warns.append(f"镜{i+1}: 镜头类型 '{t}' 不在九型菜单（确认是否新变体）")
    joined = " ".join(types)
    if joined.count("金句") < 2:
        warns.append("金句帧 <2（结构公式要求金句×2）")
    if not any("献给" in t for t in types):
        fails.append("缺献给帧（「献给每一个___的人」是硬门槛）")
    if not any("文献" in t for t in types):
        warns.append("缺文献卡（数据出处清单应进成片）")

    if args.grid and boundaries:
        beats, err = None, ""
        try:
            beats = json.load(open(args.grid, encoding="utf-8"))
        except (OSError, ValueError) as e:
            err = str(e)
        downs = (beats or {}).get("downbeats") or (beats or {}).get("beats") or []
        if len(downs) < 2:
            fails.append(f"--grid {args.grid}: 无有效下拍序列（{err if beats is None else 'downbeats/beats 均缺失或过短'}）")
        else:
            for b in boundaries:
                if abs(b) < 1e-6:
                    continue  # 首镜从 0 起播，豁免
                nearest = min(downs, key=lambda t: abs(b - t))
                if abs(b - nearest) > args.grid_tol:
                    fails.append(f"边界 {b:g}s 不在节拍网格（最近下拍 {nearest:.2f}s，差 {abs(b-nearest):.3f}s > 容差 {args.grid_tol}s）"
                                 f"——真曲片切点要钉 beats.py 网格，或放宽 --grid-tol")

    if args.dur is not None and rows and abs(prev_end - args.dur) > 1e-6:
        fails.append(f"总时长 {prev_end:g}s ≠ 声明 {args.dur:g}s")

    for w in warns:
        print(f"WARN  {w}")
    for f in fails:
        print(f"FAIL  {f}")
    print(f"--- {len(rows)} 镜 · {prev_end:.0f}s · FAIL {len(fails)} · WARN {len(warns)}")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
