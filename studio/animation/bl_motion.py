"""Animation procédurale des personnages : marche, idle, gestes, regard, expressions, clignements, lip-sync.

Tout est une fonction pure de l'image (frame) et du plan : aucune variable d'état, donc
n'importe quelle image peut être recalculée seule (reprise après erreur, rendu découpé).
"""
import json
import math
import os
import zlib

from bl_util import noise1, smoothstep, track

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GESTURES = {k: v for k, v in json.load(open(os.path.join(ROOT, "animations", "gestures.json"))).items()
            if not k.startswith("_")}

EMOTIONS = {
    # brow_dz, brow_tilt, lids, smile, frown, open, chest_rx, head_rx
    "neutral": (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "happy": (0.05, -0.05, 0.85, 0.85, 0.0, 0.0, -0.03, -0.04),
    "sad": (0.02, 0.35, 0.68, 0.0, 0.65, 0.0, 0.08, 0.14),
    "angry": (-0.07, -0.42, 0.72, 0.0, 0.45, 0.0, 0.06, 0.03),
    "fear": (0.1, 0.32, 1.18, 0.0, 0.25, 0.18, 0.1, 0.05),
    "surprised": (0.14, 0.0, 1.22, 0.0, 0.0, 0.35, -0.04, -0.05),
    "worried": (0.05, 0.26, 0.9, 0.0, 0.32, 0.0, 0.05, 0.06),
    "determined": (-0.03, -0.22, 0.85, 0.12, 0.0, 0.0, -0.03, -0.02),
}
JOINTS = ("hips", "spine", "chest", "neck", "head", "shoulder_L", "shoulder_R", "elbow_L", "elbow_R",
          "hip_L", "hip_R", "knee_L", "knee_R")


def _yaw_to(dx, dy):
    return math.atan2(dx, -dy)


def _wrap(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


class Performer:
    """Associe un Character et sa partition (dict venant du plan de tournage)."""

    def __init__(self, ch, spec, positions_of):
        self.ch = ch
        self.s = spec
        self.seed = zlib.crc32(ch.id.encode()) % 1000
        self.positions_of = positions_of  # callable(id, f) -> (x, y, z_eye)
        self.walks = sorted(spec.get("walks", []), key=lambda w: w["f0"])
        self.start = spec["pos"]
        # longueur cumulée avant chaque marche (phase de pas continue)
        self._cum, self._len = [], []
        acc, p = 0.0, self.start
        for w in self.walks:
            self._cum.append(acc)
            self._len.append(math.dist(p, w["to"]))
            acc += self._len[-1]
            p = w["to"]

    # ------------------------------------------------------------------ déplacement
    def where(self, f):
        """(x, y, distance parcourue, vitesse relative 0..1, cap de marche ou None)."""
        p = list(self.start)
        for i, w in enumerate(self.walks):
            if f < w["f0"]:
                return p[0], p[1], self._cum[i], 0.0, None
            q = w["to"]
            L = math.dist(p, q)
            if f <= w["f1"]:
                u = (f - w["f0"]) / max(1, w["f1"] - w["f0"])
                e = smoothstep(u) * 0.35 + u * 0.65  # démarrage/arrêt doux mais pas de glissade
                x, y = p[0] + (q[0] - p[0]) * e, p[1] + (q[1] - p[1]) * e
                ramp = min(1.0, (f - w["f0"]) / 8, (w["f1"] - f) / 8 + 0.25)
                return x, y, self._cum[i] + L * e, max(0.0, ramp), _yaw_to(q[0] - p[0], q[1] - p[1]) if L > 0.01 else None
            p = list(q)
        tot = self._cum[-1] + self._len[-1] if self.walks else 0.0
        return p[0], p[1], tot, 0.0, None

    def look_point(self, f):
        keys = self.s.get("look", [])
        tgt = None
        for fr, t in keys:
            if f >= fr:
                tgt = t
        if tgt is None:
            return None
        if isinstance(tgt, str):
            return self.positions_of(tgt, f)
        return tgt

    # ------------------------------------------------------------------ pose
    def pose(self, f, fps=30):
        ch, P = self.ch, self.ch.p
        H = ch.H
        rot = {j: [0.0, 0.0, 0.0] for j in JOINTS}
        x, y, dist, speed, heading = self.where(f)
        t = f / fps
        sd = self.seed

        # --- cap du corps : marche => cap de marche ; sinon on se tourne vers la cible du regard
        lp = self.look_point(f)
        body_yaw = self.s.get("yaw", 0.0)
        yaw_keys = [(0, body_yaw)]
        for w in self.walks:
            pw = self.start if w is self.walks[0] else self.walks[self.walks.index(w) - 1]["to"]
            yaw_keys.append((w["f0"] - 4, _yaw_to(w["to"][0] - pw[0], w["to"][1] - pw[1])))
            if "face" in w:
                yaw_keys.append((w["f1"] - 2, w["face"]))
        yaw = track(yaw_keys, f, body_yaw, blend=10)
        if heading is None and lp is not None and self.s.get("turn_to_look", True):
            want = _yaw_to(lp[0] - x, lp[1] - y)
            d = _wrap(want - yaw)
            if abs(d) > 0.9:  # au-delà de ~50°, le corps suit le regard
                yaw += d - math.copysign(0.9, d)
        ch.root.location = (x, y, 0)
        ch.root.rotation_euler = (0, 0, yaw)

        # --- marche
        w = speed
        hips_z = 0.0
        if w > 0.001:
            ph = math.pi * dist / ch.stride
            A, K = 0.42, 0.95
            s = math.sin(ph)
            c = math.cos(ph)
            rot["hip_L"][0] += -A * s * w
            rot["hip_R"][0] += A * s * w
            rot["knee_L"][0] += (0.12 + K * max(0.0, c) ** 1.3) * w
            rot["knee_R"][0] += (0.12 + K * max(0.0, -c) ** 1.3) * w
            hips_z += (-0.028 * H * abs(s) + 0.012 * H) * w
            rot["hips"][2] += 0.07 * s * w
            rot["chest"][2] += -0.1 * s * w
            rot["chest"][0] += 0.05 * w
            rot["shoulder_L"][0] += 0.5 * A * s * w
            rot["shoulder_R"][0] += -0.5 * A * s * w
            rot["elbow_L"][0] += (-0.25 - 0.25 * max(0, -s)) * w
            rot["elbow_R"][0] += (-0.25 - 0.25 * max(0, s)) * w
        # --- idle (respiration, transfert de poids, bras détendus)
        idle = 1 - w
        br = math.sin(t * 2 * math.pi / 4.2 + sd)
        rot["chest"][0] += 0.012 * br
        rot["neck"][0] += -0.008 * br
        rot["hips"][1] += 0.025 * noise1(t * 0.35, sd) * idle
        rot["chest"][1] += -0.02 * noise1(t * 0.35, sd) * idle
        rot["shoulder_L"][1] += 0.1
        rot["shoulder_R"][1] += -0.1
        rot["elbow_L"][0] += -0.15 * idle
        rot["elbow_R"][0] += -0.15 * idle
        if ch.old:
            rot["chest"][0] += 0.12
            rot["neck"][0] += 0.05

        # --- émotion (pistes lissées)
        emo_keys = [(fr, list(EMOTIONS.get(e, EMOTIONS["neutral"]))) for fr, e in self.s.get("emotion", [])]
        E = track(emo_keys, f, list(EMOTIONS["neutral"]), blend=12)
        bdz, btilt, lids, smile, frown, eopen, crx, hrx = E
        rot["chest"][0] += crx
        rot["head"][0] += hrx

        # --- gestes
        for g in self.s.get("gestures", []):
            G = GESTURES.get(g["name"])
            if not G:
                continue
            g0 = g["f"]
            dur = G["dur"] * fps * g.get("scale", 1.0)
            hold = G["hold"] * fps * g.get("scale", 1.0)
            ramp = (dur - hold) / 2
            if not (g0 <= f <= g0 + dur):
                continue
            k = smoothstep((f - g0) / max(1, ramp)) * (1 - smoothstep((f - g0 - ramp - hold) / max(1, ramp)))
            for j, (rx, ry, rz) in G["joints"].items():
                side = -1 if j.endswith("_R") else 1
                ryv = ry * side if j.startswith("shoulder") else ry
                base = rot[j]
                # on remplace la pose de base (pas d'addition), pondéré par k
                rot[j] = [base[0] * (1 - k) + rx * k, base[1] * (1 - k) + ryv * k, base[2] * (1 - k) + rz * k]
            if "wiggle" in G:
                wg = G["wiggle"]
                rot[wg["joint"]][wg["axis"]] += wg["amp"] * math.sin((f - g0) / fps * 2 * math.pi * wg["freq"]) * k
            hips_z -= G.get("hips_drop", 0) * H * k

        # --- parole : hochements, petits gestes de rythme
        mouth = self._mouth(f)
        talk = min(1.0, sum(mouth) * 1.5)
        talk_s = max(min(1.0, sum(self._mouth(f + d)) * 1.5) for d in (-8, -4, 0, 4, 8))
        rot["head"][0] += 0.035 * noise1(t * 2.3, sd + 3) * talk_s
        rot["head"][2] += 0.05 * noise1(t * 1.1, sd + 5) * talk_s
        rot["shoulder_R"][0] += -0.12 * (0.5 + 0.5 * noise1(t * 0.9, sd + 7)) * talk_s * idle
        rot["elbow_R"][0] += -0.35 * (0.5 + 0.5 * noise1(t * 1.3, sd + 9)) * talk_s * idle

        # --- regard (tête + cou + yeux)
        eye_yaw = 0.0
        if lp is not None:
            hx, hy, hz = x, y, ch.dims["eye_h"]
            rel = _wrap(_yaw_to(lp[0] - hx, lp[1] - hy) - yaw)
            rel = max(-1.2, min(1.2, rel))
            pitch = math.atan2(hz - lp[2], max(0.3, math.dist((hx, hy), lp[:2])))
            pitch = max(-0.45, min(0.5, pitch))
            look_k = track([(fr, 1.0) for fr, _ in self.s.get("look", [])[:1]], f, 0.0, blend=8)
            rot["neck"][2] += rel * 0.4 * look_k
            rot["head"][2] += rel * 0.45 * look_k
            rot["head"][0] += pitch * 0.7 * look_k
            eye_yaw = max(-0.3, min(0.3, rel * 0.15)) * look_k
        sacc = 0.04 * math.copysign(1, noise1(t * 0.7, sd + 11)) if abs(noise1(t * 0.7, sd + 11)) > 0.6 else 0.0
        for ep in ch.eyes:
            ep.rotation_euler = (0, 0, eye_yaw + sacc)

        # --- clignements déterministes (toutes les 2 à 5 s)
        blink = 1.0
        period = 2.0 + 3.0 * ((sd * 7919) % 100) / 100
        bt = (t + (sd % 37) / 10) % period
        if bt < 0.16:
            blink = abs(bt - 0.08) / 0.08
        op = lids * blink
        lid_rx = 1.5 + (-0.4 - 1.5) * min(op, 1.0) - 0.35 * max(0.0, op - 1.0)
        for lp_ in ch.lids:
            lp_.rotation_euler = (lid_rx, 0, 0)
        r = ch.dims["head_r"]
        for s_, bp in ch.brows:
            bp.location.z = bp["base_z"] + (bdz + 0.04 * (1 - blink) * 0) * r + 0.02 * r * talk * noise1(t * 3, sd)
            bp.rotation_euler = (0, s_ * btilt, 0)

        # --- bouche : visèmes + expression
        sk = ch.mouth.data.shape_keys.key_blocks
        o_, w_, r_, fv_ = mouth
        sk["open"].value = min(1.0, o_ + eopen * (1 - talk))
        sk["wide"].value = w_
        sk["round"].value = r_
        sk["fv"].value = fv_
        sk["smile"].value = smile * (1 - 0.5 * talk)
        sk["frown"].value = frown * (1 - 0.4 * talk)

        # --- application
        P["hips"].location.z = P["hips"]["base_z"] + hips_z
        for j in JOINTS:
            if j in P:
                P[j].rotation_euler = rot[j]

    def _mouth(self, f):
        m = self.s.get("mouth")
        if not m:
            return (0.0, 0.0, 0.0, 0.0)
        i = f - m["f0"]
        W = m["w"]
        if 0 <= i < len(W):
            return tuple(W[i])
        return (0.0, 0.0, 0.0, 0.0)


def prepare(ch):
    """Mémorise les positions de base (appelé une fois après construction)."""
    ch.p["hips"]["base_z"] = ch.p["hips"].location.z
    for _, bp in ch.brows:
        bp["base_z"] = bp.location.z
