"""Rendu réel de contrôle (Blender) : personnages, décor, caméra. Exécuté en CI avant toute évolution."""
import json
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from conftest import ROOT

pytestmark = [pytest.mark.blender, pytest.mark.skipif(not shutil.which("blender"), reason="Blender requis")]

PLAN = {"fps": 30, "shots": [
    {"id": "t1", "f0": 0, "f1": 40, "location": "village_premiers", "tod": "dusk",
     "camera": {"type": "two", "subject": "bo", "target": "grumm"},
     "cast": {"grumm": {"pos": [-0.7, -2.9], "look": [[0, "bo"]], "emotion": [[0, "worried"]]},
              "bo": {"pos": [0.7, -2.8], "look": [[0, "grumm"]], "gestures": [{"f": 0, "name": "point"}],
                     "mouth": {"f0": 0, "w": [[0.8, 0, 0, 0]] * 40}}}},
    {"id": "t2", "f0": 40, "f1": 80, "location": "foret_mysterieuse", "tod": "day", "weather": "rain",
     "camera": {"type": "track", "subject": "nala"},
     "cast": {"nala": {"pos": [-2, -1], "walks": [{"f0": 40, "f1": 80, "to": [1, -1]}]}}},
]}


def test_render_smoke(tmp_path):
    pf = tmp_path / "plan.json"
    pf.write_text(json.dumps(PLAN))
    cmd = ["blender", "-b", "-noaudio", "-P", str(ROOT / "studio/animation/render_shots.py"), "--", str(pf), str(tmp_path),
           "all", "--preview", "--frames", "5,30"]
    if shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a"] + cmd
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    assert "Traceback" not in r.stdout + r.stderr, (r.stdout + r.stderr)[-3000:]
    for sid in ("t1", "t2"):
        for idx in (5, 30):
            im = np.asarray(Image.open(tmp_path / sid / f"{idx:04d}.png").convert("L"), np.float32)
            assert im.mean() > 20, f"{sid}/{idx} trop sombre"
            assert im.std() > 12, f"{sid}/{idx} image uniforme (rien n'a été rendu ?)"
    # la marche déplace réellement le personnage
    a = np.asarray(Image.open(tmp_path / "t2" / "0005.png").convert("L"), np.float32)
    b = np.asarray(Image.open(tmp_path / "t2" / "0030.png").convert("L"), np.float32)
    assert np.abs(a - b).mean() > 2
