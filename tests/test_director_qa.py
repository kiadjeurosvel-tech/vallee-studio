"""Plan de tournage (voix eSpeak pour aller vite) + contrôle qualité sur une vidéo synthétique."""
import json
import os
import shutil
import subprocess

import pytest

from conftest import ROOT

pytestmark = pytest.mark.skipif(not shutil.which("espeak-ng") or not shutil.which("ffmpeg"), reason="espeak-ng/ffmpeg requis")


@pytest.fixture(scope="module")
def plan(tmp_path_factory):
    os.environ["STUDIO_TTS"] = "espeak"
    from studio import director
    ep = json.loads((ROOT / "story_queue" / "ep001.json").read_text())
    from studio.narrative import validate
    validate.normalize(ep)
    ep.update(number=1, date="2026-01-01")
    work = tmp_path_factory.mktemp("w")
    return director.plan(ep, work), work


def test_shots_cover_timeline(plan):
    p, _ = plan
    shots = p["shots"]
    assert shots[0]["f0"] == 0 and shots[-1]["f1"] == p["frames"]
    for a, b in zip(shots, shots[1:]):
        assert a["f1"] == b["f0"]
        assert a["f1"] > a["f0"]
    for d in p["dialogue"]:
        assert 0 <= d["start"] < d["end"] <= p["seconds"]


def test_mouths_match_shots(plan):
    p, _ = plan
    for sh in p["shots"]:
        for cid, c in sh["cast"].items():
            if "mouth" in c:
                assert len(c["mouth"]["w"]) == sh["f1"] - sh["f0"] + sh["handle"]


def test_qa_accepts_good_and_rejects_bad(plan, tmp_path):
    from studio.qa import check
    p, _ = plan
    small = dict(p, seconds=3.0, frames=90, shots=[dict(p["shots"][0], f0=0, f1=90)], dialogue=[])
    good = tmp_path / "good.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=3",
                    "-f", "lavfi", "-i", "sine=f=330:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(good)], check=True)
    rep = check.check(good, small)
    assert rep["ok"], rep["errors"]
    bad = tmp_path / "bad.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=720x1280:r=25:d=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(bad)], check=True)
    rep = check.check(bad, small)
    assert not rep["ok"] and len(rep["errors"]) >= 3
