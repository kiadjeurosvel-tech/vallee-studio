"""Contrôle strict d'un scénario (quelle que soit sa source) avant toute production."""
import re

from .memory import alive_characters, load

EMOTIONS = {"neutral", "happy", "sad", "angry", "fear", "surprised", "worried", "determined"}
GESTURES = {"point", "wave", "arms_crossed", "hands_hips", "think", "shrug", "open_arms", "fear", "stop", "fist",
            "kneel_work", "warm_hands", "lean_staff", None, ""}
TODS = {"dawn", "day", "dusk", "night"}
MOODS = {"tension", "calme", "mystere", "espoir"}
BANNED = re.compile(r"\b(magie|magique|sortil[eè]ge|dragon|sorci[eè]re?|fant[ôo]me|d[ée]mon|elfe|licorne|"
                    r"t[ée]l[ée]phone|voiture|internet|fusil|pistolet)\b", re.I)


class Invalid(ValueError):
    pass


def normalize(ep):
    """Corrige ce qui peut l'être sans changer le sens (casse, champs manquants)."""
    places = {p["id"] for p in load("geography.json")["lieux"]}
    ep.setdefault("location", "village_premiers")
    if ep["location"] not in places:
        ep["location"] = "village_premiers"
    ep.setdefault("tod", "day")
    if ep["tod"] not in TODS:
        ep["tod"] = "day"
    ep.setdefault("weather", "clear")
    if ep["weather"] not in ("clear", "rain", "fog"):
        ep["weather"] = "clear"
    ep.setdefault("mood", "mystere")
    if ep["mood"] not in MOODS:
        ep["mood"] = "mystere"
    for ln in ep.get("lines", []):
        ln["speaker"] = str(ln.get("speaker", "")).strip().upper()
        ln["text"] = re.sub(r"\s+", " ", str(ln.get("text", ""))).strip()
        if ln.get("emotion") not in EMOTIONS:
            ln["emotion"] = "neutral"
        if ln.get("gesture") not in GESTURES:
            ln["gesture"] = None
        if ln.get("location") and ln["location"] not in places:
            ln.pop("location")
        if ln.get("tod") and ln["tod"] not in TODS:
            ln.pop("tod")
    ep.setdefault("hashtags", ["#lavalleedeshorizons", "#serie", "#animation", "#histoire"])
    return ep


def check(ep, strict_words=(90, 230)):
    alive = {k.upper() for k in alive_characters()}
    errs = []
    lines = ep.get("lines") or []
    if not (5 <= len(lines) <= 16):
        errs.append(f"{len(lines)} répliques (attendu 5 à 16)")
    words = 0
    for i, ln in enumerate(lines):
        if ln["speaker"] not in alive:
            errs.append(f"réplique {i + 1} : personnage inconnu ou mort « {ln['speaker']} »")
        n = len(ln["text"].split())
        words += n
        if n < 2 or n > 45:
            errs.append(f"réplique {i + 1} : {n} mots")
        if BANNED.search(ln["text"]):
            errs.append(f"réplique {i + 1} : élément interdit par le canon ({BANNED.search(ln['text']).group(0)})")
    if not (strict_words[0] <= words <= strict_words[1]):
        errs.append(f"{words} mots au total (attendu {strict_words[0]}–{strict_words[1]})")
    c = ep.get("choice") or {}
    if not (c.get("question") and c.get("A") and c.get("B")) or c.get("A") == c.get("B"):
        errs.append("dilemme A/B incomplet")
    for k in ("title", "summary", "caption"):
        if not ep.get(k):
            errs.append(f"champ manquant : {k}")
    if lines and lines[0]["speaker"] != "VARN":
        errs.append("la première réplique doit être celle du narrateur VARN")
    if errs:
        raise Invalid("; ".join(errs))
    return True
