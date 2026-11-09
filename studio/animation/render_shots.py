"""Rendu Blender des plans d'un épisode.

blender -b -noaudio -P studio/animation/render_shots.py -- <plan.json> <out_dir> <shot_id,...|all> [--preview]

Chaque plan est rendu image par image dans out_dir/<shot>/NNNN.png puis encodé en out_dir/<shot>.mp4.
Reprise : les images déjà présentes et valides ne sont pas recalculées ; un plan déjà encodé est ignoré.
"""
import json
import math
import os
import subprocess
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))

from bl_character import Character  # noqa: E402
from bl_motion import Performer, prepare  # noqa: E402
from bl_set import Set  # noqa: E402
from bl_util import noise1  # noqa: E402


def load(p):
    return json.load(open(os.path.join(ROOT, p)))


CHARS = load("memory/characters.json")["characters"]
GEO = load("memory/geography.json")["sets3d"]
STYLE = load("memory/visual_style.json")
TUNING_P = os.environ.get("STUDIO_TUNING") or os.path.join(ROOT, "improvements", "tuning.json")
TUNING = json.load(open(TUNING_P)) if os.path.exists(TUNING_P) else {}


def setup_render(preview):
    sc = bpy.context.scene
    R = dict(STYLE["render"])
    R.update({k: v for k, v in TUNING.get("render", {}).items() if k in R})
    lo, hi = STYLE["tuning_bounds"]["res_x"]
    R["res_x"] = max(lo, min(hi, R["res_x"]))
    R["res_y"] = int(round(R["res_x"] * 16 / 9 / 2) * 2)
    lo, hi = STYLE["tuning_bounds"]["samples"]
    R["samples"] = max(lo, min(hi, R["samples"]))
    if preview:
        R.update(res_x=360, res_y=640, samples=4)
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    e = sc.eevee
    for k, v in (("taa_render_samples", R["samples"]), ("use_gtao", R["gtao"]), ("gtao_distance", 1.2),
                 ("use_soft_shadows", R["soft_shadows"]), ("shadow_cascade_size", "2048"), ("shadow_cube_size", "1024"),
                 ("use_bloom", R["bloom"]), ("bloom_intensity", 0.03), ("bloom_threshold", 1.2),
                 ("use_volumetric_lights", R["volumetrics"]), ("use_volumetric_shadows", True),
                 ("volumetric_tile_size", "8"), ("volumetric_end", 220.0), ("use_shadow_high_bitdepth", True)):
        if hasattr(e, k):
            try:
                setattr(e, k, v)
            except Exception:
                pass
    sc.render.resolution_x = R["res_x"]
    sc.render.resolution_y = R["res_y"]
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        sc.view_settings.view_transform = "Filmic"
    return R


class Cam:
    """Caméra cinématographique calculée à chaque image à partir des positions des personnages."""

    def __init__(self, spec, shot, cast, chars, setobj):
        self.s = spec
        self.shot = shot
        self.cast = cast
        self.chars = chars
        self.set = setobj
        bpy.ops.object.camera_add()
        self.cam = bpy.context.object
        bpy.context.scene.camera = self.cam
        d = self.cam.data
        d.sensor_fit = "VERTICAL"
        d.sensor_height = STYLE["camera"]["sensor_height"]
        kind = spec["type"]
        lens_key = {"establish": "wide", "wide": "wide", "landmark": "wide", "two": "medium", "track": "medium",
                    "close": "close", "ots": "over_shoulder", "reveal": "medium"}.get(kind, "medium")
        d.lens = spec.get("lens", STYLE["camera"]["lens"][lens_key])
        d.clip_end = 900
        d.dof.use_dof = STYLE["render"]["dof"]
        d.dof.aperture_fstop = spec.get("fstop", STYLE["camera"]["fstop"][lens_key])
        self.focus = bpy.data.objects.new("focus", None)
        bpy.context.scene.collection.objects.link(self.focus)
        d.dof.focus_object = self.focus

    def _clear(self, pos, look):
        """Avance la caméra vers sa cible tant qu'elle est dans un obstacle (arbre, abri)."""
        p = list(pos)
        for _ in range(40):
            hit = False
            for ox, oy, r, h in self.set.obstacles:
                if math.hypot(p[0] - ox, p[1] - oy) < r and p[2] < h + 1.0:
                    hit = True
                    break
            if not hit:
                break
            p = [p[i] + (look[i] - p[i]) * 0.08 for i in range(3)]
        return tuple(p)

    def head(self, cid):
        ch = self.chars[cid]
        h = ch.p["head"].matrix_world.translation
        return (h.x, h.y, h.z + ch.dims["head_r"] * 1.0)

    def update(self, f):
        s, sh = self.s, self.shot
        u = (f - sh["f0"]) / max(1, sh["f1"] - sh["f0"])
        k = s["type"]
        move = s.get("move", 0.06)
        if k in ("close", "ots", "two", "track") and s.get("subject") in self.chars:
            a = self.head(s["subject"])
            tgt = self.head(s["target"]) if s.get("target") in self.chars else None
            ch = self.chars[s["subject"]]
            yaw = ch.root.rotation_euler.z
            fwd = (math.sin(yaw), -math.cos(yaw))
            if k == "close":
                side = s.get("side", 1)
                acc = CHARS[s["subject"]]["reference"]["look"]["accessories"]
                if "staff" in acc or "spear" in acc:
                    side = -1  # filmer du côté opposé au bâton / à la lance
                ang = math.atan2(fwd[1], fwd[0]) + side * 0.35
                dist = 1.75 * (1 - move * u) * (0.9 if ch.child else 1.0)
                pos = (a[0] + math.cos(ang) * dist, a[1] + math.sin(ang) * dist, a[2] + 0.02)
                look = (a[0], a[1], a[2] - 0.16)
                focus = a
            elif k == "ots" and tgt:
                # derrière l'épaule de la cible, regard vers le sujet
                dx, dy = a[0] - tgt[0], a[1] - tgt[1]
                L = max(0.1, math.hypot(dx, dy))
                nx, ny = dx / L, dy / L
                sd = s.get("side", 1)
                pos = (tgt[0] - nx * 1.35 + ny * 0.62 * sd, tgt[1] - ny * 1.35 - nx * 0.62 * sd, tgt[2] + 0.12)
                look = (a[0], a[1], a[2] - 0.12)
                focus = a
            elif k == "two" and tgt:
                mx, my = (a[0] + tgt[0]) / 2, (a[1] + tgt[1]) / 2
                dx, dy = tgt[0] - a[0], tgt[1] - a[1]
                L = max(0.5, math.hypot(dx, dy))
                nx, ny = -dy / L, dx / L
                # choisir le côté où se trouve la caméra par défaut (-Y)
                if ny > 0:
                    nx, ny = -nx, -ny
                half_w = math.atan(self.cam.data.sensor_height * 9 / 16 / 2 / self.cam.data.lens)
                dist = (L / 2 + 0.6) / math.tan(half_w) * (1 - move * u)
                pos = (mx + nx * dist, my + ny * dist, (a[2] + tgt[2]) / 2 - 0.15)
                look = (mx, my, (a[2] + tgt[2]) / 2 - 0.35)
                focus = (mx, my, a[2])
            else:  # track : travelling latéral sur un personnage qui marche
                dist = 4.2
                side = (math.cos(yaw), math.sin(yaw))
                pos = (a[0] + side[0] * dist * s.get("side", 1) + fwd[0] * 1.2, a[1] + side[1] * dist * s.get("side", 1) + fwd[1] * 1.2, a[2] - 0.2)
                look = (a[0] + fwd[0] * 0.6, a[1] + fwd[1] * 0.6, a[2] - 0.5)
                focus = a
        elif k in ("establish", "wide"):
            c = s.get("center", [0, 0])
            r0 = s.get("radius", 14 if k == "establish" else 7.5)
            h0 = s.get("height", 6.5 if k == "establish" else 2.4)
            a0 = s.get("angle", -90) * math.pi / 180
            sweep = s.get("sweep", 14 if k == "establish" else 5) * math.pi / 180
            ang = a0 + sweep * (u - 0.5)
            r = r0 * (1 - 0.12 * u if k == "establish" else 1 - move * u)
            hh = h0 * (1 - 0.25 * u if k == "establish" else 1)
            pos = (c[0] + math.cos(ang) * r, c[1] + math.sin(ang) * r, self.set.height(c[0], c[1]) + hh)
            look = (c[0], c[1], s.get("look_z", 1.1))
            focus = look
        elif k in ("landmark", "reveal"):
            p0 = s.get("from", [0, -6, 1.6])
            tgt = s["look"]
            if k == "reveal" and s.get("subject") in self.chars:
                a = self.head(s["subject"])
                start = (a[0], a[1], a[2] - 0.1)
                e = 0.5 - 0.5 * math.cos(math.pi * min(1, u * 1.2))
                look = tuple(start[i] + (tgt[i] - start[i]) * e for i in range(3))
                pos = (p0[0], p0[1] - 0.6 * u, p0[2] + 0.4 * u)
            else:
                pos = (p0[0], p0[1] + 1.2 * u, p0[2] + 0.3 * u)
                look = tuple(tgt)
            focus = tgt
        else:
            pos, look, focus = (0, -8, 1.6), (0, 0, 1.2), (0, 0, 1.2)
        hh = STYLE["camera"]["handheld"] * (1.6 if k in ("close", "ots") else 0.8)
        t = f / 30
        pos = (pos[0] + hh * 10 * noise1(t * 0.7, 1), pos[1] + hh * 10 * noise1(t * 0.6, 2), pos[2] + hh * 8 * noise1(t * 0.8, 3))
        pos = self._clear(pos, look)
        floor = self.set.height(pos[0], pos[1]) + 0.35
        pos = (pos[0], pos[1], max(pos[2], floor))
        self.cam.location = pos
        dx, dy, dz = look[0] - pos[0], look[1] - pos[1], look[2] - pos[2]
        yaw = math.atan2(dy, dx) - math.pi / 2
        pitch = math.atan2(dz, math.hypot(dx, dy))
        roll = 0.004 * noise1(t * 0.5, 4) if k in ("close", "ots") else 0
        self.cam.rotation_euler = (math.pi / 2 + pitch, roll, yaw)
        self.focus.location = focus


def build_shot(shot, preview):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    from bl_util import _MATS, _UNIT
    _MATS.clear()
    _UNIT.clear()
    R = setup_render(preview)
    tod = dict(STYLE["time_of_day"][shot.get("tod", "day")])
    tod["name"] = shot.get("tod", "day")
    st = Set(shot["location"], GEO[shot["location"]], tod, shot.get("weather", "clear"))
    chars, perf = {}, {}

    def positions_of(cid, f):
        if cid == "camera":
            c = bpy.context.scene.camera.location
            return (c.x, c.y, c.z)
        ch = chars.get(cid)
        if not ch:
            return None
        return (ch.root.location.x, ch.root.location.y, ch.dims["eye_h"])

    for cid, spec in shot["cast"].items():
        ch = Character(cid, CHARS[cid]["reference"])
        prepare(ch)
        ch.place(spec["pos"][0], spec["pos"][1], spec.get("yaw", 0))
        chars[cid] = ch
        perf[cid] = Performer(ch, spec, positions_of)
    cam = Cam(shot["camera"], shot, shot["cast"], chars, st)
    return st, chars, perf, cam, R


def pose_all(f, st, perf, cam):
    st.animate(f)
    for p in perf.values():
        p.pose(f)
    bpy.context.view_layer.update()
    cam.update(f)
    for p in perf.values():  # le regard « camera » utilise la position de caméra
        p.pose(f)


def render_shot(shot, out, preview=False, only=None):
    d = os.path.join(out, shot["id"])
    mp4 = os.path.join(out, shot["id"] + ".mp4")
    if os.path.exists(mp4) and os.path.getsize(mp4) > 1000 and only is None:
        print("déjà rendu :", shot["id"])
        return {"id": shot["id"], "skipped": True}
    os.makedirs(d, exist_ok=True)
    t0 = time.time()
    st, chars, perf, cam, R = build_shot(shot, preview)
    t_setup = time.time() - t0
    t_first = None
    sc = bpy.context.scene
    frames = list(range(shot["f0"], shot["f1"] + shot.get("handle", 0)))
    if only is not None:
        frames = [frames[i] for i in only if i < len(frames)]
    done = 0
    for i, f in enumerate(frames):
        idx = f - shot["f0"]
        fn = os.path.join(d, f"{idx:04d}.png")
        if os.path.exists(fn) and os.path.getsize(fn) > 2000:
            continue
        pose_all(f, st, perf, cam)
        sc.render.filepath = fn
        bpy.ops.render.render(write_still=True)
        done += 1
        if done == 1:
            t_first = time.time()
        if done % 30 == 0:
            el = time.time() - t0
            print(f"{shot['id']} : {idx + 1}/{len(frames)} images, {el / done:.2f} s/image", flush=True)
    secs = time.time() - t0
    if only is None:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-i", os.path.join(d, "%04d.png"),
                        "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p", mp4], check=True)
    steady = (time.time() - t_first) / (done - 1) if t_first and done > 1 else secs / max(1, done)
    return {"id": shot["id"], "frames": len(frames), "rendered": done, "seconds": round(secs, 1),
            "setup_s": round(t_setup, 1), "s_per_frame": round(steady, 2), "res": [R["res_x"], R["res_y"]], "samples": R["samples"]}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    plan = json.load(open(argv[0]))
    out = argv[1]
    ids = argv[2]
    preview = "--preview" in argv
    only = None
    if "--frames" in argv:
        only = [int(x) for x in argv[argv.index("--frames") + 1].split(",")]
    os.makedirs(out, exist_ok=True)
    stats = []
    for shot in plan["shots"]:
        if ids != "all" and shot["id"] not in ids.split(","):
            continue
        stats.append(render_shot(shot, out, preview, only))
        print("PLAN", json.dumps(stats[-1]), flush=True)
    with open(os.path.join(out, f"stats_{ids.replace(',', '_')[:60]}.json"), "w") as fh:
        json.dump(stats, fh, indent=1)


if __name__ == "__main__":
    main()
