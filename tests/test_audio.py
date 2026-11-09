import wave

import numpy as np

from studio.audio import lipsync, soundscape


def test_soundscapes_finite():
    rng = np.random.default_rng(1)
    n = soundscape.SR * 2
    for y in (soundscape.wind(n, rng), soundscape.birds(n, rng), soundscape.fire(n, rng), soundscape.rain(n, rng),
              soundscape.music(n, rng, "tension"), soundscape.cave(n, rng)):
        assert y.shape[0] == n and np.isfinite(y).all() and np.abs(y).max() < 4


def test_acoustic_lipsync(tmp_path):
    sr = 48000
    t = np.arange(sr) / sr
    x = (0.3 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 3 * t) > 0)).astype(np.float32)
    p = tmp_path / "v.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    W, method = lipsync.acoustic(p)
    W = np.array(W)
    assert method == "acoustique" and W.shape == (30, 4)
    assert W[:, 0].max() > 0.3 and W[:, 0].min() < 0.1  # la bouche s'ouvre et se ferme
