"""Synchronisation labiale : poids de visèmes par image [ouvert, large, rond, f/v].

- Rhubarb Lip Sync (MIT) s'il est installé (reconnaissance phonétique indépendante de la langue).
- Sinon : analyse acoustique (énergie, centroïde spectral, passages par zéro) — approximation honnête,
  bien synchronisée sur le rythme de la voix, moins précise sur les consonnes.
"""
import json
import shutil
import subprocess
import wave

import numpy as np

RHUBARB_MAP = {  # forme Rhubarb -> (open, wide, round, fv)
    "A": (0.0, 0.0, 0.0, 0.0), "B": (0.22, 0.25, 0.0, 0.0), "C": (0.55, 0.45, 0.0, 0.0), "D": (0.95, 0.15, 0.0, 0.0),
    "E": (0.5, 0.0, 0.5, 0.0), "F": (0.15, 0.0, 0.9, 0.0), "G": (0.1, 0.0, 0.0, 1.0), "H": (0.4, 0.2, 0.0, 0.0),
    "X": (0.0, 0.0, 0.0, 0.0),
}


def read_wav(path):
    with wave.open(str(path)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(1)
    return x, sr


def _smooth(W, fps):
    out = W.copy()
    for i in range(1, len(W)):
        a = 0.65 if W[i].sum() > out[i - 1].sum() else 0.45  # ouverture rapide, fermeture plus douce
        out[i] = out[i - 1] + (W[i] - out[i - 1]) * a
    return out


def acoustic(path, fps=30):
    x, sr = read_wav(path)
    hop = sr // fps
    n = max(1, len(x) // hop)
    W = np.zeros((n, 4), np.float32)
    rms = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2) + 1e-9) for i in range(n)])
    peak = np.percentile(rms, 95) + 1e-6
    win = np.hanning(hop * 2)
    for i in range(n):
        seg = x[max(0, i * hop - hop // 2): i * hop + hop * 3 // 2]
        if len(seg) < 64:
            continue
        e = min(1.0, rms[i] / peak)
        if e < 0.08:
            continue
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        freqs = np.fft.rfftfreq(len(seg), 1 / sr)
        cen = float((spec * freqs).sum() / (spec.sum() + 1e-9))
        zcr = float(np.mean(np.abs(np.diff(np.sign(seg)))) / 2)
        if zcr > 0.18 or cen > 3500:  # fricatives (s, f, ch) : bouche peu ouverte, dents
            W[i] = (0.15 * e, 0.3 * e, 0.0, 0.7 * e)
        elif cen < 900:  # voyelles arrondies (o, ou, u)
            W[i] = (0.45 * e, 0.0, 0.75 * e, 0.0)
        elif cen > 1900:  # voyelles étirées (i, é)
            W[i] = (0.45 * e, 0.7 * e, 0.0, 0.0)
        else:  # a, è
            W[i] = (min(1.0, 1.15 * e), 0.15 * e, 0.0, 0.0)
    del win
    return _smooth(W, fps), "acoustique"


def rhubarb(path, text, fps=30):
    exe = shutil.which("rhubarb")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-r", "phonetic", "-f", "json", "--extendedShapes", "GHX", str(path)],
                           capture_output=True, text=True, timeout=300, check=True)
        cues = json.loads(r.stdout)["mouthCues"]
    except Exception as e:
        print("Rhubarb indisponible :", e)
        return None
    end = cues[-1]["end"] if cues else 0
    n = int(end * fps) + 1
    W = np.zeros((n, 4), np.float32)
    for c in cues:
        for i in range(int(c["start"] * fps), min(n, int(c["end"] * fps) + 1)):
            W[i] = RHUBARB_MAP.get(c["value"], (0, 0, 0, 0))
    return _smooth(W, fps), "rhubarb"


def visemes(path, text="", fps=30):
    r = rhubarb(path, text, fps)
    if r is None:
        r = acoustic(path, fps)
    W, method = r
    return [[round(float(v), 3) for v in row] for row in W], method
