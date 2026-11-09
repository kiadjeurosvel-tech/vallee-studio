"""Moteur narratif : produit le scénario de l'épisode N.

Priorité des sources (toujours indiquée dans episode['source']) :
1. story_queue/epNNN.json  — scénario écrit à la main ;
2. modèle local (llm.py)   — validé strictement, 3 essais ;
3. générateur à gabarits   — garantit qu'un épisode cohérent sort chaque jour.
"""
import json
import random

from . import validate
from .memory import ROOT, alive_characters, load

QUEUE = ROOT / "story_queue"

SYSTEM = """Tu es le scénariste de « La Vallée des Horizons », une série animée verticale quotidienne en français.
Dix fondateurs bâtissent une civilisation dans une vallée vierge. Monde épique SANS AUCUN SURNATUREL :
pas de magie, pas de créatures, tout s'explique par la nature, la technique ou les choix humains.
VARN, vieux conteur presque aveugle, raconte au passé et ouvre l'épisode (« Je me souviens… »).
Règles : progression lente et crédible, conséquences permanentes, 140 à 190 mots au total (≈ 60 s),
8 à 12 répliques de 6 à 30 mots, première réplique = accroche forte, vocabulaire simple, aucune violence graphique.
Termine par un dilemme clair A/B, chaque option avec un coût, sans bonne réponse évidente.
Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour."""

FORMAT = """Schéma JSON exact :
{
 "title": "titre court (max 6 mots)",
 "location": "un id parmi : %s",
 "tod": "dawn|day|dusk|night",
 "weather": "clear|rain|fog",
 "mood": "tension|calme|mystere|espoir",
 "lines": [{"speaker": "VARN|NOM", "text": "…", "emotion": "neutral|happy|sad|angry|fear|surprised|worried|determined",
            "gesture": "point|wave|arms_crossed|hands_hips|think|shrug|open_arms|fear|stop|fist|kneel_work|warm_hands|null"}],
 "choice": {"question": "…", "A": "max 8 mots", "B": "max 8 mots"},
 "caption": "légende accrocheuse (max 120 caractères) finissant par « Vote A ou B 👇 »",
 "hashtags": ["#lavalleedeshorizons", "…"],
 "summary": "résumé COMPLET de l'histoire jusqu'ici, 4 phrases max",
 "world_changes": {"nourriture": -5, "moral": 3}
}"""


def _cast_text():
    out = []
    for cid, c in alive_characters().items():
        sec = c["secret"]["texte"] if not c["secret"].get("revele") else "(révélé)"
        out.append(f"- {c['name'].upper()} ({c['age']} ans, {c['role']}) : {', '.join(c['personality'])}. "
                   f"Ambition : {c['ambition']} Secret (à distiller lentement) : {sec}")
    return "\n".join(out)


def _arc(n):
    for a in load("world.json")["arcs"]:
        lo, hi = (int(x) for x in a["episodes"].split("-"))
        if lo <= n <= hi:
            return f"{a['id']} — {a['fil']}"
    return "libre"


def build_prompt(n, state, vote):
    geo = load("geography.json")
    places = ", ".join(f"{p['id']} ({p['nom']})" for p in geo["lieux"])
    hist = load("world.json")["history"][-6:]
    ex = (QUEUE / "ep001.json").read_text(encoding="utf-8") if (QUEUE / "ep001.json").exists() else ""
    c = state["last_choice"]
    return (f"Personnages vivants :\n{_cast_text()}\n\nÉpisode {n}. Arc en cours : {_arc(n)}\n"
            f"Histoire jusqu'ici : {state['summary']}\n"
            f"Derniers épisodes : {'; '.join(h['title'] for h in hist) or 'aucun'}\n"
            f"Dilemme précédent : {c['question']} — la communauté a choisi {vote} : « {c.get(vote, '')} ». "
            f"Cet épisode montre les conséquences concrètes de ce choix.\n\n"
            f"{FORMAT % places}\n\nExemple de style (épisode 1, ne pas recopier) :\n{ex[:2500]}")


def _from_llm(n, state, vote, attempts):
    from . import llm
    last = None
    for k in range(attempts):
        try:
            txt, model = llm.chat(SYSTEM, build_prompt(n, state, vote), seed=n * 10 + k)
            ep = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
            validate.normalize(ep)
            validate.check(ep)
            ep["source"] = f"llm:{model}"
            return ep
        except Exception as e:
            last = e
            print(f"Scénario LLM refusé (essai {k + 1}) : {e}", flush=True)
    raise RuntimeError(f"LLM indisponible ou scénarios invalides : {last}")


# ------------------------------------------------------------------ gabarits de secours
TEMPLATES = [
    {"location": "foret_mysterieuse", "tod": "day", "mood": "mystere", "title": "Sous les arbres violets",
     "lines": [
         ("VARN", "Je me souviens de ce matin-là. {last} Et la forêt violette nous attendait.", "worried", None),
         ("{a}", "Avancez lentement. Ici, chaque branche cassée s'entend de loin.", "determined", "stop"),
         ("{b}", "Regarde ces marques sur l'écorce. Quelqu'un les a taillées. Elles sont récentes.", "surprised", "point"),
         ("{a}", "Des marques d'animal, peut-être. Ne touchons à rien.", "worried", "arms_crossed"),
         ("VARN", "Personne n'y croyait vraiment. Les entailles étaient trop droites, trop régulières.", "neutral", None),
         ("{c}", "Il y a des baies partout. De quoi tenir plusieurs jours, si elles ne sont pas toxiques.", "happy", "kneel_work"),
         ("{b}", "On pourrait en goûter une seule. Juste pour savoir.", "determined", "shrug"),
         ("VARN", "Ce jour-là, la faim et la prudence se sont disputé notre avenir. Et c'est vous qui avez tranché.", "neutral", None)],
     "choice": ("Que faire des baies inconnues ?", "Les goûter, prudemment", "Les laisser, chasser à la place")},
    {"location": "village_premiers", "tod": "dusk", "mood": "tension", "title": "Le feu qui faiblit",
     "lines": [
         ("VARN", "Je me souviens du soir où notre feu a failli mourir. {last}", "worried", None),
         ("{a}", "Le bois est mouillé. Si la flamme s'éteint, nous ne savons pas la rallumer.", "fear", "warm_hands"),
         ("{b}", "Alors gardons-la. Chacun son tour, toute la nuit.", "determined", "fist"),
         ("{c}", "Et demain ? Nous passerons nos vies à surveiller une flamme ?", "angry", "open_arms"),
         ("VARN", "Ils avaient raison tous les deux. C'est souvent comme ça que naissent les vraies disputes.", "neutral", None),
         ("{a}", "Il faut apprendre à faire naître le feu. Avec des pierres, avec du bois sec, peu importe.", "think", "think"),
         ("{b}", "Apprendre prend du temps. Le froid, lui, n'attend pas.", "worried", "arms_crossed"),
         ("VARN", "Cette nuit-là, personne n'a dormi. Et au matin, il fallait choisir.", "neutral", None)],
     "choice": ("Comment protéger le feu ?", "Veiller la flamme jour et nuit", "Chercher comment l'allumer seuls")},
    {"location": "lac_cristal", "tod": "dawn", "mood": "espoir", "title": "Les poissons du lac",
     "lines": [
         ("VARN", "Je me souviens de la première fois que nous avons vu le Lac Cristal à l'aube. {last}", "happy", None),
         ("{a}", "Regardez, l'eau est si claire qu'on voit les poissons dormir.", "happy", "point"),
         ("{b}", "Les voir, c'est facile. Les attraper, c'est autre chose.", "neutral", "hands_hips"),
         ("{a}", "Avec des branches tressées, on pourrait faire un piège à l'entrée du ruisseau.", "determined", "kneel_work"),
         ("{c}", "Et si le piège prend tous les poissons ? Il n'en restera plus pour demain.", "worried", "think"),
         ("VARN", "C'était la première fois que l'un de nous pensait au lendemain du lendemain.", "neutral", None),
         ("{b}", "Demain, nous serons peut-être morts de faim. Pensons d'abord à aujourd'hui.", "angry", "stop"),
         ("VARN", "Deux idées de l'avenir se faisaient face. Une seule pouvait gagner ce jour-là.", "neutral", None)],
     "choice": ("Comment pêcher dans le lac ?", "Un grand piège, tout prendre", "Pêcher peu, laisser le lac vivre")},
    {"location": "terres_fertiles", "tod": "day", "mood": "calme", "title": "Les graines sauvages",
     "lines": [
         ("VARN", "Je me souviens des herbes hautes des Terres Fertiles, dorées comme du miel. {last}", "happy", None),
         ("{a}", "Ces épis sont pleins de graines. On pourrait les moudre entre deux pierres.", "surprised", "kneel_work"),
         ("{b}", "Il en faudrait des milliers pour un seul repas. C'est du temps perdu.", "neutral", "shrug"),
         ("{a}", "Et si on en plantait près du village ? Elles pousseraient pour nous.", "determined", "open_arms"),
         ("{c}", "Planter ? Attendre des mois sans être sûrs de rien ?", "worried", "arms_crossed"),
         ("VARN", "Personne ne le savait encore, mais cette idée allait changer toute notre histoire.", "neutral", None),
         ("{b}", "Les bêtes viennent brouter ici. Elles mangeraient tout avant nous.", "worried", "point"),
         ("VARN", "Ce jour-là, il fallait choisir entre la récolte d'aujourd'hui et celle de demain.", "neutral", None)],
     "choice": ("Que faire des graines sauvages ?", "Tout récolter et manger", "En garder pour planter")},
]


def _from_templates(n, state, vote):
    rng = random.Random(n * 7919)
    alive = [c for c in alive_characters() if c != "varn"]
    t = TEMPLATES[(n - 1) % len(TEMPLATES)]
    a, b, c = rng.sample(alive, 3)
    names = {"{a}": a.upper(), "{b}": b.upper(), "{c}": c.upper()}
    picked = state["last_choice"].get(vote, "")
    last = f"La veille, nous avions choisi : {picked.lower()}." if picked and state["episode"] > 0 else ""
    lines = []
    for sp, tx, emo, g in t["lines"]:
        lines.append({"speaker": names.get(sp, sp), "text": tx.format(last=last).strip(), "emotion": emo, "gesture": g})
    q, A, B = t["choice"]
    ep = {"title": t["title"], "location": t["location"], "tod": t["tod"], "weather": "clear", "mood": t["mood"],
          "lines": lines, "choice": {"question": q, "A": A, "B": B},
          "caption": f"{t['title']} — que doit faire la vallée ? Vote A ou B 👇",
          "hashtags": ["#lavalleedeshorizons", "#serie", "#animation", "#histoire", "#vote"],
          "summary": (state["summary"] + f" Épisode {n} : {t['title'].lower()}.")[-700:],
          "world_changes": {}, "source": "gabarit"}
    validate.normalize(ep)
    validate.check(ep)
    return ep


def write(n, state, vote, use_llm=True):
    q = QUEUE / f"ep{n:03d}.json"
    if q.exists():
        ep = json.loads(q.read_text(encoding="utf-8"))
        validate.normalize(ep)
        validate.check(ep)
        ep["source"] = "manuel"
        return ep
    if use_llm:
        try:
            return _from_llm(n, state, vote, json.loads((ROOT / "config" / "studio.json").read_text())["llm"]["attempts"])
        except Exception as e:
            print("Repli sur le générateur à gabarits :", e, flush=True)
    return _from_templates(n, state, vote)
