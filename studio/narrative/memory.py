"""Mémoire permanente : lecture/écriture contrôlée de memory/*.json.

Règle : les blocs de référence (apparence, voix, décors) ne sont jamais réécrits ici.
Seuls state.json et world.json (état du monde, historique) évoluent, et uniquement par champs autorisés.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEM = ROOT / "memory"


def load(name):
    return json.loads((MEM / name).read_text(encoding="utf-8"))


def save(name, data):
    (MEM / name).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def reference_fingerprint():
    """Empreinte des éléments figés (personnages + décors + palette) : toute dérive est détectée par les tests."""
    chars = load("characters.json")["characters"]
    geo = load("geography.json")
    style = load("visual_style.json")
    ref = {
        "characters": {k: v["reference"] for k, v in sorted(chars.items())},
        "sets3d": geo.get("sets3d"),
        "places": geo.get("lieux"),
        "river": geo.get("riviere"),
        "time_of_day": style.get("time_of_day"),
        "look": style.get("look"),
    }
    return hashlib.sha256(json.dumps(ref, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def alive_characters():
    return {k: v for k, v in load("characters.json")["characters"].items() if v["status"] == "vivant"}


def berlin_today():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Europe/Berlin")).date()
    except Exception:
        return dt.datetime.utcnow().date()


ALLOWED_WORLD_KEYS = {"population", "nourriture", "eau", "bois", "pierre", "moral", "sante"}


def apply_episode(ep, vote):
    """Met à jour la mémoire après une production réussie."""
    state = load("state.json")
    world = load("world.json")
    n = ep["number"]
    world["history"].append({"episode": n, "date": ep["date"], "title": ep["title"], "location": ep["location"],
                             "vote_precedent": vote, "choice": ep["choice"], "source": ep["source"]})
    world["history"] = world["history"][-400:]
    for k, v in (ep.get("world_changes") or {}).items():
        if k in ALLOWED_WORLD_KEYS and isinstance(v, (int, float)):
            cur = world["state"].get(k, 50)
            world["state"][k] = max(0, min(100 if k != "population" else 10000, cur + max(-15, min(15, v))))
    world["meta"]["episode_actuel"] = n
    state.update(episode=n, last_date=ep["date"], last_choice=ep["choice"], summary=ep["summary"])
    save("world.json", world)
    save("state.json", state)
