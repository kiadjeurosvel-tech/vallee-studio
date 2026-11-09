"""Synthèse vocale locale et gratuite.

Ordre de préférence :
1. Piper (piper-tts, GPL-3.0 ; voix françaises rhasspy/piper-voices) — qualité naturelle, CPU, hors ligne.
2. eSpeak NG (GPL-3.0) — secours robotique mais toujours disponible.
Le moteur réellement utilisé est noté dans les métadonnées de l'épisode (jamais de faux « Piper »).
"""
import json
import os
import shutil
import subprocess
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VOICE_DIR = Path(os.environ.get("PIPER_VOICES", ROOT / ".cache" / "piper"))
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
SR = 48000


def _voice_path(model):
    lang, name, quality = model.split("-")
    fam = lang.split("_")[0]
    return f"{fam}/{lang}/{name}/{quality}/{model}"


def ensure_voice(model):
    """Télécharge une voix Piper (+ sa fiche de licence) si absente. Renvoie le chemin .onnx ou None."""
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    onnx = VOICE_DIR / f"{model}.onnx"
    if onnx.exists() and (VOICE_DIR / f"{model}.onnx.json").exists():
        return onnx
    base = f"{HF}/{_voice_path(model)}"
    try:
        for suffix in (".onnx.json", ".onnx"):
            urllib.request.urlretrieve(f"{base}{suffix}", VOICE_DIR / f"{model}{suffix}")
        try:
            card = base.rsplit("/", 1)[0] + "/MODEL_CARD"
            urllib.request.urlretrieve(card, VOICE_DIR / f"{model}.MODEL_CARD")
        except Exception:
            pass
        return onnx
    except Exception as e:
        print(f"Voix Piper {model} indisponible ({e}) -> eSpeak NG")
        for suffix in (".onnx.json", ".onnx"):
            p = VOICE_DIR / f"{model}{suffix}"
            if p.exists() and p.stat().st_size < 1000:
                p.unlink()
        return None


_LOADED = {}


def _piper(text, voice, out_raw):
    model = ensure_voice(voice["model"])
    if not model:
        return False
    try:
        from piper import PiperVoice, SynthesisConfig
    except Exception as e:
        print("piper-tts non installé :", e)
        return False
    if voice["model"] not in _LOADED:
        _LOADED[voice["model"]] = PiperVoice.load(str(model))
    pv = _LOADED[voice["model"]]
    multi = (pv.config.num_speakers or 1) > 1
    cfg = SynthesisConfig(speaker_id=voice.get("speaker", 0) if multi else None,
                          length_scale=voice.get("length_scale", 1.0), noise_scale=0.6, noise_w_scale=0.75)
    with wave.open(str(out_raw), "wb") as wf:
        pv.synthesize_wav(text, wf, syn_config=cfg)
    return True


def _espeak(text, voice, out_raw):
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("Ni Piper ni eSpeak NG disponibles : impossible de produire les voix.")
    speed = int(165 / voice.get("length_scale", 1.0))
    subprocess.run([exe, "-v", voice.get("espeak", "fr"), "-p", str(voice.get("espeak_pitch", 50)), "-s", str(speed),
                    "-w", str(out_raw), text], check=True, capture_output=True)
    return True


def synth(text, voice, out_wav):
    """Écrit out_wav (48 kHz mono) et renvoie {'engine', 'seconds'}."""
    out_wav = Path(out_wav)
    raw = out_wav.with_suffix(".raw.wav")
    engine = "piper:" + voice["model"]
    try:
        ok = os.environ.get("STUDIO_TTS") != "espeak" and _piper(text, voice, raw)
    except Exception as e:  # API ou modèle inattendu : on ne bloque jamais la production
        print("Piper en échec :", e)
        ok = False
    if not ok:
        _espeak(text, voice, raw)
        engine = "espeak-ng:" + voice.get("espeak", "fr")
        pitch = 0.0  # le décalage est déjà géré par eSpeak
    else:
        pitch = float(voice.get("pitch", 0))
    filt = ["highpass=f=70", "afade=t=in:d=0.01"]
    if abs(pitch) > 0.01:
        r = 2 ** (pitch / 12)
        filt = [f"asetrate=22050*{r:.5f}", "aresample=22050", f"atempo={1 / r:.5f}"] + filt
    # 22050 = fréquence des voix Piper medium ; on la force avant le décalage de hauteur
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                    "aresample=22050," + ",".join(filt) + f",aresample={SR},silenceremove=start_periods=1:start_threshold=-50dB:stop_periods=-1:stop_duration=0.25:stop_threshold=-50dB",
                    "-ac", "1", "-ar", str(SR), str(out_wav)], check=True)
    raw.unlink(missing_ok=True)
    with wave.open(str(out_wav)) as w:
        secs = w.getnframes() / w.getframerate()
    return {"engine": engine, "seconds": round(secs, 3)}


if __name__ == "__main__":
    import sys
    chars = json.load(open(ROOT / "memory" / "characters.json"))["characters"]
    v = chars[sys.argv[1]]["reference"]["voice"]
    print(synth(sys.argv[2], v, sys.argv[3]))
