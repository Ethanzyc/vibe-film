#!/usr/bin/env python3
"""SFX 合成原语共享库 —— gen-audio.py（BGM 内嵌音效）与 gen-sfx.py（CUES 事件层）共用。
单一实现防漂移：改任何一个音色，两条产线同时生效。
机制来源：motion-showreel synth.mjs 词表（2026-10-27 调研迁移）+ 本产线 impact/whoosh/riser 判例。
所有函数确定性（rng 由调用方传入，seed 相同则逐字节复现）。
"""
import numpy as np

SR = 44100
WHOOSH_PEAK = 0.72  # whoosh 最响点在 0.72×dur：放置 = 事件秒 − 0.72×dur，峰值钉在事件上


def env_ar(n, a, r, sus=1.0):
    na = min(int(a * SR), n // 2)
    nr = min(int(r * SR), n // 2)
    e = np.full(n, sus, dtype=float)
    if na > 0:
        e[:na] *= np.linspace(0, 1, na)
    if nr > 0:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def place(dst, sig, at, gain=1.0, pan=0.0):
    """把单声道片段放进立体声 dst (L, R)，at 秒处；等功率声像。越界部分截断。"""
    s0 = int(at * SR)
    n = min(len(sig), len(dst[0]) - s0)
    if n <= 0:
        return
    th = (pan + 1) * np.pi / 4
    gl, gr = np.cos(th) * np.sqrt(2), np.sin(th) * np.sqrt(2)
    dst[0][s0:s0 + n] += sig[:n] * gain * gl * 0.7071
    dst[1][s0:s0 + n] += sig[:n] * gain * gr * 0.7071


# ── 冲击类（gen-audio 判例：impact 瞬态片两级限幅配方按这些瞬态调的）──
def impact(rng, dur=0.55, f0=90.0, f1=38.0, decay=6.0, noise_amt=0.3):
    tt = np.arange(int(dur * SR)) / SR
    f = f0 * np.exp(-4.0 * tt) + f1
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-decay * tt)
    air = rng.standard_normal(len(tt)) * np.exp(-decay * 1.6 * tt) * noise_amt
    return np.tanh((body + air) * 1.4)


def big_impact(rng):
    tt = np.arange(int(1.0 * SR)) / SR
    f = 70.0 * np.exp(-3.0 * tt) + 30.0
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-3.2 * tt)
    sub = np.sin(2 * np.pi * 45.0 * tt) * np.exp(-2.5 * tt) * 0.6
    air = rng.standard_normal(len(tt)) * np.exp(-4.0 * tt) * 0.35
    return np.tanh((body + sub + air) * 1.5)


def boom(rng):
    from numpy import fft as _npfft  # noqa: F401  (保持与 impact 同族，低通版)
    b = impact(rng, dur=0.9, f0=70.0, f1=32.0, decay=4.0, noise_amt=0.2)
    spec = np.fft.rfft(b)
    k = int(180 / (SR / 2) * len(spec))
    spec[k:] *= np.linspace(1, 0, max(1, len(spec) - k))
    return np.fft.irfft(spec, len(b)) * 1.3


def whoosh(rng, dur=0.7):
    n = int(dur * SR)
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    y = 0.0
    for i in range(n):
        alpha = 0.04 + 0.31 * (i / n)
        y += alpha * (noise[i] - y)
        out[i] = y
    x = np.linspace(0, 1, n)
    env = np.where(x < WHOOSH_PEAK,
                   (x / WHOOSH_PEAK) ** 2.2,
                   np.exp(-(x - WHOOSH_PEAK) / (1 - WHOOSH_PEAK) * 3.0))
    return out * env


def riser(rng, dur=3.0):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    f = 80.0 * (2 ** (tt / dur * 2.0))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR)
    noise = rng.standard_normal(n) * 0.4
    env = (tt / dur) ** 2.2
    env[-int(0.3 * SR):] *= np.linspace(1, 0, int(0.3 * SR))  # 提前收口留呼吸窗
    return np.tanh((body * 0.6 + noise) * env * 1.2)


def downlifter(rng, dur=1.0):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    f = 2500.0 * (80.0 / 2500.0) ** (tt / dur)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR)
    noise = rng.standard_normal(n) * 0.3
    return np.tanh((body * 0.5 + noise) * (1 - tt / dur) ** 1.6 * 0.9)


# ── UI/事件类（ai-studio-promo 判例：bell=点亮、tick=知识星、密度即推进）──
def bell(rng, note=88.0, dur=1.2, ratio=3.01, index=3.2):
    """FM 玻璃钟（节点点亮/金句点亮）。note=载波频率 Hz 或 MIDI 数字。"""
    f = 440.0 * 2 ** ((note - 69) / 12) if note < 128 else note
    n = int(dur * SR)
    tt = np.arange(n) / SR
    mod = index * np.exp(-tt / (dur * 0.35)) * np.sin(2 * np.pi * f * ratio * tt)
    body = np.sin(2 * np.pi * f * tt + mod) * np.exp(-tt / (dur * 0.3))
    return body * env_ar(n, 0.002, 0.08)


def tick(tone=1.0):
    n = int(0.03 * SR)
    tt = np.arange(n) / SR
    return np.sin(2 * np.pi * 4400 * tone * tt) * np.exp(-tt / 0.006) * env_ar(n, 0.0002, 0.005)


def pop(rng, f0=1046.5, dur=0.07):
    """元素弹出：音高随元素大小（大低小高），f0 传入基频。"""
    n = int(dur * SR)
    tt = np.arange(n) / SR
    f = f0 * (1 - 0.4 * np.exp(-tt / 0.012))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / (dur / 4)) * env_ar(n, 0.001, 0.01)


def click(rng):
    n = int(0.03 * SR)
    tt = np.arange(n) / SR
    noise = rng.standard_normal(n) * np.exp(-tt / 0.0018)
    hi = np.diff(np.concatenate([[0], noise]))  # 一阶差分 ≈ 高通
    return (hi * 0.8 + np.sin(2 * np.pi * 2600 * tt) * np.exp(-tt / 0.004) * 0.7) * env_ar(n, 0.0002, 0.005)


def swipe(rng, dur=0.22, up=True):
    n = int(dur * SR)
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    y = 0.0
    for i in range(n):
        x = i / n
        alpha = (0.04 + 0.3 * x) if up else (0.34 - 0.3 * x)
        y += alpha * (noise[i] - y)
        out[i] = y
    return out * np.sin(np.pi * np.linspace(0, 1, n)) * 2.2


PENTA = [440.0, 523.25, 587.33, 659.25, 783.99, 880.0]


def shimmer(rng, dur=1.5, count=9):
    """粒子聚合/全亮/成功：五声音阶随机泛音簇（seeded 确定性）。"""
    n = int(dur * SR)
    out = np.zeros(n)
    for _ in range(count):
        f = PENTA[int(rng.integers(0, len(PENTA)))] * (2 ** int(rng.integers(0, 2)))
        st = int(rng.uniform(0, dur * 0.6) * SR)
        seg = int(min(dur - st / SR, 0.9) * SR)
        if seg <= 0:
            continue
        tt = np.arange(seg) / SR
        tone = np.sin(2 * np.pi * f * tt) * np.exp(-tt / (0.25 + rng.uniform(0, 0.3))) * env_ar(seg, 0.004, 0.05)
        out[st:st + seg] += tone * 0.28
    return out
