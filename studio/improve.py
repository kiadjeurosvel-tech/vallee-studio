"""Amélioration continue.

- record()  : après chaque épisode validé, ajoute les mesures à improvements/metrics.jsonl
              et écrit un rapport daté (improvements/reports/).
- autotune(): ajuste UNIQUEMENT improvements/tuning.json (qualité de rendu) dans les bornes de
              memory/visual_style.json > tuning_bounds, selon le budget de temps. Jamais le code du moteur.
              Le workflow « Amélioration » n'enregistre le changement qu'après tests + rendu de contrôle réussis.
- backlog() : liste priorisée des défauts récurrents (improvements/BACKLOG.md) pour les évolutions manuelles.
"""
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMP = ROOT / "improvements"
METRICS = IMP / "metrics.jsonl"
TUNING = IMP / "tuning.json"
STYLE = json.loads((ROOT / "memory" / "visual_style.json").read_text())
CFG = json.loads((ROOT / "config" / "studio.json").read_text())


def _rows():
    if not METRICS.exists():
        return []
    return [json.loads(x) for x in METRICS.read_text().splitlines() if x.strip()]


def record(ep, rep):
    IMP.mkdir(exist_ok=True)
    (IMP / "reports").mkdir(exist_ok=True)
    m = dict(rep["metrics"])
    row = {"episode": ep["number"], "date": ep["date"], "source": ep.get("source"), "ok": rep["ok"],
           "warnings": rep["warnings"], **{k: m.get(k) for k in (
               "duration", "render_s_per_frame", "render_minutes_total", "render_res", "render_samples", "jerks",
               "frozen_frames", "loudness_lufs", "mean_luma", "longest_shot_s", "tts_engines", "lipsync")}}
    with METRICS.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (IMP / "reports" / f"{ep['date']}_ep{ep['number']:03d}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    backlog()


def backlog():
    rows = _rows()[-14:]
    c = Counter()
    for r in rows:
        for w in r.get("warnings", []):
            c[w.split(" (")[0].split(":")[0][:80]] += 1
    L = ["# Backlog d'amélioration (généré automatiquement)", "",
         f"Fenêtre : {len(rows)} derniers épisodes. Les défauts les plus fréquents d'abord.", ""]
    for w, n in c.most_common():
        L.append(f"- [{n}×] {w}")
    if not c:
        L.append("- Aucun défaut récurrent détecté.")
    spf = [r["render_s_per_frame"] for r in rows if r.get("render_s_per_frame")]
    if spf:
        L += ["", f"Temps de rendu moyen : {sum(spf) / len(spf):.2f} s/image."]
    (IMP / "BACKLOG.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def autotune(dry=False):
    """Renvoie (nouveau_tuning, explication) ou (None, raison)."""
    rows = [r for r in _rows() if r.get("ok") and r.get("render_s_per_frame")][-3:]
    if len(rows) < 3:
        return None, "pas assez d'épisodes mesurés (3 requis)"
    cur = json.loads(TUNING.read_text()) if TUNING.exists() else {"render": {}}
    R = dict(STYLE["render"])
    R.update(cur.get("render", {}))
    b = STYLE["tuning_bounds"]
    jobs = CFG["render"]["max_jobs"]
    target = CFG["render"]["target_job_minutes"]
    frames = max(r["duration"] for r in rows) * 30
    spf = sum(r["render_s_per_frame"] for r in rows) / 3
    per_job = frames * spf / 60 / jobs
    new = dict(R)
    why = ""
    if per_job < 0.55 * target:
        if R["samples"] < b["samples"][1]:
            new["samples"] = min(b["samples"][1], R["samples"] + 4)
            why = f"marge de rendu ({per_job:.1f} min/lot < {0.55 * target:.0f}) : échantillons {R['samples']}→{new['samples']}"
        elif R["res_x"] < b["res_x"][1]:
            new["res_x"] = min(b["res_x"][1], R["res_x"] + 180)
            why = f"marge de rendu : résolution interne {R['res_x']}→{new['res_x']}"
    elif per_job > 0.95 * target:
        if R["samples"] > b["samples"][0]:
            new["samples"] = max(b["samples"][0], R["samples"] - 4)
            why = f"rendu trop long ({per_job:.1f} min/lot) : échantillons {R['samples']}→{new['samples']}"
        elif R["res_x"] > b["res_x"][0]:
            new["res_x"] = max(b["res_x"][0], R["res_x"] - 180)
            why = f"rendu trop long : résolution interne {R['res_x']}→{new['res_x']}"
    jerky = sum(1 for r in rows if (r.get("jerks") or 0) > 3)
    if jerky >= 2:
        why += " | saccades récurrentes signalées dans BACKLOG.md (correction manuelle du moteur requise)"
    changed = {k: new[k] for k in ("samples", "res_x") if new[k] != R[k]}
    if not changed:
        return None, why or f"réglages adaptés ({per_job:.1f} min/lot, cible {target})"
    out = {"render": {**cur.get("render", {}), **changed}, "updated": dt.date.today().isoformat(), "reason": why}
    if not dry:
        TUNING.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out, why


if __name__ == "__main__":
    if sys.argv[1:] == ["autotune"]:
        res, why = autotune()
        print("Réglage :", why)
        if res:
            with (ROOT / "CHANGELOG.md").open("a", encoding="utf-8") as fh:
                fh.write(f"\n- {dt.date.today().isoformat()} — réglage automatique : {why}\n")
            print("CHANGED=1")
    elif sys.argv[1:] == ["backlog"]:
        backlog()
