"""Montage final : plans -> vidéo 1080x1920 H.264/AAC avec transitions, titres, sous-titres, carte de vote,
voix, ambiances, bruitages et musique (mixage numpy + normalisation ffmpeg).
"""
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

from studio.audio import soundscape
from studio.audio.lipsync import read_wav

ROOT = Path(__file__).resolve().parents[2]
STYLE = json.loads((ROOT / "memory" / "visual_style.json").read_text())
CHARS = json.loads((ROOT / "memory" / "characters.json").read_text())["characters"]
GEO = json.loads((ROOT / "memory" / "geography.json").read_text())["sets3d"]
SR = soundscape.SR


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg a échoué : {' '.join(map(str, cmd))[:300]}\n{r.stderr[-1500:]}")
    return r


# ------------------------------------------------------------------ sous-titres (ASS)
def _ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_color(hexcol):
    h = hexcol.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _lighten(hexcol, k=0.45):
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(int(c + (255 - c) * k) for c in (r, g, b))


def _chunks(text, max_chars):
    words, out, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    # regrouper par 2 lignes
    return [out[i:i + 2] for i in range(0, len(out), 2)]


def subtitles(plan, path, series):
    S = STYLE["subtitles"]
    W, H = STYLE["output"]["width"], STYLE["output"]["height"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{S['font']},{S['size']},&H00FFFFFF,&H00FFFFFF,&H00101010,&H64000000,-1,0,0,0,100,100,0,0,1,{S['outline_px']},{S['shadow']},2,70,70,{S['margin_v']},1
Style: Narr,{S['font']},{S['size'] - 4},&H00F0F0F0,&H00FFFFFF,&H00101010,&H64000000,-1,-1,0,0,100,100,0,0,1,{S['outline_px']},{S['shadow']},2,70,70,{S['margin_v']},1
Style: Name,{S['font']},34,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,2,0,1,3,0,2,70,70,{S['margin_v'] + 150},1
Style: Series,{S['font']},44,&H00F2F2F2,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,6,0,1,3,1,8,60,60,330,1
Style: Title,{S['font']},88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,2,8,60,60,400,1
Style: Q,{S['font']},56,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,5,1,8,70,70,520,1
Style: Opt,{S['font']},46,&H00FFFFFF,&H00FFFFFF,&H40202020,&H40202020,-1,0,0,0,100,100,0,0,3,16,0,8,80,80,800,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    ev.append(f"Dialogue: 2,{_ass_time(0.15)},{_ass_time(3.4)},Series,,0,0,0,,{{\\fad(400,500)}}{series.upper()}")
    ev.append(f"Dialogue: 2,{_ass_time(0.35)},{_ass_time(3.6)},Title,,0,0,0,,{{\\fad(500,500)}}Épisode {plan['episode']}\\N{plan['title']}")
    for d in plan["dialogue"]:
        sp = d["speaker"].lower()
        narr = sp == "varn"
        groups = _chunks(d["text"], S["max_chars"])
        total_chars = sum(len(" ".join(g)) for g in groups) or 1
        t = d["start"]
        dur = d["end"] - d["start"]
        if not narr:
            col = _ass_color(_lighten(CHARS[sp]["reference"]["look"]["tunic"]))
            ev.append(f"Dialogue: 1,{_ass_time(d['start'])},{_ass_time(d['end'] + 0.15)},Name,,0,0,0,,{{\\c{col}}}{CHARS[sp]['name'].upper()}")
        for g in groups:
            share = len(" ".join(g)) / total_chars * dur
            txt = "\\N".join(g)
            ev.append(f"Dialogue: 0,{_ass_time(t)},{_ass_time(t + share + 0.08)},{'Narr' if narr else 'Sub'},,0,0,0,,{txt}")
            t += share
    T = plan["seconds"]
    c = plan["choice"]
    ev.append(f"Dialogue: 3,{_ass_time(T - 3.8)},{_ass_time(T)},Q,,0,0,0,,{{\\fad(300,0)}}{c['question']}")
    ev.append(f"Dialogue: 3,{_ass_time(T - 3.5)},{_ass_time(T)},Opt,,0,0,0,,{{\\fad(300,0)\\c&H0050E0FF&}}A{{\\c&H00FFFFFF&}}  {c['A']}")
    ev.append(f"Dialogue: 3,{_ass_time(T - 3.3)},{_ass_time(T)},Opt,,0,0,1010,,{{\\fad(300,0)\\c&H00FFB050&}}B{{\\c&H00FFFFFF&}}  {c['B']}")
    Path(path).write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    # SRT (pour les plateformes)
    srt, k = [], 1
    for d in plan["dialogue"]:
        def ts(x):
            return f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(x * 1000 % 1000):03d}"
        srt.append(f"{k}\n{ts(d['start'])} --> {ts(d['end'])}\n{d['text']}\n")
        k += 1
    Path(path).with_suffix(".srt").write_text("\n".join(srt), encoding="utf-8")


# ------------------------------------------------------------------ audio
def mix(plan, work, out_wav, seed):
    rng = np.random.default_rng(seed)
    n = int(plan["seconds"] * SR) + SR
    voice = np.zeros(n, np.float32)
    for d in plan["dialogue"]:
        x, sr = read_wav(work / "audio" / f"line_{d['i']:02d}.wav")
        x = x / (np.sqrt(np.mean(x ** 2)) + 1e-6) * 0.12  # niveau homogène entre personnages
        i = int(d["start"] * SR)
        voice[i:i + len(x)] += x[: n - i]
    amb = np.zeros(n, np.float32)
    sfx = np.zeros(n, np.float32)
    fps = plan["fps"]
    scenes = {}
    for sh in plan["shots"]:
        scenes.setdefault(sh["scene"], [sh["f0"], sh["f1"], sh])[1] = sh["f1"]
    for si, (f0, f1, sh) in scenes.items():
        a, b = int(f0 / fps * SR), min(n, int(f1 / fps * SR) + int(0.6 * SR))
        seg = soundscape.bed(b - a, rng, sh["location"], sh["tod"], sh["weather"], GEO[sh["location"]])
        L = len(seg)
        env = np.ones(L, np.float32)
        fl = min(L // 2, int(0.6 * SR))
        env[:fl] = np.linspace(0, 1, fl)
        env[-fl:] = np.linspace(1, 0, fl)
        amb[a:a + L] += seg * env
    # bruitages : pas pendant les marches, souffle sur les gestes amples
    seen = set()
    for sh in plan["shots"]:
        for cid, p in sh["cast"].items():
            for w in p.get("walks", []):
                key = (cid, w["f0"])
                if key in seen:
                    continue
                seen.add(key)
                f = w["f0"]
                while f < w["f1"]:
                    i = int(f / fps * SR)
                    s = soundscape.footstep(rng, "stone" if sh["location"] in ("rocher_anciens", "grotte_legendes") else "grass")
                    sfx[i:i + len(s)] += s[: n - i] * (0.6 if cid not in sh["camera"].values() else 1.0)
                    f += 14
            for g in p.get("gestures", []):
                key = (cid, "g", g["f"])
                if key in seen or g["name"] not in ("point", "stop", "open_arms", "fist", "wave"):
                    continue
                seen.add(key)
                i = int(g["f"] / fps * SR)
                s = soundscape.whoosh(rng)
                if 0 <= i < n:
                    sfx[i:i + len(s)] += s[: n - i]
    mus = soundscape.music(n, rng, plan.get("mood", "mystere"))
    # ducking : la musique et l'ambiance s'effacent sous les voix
    env = np.convolve(np.abs(voice), np.ones(int(0.25 * SR)) / int(0.25 * SR), mode="same")
    duck = 1 - 0.65 * np.clip(env / 0.05, 0, 1)
    fade = np.ones(n, np.float32)
    fl = int(1.5 * SR)
    fade[:int(0.3 * SR)] = np.linspace(0, 1, int(0.3 * SR))
    fade[-fl:] = np.linspace(1, 0, fl)
    mixd = voice + 0.55 * amb * (0.6 + 0.4 * duck) + 0.75 * sfx + 0.5 * mus * duck * fade
    # stéréo : ambiance et musique légèrement élargies
    side = 0.12 * (amb - np.roll(amb, 240)) + 0.08 * (mus - np.roll(mus, 360))
    st = np.stack([mixd + side, mixd - side], 1)
    st = np.clip(st / max(1.0, np.abs(st).max() / 0.95), -1, 1)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((st[: int(plan["seconds"] * SR)] * 32767).astype(np.int16).tobytes())


# ------------------------------------------------------------------ image
def video(plan, shots_dir, ass, out_mp4, audio_wav):
    O = STYLE["output"]
    W, H, fps = O["width"], O["height"], plan["fps"]
    dip = 8
    inputs, filters = [], []
    for k, sh in enumerate(plan["shots"]):
        mp4 = Path(shots_dir) / f"{sh['id']}.mp4"
        if not mp4.exists():
            raise FileNotFoundError(f"plan manquant : {mp4}")
        inputs += ["-i", str(mp4)]
        n = sh["f1"] - sh["f0"]
        f = [f"[{k}:v]trim=end_frame={n},setpts=PTS-STARTPTS,fps={fps}",
             f"scale={W}:{H}:flags=lanczos", "unsharp=5:5:0.35:5:5:0.0", "setsar=1"]
        if sh["transition_in"] == "dip" or k == 0:
            f.append(f"fade=t=in:st=0:d={dip / fps:.3f}")
        nxt = plan["shots"][k + 1] if k + 1 < len(plan["shots"]) else None
        if nxt is None or nxt["transition_in"] == "dip":
            f.append(f"fade=t=out:st={(n - dip) / fps:.3f}:d={dip / fps:.3f}")
        filters.append(",".join(f) + f"[v{k}]")
    cat = "".join(f"[v{k}]" for k in range(len(plan["shots"]))) + f"concat=n={len(plan['shots'])}:v=1:a=0[cat]"
    assp = str(ass).replace("\\", "/").replace(":", "\\:")
    na = len(plan["shots"])
    graph = ";".join(filters + [cat, f"[cat]ass='{assp}',format=yuv420p[vout]",
                                f"[{na}:a]loudnorm=I=-14:TP=-1.5:LRA=9,aresample=48000[aout]"])
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-i", str(audio_wav), "-filter_complex", graph,
           "-map", "[vout]", "-map", "[aout]",
           "-c:v", O["vcodec"], "-preset", O["preset"], "-crf", str(O["crf"]), "-profile:v", "high", "-level", "4.1",
           "-pix_fmt", O["pix_fmt"], "-r", str(fps), "-c:a", O["acodec"], "-b:a", O["abitrate"], "-ar", "48000",
           "-movflags", "+faststart", "-shortest", str(out_mp4)]
    run(cmd)


def thumbnail(out_mp4, plan, png):
    # image d'un gros plan au milieu de l'épisode
    sh = next((s for s in plan["shots"] if s["camera"]["type"] == "close"), plan["shots"][0])
    t = (sh["f0"] + sh["f1"]) / 2 / plan["fps"]
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(out_mp4), "-frames:v", "1", str(png)])


def assemble(plan, work, out_dir, series, seed):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"vallee_ep{plan['episode']:03d}"
    ass = out_dir / f"{name}.ass"
    subtitles(plan, ass, series)
    wav = work / "mix.wav"
    mix(plan, work, wav, seed)
    tmp = out_dir / f"{name}.tmp.mp4"
    video(plan, work / "shots", ass, tmp, wav)
    final = out_dir / f"{name}.mp4"
    tmp.replace(final)
    thumbnail(final, plan, out_dir / f"{name}.png")
    return final
