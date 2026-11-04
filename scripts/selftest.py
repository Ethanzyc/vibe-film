#!/usr/bin/env python3
"""Planted-fault selftest for the vibe-film checkers (checker validity:
"a control that doesn't fail means the check is broken").

Every checker change must pass this BEFORE it ships: a good fixture must pass both
checkers, and each planted fault must be caught with the expected message. Fixtures
are materialised into a temp dir and both checkers run as subprocesses — the same
way an agent would run them.

  python3 selftest.py            # run all cases
Exit 0 = every control and every planted fault behaved as designed.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

GOOD_STORYBOARD = """| 时间 | 镜头类型 | 字幕中 | 字幕 EN | 背景 | 中景 | 前景/微文案 | 转场 | 情绪色 |
|---|---|---|---|---|---|---|---|---|
| 0-3 | 钩子帧 | 凌晨一点，你还在找。⟨找⟩ | One a.m., still searching. | 星场微动 | 剪影+caret 闪 | `01:00:00` | 开场无切 | 雾蓝 |
| 3-6 | 概念帧 | 它明明就在那里。⟨明明⟩ | It was right there. | 网格缓移 | 光点路径 | `cache: miss` | 硬切 | 青灰 |
| 6-9 | 金句帧 | 记忆是重写。⟨重写⟩ | Memory is rewriting. | 粒子聚散 | 金句大字 | `rw: 1` | 白闪+impact | 琥珀 |
| 9-12 | 金句帧 | 每次回忆都在改写。⟨改写⟩ | Every recall rewrites. | 粒子聚散 | 金句大字 | `rw: 2` | 无切 | 琥珀 |
| 12-15 | 献给帧 | 献给每一个，怕忘记的人。 | To everyone afraid of forgetting. | 晨光星场 | 两行逐词 | `FOR THE ONES` | 无切 | 晨金 |
"""

GOOD_TABLE_6S = """| 时间 | 镜头类型 | 字幕中 | 字幕 EN | 背景 | 中景 | 前景/微文案 | 转场 | 情绪色 |
|---|---|---|---|---|---|---|---|---|
| 0-3 | 钩子帧 | 凌晨一点，你在找文章。⟨文章⟩ | One a.m. — searching for the piece. | 星场微动 | 剪影 | `01:00` | 开场无切 | 雾蓝 |
| 3-6 | 概念帧 | 它不在了。⟨不在⟩ | It is gone. | 网格缓移 | 光点熄灭 | `cache: miss` | 白闪+impact | 青灰 |
"""

GOOD_TIMELINE = """// timeline.js — selftest fixture (contract layout)
export const DUR = 6;
export const CUES = [
  { t: 3, sfx: 'impact', visual: 'white flash, exactly 1 frame' },
];
export const COPY = [
  { zh: '凌晨一点，你在找文章。', tok: [], gold: [2], en: 'One a.m. — searching for the piece.' },
  { zh: '它不在了。', tok: [], gold: [1], en: 'It is gone.' },
];
"""

# 真曲网格模式 fixture：边界钉在检测下拍上（模拟 We Never 0.9x 网格）
BEAT_TABLE = GOOD_STORYBOARD
for _old, _new in (("| 0-3 |", "| 0-1.695 |"), ("| 3-6 |", "| 1.695-3.808 |"),
                   ("| 6-9 |", "| 3.808-5.933 |"), ("| 9-12 |", "| 5.933-8.022 |"),
                   ("| 12-15 |", "| 8.022-10.136 |")):
    BEAT_TABLE = BEAT_TABLE.replace(_old, _new)
BEATS_JSON = """{"engine": "numpy", "bpm": 113.58,
 "beats": [0.104, 0.639, 1.173, 1.695, 2.229, 2.752, 3.274, 3.808, 4.342, 4.865,
           5.399, 5.933, 6.42, 6.954, 7.488, 8.022, 8.545, 9.079, 9.601, 10.136],
 "downbeats": [1.695, 3.808, 5.933, 8.022, 10.136]}"""

results = []


def run(script, *args):
    p = subprocess.run([sys.executable, str(HERE / script), *args],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(("PASS  " if cond else "FAIL  ") + name + (f"  [{detail}]" if not cond and detail else ""))


def write_project(root: Path, table: str, timeline: str):
    seg = root / "seg1"
    seg.mkdir(parents=True, exist_ok=True)
    (root / "分镜与文案.md").write_text(table, encoding="utf-8")
    (seg / "timeline.js").write_text(timeline, encoding="utf-8")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="vibe-selftest-"))
    try:
        # ── check-storyboard ────────────────────────────────────────────
        good = tmp / "sb-good.md"
        good.write_text(GOOD_STORYBOARD, encoding="utf-8")
        rc, out = run("check-storyboard.py", str(good), "--dur", "15")
        check("storyboard 好 fixture 通过", rc == 0, out)

        gap = tmp / "sb-gap.md"
        gap.write_text(GOOD_STORYBOARD.replace("| 6-9 |", "| 7-9 |"), encoding="utf-8")
        rc, out = run("check-storyboard.py", str(gap), "--dur", "15")
        check("planted 时间不连续被抓", rc == 1 and "时间不连续" in out, out)

        noEN = tmp / "sb-noen.md"
        noEN.write_text(GOOD_STORYBOARD.replace("| It was right there. |", "| |"), encoding="utf-8")
        rc, out = run("check-storyboard.py", str(noEN), "--dur", "15")
        check("planted 缺英文被抓", rc == 1 and "英文" in out, out)

        noDed = tmp / "sb-noded.md"
        noDed.write_text(GOOD_STORYBOARD.replace("献给帧", "收束帧"), encoding="utf-8")
        rc, out = run("check-storyboard.py", str(noDed), "--dur", "15")
        check("planted 缺献给被抓", rc == 1 and "献给" in out, out)

        col8 = tmp / "sb-col8.md"
        col8.write_text(GOOD_STORYBOARD.replace("| 粒子聚散 | 金句大字 | `rw: 1` |", "| 粒子聚散 | 金句大字 |"), encoding="utf-8")
        rc, out = run("check-storyboard.py", str(col8), "--dur", "15")
        check("planted 8 列被抓", rc == 1 and "列数" in out, out)

        # ── check-storyboard 真曲网格模式（--grid，2026-10-27 拍板）────────
        (tmp / "beats.json").write_text(BEATS_JSON, encoding="utf-8")
        beat = tmp / "sb-beat.md"
        beat.write_text(BEAT_TABLE, encoding="utf-8")
        rc, out = run("check-storyboard.py", str(beat), "--dur", "10.136",
                      "--grid", str(tmp / "beats.json"))
        check("storyboard 真曲网格好 fixture 通过", rc == 0, out)

        offgrid = tmp / "sb-offgrid.md"
        offgrid.write_text(BEAT_TABLE.replace("| 5.933-8.022 |", "| 5.933-8.1 |"), encoding="utf-8")
        rc, out = run("check-storyboard.py", str(offgrid), "--dur", "10.213",
                      "--grid", str(tmp / "beats.json"))
        check("planted 真曲边界脱网格被抓", rc == 1 and "节拍网格" in out, out)

        decimal = tmp / "sb-decimal.md"
        decimal.write_text(GOOD_STORYBOARD.replace("| 3-6 |", "| 3-6.5 |"), encoding="utf-8")
        rc, out = run("check-storyboard.py", str(decimal), "--dur", "15")
        check("planted 合成曲模式非 3s 倍数被抓", rc == 1 and "3s 正倍数" in out, out)

        # ── check-build ────────────────────────────────────────────────
        goodP = tmp / "proj-good"
        write_project(goodP, GOOD_TABLE_6S, GOOD_TIMELINE)
        rc, out = run("check-build.py", str(goodP))
        check("check-build 好 fixture 通过", rc == 0, out)

        driftP = tmp / "proj-drift"
        write_project(driftP, GOOD_TABLE_6S, GOOD_TIMELINE.replace("它不在了。', tok", "它真的不在了。', tok"))
        rc, out = run("check-build.py", str(driftP))
        check("planted 字幕漂移被抓", rc == 1 and "漂移" in out, out)

        missP = tmp / "proj-miss"
        miss_tl = GOOD_TIMELINE.replace(
            "  { zh: '它不在了。', tok: [], gold: [1], en: 'It is gone.' },\n", "")
        write_project(missP, GOOD_TABLE_6S, miss_tl)
        rc, out = run("check-build.py", str(missP))
        check("planted 漏拍被抓", rc == 1 and "未在代码" in out, out)

        durP = tmp / "proj-dur"
        write_project(durP, GOOD_TABLE_6S, GOOD_TIMELINE.replace("DUR = 6", "DUR = 9"))
        rc, out = run("check-build.py", str(durP))
        check("planted DUR 不符被抓", rc == 1 and "总时长" in out, out)

        flashP = tmp / "proj-flash"
        write_project(flashP, GOOD_TABLE_6S,
                      GOOD_TIMELINE.replace("{ t: 3,", "{ t: 1,").replace("exactly 1 frame", "1 frame"))
        rc, out = run("check-build.py", str(flashP))
        check("planted 白闪脱白名单被抓", rc == 1 and "白闪" in out, out)

        # ── check-build CUES 事件层（v1.8.0：音画同表）─────────────────────
        sfxP = tmp / "proj-sfx"
        write_project(sfxP, GOOD_TABLE_6S, GOOD_TIMELINE.replace(
            "export const COPY",
            "export const CUES2 = [{ t: 2.5, sfx: 'bell' }, { t: 9.5, sfx: 'tick' }, { t: 5, sfx: 'wat' }];\nexport const COPY"))
        rc, out = run("check-build.py", str(sfxP))
        check("planted CUES 超段时长被抓", rc == 1 and "超出段时长" in out, out)
        check("planted CUES 未知词被 WARN", "不在词表" in out and "wat" in out, out)

        exp = tmp / "cues.json"
        rc, out = run("check-build.py", str(goodP), "--export-cues", str(exp))
        import json as _json
        data = _json.loads(exp.read_text(encoding="utf-8"))
        check("export-cues 导出内容正确", rc == 0 and len(data) == 1
              and data[0]["sfx"] == "impact" and abs(data[0]["abs_t"] - 3) < 0.01, out + str(data))

        gs = (HERE / "gen-sfx.py").read_text(encoding="utf-8")
        cbt = (HERE / "check-build.py").read_text(encoding="utf-8")
        w1 = set(__import__("re").findall(r'"(\w+)"', __import__("re").search(r"WORDS = \{([^}]*)\}", gs).group(1)))
        w2 = set(__import__("re").findall(r'"(\w+)"', __import__("re").search(r"SFX_WORDS = \{([^}]*)\}", cbt).group(1)))
        check("SFX 词表双处一致（gen-sfx ↔ check-build）", w1 == w2, f"{sorted(w1 ^ w2)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for (n, ok, _d) in results if not ok]
    print(f"--- selftest {len(results)} 例 · FAIL {len(bad)}")
    for n in bad:
        print(f"FAIL  {n}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
