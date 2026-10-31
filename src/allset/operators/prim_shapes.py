# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya primitives as data: creation nodes (attributes + defaults) and the shapes they build.

Pure Python (no bpy), in Maya's Y-up space and Maya units; ``prim_history`` turns a shape into a Blender mesh /
curve. Every rule here follows Maya (default option boxes).
No Maya code or data was copied; vertex counts, positions,
face layouts and UVs follow Maya's for the default and varied attributes
(``tests/test_step129_primitives.py`` keeps the count table).

A polygon shape = ``Mesh(verts, faces, uvs, hard, edges)``: ``uvs`` one (u, v) per face corner (or None), ``hard`` the
edges Maya marks hard (frozenset vertex pairs) or ``ALL``, ``edges`` Maya's edge ids as vertex pairs in Maya's order
(polyCube / polyCylinder) or None. A NURBS shape = list of ``Patch`` (one per Maya shape:
nurbsSquare / nurbsCube are a group of four / six).
"""

import math

ALL = "ALL"


class Mesh:
    __slots__ = ("verts", "faces", "uvs", "hard", "edges")

    def __init__(self, verts, faces, uvs=None, hard=(), edges=None):
        self.verts, self.faces, self.uvs, self.hard = verts, faces, uvs, hard
        # Maya's edge ids: (a, b) per edge in Maya's order and direction, or None (unknown for this node)
        self.edges = edges


class Patch:
    """A NURBS curve (``rows`` = 1) or surface: ``points[row][col]`` in Maya space. Blender u = along a row
    (Maya V: sections / around), Blender v = rows (Maya U: spans / profile)."""
    __slots__ = ("name", "points", "order_u", "order_v", "cyclic_u", "cyclic_v")

    def __init__(self, name, points, order_u, order_v=1, cyclic_u=False, cyclic_v=False):
        self.name, self.points = name, points
        self.order_u, self.order_v, self.cyclic_u, self.cyclic_v = order_u, order_v, cyclic_u, cyclic_v


# --- creation nodes: Maya attribute name, Channel Box label, default, kind, (min, max) ------------------
# kind: "length" (scaled by the Maya unit), "float", "int", "bool", "angle" (degrees), ("enum", labels)

def _a(name, label, default, kind, lo=None, hi=None):
    return (name, label, default, kind, lo, hi)


AXIS = [_a("axisX", "Axis X", 0.0, "float"), _a("axisY", "Axis Y", 1.0, "float"), _a("axisZ", "Axis Z", 0.0, "float")]
PIVOT = [_a("pivotX", "Pivot X", 0.0, "length"), _a("pivotY", "Pivot Y", 0.0, "length"),
         _a("pivotZ", "Pivot Z", 0.0, "length")]
NORMAL = [_a("normalX", "Normal X", 0.0, "float"), _a("normalY", "Normal Y", 1.0, "float"),
          _a("normalZ", "Normal Z", 0.0, "float")]
CENTER = [_a("centerX", "Center X", 0.0, "length"), _a("centerY", "Center Y", 0.0, "length"),
          _a("centerZ", "Center Z", 0.0, "length")]
DEGREE = ("enum", ("Linear", "Cubic"))   # Maya degree 1 / 3 (stored as 1 / 3)
# Create UVs (polyCylinder): 0 = no UVs; the kit lays out every other choice like the Create menu
# (Normalize and Preserve Aspect Ratio)
CREATE_UVS = ("None", "Normalization Off", "Normalize", "Normalize and Preserve Aspect Ratio")
SWEEPS = [_a("startSweep", "Start Sweep", 0.0, "angle", 0.0, 360.0), _a("endSweep", "End Sweep", 360.0, "angle", 0.0, 360.0)]

# Defaults = what the Create menu builds with factory option boxes; where
# that differs from the bare command (polyCylinder subdivisionsCaps 0 -> menu 1) the menu wins.
NODES = {
    "polyCube": [*AXIS, _a("width", "Width", 1.0, "length", 0.0), _a("height", "Height", 1.0, "length", 0.0),
                 _a("depth", "Depth", 1.0, "length", 0.0), _a("subdivisionsWidth", "Subdivisions Width", 1, "int", 1),
                 _a("subdivisionsHeight", "Subdivisions Height", 1, "int", 1),
                 _a("subdivisionsDepth", "Subdivisions Depth", 1, "int", 1)],
    "polySphere": [*AXIS, _a("radius", "Radius", 1.0, "length", 0.0),
                   _a("subdivisionsAxis", "Subdivisions Axis", 20, "int", 3),
                   _a("subdivisionsHeight", "Subdivisions Height", 20, "int", 2)],
    "polyCylinder": [*AXIS, _a("heightBaseline", "Height Baseline", 0.0, "float"),
                     _a("radius", "Radius", 1.0, "length", 0.0), _a("height", "Height", 2.0, "length", 0.0),
                     _a("subdivisionsAxis", "Subdivisions Axis", 20, "int", 3),
                     _a("subdivisionsHeight", "Subdivisions Height", 1, "int", 1),
                     _a("subdivisionsCaps", "Subdivisions Caps", 1, "int", 0),
                     _a("createUVs", "Create UVs", 3, ("enum", CREATE_UVS)),
                     _a("roundCap", "Round Cap", False, "bool"),
                     _a("roundCapHeightCompensation", "Round Cap Height Compensation", False, "bool")],
    "polyCone": [*AXIS, _a("radius", "Radius", 1.0, "length", 0.0), _a("height", "Height", 2.0, "length", 0.0),
                 _a("subdivisionsAxis", "Subdivisions Axis", 20, "int", 3),
                 _a("subdivisionsHeight", "Subdivisions Height", 1, "int", 1),
                 _a("subdivisionsCap", "Subdivisions Cap", 0, "int", 0), _a("roundCap", "Round Cap", False, "bool")],
    "polyTorus": [*AXIS, _a("radius", "Radius", 1.0, "length", 0.0),
                  _a("sectionRadius", "Section Radius", 0.5, "length", 0.0), _a("twist", "Twist", 0.0, "angle"),
                  _a("subdivisionsAxis", "Subdivisions Axis", 20, "int", 3),
                  _a("subdivisionsHeight", "Subdivisions Height", 20, "int", 3)],
    "polyPlane": [*AXIS, _a("width", "Width", 1.0, "length", 0.0), _a("height", "Height", 1.0, "length", 0.0),
                  _a("subdivisionsWidth", "Subdivisions Width", 10, "int", 1),
                  _a("subdivisionsHeight", "Subdivisions Height", 10, "int", 1)],
    "polyDisc": [_a("sides", "Sides", 3, "int", 3),
                 _a("subdivisionMode", "Subdivision Mode", 4, ("enum", ("Quads", "Triangles", "Pie", "Caps", "Circle"))),
                 _a("subdivisions", "Subdivisions", 3, "int", 0), _a("radius", "Radius", 1.0, "length", 0.0)],
    "polyPlatonic": [_a("primitive", "Primitive", 4,
                        ("enum", ("Tetrahedron", "Cube", "Octahedron", "Dodecahedron", "Icosahedron"))),
                     _a("subdivisionMode", "Subdivision Mode", 0, ("enum", ("Quads", "Triangles", "Pie", "Caps"))),
                     _a("subdivisions", "Subdivisions", 0, "int", 0), _a("radius", "Radius", 1.0, "length", 0.0),
                     _a("sphericalInflation", "Spherical Inflation", 1.0, "float", 0.0, 1.0)],
    "polyPyramid": [*AXIS, _a("sideLength", "Side Length", 1.0, "length", 0.0),
                    _a("numberOfSides", "Number Of Sides", 4, ("enum3", (3, 4, 5))),
                    _a("subdivisionsHeight", "Subdivisions Height", 1, "int", 1),
                    _a("subdivisionsCaps", "Subdivisions Caps", 0, "int", 0)],
    "polyPrism": [*AXIS, _a("length", "Length", 2.0, "length", 0.0), _a("sideLength", "Side Length", 1.0, "length", 0.0),
                  _a("numberOfSides", "Number Of Sides", 3, "int", 3),
                  _a("subdivisionsHeight", "Subdivisions Height", 1, "int", 1),
                  _a("subdivisionsCaps", "Subdivisions Caps", 0, "int", 0)],
    # NURBS
    "makeNurbCircle": [*NORMAL, *CENTER, _a("radius", "Radius", 1.0, "length", 0.0),
                       _a("sweep", "Sweep", 360.0, "angle", -360.0, 360.0), _a("degree", "Degree", 3, DEGREE),
                       _a("sections", "Sections", 8, "int", 1)],
    "makeNurbsSquare": [*NORMAL, *CENTER, _a("sideLength1", "Side Length 1", 1.0, "length", 0.0),
                        _a("sideLength2", "Side Length 2", 1.0, "length", 0.0), _a("degree", "Degree", 3, DEGREE),
                        _a("spansPerSide", "Spans Per Side", 1, "int", 1)],
    "makeNurbSphere": [*PIVOT, *AXIS, _a("radius", "Radius", 1.0, "length", 0.0), *SWEEPS,
                       _a("degree", "Degree", 3, DEGREE), _a("sections", "Sections", 8, "int", 2),
                       _a("spans", "Spans", 4, "int", 2)],
    "makeNurbCylinder": [*PIVOT, *AXIS, _a("radius", "Radius", 1.0, "length", 0.0), *SWEEPS,
                         _a("degree", "Degree", 3, DEGREE), _a("sections", "Sections", 8, "int", 2),
                         _a("spans", "Spans", 1, "int", 1), _a("heightRatio", "Height Ratio", 2.0, "float", 0.0)],
    "makeNurbCone": [*PIVOT, *AXIS, _a("radius", "Radius", 1.0, "length", 0.0), *SWEEPS,
                     _a("degree", "Degree", 3, DEGREE), _a("sections", "Sections", 8, "int", 2),
                     _a("spans", "Spans", 1, "int", 1), _a("heightRatio", "Height Ratio", 2.0, "float", 0.0)],
    "makeNurbTorus": [*PIVOT, *AXIS, _a("radius", "Radius", 1.0, "length", 0.0), *SWEEPS,
                      _a("degree", "Degree", 3, DEGREE), _a("sections", "Sections", 8, "int", 2),
                      _a("spans", "Spans", 4, "int", 2), _a("heightRatio", "Height Ratio", 0.5, "float", 0.0),
                      _a("minorSweep", "Minor Sweep", 360.0, "angle", 0.0, 360.0)],
    "makeNurbPlane": [*PIVOT, *AXIS, _a("width", "Width", 1.0, "length", 0.0),
                      _a("lengthRatio", "Length Ratio", 1.0, "float", 0.0),
                      _a("patchesU", "Patches U", 1, "int", 1), _a("patchesV", "Patches V", 1, "int", 1),
                      _a("degree", "Degree", 3, DEGREE)],
    "makeNurbCube": [*PIVOT, *AXIS, _a("width", "Width", 1.0, "length", 0.0),
                     _a("lengthRatio", "Length Ratio", 1.0, "float", 0.0),
                     _a("heightRatio", "Height Ratio", 1.0, "float", 0.0),
                     _a("patchesU", "Patches U", 1, "int", 1), _a("patchesV", "Patches V", 1, "int", 1),
                     _a("degree", "Degree", 3, DEGREE)],
}
NURBS = {t for t in NODES if t.startswith("make")}


def defaults(node_type):
    return {a[0]: a[2] for a in NODES[node_type]}


def spec(node_type, name):
    return next(a for a in NODES[node_type] if a[0] == name)


def clamp(node_type, name, value):
    """``value`` for attribute ``name`` within Maya's limits (ints / bools / enums coerced)."""
    _n, _l, default, kind, lo, hi = spec(node_type, name)
    if kind == "bool":
        return bool(value)
    if isinstance(kind, tuple):
        if kind[0] == "enum3":
            v = int(round(value))
            return min(kind[1], key=lambda c: abs(c - v))
        if kind is DEGREE:
            return 1 if int(round(value)) < 2 else 3
        return max(0, min(len(kind[1]) - 1, int(round(value))))
    value = int(round(value)) if kind == "int" else float(value)
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


# --- small vector helpers ---------------------------------------------------------------------------------

def _rot_to(axis):
    """3x3 rotation taking Maya +Y to ``axis`` (shortest arc)."""
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-12:
        return None
    x, y, z = x / n, y / n, z / n
    if y > 1 - 1e-12:
        return None
    if y < -1 + 1e-12:
        return ((1, 0, 0), (0, -1, 0), (0, 0, -1))
    kx, kz = z, -x   # rotation axis Y x a = (z, 0, -x), angle acos(y)
    s = math.sqrt(kx * kx + kz * kz)
    kx, kz = kx / s, kz / s
    c, sn = y, s
    t = 1 - c
    return ((t * kx * kx + c, -sn * kz, t * kx * kz),
            (sn * kz, c, -sn * kx),
            (t * kx * kz, sn * kx, t * kz * kz + c))


def _apply(m, p):
    return (m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2],
            m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2],
            m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2])


def _orient(verts, a, offset=(0.0, 0.0, 0.0)):
    m = _rot_to((a.get("axisX", 0.0), a.get("axisY", 1.0), a.get("axisZ", 0.0)))
    if m is not None:
        verts = [_apply(m, p) for p in verts]
    if any(offset):
        verts = [(p[0] + offset[0], p[1] + offset[1], p[2] + offset[2]) for p in verts]
    return verts


def _ring(n, r, y):
    """Maya's ring order: vertex i at angle -(i + 1) * 360 / n in (x, z)."""
    out = []
    for i in range(n):
        t = -2 * math.pi * (i + 1) / n
        out.append((r * math.cos(t), y, r * math.sin(t)))
    return out


def _edges_of(faces):
    out = set()
    for f in faces:
        for i in range(len(f)):
            out.add(frozenset((f[i], f[i - 1])))
    return out


# --- polygon primitives  ---------------------------------------------------------------------------------

def poly_cube(a):
    w, h, d = a["width"], a["height"], a["depth"]
    sx, sy, sz = a["subdivisionsWidth"], a["subdivisionsHeight"], a["subdivisionsDepth"]
    verts, index = [], {}

    def vid(p):
        key = tuple(round(c, 7) for c in p)
        if key not in index:
            index[key] = len(verts)
            verts.append(p)
        return index[key]

    faces, uvs = [], []
    # Maya's cross layout, menu Create UVs = Normalize Collectively and Preserve Aspect Ratio: 0.25 squares,
    # columns 0.125 / 0.375 / 0.625 / 0.875
    c_, c0, c1, c2 = 0.125, 0.375, 0.625, 0.875
    # side: (origin, u axis, v axis, nu, nv, uv rect (u0, v0, u1, v1))
    sides = (
        ((-w / 2, -h / 2, d / 2), (w, 0, 0), (0, h, 0), sx, sy, (c0, 0.0, c1, 0.25)),        # front +Z
        ((-w / 2, h / 2, d / 2), (w, 0, 0), (0, 0, -d), sx, sz, (c0, 0.25, c1, 0.5)),       # top +Y
        ((-w / 2, h / 2, -d / 2), (w, 0, 0), (0, -h, 0), sx, sy, (c0, 0.5, c1, 0.75)),      # back -Z
        ((-w / 2, -h / 2, -d / 2), (w, 0, 0), (0, 0, d), sx, sz, (c0, 0.75, c1, 1.0)),      # bottom -Y
        ((w / 2, -h / 2, d / 2), (0, 0, -d), (0, h, 0), sz, sy, (c1, 0.0, c2, 0.25)),       # right +X
        ((-w / 2, -h / 2, -d / 2), (0, 0, d), (0, h, 0), sz, sy, (c_, 0.0, c0, 0.25)),      # left -X
    )
    for side, (o, du, dv, nu, nv, (u0, v0, u1, v1)) in enumerate(sides):
        # Maya walks the right side (+X) from the back (15 / 15 polyCube sizes): its interior vertices
        # and faces come back to front
        cols = list(range(nu + 1))[::-1] if side == 4 else list(range(nu + 1))
        grid = [{} for _ in range(nv + 1)]
        for j in range(nv + 1):
            for i in cols:
                grid[j][i] = vid((o[0] + du[0] * i / nu + dv[0] * j / nv, o[1] + du[1] * i / nu + dv[1] * j / nv,
                                  o[2] + du[2] * i / nu + dv[2] * j / nv))
        for j in range(nv):
            for i in cols[1:] if side == 4 else cols[:-1]:
                faces.append([grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]])
                uvs.append([(u0 + (u1 - u0) * i / nu, v0 + (v1 - v0) * j / nv),
                            (u0 + (u1 - u0) * (i + 1) / nu, v0 + (v1 - v0) * j / nv),
                            (u0 + (u1 - u0) * (i + 1) / nu, v0 + (v1 - v0) * (j + 1) / nv),
                            (u0 + (u1 - u0) * i / nu, v0 + (v1 - v0) * (j + 1) / nv)])
    hard = set()
    for f in faces:   # Maya: the cube's 12 box edges are hard, the subdivision edges soft
        for i in range(len(f)):
            p, q = verts[f[i]], verts[f[i - 1]]
            on = sum(1 for k, half in enumerate((w / 2, h / 2, d / 2))
                     if abs(abs(p[k]) - half) < 1e-7 and abs(abs(q[k]) - half) < 1e-7 and p[k] * q[k] > 0)
            if on >= 2:
                hard.add(frozenset((f[i], f[i - 1])))
    return Mesh(_orient(verts, a), faces, uvs, hard, _cube_edges(index, w, h, d, sx, sy, sz))


def _cube_edges(index, w, h, d, sx, sy, sz):
    """polyCube's edge ids (15 / 15 sizes edge for edge): the
    2 x (Height + Depth) vertex rows around the front / top / back / bottom, first the Width edges along each row,
    then the edges from each row to the next; then per side cap (+X, then -X) its inner rows (bottom to top, back to
    front), then its inner columns (rows of cells bottom to top, columns back to front)."""
    def at(x, y, z):
        return index[tuple(round(c, 7) for c in (x, y, z))]

    rows = 2 * (sy + sz)
    out = [(r * (sx + 1) + i, r * (sx + 1) + i + 1) for r in range(rows) for i in range(sx)]
    out += [(r * (sx + 1) + i, (r + 1) % rows * (sx + 1) + i) for r in range(rows) for i in range(sx + 1)]
    for x in (w / 2, -w / 2):
        def g(j, k):
            return at(x, -h / 2 + h * j / sy, -d / 2 + d * k / sz)
        out += [(g(j, k), g(j, k + 1)) for j in range(1, sy) for k in range(sz)]
        out += [(g(j, k), g(j + 1, k)) for j in range(sy) for k in range(1, sz)]
    return out


def poly_sphere(a):
    r, sx, sy = a["radius"], a["subdivisionsAxis"], a["subdivisionsHeight"]
    verts = []
    for k in range(1, sy):
        phi = -math.pi / 2 + math.pi * k / sy
        verts += _ring(sx, r * math.cos(phi), r * math.sin(phi))
    bottom, top = len(verts), len(verts) + 1
    verts += [(0.0, -r, 0.0), (0.0, r, 0.0)]
    faces, uvs = [], []
    for k in range(sy - 2):
        for i in range(sx):
            j = (i + 1) % sx
            faces.append([k * sx + i, k * sx + j, (k + 1) * sx + j, (k + 1) * sx + i])
            uvs.append([(i / sx, (k + 1) / sy), ((i + 1) / sx, (k + 1) / sy), ((i + 1) / sx, (k + 2) / sy),
                        (i / sx, (k + 2) / sy)])
    last = (sy - 2) * sx
    for i in range(sx):   # pole fans, "sawtooth" pole UVs (menu Create UVs = 2)
        j = (i + 1) % sx
        faces.append([j, i, bottom])
        uvs.append([((i + 1) / sx, 1 / sy), (i / sx, 1 / sy), ((i + 0.5) / sx, 0.0)])
    for i in range(sx):
        j = (i + 1) % sx
        faces.append([last + i, last + j, top])
        uvs.append([(i / sx, (sy - 1) / sy), ((i + 1) / sx, (sy - 1) / sy), ((i + 0.5) / sx, 1.0)])
    return Mesh(_orient(verts, a), faces, uvs, _soft_by_angle(verts, faces))


def _cap(verts, faces, uvs, rim, centre_y, sc, r, top, uv_c, uv_r, dome=0.0, centre_dv=0.0):
    """A cylinder / cone / pyramid / prism cap on ring ``rim`` (vertex ids): an n-gon (sc 0) or ``sc`` rings with a
    centre fan. ``dome`` > 0: Maya Round Cap (rings on a hemisphere of radius ``dome``). UVs: a circle of
    radius ``uv_r`` around ``uv_c`` (u = x, v = z on the bottom cap and -z on the top one, menu Create UVs = Normalize
    and Preserve Aspect Ratio); Maya puts the centre vertex ``centre_dv`` lower."""
    n = len(rim)
    sign = 1 if top else -1
    rim_r = math.hypot(verts[rim[0]][0], verts[rim[0]][2]) or 1.0

    def cap_uv(p):
        if abs(p[0]) < 1e-12 and abs(p[2]) < 1e-12:
            return (uv_c[0], uv_c[1] - centre_dv)
        k = uv_r / rim_r
        return (uv_c[0] + k * p[0], uv_c[1] - sign * k * p[2])

    if sc == 0:
        f = list(rim) if top else list(reversed(rim))
        if not top:
            f = [rim[0]] + list(reversed(rim[1:]))
        faces.append(f)
        uvs.append([cap_uv(verts[v]) for v in f])
        return
    rings = [list(rim)]
    for c in range(sc - 1, 0, -1):
        if dome:
            ang = math.pi / 2 * (sc - c) / sc
            rr, yy = dome * math.cos(ang), centre_y + sign * dome * math.sin(ang)
        else:
            rr, yy = r * c / sc, centre_y
        start = len(verts)
        verts += _ring(n, rr, yy)
        rings.append(list(range(start, start + n)))
    centre = len(verts)
    verts.append((0.0, centre_y + sign * dome, 0.0))
    for outer, inner in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            f = [outer[i], outer[j], inner[j], inner[i]] if top else [outer[j], outer[i], inner[i], inner[j]]
            faces.append(f)
            uvs.append([cap_uv(verts[v]) for v in f])
    inner = rings[-1]
    for i in range(n):
        j = (i + 1) % n
        f = [inner[i], inner[j], centre] if top else [inner[j], inner[i], centre]
        faces.append(f)
        uvs.append([cap_uv(verts[v]) for v in f])


# Menu UV layout (Create UVs = Normalize and Preserve Aspect Ratio): sides in u 0.375..0.625,
# v 0.3125..0.68844; caps circles of radius 0.15625 around v 0.15625 / 0.84375
SIDE_U, SIDE_V = (0.375, 0.625), (0.3125, 0.68844)
CAP_R, CAP_V, CAP_DV = 0.15625, (0.15625, 0.84375), 0.00625


def cylinder_heights(a):
    """(side height, y shift) of polyCylinder: Round Cap Height Compensation keeps the round caps inside Height
    (the side gets 2 x radius shorter); Height Baseline moves the shape by -baseline x half its whole height
    (-1 = bottom on the origin, 1 = top on the origin)."""
    h, sc = a["height"], a["subdivisionsCaps"]
    dome = a["radius"] if a.get("roundCap") and sc > 0 else 0.0
    if dome and a.get("roundCapHeightCompensation"):
        h = max(h - 2.0 * dome, 0.0)
    return h, -a.get("heightBaseline", 0.0) * (h + 2.0 * dome) / 2.0


def _shifted(verts, dy):
    return verts if not dy else [(x, y + dy, z) for x, y, z in verts]


def poly_cylinder(a):
    r, sx, sy, sc = a["radius"], a["subdivisionsAxis"], a["subdivisionsHeight"], a["subdivisionsCaps"]
    h, dy = cylinder_heights(a)
    dome = r if a.get("roundCap") and sc > 0 else 0.0
    if sc == 0:
        return _cylinder_ngon_caps(a, r, h, sx, sy, dy)
    # Maya stacks every ring from the bottom cap's innermost up the side to the top cap's innermost, then the two
    # centres (24 / 24 polyCylinder sizes with Subdivisions Caps >= 1, round caps 4 / 4)
    rings = []          # (radius, y, part): part -1 bottom cap, 0 side, 1 top cap
    for c in range(1, sc):
        rings.append(_cap_ring(r, -h / 2, sc, c, -1, dome) + (-1,))
    rings += [(r, -h / 2 + h * j / sy, 0) for j in range(sy + 1)]
    for c in range(sc - 1, 0, -1):
        rings.append(_cap_ring(r, h / 2, sc, c, 1, dome) + (1,))
    verts = []
    for rr, yy, _part in rings:
        verts += _ring(sx, rr, yy)
    c0, c1 = len(verts), len(verts) + 1
    verts += [(0.0, -h / 2 - dome, 0.0), (0.0, h / 2 + dome, 0.0)]
    rim0, rim1 = sc - 1, sc - 1 + sy          # the rim rings
    uv_bottom = _cap_uv(r, False, (0.5, CAP_V[0]), CAP_R, CAP_DV)
    uv_top = _cap_uv(r, True, (0.5, CAP_V[1]), CAP_R, CAP_DV)
    faces, uvs, side = [], [], []
    for q in range(len(rings) - 1):
        for i in range(sx):
            k = (i + 1) % sx
            f = [q * sx + i, q * sx + k, (q + 1) * sx + k, (q + 1) * sx + i]
            if rim0 <= q < rim1:
                j = q - rim0
                side.append(len(faces))
                uvs.append([_side_uv(i, j, sx, sy), _side_uv(i + 1, j, sx, sy), _side_uv(i + 1, j + 1, sx, sy),
                            _side_uv(i, j + 1, sx, sy)])
            else:
                uvs.append([(uv_bottom if q < rim0 else uv_top)(verts[v]) for v in f])
            faces.append(f)
    last = (len(rings) - 1) * sx
    for i in range(sx):
        f = [(i + 1) % sx, i, c0]
        faces.append(f)
        uvs.append([uv_bottom(verts[v]) for v in f])
    for i in range(sx):
        f = [last + i, last + (i + 1) % sx, c1]
        faces.append(f)
        uvs.append([uv_top(verts[v]) for v in f])
    hard = set()
    if not dome:
        for i in range(sx):   # the cap rims are hard, the sides soft unless facetted
            hard.add(frozenset((rim0 * sx + i, rim0 * sx + (i + 1) % sx)))
            hard.add(frozenset((rim1 * sx + i, rim1 * sx + (i + 1) % sx)))
    hard |= _soft_by_angle(verts, [faces[i] for i in side])
    return Mesh(_orient(_shifted(verts, dy), a), faces, uvs, hard, _cylinder_edges(len(rings), sx, (c0, c1)))


def _cylinder_ngon_caps(a, r, h, sx, sy, dy=0.0):
    verts = []
    for j in range(sy + 1):
        verts += _ring(sx, r, -h / 2 + h * j / sy)
    faces, uvs = [], []
    for j in range(sy):
        for i in range(sx):
            k = (i + 1) % sx
            faces.append([j * sx + i, j * sx + k, (j + 1) * sx + k, (j + 1) * sx + i])
            uvs.append([_side_uv(i, j, sx, sy), _side_uv(i + 1, j, sx, sy), _side_uv(i + 1, j + 1, sx, sy),
                        _side_uv(i, j + 1, sx, sy)])
    side = len(faces)
    _cap(verts, faces, uvs, list(range(sx)), -h / 2, 0, r, False, (0.5, CAP_V[0]), CAP_R, 0.0, CAP_DV)
    _cap(verts, faces, uvs, list(range(sy * sx, sy * sx + sx)), h / 2, 0, r, True, (0.5, CAP_V[1]), CAP_R, 0.0,
         CAP_DV)
    hard = set()
    for i in range(sx):   # the cap rims are hard, the sides soft unless facetted
        hard.add(frozenset((i, (i + 1) % sx)))
        hard.add(frozenset((sy * sx + i, sy * sx + (i + 1) % sx)))
    hard |= _soft_by_angle(verts, faces[:side])
    return Mesh(_orient(_shifted(verts, dy), a), faces, uvs, hard, _cylinder_edges(sy + 1, sx, None))


def _cap_ring(r, centre_y, sc, c, sign, dome):
    """(radius, y) of cap ring ``c`` (sc - c rings in from the rim), as ``_cap`` places it."""
    if dome:
        ang = math.pi / 2 * (sc - c) / sc
        return dome * math.cos(ang), centre_y + sign * dome * math.sin(ang)
    return r * c / sc, centre_y


def _cap_uv(rim_r, top, uv_c, uv_r, centre_dv):
    """``_cap``'s UV rule as a function of the position (``rim_r`` = the rim's radius)."""
    sign = 1 if top else -1
    rim_r = rim_r or 1.0

    def uv(p):
        if abs(p[0]) < 1e-12 and abs(p[2]) < 1e-12:
            return (uv_c[0], uv_c[1] - centre_dv)
        k = uv_r / rim_r
        return (uv_c[0] + k * p[0], uv_c[1] - sign * k * p[2])
    return uv


def _cylinder_edges(nrings, sx, centres):
    """polyCylinder's edge ids (36 / 36 sizes + 4 round caps, edge for edge): every ring's edges ring by
    ring, then the edges from each ring to the next, then the bottom centre's spokes (centre first) and the top
    centre's (centre last)."""
    out = [(q * sx + i, q * sx + (i + 1) % sx) for q in range(nrings) for i in range(sx)]
    out += [(q * sx + i, (q + 1) * sx + i) for q in range(nrings - 1) for i in range(sx)]
    if centres:
        out += [(centres[0], i) for i in range(sx)]
        out += [((nrings - 1) * sx + i, centres[1]) for i in range(sx)]
    return out


def _side_uv(i, j, n, rows):
    return (SIDE_U[0] + (SIDE_U[1] - SIDE_U[0]) * i / n, SIDE_V[0] + (SIDE_V[1] - SIDE_V[0]) * j / rows)


def poly_cone(a):
    r, h, sx, sy, sc = a["radius"], a["height"], a["subdivisionsAxis"], a["subdivisionsHeight"], a["subdivisionsCap"]
    dome = r if a.get("roundCap") and sc > 0 else 0.0
    verts = []
    for j in range(sy):
        verts += _ring(sx, r * (1 - j / sy), -h / 2 + h * j / sy)
    faces, uvs = [], []

    def side_uv(i, j):   # menu UVs: side fan u 0.25..0.75 at the base, apex (0.5, 1); base circle r 0.25
        return (0.5 + (i / sx - 0.5) * 0.5 * (1 - j / sy), 0.5 + 0.5 * j / sy)

    for j in range(sy - 1):
        for i in range(sx):
            k = (i + 1) % sx
            faces.append([j * sx + i, j * sx + k, (j + 1) * sx + k, (j + 1) * sx + i])
            uvs.append([side_uv(i, j), side_uv(i + 1, j), side_uv(i + 1, j + 1), side_uv(i, j + 1)])
    _cap(verts, faces, uvs, list(range(sx)), -h / 2, sc, r, False, (0.5, 0.25), 0.25, dome)
    apex = len(verts)
    verts.append((0.0, h / 2, 0.0))
    last = (sy - 1) * sx
    for i in range(sx):
        k = (i + 1) % sx
        faces.append([last + i, last + k, apex])
        uvs.append([side_uv(i, sy - 1), side_uv(i + 1, sy - 1), (0.5, 1.0)])
    hard = set() if dome else {frozenset((i, (i + 1) % sx)) for i in range(sx)}
    hard |= {frozenset((last + i, apex)) for i in range(sx)}   # Maya keeps the apex edges hard
    return Mesh(_orient(verts, a), faces, uvs, hard)


def poly_torus(a):
    R, sr, tw = a["radius"], a["sectionRadius"], math.radians(a["twist"])
    sx, sy = a["subdivisionsAxis"], a["subdivisionsHeight"]
    verts = []
    for j in range(sy):
        phi = tw + 2 * math.pi * j / sy
        verts += _ring(sx, R - sr * math.cos(phi), sr * math.sin(phi))
    faces, uvs = [], []
    for j in range(sy):
        jn = (j + 1) % sy
        for i in range(sx):
            k = (i + 1) % sx
            faces.append([j * sx + k, j * sx + i, jn * sx + i, jn * sx + k])
            uvs.append([((i + 1) / sx, 1 - j / sy), (i / sx, 1 - j / sy), (i / sx, 1 - (j + 1) / sy),
                        ((i + 1) / sx, 1 - (j + 1) / sy)])
    return Mesh(_orient(verts, a), faces, uvs, _soft_by_angle(verts, faces))


def poly_plane(a):
    w, h, sx, sy = a["width"], a["height"], a["subdivisionsWidth"], a["subdivisionsHeight"]
    verts = [(-w / 2 + w * i / sx, 0.0, h / 2 - h * j / sy) for j in range(sy + 1) for i in range(sx + 1)]
    faces, uvs = [], []
    big = max(w, h) or 1.0
    su, sv = w / big, h / big   # menu Create UVs = Normalize and Preserve Aspect Ratio
    for j in range(sy):
        for i in range(sx):
            v0 = j * (sx + 1) + i
            faces.append([v0, v0 + 1, v0 + sx + 2, v0 + sx + 1])
            uvs.append([(su * i / sx, sv * j / sy), (su * (i + 1) / sx, sv * j / sy),
                        (su * (i + 1) / sx, sv * (j + 1) / sy), (su * i / sx, sv * (j + 1) / sy)])
    return Mesh(_orient(verts, a), faces, uvs, ())


def _apex_uv(i, j, n, rows):
    """Cone / pyramid side UVs (menu layout): a fan from u 0.25..0.75 at v 0.5 to the apex (0.5, 1)."""
    return (0.5 + (i / n - 0.5) * 0.5 * (1 - j / rows), 0.5 + 0.5 * j / rows)


def _ngon_solid(a, n, side, length, sh, sc, apex):
    """Pyramid (``apex``) / prism: Maya side-length based polygons."""
    R = side / (2 * math.sin(math.pi / n))
    verts, faces, uvs = [], [], []
    rows = sh if apex else sh + 1
    for j in range(rows):
        f = j / sh
        verts += _ring(n, R * (1 - f) if apex else R, -length / 2 + length * f)
    for j in range(rows - 1):
        for i in range(n):
            k = (i + 1) % n
            faces.append([j * n + i, j * n + k, (j + 1) * n + k, (j + 1) * n + i])
            if apex:
                uvs.append([_apex_uv(i, j, n, sh), _apex_uv(i + 1, j, n, sh), _apex_uv(i + 1, j + 1, n, sh),
                            _apex_uv(i, j + 1, n, sh)])
            else:
                uvs.append([_side_uv(i, j, n, sh), _side_uv(i + 1, j, n, sh), _side_uv(i + 1, j + 1, n, sh),
                            _side_uv(i, j + 1, n, sh)])
    if apex:
        _cap(verts, faces, uvs, list(range(n)), -length / 2, sc, R, False, (0.5, 0.25), 0.25)
        top = len(verts)
        verts.append((0.0, length / 2, 0.0))
        last = (rows - 1) * n
        for i in range(n):
            k = (i + 1) % n
            faces.append([last + i, last + k, top])
            uvs.append([_apex_uv(i, rows - 1, n, sh), _apex_uv(i + 1, rows - 1, n, sh), (0.5, 1.0)])
    else:
        _cap(verts, faces, uvs, list(range(n)), -length / 2, sc, R, False, (0.5, CAP_V[0]), CAP_R, 0.0, CAP_DV)
        _cap(verts, faces, uvs, list(range(sh * n, sh * n + n)), length / 2, sc, R, True, (0.5, CAP_V[1]), CAP_R,
             0.0, CAP_DV)
    return Mesh(_orient(verts, a), faces, uvs, ALL)


def poly_pyramid(a):
    n, s = a["numberOfSides"], a["sideLength"]
    R = s / (2 * math.sin(math.pi / n))
    height = math.sqrt(max(s * s - R * R, 0.0))   # equilateral side triangles
    return _ngon_solid(a, n, s, height, a["subdivisionsHeight"], a["subdivisionsCaps"], True)


def poly_prism(a):
    return _ngon_solid(a, a["numberOfSides"], a["sideLength"], a["length"], a["subdivisionsHeight"],
                       a["subdivisionsCaps"], False)


# --- polyDisc  ------------------------------------------------------------------------------------------

def _polygon(n, r):
    """polyDisc corners in (x, z): corner i at 90 + 180 / n - 360 i / n degrees (n = 3 -> (-0.866, 0.5),
    (0.866, 0.5), (0, -1))."""
    out = []
    for i in range(n):
        t = math.pi / 2 + math.pi / n - 2 * math.pi * i / n
        out.append((r * math.cos(t), r * math.sin(t)))
    return out


def _lerp(p, q, t):
    return tuple(a + (b - a) * t for a, b in zip(p, q))


class _Builder:
    def __init__(self):
        self.verts, self.faces, self.index = [], [], {}

    def v(self, p):
        key = tuple(round(c, 7) for c in p)
        if key not in self.index:
            self.index[key] = len(self.verts)
            self.verts.append(tuple(p))
        return self.index[key]


def _disc_2d(n, mode, sub, r):
    """polyDisc in (x, z): list of 2D points and faces."""
    corners = _polygon(n, r)
    b = _Builder()
    centre = (0.0, 0.0)
    if mode in (0, 4):
        if sub == 0:
            b.faces.append([b.v(c) for c in corners])
            return b
        g = 2 ** (sub - 1)
        for i in range(n):
            c, nxt, prv = corners[i], corners[(i + 1) % n], corners[i - 1]
            m1, m0 = _lerp(c, nxt, 0.5), _lerp(prv, c, 0.5)
            # kite c -> m1 -> centre -> m0, bilinear g x g
            for y in range(g):
                for x in range(g):
                    def pt(s, t):
                        a0 = _lerp(m0, c, s)
                        a1 = _lerp(centre, m1, s)
                        return _lerp(a0, a1, t)
                    quad = [pt((x) / g, y / g), pt((x + 1) / g, y / g), pt((x + 1) / g, (y + 1) / g),
                            pt(x / g, (y + 1) / g)]
                    b.faces.append([b.v(p) for p in quad])
        if mode == 4:   # Circle: kites rebuilt as Coons patches between circle arcs and straight spokes
            b = _Builder()
            step = 2 * math.pi / n
            for i in range(n):
                ca = math.atan2(corners[i][1], corners[i][0])
                m0a, m1a = ca + step / 2, ca - step / 2   # corner order runs clockwise: next corner at ca - step

                def arc(t0, t1, u):
                    t = t0 + (t1 - t0) * u
                    return (r * math.cos(t), r * math.sin(t))

                def spoke(t, u):
                    return (r * u * math.cos(t), r * u * math.sin(t))

                c, m1, m0 = corners[i], (r * math.cos(m1a), r * math.sin(m1a)), (r * math.cos(m0a), r * math.sin(m0a))

                def pt(s_, t_):
                    # s_: m0 -> c (bottom) and centre -> m1 (top); t_: bottom -> top
                    bottom = arc(m0a, ca, s_)
                    top = spoke(m1a, s_)
                    left = spoke(m0a, 1 - t_)
                    right = arc(ca, m1a, t_)
                    bl = tuple(m0[k] * (1 - s_) * (1 - t_) + c[k] * s_ * (1 - t_) + 0.0 * (1 - s_) * t_ + m1[k] * s_ * t_
                               for k in range(2))
                    return tuple((1 - t_) * bottom[k] + t_ * top[k] + (1 - s_) * left[k] + s_ * right[k] - bl[k]
                                 for k in range(2))
                for y in range(g):
                    for x in range(g):
                        quad = [pt(x / g, y / g), pt((x + 1) / g, y / g), pt((x + 1) / g, (y + 1) / g),
                                pt(x / g, (y + 1) / g)]
                        b.faces.append([b.v(p) for p in quad])
        return b
    if mode == 3:   # Caps: sub + 1 concentric rings, centre fan
        rings = sub + 1
        for k in range(rings):
            s0, s1 = 1 - k / rings, 1 - (k + 1) / rings
            for i in range(n):
                j = (i + 1) % n
                a0, a1 = _lerp(centre, corners[i], s0), _lerp(centre, corners[j], s0)
                if k == rings - 1:
                    b.faces.append([b.v(a0), b.v(a1), b.v(centre)])
                else:
                    b.faces.append([b.v(a0), b.v(a1), b.v(_lerp(centre, corners[j], s1)),
                                    b.v(_lerp(centre, corners[i], s1))])
        return b
    if mode == 1 and n == 3:   # Triangles on a triangle: the triangle itself on a (sub + 1) grid
        _tri_grid(b, corners[0], corners[1], corners[2], sub + 1)
        return b
    tris = [(corners[i], corners[(i + 1) % n], centre) for i in range(n)]
    if mode == 1:
        for t in tris:
            _tri_grid(b, t[0], t[1], t[2], max(sub, 1))
        return b
    # Pie: fan, then (sub - 1) centroid splits
    for _ in range(max(sub, 1) - 1):
        tris = [s for t in tris for s in _centroid_split(t)]
    for t in tris:
        b.faces.append([b.v(p) for p in t])
    return b


def _tri_grid(b, p0, p1, p2, g):
    def pt(i, j):   # i along p0->p1, j along p0->p2
        return tuple(p0[k] + (p1[k] - p0[k]) * i / g + (p2[k] - p0[k]) * j / g for k in range(len(p0)))
    for j in range(g):
        for i in range(g - j):
            b.faces.append([b.v(pt(i, j)), b.v(pt(i + 1, j)), b.v(pt(i, j + 1))])
            if i + j + 1 < g:
                b.faces.append([b.v(pt(i + 1, j)), b.v(pt(i + 1, j + 1)), b.v(pt(i, j + 1))])


def _centroid_split(t):
    c = tuple(sum(p[k] for p in t) / 3 for k in range(len(t[0])))
    return [(t[0], t[1], c), (t[1], t[2], c), (t[2], t[0], c)]


def poly_disc(a):
    n, mode, sub, r = a["sides"], a["subdivisionMode"], a["subdivisions"], a["radius"]
    b = _disc_2d(n, mode, sub, r)
    verts = [(x, 0.0, z) for x, z in b.verts]
    faces = [list(reversed(f)) if _facing_down(verts, f) else f for f in b.faces]
    uvs = [[(0.5 + verts[v][0] / (2 * r or 1), 0.5 - verts[v][2] / (2 * r or 1)) for v in f] for f in faces]
    return Mesh(verts, faces, uvs, ())


def _facing_down(verts, f):
    s = 0.0
    for i in range(len(f)):
        p, q = verts[f[i - 1]], verts[f[i]]
        s += p[2] * q[0] - p[0] * q[2]
    return s < 0


# --- polyPlatonic  ----------------------------------------------------------------------------------------

def _platonic_base(kind):
    phi = (1 + math.sqrt(5)) / 2
    if kind == 0:   # tetrahedron, apex on +Z
        # Maya's tetrahedron: apex +Z, base ring at z = -0.5 (radius 0.866), not the regular -1/3
        k = math.sqrt(0.75)
        v = [(0, 0, 1)] + [(k * math.cos(t), k * math.sin(t), -0.5) for t in (0, 2 * math.pi / 3, -2 * math.pi / 3)]
        f = [[0, 1, 2], [1, 3, 2], [0, 2, 3], [0, 3, 1]]
    elif kind == 1:
        s = 1 / math.sqrt(3)
        v = [(s, s, s), (s, -s, s), (-s, -s, s), (-s, s, s), (s, s, -s), (s, -s, -s), (-s, -s, -s), (-s, s, -s)]
        f = [[0, 3, 2, 1], [7, 4, 5, 6], [2, 6, 5, 1], [0, 4, 7, 3], [2, 3, 7, 6], [1, 5, 4, 0]]
    elif kind == 2:
        v = [(0, 0, 1), (1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0), (0, 0, -1)]
        f = [[1, 2, 0], [2, 3, 0], [3, 4, 0], [0, 4, 1], [5, 2, 1], [5, 3, 2], [5, 4, 3], [5, 1, 4]]
    elif kind == 4:   # icosahedron, poles on Z
        z = 1 / math.sqrt(5)
        rr = 2 / math.sqrt(5)
        v = [(0, 0, -1)]
        v += [(rr * math.cos(math.radians(36 + 72 * k)), rr * math.sin(math.radians(36 + 72 * k)), -z) for k in range(5)]
        v += [(rr * math.cos(math.radians(72 * k)), rr * math.sin(math.radians(72 * k)), z) for k in range(5)]
        v += [(0, 0, 1)]
        f = [[0, 2, 1], [0, 3, 2], [0, 4, 3], [0, 5, 4], [0, 1, 5], [1, 2, 7], [2, 3, 8], [3, 4, 9], [4, 5, 10],
             [5, 1, 6], [1, 7, 6], [2, 8, 7], [3, 9, 8], [4, 10, 9], [5, 6, 10], [6, 7, 11], [7, 8, 11], [8, 9, 11],
             [9, 10, 11], [10, 6, 11]]
    else:   # dodecahedron: (+-1, +-1, +-1) and (0, +-1/phi, +-phi) cycles over sqrt(3), Maya's order
        q, g = 1 / phi, phi
        raw = [(0, -q, -g), (-q, -g, 0), (-g, 0, -q), (-1, -1, -1), (-1, -1, 1), (0, -q, g), (-q, g, 0), (-g, 0, q),
               (-1, 1, -1), (-1, 1, 1), (0, q, -g), (q, -g, 0), (g, 0, -q), (1, -1, -1), (1, -1, 1), (0, q, g),
               (q, g, 0), (g, 0, q), (1, 1, -1), (1, 1, 1)]
        s3 = math.sqrt(3)
        v = [(x / s3, y / s3, z / s3) for x, y, z in raw]
        f = []
        for nrm in [(0, g, 1), (0, g, -1), (0, -g, 1), (0, -g, -1), (g, 1, 0), (g, -1, 0), (-g, 1, 0), (-g, -1, 0),
                    (1, 0, g), (1, 0, -g), (-1, 0, g), (-1, 0, -g)]:
            five = sorted(range(20), key=lambda i: -sum(v[i][k] * nrm[k] for k in range(3)))[:5]
            cx = [sum(v[i][k] for i in five) / 5 for k in range(3)]
            ref = [v[five[0]][k] - cx[k] for k in range(3)]
            ref2 = (nrm[1] * ref[2] - nrm[2] * ref[1], nrm[2] * ref[0] - nrm[0] * ref[2],
                    nrm[0] * ref[1] - nrm[1] * ref[0])

            def ang(i, ref=ref, ref2=ref2, cx=cx):
                d = [v[i][k] - cx[k] for k in range(3)]
                return math.atan2(sum(d[k] * ref2[k] for k in range(3)), sum(d[k] * ref[k] for k in range(3)))
            f.append(sorted(five, key=ang))
    return [tuple(float(c) for c in p) for p in v], f


def poly_platonic(a):
    kind, mode, sub, r, infl = (a["primitive"], a["subdivisionMode"], a["subdivisions"], a["radius"],
                                a["sphericalInflation"])
    base_v, base_f = _platonic_base(kind)
    b = _Builder()
    polys = [[base_v[i] for i in f] for f in base_f]
    if mode == 3:   # Caps: sub + 1 rings per face, centre fan
        for p in polys:
            n = len(p)
            c = tuple(sum(q[k] for q in p) / n for k in range(3))
            rings = sub + 1
            for k in range(rings):
                s0, s1 = 1 - k / rings, 1 - (k + 1) / rings
                for i in range(n):
                    j = (i + 1) % n
                    a0, a1 = _lerp(c, p[i], s0), _lerp(c, p[j], s0)
                    if k == rings - 1:
                        b.faces.append([b.v(a0), b.v(a1), b.v(c)])
                    else:
                        b.faces.append([b.v(a0), b.v(a1), b.v(_lerp(c, p[j], s1)), b.v(_lerp(c, p[i], s1))])
    elif sub == 0:
        for p in polys:
            b.faces.append([b.v(q) for q in p])
    elif mode == 0:   # Quads: each n-gon -> n quads, then each quad -> 4 per further level
        quads = []
        for p in polys:
            n = len(p)
            c = tuple(sum(q[k] for q in p) / n for k in range(3))
            for i in range(n):
                quads.append([p[i], _lerp(p[i], p[(i + 1) % n], 0.5), c, _lerp(p[i - 1], p[i], 0.5)])
        for _ in range(sub - 1):
            nq = []
            for q in quads:
                c = tuple(sum(x[k] for x in q) / 4 for k in range(3))
                m = [_lerp(q[i], q[(i + 1) % 4], 0.5) for i in range(4)]
                for i in range(4):
                    nq.append([q[i], m[i], c, m[i - 1]])
            quads = nq
        for q in quads:
            b.faces.append([b.v(x) for x in q])
    elif mode == 1:   # Triangles: n-gons fan first, then midpoint splits
        tris, levels = [], sub
        for p in polys:
            if len(p) == 3:
                tris.append(tuple(p))
            else:
                c = tuple(sum(q[k] for q in p) / len(p) for k in range(3))
                tris += [(p[i], p[(i + 1) % len(p)], c) for i in range(len(p))]
        if any(len(p) > 3 for p in polys):
            levels -= 1
        for _ in range(levels):
            nt = []
            for t in tris:
                m = [_lerp(t[i], t[(i + 1) % 3], 0.5) for i in range(3)]
                nt += [(t[0], m[0], m[2]), (m[0], t[1], m[1]), (m[2], m[1], t[2]), (m[0], m[1], m[2])]
            tris = nt
        for t in tris:
            b.faces.append([b.v(x) for x in t])
    else:   # Pie: centroid fan, then centroid splits
        tris = []
        for p in polys:
            c = tuple(sum(q[k] for q in p) / len(p) for k in range(3))
            tris += [(p[i], p[(i + 1) % len(p)], c) for i in range(len(p))]
        for _ in range(sub - 1):
            tris = [s for t in tris for s in _centroid_split(t)]
        for t in tris:
            b.faces.append([b.v(x) for x in t])
    verts = []
    for p in b.verts:
        n = math.sqrt(sum(x * x for x in p)) or 1.0
        s = (1 - infl) + infl / n
        verts.append(tuple(x * s * r for x in p))
    uvs = [[(0.5 + math.atan2(verts[v][2], verts[v][0]) / (2 * math.pi),
             0.5 + math.asin(max(-1.0, min(1.0, verts[v][1] / (r or 1)))) / math.pi) for v in f] for f in b.faces]
    return Mesh(verts, b.faces, uvs, ALL if sub == 0 else ())


def _soft_by_angle(verts, faces, limit=55.0):
    """Edges Maya leaves hard on facetted round primitives: normals more than ~55 degrees apart (6-sided
    cylinders / spheres hard at 60, 20-sided soft, cone sides soft at 53)."""
    normals = []
    for f in faces:
        nx = ny = nz = 0.0
        for i in range(len(f)):
            p, q = verts[f[i - 1]], verts[f[i]]
            nx += (p[1] - q[1]) * (p[2] + q[2])
            ny += (p[2] - q[2]) * (p[0] + q[0])
            nz += (p[0] - q[0]) * (p[1] + q[1])
        n = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        normals.append((nx / n, ny / n, nz / n))
    owner = {}
    for fi, f in enumerate(faces):
        for i in range(len(f)):
            owner.setdefault(frozenset((f[i], f[i - 1])), []).append(fi)
    c = math.cos(math.radians(limit))
    hard = set()
    for e, fs in owner.items():
        if len(fs) == 2:
            a, b = normals[fs[0]], normals[fs[1]]
            if a[0] * b[0] + a[1] * b[1] + a[2] * b[2] < c:
                hard.add(e)
    return hard


POLY = {"polyCube": poly_cube, "polySphere": poly_sphere, "polyCylinder": poly_cylinder, "polyCone": poly_cone,
        "polyTorus": poly_torus, "polyPlane": poly_plane, "polyDisc": poly_disc, "polyPlatonic": poly_platonic,
        "polyPyramid": poly_pyramid, "polyPrism": poly_prism}


# --- NURBS  -----------------------------------------------------------------------------------------------

def _circle_factor(n):
    """Periodic cubic CVs that interpolate a circle at the knots sit at radius 6 / (4 + 2 cos(360/n))."""
    return 6.0 / (4.0 + 2.0 * math.cos(2 * math.pi / n))


def _solve(A, B):
    """Gaussian elimination for small dense systems; B rows are tuples."""
    n = len(A)
    M = [list(A[i]) + list(B[i]) for i in range(n)]
    w = len(B[0])
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c and M[r][c] != 0.0:
                f = M[r][c] / M[c][c]
                M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return [tuple(M[i][n + k] / M[i][i] for k in range(w)) for i in range(n)]


def _bspline_row(n, t):
    """Values of the 3 non-zero... all n + 3 cubic basis functions of the clamped uniform knot vector at ``t``."""
    knots = [0] * 4 + list(range(1, n)) + [n] * 4

    def N(i, p, x):
        if p == 0:
            return 1.0 if knots[i] <= x < knots[i + 1] else 0.0
        out = 0.0
        if knots[i + p] != knots[i]:
            out += (x - knots[i]) / (knots[i + p] - knots[i]) * N(i, p - 1, x)
        if knots[i + p + 1] != knots[i + 1]:
            out += (knots[i + p + 1] - x) / (knots[i + p + 1] - knots[i + 1]) * N(i + 1, p - 1, x)
        return out
    return [N(i, 3, t) for i in range(n + 3)]


def _open_fit(points, t0, t1):
    """Open cubic CVs through ``points`` (n + 1, at the knots) with Maya's end rule: the second CV lies on the end
    tangent ``t0`` / ``t1`` (unit) at a third of the first / last chord."""
    n = len(points) - 1
    dim = len(points[0])
    m = n + 3
    P = [None] * m
    P[0], P[-1] = points[0], points[-1]
    c0 = math.dist(points[0], points[1]) / 3
    c1 = math.dist(points[-2], points[-1]) / 3
    P[1] = tuple(points[0][k] + t0[k] * c0 for k in range(dim))
    P[-2] = tuple(points[-1][k] - t1[k] * c1 for k in range(dim))
    unknown = list(range(2, m - 2))
    if not unknown:
        return P
    A, B = [], []
    for j in range(1, n):
        row = _bspline_row(n, j)
        rhs = list(points[j])
        for i in (0, 1, m - 2, m - 1):
            for k in range(dim):
                rhs[k] -= row[i] * P[i][k]
        A.append([row[i] for i in unknown])
        B.append(tuple(rhs))
    for idx, val in zip(unknown, _solve(A, B)):
        P[idx] = val
    return P


def arc_cvs(radius, start, sweep, sections, degree):
    """CVs of a Maya circle / arc in its own plane (x, y), angles in radians. Returns (points, cyclic)."""
    if degree == 1:
        n = max(sections, 1)
        closed = abs(abs(sweep) - 2 * math.pi) < 1e-9
        pts = [(radius * math.cos(start + sweep * i / n), radius * math.sin(start + sweep * i / n)) for i in range(n + 1)]
        return pts, False if not closed else False
    if abs(abs(sweep) - 2 * math.pi) < 1e-9:
        n = max(sections, 4)
        R = radius * _circle_factor(n)
        step = 2 * math.pi / n * (1 if sweep > 0 else -1)
        return [(R * math.cos(start + step * (i - 1)), R * math.sin(start + step * (i - 1))) for i in range(n)], True
    n = max(sections, 1)
    pts = [(radius * math.cos(start + sweep * i / n), radius * math.sin(start + sweep * i / n)) for i in range(n + 1)]
    s = 1 if sweep > 0 else -1
    t0 = (-math.sin(start) * s, math.cos(start) * s)
    e = start + sweep
    t1 = (-math.sin(e) * s, math.cos(e) * s)
    return _open_fit(pts, t0, t1), False


def _frame_to(normal):
    """Rotation taking +Z to ``normal`` (shortest arc), as a function on 3D points."""
    x, y, z = normal
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / n, y / n, z / n
    if z > 1 - 1e-12:
        return lambda p: p
    if z < -1 + 1e-12:
        return lambda p: (p[0], -p[1], -p[2])
    kx, ky = -y, x   # Z x n
    s = math.sqrt(kx * kx + ky * ky)
    kx, ky = kx / s, ky / s
    c, sn = z, s
    t = 1 - c
    m = ((t * kx * kx + c, t * kx * ky, sn * ky),
         (t * kx * ky, t * ky * ky + c, -sn * kx),
         (-sn * ky, sn * kx, c))
    return lambda p: _apply(m, p)


def nurbs_circle(a):
    sweep = math.radians(a["sweep"])
    deg = a["degree"]
    # Maya: a cubic circle / arc gets at least 4 sections (s 1 / 2 / 3 -> 4)
    sections = max(a["sections"], 4) if deg == 3 else a["sections"]
    pts, cyclic = arc_cvs(a["radius"], math.pi / 2, sweep, sections, deg)
    rot = _frame_to((a["normalX"], a["normalY"], a["normalZ"]))
    c = (a["centerX"], a["centerY"], a["centerZ"])
    out = [_add(rot((p[0], p[1], 0.0)), c) for p in pts]
    return [Patch("", [out], 2 if deg == 1 else 4, 1, cyclic)]


def _add(p, c):
    return (p[0] + c[0], p[1] + c[1], p[2] + c[2])


def _line(p, q, spans, degree):
    pts = [_lerp(p, q, i / spans) for i in range(spans + 1)]
    if degree == 1:
        return pts
    d = tuple(b - a for a, b in zip(p, q))
    n = math.sqrt(sum(x * x for x in d)) or 1.0
    t = tuple(x / n for x in d)
    return _open_fit(pts, t, t)


def nurbs_square(a):
    w, h, sps, deg = a["sideLength1"], a["sideLength2"], a["spansPerSide"], a["degree"]
    rot = _rot_to((a["normalX"], a["normalY"], a["normalZ"]))
    c = (a["centerX"], a["centerY"], a["centerZ"])
    # Maya's four curves for normal +Y in (x, z): top, left, bottom, right, counter-clockwise from +X+Z
    x, z = w / 2, h / 2
    sides = (("top", (x, z), (-x, z)), ("left", (-x, z), (-x, -z)), ("bottom", (-x, -z), (x, -z)),
             ("right", (x, -z), (x, z)))
    out = []
    for name, p, q in sides:
        pts = [(u, 0.0, v) for u, v in _line(p, q, sps, deg)]
        if rot is not None:
            pts = [_apply(rot, p3) for p3 in pts]
        out.append(Patch(name, [[_add(p3, c) for p3 in pts]], 2 if deg == 1 else 4))
    return out


def _revolve(profile, a, sweep_closed):
    """Surface of revolution about Maya +Y: ``profile`` = list of (radius, y); rows = profile points."""
    deg = a["degree"]
    s0, s1 = math.radians(a["startSweep"]), math.radians(a["endSweep"])
    sweep = s1 - s0
    full = abs(abs(sweep) - 2 * math.pi) < 1e-9
    if full and deg == 3:
        n = max(a["sections"], 4)
        f = _circle_factor(n)
        angles = [s0 + 2 * math.pi / n * (i - 1) for i in range(n)]
        factors = [f] * n
        cyclic = True
    else:
        unit, _c = arc_cvs(1.0, s0, sweep, a["sections"], deg)
        angles = [math.atan2(p[1], p[0]) for p in unit]
        factors = [math.hypot(p[0], p[1]) for p in unit]
        cyclic = False
    rows = []
    for rad, y in profile:
        rows.append([(rad * fct * math.cos(t), y, rad * fct * math.sin(t)) for t, fct in zip(angles, factors)])
    return rows, cyclic


def _finish(rows, a, cyclic_u, cyclic_v, name=""):
    pivot = (a.get("pivotX", 0.0), a.get("pivotY", 0.0), a.get("pivotZ", 0.0))
    flat = [p for row in rows for p in row]
    flat = _orient(flat, a, pivot)
    w = len(rows[0])
    rows = [flat[i * w:(i + 1) * w] for i in range(len(rows))]
    order = 2 if a.get("degree", 3) == 1 else 4
    return Patch(name, rows, order, order, cyclic_u, cyclic_v)


def nurbs_sphere(a):
    r, spans, deg = a["radius"], max(a["spans"], 2), a["degree"]
    prof, _c = arc_cvs(r, -math.pi / 2, math.pi, spans, deg)   # (radius, y) from the bottom pole
    prof = [(p[0], p[1]) for p in prof]
    rows, cyc = _revolve(prof, a, True)
    return [_finish(rows, a, cyc, False)]


def nurbs_cylinder(a):
    r, h = a["radius"], a["heightRatio"] * a["radius"]
    prof = _line((r, -h / 2), (r, h / 2), max(a["spans"], 1), a["degree"])
    rows, cyc = _revolve(prof, a, True)
    return [_finish(rows, a, cyc, False)]


def nurbs_cone(a):
    r, h = a["radius"], a["heightRatio"] * a["radius"]
    prof = _line((r, -h / 2), (0.0, h / 2), max(a["spans"], 1), a["degree"])
    rows, cyc = _revolve(prof, a, True)
    return [_finish(rows, a, cyc, False)]


def nurbs_torus(a):
    R, sr, deg = a["radius"], a["heightRatio"] * a["radius"], a["degree"]
    msw = math.radians(a["minorSweep"])
    spans = max(a["spans"], 2)
    start = math.pi
    if deg == 3 and abs(abs(msw) - 2 * math.pi) < 1e-9:
        start += 2 * math.pi / max(spans, 4)   # periodic CVs: the first one on the inner side
    sec, cyc_minor = arc_cvs(sr, start, msw, spans, deg)
    prof = [(R + p[0], p[1]) for p in sec]
    rows, cyc = _revolve(prof, a, True)
    return [_finish(rows, a, cyc, cyc_minor)]


def _grid(width, length, pu, pv, deg):
    xs = _line((-width / 2,), (width / 2,), pu, deg)
    zs = _line((length / 2,), (-length / 2,), pv, deg)
    return [[(x[0], 0.0, z[0]) for z in zs] for x in xs]


def nurbs_plane(a):
    w = a["width"]
    rows = _grid(w, w * a["lengthRatio"], max(a["patchesU"], 1), max(a["patchesV"], 1), a["degree"])
    return [_finish(rows, a, False, False)]


def nurbs_cube(a):
    w = a["width"]
    L, H = w * a["lengthRatio"], w * a["heightRatio"]
    pu, pv, deg = max(a["patchesU"], 1), max(a["patchesV"], 1), a.get("degree", 3)
    X, Y, Z, nZ = (w, 0, 0), (0, H, 0), (0, 0, L), (0, 0, -L)
    out = []
    # (name, centre, u direction, v direction): Maya's six patches; left / right are the +Z / -Z sides,
    # front / back +X / -X
    faces = (("top", (0, H / 2, 0), X, nZ), ("bottom", (0, -H / 2, 0), nZ, X),
             ("left", (0, 0, L / 2), X, Y), ("right", (0, 0, -L / 2), Y, X),
             ("front", (w / 2, 0, 0), nZ, Y), ("back", (-w / 2, 0, 0), Y, nZ))
    for name, c, du, dv in faces:
        # the face's lower Maya axis (x < y < z) gets patchesU, the higher one patchesV
        au, av = _axis_of(du), _axis_of(dv)
        nu_, nv_ = (pu, pv) if au < av else (pv, pu)
        us = _line((-0.5,), (0.5,), nu_, deg)
        vs = _line((-0.5,), (0.5,), nv_, deg)
        rows = [[tuple(c[k] + du[k] * u[0] + dv[k] * v[0] for k in range(3)) for v in vs] for u in us]
        out.append(_finish(rows, a, False, False, name))
    return out


def _axis_of(v):
    return max(range(3), key=lambda k: abs(v[k]))


NURBS_BUILD = {"makeNurbCircle": nurbs_circle, "makeNurbsSquare": nurbs_square, "makeNurbSphere": nurbs_sphere,
               "makeNurbCylinder": nurbs_cylinder, "makeNurbCone": nurbs_cone, "makeNurbTorus": nurbs_torus,
               "makeNurbPlane": nurbs_plane, "makeNurbCube": nurbs_cube}


def build(node_type, attrs):
    a = {**defaults(node_type), **attrs}
    a = {k: clamp(node_type, k, v) for k, v in a.items() if any(s[0] == k for s in NODES[node_type])}
    if node_type in POLY:
        return POLY[node_type](a)
    return NURBS_BUILD[node_type](a)


# Pipe / Helix / Gear / Soccer Ball (prim_shapes_more) and Super Ellipse / Spherical Harmonics / Ultra Shape
# (prim_supershape, one polySuperShape node) join the tables; both modules import this one, so they come last.
from . import prim_shapes_more, prim_supershape  # noqa: E402

for _mod in (prim_shapes_more, prim_supershape):
    NODES.update(_mod.NODES)
    POLY.update(_mod.POLY)
