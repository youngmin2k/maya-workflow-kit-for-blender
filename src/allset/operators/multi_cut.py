# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Multi-Cut (GitHub #27).

The kit tool ``allset.multi_cut_tool`` (ui/mesh_tools.py) runs ``allset.multi_cut``, a modal that places Maya's cut
points and cuts on completion:

- click an edge = a point on it (``NN%`` from the edge's first vertex, like polySplit's edge fraction),
  a vertex = start there, inside a face = a point on the face; press-drag slides the
  point along its edge, Shift snaps it to the Snap Step %; a live line runs from the last point to the mouse;
- Backspace removes the last point, Enter / RMB completes the cut (one undo step) and the tool stays, Esc drops the
  points (with none placed it leaves the tool for Select);
- Ctrl+click on an edge = an edge loop through the ring at that point (``allset.multicut_loop``, so its
  Position is in Adjust Last Operation; Ctrl+Shift = at the Snap Step, Ctrl+MMB = in the middle); Ctrl hover
  previews the loop;
- a drag that starts on a face / empty space = slice along the dragged line (Slice Tool options), and with
  Slice Along Plane YZ / ZX / XY on, a click slices along that world plane.

The cut itself (``cut``) and the slice (``slice_mesh``) are bmesh-only (tests/test_step129_multi_cut.py); picking
uses the pre-selection caches (numpy + BVH occlusion).
"""

import math

import bmesh
import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, geometry

from . import mesh_tools, preselect

TOOL = "allset.multi_cut_tool"
VERT_PX = 10.0          # a press this close to a vertex starts there
EDGE_PX = 16.0          # Maya MT_preSelectSize (preselect.RADIUS_PX)
SLICE_PX = 8.0          # a press-drag longer than this on a face / empty space = slice
END_T = 0.001           # an edge point this close to an end is that vertex
POINT_RGB = (1.0, 0.85, 0.1)       # Maya draws the cut points / line yellow-ish
PREVIEW_RGB = (0.85, 0.85, 0.85)
LOOP_RGB = (1.0, 0.55, 0.1)
REJECT_RGB = (0.9, 0.2, 0.2)
POINT_PX = 7.0
LINE_PX = 2.0

# Maya Y-up plane names -> Blender plane normal (X -> X, Y -> Z, Z -> -Y)
PLANE_NORMALS = {'YZ': Vector((1, 0, 0)), 'ZX': Vector((0, 0, 1)), 'XY': Vector((0, 1, 0))}


# --- pure: the cut (bmesh) ------------------------------------------------------------------------------

def point_faces(bm, point):
    """Faces a cut point lies on (for the "consecutive points share a face" rule)."""
    kind, index = point[0], point[1]
    if kind == 'VERT':
        return set(bm.verts[index].link_faces)
    if kind == 'EDGE':
        return set(bm.edges[index].link_faces)
    return {bm.faces[index]}


def same_point(a, b):
    if a[0] != b[0] or a[1] != b[1]:
        return False
    if a[0] == 'EDGE':
        return abs(a[2] - b[2]) < 1e-6
    if a[0] == 'FACE':
        return (Vector(a[2]) - Vector(b[2])).length < 1e-9
    return True


def accepts(bm, points, new):
    """Maya places a new point only on a face of the previous one (and not on the previous point itself)."""
    if not points:
        return True
    last = points[-1]
    if same_point(last, new):
        return False
    return bool(point_faces(bm, last) & point_faces(bm, new))


def normalize(bm, point):
    """An edge point at an end is that vertex."""
    if point[0] == 'EDGE':
        e = bm.edges[point[1]]
        if point[2] <= END_T:
            return ('VERT', e.verts[0].index)
        if point[2] >= 1.0 - END_T:
            return ('VERT', e.verts[1].index)
    return point


def _inside(face, co):
    try:
        return bmesh.geometry.intersect_face_point(face, co)
    except (AttributeError, ValueError):
        return False


def _split_face(bm, a, b, coords):
    """Split the face shared by vertices ``a`` and ``b`` along a -> coords -> b. Returns the new edges (cut chain)."""
    if a is b:
        return []
    if not coords and bm.edges.get((a, b)) is not None:
        return []               # already joined (two points on the same edge)
    shared = [f for f in a.link_faces if b in f.verts]
    if not shared:
        return []
    probe = coords[0] if coords else (a.co + b.co) / 2
    face = next((f for f in shared if _inside(f, probe)), None)
    if face is None:
        face = min(shared, key=lambda f: (f.calc_center_median() - probe).length)
    before = set(face.verts)
    try:
        new_face, _loop = bmesh.utils.face_split(face, a, b, coords=[tuple(c) for c in coords])
    except ValueError:
        return []
    if new_face is None:
        return []
    created = [v for v in set(face.verts) | set(new_face.verts) if v not in before]
    chain = [a]
    for c in coords:
        if created:
            v = min(created, key=lambda v: (v.co - c).length)
            created.remove(v)
            chain.append(v)
    chain.append(b)
    out = []
    for x, y in zip(chain, chain[1:]):
        e = bm.edges.get((x, y))
        if e is not None:
            out.append(e)
    return out


def cut(bm, points, subdivisions=1, smoothing_angle=math.pi):
    """Maya polySplit: cut ``bm`` along ``points`` (each ``('VERT', i)``, ``('EDGE', i, t)`` with t from
    ``edges[i].verts[0]``, or ``('FACE', i, local co)``). Consecutive vertex / edge points are joined across the face
    they share; face points in between become vertices inside that face. Returns the new cut edges."""
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    points = [normalize(bm, p) for p in points]
    # resolve every element before the mesh changes (BMesh references survive the splits, indices don't matter)
    chains = {}           # original edge -> [(t, vert)] sorted, ends included

    def edge_vert(edge, t):
        chain = chains.setdefault(edge, [(0.0, edge.verts[0]), (1.0, edge.verts[1])])
        for tt, v in chain:
            if abs(tt - t) < 1e-6:
                return v
        for k in range(len(chain) - 1):
            (ta, va), (tb, vb) = chain[k], chain[k + 1]
            if ta < t < tb:
                e = bm.edges.get((va, vb))
                if e is None:
                    return None
                u = (t - ta) / (tb - ta)
                co = va.co.lerp(vb.co, u)
                _e, nv = bmesh.utils.edge_split(e, va, u)
                nv.co = co
                chain.insert(k + 1, (t, nv))
                return nv
        return None

    resolved = []         # ('B', vert-getter) / ('F', world-less local co)
    for p in points:
        if p[0] == 'VERT':
            resolved.append(('B', bm.verts[p[1]], None))
        elif p[0] == 'EDGE':
            resolved.append(('E', bm.edges[p[1]], p[2]))
        else:
            resolved.append(('F', None, Vector(p[2])))
    verts = []            # boundary vertices in order, with the face coords that lead to them
    pending = []
    for kind, el, val in resolved:
        if kind == 'F':
            pending.append(val)
            continue
        v = el if kind == 'B' else edge_vert(el, val)
        if v is None:
            pending = []
            continue
        verts.append((v, pending))
        pending = []
    new_edges = []
    for (a, _c), (b, coords) in zip(verts, verts[1:]):
        new_edges += _split_face(bm, a, b, divided([a.co, *coords, b.co], subdivisions)[1:-1])
    for e in new_edges:
        if len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) <= smoothing_angle + 1e-6
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    return new_edges


def divided(chain, subdivisions):
    """Maya Subdivisions: every segment of the cut chain split into ``subdivisions`` equal parts."""
    n = max(1, int(subdivisions))
    out = [chain[0].copy()]
    for a, b in zip(chain, chain[1:]):
        out += [a.lerp(b, k / n) for k in range(1, n)] + [b.copy()]
    return out


def loop(bm, edge_index, t, smoothing_angle=math.pi):
    """Maya Ctrl+click: an edge loop through the ring of ``edge_index`` at ``t`` (from its first vertex)."""
    bm.edges.ensure_lookup_table()
    t = min(max(t, 0.001), 0.999)
    edges = mesh_tools.insert_loop(bm, bm.edges[edge_index], t)
    for e in edges:
        if len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) <= smoothing_angle + 1e-6
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    return edges


def loop_segments(bm, edge_index, t):
    """Local-space segments of the loop ``loop`` would insert (Ctrl hover preview)."""
    bm.edges.ensure_lookup_table()
    edge = bm.edges[edge_index]
    ring = mesh_tools.edge_ring(edge, edge.verts[0], min(max(t, 0.001), 0.999))
    pos = {e: e.verts[0].co.lerp(e.verts[1].co, u) for e, u in ring.items()}
    segs, seen = [], set()
    for e in ring:
        for f in e.link_faces:
            if f in seen:
                continue
            others = [o for o in f.edges if o is not e and o in pos]
            if others:
                seen.add(f)
                segs.append((pos[e].copy(), pos[others[0]].copy()))
    return segs


def slice_mesh(bm, plane_co, plane_no, faces=None, delete=False, extract=None):
    """Maya Slice Tool: cut ``faces`` (default every face) with a plane (local space). ``delete``: remove the faces on
    the plane's positive side; ``extract`` (local offset vector): split them off and move them. Returns the new cut
    edges."""
    faces = [f for f in (faces if faces is not None else bm.faces) if f.is_valid]
    if not faces:
        return []
    edges = list({e for f in faces for e in f.edges})
    verts = list({v for f in faces for v in f.verts})
    res = bmesh.ops.bisect_plane(bm, geom=verts + edges + faces, dist=1e-6, plane_co=plane_co, plane_no=plane_no)
    cut_edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if delete or extract is not None:
        region = set(faces)
        for e in edges:
            region.update(e.link_faces)
        side = [f for f in region if f.is_valid and (f.calc_center_median() - plane_co).dot(plane_no) > 1e-7]
        if delete and side:
            bmesh.ops.delete(bm, geom=side, context='FACES')
            cut_edges = [e for e in cut_edges if e.is_valid]
        elif extract is not None and side:
            border = [e for e in cut_edges if e.is_valid]
            if border:
                bmesh.ops.split_edges(bm, edges=border)
            moved = {v for f in side if f.is_valid for v in f.verts}
            for v in moved:
                v.co += extract
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    return [e for e in cut_edges if e.is_valid]


# --- picking -------------------------------------------------------------------------------------------

def _ui_scale(context):
    return context.preferences.system.ui_scale or 1.0


def _occluded(cs, region, rv3d, p, xray):
    if xray:
        return False
    p2 = view3d_utils.location_3d_to_region_2d(region, rv3d, p)
    if p2 is None:
        return True
    o = view3d_utils.region_2d_to_origin_3d(region, rv3d, p2)
    d = p - o
    dist = d.length
    if dist < 1e-12:
        return False
    d /= dist
    for _ob, c in cs:
        h = c.ray(o, d)
        if h is not None and h[0] < dist * (1.0 - 1e-4) - 1e-6:
            return True
    return False


def ray_edge_t(region, rv3d, a, b, mouse):
    """Where the view ray under ``mouse`` passes the world segment a-b (0 at a)."""
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    hit = geometry.intersect_line_line(a, b, origin, origin + direction)
    seg = b - a
    if hit is None or seg.length_squared < 1e-12:
        return 0.5
    return max(0.0, min(1.0, (hit[0] - a).dot(seg) / seg.length_squared))


def pick(context, region, rv3d, mouse, only=None, edges_only=False):
    """(object name, point) under ``mouse``: ``('VERT', i)``, ``('EDGE', i, t)`` or ``('FACE', i, local co)``,
    or None. ``only``: object name to look at. Select mode doesn't matter (Maya's Multi-Cut picks all three)."""
    import numpy as np
    cs = [(ob, c) for ob, c in preselect.caches(context) if only is None or ob.name == only]
    if not cs:
        return None
    xray = preselect._xray(context.space_data)
    scale = _ui_scale(context)
    persp = rv3d.perspective_matrix
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    face_hit = None
    for ob, c in cs:
        h = c.ray(origin, direction)
        if h is not None and (face_hit is None or h[0] < face_hit[0]):
            face_hit = (h[0], ob, c, h[1])
    best = None
    for ob, c in cs:
        xy, front = preselect.project(c.co, persp, region.width, region.height)
        if not edges_only:
            i = preselect.pick_vert(xy, c.vok & front, mouse, VERT_PX * scale,
                                    lambda i, c=c: not _occluded(cs, region, rv3d, Vector(c.co[i]), xray))
            if i is not None:
                d = math.hypot(xy[i, 0] - mouse[0], xy[i, 1] - mouse[1])
                if best is None or best[0] != 'VERT' or d < best[1]:
                    best = ('VERT', d, ob, i)
    if best is not None:
        return best[2].name, ('VERT', best[3])
    for ob, c in cs:
        if not len(c.edges):
            continue
        xy, front = preselect.project(c.co, persp, region.width, region.height)
        ok = c.eok & front[c.edges[:, 0]] & front[c.edges[:, 1]]

        def vis(i, t, c=c):
            a, b = c.co[c.edges[i, 0]], c.co[c.edges[i, 1]]
            return not _occluded(cs, region, rv3d, Vector(a + (b - a) * t), xray)
        i = preselect.pick_edge(xy, c.edges, ok, mouse, EDGE_PX * scale, vis)
        if i is not None:
            d, _t = preselect.segment_distance(mouse, xy[c.edges[[i], 0]], xy[c.edges[[i], 1]])
            d = float(np.asarray(d)[0])
            if best is None or d < best[1]:
                best = ('EDGE', d, ob, i, c)
    if best is not None:
        _k, _d, ob, i, c = best
        a, b = Vector(c.co[c.edges[i, 0]]), Vector(c.co[c.edges[i, 1]])
        return ob.name, ('EDGE', i, ray_edge_t(region, rv3d, a, b, mouse))
    if face_hit is not None and not edges_only:
        dist, ob, c, fi = face_hit
        world = origin + direction.normalized() * dist
        return ob.name, ('FACE', fi, tuple(c.inv @ world))
    return None


def snapped(point, step, shift):
    """An edge point snapped to the Snap Step % while Shift is held."""
    if shift and point is not None and point[0] == 'EDGE':
        return ('EDGE', point[1], mesh_tools.snap_factor(point[2], step))
    return point


def world_of(ob, point):
    bm = bmesh.from_edit_mesh(ob.data)
    mw = ob.matrix_world
    if point[0] == 'VERT':
        bm.verts.ensure_lookup_table()
        return mw @ bm.verts[point[1]].co
    if point[0] == 'EDGE':
        bm.edges.ensure_lookup_table()
        e = bm.edges[point[1]]
        return mw @ e.verts[0].co.lerp(e.verts[1].co, point[2])
    return mw @ Vector(point[2])


# --- live state (drawn by _draw) ---------------------------------------------------------------------

STATE = {"ob": None, "points": [], "hover": None, "hover_ok": True, "loop": None, "slice": None, "ctrl": False}


def reset_state():
    STATE.update(ob=None, points=[], hover=None, hover_ok=True, loop=None, slice=None, ctrl=False)


def tool_active(context):
    return context.mode == 'EDIT_MESH' and preselect.tool_id(context) == TOOL


def _settings(context):
    return mesh_tools.settings(context)


def _update_hover(context, region, rv3d, mouse, ctrl, shift):
    s = _settings(context)
    STATE["ctrl"] = ctrl
    STATE["loop"] = None
    STATE["hover"] = None
    STATE["hover_ok"] = True
    if ctrl and not STATE["points"]:
        hit = pick(context, region, rv3d, mouse, edges_only=True)
        if hit is not None:
            name, p = hit
            t = mesh_tools.snap_factor(p[2], s.snap_step, inner=True) if shift else p[2]
            STATE["loop"] = (name, p[1], t)
        return
    hit = pick(context, region, rv3d, mouse, only=STATE["ob"])
    if hit is None:
        return
    name, p = hit
    p = snapped(p, s.snap_step, shift)
    ob = bpy.data.objects.get(name)
    if ob is None:
        return
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    p = normalize(bm, p)
    STATE["hover"] = (name, p)
    STATE["hover_ok"] = accepts(bm, STATE["points"], p)


# --- drawing --------------------------------------------------------------------------------------------

_handles = []


def _shader_lines(region, pts, rgb, px):
    if len(pts) < 2:
        return
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", px)
    shader.uniform_float("color", (*rgb, 1.0))
    batch_for_shader(shader, 'LINES', {"pos": pts}).draw(shader)


def _shader_points(pts, rgb, px):
    if not pts:
        return
    shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
    gpu.state.point_size_set(px)
    shader.uniform_float("color", (*rgb, 1.0))
    batch_for_shader(shader, 'POINTS', {"pos": pts}).draw(shader)


def _draw_view():
    context = bpy.context
    try:
        if not tool_active(context):
            return
        scale = _ui_scale(context)
        region = context.region
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        if STATE["loop"] is not None:
            name, ei, t = STATE["loop"]
            ob = bpy.data.objects.get(name)
            if ob is not None:
                mw = ob.matrix_world
                segs = loop_segments(bmesh.from_edit_mesh(ob.data), ei, t)
                _shader_lines(region, [tuple(mw @ p) for s in segs for p in s], LOOP_RGB, LINE_PX * scale)
        ob = bpy.data.objects.get(STATE["ob"]) if STATE["ob"] else None
        pts = [tuple(world_of(ob, p)) for p in STATE["points"]] if ob is not None else []
        if len(pts) > 1:
            _shader_lines(region, [q for a, b in zip(pts, pts[1:]) for q in (a, b)], POINT_RGB, LINE_PX * scale)
        hover = STATE["hover"]
        if hover is not None:
            hob = bpy.data.objects.get(hover[0])
            if hob is not None:
                hp = tuple(world_of(hob, hover[1]))
                rgb = PREVIEW_RGB if STATE["hover_ok"] else REJECT_RGB
                if pts and STATE["hover_ok"]:
                    _shader_lines(region, [pts[-1], hp], PREVIEW_RGB, LINE_PX * scale)
                _shader_points([hp], rgb, POINT_PX * scale)
        _shader_points(pts, POINT_RGB, POINT_PX * scale)
        gpu.state.blend_set('NONE')
    except (ReferenceError, AttributeError, IndexError, ValueError):
        pass


def _label_points():
    out = []
    hover = STATE["hover"]
    for name, p in ([(STATE["ob"], q) for q in STATE["points"][-1:]] if STATE["ob"] else []) + (
            [hover] if hover is not None else []):
        if p[0] == 'EDGE':
            out.append((name, p, f"{p[2] * 100:.0f}%"))
    if STATE["loop"] is not None:
        name, ei, t = STATE["loop"]
        out.append((name, ('EDGE', ei, t), f"{t * 100:.0f}%"))
    return out


def _draw_pixel():
    context = bpy.context
    try:
        if not tool_active(context):
            return
        import blf
        region, rv3d = context.region, context.region_data
        scale = _ui_scale(context)
        font = 0
        blf.size(font, 12 * scale)
        for name, p, text in _label_points():
            ob = bpy.data.objects.get(name)
            if ob is None:
                continue
            xy = view3d_utils.location_3d_to_region_2d(region, rv3d, world_of(ob, p))
            if xy is None:
                continue
            blf.color(font, *POINT_RGB, 1.0)
            blf.position(font, xy.x + 8 * scale, xy.y + 8 * scale, 0)
            blf.draw(font, text)
        sl = STATE["slice"]
        if sl is not None:
            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
            shader.uniform_float("viewportSize", (region.width, region.height))
            shader.uniform_float("lineWidth", LINE_PX * scale)
            shader.uniform_float("color", (*POINT_RGB, 1.0))
            batch_for_shader(shader, 'LINES', {"pos": [(*sl[0], 0.0), (*sl[1], 0.0)]}).draw(shader)
    except (ReferenceError, AttributeError, IndexError, ValueError):
        pass


def _redraw(context):
    if context.area is not None:
        context.area.tag_redraw()


# --- operators ------------------------------------------------------------------------------------------

def _view_ok(context):
    r = context.region
    return r is not None and r.type == 'WINDOW' and context.region_data is not None


class ALLSET_OT_multi_cut_hover(bpy.types.Operator):
    """Multi-Cut hover preview: the point / loop under the mouse (passes the event on)"""
    bl_idname = "allset.multi_cut_hover"
    bl_label = "Multi-Cut Preview"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        if _view_ok(context) and not STATE["points"] and STATE["slice"] is None:
            ctrl = event.ctrl or (event.type in {'LEFT_CTRL', 'RIGHT_CTRL'} and event.value == 'PRESS')
            if event.type in {'LEFT_CTRL', 'RIGHT_CTRL'} and event.value == 'RELEASE':
                ctrl = False
            shift = event.shift or (event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'} and event.value == 'PRESS')
            if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'} and event.value == 'RELEASE':
                shift = False
            try:
                _update_hover(context, context.region, context.region_data,
                              (event.mouse_region_x, event.mouse_region_y), ctrl, shift)
            except (ReferenceError, ValueError, IndexError):
                pass
            _redraw(context)
        return {'PASS_THROUGH'}


class ALLSET_OT_multi_cut(bpy.types.Operator):
    """Maya Multi-Cut: click edges / faces / vertices to place cut points, Enter or right-click to cut.
    Ctrl+click = edge loop, Shift = Snap Step %, Backspace = remove the last point, drag across faces = slice"""
    bl_idname = "allset.multi_cut"
    bl_label = "Multi-Cut"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.area is not None and context.area.type == 'VIEW_3D'

    # -- helpers
    def _ob(self):
        return bpy.data.objects.get(STATE["ob"]) if STATE["ob"] else None

    def _bm(self, name):
        ob = bpy.data.objects.get(name)
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        return ob, bm

    def _mouse(self, event):
        return (event.mouse_region_x, event.mouse_region_y)

    def _add_point(self, context, hit, shift):
        name, p = hit
        if STATE["ob"] is not None and name != STATE["ob"]:
            return False
        _ob, bm = self._bm(name)
        p = normalize(bm, snapped(p, _settings(context).snap_step, shift))
        if not accepts(bm, STATE["points"], p):
            if STATE["points"]:
                self.report({'WARNING'}, "Multi-Cut: place the next point on a face of the last point")
            return False
        STATE["ob"] = name
        STATE["points"].append(p)
        return True

    def _complete(self, context):
        ob = self._ob()
        points = list(STATE["points"])
        if ob is None or len(points) < 2:
            return False
        s = _settings(context)
        bm = bmesh.from_edit_mesh(ob.data)
        edges = cut(bm, points, s.subdivisions, math.radians(s.smoothing_angle))
        bmesh.update_edit_mesh(ob.data)
        preselect.invalidate()
        return bool(edges)

    def _end(self, context, result):
        reset_state()
        _redraw(context)
        context.workspace.status_text_set(None)
        return result

    def _status(self, context):
        context.workspace.status_text_set(
            "Multi-Cut: click edges / faces to place points, Enter or right-click to cut, Backspace: remove the "
            "last point, Shift: Snap Step, Ctrl+click: edge loop, Esc: cancel")

    # -- slice
    def _slice_plane(self, context, a, b):
        region, rv3d = context.region, context.region_data
        ob = self._slice_ob or next((o for o in context.objects_in_mode_unique_data if o.type == 'MESH'), None)
        if ob is None:
            return None
        depth = ob.matrix_world.translation
        pa = view3d_utils.region_2d_to_location_3d(region, rv3d, a, depth)
        pb = view3d_utils.region_2d_to_location_3d(region, rv3d, b, depth)
        view = view3d_utils.region_2d_to_vector_3d(region, rv3d, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        n = (pb - pa).cross(view)
        if n.length < 1e-9:
            return None
        return ob, pa, n.normalized()

    def _do_slice(self, context, objects, plane_co, plane_no):
        s = _settings(context)
        from . import units
        done = 0
        rv3d = context.region_data
        view_dir = rv3d.view_rotation @ Vector((0, 0, -1))
        for ob in objects:
            mw = ob.matrix_world
            inv = mw.inverted_safe()
            bm = bmesh.from_edit_mesh(ob.data)
            co = inv @ plane_co
            no = (mw.to_3x3().transposed() @ plane_no).normalized()
            faces = None
            if s.ignore_backfaces:
                local_view = (inv.to_3x3() @ view_dir).normalized()
                faces = [f for f in bm.faces if not f.hide and f.normal.dot(local_view) < 0]
            else:
                faces = [f for f in bm.faces if not f.hide]
            extract = None
            if s.extract_faces:
                o = Vector(s.extract_offset) * units.maya_unit(context.scene)
                extract = inv.to_3x3() @ Vector((o.x, -o.z, o.y))   # Maya Y-up -> Blender Z-up
            edges = slice_mesh(bm, co, no, faces, delete=s.delete_faces, extract=extract)
            bmesh.update_edit_mesh(ob.data)
            done += len(edges)
        preselect.invalidate()
        return done

    # -- invoke / modal
    def invoke(self, context, event):
        if not _view_ok(context):
            return {'PASS_THROUGH'}
        if event.alt:
            return {'PASS_THROUGH'}      # Maya Alt+drag = navigation
        reset_state()
        region, rv3d = context.region, context.region_data
        mouse = self._mouse(event)
        s = _settings(context)
        self._slice_ob = None
        if event.ctrl:
            # Ctrl+click / Ctrl+Shift+click / Ctrl+MMB are allset.multicut_loop items ahead of this one in the tool
            # keymap (their own undo step + Adjust Last Operation Position); off an edge they pass through to here.
            return {'PASS_THROUGH'}
        if s.slice_plane != 'NONE':
            hit = pick(context, region, rv3d, mouse)
            if hit is None:
                return {'PASS_THROUGH'}
            ob = bpy.data.objects.get(hit[0])
            n = self._do_slice(context, [ob], world_of(ob, hit[1]), PLANE_NORMALS[s.slice_plane])
            return self._end(context, {'FINISHED'} if n else {'CANCELLED'})
        else:
            hit = pick(context, region, rv3d, mouse)
            self._press = mouse
            if hit is not None and hit[1][0] in {'VERT', 'EDGE'}:
                self._add_point(context, hit, event.shift)
                self._state = 'DRAG'
            elif hit is not None:
                self._face_hit = hit
                self._slice_ob = bpy.data.objects.get(hit[0])
                self._state = 'PRESS'
            else:
                self._face_hit = None
                self._state = 'PRESS'
        context.window_manager.modal_handler_add(self)
        self._status(context)
        _redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not tool_active(context) or not _view_ok(context):
            return self._end(context, {'CANCELLED'})
        mouse = self._mouse(event)
        region, rv3d = context.region, context.region_data
        s = _settings(context)
        moving = event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}
        state = self._state

        if state == 'PRESS':
            if moving and math.hypot(mouse[0] - self._press[0], mouse[1] - self._press[1]) > SLICE_PX * _ui_scale(
                    context) and not STATE["points"]:
                self._state = 'SLICE'
                STATE["slice"] = (self._press, mouse)
                _redraw(context)
            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                if self._face_hit is not None:
                    self._add_point(context, self._face_hit, False)
                if not STATE["points"]:
                    return self._end(context, {'CANCELLED'})
                self._state = 'POINTS'
                _redraw(context)
            return {'RUNNING_MODAL'}

        if state == 'SLICE':
            if moving:
                STATE["slice"] = (self._press, mouse)
                _redraw(context)
            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                plane = self._slice_plane(context, self._press, mouse)
                n = 0
                if plane is not None:
                    _ob, co, no = plane
                    obs = [o for o in context.objects_in_mode_unique_data if o.type == 'MESH']
                    n = self._do_slice(context, obs, co, no)
                return self._end(context, {'FINISHED'} if n else {'CANCELLED'})
            elif event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
                return self._end(context, {'CANCELLED'})
            return {'RUNNING_MODAL'}

        if state == 'DRAG':
            if moving and STATE["points"]:
                p = STATE["points"][-1]
                ob, bm = self._bm(STATE["ob"])
                mw = ob.matrix_world
                if p[0] == 'EDGE':
                    e = bm.edges[p[1]]
                    t = ray_edge_t(region, rv3d, mw @ e.verts[0].co, mw @ e.verts[1].co, mouse)
                    q = snapped(('EDGE', p[1], t), s.snap_step, event.shift)
                    q = ('EDGE', p[1], min(max(q[2], 0.0), 1.0))
                    if len(STATE["points"]) < 2 or accepts(bm, STATE["points"][:-1], normalize(bm, q)):
                        STATE["points"][-1] = q
                _redraw(context)
            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                if STATE["points"]:
                    ob, bm = self._bm(STATE["ob"])
                    STATE["points"][-1] = normalize(bm, STATE["points"][-1])
                self._state = 'POINTS' if STATE["points"] else 'PRESS'
                if not STATE["points"]:
                    return self._end(context, {'CANCELLED'})
            return {'RUNNING_MODAL'}

        # POINTS: waiting for the next point / completion
        if moving:
            try:
                _update_hover(context, region, rv3d, mouse, False, event.shift)
            except (ReferenceError, ValueError, IndexError):
                pass
            _redraw(context)
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type in {'RET', 'NUMPAD_ENTER', 'RIGHTMOUSE'}:
            ok = self._complete(context)
            return self._end(context, {'FINISHED'} if ok else {'CANCELLED'})
        if event.value == 'PRESS' and event.type == 'BACK_SPACE':
            if STATE["points"]:
                STATE["points"].pop()
            if not STATE["points"]:
                STATE["ob"] = None
            _redraw(context)
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type == 'ESC':
            return self._end(context, {'CANCELLED'})
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and not event.alt:
            hit = pick(context, region, rv3d, mouse, only=STATE["ob"])
            if hit is not None and self._add_point(context, hit, event.shift):
                STATE["hover"] = None
                self._state = 'DRAG' if hit[1][0] in {'VERT', 'EDGE'} else 'POINTS'
            _redraw(context)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE' and not event.alt:
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}     # navigation (Alt+drag, MMB, wheel), view keys


class ALLSET_OT_multi_cut_exit(bpy.types.Operator):
    """Leave the Multi-Cut tool for the Select tool (Maya Esc / Q in the tool)"""
    bl_idname = "allset.multi_cut_exit"
    bl_label = "Exit Multi-Cut"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return tool_active(context)

    def execute(self, context):
        reset_state()
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box", space_type='VIEW_3D')
        return {'FINISHED'}


class ALLSET_OT_multi_cut_reset(bpy.types.Operator):
    """Reset the Multi-Cut options to their default values, like Maya (Tool Settings > Reset Tool)"""
    bl_idname = "allset.multi_cut_reset"
    bl_label = "Reset Multi-Cut"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        reset_settings(_settings(context))
        return {'FINISHED'}


SETTINGS = ("snap_step", "smoothing_angle", "edge_flow", "edge_flow_adjust", "subdivisions", "ignore_backfaces",
            "delete_faces", "extract_faces", "extract_offset", "slice_plane")


def reset_settings(s):
    for name in SETTINGS:
        s.property_unset(name)


classes = (ALLSET_OT_multi_cut_hover, ALLSET_OT_multi_cut, ALLSET_OT_multi_cut_exit, ALLSET_OT_multi_cut_reset)


def register_handlers():
    if not _handles:
        _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw_view, (), 'WINDOW', 'POST_VIEW'))
        _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw_pixel, (), 'WINDOW', 'POST_PIXEL'))


def unregister_handlers():
    while _handles:
        bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), 'WINDOW')
    reset_state()
