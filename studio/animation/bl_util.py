"""Outils Blender communs (exécutés dans le Python de Blender)."""
import math

import bmesh
import bpy
from mathutils import Vector


def hex_rgb(h, a=1.0):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return (*lin, a)


_MATS = {}


def mat(name, color, rough=0.75, emission=None, strength=0.0, metallic=0.0, sss=0.0, alpha=1.0, spec=0.3):
    """Matériau Principled mis en cache (même nom = même matériau)."""
    key = (name, color if isinstance(color, str) else tuple(color), emission, round(strength, 3), alpha)
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    col = hex_rgb(color) if isinstance(color, str) else color
    b.inputs["Base Color"].default_value = col
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    for k in ("Specular IOR Level", "Specular"):
        if k in b.inputs:
            b.inputs[k].default_value = spec
            break
    if sss:
        for k in ("Subsurface Weight", "Subsurface"):
            if k in b.inputs:
                b.inputs[k].default_value = sss
                break
    if emission:
        for k in ("Emission Color", "Emission"):
            if k in b.inputs:
                b.inputs[k].default_value = hex_rgb(emission) if isinstance(emission, str) else emission
                break
        b.inputs["Emission Strength"].default_value = strength
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
        m.shadow_method = "NONE"
    _MATS[key] = m
    return m


def W(o):
    """Position monde au moment de la construction (pivots non tournés)."""
    return Vector(o["wpos"]) if "wpos" in o else o.location.copy()


def empty(name, loc=(0, 0, 0), parent=None):
    """Pivot animable. `loc` est en coordonnées monde (construction en pose neutre)."""
    o = bpy.data.objects.new(name, None)
    o.empty_display_size = 0.05
    bpy.context.scene.collection.objects.link(o)
    o["wpos"] = list(loc)
    o.location = Vector(loc) - (W(parent) if parent else Vector())
    if parent:
        o.parent = parent
    return o


_UNIT = {}


def _link(name, me, loc, rot, scale):
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    o.scale = scale
    return o


def _mesh_from(fn, key=None):
    """Crée (ou réutilise) un maillage unitaire construit par bmesh (bien plus rapide que bpy.ops)."""
    if key and key in _UNIT:
        return _UNIT[key]
    me = bpy.data.meshes.new(key or "m")
    bm = bmesh.new()
    fn(bm)
    bm.to_mesh(me)
    bm.free()
    if key:
        _UNIT[key] = me
    return me


def _finish(o, name, material, parent, smooth=True, subsurf=0, shared=False):
    o.name = name
    if material:
        if shared:
            if not len(o.data.materials):
                o.data.materials.append(None)
            o.material_slots[0].link = "OBJECT"
            o.material_slots[0].material = material
        else:
            o.data.materials.append(material)
    if smooth and not shared:
        for p in o.data.polygons:
            p.use_smooth = True
    if subsurf:
        m = o.modifiers.new("sub", "SUBSURF")
        m.levels = subsurf
        m.render_levels = subsurf
    o["wpos"] = list(o.location)
    if parent:
        o.location = o.location - W(parent)
        o.parent = parent
    return o


def _smooth_once(me):
    if not me.get("smooth"):
        for p in me.polygons:
            p.use_smooth = True
        me["smooth"] = 1


def sphere(name, loc, scale, material, parent=None, seg=24, ring=16, subsurf=0, unique=False):
    me = _mesh_from(lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1), f"sph{seg}_{ring}")
    _smooth_once(me)
    if unique:
        me = me.copy()  # maillage qui sera découpé (cheveux, paupières)
        me.materials.clear()
    o = _link(name, me, loc, (0, 0, 0), scale)
    return _finish(o, name, material, parent, smooth=False, subsurf=subsurf, shared=not unique)


def ico(name, loc, radius, material, sub=2, scale=(1, 1, 1), rot=(0, 0, 0)):
    me = _mesh_from(lambda bm: bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1), f"ico{sub}")
    o = _link(name, me, loc, rot, tuple(radius * s for s in scale))
    return _finish(o, name, material, None, smooth=False, shared=True)


def cone(name, loc, r1, r2, depth, material, parent=None, rot=(0, 0, 0), verts=24, scale=(1, 1, 1), subsurf=0):
    def build(bm):
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r1, radius2=r2, depth=depth)
    me = _mesh_from(build)
    o = _link(name, me, loc, rot, scale)
    return _finish(o, name, material, parent, subsurf=subsurf)


def cyl(name, loc, r, depth, material, parent=None, rot=(0, 0, 0), verts=20, scale=(1, 1, 1)):
    key = f"cyl{verts}"
    me = _mesh_from(lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts,
                                                     radius1=1, radius2=1, depth=1), key)
    _smooth_once(me)
    o = _link(name, me, loc, rot, (r * scale[0], r * scale[1], depth * scale[2]))
    return _finish(o, name, material, parent, smooth=False, shared=True)


def box(name, loc, size, material, parent=None, rot=(0, 0, 0), bevel=0.0):
    me = _mesh_from(lambda bm: bmesh.ops.create_cube(bm, size=1), "cube")
    o = _link(name, me, loc, rot, size)
    _finish(o, name, material, parent, smooth=False, shared=True)
    if bevel:
        m = o.modifiers.new("bev", "BEVEL")
        m.width = bevel
        m.segments = 2
    return o


def torus(name, loc, R, r, material, parent=None, rot=(0, 0, 0), scale=(1, 1, 1)):
    key = f"tor{round(r / R, 3)}"

    def build(bm):
        n, m = 32, 10
        rr = r / R
        grid = []
        for i in range(n):
            a = 2 * math.pi * i / n
            row = []
            for j in range(m):
                b = 2 * math.pi * j / m
                row.append(bm.verts.new(((1 + rr * math.cos(b)) * math.cos(a), (1 + rr * math.cos(b)) * math.sin(a), rr * math.sin(b))))
            grid.append(row)
        for i in range(n):
            for j in range(m):
                bm.faces.new((grid[i][j], grid[(i + 1) % n][j], grid[(i + 1) % n][(j + 1) % m], grid[i][(j + 1) % m]))
    me = _mesh_from(build, key)
    _smooth_once(me)
    o = _link(name, me, loc, rot, tuple(R * s for s in scale))
    return _finish(o, name, material, parent, smooth=False, shared=True)


def smoothstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def track(keys, f, default=0.0, blend=8):
    """Piste à états lissée, sans état interne : keys = [(frame, valeur)], transition smoothstep de `blend` images.
    Déterministe pour n'importe quelle image (rendu découpé possible)."""
    if not keys:
        return default
    prev = default
    val = default
    for fr, v in keys:
        if f < fr:
            break
        u = smoothstep((f - fr) / max(1, blend))
        if isinstance(v, (list, tuple)):
            val = [a + (b - a) * u for a, b in zip(prev, v)]
        else:
            val = prev + (v - prev) * u
        prev = v if u >= 1 else val
    return val


def noise1(x, seed=0):
    """Bruit 1D lisse et déterministe (somme de sinus incommensurables)."""
    s = seed * 1.618
    return (math.sin(x * 1.0 + s) * 0.5 + math.sin(x * 2.17 + s * 2.3) * 0.3 + math.sin(x * 4.73 + s * 0.7) * 0.2)
