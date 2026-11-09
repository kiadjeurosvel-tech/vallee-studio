"""Modèle de langage local et gratuit (llama.cpp via llama-cpp-python, CPU).

Modèles (licence Apache-2.0) essayés dans l'ordre de config/studio.json > llm.models.
Aucune API payante : le modèle tourne sur le runner GitHub (4 vCPU, 16 Go).
"""
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.environ.get("LLM_CACHE", ROOT / ".cache" / "llm"))


def _cfg():
    return json.loads((ROOT / "config" / "studio.json").read_text())["llm"]


def ensure_model():
    CACHE.mkdir(parents=True, exist_ok=True)
    for m in _cfg()["models"]:
        p = CACHE / m["file"]
        if p.exists() and p.stat().st_size > 100_000_000:
            return p, m
    for m in _cfg()["models"]:
        p = CACHE / m["file"]
        url = f"https://huggingface.co/{m['repo']}/resolve/main/{m['file']}"
        try:
            print("Téléchargement du modèle", m["file"], "…", flush=True)
            tmp = p.with_suffix(".part")
            urllib.request.urlretrieve(url, tmp)
            tmp.rename(p)
            return p, m
        except Exception as e:
            print("Modèle indisponible :", m["file"], e)
    return None, None


_LLM = None


def chat(system, user, max_tokens=1400, temperature=0.8, seed=0):
    """Renvoie (texte, nom_du_modèle) ou lève une exception si aucun modèle n'est utilisable."""
    global _LLM
    try:
        from llama_cpp import Llama
    except Exception as e:
        raise RuntimeError(f"llama-cpp-python absent : {e}")
    path, meta = ensure_model()
    if not path:
        raise RuntimeError("aucun modèle local disponible")
    if _LLM is None:
        _LLM = Llama(model_path=str(path), n_ctx=8192, n_threads=os.cpu_count() or 4, verbose=False, seed=seed)
    t0 = time.time()
    out = _LLM.create_chat_completion(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens, temperature=temperature, top_p=0.92, repeat_penalty=1.08,
        response_format={"type": "json_object"})
    txt = out["choices"][0]["message"]["content"]
    print(f"LLM {meta['file']} : {out['usage']['completion_tokens']} jetons en {time.time() - t0:.0f} s", flush=True)
    return txt, meta["file"]
