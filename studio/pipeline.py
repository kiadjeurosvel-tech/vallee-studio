"""Orchestrateur de production (utilisé tel quel par GitHub Actions et en local).

python -m studio.pipeline prepare   [--force] [--no-llm] [--episode N]
python -m studio.pipeline chunks    [--jobs K]          -> work/current/chunks.json
python -m studio.pipeline render    --chunk k [--preview]
python -m studio.pipeline assemble
python -m studio.pipeline publish                       -> met à jour la mémoire (uniquement si QA validée)
python -m studio.pipeline all       [--preview] [--no-llm]   (tout d'un coup, en local)

Chaque étape lit/écrit work/current/ (épisode en cours) : une étape relancée reprend où elle s'était arrêtée.
"""
import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio.narrative import memory, writer  # noqa: E402

WORK = ROOT / "work" / "current"
CFG = json.loads((ROOT / "config" / "studio.json").read_text())


def _today():
    return memory.berlin_today().isoformat()


def read_vote(state):
    """Vote : issue GitHub « VOTE » du dépôt (facultatif). Sans vote, « le destin décide » (tirage reproductible)."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if token and repo:
        try:
            import urllib.request

            def get(u):
                req = urllib.request.Request(u, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
                return json.load(urllib.request.urlopen(req, timeout=30))
            issues = get(f"https://api.github.com/repos/{repo}/issues?state=open&per_page=50")
            iss = next((i for i in issues if i["title"].strip().upper() == "VOTE"), None)
            if iss:
                url = iss["comments_url"] + "?per_page=100"
                if state.get("last_date"):
                    url += f"&since={state['last_date']}T00:00:00Z"
                a = b = 0
                for c in get(url):
                    body = c.get("body", "").strip().upper()
                    a += body in ("A", "A.", "A!")
                    b += body in ("B", "B.", "B!")
                if a or b:
                    return ("A" if a >= b else "B"), f"vote ({a} A / {b} B)"
        except Exception as e:
            print("Lecture du vote impossible :", e)
    rng = random.Random(state.get("episode", 0) * 31 + 7)
    return rng.choice("AB"), "le destin (aucun vote)"


def prepare(args):
    from studio import director
    state = memory.load("state.json")
    today = _today()
    cur = WORK / "episode.json"
    if cur.exists():
        ep = json.loads(cur.read_text())
        stale = ep.get("status") == "publié" or ep["number"] <= state["episode"]
        if not stale and (args.episode is None or ep["number"] == args.episode):
            print(f"Reprise de l'épisode {ep['number']} en cours ({ep['source']}).")
            if not (WORK / "plan.json").exists():
                director.plan(ep, WORK)
            _emit(ep)
            return ep
    if state.get("last_date") == today and not args.force:
        print(f"L'épisode du {today} est déjà produit (n°{state['episode']}). Rien à faire.")
        _emit(None)
        return None
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    n = args.episode or state["episode"] + 1
    vote, vote_src = read_vote(state)
    ep = writer.write(n, state, vote, use_llm=not args.no_llm)
    ep.update(number=n, date=today, vote=vote, vote_source=vote_src, status="en_production")
    cur.write_text(json.dumps(ep, ensure_ascii=False, indent=1))
    epdir = ROOT / "episodes" / f"ep{n:03d}"
    epdir.mkdir(parents=True, exist_ok=True)
    (epdir / "script.json").write_text(json.dumps(ep, ensure_ascii=False, indent=1))
    director.plan(ep, WORK)
    print(f"Épisode {n} « {ep['title']} » préparé (scénario : {ep['source']}, vote {vote} — {vote_src}).")
    _emit(ep)
    return ep


def _emit(ep):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"produce={'true' if ep else 'false'}\n")
            if ep:
                fh.write(f"episode={ep['number']}\n")


def _estimate_spf():
    """Secondes par image mesurées lors des derniers épisodes (sinon estimation prudente)."""
    p = ROOT / "improvements" / "metrics.jsonl"
    if p.exists():
        rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        vals = [r["render_s_per_frame"] for r in rows[-5:] if r.get("render_s_per_frame")]
        if vals:
            return sum(vals) / len(vals)
    return 6.0


def chunks(args):
    plan = json.loads((WORK / "plan.json").read_text())
    spf = _estimate_spf()
    cost = {"establish": 1.35, "wide": 1.25, "landmark": 1.2, "reveal": 1.15, "two": 1.0, "track": 1.1, "ots": 0.95, "close": 0.9}
    shots = sorted(plan["shots"], key=lambda s: -(s["f1"] - s["f0"]) * cost.get(s["camera"]["type"], 1))
    total_min = sum((s["f1"] - s["f0"]) * cost.get(s["camera"]["type"], 1) for s in shots) * spf / 60
    k = args.jobs or max(1, min(CFG["render"]["max_jobs"], math.ceil(total_min / CFG["render"]["target_job_minutes"])))
    bins = [[0.0, []] for _ in range(k)]
    for s in shots:
        b = min(bins, key=lambda x: x[0])
        b[0] += (s["f1"] - s["f0"]) * cost.get(s["camera"]["type"], 1) * spf / 60 + 0.3
        b[1].append(s["id"])
    res = {"jobs": k, "estimated_minutes": round(total_min, 1), "chunks": [",".join(sorted(b[1])) for b in bins if b[1]]}
    (WORK / "chunks.json").write_text(json.dumps(res))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"matrix={json.dumps(list(range(len(res['chunks']))))}\n")
    print(f"{len(res['chunks'])} lot(s) de rendu, ~{res['estimated_minutes']} min CPU au total ({spf:.1f} s/image).")
    return res


def render(args):
    ids = json.loads((WORK / "chunks.json").read_text())["chunks"][args.chunk] if args.chunk is not None else "all"
    blender = shutil.which("blender")
    if not blender:
        raise SystemExit("Blender introuvable")
    cmd = [blender, "-b", "-noaudio", "-P", str(ROOT / "studio" / "animation" / "render_shots.py"), "--",
           str(WORK / "plan.json"), str(WORK / "shots"), ids] + (["--preview"] if args.preview else [])
    if shutil.which("xvfb-run") and not os.environ.get("DISPLAY"):
        cmd = ["xvfb-run", "-a"] + cmd
    p = subprocess.run(cmd, text=True, capture_output=True)
    keep = [ln for ln in p.stdout.splitlines() if ln.startswith(("PLAN", "s0", "s1", "s2", "s3", "déjà", "Error", "Traceback", "  File"))]
    print("\n".join(keep[-60:]))
    if p.returncode != 0 or "Traceback" in p.stdout or "Traceback" in p.stderr:
        print(p.stderr[-3000:])
        raise SystemExit("échec du rendu")
    missing = [i for i in ids.split(",") if ids != "all" and not (WORK / "shots" / f"{i}.mp4").exists()]
    if missing:
        raise SystemExit(f"plans non produits : {missing}")


def assemble(args):
    from studio.edit.assemble import assemble as asm
    from studio.qa import check as qa
    ep = json.loads((WORK / "episode.json").read_text())
    plan = json.loads((WORK / "plan.json").read_text())
    stats = []
    for f in (WORK / "shots").glob("stats_*.json"):
        stats += json.loads(f.read_text())
    out = WORK / "final"
    mp4 = asm(plan, WORK, out, CFG["series"], seed=ep["number"])
    rep = qa.check(mp4, plan, out / f"vallee_ep{ep['number']:03d}.ass", stats)
    rep["episode"] = ep["number"]
    (out / "qa.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    (out / "qa.md").write_text(qa.markdown(ep, rep), encoding="utf-8")
    caption = f"{ep['caption']}\n\n{' '.join(ep.get('hashtags', [])[:6])}"
    (out / "legende.txt").write_text(caption, encoding="utf-8")
    print(qa.markdown(ep, rep))
    if not rep["ok"]:
        bad = out / "REJETE.mp4"
        mp4.replace(bad)
        raise SystemExit("QA : vidéo rejetée — rien n'est livré.")
    return rep


def publish(args):
    from studio import improve
    ep = json.loads((WORK / "episode.json").read_text())
    rep = json.loads((WORK / "final" / "qa.json").read_text())
    if not rep["ok"]:
        raise SystemExit("QA non validée : publication refusée.")
    memory.apply_episode(ep, ep.get("vote"))
    ep["status"] = "publié"
    epdir = ROOT / "episodes" / f"ep{ep['number']:03d}"
    epdir.mkdir(parents=True, exist_ok=True)
    (epdir / "script.json").write_text(json.dumps(ep, ensure_ascii=False, indent=1))
    (epdir / "qa.md").write_text((WORK / "final" / "qa.md").read_text(encoding="utf-8"), encoding="utf-8")
    (WORK / "episode.json").write_text(json.dumps(ep, ensure_ascii=False, indent=1))
    improve.record(ep, rep)
    print(f"Épisode {ep['number']} publié dans la mémoire.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["prepare", "chunks", "render", "assemble", "publish", "all"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--episode", type=int)
    ap.add_argument("--chunk", type=int)
    ap.add_argument("--jobs", type=int)
    a = ap.parse_args()
    if a.stage == "all":
        if prepare(a) is None:
            return
        a.chunk = None
        render(a)
        assemble(a)
        publish(a)
        return
    {"prepare": prepare, "chunks": chunks, "render": render, "assemble": assemble, "publish": publish}[a.stage](a)


if __name__ == "__main__":
    main()
