"""Réalisateur automatique : scénario + voix => plan de tournage (plan.json).

Découpe en scènes (lieu/heure), place les personnages, choisit les plans (établissement, gros plan,
champ/contrechamp, plan à deux, repère du décor, travelling), les gestes, émotions, regards et marches,
et cale tout sur la durée réelle des voix (synchronisation image/son à l'image près).
"""
import json
import math
import re
from pathlib import Path

from studio.audio import lipsync, tts

ROOT = Path(__file__).resolve().parents[1]
FPS = 30
CHARS = json.loads((ROOT / "memory" / "characters.json").read_text())["characters"]
GEO = json.loads((ROOT / "memory" / "geography.json").read_text())
STYLE = json.loads((ROOT / "memory" / "visual_style.json").read_text())
SETS = GEO["sets3d"]

LOC_WORDS = [
    (r"for[êe]t|arbres? violets?", "foret_mysterieuse"), (r"\blac\b", "lac_cristal"),
    (r"terres? fertiles?|plaines?|herbes hautes", "terres_fertiles"), (r"volcan|lave|terres br[ûu]l[ée]es", "terres_brulees"),
    (r"grotte", "grotte_legendes"), (r"mont des [ée]toiles|cascade|sommet", "mont_etoiles"),
    (r"village|abris?|feu de camp", "village_premiers"),
]
TOD_WORDS = [(r"\bnuit\b|cette nuit", "night"), (r"\bsoir\b|cr[ée]puscule|coucher", "dusk"),
             (r"\baube\b|lendemain|\bmatin", "dawn"), (r"\bmidi\b|plein jour", "day")]
LANDMARK_WORDS = [(r"rocher|ruines?|\bmurs?\b|anciens", "ruins_far"), (r"montagne|mont\b|sommet", "mountain"),
                  (r"for[êe]t violette|arbres violets", "violet_forest_far"), (r"volcan", "volcano")]
GESTURE_WORDS = [(r"\bregarde[zs]?\b|\blà-haut\b|\blà-bas\b", "point"), (r"\breste\b|\bstop\b|\barr[êe]te", "stop"),
                 (r"\bpersonne n'y\b|\bjamais\b", "stop"), (r"\bpeut-[êe]tre\b|\bje ne sais\b", "shrug"),
                 (r"\bensemble\b|\btous\b", "open_arms")]
EMO_WORDS = [(r"peur|effray|danger|dents", "fear"), (r"faim|plus que|reste(nt)? que|deux jours", "worried"),
             (r"\bbravo\b|magnifique|regarde", "surprised"), (r"col[èe]re|refus", "angry"), (r"triste|mort", "sad")]


def _match(table, text):
    for pat, val in table:
        if re.search(pat, text, re.I):
            return val
    return None


def _names_in(text):
    return [cid for cid, c in CHARS.items() if re.search(r"\b" + re.escape(c["name"]) + r"\b", text, re.I)]


def _frames(sec):
    return int(round(sec * FPS))


FORMATION = [(-0.72, 0.0), (0.72, 0.12), (-2.0, 1.5), (2.1, 1.6), (0.3, 2.7), (-3.1, -0.2), (3.2, 0.4)]


def synth_audio(ep, work):
    """Voix de chaque réplique + visèmes. Reprise : une réplique déjà synthétisée n'est pas refaite."""
    aud = work / "audio"
    aud.mkdir(parents=True, exist_ok=True)
    meta_p = aud / "lines.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    for i, ln in enumerate(ep["lines"]):
        key = f"{i:02d}"
        wav = aud / f"line_{key}.wav"
        sig = f"{ln['speaker']}|{ln['text']}"
        if key in meta and meta[key]["sig"] == sig and wav.exists():
            continue
        voice = CHARS[ln["speaker"].lower()]["reference"]["voice"]
        info = tts.synth(ln["text"], voice, wav)
        W, method = lipsync.visemes(wav, ln["text"], FPS)
        meta[key] = {"sig": sig, **info, "visemes": W, "lipsync": method}
        meta_p.write_text(json.dumps(meta))
        print(f"voix {key} {ln['speaker']:6s} {info['seconds']:.2f}s ({info['engine']}, lip-sync {method})", flush=True)
    return meta


def plan(ep, work):
    meta = synth_audio(ep, work)
    lines = ep["lines"]
    # ---------------------------------------------------------------- minutage
    t = 1.2  # titre
    timing = []
    prev_sc = None
    loc, tod = ep["location"], ep["tod"]
    for i, ln in enumerate(lines):
        txt = ln["text"]
        if ln["speaker"] == "VARN" and i > 0:
            loc = ln.get("location") or _match(LOC_WORDS, txt) or loc
            tod = ln.get("tod") or _match(TOD_WORDS, txt) or tod
        else:
            loc = ln.get("location") or loc
            tod = ln.get("tod") or tod
        sc = (loc, tod)
        gap = 0.0 if i == 0 else (0.85 if sc != prev_sc else 0.4)
        t += gap
        dur = meta[f"{i:02d}"]["seconds"]
        timing.append({"i": i, "start": t, "end": t + dur, "loc": loc, "tod": tod, "scene_change": sc != prev_sc})
        t += dur
        prev_sc = sc
    total = t + 4.0  # carte de vote
    nframes = _frames(total)

    # ---------------------------------------------------------------- bouches (pistes globales)
    mouths = {}
    for tm in timing:
        sp = lines[tm["i"]]["speaker"].lower()
        W = meta[f"{tm['i']:02d}"]["visemes"]
        arr = mouths.setdefault(sp, [[0, 0, 0, 0] for _ in range(nframes + 60)])
        f0 = _frames(tm["start"])
        for k, w in enumerate(W):
            if f0 + k < len(arr):
                arr[f0 + k] = w

    # ---------------------------------------------------------------- scènes et distribution
    scenes = []
    for tm in timing:
        if tm["scene_change"]:
            scenes.append({"loc": tm["loc"], "tod": tm["tod"], "lines": []})
        scenes[-1]["lines"].append(tm)
    shots = []
    alive = [c for c, v in CHARS.items() if v["status"] == "vivant" and c != "varn"]
    for si, scn in enumerate(scenes):
        spk = []
        for tm in scn["lines"]:
            sp = lines[tm["i"]]["speaker"].lower()
            if sp != "varn" and sp not in spk:
                spk.append(sp)
        mentioned = []
        for tm in scn["lines"]:
            for c in _names_in(lines[tm["i"]]["text"]):
                if c not in spk and c not in mentioned and c != "varn":
                    mentioned.append(c)
        cast_ids = (spk + mentioned)[:4]
        # figurants pour un monde vivant (stables d'un épisode à l'autre : ordre fixe)
        for c in alive:
            if len(cast_ids) >= (5 if scn["loc"] == "village_premiers" else 3):
                break
            if c not in cast_ids:
                cast_ids.append(c)
        S = SETS[scn["loc"]]
        cx, cy = S["marks"]["center"]
        pos = {}
        for k, cid in enumerate(cast_ids):
            dx, dy = FORMATION[k % len(FORMATION)]
            pos[cid] = [cx + dx, cy + dy]
        scn["cast"] = cast_ids
        scn["pos"] = pos
        scn["main"] = cast_ids[:2]

        # ------------------------------------------------------------ plans
        f_scene0 = 0 if si == 0 else _frames(scn["lines"][0]["start"] - 0.45)
        f_scene1 = nframes if si == len(scenes) - 1 else _frames(scenes[si + 1]["lines"][0]["start"] - 0.45)
        for j, tm in enumerate(scn["lines"]):
            ln = lines[tm["i"]]
            sp = ln["speaker"].lower()
            f0 = f_scene0 if j == 0 else _frames(tm["start"] - 0.2)
            f1 = f_scene1 if j == len(scn["lines"]) - 1 else _frames(scn["lines"][j + 1]["start"] - 0.2)
            other = None
            if sp != "varn":
                for tm2 in scn["lines"][j + 1:] + scn["lines"][:j][::-1]:
                    s2 = lines[tm2["i"]]["speaker"].lower()
                    if s2 not in ("varn", sp):
                        other = s2
                        break
                named = [c for c in _names_in(ln["text"]) if c != sp and c in scn["cast"]]
                other = named[0] if named else other or next((c for c in scn["cast"] if c != sp), None)
            cams = _choose_cameras(si, j, ln, sp, other, scn, tm, S)
            # découpe des répliques longues en deux plans
            if len(cams) > 1 and ((f1 - f0) / FPS > STYLE["shot"]["max_s"] or cams[1]["type"] == "reveal"):
                mid = (f0 + f1) // 2
                spans = [(f0, mid, cams[0]), (mid, f1, cams[1])]
            else:
                spans = [(f0, f1, cams[0])]
            for a, b, cam in spans:
                shots.append({"id": f"s{len(shots) + 1:02d}", "f0": a, "f1": b, "location": scn["loc"], "tod": scn["tod"],
                              "weather": ep.get("weather", "clear"), "camera": cam, "line": tm["i"], "scene": si,
                              "transition_in": "dip" if (a == f_scene0 and si > 0) else "cut"})
        scn["f0"], scn["f1"] = f_scene0, f_scene1

    # ---------------------------------------------------------------- jeu d'acteurs par scène
    for si, scn in enumerate(scenes):
        perf = {cid: {"pos": scn["pos"][cid], "look": [], "emotion": [[0, "neutral"]], "gestures": [], "walks": []}
                for cid in scn["cast"]}
        center = SETS[scn["loc"]]["marks"]["center"]
        for cid, p in perf.items():
            p["yaw"] = math.atan2(center[0] - p["pos"][0], -(center[1] + 0.3 - p["pos"][1]))
        bg = scn["cast"][2:]
        for k, cid in enumerate(bg):  # occupations des figurants
            g = ["kneel_work", "warm_hands", "arms_crossed", "think"][k % 4]
            for f in range(scn["f0"], scn["f1"], 150):
                perf[cid]["gestures"].append({"f": f + 10 * k, "name": g, "scale": 1.6})

        for tm in scn["lines"]:
            ln = lines[tm["i"]]
            sp = ln["speaker"].lower()
            f = _frames(tm["start"])
            emo = ln.get("emotion") if ln.get("emotion") not in (None, "neutral") else _match(EMO_WORDS, ln["text"]) or "neutral"
            if sp in perf:
                perf[sp]["emotion"].append([f - 6, emo])
                g = ln.get("gesture") or _match(GESTURE_WORDS, ln["text"])
                if g:
                    perf[sp]["gestures"].append({"f": f + 6, "name": g})
                addressee = next((s["camera"].get("target") for s in shots if s["line"] == tm["i"] and s["camera"].get("target")), None)
                if addressee in perf:
                    perf[sp]["look"].append([f - 8, addressee])
                for cid in perf:
                    if cid != sp:
                        perf[cid]["look"].append([f - 4 + 3 * (hash(cid) % 3), sp])
                        if emo in ("fear", "surprised", "worried", "sad") and cid in scn["main"]:
                            perf[cid]["emotion"].append([f + 12, "worried"])

            else:  # narration : les personnages vivent leur scène
                for k, cid in enumerate(scn["main"]):
                    o = scn["main"][1 - k] if len(scn["main"]) > 1 else "camera"
                    perf[cid]["look"].append([f, o])
                    if emo != "neutral":
                        perf[cid]["emotion"].append([f, emo])
                for cid in _names_in(ln["text"]):
                    if cid in perf and re.search(r"partir|seule?|loin|chercher", ln["text"], re.I):
                        p0 = perf[cid]["pos"]
                        perf[cid]["walks"].append({"f0": f + 15, "f1": f + 15 + _frames(3.2),
                                                   "to": [p0[0] + 3.2, p0[1] + 2.4]})
        for cid, p in perf.items():
            p["look"].sort(key=lambda x: x[0])
            p["emotion"].sort(key=lambda x: x[0])
            if cid in mouths:
                p["_mouth_all"] = True
        scn["perf"] = perf

    # ---------------------------------------------------------------- assemblage des plans
    handle = 0
    for k, sh in enumerate(shots):
        scn = scenes[sh["scene"]]
        cast = {}
        for cid, p in scn["perf"].items():
            q = {kk: vv for kk, vv in p.items() if not kk.startswith("_")}
            if cid in mouths:
                q["mouth"] = {"f0": sh["f0"], "w": mouths[cid][sh["f0"]: sh["f1"] + handle]}
            cast[cid] = q
        sh["cast"] = cast
        sh["handle"] = 0  # transitions « fondu au noir » sans chevauchement : synchro son/image exacte
    out = {"episode": ep["number"], "title": ep["title"], "fps": FPS, "frames": nframes, "seconds": round(total, 3),
           "shots": shots,
           "dialogue": [{"i": tm["i"], "speaker": lines[tm["i"]]["speaker"], "text": lines[tm["i"]]["text"],
                         "start": round(tm["start"], 3), "end": round(tm["end"], 3),
                         "engine": meta[f"{tm['i']:02d}"]["engine"], "lipsync": meta[f"{tm['i']:02d}"]["lipsync"]}
                        for tm in timing],
           "choice": ep["choice"], "mood": ep.get("mood", "mystere")}
    (work / "plan.json").write_text(json.dumps(out))
    return out


def _choose_cameras(si, j, ln, sp, other, scn, tm, S):
    txt = ln["text"]
    center = S["marks"]["center"]
    if sp == "varn":
        lm = _match(LANDMARK_WORDS, txt)
        lms = {l["type"]: l for l in S.get("landmarks", [])}
        if si == 0 and j == 0:
            return [{"type": "establish", "center": center, "angle": -100}, {"type": "wide", "center": center, "angle": -70}]
        if lm and lm in lms:
            L = lms[lm]
            look = [L["pos"][0], L["pos"][1], L.get("h", 10) * 0.6]
            return [{"type": "reveal", "subject": scn["main"][0], "look": look, "from": [center[0] - 1.6, center[1] - 2.2, 1.5]},
                    {"type": "landmark", "look": look, "from": [center[0], center[1] - 1.0, 1.7]}]
        names = [c for c in _names_in(txt) if c in scn["cast"]]
        if names and j > 0:
            tgt = next((c for c in scn["main"] + scn["cast"] if c != names[0]), None)
            return [{"type": "close", "subject": names[0], "target": tgt, "side": -1 if j % 2 else 1},
                    {"type": "wide", "center": center, "angle": -90 + (25 if j % 2 else -25)}]
        if j == 0:
            return [{"type": "establish", "center": center, "angle": -90 + 35 * (1 if si % 2 else -1), "radius": 11},
                    {"type": "wide", "center": center, "angle": -90}]
        return [{"type": "wide", "center": center, "angle": -90 + (30 if j % 2 else -30)},
                {"type": "two", "subject": scn["main"][0], "target": scn["main"][-1]}]
    lm = _match(LANDMARK_WORDS, txt)
    lms = {l["type"]: l for l in S.get("landmarks", [])}
    if lm in lms:  # un personnage parle d'un lieu visible : on le montre
        L = lms[lm]
        look = [L["pos"][0], L["pos"][1], L.get("h", 10) * 0.6]
        p = scn["pos"][sp]
        return [{"type": "close", "subject": sp, "target": other, "side": 1},
                {"type": "reveal", "subject": sp, "look": look, "from": [p[0] - 0.9, p[1] - 1.6, 1.45]}]
    variants = [
        [{"type": "close", "subject": sp, "target": other, "side": 1}, {"type": "ots", "subject": sp, "target": other, "side": 1}],
        [{"type": "ots", "subject": sp, "target": other, "side": -1}, {"type": "close", "subject": sp, "target": other, "side": -1}],
        [{"type": "two", "subject": sp, "target": other}, {"type": "close", "subject": sp, "target": other, "side": 1}],
    ]
    if other is None:
        return [{"type": "close", "subject": sp, "target": None, "side": 1}, {"type": "wide", "center": center}]
    return variants[(j + si) % 3]
