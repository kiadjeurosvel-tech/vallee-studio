"""La mémoire de référence est figée : toute modification doit être volontaire (mise à jour de reference.lock)."""

from studio.narrative import memory
from conftest import ROOT


def test_reference_lock():
    lock = (ROOT / "memory" / "reference.lock").read_text().strip()
    assert memory.reference_fingerprint() == lock, (
        "Les références (visages, proportions, vêtements, couleurs, voix, décors) ont changé. "
        "Si c'est voulu : python -m studio.lock_reference")


def test_characters_complete():
    chars = memory.load("characters.json")["characters"]
    assert len(chars) == 10
    for cid, c in chars.items():
        L = c["reference"]["look"]
        for k in ("height", "build", "skin", "hair", "eyes", "tunic", "pants", "accessories"):
            assert k in L, (cid, k)
        v = c["reference"]["voice"]
        assert v["model"].startswith("fr_FR-") and "espeak" in v


def test_every_place_has_a_3d_set():
    geo = memory.load("geography.json")
    for p in geo["lieux"]:
        s = geo["sets3d"][p["id"]]
        assert "seed" in s and "center" in s["marks"]


def test_state_consistent():
    st = memory.load("state.json")
    w = memory.load("world.json")
    assert st["episode"] == (w["history"][-1]["episode"] if w["history"] else 0)
