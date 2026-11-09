"""Construction procédurale d'un personnage à partir de sa fiche de référence (memory/characters.json).

Même fiche => même personnage, au millimètre près : aucune part d'aléatoire ici.
Hiérarchie de pivots (empties) animables :
root > hips > spine > chest > neck > head ; chest > shoulder_L/R > elbow_L/R > hand_L/R ;
hips > hip_L/R > knee_L/R. Le personnage regarde vers -Y.
"""
import math

import bmesh
import bpy

from mathutils import Vector

from bl_util import W, box, cone, cyl, empty, mat, sphere, torus

MOUTH_SHAPES = {
    # (largeur, ouverture, courbure)  courbure>0 = sourire
    "rest": (1.0, 0.07, 0.0),
    "open": (0.95, 0.75, 0.0),
    "wide": (1.25, 0.32, 0.05),
    "round": (0.55, 0.5, 0.0),
    "fv": (0.9, 0.12, -0.02),
    "smile": (1.15, 0.1, 0.38),
    "frown": (0.95, 0.08, -0.3),
}


def _mouth_mesh(name, w, h, material, parent, loc):
    """Bouche en lentille avec clés de forme (visèmes + expressions)."""
    n = 28
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()

    def pts(sw, sh, sc):
        out = []
        for i in range(n):
            t = 2 * math.pi * i / n
            x = math.cos(t) * w * sw
            z = math.sin(t) * h * sh + sc * h * 6 * (x / w) ** 2 - sc * h * 2
            y = -0.25 * w * (1 - (x / (w * 1.3)) ** 2) * 0.2
            out.append((x, y, z))
        return out

    base = pts(*MOUTH_SHAPES["rest"])
    vs = [bm.verts.new(p) for p in base]
    bm.faces.new(vs)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(material)
    o.shape_key_add(name="Basis")
    for key, (sw, sh, sc) in MOUTH_SHAPES.items():
        if key == "rest":
            continue
        sk = o.shape_key_add(name=key)
        for i, p in enumerate(pts(sw, sh, sc)):
            sk.data[i].co = p
    o["wpos"] = list(loc)
    o.location = Vector(loc) - W(parent)
    o.parent = parent
    return o


class Character:
    def __init__(self, cid, ref, scene_scale=1.0):
        self.id = cid
        self.ref = ref
        L = ref["look"]
        self.H = H = L["height"] * scene_scale
        self.child = bool(L.get("child"))
        self.old = bool(L.get("old"))
        bw = L["build"]
        self.p = {}
        skin = mat(f"skin_{cid}", L["skin"], rough=0.6, sss=0.08)
        tunic = mat(f"tunic_{cid}", L["tunic"], rough=0.9)
        pants = mat(f"pants_{cid}", L["pants"], rough=0.9)
        leather = mat("leather", "#4a3020", rough=0.8)
        hairm = mat(f"hair_{cid}", L["hair"]["color"], rough=0.55)
        dark = mat("mouth_dark", "#2a0808", rough=0.9)

        head_r = H * (0.112 if self.child else 0.088)
        hip_h = H * (0.44 if self.child else 0.48)
        sh_h = H * (0.74 if self.child else 0.79)
        thigh = hip_h * 0.52
        shin = hip_h * 0.48
        torso_w = H * 0.115 * bw
        arm_up = H * 0.17
        arm_lo = H * 0.16
        self.dims = dict(head_r=head_r, hip_h=hip_h, sh_h=sh_h, thigh=thigh, shin=shin, eye_h=sh_h + H * 0.045 + head_r)
        self.stride = thigh * 1.1

        root = self.root = empty(f"{cid}_root")
        hips = self.p["hips"] = empty(f"{cid}_hips", (0, 0, hip_h), root)
        spine = self.p["spine"] = empty(f"{cid}_spine", (0, 0, hip_h), hips)
        # Torse (tunique) + jupe de tunique
        cone(f"{cid}_torso", (0, 0, hip_h + (sh_h - hip_h) / 2), torso_w * 0.92, torso_w * 0.78, (sh_h - hip_h),
             tunic, spine, scale=(1, 0.62, 1), verts=40)
        cone(f"{cid}_skirt", (0, 0, hip_h - H * 0.03), torso_w * 1.12, torso_w * 0.9, H * 0.12, tunic, spine,
             scale=(1, 0.7, 1))
        torus(f"{cid}_belt", (0, 0, hip_h + H * 0.025), torso_w * 0.9, H * 0.012, leather, spine, scale=(1, 0.64, 1))
        chest = self.p["chest"] = empty(f"{cid}_chest", (0, 0, sh_h), spine)
        sphere(f"{cid}_shoulders", (0, 0, sh_h - H * 0.015), (torso_w * 0.95, torso_w * 0.5, H * 0.035), tunic, chest)
        neck = self.p["neck"] = empty(f"{cid}_neck", (0, 0, sh_h), chest)
        cyl(f"{cid}_neckm", (0, 0, sh_h + H * 0.03), H * 0.032, H * 0.07, skin, neck)
        hc = sh_h + H * 0.045 + head_r * 0.95
        head = self.p["head"] = empty(f"{cid}_head", (0, 0, sh_h + H * 0.05), neck)
        sphere(f"{cid}_skull", (0, 0, hc), (head_r * 0.93, head_r * 0.95, head_r * 1.06), skin, head, subsurf=1)
        sphere(f"{cid}_jaw", (0, -head_r * 0.12, hc - head_r * 0.38), (head_r * 0.8, head_r * 0.8, head_r * 0.62), skin, head, subsurf=1)
        for s in (-1, 1):
            sphere(f"{cid}_ear{s}", (s * head_r * 0.92, 0.02 * head_r, hc), (head_r * 0.12, head_r * 0.08, head_r * 0.2), skin, head)
        sphere(f"{cid}_nose", (0, -head_r * 0.98, hc - head_r * 0.12),
               (head_r * 0.12, head_r * 0.14, head_r * 0.17 if not self.child else head_r * 0.12), skin, head)
        # Yeux : blanc, iris, pupille ; pivot par œil pour clignement/regard
        white = mat("eye_white", "#f4f1ea", rough=0.25)
        iris = mat(f"iris_{cid}", L["eyes"], rough=0.3)
        pupil = mat("pupil", "#050505", rough=0.2)
        er = head_r * (0.2 if self.child else 0.165)
        self.eyes = []
        for s in (-1, 1):
            ep = empty(f"{cid}_eye{s}", (s * head_r * 0.36, -head_r * 0.8, hc + head_r * 0.12), head)
            sphere(f"{cid}_eyew{s}", W(ep), (er, er * 0.7, er), white, ep)
            sphere(f"{cid}_iris{s}", W(ep) + Vector((0, -er * 0.62, 0)), (er * 0.58, er * 0.15, er * 0.58), iris, ep)
            sphere(f"{cid}_pupil{s}", W(ep) + Vector((0, -er * 0.72, 0)), (er * 0.28, er * 0.08, er * 0.28), pupil, ep)
            self.eyes.append(ep)
        # Paupières : demi-sphère couleur peau qui descend (clignement / plissement)
        self.lids = []
        for s, ep in zip((-1, 1), self.eyes):
            lp = empty(f"{cid}_lidp{s}", W(ep), head)
            lid = sphere(f"{cid}_lid{s}", W(lp), (er * 1.08, er * 0.82, er * 1.08), skin, lp, unique=True)
            # ne garder que la moitié supérieure
            me = lid.data
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < 0.05], context="VERTS")
            bm.to_mesh(me)
            bm.free()
            lp.rotation_euler.x = -0.4  # ouvert (1.5 = fermé)
            self.lids.append(lp)
        # Sourcils
        bc = mat(f"brow_{cid}", L.get("brow_color", L["hair"]["color"]), rough=0.7)
        self.brows = []
        for s in (-1, 1):
            bp = empty(f"{cid}_browp{s}", (s * head_r * 0.36, -head_r * 0.86, hc + head_r * 0.36), head)
            box(f"{cid}_brow{s}", W(bp), (er * 2.1, er * 0.35, er * (0.5 if not self.old else 0.6)),
                bc, bp, bevel=er * 0.12)
            self.brows.append((s, bp))
        # Bouche
        self.mouth = _mouth_mesh(f"{cid}_mouth", head_r * 0.3, head_r * 0.14, dark, head,
                                 (0, -head_r * 0.93, hc - head_r * 0.42))
        self._hair(L, head, hc, head_r, hairm, skin)
        self._paint(L, head, hc, head_r)
        # Bras
        for s, side in ((-1, "L"), (1, "R")):
            shp = self.p[f"shoulder_{side}"] = empty(f"{cid}_sh{side}", (s * torso_w * 0.95, 0, sh_h - H * 0.02), chest)
            sphere(f"{cid}_shj{side}", W(shp), (H * 0.045 * bw ** 0.5,) * 3, tunic, shp)
            cyl(f"{cid}_uarm{side}", (s * torso_w * 0.95, 0, sh_h - H * 0.02 - arm_up / 2), H * 0.033 * bw ** 0.5, arm_up, tunic, shp)
            el = self.p[f"elbow_{side}"] = empty(f"{cid}_el{side}", (s * torso_w * 0.95, 0, sh_h - H * 0.02 - arm_up), shp)
            sphere(f"{cid}_elj{side}", W(el), (H * 0.03,) * 3, skin, el)
            cyl(f"{cid}_farm{side}", (s * torso_w * 0.95, 0, sh_h - H * 0.02 - arm_up - arm_lo / 2), H * 0.027, arm_lo, skin, el)
            hd = self.p[f"hand_{side}"] = empty(f"{cid}_hand{side}", (s * torso_w * 0.95, 0, sh_h - H * 0.02 - arm_up - arm_lo), el)
            sphere(f"{cid}_handm{side}", W(hd) + Vector((0, 0, -H * 0.03)),
                   (H * 0.032, H * 0.024, H * 0.045), skin, hd)
        # Jambes
        boot = mat("boot", "#3a2618", rough=0.85)
        for s, side in ((-1, "L"), (1, "R")):
            hp = self.p[f"hip_{side}"] = empty(f"{cid}_hip{side}", (s * torso_w * 0.45, 0, hip_h), hips)
            cyl(f"{cid}_thigh{side}", (s * torso_w * 0.45, 0, hip_h - thigh / 2), H * 0.05 * bw ** 0.5, thigh, pants, hp)
            kn = self.p[f"knee_{side}"] = empty(f"{cid}_knee{side}", (s * torso_w * 0.45, 0, hip_h - thigh), hp)
            cyl(f"{cid}_shin{side}", (s * torso_w * 0.45, 0, hip_h - thigh - shin / 2), H * 0.04, shin, pants, kn)
            sphere(f"{cid}_foot{side}", (s * torso_w * 0.45, -H * 0.035, H * 0.022), (H * 0.045, H * 0.08, H * 0.03), boot, kn)
        self._accessories(L, skin, tunic, leather, torso_w, head, hc, head_r, sh_h, hip_h)
        for o in bpy.data.objects:
            if o.name.startswith(cid + "_") and o.type == "MESH":
                o.visible_shadow = True

    # ------------------------------------------------------------------ apparence
    def _hair(self, L, head, hc, r, hairm, skin):
        cid, st = self.id, L["hair"]["style"]
        cap = sphere(f"{cid}_hair", (0, r * 0.1, hc + r * 0.2), (r * 1.0, r * 1.0, r * 0.98), hairm, head, subsurf=1, unique=True)
        me = cap.data
        bm = bmesh.new()
        bm.from_mesh(me)
        # garder le dessus + l'arrière (front dégagé)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if (v.co.z < 0.42 and v.co.y < -0.35) or (v.co.z < 0.0 and v.co.y < 0.3) or v.co.z < -0.6],
                         context="VERTS")
        bm.to_mesh(me)
        bm.free()
        if st == "messy":
            for i in range(9):
                a = i * 2.4
                sphere(f"{cid}_tuft{i}", (math.cos(a) * r * 0.6, math.sin(a) * r * 0.5 + r * 0.1, hc + r * 0.85),
                       (r * 0.28, r * 0.28, r * 0.35), hairm, head)
        if st == "long":
            cone(f"{cid}_hairlong", (0, r * 0.45, hc - r * 0.9), r * 1.05, r * 0.9, r * 2.0, hairm, head, scale=(1, 0.6, 1))
        if st == "bun":
            sphere(f"{cid}_bun", (0, r * 0.75, hc + r * 0.55), (r * 0.42,) * 3, hairm, head)
        if st == "braids":
            for s in (-1, 1):
                for k in range(6):
                    sphere(f"{cid}_braid{s}{k}", (s * r * 0.75, r * 0.35, hc - r * 0.4 - k * r * 0.32),
                           (r * 0.17, r * 0.17, r * 0.2), hairm, head)
        b = L.get("beard")
        if b:
            bm_ = mat(f"beard_{cid}", b["color"], rough=0.6)
            if b["style"] == "long":
                cone(f"{cid}_beard", (0, -r * 0.62, hc - r * 0.95), r * 0.55, r * 0.12, r * 1.2, bm_, head, scale=(1, 0.6, 1))
            sphere(f"{cid}_beardc", (0, -r * 0.42, hc - r * 0.55), (r * 0.72, r * 0.6, r * (0.5 if b["style"] != "neat" else 0.42)), bm_, head)
            sphere(f"{cid}_mous", (0, -r * 0.93, hc - r * 0.3), (r * 0.32, r * 0.08, r * 0.07), bm_, head)

    def _paint(self, L, head, hc, r):
        cid = self.id
        pt = L.get("paint")
        if pt:
            pm = mat(f"paint_{cid}", pt["color"], rough=0.8)
            n = 2 if pt["pattern"] == "cheek_lines" else 3
            for s in (-1, 1):
                for k in range(n):
                    box(f"{cid}_paint{s}{k}", (s * r * 0.55, -r * 0.78, hc - r * 0.08 - k * r * 0.13),
                        (r * 0.28, r * 0.04, r * 0.035), pm, head, rot=(0, 0.25 * s, 0))
        if "scar_left_eye" in L["accessories"]:
            box(f"{cid}_scar", (-r * 0.36, -r * 0.93, hc + r * 0.1), (r * 0.03, r * 0.03, r * 0.42),
                mat("scar", "#5a2a20", rough=0.8), head, rot=(0, 0.3, 0))

    def _accessories(self, L, skin, tunic, leather, tw, head, hc, r, sh_h, hip_h):
        cid, H, acc = self.id, self.H, L["accessories"]
        chest, spine = self.p["chest"], self.p["spine"]
        wood = mat("wood", "#6b4a2a", rough=0.85)
        if "fur_cape" in acc or "long_coat" in acc:
            col = L.get("cape_color", "#5a3b22")
            long_ = "long_coat" in acc
            cone(f"{cid}_cape", (0, tw * 0.45, sh_h - H * (0.3 if long_ else 0.2)), tw * (1.25 if long_ else 1.15), tw * 0.85,
                 H * (0.6 if long_ else 0.42), mat(f"cape_{cid}", col, rough=1.0), chest, scale=(1, 0.55, 1), subsurf=1)
            if not long_:
                torus(f"{cid}_fur", (0, 0, sh_h + H * 0.005), tw * 0.8, H * 0.03, mat(f"fur_{cid}", "#7a5a3a", rough=1), chest,
                      scale=(1, 0.75, 1))
        hand = self.p["hand_R"]
        hp = W(hand)
        if "staff" in acc:
            cyl(f"{cid}_staff", (hp.x + H * 0.05, hp.y - H * 0.03, hp.z - H * 0.04), H * 0.018, H * 1.05, wood, hand, rot=(0, -0.08, 0))
        if "spear" in acc:
            cyl(f"{cid}_spear", (hp.x + H * 0.05, hp.y - H * 0.03, hp.z + H * 0.1), H * 0.014, H * 1.1, wood, hand, rot=(0, -0.08, 0))
            cone(f"{cid}_spearpt", (hp.x + H * 0.005, hp.y - H * 0.03, hp.z + H * 0.7), H * 0.03, 0, H * 0.1,
                 mat("flint", "#3a3a40", rough=0.35), hand)
        if "bow" in acc:
            bo = torus(f"{cid}_bow", (0, tw * 0.75, sh_h - H * 0.12), H * 0.3, H * 0.012, wood, chest, rot=(0, math.pi / 2, 0),
                       scale=(1, 1, 0.35))
            bo.rotation_euler.y += 0.5
        if "basket" in acc:
            hl = W(self.p["hand_L"])
            cone(f"{cid}_basket", (hl.x - H * 0.04, hl.y, hl.z - H * 0.05), H * 0.09, H * 0.12, H * 0.12,
                 mat("wicker", "#a8834a", rough=0.95), self.p["hand_L"])
        if "scarf" in acc:
            torus(f"{cid}_scarf", (0, 0, sh_h + H * 0.02), H * 0.055, H * 0.022, mat(f"scarf_{cid}", L.get("scarf_color", "#4f9a46")),
                  chest, scale=(1, 0.9, 1))
        if "headband" in acc:
            torus(f"{cid}_headband", (0, r * 0.05, hc + r * 0.32), r * 0.98, r * 0.08, mat(f"hb_{cid}", L.get("headband_color", "#b5832e")),
                  head, rot=(0.08, 0, 0))
        for kind, col in (("bone_necklace", "#efe8d8"), ("shell_necklace", "#4fa0d8")):
            if kind in acc:
                n = 9
                for i in range(n):
                    a = math.pi * (0.15 + 0.7 * i / (n - 1))
                    sphere(f"{cid}_bead{i}", (math.cos(a) * H * 0.07, -math.sin(a) * H * 0.05, sh_h - H * 0.01 - math.sin(a) * H * 0.03),
                           (H * 0.012, H * 0.012, H * 0.016), mat(kind, col, rough=0.4), chest)
        if "satchel" in acc:
            box(f"{cid}_satchel", (tw * 0.95, -tw * 0.1, hip_h + H * 0.02), (H * 0.05, H * 0.11, H * 0.09), leather, spine, bevel=H * 0.01)
            torus(f"{cid}_strap", (0, 0, hip_h + (sh_h - hip_h) * 0.55), tw * 0.95, H * 0.008, leather, spine, rot=(0, 0.75, 0),
                  scale=(1, 0.66, 1.4))
        if "pouch" in acc:
            sphere(f"{cid}_pouch", (tw * 0.7, -tw * 0.4, hip_h + H * 0.0), (H * 0.04, H * 0.03, H * 0.045), leather, spine)
        if "bracelets" in acc:
            for side in ("L", "R"):
                el = self.p[f"elbow_{side}"]
                hp2 = W(self.p[f"hand_{side}"])
                torus(f"{cid}_brac{side}", (hp2.x, hp2.y, hp2.z + H * 0.04), H * 0.03, H * 0.006, mat("bone", "#e6dcc4", rough=0.5), el)

    # ------------------------------------------------------------------ placement
    def place(self, x, y, yaw):
        self.root.location = (x, y, 0)
        self.root.rotation_euler = (0, 0, yaw)
