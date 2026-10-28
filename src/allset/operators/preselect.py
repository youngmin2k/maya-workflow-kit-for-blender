# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya pre-selection highlight in mesh edit mode (docs/steps/step_30.md, step_74.md 「계획」).

Maya highlights the component under the mouse before you click (``preSelectHilite true``,
research/maya/interaction.md:73, defaults.json:96), following the select mode, also while the
Move / Rotate / Scale tool is active (measured in research/maya/screens/pre/): a vertex = 5 px red
square, an edge = 2 px red line (an edge also near its vertices), a face = red outline + red stipple.
Maya 2022 doesn't highlight objects in object mode (pre_01), so neither does the kit,
except for component targets while editing a custom pivot.

Blender's ``GIZMO_GT_mesh_preselect_elem_3d`` (step 30) picks the nearest vertex in every select
mode (measured, step_74.md), so this is a Python gizmo with its own picking:

- ``pick_*`` (numpy, no bpy): nearest vertex / edge within ``RADIUS_PX`` on screen that the
  ``visible`` callback accepts; a face = the one under the cursor (BVH ray cast).
- Occlusion: a per-object ``BVHTree`` of the visible faces, cached until the next depsgraph update;
  X-ray (the shading flag) turns it off.
- With a transform tool, ``test_select`` declines over the manipulator's handles (a Python gizmo's
  test_select wins the hover over them, step 30).
- The gizmo has no invoke / modal, so a click goes on to the select tool (GUI test).
"""

import math

import bpy
import gpu
import numpy as np
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from mathutils.bvhtree import BVHTree

MODES = {'EDIT_MESH'}
SELECT_TOOLS = ("builtin.select", "allset.target_weld_tool", "allset.cut_sew_tool")   # step 79: the edge a press cuts
TRANSFORM_TOOLS = {"builtin.move": 'TRANSLATE', "builtin.scale": 'RESIZE', "builtin.rotate": 'ROTATE',
                   "builtin.transform": 'TRANSFORM'}

# --- Maya measurements (step_74.md) ------------------------------------------------------------------
RGB = (1.0, 0.0, 0.0)               # preselect_hilite_component (research/maya/colors.json)
VERT_PX = 5.0
LINE_PX = 2.0
FACE_FILL = (0.85, 0.26, 0.25, 0.35)  # the #d84240 stipple seen as a fill [I]
RADIUS_PX = 16.0                    # MT_preSelectSize 16 (defaults.json:99) [I]
HANDLE_PX = 12.0                    # keep the hover on a manipulator handle this close
ROTATE_RING = 1.25                  # Rotate (Blender's gizmo): disc of gizmo_size / 2 x this

_last = []    # the live group (tests read its gizmo)
_cache = {}   # object pointer -> MeshCache


# --- pure helpers (tests/test_step74_preselect.py) ----------------------------------------------------

def project(co, persp, width, height):
    """Screen xy (N x 2) and an in-front mask of world points ``co`` (N x 3) under ``persp`` (4 x 4)."""
    co = np.asarray(co, dtype=np.float64).reshape(-1, 3)
    h = np.hstack([co, np.ones((len(co), 1))]) @ np.asarray(persp, dtype=np.float64).T
    w = h[:, 3]
    front = w > 1e-9
    w = np.where(front, w, 1.0)
    xy = np.empty((len(co), 2))
    xy[:, 0] = (h[:, 0] / w + 1.0) * 0.5 * width
    xy[:, 1] = (h[:, 1] / w + 1.0) * 0.5 * height
    return xy, front


def segment_distance(p, a, b):
    """Distances from point ``p`` to segments a[i]-b[i] (N x 2 each) and the segment parameters t."""
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    d = b - a
    ll = (d * d).sum(axis=1)
    t = np.where(ll > 1e-12, ((np.asarray(p) - a) * d).sum(axis=1) / np.where(ll > 1e-12, ll, 1.0), 0.0)
    t = np.clip(t, 0.0, 1.0)
    q = a + d * t[:, None]
    return np.hypot(q[:, 0] - p[0], q[:, 1] - p[1]), t


def pick_vert(xy, ok, mouse, radius, visible):
    """Index of the nearest ``ok`` point within ``radius`` that ``visible(i)`` accepts, or None."""
    if len(xy) == 0:
        return None
    dist = np.hypot(xy[:, 0] - mouse[0], xy[:, 1] - mouse[1])
    for i in np.argsort(dist):
        if dist[i] > radius:
            break
        if ok[i] and visible(int(i)):
            return int(i)
    return None


def pick_edge(xy, edges, ok, mouse, radius, visible, fallback=()):
    """Index of the nearest ``ok`` edge within ``radius`` (screen) that ``visible(i, t)`` accepts; else the
    nearest of ``fallback`` (the edges of the face under the cursor); else None."""
    edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
    if len(edges) == 0:
        return None
    dist, t = segment_distance(mouse, xy[edges[:, 0]], xy[edges[:, 1]])
    for i in np.argsort(dist):
        if dist[i] > radius:
            break
        if ok[i] and visible(int(i), float(t[i])):
            return int(i)
    fallback = [i for i in fallback if ok[i]]
    if fallback:
        return int(min(fallback, key=lambda i: dist[i]))
    return None


def near_handles(mouse, center, tips, center_half, reach):
    """True when ``mouse`` is on a manipulator: within ``center_half`` + ``reach`` of ``center`` or within
    ``reach`` of an axis line center -> tip (screen points)."""
    if center is None:
        return False
    if math.hypot(mouse[0] - center[0], mouse[1] - center[1]) <= center_half + reach:
        return True
    if not tips:
        return False
    a = np.repeat(np.asarray([center], dtype=np.float64), len(tips), axis=0)
    dist, _t = segment_distance(mouse, a, np.asarray(tips, dtype=np.float64))
    return bool((dist <= reach).any())


# --- per-object cache ---------------------------------------------------------------------------------

class MeshCache:
    """World vertex positions, edges, visible-face BVH and (lazily) selection of one mesh.
    Rebuilt after geometry / transform updates only (selection updates keep it, step_74.md)."""

    def __init__(self, ob):
        import bmesh
        self.ob_ptr = ob.as_pointer()
        self.name = ob.name
        self.editing = ob.mode == 'EDIT'
        self.bm = bm = bmesh.from_edit_mesh(ob.data) if self.editing else bmesh.new()
        if not self.editing:
            bm.from_mesh(ob.data)
            bm.normal_update()
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        self.mw = ob.matrix_world.copy()
        self.inv = self.mw.inverted_safe()
        m = np.array(self.mw, dtype=np.float64)
        local = np.array([v.co[:] for v in bm.verts], dtype=np.float64).reshape(-1, 3)
        self.co = local @ m[:3, :3].T + m[:3, 3]
        self.vok = np.array([not v.hide for v in bm.verts], dtype=bool)
        self.edges = np.array([(e.verts[0].index, e.verts[1].index) for e in bm.edges],
                              dtype=np.int64).reshape(-1, 2)
        self.eok = np.array([not e.hide for e in bm.edges], dtype=bool)
        hidden = [f.index for f in bm.faces if f.hide]
        if not hidden:
            self.bvh_map = None                         # BVH index = face index
            self.bvh = BVHTree.FromBMesh(bm) if len(bm.faces) else None
        else:
            vis = [f.index for f in bm.faces if not f.hide]
            self.bvh_map = vis
            self.bvh = BVHTree.FromPolygons([v.co.copy() for v in bm.verts],
                                            [self.face_verts(i) for i in vis]) if vis else None
        self._sel = None

    def __del__(self):
        bm = getattr(self, "bm", None)
        if not getattr(self, "editing", True) and bm is not None and bm.is_valid:
            bm.free()

    def face_verts(self, i):
        return tuple(v.index for v in self.bm.faces[i].verts)

    def face_edges(self, i):
        return tuple(e.index for e in self.bm.faces[i].edges)

    def face_ok(self, i):
        return not self.bm.faces[i].hide

    def selection(self):
        """(world points of the selected vertices, active element centre or None), cached."""
        if self._sel is None:
            import bmesh
            bm, mw = self.bm, self.mw
            if not self.editing:
                self._sel = ([mw.translation.copy()], mw.translation.copy())
                return self._sel
            pts = [mw @ v.co for v in bm.verts if v.select and not v.hide]
            el, active = bm.select_history.active, None
            if isinstance(el, bmesh.types.BMVert):
                active = mw @ el.co
            elif isinstance(el, bmesh.types.BMEdge):
                active = mw @ ((el.verts[0].co + el.verts[1].co) / 2)
            elif isinstance(el, bmesh.types.BMFace):
                active = mw @ el.calc_center_median()
            self._sel = (pts, active)
        return self._sel

    def ray(self, origin, direction):
        """(world distance, face index) of the first visible face along a world ray, or None."""
        if self.bvh is None:
            return None
        lo = self.inv @ origin
        ld = (self.inv.to_3x3() @ direction).normalized()
        loc, _n, idx, _d = self.bvh.ray_cast(lo, ld)
        if loc is None:
            return None
        return (self.mw @ loc - origin).length, (idx if self.bvh_map is None else self.bvh_map[idx])


def caches(context):
    out = []
    objects = context.selected_objects if context.mode == 'OBJECT' else context.objects_in_mode_unique_data or ()
    for ob in objects:
        if ob is None or ob.type != 'MESH':
            continue
        if context.mode == 'OBJECT':
            space = getattr(context, "space_data", None)
            viewport = {"viewport": space} if space is not None and space.type == 'VIEW_3D' else {}
            if not ob.visible_get(**viewport):
                continue
        c = _cache.get(ob.as_pointer())
        if c is None or c.name != ob.name or c.editing != (ob.mode == 'EDIT'):
            c = _cache[ob.as_pointer()] = MeshCache(ob)
        out.append((ob, c))
    return out


@bpy.app.handlers.persistent
def invalidate(_scene=None, depsgraph=None):
    """depsgraph_update_post: drop the caches on a geometry / transform change; a selection-only change
    keeps them and only forgets the selection."""
    if depsgraph is not None:
        for u in depsgraph.updates:
            if isinstance(u.id, (bpy.types.Mesh, bpy.types.Object)) and (u.is_updated_geometry or u.is_updated_transform):
                break
        else:
            for c in _cache.values():
                c._sel = None
            return
    _cache.clear()


# --- policy -------------------------------------------------------------------------------------------

def tool_id(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except (AttributeError, TypeError):
        return None
    return tool.idname if tool is not None else None


def _enabled(context):
    from .. import preferences
    try:
        if not preferences.get().preselect_highlight:
            return False
    except KeyError:
        return False
    from .pivot_menu import pivot_editing
    if context.mode in {'OBJECT', 'EDIT_MESH'} and pivot_editing(context):
        return True
    if context.mode not in MODES:
        return False
    tid = tool_id(context)
    return tid is not None and (tid.startswith(SELECT_TOOLS) or tid in TRANSFORM_TOOLS)


def _xray(space):
    shading = space.shading
    return shading.show_xray_wireframe if shading.type == 'WIREFRAME' else shading.show_xray


def pivot_picking(context):
    from .pivot_menu import pivot_editing
    return context.mode in {'OBJECT', 'EDIT_MESH'} and pivot_editing(context)


def _handles_block(context, region, rv3d, mouse, cs):
    """The mouse is over the transform manipulator of the active tool."""
    from ..ui import manipulator
    kind = manipulator.tool_kind(context) or TRANSFORM_TOOLS.get(tool_id(context))
    if kind is None:
        return False
    sels = [c.selection() for _ob, c in cs]
    pts = [p for s_ in sels for p in s_[0]]
    if not pts:
        return False
    act = next((s_[1] for s_ in sels if s_[1] is not None), None)
    ts = context.scene.tool_settings
    center = manipulator.center_of(pts, act, ts.transform_pivot_point, context.scene.cursor.location)
    c2 = view3d_utils.location_3d_to_region_2d(region, rv3d, center)
    if c2 is None:
        return False
    scale = context.preferences.system.ui_scale or 1.0
    size = context.preferences.view.gizmo_size
    if kind in ('ROTATE', 'TRANSFORM'):
        return math.hypot(mouse[0] - c2.x, mouse[1] - c2.y) <= size / 2.0 * scale * ROTATE_RING
    length_px = manipulator.ARROW_PX * size / 75.0 * scale
    right = rv3d.view_rotation @ Vector((1.0, 0.0, 0.0))
    p1 = view3d_utils.location_3d_to_region_2d(region, rv3d, center + right)
    px_per_world = (p1 - c2).length if p1 is not None else 0.0
    tips = []
    if px_per_world > 1e-9:
        frame = manipulator.axes_of(context, 'CURSOR' if context.mode == 'EDIT_MESH' and pivot_picking(context)
                                     else manipulator.slot_type(context.scene, kind), rv3d)
        for i in range(3):
            t = view3d_utils.location_3d_to_region_2d(region, rv3d, center + frame.col[i] * (length_px / px_per_world))
            if t is not None:
                tips.append((t.x, t.y))
    half = length_px * manipulator.CENTER_HALF
    return near_handles(mouse, (c2.x, c2.y), tips, half, HANDLE_PX * scale)


def _extrude_block(context, region, rv3d, mouse):
    """The mouse is over the polyExtrudeFace arrow or the In-View Editor box (step 65): like the manipulator's
    handles, they must get the click, not the hovered face under them (step 97)."""
    from ..ui import in_view
    try:
        if not in_view.manip_visible(context):
            return False
        ob, rec = in_view.record(context)
        frame = in_view.cap_frame(ob, rec) if rec is not None else None
    except (ReferenceError, AttributeError):
        return False
    if frame is None:
        return False
    _r, lay = in_view.current_layout(context)
    if lay is not None and any(x0 <= mouse[0] <= x1 and y0 <= mouse[1] <= y1
                               for x0, y0, x1, y1 in (lay["box"], lay["title"])):
        return True
    # step 151: every handle of Maya's extrude manipulator (arrows, scale cubes, plane handles, centre square)
    return in_view.handles_hit(context, region, rv3d, mouse, HANDLE_PX * (context.preferences.system.ui_scale or 1.0))


def pick(context, region, rv3d, mouse):
    """(object pointer, 'VERT' / 'EDGE' / 'FACE', index) under ``mouse`` (region pixels), or None."""
    cs = caches(context)
    if not cs or _handles_block(context, region, rv3d, mouse, cs) or _extrude_block(context, region, rv3d, mouse):
        return None
    ts = context.tool_settings
    multi = pivot_picking(context)
    vmode, emode, fmode = (True, True, True) if multi else tuple(ts.mesh_select_mode)
    xray = _xray(context.space_data)
    scale = context.preferences.system.ui_scale or 1.0
    radius = RADIUS_PX * scale
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    hit = None   # (distance, cache, face index)
    for _ob, c in cs:
        h = c.ray(origin, direction)
        if h is not None and (hit is None or h[0] < hit[0]):
            hit = (h[0], c, h[1])

    def occluded(p):
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

    if fmode and not (vmode or emode):
        return None if hit is None else (hit[1].ob_ptr, 'FACE', hit[2])
    best = None   # (screen distance, result)
    persp = rv3d.perspective_matrix
    for _ob, c in cs:
        xy, front = project(c.co, persp, region.width, region.height)
        if vmode:
            i = pick_vert(xy, c.vok & front, mouse, radius, lambda i, c=c: not occluded(Vector(c.co[i])))
            if i is not None:
                d = math.hypot(xy[i, 0] - mouse[0], xy[i, 1] - mouse[1])
                if best is None or best[1][1] != 'VERT' or d < best[0]:
                    best = (d, (c.ob_ptr, 'VERT', i))
        if emode and (not vmode or multi) and (best is None or best[1][1] != 'VERT'):
            fallback = c.face_edges(hit[2]) if not multi and hit is not None and hit[1] is c else ()
            ok = c.eok & front[c.edges[:, 0]] & front[c.edges[:, 1]] if len(c.edges) else c.eok

            def vis(i, t, c=c):
                a, b = c.co[c.edges[i, 0]], c.co[c.edges[i, 1]]
                return not occluded(Vector(a + (b - a) * t))
            i = pick_edge(xy, c.edges, ok, mouse, radius, vis, fallback)
            if i is not None:
                d, _t = segment_distance(mouse, xy[c.edges[[i], 0]], xy[c.edges[[i], 1]])
                d = float(d[0]) if i not in fallback else radius + 1.0
                if best is None or d < best[0]:
                    best = (d, (c.ob_ptr, 'EDGE', i))
    if best is not None:
        return best[1]
    return (hit[1].ob_ptr, 'FACE', hit[2]) if multi and hit is not None else None


# --- the gizmo ----------------------------------------------------------------------------------------

def _cache_of(ptr):
    return _cache.get(ptr)


class ALLSET_GT_preselect(bpy.types.Gizmo):
    bl_idname = "ALLSET_GT_preselect"

    def setup(self):
        self.target = None          # (object pointer, kind, index)
        self.vert_index = self.edge_index = self.face_index = -1

    def _set(self, target):
        self.target = target
        self.vert_index = self.edge_index = self.face_index = -1
        if target is not None:
            setattr(self, {'VERT': "vert_index", 'EDGE': "edge_index", 'FACE': "face_index"}[target[1]], target[2])

    def test_select(self, context, location):
        region, rv3d = context.region, context.region_data
        try:
            target = pick(context, region, rv3d, (float(location[0]), float(location[1])))
        except ReferenceError:      # the edit mesh changed under the cache
            invalidate()
            target = None
        if target != self.target:
            self._set(target)
            region.tag_redraw()
        return -1 if target is None else 0

    def draw(self, context):
        if not self.is_highlight or self.target is None:
            return
        c = _cache_of(self.target[0])
        if c is None:
            return
        kind, i = self.target[1], self.target[2]
        scale = context.preferences.system.ui_scale or 1.0
        region = context.region
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('ALPHA')
        if kind == 'VERT':
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            gpu.state.point_size_set(VERT_PX * scale)
            batch = batch_for_shader(shader, 'POINTS', {"pos": [tuple(c.co[i])]})
            shader.uniform_float("color", (*RGB, 1.0))
            batch.draw(shader)
            gpu.state.point_size_set(1.0)
        else:
            if kind == 'EDGE':
                lines = [tuple(c.co[c.edges[i, 0]]), tuple(c.co[c.edges[i, 1]])]
            else:
                verts = [tuple(c.co[v]) for v in c.face_verts(i)]
                fill = gpu.shader.from_builtin('UNIFORM_COLOR')
                tris = [(0, k, k + 1) for k in range(1, len(verts) - 1)]
                fill.uniform_float("color", FACE_FILL)
                batch_for_shader(fill, 'TRIS', {"pos": verts}, indices=tris).draw(fill)
                lines = []
                for k in range(len(verts)):
                    lines += [verts[k], verts[(k + 1) % len(verts)]]
            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
            shader.uniform_float("viewportSize", (region.width, region.height))
            shader.uniform_float("lineWidth", LINE_PX * scale)
            shader.uniform_float("color", (*RGB, 1.0))
            batch_for_shader(shader, 'LINES', {"pos": lines}).draw(shader)
        gpu.state.blend_set('NONE')


def gizmo():
    """The pre-selection gizmo of the last set-up group, or None."""
    try:
        return _last[0].gz if _last else None
    except ReferenceError:
        return None


class ALLSET_GGT_preselect(bpy.types.GizmoGroup):
    bl_idname = "ALLSET_GGT_preselect"
    bl_label = "Maya Pre-selection Highlight"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SELECT'}

    @classmethod
    def poll(cls, context):
        return _enabled(context)

    def setup(self, context):
        self.gz = self.gizmos.new(ALLSET_GT_preselect.bl_idname)
        self.gz.hide_keymap = True   # a click goes to the select tool, not to a gizmo tweak (step 74)
        _last[:] = [self]


classes = (ALLSET_GT_preselect, ALLSET_GGT_preselect)


def register_handlers():
    if invalidate not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(invalidate)


def clear():
    _last.clear()
    _cache.clear()
    if invalidate in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(invalidate)
