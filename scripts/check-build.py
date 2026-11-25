#!/usr/bin/env python3
"""Static cross-audit of a rendered/renders-in-progress vibe-film project (no rendering).

Design note: pixel-based QC has blind
spots; the cheapest reliable check is reconciling SOURCE LITERALS against the storyboard
(the reviewed single source of truth). Real-world catch it is designed for: a counter
silently edited in JS (2022 -> 2023) that every frame-watching QC agent missed.

Checks (project layout per SKILL.md step 6/7: seg1..segN/ with timeline.js as the
per-seg source of truth for DUR / CUES / COPY):
  1. Copy audit (FAIL): every 字幕中 sentence in the storyboard table must appear in some
     seg's COPY[].zh, and every COPY[].zh must exist in the table — both directions.
     Extra literal in code = drift (the 2022->2023 class). EN reconciliation is WARN
     (translation may be fine-tuned at implementation).
  2. Time reconciliation (FAIL): sum of seg DUR must equal the table's total duration;
     any DUR > 45s violates the per-seg limit; a storyboard shot crossing a seg boundary
     is a structural bug.
  3. White-flash whitelist (FAIL/WARN): every white-flash CUE in code must land inside a
     storyboard row whose 转场 column mentions 白闪/闪 (hard rule: 白闪只出现在分镜表指定处);
     table 白闪 rows with no code cue in their window are WARN (may be implemented differently).
  4. On-screen literal sweep (INFO, report-only): CJK string literals in seg JS that do
     NOT appear anywhere in the storyboard file — agent/human confirms each belongs to
     微文案/场景标签 and traces back to the fact list. Plus year/percent literals for
     fact-audit. Not a FAIL by design: heuristic extraction cannot judge semantics.
  5. CUES audit (FAIL/WARN): every cue's t must sit inside its seg's DUR (音画事件必须
     落在本段内，FAIL); an sfx word outside the gen-sfx vocabulary is WARN (gen-sfx 会
     跳过). --export-cues <path> dumps all sfx-bearing cues with absolute seconds as
     JSON for gen-sfx.py（音画同表：画面读 CUES 做点亮脉冲，gen-sfx 出声）.
     v1.8.1: the per-seg cue list, DUR and OFFSET come from node actually importing
     timeline.js (what the page really plays) — so gain / pan / note survive the export
     and helper-expanded cues (row(...), Array.from) are neither skipped by the audit nor
     dropped from the export. The regex pass still runs and anything only it sees gets
     audited too. No node / import failure = fall back to regex with a WARN that says
     what gets lost (needs node on PATH).

Usage:  python3 check-build.py <project-slug-dir> [--storyboard <path>] [--export-cues <path>]
        (default storyboard: <project>/分镜与文案.md)
Exit 0 = no FAIL; exit 1 = any FAIL. WARN/INFO never fail.
"""
import argparse
import re
import sys
from pathlib import Path

PUNCT = re.compile(r"[\s，。；：、！？·—…《》「」『』（）()\[\]{}\"'`~～\-—_|,.;:!?\u3000]+")

# CUES 音效词表 —— 与 gen-sfx.py WORDS 保持一致（selftest 有双处一致校验；
# sfx_lib.py 是音色实现。加新词：sfx_lib 实现 + 两处词表 + selftest 自动把关）
SFX_WORDS = {"impact", "big_impact", "boom", "whoosh", "riser", "downlifter",
             "bell", "tick", "pop", "click", "swipe", "shimmer"}


def norm(s: str) -> str:
    return PUNCT.sub("", s)


def parse_storyboard(path: Path):
    """Return (rows, total) where rows = [(a, b, shot_type, zh_cell, en_cell, trans_cell)]."""
    text = path.read_text(encoding="utf-8")
    rows, total = [], 0.0
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= {"-", " ", ":"}:
            continue
        m = re.match(r"^(\d+)(?:-|–|~)(\d+)$", cells[0])
        if not m or len(cells) != 9:
            continue
        a, b = float(m.group(1)), float(m.group(2))
        rows.append((a, b, cells[1], cells[2], cells[3], cells[7]))
        total = max(total, b)
    return rows, total


def table_sentences(zh_cell: str):
    """Split a 字幕中 cell into sentences. ⟨重点词⟩ markers are stripped entirely
    (same semantics as check-storyboard.py); （无字幕…） placeholders are stripped
    so real content sharing the cell (e.g. 「（无字幕）找到了。」) still parses."""
    zh_cell = re.sub(r"⟨[^⟩]*⟩", "", zh_cell)
    zh_cell = re.sub(r"（无字幕[^）]*）", "", zh_cell)
    if not zh_cell.strip():
        return []
    return [s for s in (x.strip() for x in re.split(r"[。？！]", zh_cell)) if s]


def find_segs(project: Path):
    """seg dirs in numeric order: [ (seg_path, offset, dur or None) ]."""
    segs = []
    for d in sorted(project.glob("seg*"), key=lambda p: (len(p.name), p.name)):
        m = re.search(r"(\d+)$", d.name)
        if d.is_dir() and m:
            segs.append((d, int(m.group(1))))
    segs.sort(key=lambda x: x[1])
    return [s[0] for s in segs]


_NUM_EXPR = re.compile(r"^[0-9.\s*/+()-]+$")


def _resolve_const_expr(expr: str, consts: dict, depth: int = 0):
    """Resolve `export const NAME = <expr>` to a float, following identifiers
    (BPM -> BEAT -> BAR chains) and simple arrow functions `b = n => n * BAR`."""
    if depth > 8:
        return None
    expr = expr.strip()
    arrow = re.match(r"^([A-Za-z_]\w*)\s*=>\s*(.+)$", expr)
    if arrow:
        return ("fn", arrow.group(1), arrow.group(2))  # caller substitutes the argument
    if not _NUM_EXPR.match(expr):
        def repl(mm):
            v = _resolve_const_expr(consts.get(mm.group(1), mm.group(1)), consts, depth + 1)
            return f"({v})" if isinstance(v, float) else mm.group(1)
        expr = re.sub(r"\b([A-Za-z_]\w*)\b", repl, expr)
    if not _NUM_EXPR.match(expr):
        return None
    try:
        return float(eval(expr, {"__builtins__": {}}, {}))  # digits/operators only, regex-gated
    except Exception:
        return None


def parse_timeline(tl: Path):
    """Extract (dur, dur_err, cues, cue_errs, zh_list, en_list) from a seg's timeline.js.
    DUR may be a numeric expression (1080 / 30) or a helper call (b(15)).
    cues = [(t, visual, sfx)]; cue_errs = 无法解析的事件（调用方 FAIL，不许静默丢）。"""
    text = tl.read_text(encoding="utf-8") if tl.exists() else ""
    dur, dur_err = None, None
    consts = {m.group(1): m.group(2).strip() for m in
              re.finditer(r"^export const ([A-Za-z_]\w*)\s*=\s*([^;\n]+);", text, re.M)}
    m = re.search(r"^export const DUR\s*=\s*([^;\n]+);", text, re.M)
    if m:
        expr = m.group(1).strip()
        call = re.match(r"^([A-Za-z_]\w*)\(\s*([\d.]+)\s*\)$", expr)
        if call and call.group(1) in consts:
            fn = _resolve_const_expr(consts[call.group(1)], consts)
            if isinstance(fn, tuple):
                body = re.sub(rf"\b{fn[1]}\b", f"({call.group(2)})", fn[2])
                v = _resolve_const_expr(body, consts)
                if isinstance(v, float):
                    dur = v
        else:
            v = _resolve_const_expr(expr, consts)
            if isinstance(v, float):
                dur = v
        if dur is None:
            dur_err = f"DUR 表达式无法求值: {expr}"
    cues, cue_errs = [], []
    # 手写 cue 对象：t 必须是数字字面量（表达式 t 交给下方展开规则，两边都不行的 FAIL）
    for m in re.finditer(r"\{[^{}]*\bt:\s*([^,{}]+)[^{}]*\}", text, re.S):
        block = m.group(0)
        sfx = re.search(r"\bsfx:\s*(['\"])([\w-]+)\1", block)
        visual = re.search(r"\bvisual:\s*(['\"])(.*?)\1", block, re.S)
        try:
            t = float(m.group(1).strip())
        except ValueError:
            continue  # 表达式：若在 Array.from 惯用法内由下方展开
        cues.append((t, visual.group(2) if visual else "", sfx.group(2) if sfx else ""))
    # 展开式事件序列惯用法：...Array.from({length: N}, (_, i) => ({ t: A + i * STEP, sfx: 'X' }))
    # （promo 片接力点亮判例）。密事件序列写这条，解析器展开成逐个 cue。
    unroll_spans = []
    for m in re.finditer(
            r"Array\.from\(\s*\{\s*length:\s*(\d+)\s*\}\s*,\s*\([^)]*\)\s*=>\s*\(\s*\{([^}]*)\}\s*\)\s*\)", text):
        unroll_spans.append(m.span())
        body = m.group(2)
        tm = re.search(r"\bt:\s*([\d.]+)\s*\+\s*i\s*\*\s*([\d.]+)", body)
        sm = re.search(r"\bsfx:\s*(['\"])([\w-]+)\1", body)
        vm = re.search(r"\bvisual:\s*(['\"])(.*?)\1", body, re.S)
        if tm and sm:
            for i in range(int(m.group(1))):
                cues.append((float(tm.group(1)) + i * float(tm.group(2)),
                             vm.group(2) if vm else "", sm.group(2)))
        elif "t:" in body and "sfx:" in body:
            cue_errs.append("Array.from 展开式只支持 { t: A + i * STEP, sfx: 'X' } 形状: " + body.strip()[:60])
    # 数字字面量与展开规则都没接住的 t 表达式 = 音频层会静默漏掉的事件，FAIL
    # （Array.from 展开式内层的表达式 t 已由上方规则处理，按区间排除）
    for m in re.finditer(r"\{[^{}]*\bt:\s*([^,{}]+)[^{}]*\bsfx:", text, re.S):
        if any(s <= m.start() < e for (s, e) in unroll_spans):
            continue
        tv = m.group(1).strip()
        try:
            float(tv)
        except ValueError:
            cue_errs.append(f"t 表达式无法求值: 't: {tv[:40]}'（写数字字面量，或用 Array.from 惯用法）")
    # DROPS/IMPACTS numeric arrays are legitimate flash carriers too (白闪照 impact 秒渲染)
    for m in re.finditer(r"export const (?:DROPS|IMPACTS)\s*=\s*\[([^\]]*)\]", text):
        for n in re.finditer(r"[\d.]+", m.group(1)):
            cues.append((float(n.group(0)), "impact drop (DROPS/IMPACTS)", "impact"))
    return dur, dur_err, cues, cue_errs


_COPY_KEY = re.compile(r"\b(zh|en):\s*(['\"`])((?:\\[\s\S]|(?!\2).)*)\2", re.S)
# 字符串里可以有转义引号（'It\'s gone.'、"say \"hi\""）。旧写法读到第一个撇号就断，把 It\'s 截成 It\，
# 于是每一句带撇号的英文都报一次假的「表内英文未在代码中逐字找到」
_UNESCAPE = re.compile(r"\\(['\"`])")


def parse_seg_copy(seg: Path):
    """Scan seg JS for `zh:` / `en:` object-literal keys. Returns
    (tl_zh, tl_en, other_zh, other_en): timeline.js holds the copy CONTRACT (drift
    there is FAIL); other files' keys (QA palette boards, legends, older layouts)
    are advisory — matched against the table for the missing direction, swept as
    INFO otherwise. Backtick template literals are stripped of ${...} code."""
    tl_zh, tl_en, other_zh, other_en = [], [], [], []
    for f in seg.rglob("*.js"):
        if {"out", "qa", "fonts", "node_modules", "audio"} & set(f.parts):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        in_tl = f.name == "timeline.js"
        for m in _COPY_KEY.finditer(text):
            v = _UNESCAPE.sub(r"\1", re.sub(r"\$\{[^}]*\}", "", m.group(3)))
            if in_tl:
                (tl_zh if m.group(1) == "zh" else tl_en).append(v)
            else:
                (other_zh if m.group(1) == "zh" else other_en).append(v)
    return tl_zh, tl_en, other_zh, other_en


def cjk_literals(seg: Path):
    """All CJK-containing string literals in the seg's JS/HTML (info sweep)."""
    out = []
    files = list(seg.rglob("*.js")) + list(seg.rglob("*.html"))
    skip = {"out", "qa", "fonts", "node_modules", "audio"}
    for f in files:
        if skip & set(f.parts):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in re.finditer(r"(['\"`])((?:(?!\1)[^\n])+)\1", text):
            s = m.group(2)
            if re.search(r"[\u4e00-\u9fff]", s) and len(norm(s)) >= 2:
                out.append((f.relative_to(seg), s))
    return out


def refine_info(infos):
    """Dedupe literal-sweep INFO lines that are substrings of an already-flagged longer line."""
    kept = []
    for line in infos:
        if not any(line != other and _quote_of(line) in _quote_of(other) for other in infos):
            kept.append(line)
    return kept


def _quote_of(info_line: str) -> str:
    m = re.search(r"「(.*?)」", info_line)
    return norm(m.group(1)) if m else ""


def real_timeline(tl: Path):
    """让 node 真 import 这份 timeline.js，读出页面实际在用的 OFFSET / DUR / CUES。

    正则只认得 { t, sfx, visual } 三个字段，也展不开 row(...) 这类辅助函数：事件音的 gain / pan
    就是这样被 --export-cues 丢掉的（gen-sfx 只好按词表默认值出声，整条事件层比设计的响了一倍，
    把配乐的 drop 呼吸填平——2026-11-25 成片复测抓到）。
    返回 ({"OFFSET", "DUR", "CUES"} 或 None, 错误信息或 None)。模块 import 不了不算致命：调用方退回
    正则结果，但必须把「会丢什么」说出口。"""
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        return None, "找不到 node"
    code = ("import(process.argv[1]).then(m => process.stdout.write(JSON.stringify("
            "{ OFFSET: m.OFFSET, DUR: m.DUR, CUES: m.CUES ?? [] })))"
            ".catch(e => { process.stderr.write(String((e && e.message) || e)); process.exit(3); })")
    try:
        r = subprocess.run([node, "--input-type=module", "-e", code, tl.resolve().as_uri()],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"node 调用失败：{e}"
    if r.returncode != 0:
        return None, (r.stderr or "").strip()[-160:] or f"node 退出码 {r.returncode}"
    try:
        data = json.loads(r.stdout)
    except ValueError as e:
        return None, f"模块输出不是合法 JSON：{e}"
    if not isinstance(data, dict) or not isinstance(data.get("CUES"), list):
        return None, "模块没有导出 CUES 数组"
    return data, None


def _num(v):
    """把可能是数字的东西收成 float；不是数字（含 bool）返回 None。"""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--storyboard", default=None)
    ap.add_argument("--export-cues", default=None, metavar="PATH",
                    help="把各段 CUES（含 sfx 的音画事件）导出为 JSON（gen-sfx.py 消费）；"
                         "绝对秒 = 段偏移 + 段内 t，gain / pan / note 原样带出。审计 FAIL 也会导出（数据可用于调试）")
    args = ap.parse_args()

    project = Path(args.project)
    sb_path = Path(args.storyboard) if args.storyboard else project / "分镜与文案.md"
    fails, warns, infos = [], [], []

    if not sb_path.exists():
        print(f"FAIL  找不到分镜表 {sb_path}")
        sys.exit(1)
    rows, total = parse_storyboard(sb_path)
    if not rows:
        print("FAIL  分镜表没解析到逐镜行")
        sys.exit(1)
    sb_text_norm = norm(sb_path.read_text(encoding="utf-8"))

    segs = find_segs(project)
    if not segs:
        print("FAIL  项目目录下没有 seg* 段目录")
        sys.exit(1)

    # ── 1+2. per-seg copy / time / cue audit ─────────────────────────────
    # Two granularities: a storyboard cell may render as ONE code entry or as several
    # sentences; match at both cell level and sentence level.
    table_zh_cells, table_zh_sents = set(), {}
    for (a, b, _t, zh, _en, _tr) in rows:
        sents = table_sentences(zh)
        if norm(zh):
            table_zh_cells.add(norm(zh))
        for s in sents:
            table_zh_sents.setdefault(norm(s), s)
    table_en_norms = set()
    for (_a, _b, _t, _zh, en, _tr) in rows:
        if norm(en):
            table_en_norms.add(norm(en))
        for s in re.split(r"[/;]", en) if en else []:
            if norm(s):
                table_en_norms.add(norm(s))

    table_flash_windows = [(a, b) for (a, b, _t, _zh, _en, tr) in rows
                           if ("白闪" in tr or "闪" in tr)]
    code_flash_times = []
    all_cues = []  # (seg_name, seg_lo, t, sfx, visual)
    export_rows = []  # 同上 + 真实 cue 对象（带 gain / pan / note；正则见到的为 None）
    offset, sum_dur = 0.0, 0.0
    boundaries = []
    all_code_zh, all_code_en, all_advisory_zh = [], [], []

    for seg in segs:
        tl = seg / "timeline.js"
        if not tl.exists():
            fails.append(f"{seg.name}: 缺 timeline.js（段真相源）")
            continue
        dur, dur_err, cues, cue_errs = parse_timeline(tl)
        for err in cue_errs:
            fails.append(f"{seg.name}: CUES {err}")
        real, real_err = real_timeline(tl)
        real_dur = _num(real.get("DUR")) if real is not None else None
        if real_dur is not None and (dur is None or dur_err):
            infos.append(f"{seg.name}: DUR 表达式正则求不出，按真实模块的 {real_dur:g}s 对账")
            dur, dur_err = float(real_dur), None
        tl_zh, tl_en, other_zh, other_en = parse_seg_copy(seg)
        if dur_err:
            warns.append(f"{seg.name}: {dur_err}，时间对账 NOT CHECKED")
        elif dur is None:
            warns.append(f"{seg.name}: timeline.js 没有 DUR 常量，时间对账 NOT CHECKED")
        else:
            if dur > 45:
                fails.append(f"{seg.name}: DUR {dur}s > 45s 段上限")
            boundaries.append((seg.name, offset, offset + dur))
            sum_dur += dur
            offset += dur
        seg_lo = offset - (dur or 0)
        # 事件表以真实模块为准（字段全带）；正则多见到的（别的 CUES* 数组、DROPS/IMPACTS）照样校验，一个不漏
        cues = [(t, v, s, None) for (t, v, s) in cues]
        if real is None:
            warns.append(f"{seg.name}: 读不到真实 CUES（{real_err}）——退回正则解析："
                         "辅助函数展开的事件不校验，导出的 gain / pan 会丢")
        else:
            mod_off = _num(real.get("OFFSET"))
            if mod_off is not None and abs(mod_off - seg_lo) > 0.01:
                fails.append(f"{seg.name}: OFFSET {mod_off:g}s ≠ 前面各段 DUR 之和 {seg_lo:g}s（页面的绝对时间会错位）")
            if real_dur is not None and dur is not None and abs(real_dur - dur) > 0.01:
                fails.append(f"{seg.name}: DUR 正则求值 {dur:g}s ≠ 真实模块 {real_dur:g}s")
            real_cues = [(_num(c["t"]), str(c.get("visual") or ""), str(c.get("sfx") or ""), c)
                         for c in real["CUES"] if isinstance(c, dict) and _num(c.get("t")) is not None]
            bad = len(real["CUES"]) - len(real_cues)
            if bad:
                fails.append(f"{seg.name}: 真实 CUES 里有 {bad} 条形状不对（不是对象，或 t 不是数字）")
            seen = {(round(t, 3), s) for (t, _v, s, _c) in real_cues}
            n_reg = sum(1 for c in cues if c[2])
            n_real = sum(1 for c in real_cues if c[2])
            if n_reg != n_real:
                infos.append(f"{seg.name}: 正则见到 {n_reg} 条带音效的事件，真实 CUES 有 {n_real} 条"
                             "（差在辅助函数展开式或别的 CUES* 数组）——两边都校验，导出以真实 CUES 为准")
            cues = real_cues + [c for c in cues if c[2] and (round(c[0], 3), c[2]) not in seen]
        for (t, visual, sfx, src) in cues:
            if dur is not None and (t < -0.01 or t > dur + 0.01):
                fails.append(f"{seg.name}: CUES t={t}s 超出段时长 {dur:g}s（音画事件必须落在本段内）")
            if sfx and sfx not in SFX_WORDS:
                warns.append(f"{seg.name}: CUES sfx='{sfx}' 不在词表（gen-sfx 会跳过；确认拼写或先扩词表）: t={t}")
            if sfx:
                all_cues.append((seg.name, seg_lo, t, sfx, visual))
                export_rows.append((seg.name, seg_lo, t, sfx, visual, src))
            if re.search(r"flash|闪", visual, re.I):
                code_flash_times.append((seg.name, t, seg_lo + t, visual))
        all_code_zh += [(seg.name, z) for z in tl_zh if norm(z)]
        all_advisory_zh += [(seg.name, z) for z in other_zh if norm(z)]
        all_code_en += [(seg.name, e) for e in tl_en + other_en if norm(e)]

    # copy audit: table -> code (missing) and code -> table (drift), both granularities
    code_zh_norms = {norm(z) for (_seg, z) in all_code_zh}
    for n, orig in table_zh_sents.items():
        if n not in code_zh_norms and n not in table_zh_cells.intersection(code_zh_norms) \
                and not any(n in cz for cz in code_zh_norms):
            fails.append(f"表内字幕未在代码 COPY 中找到（漏拍/改写）: {orig[:28]}")
    for (seg_name, z) in all_code_zh:
        nz = norm(z)
        if nz not in table_zh_sents and nz not in table_zh_cells \
                and not any(cz in nz or nz in cz for cz in table_zh_sents):
            fails.append(f"{seg_name}: 代码 COPY 字幕在分镜表中不存在（字幕漂移类）: {z[:28]}")
    for (seg_name, z) in all_advisory_zh:
        nz = norm(z)
        if nz not in table_zh_sents and nz not in table_zh_cells \
                and not any(cz in nz or nz in cz for cz in table_zh_sents):
            infos.append(f"{seg_name}: 非契约文件的 zh 字串不在表内（INFO 仅报备）: {z[:28]}")
    code_en_norms = {norm(e) for (_seg, e) in all_code_en}
    for (_a, _b, _t, _zh, en, _tr) in rows:
        parts = [norm(s) for s in (re.split(r"[/;]", en) if en else [])]
        if norm(en) and norm(en) not in code_en_norms \
                and not any(p and p in ce for p in parts for ce in code_en_norms):
            warns.append(f"表内英文未在代码中逐字找到（允许微调，人工确认）: {en[:36]}")

    if sum_dur and abs(sum_dur - total) > 0.01:
        fails.append(f"各段 DUR 总和 {sum_dur:.0f}s ≠ 分镜表总时长 {total:.0f}s")
    for (name, lo, hi) in boundaries:
        for (a, b, *_r) in rows:
            if a < hi - 0.01 and b > hi + 0.01 and a >= lo - 0.01 and a < hi:
                fails.append(f"镜头 {a:.0f}-{b:.0f}s 跨段界 {name}({hi:.0f}s)——段界必须是切点")

    # white-flash whitelist. Cue seconds sit ON the bar line (转折秒), and the table may
    # write the flash on either the exiting or the entering row — so each row's window
    # is the closed interval [a, b].
    for (seg_name, t, abs_t, visual) in code_flash_times:
        if not any(a - 0.01 <= abs_t <= b + 0.01 for (a, b) in table_flash_windows):
            fails.append(f"{seg_name}: 代码白闪 cue t={t}s (绝对 {abs_t:.0f}s) 不在任何白闪转场窗内: {visual[:30]}")
    for (a, b) in table_flash_windows:
        if not any(a - 0.01 <= abs_t <= b + 0.01 for (_s, _t, abs_t, _v) in code_flash_times):
            warns.append(f"表 {a:.0f}-{b:.0f}s 白闪转场在代码 CUES 中无对应 cue（确认实现方式）")

    # ── 4. literal sweep (report-only) ──────────────────────────────────
    for seg in segs:
        for (rel, s) in cjk_literals(seg):
            if norm(s) in sb_text_norm:
                continue
            infos.append(f"{seg.name}/{rel}: 「{s[:32]}」不在分镜表文本中——确认可溯源；工单允许的增补应回写表内")
    infos = refine_info(infos)

    years = set()
    for seg in segs:
        for f in list(seg.rglob("*.js")):
            if {"out", "qa", "fonts", "node_modules"} & set(f.parts):
                continue
            try:
                years |= set(re.findall(r"\b(?:19|20)\d{2}\b", f.read_text(encoding="utf-8")))
            except UnicodeDecodeError:
                pass
    if years:
        infos.append(f"代码中出现的年份字面量（须能溯源到文献卡/调研）: {sorted(years)}")

    for w in warns:
        print(f"WARN  {w}")
    for i in infos:
        print(f"INFO  {i}")
    for f in fails:
        print(f"FAIL  {f}")
    print(f"--- {len(segs)} 段 · 表 {total:.0f}s vs 段和 {sum_dur:.0f}s · COPY {len(all_code_zh)} 条 · "
          f"CUES {len(all_cues)} 个音画事件 · FAIL {len(fails)} · WARN {len(warns)} · INFO {len(infos)}")

    if args.export_cues:
        import json
        out = []
        for (s, seg_lo, t, sfx, v, src) in export_rows:
            row = {"seg": s, "t": round(float(t), 3), "abs_t": round(seg_lo + float(t), 3), "sfx": sfx, "visual": v}
            for k in ("gain", "pan", "pitch"):
                if src is not None and k in src:
                    row[k] = src[k]
            if src is not None and "note" in src:
                row["desc"] = src["note"]    # timeline 的 note 是给人读的说明；bell / pop 的音高另走 pitch
            out.append(row)
        dst = Path(args.export_cues)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        n_gain = sum(1 for r in out if "gain" in r)
        print(f"CUES → {dst}（{len(out)} 个事件，含绝对秒；{n_gain} 个带 gain；gen-sfx.py 消费）"
              + ("——注意：有段落退回了正则解析，见上面的 WARN" if any(r[5] is None for r in export_rows) else "")
              + ("——注意：审计存在 FAIL，导出仅供调试" if fails else ""))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
