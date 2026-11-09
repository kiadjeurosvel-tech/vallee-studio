"""Contrôle qualité automatique d'un épisode monté.

Erreurs (bloquantes : la vidéo n'est PAS livrée) : format, codec, résolution, cadence, durée,
fichier non décodable, audio absent, long noir non prévu, sous-titres manquants.
Avertissements (signalés dans le rapport et le backlog d'amélioration) : saccades, images figées,
silences, volume, plans trop longs, temps de rendu.
"""
import json
import re
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
STYLE = json.loads((ROOT / "memory" / "visual_style.json").read_text())


def _probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(p)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _ff(args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True).stderr


def motion_profile(p, w=54, h=96):
    """Différence moyenne entre images successives (vignettes en niveaux de gris)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, check=True)
    fr = np.frombuffer(r.stdout, np.uint8).reshape(-1, h, w).astype(np.float32)
    return np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2)), fr.mean(axis=(1, 2))


def check(mp4, plan, ass=None, render_stats=None):
    O = STYLE["output"]
    errors, warns, m = [], [], {}
    mp4 = Path(mp4)
    if not mp4.exists() or mp4.stat().st_size < 50_000:
        return {"ok": False, "errors": ["fichier vidéo absent ou vide"], "warnings": [], "metrics": {}}
    info = _probe(mp4)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    m.update(duration=round(dur, 2), size_mb=round(mp4.stat().st_size / 1e6, 2))
    if not v:
        errors.append("pas de flux vidéo")
    else:
        num, den = (int(x) for x in v["r_frame_rate"].split("/"))
        fps = num / den
        m.update(width=v["width"], height=v["height"], fps=round(fps, 3), vcodec=v["codec_name"], pix_fmt=v["pix_fmt"])
        if (v["width"], v["height"]) != (O["width"], O["height"]):
            errors.append(f"résolution {v['width']}x{v['height']} (attendu {O['width']}x{O['height']})")
        if v["codec_name"] != "h264":
            errors.append(f"codec vidéo {v['codec_name']} (attendu h264)")
        if v["pix_fmt"] != "yuv420p":
            errors.append(f"pix_fmt {v['pix_fmt']}")
        if abs(fps - O["fps"]) > 0.01:
            errors.append(f"{fps:.2f} i/s (attendu {O['fps']})")
    if not a:
        errors.append("pas de piste audio")
    else:
        m.update(acodec=a["codec_name"], channels=a.get("channels"), sample_rate=a.get("sample_rate"))
        if a["codec_name"] != "aac":
            errors.append(f"codec audio {a['codec_name']} (attendu aac)")
    if abs(dur - plan["seconds"]) > 0.4:
        errors.append(f"durée {dur:.2f} s ≠ plan {plan['seconds']:.2f} s (désynchronisation possible)")
    # décodage intégral : aucun fichier corrompu ne doit sortir
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-f", "null", "-"], capture_output=True, text=True).stderr
    if dec.strip():
        errors.append("erreurs de décodage : " + dec.strip()[:300])
    # noirs non prévus
    bl = _ff(["-i", str(mp4), "-vf", "blackdetect=d=0.4:pic_th=0.97:pix_th=0.08", "-an", "-f", "null", "-"])
    blacks = [(float(s), float(e)) for s, e in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", bl)]
    m["black_segments"] = blacks
    for s, e in blacks:
        if e - s > 0.9:
            errors.append(f"noir de {e - s:.1f} s à {s:.1f} s")
    # audio
    vol = _ff(["-i", str(mp4), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    lu = re.findall(r"I:\s+(-?[\d.]+) LUFS", vol)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", vol)
    if lu:
        m["loudness_lufs"] = float(lu[-1])
        if not (-18 <= m["loudness_lufs"] <= -11):
            warns.append(f"volume {m['loudness_lufs']} LUFS (cible -14)")
    if tp:
        m["true_peak_db"] = float(tp[-1])
    sil = _ff(["-i", str(mp4), "-vn", "-af", "silencedetect=noise=-50dB:d=1.5", "-f", "null", "-"])
    m["silences"] = len(re.findall("silence_start", sil))
    if m["silences"]:
        warns.append(f"{m['silences']} silence(s) de plus de 1,5 s")
    # fluidité
    fps = plan["fps"]
    d, lum = motion_profile(mp4)
    cuts = set()
    for sh in plan["shots"][1:]:
        w = 10 if sh.get("transition_in") == "dip" else 1
        for k in range(-w - 1, w + 1):
            cuts.add(sh["f0"] - 1 + k)
    T = int(plan["seconds"] * fps)
    # fondus prévus : début, titre, carte de vote, fin
    for a, b in ((0, 12), (int(3.0 * fps), int(3.8 * fps)), (T - int(4.0 * fps), T - int(3.1 * fps)), (T - 12, T + 1)):
        cuts.update(range(a, b))
    inside = np.array([i not in cuts for i in range(len(d))])
    di = d[inside]
    med = float(np.median(di)) if len(di) else 0
    jerks = [int(i) for i in np.where((d > max(4 * med, 6.0)) & inside)[0]]
    frozen = int(np.sum(d[inside] < 0.02))
    m.update(motion_median=round(med, 3), jerks=len(jerks), jerk_frames=jerks[:20], frozen_frames=frozen,
             mean_luma=round(float(lum.mean()), 1), min_luma=round(float(lum.min()), 1))
    if jerks:
        warns.append(f"{len(jerks)} saccade(s) détectée(s) hors coupes (images {jerks[:8]})")
    if frozen > fps * 2:
        warns.append(f"{frozen} images quasi identiques (animation figée ?)")
    if lum.mean() < 35:
        warns.append(f"image globalement sombre (luminance moyenne {lum.mean():.0f}/255)")
    # plans
    longest = max((sh["f1"] - sh["f0"]) / fps for sh in plan["shots"])
    m["longest_shot_s"] = round(longest, 2)
    if longest > STYLE["shot"]["max_s"] + 0.5:
        warns.append(f"plan de {longest:.1f} s (max conseillé {STYLE['shot']['max_s']} s)")
    # sous-titres
    if ass:
        n_ev = sum(1 for ln in Path(ass).read_text(encoding="utf-8").splitlines() if ln.startswith("Dialogue: 0"))
        m["subtitle_events"] = n_ev
        if n_ev < len(plan["dialogue"]):
            errors.append("sous-titres incomplets")
    # moteurs réellement utilisés (transparence)
    m["tts_engines"] = sorted({d["engine"] for d in plan["dialogue"]})
    m["lipsync"] = sorted({d["lipsync"] for d in plan["dialogue"]})
    if any(e.startswith("espeak") for e in m["tts_engines"]):
        warns.append("voix de secours eSpeak NG utilisée (voix Piper indisponible)")
    if render_stats:
        rs = [s for s in render_stats if not s.get("skipped")]
        if rs:
            m["render_s_per_frame"] = round(sum(s["seconds"] for s in rs) / max(1, sum(s["rendered"] for s in rs)), 2)
            m["render_minutes_total"] = round(sum(s["seconds"] for s in rs) / 60, 1)
            m["render_res"] = rs[0]["res"]
            m["render_samples"] = rs[0]["samples"]
    return {"ok": not errors, "errors": errors, "warnings": warns, "metrics": m}


def markdown(ep, rep):
    m = rep["metrics"]
    L = [f"# Rapport qualité — épisode {ep['number']} « {ep['title']} »", "",
         f"- Statut : **{'VALIDÉ' if rep['ok'] else 'REJETÉ'}**",
         f"- Source du scénario : {ep.get('source')}",
         f"- Durée : {m.get('duration')} s — {m.get('width')}x{m.get('height')} — {m.get('fps')} i/s — {m.get('vcodec')}/{m.get('acodec')}",
         f"- Voix : {', '.join(m.get('tts_engines', []))} — lip-sync : {', '.join(m.get('lipsync', []))}",
         f"- Volume : {m.get('loudness_lufs')} LUFS, crête {m.get('true_peak_db')} dBTP",
         f"- Fluidité : {m.get('jerks')} saccade(s), {m.get('frozen_frames')} image(s) figée(s)",
         f"- Rendu : {m.get('render_s_per_frame')} s/image, {m.get('render_minutes_total')} min CPU, "
         f"{m.get('render_res')} px, {m.get('render_samples')} échantillons", ""]
    if rep["errors"]:
        L += ["## Erreurs bloquantes", *[f"- {e}" for e in rep["errors"]], ""]
    if rep["warnings"]:
        L += ["## Avertissements", *[f"- {w}" for w in rep["warnings"]], ""]
    return "\n".join(L)
