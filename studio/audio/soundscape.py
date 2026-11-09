"""Ambiances, bruitages et musique 100 % synthétisés (numpy) : aucune licence tierce, aucun fichier externe.

Tout est déterministe (graine = épisode) : relancer la production donne exactement le même son.
"""
import math

import numpy as np

SR = 48000


def _shape_noise(n, rng, lo, hi, tilt=0.0):
    """Bruit filtré dans le domaine fréquentiel (passe-bande lo-hi, pente tilt dB/octave)."""
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR) + 1
    g = ((f > lo) & (f < hi)).astype(np.float32)
    g *= (f / 1000) ** (tilt / 6.02)
    edge = np.clip((f - lo) / (lo * 0.5 + 1), 0, 1) * np.clip((hi - f) / (hi * 0.3 + 1), 0, 1)
    y = np.fft.irfft(X * g * edge, n)
    return (y / (np.abs(y).max() + 1e-9)).astype(np.float32)


def _lfo(n, rate, seed, depth=0.5):
    t = np.arange(n) / SR
    return (1 - depth) + depth * (0.5 + 0.5 * np.sin(2 * math.pi * rate * t + seed) * np.sin(2 * math.pi * rate * 0.37 * t + seed * 2))


def wind(n, rng, strength=1.0):
    return 0.10 * strength * _shape_noise(n, rng, 60, 1400, -4) * _lfo(n, 0.11, rng.random() * 6, 0.7)


def water(n, rng, kind="river"):
    lo, hi, a = (200, 5000, 0.07) if kind == "river" else (100, 1500, 0.035)
    return a * _shape_noise(n, rng, lo, hi, -2) * _lfo(n, 0.3, 1, 0.3)


def rain(n, rng):
    y = 0.09 * _shape_noise(n, rng, 800, 12000, -1)
    drops = np.zeros(n, np.float32)
    for _ in range(int(n / SR * 25)):
        i = rng.integers(0, n - 2000)
        drops[i:i + 300] += rng.uniform(0.02, 0.08) * np.exp(-np.arange(300) / 40) * rng.standard_normal(300)
    return y + drops


def birds(n, rng, density=0.35):
    y = np.zeros(n, np.float32)
    for _ in range(int(n / SR * density)):
        start = rng.integers(0, max(1, n - SR))
        f0 = rng.uniform(2500, 4800)
        notes = rng.integers(2, 6)
        pos = start
        for k in range(notes):
            d = int(rng.uniform(0.05, 0.14) * SR)
            t = np.arange(d) / SR
            sweep = f0 * (1 + rng.uniform(-0.25, 0.3) * t / t[-1])
            ph = 2 * math.pi * np.cumsum(sweep) / SR
            env = np.sin(np.pi * np.arange(d) / d) ** 2
            if pos + d < n:
                y[pos:pos + d] += 0.035 * env * np.sin(ph + 3 * np.sin(2 * math.pi * 30 * t))
            pos += d + int(rng.uniform(0.02, 0.1) * SR)
    return y


def crickets(n, rng):
    t = np.arange(n) / SR
    y = np.zeros(n, np.float32)
    for k in range(3):
        f = rng.uniform(4200, 5200)
        rate = rng.uniform(2.5, 4.0)
        gate = (np.sin(2 * math.pi * rate * t + k) > 0.6).astype(np.float32)
        chirp = (np.sin(2 * math.pi * 30 * t) > 0).astype(np.float32)
        y += 0.012 * np.sin(2 * math.pi * f * t) * gate * chirp
    return y


def fire(n, rng):
    y = 0.03 * _shape_noise(n, rng, 40, 400, -6) * _lfo(n, 0.7, 2, 0.5)
    for _ in range(int(n / SR * 9)):
        i = rng.integers(0, n - 800)
        L = int(rng.uniform(80, 500))
        y[i:i + L] += rng.uniform(0.04, 0.16) * rng.standard_normal(L) * np.exp(-np.arange(L) / (L / 4))
    return y


def rumble(n, rng):
    return 0.08 * _shape_noise(n, rng, 20, 160, -6) * _lfo(n, 0.05, 3, 0.5)


def cave(n, rng):
    y = 0.015 * _shape_noise(n, rng, 50, 600, -6)
    for _ in range(int(n / SR * 1.2)):
        i = rng.integers(0, n - SR)
        f = rng.uniform(900, 1800)
        L = int(0.12 * SR)
        t = np.arange(L) / SR
        drip = 0.06 * np.sin(2 * math.pi * f * t * (1 + 2 * t)) * np.exp(-t * 40)
        for k, (dl, g) in enumerate(((0, 1), (0.11, 0.45), (0.23, 0.25), (0.37, 0.12))):
            j = i + int(dl * SR)
            if j + L < n:
                y[j:j + L] += drip * g
    return y


def footstep(rng, surface="grass"):
    L = int(0.12 * SR)
    t = np.arange(L) / SR
    lo, hi = (150, 2500) if surface != "stone" else (300, 6000)
    s = _shape_noise(L, rng, lo, hi, -3) * np.exp(-t * 35)
    thump = np.sin(2 * math.pi * 70 * t) * np.exp(-t * 50)
    return (0.10 * s + 0.08 * thump).astype(np.float32)


def whoosh(rng):
    L = int(0.35 * SR)
    env = np.sin(np.pi * np.arange(L) / L) ** 2
    return (0.03 * _shape_noise(L, rng, 300, 3000, -3) * env).astype(np.float32)


# ------------------------------------------------------------------ musique
SCALES = {"minor": [0, 2, 3, 5, 7, 8, 10], "major": [0, 2, 4, 5, 7, 9, 11], "dorian": [0, 2, 3, 5, 7, 9, 10]}
PROGRESSIONS = {"tension": [0, 5, 2, 6], "calme": [0, 3, 4, 0], "mystere": [0, 1, 0, 6], "espoir": [0, 4, 5, 3]}


def _note(m):
    return 440 * 2 ** ((m - 69) / 12)


def _pad(freqs, dur, amp):
    L = int(dur * SR)
    t = np.arange(L) / SR
    y = np.zeros(L, np.float32)
    for f in freqs:
        for det in (-0.12, 0.0, 0.11):
            ff = f * 2 ** (det / 12)
            for h, ha in ((1, 1.0), (2, 0.35), (3, 0.15), (4, 0.06)):
                y += ha * np.sin(2 * math.pi * ff * h * t + det * 10)
    att = np.clip(t / (dur * 0.35), 0, 1)
    rel = np.clip((dur - t) / (dur * 0.35), 0, 1)
    return amp * y / (len(freqs) * 3 * 1.6) * att * rel


def _pluck(f, dur, amp):
    L = int(dur * SR)
    t = np.arange(L) / SR
    y = sum(a * np.sin(2 * math.pi * f * h * t) * np.exp(-t * (3 + h * 2.5)) for h, a in ((1, 1), (2, 0.5), (3, 0.25), (4, 0.12)))
    return amp * y.astype(np.float32)


def _drum(dur=0.7, amp=0.4):
    L = int(dur * SR)
    t = np.arange(L) / SR
    f = 60 + 50 * np.exp(-t * 25)
    return amp * np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 6)


def music(n, rng, mood="mystere", root=50, tempo=72):
    scale = SCALES["minor" if mood in ("tension", "mystere") else "major" if mood == "espoir" else "dorian"]
    prog = PROGRESSIONS.get(mood, PROGRESSIONS["mystere"])
    beat = 60 / tempo
    bar = beat * 4
    y = np.zeros(n + SR * 4, np.float32)
    pos, k = 0, 0
    while pos < n:
        deg = prog[k % len(prog)]
        chord = [root + scale[(deg + i) % 7] + 12 * ((deg + i) // 7) for i in (0, 2, 4)]
        seg = _pad([_note(m) for m in chord] + [_note(chord[0] - 12)], bar * 1.25, 0.16)
        y[pos:pos + len(seg)] += seg[: len(y) - pos]
        for b in range(8):  # arpège pincé (croches), quelques silences
            if rng.random() < 0.3:
                continue
            m = chord[rng.integers(0, 3)] + 12 * rng.integers(1, 3)
            p = pos + int(b * beat / 2 * SR)
            s = _pluck(_note(m), 1.2, 0.05)
            if p < len(y):
                y[p:p + len(s)] += s[: len(y) - p]
        if mood == "tension":
            for b in (0, 2.5):
                p = pos + int(b * beat * SR)
                d = _drum()
                if p < len(y):
                    y[p:p + len(d)] += d[: len(y) - p]
        pos += int(bar * SR)
        k += 1
    # réverbération simple (peignes)
    out = y.copy()
    for dl, g in ((0.031, 0.35), (0.047, 0.3), (0.071, 0.25), (0.113, 0.2), (0.173, 0.12)):
        d = int(dl * SR)
        out[d:] += g * y[:-d]
    return out[:n]


def bed(n, rng, location, tod, weather, spec):
    """Ambiance d'un plan selon le lieu, l'heure et la météo."""
    y = wind(n, rng, 1.6 if weather == "rain" else (0.5 if spec.get("cave") else 1.0))
    w = spec.get("water")
    if w:
        y += water(n, rng, "river" if w["type"] in ("river", "stream") else "lake")
    if weather == "rain":
        y += rain(n, rng)
    if spec.get("cave"):
        y += cave(n, rng)
    elif tod in ("day", "dawn") and weather != "rain":
        y += birds(n, rng, 0.45 if spec["trees"]["count"] > 20 else 0.2)
    elif tod in ("night", "dusk"):
        y += crickets(n, rng)
    if any(s["type"] == "campfire" for s in spec.get("structures", [])):
        y += fire(n, rng)
    if spec.get("lava") or any(l["type"] == "volcano" and l.get("active") for l in spec.get("landmarks", [])):
        y += rumble(n, rng)
    return y
