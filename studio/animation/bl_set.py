"""Décors procéduraux à graine fixe (memory/geography.json > sets3d).

Même lieu => même décor à chaque épisode. Les éléments vivants (vent, eau, feu, fumée, pluie, lucioles,
feuilles) sont animés par des fonctions pures de l'image : voir Set.animate(f).
"""
import math
import random

import bmesh
import bpy

from bl_util import box, cone, cyl, hex_rgb, ico, mat, noise1, sphere


def _fbm(x, y, seed):
    v, a, fr = 0.0, 1.0, 0.035
    for o in range(4):
        v += a * (math.sin(x * fr * 1.7 + seed * 1.3 + o) * math.cos(y * fr * 1.3 - seed * 0.7 + o * 2.1))
        a *= 0.5
        fr *= 2.1
    return v


class Set:
    def __init__(self, loc_id, spec, tod, weather="clear", night_lights=True):
        self.id = loc_id
        self.S = spec
        self.tod = tod
        self.weather = weather
        self.rng = random.Random(spec["seed"])
        self.anim = []  # fonctions f -> None
        self.lights = []
        self.obstacles = []  # (x, y, rayon, hauteur) pour que la caméra ne traverse rien
        self._sky()
        self._terrain()
        if spec.get("cave"):
            self._cave()
        if spec.get("water"):
            self._water(spec["water"])
        self._trees()
        self._grass()
        self._rocks()
        for st in spec.get("structures", []):
            getattr(self, "_s_" + st["type"])(st)
        for lm in spec.get("landmarks", []):
            getattr(self, "_l_" + lm["type"])(lm)
        if spec.get("lava"):
            self._lava()
        if spec.get("waterfall"):
            self._waterfall(spec["waterfall"])
        if spec.get("mushrooms"):
            self._mushrooms(spec["mushrooms"])
        if spec.get("reeds"):
            self._reeds(spec["reeds"])
        if spec.get("ferns"):
            self._ferns(spec["ferns"])
        if spec.get("smoke_plumes"):
            for i in range(spec["smoke_plumes"]):
                self.smoke((self.rng.uniform(-25, 25), self.rng.uniform(15, 40), 0), n=10, scale=3.0, rise=1.6, seed=i)
        if weather == "rain":
            self.rain()
        if tod["name"] == "night" and not spec.get("cave"):
            self.fireflies(30)
        if spec.get("trees", {}).get("kind") == "violet":
            self.leaves(40)
        if spec.get("light_shafts"):
            self._shafts()

    # ------------------------------------------------------------------ relief
    def height(self, x, y):
        r = math.hypot(x, y)
        flat = min(1.0, max(0.0, (r - 7) / 12))  # zone de jeu plate au centre
        return self.S["relief"] * (1.2 * _fbm(x, y, self.S["seed"]) + 0.6) * flat * (1 + r / 40)

    def _terrain(self):
        n, size = 90, 140.0
        me = bpy.data.meshes.new("terrain")
        bm = bmesh.new()
        vs = []
        for j in range(n + 1):
            row = []
            for i in range(n + 1):
                # grille plus dense au centre
                u, v = (i / n - 0.5) * 2, (j / n - 0.5) * 2
                x = math.copysign(abs(u) ** 1.6, u) * size / 2
                y = math.copysign(abs(v) ** 1.6, v) * size / 2
                row.append(bm.verts.new((x, y, self.height(x, y))))
            vs.append(row)
        for j in range(n):
            for i in range(n):
                bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new("terrain", me)
        bpy.context.scene.collection.objects.link(o)
        for p in me.polygons:
            p.use_smooth = True
        m = bpy.data.materials.new("ground")
        m.use_nodes = True
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        b.inputs["Roughness"].default_value = 0.95
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 0.18
        noise.inputs["Detail"].default_value = 6
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = hex_rgb(self.S["ground"])
        ramp.color_ramp.elements[1].color = hex_rgb(self.S["ground2"])
        ramp.color_ramp.elements[0].position = 0.4
        ramp.color_ramp.elements[1].position = 0.65
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        n2 = nt.nodes.new("ShaderNodeTexNoise")
        n2.inputs["Scale"].default_value = 6
        bump.inputs["Strength"].default_value = 0.25
        nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
        if self.S.get("snow"):
            # neige sur les pentes hautes
            geo = nt.nodes.new("ShaderNodeNewGeometry")
            sep = nt.nodes.new("ShaderNodeSeparateXYZ")
            mr = nt.nodes.new("ShaderNodeMapRange")
            mr.inputs["From Min"].default_value = 1.0
            mr.inputs["From Max"].default_value = 3.0
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.inputs[7].default_value = hex_rgb("#f2f6fa")
            nt.links.new(geo.outputs["Position"], sep.inputs[0])
            nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
            nt.links.new(mr.outputs["Result"], mix.inputs["Factor"])
            nt.links.new(ramp.outputs["Color"], mix.inputs[6])
            nt.links.new(mix.outputs[2], b.inputs["Base Color"])
        o.data.materials.append(m)

    # ------------------------------------------------------------------ ciel, soleil, brume
    def _sky(self):
        T = self.tod
        sc = bpy.context.scene
        w = bpy.data.worlds.new("sky")
        sc.world = w
        w.use_nodes = True
        nt = w.node_tree
        bg = nt.nodes["Background"]
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.0
        ramp.color_ramp.elements[0].color = hex_rgb(T["sky_horizon"])
        ramp.color_ramp.elements[1].position = 0.45
        ramp.color_ramp.elements[1].color = hex_rgb(T["sky_top"])
        nt.links.new(tc.outputs["Generated"], sep.inputs[0])
        nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
        amb = T["ambient"] * (0.25 if self.S.get("cave") else 1.0) * (0.6 if self.weather == "rain" else 1.0)
        bg.inputs["Strength"].default_value = 0.6 + amb
        fog = self.S.get("fog", 0.01) * (2.2 if self.weather in ("rain", "fog") else 1.0)
        if fog > 0:
            vol = nt.nodes.new("ShaderNodeVolumePrincipled")
            vol.inputs["Color"].default_value = hex_rgb(T["fog_color"])
            vol.inputs["Density"].default_value = fog
            vol.inputs["Anisotropy"].default_value = 0.6
            nt.links.new(vol.outputs[0], nt.nodes["World Output"].inputs["Volume"])
        el = math.radians(T["sun_elev"])
        az = math.radians(T["sun_az"])
        bpy.ops.object.light_add(type="SUN", rotation=(math.pi / 2 - el, 0, az + math.pi))
        sun = bpy.context.object
        sun.data.energy = T["sun_strength"] * (0.35 if self.weather == "rain" else 1.0) * (0.15 if self.S.get("cave") else 1.0)
        sun.data.color = hex_rgb(T["sun_color"])[:3]
        sun.data.angle = math.radians(3)
        self.sun = sun
        if T["name"] == "night":
            # lune : douce lumière froide + étoiles (points émissifs lointains)
            starm = mat("star", "#ffffff", emission="#ffffff", strength=6)
            r = random.Random(7)
            for i in range(140):
                a, e = r.uniform(0, 2 * math.pi), r.uniform(0.25, 1.4)
                d = 400
                sphere(f"star{i}", (math.cos(a) * math.cos(e) * d, math.sin(a) * math.cos(e) * d, math.sin(e) * d),
                       (r.uniform(0.4, 1.0),) * 3, starm, seg=6, ring=4)

    # ------------------------------------------------------------------ végétation
    def _tree(self, x, y, kind, color, k):
        r = self.rng
        z = self.height(x, y)
        h = r.uniform(4.5, 7.5) * (1.4 if kind == "pine" else 1.0)
        bark = mat("bark_" + kind, "#4a3423" if kind != "violet" else "#3a2a3a", rough=0.9)
        trunk = cone(f"trunk{k}", (x, y, z + h * 0.3), 0.32, 0.18, h * 0.6, bark, verts=10)
        leaf_cols = [color]
        if kind == "violet":
            leaf_cols = [color, "#9b55c4", "#5e2e86", "#b070d8"]
        elif kind == "broadleaf":
            leaf_cols = [color, "#4f7d36", "#35602a", "#5a8a3c"]
        parts = []
        if kind == "pine":
            for i in range(4):
                parts.append(cone(f"pine{k}_{i}", (x, y, z + h * (0.35 + i * 0.17)), h * (0.32 - i * 0.06), 0.02, h * 0.32,
                                  mat("pine", color, rough=0.85), verts=10))
        elif kind == "dead":
            for i in range(3):
                parts.append(cyl(f"br{k}_{i}", (x + 0.4 * (i - 1), y, z + h * (0.5 + 0.1 * i)), 0.06, h * 0.35, bark,
                                 rot=(0, 0.7 * (i - 1) + 0.2, r.uniform(0, 3)), verts=6))
        else:
            for i in range(r.randint(3, 5)):
                c = r.choice(leaf_cols)
                rr = r.uniform(1.2, 2.0) * h / 6
                o = ico(f"leaf{k}_{i}", (x + r.uniform(-1, 1), y + r.uniform(-1, 1), z + h * r.uniform(0.62, 0.95)), rr,
                        mat("leaf_" + c, c, rough=0.8, sss=0.15), scale=(1, 1, r.uniform(0.75, 0.95)))
                parts.append(o)
        for o in parts:
            o.parent = trunk
            o.location = (o.location.x - x, o.location.y - y, o.location.z - (z + h * 0.3))
        # vent : balancement doux depuis le pied (pivot déplacé à la base)
        base = bpy.data.objects.new(f"treeb{k}", None)
        bpy.context.scene.collection.objects.link(base)
        base.location = (x, y, z)
        trunk.parent = base
        trunk.location = (0, 0, h * 0.3)
        ph = r.uniform(0, 6.28)
        amp = 0.018 + 0.012 * r.random()

        def sway(f, base=base, ph=ph, amp=amp):
            t = f / 30
            wind = 1.8 if self.weather == "rain" else 1.0
            base.rotation_euler = (amp * wind * noise1(t * 0.9 + ph, 1), amp * wind * noise1(t * 0.8 + ph, 2), 0)
        self.anim.append(sway)

    def _trees(self):
        T = self.S["trees"]
        r = self.rng
        k = 0
        tries = 0
        while k < T["count"] and tries < T["count"] * 20:
            tries += 1
            a = r.uniform(0, 2 * math.pi)
            d = r.uniform(*T["ring"])
            x, y = math.cos(a) * d, math.sin(a) * d
            if self._blocked(x, y, 2.5):
                continue
            self._tree(x, y, T["kind"], T["color"], k)
            self.obstacles.append((x, y, 2.6, 9.0))
            k += 1

    def _blocked(self, x, y, m):
        # couloir caméra : secteur sud du centre gardé dégagé (plans larges et d'établissement)
        cx, cy = self.S["marks"]["center"]
        dx, dy = x - cx, y - cy
        ang = math.degrees(math.atan2(dy, dx))
        if -155 < ang < -25 and math.hypot(dx, dy) < 26 and m > 0.4:
            return True
        w = self.S.get("water")
        if w and w["type"] in ("river", "stream") and abs(x - w["x"]) < w["width"] / 2 + m:
            return True
        if w and w["type"] == "lake" and math.dist((x, y), w["center"]) < w["radius"] + m:
            return True
        for st in self.S.get("structures", []):
            if math.dist((x, y), st["pos"]) < 3.5 + m:
                return True
        for mk in self.S.get("marks", {}).values():
            if math.dist((x, y), mk) < 1.6 + m * 0.4:
                return True
        return False

    def _grass(self):
        G = self.S["grass"]
        if not G["count"]:
            return
        r = self.rng
        gm = mat("grass", G["color"], rough=0.8, sss=0.1)
        gm2 = mat("grass2", "#8aa64a" if not G.get("tall") else "#c8b85a", rough=0.8, sss=0.1)
        protos = []
        for v in range(3):
            me = bpy.data.meshes.new(f"tuft{v}")
            bm = bmesh.new()
            for b in range(7):
                a = b / 7 * 6.28 + v
                hh = (0.45 if not G.get("tall") else 1.0) * (0.7 + 0.3 * math.sin(b * 3.1 + v))
                lean = 0.12
                p0 = bm.verts.new((math.cos(a) * 0.03 - 0.025, math.sin(a) * 0.03, 0))
                p1 = bm.verts.new((math.cos(a) * 0.03 + 0.025, math.sin(a) * 0.03, 0))
                p2 = bm.verts.new((math.cos(a) * lean, math.sin(a) * lean, hh))
                bm.faces.new((p0, p1, p2))
            bm.to_mesh(me)
            bm.free()
            me.materials.append(gm if v != 1 else gm2)
            protos.append(me)
        for i in range(G["count"]):
            a = r.uniform(0, 6.28)
            d = 2.0 + 30 * r.random() ** 1.4
            x, y = math.cos(a) * d, math.sin(a) * d
            if self._blocked(x, y, 0.2):
                continue
            o = bpy.data.objects.new(f"g{i}", protos[i % 3])
            bpy.context.scene.collection.objects.link(o)
            s = r.uniform(0.7, 1.5)
            o.location = (x, y, self.height(x, y) - 0.02)
            o.scale = (s, s, s * r.uniform(0.8, 1.3))
            o.rotation_euler.z = r.uniform(0, 6.28)
            ph = x * 0.25 + y * 0.1

            def sway(f, o=o, ph=ph):
                t = f / 30
                o.rotation_euler.x = 0.09 * noise1(t * 1.6 + ph, 3)
                o.rotation_euler.y = 0.07 * noise1(t * 1.3 + ph, 4)
            self.anim.append(sway)

    def _rocks(self):
        r = self.rng
        rm = mat("rock", "#7a7670", rough=0.9)
        rm2 = mat("rock2", "#5d5a55", rough=0.9)
        for i in range(self.S["rocks"]):
            a = r.uniform(0, 6.28)
            d = r.uniform(4, 35)
            x, y = math.cos(a) * d, math.sin(a) * d
            if self._blocked(x, y, 0.5):
                continue
            s = r.uniform(0.2, 1.1)
            ico(f"rock{i}", (x, y, self.height(x, y) + s * 0.2), s, rm if i % 2 else rm2, sub=1,
                scale=(1, r.uniform(0.6, 1), r.uniform(0.4, 0.8)), rot=(r.uniform(0, 1), r.uniform(0, 1), r.uniform(0, 6)))

    # ------------------------------------------------------------------ eau
    def _water(self, W):
        wm = bpy.data.materials.new("water")
        wm.use_nodes = True
        nt = wm.node_tree
        b = nt.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = hex_rgb("#2c6f8f")
        b.inputs["Roughness"].default_value = 0.08
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 2.5
        mapping = nt.nodes.new("ShaderNodeMapping")
        tc = nt.nodes.new("ShaderNodeTexCoord")
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.15
        nt.links.new(tc.outputs["Object"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
        if W["type"] in ("river", "stream"):
            bpy.ops.mesh.primitive_plane_add(size=1, location=(W["x"], 0, 0.06))
            o = bpy.context.object
            o.scale = (W["width"], 160, 1)
            # lit creusé : on abaisse le terrain sous la rivière
            ter = bpy.data.objects["terrain"]
            for v in ter.data.vertices:
                dx = abs(v.co.x - W["x"])
                if dx < W["width"] / 2 + 1.5:
                    v.co.z = min(v.co.z, -0.25 + 0.2 * max(0, dx - W["width"] / 2))
            flow = 0.9
        else:
            bpy.ops.mesh.primitive_circle_add(vertices=64, radius=W["radius"], fill_type="NGON",
                                              location=(W["center"][0], W["center"][1], 0.05))
            o = bpy.context.object
            ter = bpy.data.objects["terrain"]
            for v in ter.data.vertices:
                d = math.dist((v.co.x, v.co.y), W["center"])
                if d < W["radius"] + 1.5:
                    v.co.z = min(v.co.z, -0.3 + 0.25 * max(0, d - W["radius"]))
            flow = 0.15
        o.name = "water"
        o.data.materials.append(wm)

        def ripple(f, mapping=mapping, flow=flow):
            mapping.inputs["Location"].default_value = (0, -f / 30 * flow, f / 30 * 0.2)
        self.anim.append(ripple)

    # ------------------------------------------------------------------ structures
    def _s_shelter(self, st):
        x, y = st["pos"]
        z = self.height(x, y)
        wood = mat("branch", "#6a4c2e", rough=0.95)
        thatch = mat("thatch", "#8a7240", rough=1.0)
        self.obstacles.append((x, y, 2.3, 2.6))
        o = cone("shelter", (x, y, z + 1.1), 1.9, 0.08, 2.3, thatch, verts=14, scale=(1, 0.85, 1))
        o.rotation_euler.z = math.radians(st.get("rot", 0))
        for i in range(10):
            a = i / 10 * 6.28
            cyl(f"pole{i}", (x + math.cos(a) * 1.0, y + math.sin(a) * 0.85, z + 1.25), 0.05, 2.9, wood,
                rot=(math.sin(a) * 0.62, -math.cos(a) * 0.62, 0), verts=6)
        # entrée sombre
        box("door", (x + 0.0, y - 1.2, z + 0.55), (0.9, 0.3, 1.0), mat("dark", "#1a120c"), rot=(0.35, 0, 0))

    def _s_logs(self, st):
        x, y = st["pos"]
        wood = mat("log", "#5a3e26", rough=0.9)
        for i, a in enumerate((0.6, 2.4, 4.2)):
            cyl(f"seat{i}", (x + math.cos(a) * 2.0, y + math.sin(a) * 2.0, 0.22), 0.22, 1.5, wood,
                rot=(0, math.pi / 2, a + math.pi / 2), verts=12)

    def _s_campfire(self, st):
        x, y = st["pos"]
        stone = mat("stone", "#6d6a66", rough=0.9)
        for i in range(10):
            a = i / 10 * 6.28
            sphere(f"fst{i}", (x + math.cos(a) * 0.55, y + math.sin(a) * 0.55, 0.06), (0.15, 0.13, 0.1), stone, seg=8, ring=6)
        wood = mat("firewood", "#3a2414", rough=0.9)
        for i in range(4):
            cyl(f"fw{i}", (x, y, 0.15), 0.05, 0.8, wood, rot=(1.1, 0, i * 0.8), verts=6)
        self.fire((x, y, 0.1))

    def _s_ruins(self, st):
        x, y = st["pos"]
        z = self.height(x, y)
        stone = mat("ruinstone", "#8a8476", rough=0.9)
        moss = mat("moss", "#4a6a2e", rough=1.0)
        r = random.Random(11)
        for i in range(7):
            w = r.uniform(1.5, 3.5)
            h = r.uniform(1.2, 4.0)
            a = i / 7 * 3.14 + 3.3
            box(f"wall{i}", (x + math.cos(a) * 6, y + math.sin(a) * 4 + 4, z + h / 2), (w, 0.6, h), stone,
                rot=(0, r.uniform(-0.05, 0.05), a + 1.57), bevel=0.05)
        for i in range(5):
            h = r.uniform(1.5, 4.5)
            cyl(f"col{i}", (x - 4 + i * 2, y, z + h / 2), 0.35, h, stone, verts=14)
            sphere(f"vine{i}", (x - 4 + i * 2, y - 0.3, z + h * 0.6), (0.4, 0.2, h * 0.3), moss, seg=8, ring=6)
        for i in range(4):
            box(f"step{i}", (x, y - 3 - i * 0.6, z + 0.2 - i * 0.12), (4, 0.6, 0.25), stone, bevel=0.03)

    # ------------------------------------------------------------------ repères lointains
    def _l_mountain(self, lm):
        x, y = lm["pos"]
        h = lm["h"]
        r = random.Random(int(x * 7 + y))
        rock = mat("mtn", "#6e6a72", rough=0.95)
        snow = mat("snow", "#f2f5f8", rough=0.6)
        for i in range(3):
            dx = (i - 1) * h * 0.9
            hh = h * (1.0 if i == 1 else r.uniform(0.55, 0.75))
            bpy.ops.mesh.primitive_cone_add(vertices=18, radius1=hh * 0.9, depth=hh, location=(x + dx, y + abs(dx) * 0.3, hh / 2 - 2))
            o = bpy.context.object
            o.data.materials.append(rock)
            if lm.get("snow"):
                cone(f"snowcap{i}", (x + dx, y + abs(dx) * 0.3, hh * 0.86 - 2), hh * 0.27, 0, hh * 0.3, snow, verts=18)

    def _l_volcano(self, lm):
        x, y = lm["pos"]
        h = lm["h"]
        cone("volcano", (x, y, h / 2 - 2), h * 1.1, h * 0.18, h, mat("basalt", "#2e2a2a", rough=0.95), verts=24)
        cone("crater", (x, y, h - 1.5), h * 0.17, h * 0.1, 1.2, mat("lava", "#ff5a1a", emission="#ff4a10", strength=6))
        self.smoke((x, y, h - 1), n=14, scale=h * 0.12, rise=h * 0.03, seed=99, dark=True)

    def _l_ruins_far(self, lm):
        x, y = lm["pos"]
        h = lm["h"]
        cone("hill", (x, y, h / 2 - 1), h * 3, h * 1.5, h, mat("hill", "#5f6a48", rough=1), verts=16)
        st = mat("ruinstone", "#8a8476", rough=0.9)
        for i in range(5):
            box(f"farwall{i}", (x - 6 + i * 3, y, h + 1.2 + (i % 2)), (2, 1, 2.5 + (i % 3)), st)

    def _l_violet_forest_far(self, lm):
        x, y = lm["pos"]
        r = random.Random(5)
        for i in range(40):
            c = r.choice(["#7b3fa0", "#9b55c4", "#5e2e86"])
            px, py = x + r.uniform(-25, 25), y + r.uniform(-20, 20)
            sphere(f"vf{i}", (px, py, 5 + r.uniform(0, 3)), (4, 4, 3.5), mat("leaf_" + c, c, rough=0.8), seg=10, ring=8)

    # ------------------------------------------------------------------ lieux spéciaux
    def _cave(self):
        rock = mat("caverock", "#4a4440", rough=0.95)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1, location=(0, 4, 0))
        o = bpy.context.object
        o.scale = (14, 16, 7)
        o.data.materials.append(rock)
        for p in o.data.polygons:
            p.use_smooth = True
        d = o.modifiers.new("disp", "DISPLACE")
        tex = bpy.data.textures.new("cavetex", "CLOUDS")
        tex.noise_scale = 0.4
        d.texture = tex
        d.strength = 0.18
        # ouverture vers la caméra
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y < -0.8 and v.co.z > -0.3], context="VERTS")
        bm.to_mesh(o.data)
        bm.free()

    def _mushrooms(self, n):
        r = self.rng
        glow = mat("glowcap", "#4ad6c0", emission="#3fe0c8", strength=3.5)
        stem = mat("stem", "#d8d0c0", rough=0.7)
        for i in range(n):
            x, y = r.uniform(-10, 10), r.uniform(-2, 14)
            if self._blocked(x, y, 0.2):
                continue
            s = r.uniform(0.06, 0.18)
            cyl(f"ms{i}", (x, y, s), s * 0.25, s * 2, stem, verts=6)
            sphere(f"mc{i}", (x, y, s * 2), (s, s, s * 0.5), glow, seg=10, ring=6)
        bpy.ops.object.light_add(type="POINT", location=(0, 5, 1.5))
        L = bpy.context.object
        L.data.energy = 400
        L.data.color = (0.3, 0.9, 0.8)

    def _reeds(self, n):
        r = self.rng
        rm = mat("reed", "#7a8a3a", rough=0.8)
        W = self.S["water"]
        for i in range(n):
            a = r.uniform(3.4, 6.0)
            d = W["radius"] + r.uniform(-0.8, 0.6)
            x, y = W["center"][0] + math.cos(a) * d, W["center"][1] + math.sin(a) * d
            o = cyl(f"reed{i}", (x, y, 0.6), 0.02, 1.3, rm, verts=5)
            ph = r.uniform(0, 6)

            def sway(f, o=o, ph=ph):
                o.rotation_euler.x = 0.08 * noise1(f / 30 * 1.5 + ph, 6)
            self.anim.append(sway)

    def _ferns(self, n):
        r = self.rng
        fm = mat("fern", "#3f6a30", rough=0.8, sss=0.1)
        for i in range(n):
            a = r.uniform(0, 6.28)
            d = r.uniform(2.5, 14)
            x, y = math.cos(a) * d, math.sin(a) * d
            if self._blocked(x, y, 0.3):
                continue
            for k in range(5):
                cone(f"fern{i}_{k}", (x, y, 0.25), 0.12, 0.0, 0.9, fm, rot=(0.9, 0, k * 1.26 + i), verts=4, scale=(1, 0.25, 1))

    def _lava(self):
        lv = mat("lavaflow", "#ff6a1a", emission="#ff3a00", strength=4)
        r = self.rng
        for i in range(6):
            bpy.ops.mesh.primitive_plane_add(size=1, location=(r.uniform(-15, 15), r.uniform(8, 30), 0.15))
            o = bpy.context.object
            o.scale = (r.uniform(0.6, 1.4), r.uniform(6, 14), 1)
            o.rotation_euler.z = r.uniform(-0.5, 0.5)
            o.data.materials.append(lv)
        bpy.ops.object.light_add(type="AREA", location=(0, 18, 2))
        L = bpy.context.object
        L.data.energy = 2500
        L.data.size = 20
        L.data.color = (1, 0.4, 0.15)
        L.rotation_euler = (math.pi, 0, 0)

    def _waterfall(self, wf):
        x, y = wf["pos"]
        h = wf["h"]
        box("cliff", (x, y + 1.5, h / 2), (8, 3, h), mat("cliff", "#6a6670", rough=0.95))
        fm = bpy.data.materials.new("fall")
        fm.use_nodes = True
        nt = fm.node_tree
        b = nt.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.85, 0.92, 1, 1)
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 3
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (8, 1, 0.6)
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nt.links.new(tc.outputs["Object"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        nt.links.new(noise.outputs["Fac"], b.inputs["Alpha"])
        fm.blend_method = "BLEND"
        bpy.ops.mesh.primitive_plane_add(size=1, location=(x, y - 0.05, h / 2), rotation=(math.pi / 2, 0, 0))
        o = bpy.context.object
        o.scale = (2.4, h, 1)
        o.data.materials.append(fm)

        def flow(f, mapping=mapping):
            mapping.inputs["Location"].default_value = (0, 0, f / 30 * 2.2)
        self.anim.append(flow)
        self.smoke((x, y - 1, 0.5), n=12, scale=1.5, rise=0.3, seed=55, color="#e8f0f8")

    def _shafts(self):
        bpy.ops.object.light_add(type="SPOT", location=(3, 6, 14), rotation=(0.35, 0.15, 0))
        L = bpy.context.object
        L.data.energy = 4000
        L.data.spot_size = 0.5
        L.data.color = (1.0, 0.92, 0.75)

    # ------------------------------------------------------------------ effets (déterministes)
    def fire(self, p):
        x, y, z = p
        fl = [mat(f"flame{i}", c, emission=c, strength=s) for i, (c, s) in
              enumerate((("#ffb030", 18), ("#ff7a18", 14), ("#ffe070", 22)))]
        flames = []
        for i in range(5):
            a = i * 1.3
            o = cone(f"flame{i}", (x + math.cos(a) * 0.12, y + math.sin(a) * 0.12, z + 0.35), 0.16, 0.0, 0.7, fl[i % 3], verts=10)
            o.visible_shadow = False
            flames.append(o)
        bpy.ops.object.light_add(type="POINT", location=(x, y, z + 0.7))
        L = bpy.context.object
        L.data.energy = 220 if self.tod["name"] in ("night", "dusk") else 90
        L.data.color = (1.0, 0.55, 0.2)
        L.data.shadow_soft_size = 0.3
        base = L.data.energy

        def flicker(f):
            t = f / 30
            for i, o in enumerate(flames):
                s = 0.75 + 0.35 * (0.5 + 0.5 * noise1(t * 7 + i * 1.7, 20 + i))
                o.scale = (1 + 0.15 * noise1(t * 9 + i, 30 + i), 1, s)
                o.rotation_euler = (0.1 * noise1(t * 5 + i, 40), 0.1 * noise1(t * 6 + i, 41), 0)
            L.data.energy = base * (0.8 + 0.3 * (0.5 + 0.5 * noise1(t * 11, 50)))
        self.anim.append(flicker)
        self.smoke((x, y, z + 1.0), n=10, scale=0.5, rise=0.55, seed=3)
        self.embers((x, y, z + 0.5))

    def embers(self, p, n=16):
        em = mat("ember", "#ffa040", emission="#ff8020", strength=25)
        objs = [sphere(f"ember{i}", p, (0.015,) * 3, em, seg=6, ring=4) for i in range(n)]

        def anim(f):
            for i, o in enumerate(objs):
                life = 50 + (i * 13) % 30
                u = ((f + i * 17) % life) / life
                o.location = (p[0] + 0.3 * noise1(u * 4 + i, 60 + i), p[1] + 0.3 * noise1(u * 3 + i, 70 + i), p[2] + u * 2.2)
                s = 0.015 * (1 - u)
                o.scale = (s, s, s)
        self.anim.append(anim)

    def smoke(self, p, n=10, scale=0.5, rise=0.5, seed=0, dark=False, color=None):
        sm = mat(f"smoke{seed}", color or ("#3a3633" if dark else "#9a948c"), rough=1.0, alpha=0.22)
        puffs = [sphere(f"puff{seed}_{i}", p, (scale,) * 3, sm, seg=12, ring=8) for i in range(n)]
        for o in puffs:
            o.visible_shadow = False

        def anim(f):
            for i, o in enumerate(puffs):
                life = 110
                u = ((f + i * life / n) % life) / life
                drift = u * 3.0 * scale
                o.location = (p[0] + drift + 0.3 * scale * noise1(u * 3 + i, seed + i), p[1] + 0.2 * scale * noise1(u * 2 + i, seed + 2 * i),
                              p[2] + u * rise * 8)
                s = scale * (0.4 + 1.6 * u) * (1 - smooth_out(u))
                o.scale = (s, s, s)
        self.anim.append(anim)

    def rain(self, n=420):
        rm = mat("rain", "#cfdcea", rough=0.1, alpha=0.35)
        r = random.Random(77)
        drops = []
        for i in range(n):
            o = cyl(f"drop{i}", (0, 0, 0), 0.006, 0.45, rm, verts=4)
            o.visible_shadow = False
            drops.append((o, r.uniform(-9, 9), r.uniform(-12, 6), r.uniform(0, 1)))

        def anim(f):
            for o, x, y, off in drops:
                u = (f / 30 * 1.6 + off) % 1.0
                o.location = (x + u * 0.6, y, 9 * (1 - u))
        self.anim.append(anim)

    def fireflies(self, n):
        fm = mat("firefly", "#d8ff70", emission="#c8ff50", strength=40)
        objs = [sphere(f"ff{i}", (0, 0, 0), (0.025,) * 3, fm, seg=6, ring=4) for i in range(n)]
        r = random.Random(9)
        base = [(r.uniform(-10, 10), r.uniform(-4, 14), r.uniform(0.5, 2.5)) for _ in range(n)]

        def anim(f):
            t = f / 30
            for i, o in enumerate(objs):
                bx, by, bz = base[i]
                o.location = (bx + 0.8 * noise1(t * 0.4 + i, i), by + 0.8 * noise1(t * 0.35 + i, i + 50), bz + 0.4 * noise1(t * 0.5 + i, i + 90))
                k = 0.5 + 0.5 * math.sin(t * 2.5 + i * 1.7)
                o.scale = (0.025 * (0.3 + k),) * 3
        self.anim.append(anim)

    def leaves(self, n):
        lm = mat("fallleaf", "#9b55c4", rough=0.7, sss=0.2)
        objs = [box(f"fl{i}", (0, 0, 0), (0.08, 0.05, 0.005), lm) for i in range(n)]
        r = random.Random(12)
        base = [(r.uniform(-8, 8), r.uniform(-4, 10), r.uniform(0, 1)) for _ in range(n)]

        def anim(f):
            t = f / 30
            for i, o in enumerate(objs):
                bx, by, off = base[i]
                u = (t * 0.08 + off) % 1.0
                o.location = (bx + 1.2 * math.sin(u * 9 + i), by + 0.5 * noise1(u * 5, i), 7 * (1 - u))
                o.rotation_euler = (u * 12 + i, u * 7, u * 5)
        self.anim.append(anim)

    def animate(self, f):
        for a in self.anim:
            a(f)


def smooth_out(u):
    return max(0.0, (u - 0.7) / 0.3) ** 2
