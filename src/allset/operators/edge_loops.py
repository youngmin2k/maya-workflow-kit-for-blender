# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Insert Edge Loop, Offset Edge Loop and Slide Edge (GitHub #31).

Maya behaviour:
- Insert Edge Loop (polySplitRing): the press on an edge inserts the loop at that point at once, dragging slides it
  along the edge ring, the release keeps it. Relative distance = the same fraction of every ring edge; Equal
  distance = the same length from one side of the ring (the side of the clicked edge nearer to the click), clamped
  to the shortest ring edge (where it reaches an edge's end the loop goes through that vertex); Multiple edge loops =
  N loops at k/(N+1), wherever the click was.
- Offset Edge Loop (polyDuplicateEdge): press-drag on an edge = a new loop on each side of its edge loop. Relative =
  offset × each side edge's own length, Equal = offset × the shortest side edge; inside the mesh a path end cuts the
  faces beyond it into two triangles that Delete edge merges into one quad. A click without a drag uses an offset
  of 0.5.
- Slide Edge (polySlideEdge): middle-drag slides the selected edges along their side edges; Relative = a fraction of
  each vertex's side edge, Absolute = one distance (fraction × the shortest side edge of that side); Use Snapping
  catches the fraction at k/(points+1) within the tolerance.
Tool Settings / window values live in ``Scene.allset_loop_tools`` (default values).
The bmesh parts are tested headless (tests/test_step144_loop.py).
"""

import math

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras import view3d_utils
from mathutils import Vector

from . import mesh_tools
from .menu_items import edge_flow
from .select_convert import loop_next

INSERT_TOOL = "allset.insert_edge_loop_tool"
OFFSET_TOOL = "allset.offset_edge_loop_tool"
SLIDE_TOOL = "allset.slide_edge_tool"
EPS = 1e-6
DRAG_PX = 3              # a press that moves less than this is a click (Offset: offset 0.5)
PRE_MESH = ".allset_loop_pre"

INSERT_POSITIONS = (('RELATIVE', "Relative distance from edge", "The loop cuts every ring edge at the same fraction"),
                    ('EQUAL', "Equal distance from edge", "The loop keeps the same distance from one side of the ring"),
                    ('MULTIPLE', "Multiple edge loops", "Several loops, evenly spaced"))
OFFSET_POSITIONS = INSERT_POSITIONS[:2]
SLIDE_MODES = (('RELATIVE', "Relative", "Each vertex slides the same fraction of its own side edge"),
               ('ABSOLUTE', "Absolute", "Every vertex slides the same distance"))


class ALLSET_PG_loop_tools(bpy.types.PropertyGroup):
    """Maya Tool Settings of Insert Edge Loop / Offset Edge Loop / Slide Edge (default values)."""
    # Insert Edge Loop (SplitEdgeRingTool)
    iel_position: EnumProperty(name="Maintain position", items=INSERT_POSITIONS, default='RELATIVE')
    iel_loops: IntProperty(name="Number of edge loops", default=2, min=1, soft_max=10, max=100,
                           description="How many loops Multiple edge loops inserts")
    iel_edge_flow: BoolProperty(name="Insert with edge flow", default=False,
                                description="The new loop follows the curvature of the surrounding surface")
    iel_adjust_flow: FloatProperty(name="Adjust Edge Flow", default=1.0, min=-1.0, max=2.0, soft_min=0.0,
                                   soft_max=1.0, precision=4)
    iel_smoothing: FloatProperty(name="Smoothing angle", default=30.0, min=0.0, max=180.0, precision=4,
                                 description="New edges between faces at more than this angle are hard")
    # Offset Edge Loop (polyDuplicateEdge window)
    oel_position: EnumProperty(name="Maintain position", items=OFFSET_POSITIONS, default='RELATIVE')
    oel_delete_edge: BoolProperty(name="Delete edge (maintain 4-sided polygons)", default=True,
                                  description="Where a loop ends inside the mesh, merge the two triangles there")
    oel_edge_flow: BoolProperty(name="Insert with edge flow", default=False,
                                description="The new loops follow the curvature of the surrounding surface")
    oel_adjust_flow: FloatProperty(name="Adjust Edge Flow", default=1.0, min=-1.0, max=2.0, soft_min=0.0,
                                   soft_max=1.0, precision=4)
    oel_smoothing: FloatProperty(name="Smoothing angle", default=180.0, min=0.0, max=180.0, precision=4,
                                 description="New edges between faces at more than this angle are hard")
    oel_offset: FloatProperty(name="Offset", default=0.5, min=0.001, max=0.999, precision=4,
                              description="Offset of a click without a drag (Maya polyDuplicateEdgeOffset)")
    # Slide Edge (polySlideEdgeContext)
    slide_mode: EnumProperty(name="Mode", items=SLIDE_MODES, default='RELATIVE')
    slide_snap: BoolProperty(name="Use Snapping", default=True,
                             description="Catch the slide at the snapping points")
    slide_snap_points: IntProperty(name="Snapping Points", default=1, min=1, soft_max=10, max=100,
                                   description="Snapping points along each side edge (1 = the middle)")
    slide_snap_tolerance: FloatProperty(name="Snapping Tolerance", default=0.1, min=0.0, max=1.0, precision=4,
                                        description="How near (fraction of the edge) a snapping point catches")


SETTINGS = {'INSERT': ("iel_position", "iel_loops", "iel_edge_flow", "iel_adjust_flow", "iel_smoothing"),
            'OFFSET': ("oel_position", "oel_delete_edge", "oel_edge_flow", "oel_adjust_flow", "oel_smoothing",
                       "oel_offset"),
            'SLIDE': ("slide_mode", "slide_snap", "slide_snap_points", "slide_snap_tolerance")}


def settings(context=None):
    return (context or bpy.context).scene.allset_loop_tools


def reset_settings(s, kind):
    for name in SETTINGS[kind]:
        s.property_unset(name)


# --- pure: rings and loops ------------------------------------------------------------------------------

def _walk(root, vert, loop):
    """One direction of the quad ring from ``root``: ([(edge, side vertex)], [faces], closed)."""
    items, faces, a = [], [], vert
    while True:
        face = loop.face
        if len(face.verts) != 4:
            return items, faces, False
        opposite = loop.link_loop_next.link_loop_next
        e2 = opposite.edge
        a2 = opposite.link_loop_next.vert if loop.vert is a else opposite.vert
        faces.append(face)
        if e2 is root:
            return items, faces, True
        items.append((e2, a2))
        others = [lo for lo in e2.link_loops if lo.face is not face]
        if len(others) != 1:
            return items, faces, False
        loop, a = others[0], a2


def ring(edge, vert):
    """The quad edge ring through ``edge`` in ring order: (items, faces, closed). ``items`` = [(edge, side vertex)],
    the side vertex being each edge's end on the same side of the ring as ``vert``; ``faces[i]`` lies between
    items i and i+1 (closed: the last face closes the ring). The ring stops at a face that isn't a quad and at
    borders."""
    loops = list(edge.link_loops)
    if not loops:
        return [(edge, vert)], [], False
    fwd, fwd_faces, closed = _walk(edge, vert, loops[0])
    if closed:
        return [(edge, vert)] + fwd, fwd_faces, True
    back, back_faces = [], []
    if len(loops) > 1:
        back, back_faces, _c = _walk(edge, vert, loops[1])
    return back[::-1] + [(edge, vert)] + fwd, back_faces[::-1] + fwd_faces, False


def _shares_edge(a, b):
    return any(b in e.verts for e in a.link_edges)


def _smooth(edges, limit):
    for e in edges:
        if e.is_valid and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) <= limit + 1e-6


def _select_only(bm, edges):
    for f in bm.faces:
        f.select = False
    for e in bm.edges:
        e.select = False
    for v in bm.verts:
        v.select = False
    for e in edges:
        if e.is_valid:
            e.select = True
            for v in e.verts:
                v.select = True
    bm.select_history.clear()


def _cut_points(bm, items, fractions):
    """Split each ring edge at its fractions (ascending, from the side vertex); a fraction at an end is that vertex.
    Returns [[vertex per fraction] per item]."""
    points = []
    for (e, side), fracs in zip(items, fractions):
        far = e.other_vert(side)
        pts, cur, cur_v, done = [], e, side, 0.0
        for u in fracs:
            if u >= 1.0 - EPS:
                pts.append(far)
                continue
            if u <= EPS:
                pts.append(side)
                continue
            new_edge, nv = bmesh.utils.edge_split(cur, cur_v, (u - done) / (1.0 - done))
            pts.append(nv)
            cur = new_edge if far in new_edge.verts else cur
            cur_v, done = nv, u
        points.append(pts)
    return points


def _connect(bm, points, n_faces, closed):
    new = []
    count = len(points)
    for i in range(n_faces):
        j = (i + 1) % count if closed else i + 1
        if j >= count:
            break
        for a, b in zip(points[i], points[j]):
            if a is b or _shares_edge(a, b):
                continue
            res = bmesh.ops.connect_verts(bm, verts=[a, b])
            new += res["edges"]
    return new


def insert_fractions(lengths, root_length, t, from_far, position='RELATIVE', count=2):
    """Per ring edge (``lengths``), the fractions from its side vertex where the new loops cut it. ``t`` = the click
    on the root edge from its side vertex. Equal distance takes ``t``'s distance from the side the click was
    nearer to (``from_far``: the far side), clamped to the shortest ring edge."""
    if position == 'MULTIPLE':
        n = max(1, int(count))
        return [[k / (n + 1) for k in range(1, n + 1)] for _length in lengths]
    t = min(max(t, 0.0), 1.0)
    if position != 'EQUAL':
        return [[t] for _length in lengths]
    d = min((1.0 - t if from_far else t) * root_length, min(lengths))
    out = []
    for length in lengths:
        u = min(d / length, 1.0) if length > EPS else 1.0
        out.append([1.0 - u if from_far else u])
    return out


def insert_loops(bm, edge, t, position='RELATIVE', count=2, smoothing=math.radians(30.0), flow=None):
    """Insert Maya's edge loop(s) through ``edge``; ``t`` = the click on it from ``edge.verts[0]`` (Maya polySplitRing
    weight). Returns the new edges (selected), or [] when nothing could be cut."""
    items, faces, closed = ring(edge, edge.verts[0])
    lengths = [e.calc_length() for e, _s in items]
    fractions = [sorted(f) for f in insert_fractions(lengths, edge.calc_length(), t, t > 0.5, position, count)]
    points = _cut_points(bm, items, fractions)
    new = _connect(bm, points, len(faces), closed)
    _smooth(new, smoothing)
    if flow is not None and new:
        edge_flow(bm, new, flow)
    _select_only(bm, new)
    return new


def loop_path(edge):
    """The edge loop through ``edge`` as a vertex chain: (vertices, edges, closed); edges[i] joins vertices i, i+1."""
    fwd_e, fwd_v = [], []
    e, v = edge, edge.verts[1]
    closed = False
    while True:
        nxt = loop_next(e, v)
        if nxt is None:
            break
        if nxt is edge:
            closed = True
            break
        fwd_e.append(nxt)
        v = nxt.other_vert(v)
        fwd_v.append(v)
        e = nxt
    back_e, back_v = [], []
    if not closed:
        e, v = edge, edge.verts[0]
        while True:
            nxt = loop_next(e, v)
            if nxt is None or nxt is edge:
                break
            back_e.append(nxt)
            v = nxt.other_vert(v)
            back_v.append(v)
            e = nxt
    verts = back_v[::-1] + [edge.verts[0], edge.verts[1]] + fwd_v
    edges = back_e[::-1] + [edge] + fwd_e
    if closed:
        verts = verts[:-1] if verts[-1] is verts[0] else verts
    return verts, edges, closed


def chains(edges):
    """The connected paths of ``edges`` as (vertices, edges, closed); branched groups are left out."""
    edges = [e for e in edges if e.is_valid]
    eset = set(edges)
    seen, out = set(), []

    def links(v):
        return [x for x in v.link_edges if x in eset]
    for start_edge in edges:
        if start_edge in seen:
            continue
        group, todo = set(), [start_edge]
        while todo:
            e = todo.pop()
            if e in group:
                continue
            group.add(e)
            for v in e.verts:
                todo += [x for x in links(v) if x not in group]
        seen |= group
        gverts = {v for e in group for v in e.verts}
        degree = {v: len(links(v)) for v in gverts}
        if any(d > 2 for d in degree.values()):
            continue
        ends = [v for v in gverts if degree[v] == 1]
        closed = not ends
        v = ends[0] if ends else next(iter(gverts))
        verts, path, prev = [v], [], None
        while True:
            nxt = [x for x in links(v) if x is not prev and x not in path]
            if not nxt:
                break
            prev = nxt[0]
            path.append(prev)
            v = prev.other_vert(v)
            if v is verts[0]:
                break
            verts.append(v)
        out.append((verts, path, closed))
    return out


def _other_edge(face, v, e):
    for lo in face.loops:
        if lo.vert is v:
            a, b = lo.edge, lo.link_loop_prev.edge
            return b if a is e else a
    return None


def path_sides(verts, edges, closed):
    """For each vertex of the chain its side edge on side A and side B (None where that side has no face), and the
    path edges' faces per side. Sides are kept across the chain through the shared side edge (4-edge vertices)."""
    n = len(edges)
    faces = [list(e.link_faces) for e in edges]
    fa = [None] * n
    fb = [None] * n
    fa[0] = faces[0][0] if faces[0] else None
    fb[0] = faces[0][1] if len(faces[0]) > 1 else None
    for i in range(1, n):
        v = verts[i]
        for side, src in ((fa, fa), (fb, fb)):
            prev_face = src[i - 1]
            if prev_face is None:
                continue
            s = _other_edge(prev_face, v, edges[i - 1])
            cand = [f for f in faces[i] if s is not None and s in f.edges]
            side[i] = cand[0] if cand else None
        if fa[i] is None and fb[i] is None:
            return None
        if fa[i] is None:
            fa[i] = next((f for f in faces[i] if f is not fb[i]), None)
        if fb[i] is None:
            fb[i] = next((f for f in faces[i] if f is not fa[i]), None)
    sides = []
    for k, v in enumerate(verts):
        if closed:
            before, after = (k - 1) % n, k % n
        else:
            before, after = (k - 1 if k > 0 else None), (k if k < n else None)
        out = []
        for side in (fa, fb):
            s = None
            for i in (after, before):
                if i is not None and side[i] is not None:
                    s = _other_edge(side[i], v, edges[i])
                    if s is not None:
                        break
            out.append(s)
        sides.append(tuple(out))
    return sides, fa, fb


# --- Offset Edge Loop ------------------------------------------------------------------------------------

def offset_loops(bm, edges, offset=0.5, position='RELATIVE', delete_edge=True, smoothing=math.pi, flow=None):
    """Maya polyDuplicateEdge on the edge path ``edges`` (one chain): a new loop on each side. Returns the new loop
    edges (selected), or None when the path can't be offset (a border edge, a branch)."""
    found = chains(edges)
    if len(found) != 1:
        return None
    verts, path, closed = found[0]
    if any(len(e.link_faces) != 2 for e in path):
        return None
    got = path_sides(verts, path, closed)
    if got is None:
        return None
    sides, fa, fb = got
    if any(sa is None or sb is None for sa, sb in sides):
        return None
    offset = min(max(offset, 0.001), 0.999)
    shortest = min(s.calc_length() for pair in sides for s in pair)
    # path ends inside the mesh: the continuation edge and the faces beyond the side edges (before any split)
    ends = []
    if not closed:
        for k, e in ((0, path[0]), (len(verts) - 1, path[-1])):
            v = verts[k]
            if v.is_boundary:
                continue
            cont = loop_next(e, v)
            if cont is None:
                continue
            ends.append((k, cont, cont.other_vert(v)))
    new_points = []
    for k, v in enumerate(verts):
        row = []
        for s in sides[k]:
            length = s.calc_length()
            dist = offset * length if position != 'EQUAL' else offset * shortest
            frac = min(dist / length, 0.999) if length > EPS else 0.5
            _ne, nv = bmesh.utils.edge_split(s, v, frac)
            row.append(nv)
        new_points.append(row)
    new = []
    count = len(verts)
    for i in range(len(path)):
        j = (i + 1) % count
        for side in (0, 1):
            a, b = new_points[i][side], new_points[j][side]
            if not _shares_edge(a, b):
                new += bmesh.ops.connect_verts(bm, verts=[a, b])["edges"]
    loops_only = list(new)
    for k, cont, far in ends:
        for side in (0, 1):
            x = new_points[k][side]
            if not _shares_edge(x, far) and any(far in f.verts for f in x.link_faces):
                new += bmesh.ops.connect_verts(bm, verts=[x, far])["edges"]
        if delete_edge and cont.is_valid:
            bmesh.ops.dissolve_edges(bm, edges=[cont], use_verts=False, use_face_split=False)
    new = [e for e in new if e.is_valid]
    _smooth(new, smoothing)
    if flow is not None and loops_only:
        edge_flow(bm, [e for e in loops_only if e.is_valid], flow)
    _select_only(bm, loops_only)
    return [e for e in loops_only if e.is_valid]


# --- Slide Edge ------------------------------------------------------------------------------------------

def slide_frame(edges):
    """{vertex: (side-A neighbour, side-B neighbour)} of the vertices of ``edges`` (None where a side is missing)."""
    out = {}
    for verts, path, closed in chains(edges):
        got = path_sides(verts, path, closed)
        if got is None:
            continue
        sides = got[0]
        for v, (sa, sb) in zip(verts, sides):
            out[v] = (sa.other_vert(v) if sa is not None else None, sb.other_vert(v) if sb is not None else None)
    return out


def snap(f, points=1, tolerance=0.1):
    """Maya Use Snapping: ``f`` (0..1 along the side edge) caught at k/(points+1) or the ends within ``tolerance``."""
    n = max(1, int(points))
    targets = [k / (n + 1) for k in range(0, n + 2)]
    best = min(targets, key=lambda x: abs(x - f))
    return best if abs(best - f) <= tolerance + 1e-9 else f


def slide_positions(frame, origins, side, f, absolute=False):
    """New positions {vertex: co} for a slide of ``f`` (0..1) towards side 0 (A) or 1 (B). ``origins`` = the
    positions before the slide (of the slid vertices and their neighbours)."""
    f = min(max(f, 0.0), 1.0)
    pairs = [(v, ws[side]) for v, ws in frame.items() if ws[side] is not None]
    if not pairs:
        return {}
    out = {}
    if absolute:
        dist = f * min((origins[w] - origins[v]).length for v, w in pairs)
        for v, w in pairs:
            d = origins[w] - origins[v]
            out[v] = origins[v] + (d.normalized() * min(dist, d.length) if d.length > EPS else d)
    else:
        for v, w in pairs:
            out[v] = origins[v].lerp(origins[w], f)
    return out


# --- operators -------------------------------------------------------------------------------------------

def _region_xy(region, rv3d, world):
    p = view3d_utils.location_3d_to_region_2d(region, rv3d, world)
    return Vector(p) if p is not None else None


class _PreMesh:
    """The mesh as it was at the press: every drag step rebuilds from it (the extrude record's restore_pre pattern)."""

    def __init__(self, bm):
        self.me = bpy.data.meshes.new(PRE_MESH)
        bm.to_mesh(self.me)

    def restore(self, bm):
        bm.clear()
        bm.from_mesh(self.me)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

    def free(self):
        if self.me is not None:
            bpy.data.meshes.remove(self.me)
            self.me = None


def _status(context, text):
    if context.workspace is not None:
        context.workspace.status_text_set(text)


class ALLSET_OT_insert_edge_loop(bpy.types.Operator):
    """Click an edge to insert an edge loop at that point, drag to slide it along the ring (Maya Insert Edge Loop)"""
    bl_idname = "allset.insert_edge_loop"
    bl_label = "Insert Edge Loop"
    bl_options = {'UNDO'}

    object: StringProperty(name="Object", options={'SKIP_SAVE', 'HIDDEN'})
    edge: IntProperty(name="Edge", default=-1, options={'SKIP_SAVE', 'HIDDEN'})
    weight: FloatProperty(name="Weight", default=0.5, min=0.0, max=1.0, subtype='FACTOR',
                          description="Where the loop cuts the clicked edge (from its first vertex)")

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def _build(self, context, bm):
        s = settings(context)
        bm.edges.ensure_lookup_table()
        if not 0 <= self.edge < len(bm.edges):
            return []
        return insert_loops(bm, bm.edges[self.edge], self.weight, s.iel_position, s.iel_loops,
                            math.radians(s.iel_smoothing), s.iel_adjust_flow if s.iel_edge_flow else None)

    def execute(self, context):
        ob = bpy.data.objects.get(self.object) if self.object else context.edit_object
        if ob is None or ob.type != 'MESH' or ob.mode != 'EDIT':
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(ob.data)
        if not self._build(context, bm):
            return {'CANCELLED'}
        bmesh.update_edit_mesh(ob.data)
        return {'FINISHED'}

    def invoke(self, context, event):
        view = mesh_tools._view(context)
        if view is None:
            return {'PASS_THROUGH'}
        mouse = (event.mouse_region_x, event.mouse_region_y)
        ob, index = mesh_tools.pick(view, mesh_tools._mesh_objects(context), mouse, 'EDGE',
                                    mesh_tools.PICK_RADIUS * mesh_tools._ui_scale())
        if ob is None:
            return {'PASS_THROUGH'}
        self._view, self._ob = view, ob
        self.object, self.edge = ob.name, index
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        self._pre = _PreMesh(bm)
        self._update(context, mouse)
        context.window_manager.modal_handler_add(self)
        _status(context, "Insert Edge Loop: drag to slide the loop, release to keep it, Esc / right-click to cancel")
        return {'RUNNING_MODAL'}

    def _update(self, context, mouse):
        bm = bmesh.from_edit_mesh(self._ob.data)
        self._pre.restore(bm)
        edge = bm.edges[self.edge]
        self.weight = min(max(mesh_tools.edge_factor(self._view, self._ob, edge, mouse), 0.001), 0.999)
        self._build(context, bm)
        bmesh.update_edit_mesh(self._ob.data)

    def _end(self, context, keep):
        if not keep:
            bm = bmesh.from_edit_mesh(self._ob.data)
            self._pre.restore(bm)
            bmesh.update_edit_mesh(self._ob.data)
        self._pre.free()
        _status(context, None)
        return {'FINISHED'} if keep else {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            if settings(context).iel_position != 'MULTIPLE':
                self._update(context, (event.mouse_region_x, event.mouse_region_y))
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return self._end(context, True)
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self._end(context, False)
        return {'RUNNING_MODAL'}


class ALLSET_OT_offset_edge_loop(bpy.types.Operator):
    """Click an edge and drag: an edge loop on each side of its edge loop (Maya Offset Edge Loop). Without a click:
    the selected edges"""
    bl_idname = "allset.offset_edge_loop"
    bl_label = "Offset Edge Loop"
    bl_options = {'UNDO'}

    object: StringProperty(name="Object", options={'SKIP_SAVE', 'HIDDEN'})
    edge: IntProperty(name="Edge", default=-1, options={'SKIP_SAVE', 'HIDDEN'},
                      description="Clicked edge (its edge loop); -1 = the selected edges")
    offset: FloatProperty(name="Offset", default=0.5, min=0.001, max=0.999, precision=4,
                          description="Distance of the new loops (fraction of the side edges)")

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def _path(self, bm):
        bm.edges.ensure_lookup_table()
        if self.edge >= 0:
            if self.edge >= len(bm.edges):
                return []
            return loop_path(bm.edges[self.edge])[1]
        return [e for e in bm.edges if e.select]

    def _build(self, context, bm, path):
        s = settings(context)
        return offset_loops(bm, path, self.offset, s.oel_position, s.oel_delete_edge, math.radians(s.oel_smoothing),
                            s.oel_adjust_flow if s.oel_edge_flow else None)

    def execute(self, context):
        objects = [bpy.data.objects.get(self.object)] if self.object else mesh_tools._mesh_objects(context)
        done = False
        for ob in objects:
            if ob is None or ob.type != 'MESH' or ob.mode != 'EDIT':
                continue
            bm = bmesh.from_edit_mesh(ob.data)
            if self.edge >= 0:
                paths = [self._path(bm)]
            else:
                paths = [p for _v, p, _c in chains([e for e in bm.edges if e.select])]
            for path in paths:
                if path and self._build(context, bm, path):
                    done = True
            bmesh.update_edit_mesh(ob.data)
        if not done:
            self.report({'WARNING'}, "Can't perform Offset Edge Loop: pick edges with a face on both sides.")
            return {'CANCELLED'}
        return {'FINISHED'}

    def invoke(self, context, event):
        view = mesh_tools._view(context)
        if view is None:
            return self.execute(context)
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        ob, index = mesh_tools.pick(view, mesh_tools._mesh_objects(context), mouse, 'EDGE',
                                    mesh_tools.PICK_RADIUS * mesh_tools._ui_scale())
        if ob is None:
            return {'PASS_THROUGH'}
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        edge = bm.edges[index]
        path = loop_path(edge)[1]
        if any(len(e.link_faces) != 2 for e in path):
            self.report({'WARNING'}, "Can't perform Offset Edge Loop on a border edge.")
            return {'CANCELLED'}
        region, rv3d = view
        mw = ob.matrix_world
        lengths = []
        for v in edge.verts:
            a = _region_xy(region, rv3d, mw @ v.co)
            for s in v.link_edges:
                if s is edge or s in path:
                    continue
                b = _region_xy(region, rv3d, mw @ s.other_vert(v).co)
                if a is not None and b is not None:
                    lengths.append((b - a).length)
        self._px = max(min(lengths) if lengths else 50.0, 4.0)
        self._view, self._ob, self._press, self._moved = view, ob, mouse, False
        self.object, self.edge = ob.name, index
        self._pre = _PreMesh(bm)
        context.window_manager.modal_handler_add(self)
        _status(context, "Offset Edge Loop: drag to set the offset, release to keep it, Esc / right-click to cancel")
        return {'RUNNING_MODAL'}

    def _update(self, context):
        bm = bmesh.from_edit_mesh(self._ob.data)
        self._pre.restore(bm)
        path = self._path(bm)
        self._build(context, bm, path)
        bmesh.update_edit_mesh(self._ob.data)

    def _end(self, context, keep):
        if not keep:
            bm = bmesh.from_edit_mesh(self._ob.data)
            self._pre.restore(bm)
            bmesh.update_edit_mesh(self._ob.data)
        self._pre.free()
        _status(context, None)
        return {'FINISHED'} if keep else {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            d = (Vector((event.mouse_region_x, event.mouse_region_y)) - self._press).length
            if d >= DRAG_PX or self._moved:
                self._moved = True
                self.offset = min(max(d / self._px, 0.001), 0.999)
                self._update(context)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if not self._moved:
                self.offset = settings(context).oel_offset
                self._update(context)
            return self._end(context, True)
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self._end(context, False)
        return {'RUNNING_MODAL'}


class ALLSET_OT_slide_edge(bpy.types.Operator):
    """Middle-drag: slide the selected edges along their neighbouring edges (Maya Slide Edge)"""
    bl_idname = "allset.slide_edge"
    bl_label = "Slide Edge"
    bl_options = {'UNDO'}

    side: IntProperty(name="Side", default=0, min=0, max=1, options={'SKIP_SAVE'})
    factor: FloatProperty(name="Slide", default=0.0, min=0.0, max=1.0, subtype='FACTOR', options={'SKIP_SAVE'},
                          description="How far along the side edges (fraction)")

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def _frames(self, context):
        out = []
        for ob in mesh_tools._mesh_objects(context):
            bm = bmesh.from_edit_mesh(ob.data)
            frame = slide_frame([e for e in bm.edges if e.select])
            if frame:
                origins = {}
                for v, ws in frame.items():
                    origins[v] = v.co.copy()
                    for w in ws:
                        if w is not None:
                            origins[w] = w.co.copy()
                out.append((ob, bm, frame, origins))
        return out

    def _apply(self, context, frames):
        s = settings(context)
        f = snap(self.factor, s.slide_snap_points, s.slide_snap_tolerance) if s.slide_snap else self.factor
        for ob, bm, frame, origins in frames:
            for v, co in origins.items():
                v.co = co
            for v, co in slide_positions(frame, origins, self.side, f, s.slide_mode == 'ABSOLUTE').items():
                v.co = co
            bmesh.update_edit_mesh(ob.data, loop_triangles=True, destructive=False)

    def execute(self, context):
        frames = self._frames(context)
        if not frames:
            self.report({'WARNING'}, "Select edges to slide.")
            return {'CANCELLED'}
        self._apply(context, frames)
        return {'FINISHED'}

    def invoke(self, context, event):
        view = mesh_tools._view(context)
        frames = self._frames(context)
        if not frames:
            self.report({'WARNING'}, "Select edges to slide.")
            return {'CANCELLED'}
        if view is None:
            return self.execute(context)
        region, rv3d = view
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        best = None
        for ob, _bm, frame, _o in frames:
            mw = ob.matrix_world
            for v, ws in frame.items():
                p = _region_xy(region, rv3d, mw @ v.co)
                if p is None:
                    continue
                dirs = []
                for w in ws:
                    q = _region_xy(region, rv3d, mw @ w.co) if w is not None else None
                    dirs.append(q - p if q is not None and (q - p).length > 1.0 else None)
                d = (p - mouse).length
                if any(x is not None for x in dirs) and (best is None or d < best[0]):
                    best = (d, dirs)
        if best is None:
            return {'CANCELLED'}
        self._dirs, self._press, self._frames_ = best[1], mouse, frames
        context.window_manager.modal_handler_add(self)
        _status(context, "Slide Edge: drag to slide, release to keep, Esc / right-click to cancel")
        return {'RUNNING_MODAL'}

    def _from_mouse(self, mouse):
        delta = mouse - self._press
        best = (0, 0.0)
        for side, d in enumerate(self._dirs):
            if d is None:
                continue
            f = delta.dot(d) / d.length_squared
            if f > best[1]:
                best = (side, f)
        self.side, self.factor = best[0], min(best[1], 1.0)

    def _end(self, context, keep):
        if not keep:
            for ob, _bm, _frame, origins in self._frames_:
                for v, co in origins.items():
                    v.co = co
                bmesh.update_edit_mesh(ob.data, loop_triangles=True, destructive=False)
        _status(context, None)
        return {'FINISHED'} if keep else {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            self._from_mouse(Vector((event.mouse_region_x, event.mouse_region_y)))
            self._apply(context, self._frames_)
            return {'RUNNING_MODAL'}
        if event.type == 'MIDDLEMOUSE' and event.value == 'RELEASE':
            return self._end(context, True)
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self._end(context, False)
        return {'RUNNING_MODAL'}


classes = (ALLSET_PG_loop_tools, ALLSET_OT_insert_edge_loop, ALLSET_OT_offset_edge_loop, ALLSET_OT_slide_edge)


def register_props():
    bpy.types.Scene.allset_loop_tools = bpy.props.PointerProperty(type=ALLSET_PG_loop_tools)


def unregister_props():
    del bpy.types.Scene.allset_loop_tools


def clear():
    """Remove pre-press meshes a modal left behind (add-on disabled mid-drag)."""
    for me in list(bpy.data.meshes):
        if me.name.startswith(PRE_MESH) and me.users == 0:
            bpy.data.meshes.remove(me)
