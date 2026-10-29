# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Create Polygon and Append to Polygon tools (docs/steps/step_144_poly.md 「계획」 3-4, GitHub #30).

- Create Polygon (Mesh Tools > Create Polygon): the kit tool ``allset.create_polygon_tool`` (object and edit mode) runs
  ``allset.create_polygon``: click = a point (Maya's construction plane: the ground in a perspective view, the view
  plane through the origin in an orthographic one, ``joints.click_point``; grid / point snapping while held), press-drag
  moves it, middle-drag moves the last point, Backspace / Delete removes the last point, Enter completes a new
  ``polySurfaceN`` (vertices in world space, pivot at the origin, lambert1), Limit points completes by itself, Esc drops
  the points (with none, leaves the tool). The tool stays, like Maya's.
- Append to Polygon (Mesh Tools > Append to Polygon): ``allset.append_polygon_tool`` (edit mode) runs
  ``allset.append_polygon``: the first click picks a border edge of the edited mesh (its two vertices start the new
  face, wound against the face they border), later clicks pick another border edge (its two vertices) or place a point
  (on the plane through the first edge that faces the view), Enter adds the face to the mesh.
Tool Settings (Divisions, Limit points, Keep new faces planar, Texture) live in ``Scene.allset_poly_tools``; their
Maya factory values (Maya 2022 Tool Settings). Pure bmesh parts (``polygon_points``, ``polygon_uvs``,
``build_polygon``, ``append_face``) are tested headless (tests/test_step144_poly.py).
"""

import math

import bmesh
import bpy
import gpu
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, geometry

from .. import results
from . import preselect

CREATE_TOOL = "allset.create_polygon_tool"
APPEND_TOOL = "allset.append_polygon_tool"
BASE_NAME = "polySurface"        # Maya polyCreateFacet result (kit Maya naming, step 63 Separate)
EDGE_PX = 16.0                   # border-edge pick radius (preselect.RADIUS_PX)
SNAP_PX = 16.0                   # point snapping radius (V hold)
POINT_RGB = (0.27, 0.82, 0.98)   # the tool's points / outline [I]
PREVIEW_RGB = (0.85, 0.85, 0.85)
BORDER_RGB = (0.98, 0.65, 0.2)   # Append: the mesh's border edges [I]
POINT_PX = 7.0
LINE_PX = 2.0

TEXTURES = (('NORMALIZE', "Normalize (scale to fit)", "UVs: planar projection scaled to fit the 0-1 square"),
            ('UNITIZE', "Unitize (use corners and boundary)", "UVs: the points spread around the edge of the 0-1 square"),
            ('NONE', "None", "No UVs"))


class ALLSET_PG_poly_tools(bpy.types.PropertyGroup):
    """Maya Tool Settings of Create Polygon / Append to Polygon / Quad Draw (factory values)."""
    # Create Polygon (polyCreateFacetCtx)
    cp_divisions: IntProperty(name="Divisions", default=1, min=1, soft_max=10,
                              description="Each edge of the new polygon is split into this many edges")
    cp_limit_on: BoolProperty(name="Limit the number of points", default=False,
                              description="Complete the polygon by itself at Limit points to")
    cp_limit_points: IntProperty(name="Limit points to", default=4, min=3, soft_max=20,
                                 description="Number of points that completes the polygon")
    cp_keep_planar: BoolProperty(name="Keep new faces planar", default=False,
                                 description="Flatten the points onto one plane")
    cp_texture: EnumProperty(name="Texture space", items=TEXTURES, default='NORMALIZE')
    # Append to Polygon (polyAppendFacetCtx)
    ap_divisions: IntProperty(name="Divisions", default=1, min=1, soft_max=10,
                              description="Each new edge of the face is split into this many edges")
    ap_rotation_angle: FloatProperty(name="Rotation angle", default=0.0, min=-360.0, max=360.0,
                                     description="Maya turns new points about the first edge (kept for reference)")
    ap_limit_on: BoolProperty(name="Limit the number of points", default=False,
                              description="Add the face by itself at Limit points to")
    ap_limit_points: IntProperty(name="Limit points to", default=4, min=3, soft_max=20,
                                 description="Number of points that completes the face")
    ap_keep_planar: BoolProperty(name="Keep new faces planar", default=False,
                                 description="Flatten the new points onto one plane with the face's other points")
    ap_texture: EnumProperty(name="Texture space", items=TEXTURES, default='NORMALIZE')
    # Quad Draw (nexQuadDrawCtx)
    qd_auto_weld: BoolProperty(name="Auto-weld", default=True,
                               description="A vertex moved this close (pixels) to another one is merged with it")
    qd_weld_px: IntProperty(name="Auto-weld distance", default=10, min=1, soft_max=50, subtype='PIXEL')
    qd_relax: EnumProperty(name="Relax", default='AUTO_LOCK', items=(
        ('AUTO_LOCK', "Auto-Lock", "The nearest vertex at stroke start chooses border or interior relaxation"),
        ('INTERIOR', "Interior Vertices", "Shift+drag relaxes only inner vertices"),
        ('BORDER', "Border Vertices", "Shift+drag relaxes only border vertices"),
        ('ALL', "All Vertices", "Relax all vertices, including borders, using all connected neighbours")))
    qd_extend: EnumProperty(name="Extend", default='EDGE', items=(
        ('EDGE', "Edge", "Tab+drag on a border edge adds one quad"),
        ('LOOP', "Loop", "Tab+drag extends the boundary chain up to its corners"),
        ('BORDER', "Border", "Tab+drag extends the entire connected border")))
    qd_strip_width: IntProperty(name="Quad Strip Width", default=20, min=1, soft_max=100, subtype='PIXEL',
                                description="Width of the quads Tab+drag draws in empty space (pixels)")
    qd_snap_backfaces: BoolProperty(name="Snap to Backfaces", default=False,
                                    description="Dots and moved points may land on surface faces turned away")
    qd_wire_overlay: BoolProperty(name="Wireframe Overlay", default=True)
    qd_wire_color: FloatVectorProperty(name="Wire Color", subtype='COLOR', size=3,
                                       default=(0.0, 0.0, 0.0), min=0.0, max=1.0)
    qd_mesh_color_on: BoolProperty(name="Mesh Color", default=True)
    # Linear sRGB for the supplied Maya display swatch #008BD4 (ACEScg picker).
    qd_mesh_color: FloatVectorProperty(name="Mesh Color", subtype='COLOR', size=3,
                                       default=(0.0, 0.258183, 0.658375), min=0.0, max=1.0,
                                       description="Quad Draw display tint; does not change materials")
    qd_mesh_alpha: FloatProperty(name="Mesh Alpha", default=0.75, min=0.0, max=1.0)
    qd_offset_on: BoolProperty(name="Surface Offset", default=False)
    qd_surface_offset: FloatProperty(name="Surface Offset", default=0.0, soft_min=-0.1, soft_max=0.1,
                                      description="World-space distance of new and projected points from the live surface")


SETTINGS = {
    'CREATE': ("cp_divisions", "cp_limit_on", "cp_limit_points", "cp_keep_planar", "cp_texture"),
    'APPEND': ("ap_divisions", "ap_rotation_angle", "ap_limit_on", "ap_limit_points", "ap_keep_planar", "ap_texture"),
    'QUAD_DRAW': ("qd_auto_weld", "qd_weld_px", "qd_relax", "qd_extend", "qd_strip_width", "qd_snap_backfaces",
                  "qd_wire_overlay", "qd_wire_color", "qd_mesh_color_on", "qd_mesh_color", "qd_mesh_alpha",
                  "qd_offset_on", "qd_surface_offset"),
}


def settings(context=None):
    return (context or bpy.context).scene.allset_poly_tools


def reset_settings(s, kind):
    for name in SETTINGS[kind]:
        s.property_unset(name)


# --- pure: polygon geometry -----------------------------------------------------------------------------

def _dedupe(points, eps=1e-9):
    out = []
    for p in points:
        p = Vector(p)
        if not out or (p - out[-1]).length > eps:
            out.append(p)
    while len(out) > 1 and (out[0] - out[-1]).length <= eps:
        out.pop()
    return out


def newell_normal(points):
    n = Vector((0.0, 0.0, 0.0))
    for a, b in zip(points, points[1:] + points[:1]):
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n.normalized() if n.length > 1e-12 else Vector((0.0, 0.0, 1.0))


def flatten(points, fixed=()):
    """Points projected onto their best-fit plane (Newell normal through the centroid of ``fixed`` if given, else
    of every point); points whose index is in ``fixed`` keep their place."""
    pts = [Vector(p) for p in points]
    if len(pts) < 3:
        return pts
    n = newell_normal(pts)
    ref = [pts[i] for i in fixed] or pts
    c = sum(ref, Vector()) / len(ref)
    return [p if i in fixed else p - n * (p - c).dot(n) for i, p in enumerate(pts)]


def divide_ring(points, divisions, skip=()):
    """Every edge of the closed ring split into ``divisions`` edges; edge k (points[k] -> points[k+1]) is left whole
    when ``k`` is in ``skip``. Returns [(point, original index or None)]."""
    n = max(1, int(divisions))
    out = []
    for k, a in enumerate(points):
        b = points[(k + 1) % len(points)]
        out.append((a, k))
        if k in skip:
            continue
        out += [(a.lerp(b, j / n), None) for j in range(1, n)]
    return out


def polygon_points(points, divisions=1, planar=True):
    """Maya Create Polygon: the clicked points (duplicates dropped), flattened (Keep new faces planar), each edge
    divided (Divisions)."""
    pts = _dedupe(points)
    if planar:
        pts = flatten(pts)
    return [p for p, _k in divide_ring(pts, divisions)] if len(pts) >= 2 else pts


def polygon_uvs(points, texture='NORMALIZE'):
    """UVs for a polygon's points: Normalize = planar projection on the polygon's plane scaled (aspect kept) into
    0-1; Unitize = the points spread by perimeter around the 0-1 square's edge; None = no UVs (returns None)."""
    pts = [Vector(p) for p in points]
    if texture == 'NONE' or len(pts) < 3:
        return None
    if texture == 'UNITIZE':
        lens = [(b - a).length for a, b in zip(pts, pts[1:] + pts[:1])]
        total = sum(lens) or 1.0
        out, acc = [], 0.0
        for k in range(len(pts)):
            out.append(_square_edge(acc / total))
            acc += lens[k]
        return out
    n = newell_normal(pts)
    u = (pts[1] - pts[0])
    u = (u - n * u.dot(n)).normalized() if (u - n * u.dot(n)).length > 1e-12 else n.orthogonal().normalized()
    v = n.cross(u)
    flat = [((p - pts[0]).dot(u), (p - pts[0]).dot(v)) for p in pts]
    lo_u, lo_v = min(f[0] for f in flat), min(f[1] for f in flat)
    span = max(max(f[0] for f in flat) - lo_u, max(f[1] for f in flat) - lo_v) or 1.0
    return [((a - lo_u) / span, (b - lo_v) / span) for a, b in flat]


def _square_edge(t):
    """Point at fraction ``t`` of the 0-1 square's perimeter, counter-clockwise from (0, 0)."""
    t = (t % 1.0) * 4.0
    side, f = int(t), t - int(t)
    return ((f, 0.0), (1.0, f), (1.0 - f, 1.0), (0.0, 1.0 - f))[min(side, 3)]


def build_polygon(bm, points, texture='NORMALIZE'):
    """One face through ``points`` (in order) in ``bm``; UVs per ``texture``. Returns the face or None."""
    pts = _dedupe(points)
    if len(pts) < 3:
        return None
    verts = [bm.verts.new(p) for p in pts]
    try:
        face = bm.faces.new(verts)
    except ValueError:
        for v in verts:
            bm.verts.remove(v)
        return None
    uvs = polygon_uvs(pts, texture)
    if uvs is not None:
        layer = bm.loops.layers.uv.active or bm.loops.layers.uv.new("map1")
        for loop, uv in zip(face.loops, uvs):
            loop[layer].uv = uv
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    bm.normal_update()
    return face


# --- pure: Append to Polygon ---------------------------------------------------------------------------

def edge_start(edge):
    """The two vertices an appended face starts with on border edge ``edge``: against the winding of the face it
    borders, so the new face's normal agrees with it (Maya polyAppend)."""
    if not edge.link_loops:
        return [edge.verts[0], edge.verts[1]]
    loop = edge.link_loops[0]
    a, b = loop.vert, loop.link_loop_next.vert
    return [b, a]


def append_face(bm, items, divisions=1, planar=True, texture='NORMALIZE'):
    """Maya Append to Polygon: a face from ``items`` added to ``bm``: ``('EDGE', index)`` = that border edge's two
    vertices (``edge_start`` order), ``('POINT', local co)`` = a new vertex. Returns the face or None."""
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    seq = []                      # BMVert or Vector
    for it in items:
        if it[0] == 'EDGE':
            for v in edge_start(bm.edges[it[1]]):
                if not seq or seq[-1] is not v:
                    seq.append(v)
        else:
            seq.append(Vector(it[1]))
    while len(seq) > 1 and isinstance(seq[0], bmesh.types.BMVert) and seq[0] is seq[-1]:
        seq.pop()
    olds = [s for s in seq if isinstance(s, bmesh.types.BMVert)]
    if len(seq) < 3 or len(set(olds)) != len(olds):
        return None
    cos = [s.co.copy() if isinstance(s, bmesh.types.BMVert) else s for s in seq]
    fixed = {i for i, s in enumerate(seq) if isinstance(s, bmesh.types.BMVert)}
    if planar:
        cos = flatten(cos, fixed)
    skip = {k for k, s in enumerate(seq) if isinstance(s, bmesh.types.BMVert)
            and isinstance(seq[(k + 1) % len(seq)], bmesh.types.BMVert)
            and bm.edges.get((s, seq[(k + 1) % len(seq)])) is not None}
    ring = divide_ring(cos, divisions, skip)
    verts = [seq[k] if k is not None and k in fixed else bm.verts.new(p) for p, k in ring]
    try:
        face = bm.faces.new(verts)
    except ValueError:
        for v in verts:
            if v not in olds:
                bm.verts.remove(v)
        return None
    layer = bm.loops.layers.uv.active
    uvs = polygon_uvs([v.co for v in verts], texture) if layer is not None else None
    if uvs is not None:
        _fit_uvs(face, layer, uvs)
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()
    bm.normal_update()
    return face


def _fit_uvs(face, layer, uvs):
    """The new face's UVs: its own projection, moved next to the UVs its first old vertex already has [K]."""
    anchor = None
    for loop in face.loops:
        for other in loop.vert.link_loops:
            if other.face is not face:
                anchor = (loop, other[layer].uv.copy())
                break
        if anchor:
            break
    off = Vector((0.0, 0.0))
    if anchor is not None:
        k = list(face.loops).index(anchor[0])
        off = anchor[1] - Vector(uvs[k])
    for loop, uv in zip(face.loops, uvs):
        loop[layer].uv = Vector(uv) + off


# --- picking / placing on screen ------------------------------------------------------------------------

def _ui_scale(context):
    return context.preferences.system.ui_scale or 1.0


def construction_point(context, region, rv3d, coord):
    """Maya's construction plane point under ``coord`` (joints.click_point), with the snapping the user holds:
    grid (X) rounds to one Maya unit, point (V) takes the nearest vertex of a visible mesh on screen."""
    from . import joints, units
    p = joints.click_point(region, rv3d, coord)
    ts = context.scene.tool_settings
    if not ts.use_snap:
        return p
    elements = set(ts.snap_elements)
    if 'VERTEX' in elements:
        q = nearest_vertex(context, region, rv3d, coord, SNAP_PX * _ui_scale(context))
        if q is not None:
            return q
    if elements & {'GRID', 'INCREMENT'}:
        step = units.maya_unit(context.scene)
        return Vector(tuple(round(c / step) * step for c in p))
    return p


def nearest_vertex(context, region, rv3d, coord, radius):
    best = None
    for ob in context.visible_objects:
        if ob.type != 'MESH':
            continue
        mw = ob.matrix_world
        if ob.mode == 'EDIT':
            cos = [mw @ v.co for v in bmesh.from_edit_mesh(ob.data).verts]
        else:
            cos = [mw @ v.co for v in ob.data.vertices]
        for w in cos:
            xy = view3d_utils.location_3d_to_region_2d(region, rv3d, w)
            if xy is None:
                continue
            d = math.hypot(xy.x - coord[0], xy.y - coord[1])
            if d <= radius and (best is None or d < best[0]):
                best = (d, w)
    return best[1] if best else None


def border_edge_at(context, region, rv3d, mouse, ob):
    """Index of the border edge of edit mesh ``ob`` under ``mouse`` (screen distance), or None."""
    import numpy as np
    c = next((c for o, c in preselect.caches(context) if o == ob), None)
    if c is None or not len(c.edges):
        return None
    xy, front = preselect.project(c.co, rv3d.perspective_matrix, region.width, region.height)
    border = np.array([e.is_boundary for e in c.bm.edges], dtype=bool)
    ok = c.eok & border & front[c.edges[:, 0]] & front[c.edges[:, 1]]
    return preselect.pick_edge(xy, c.edges, ok, mouse, EDGE_PX * _ui_scale(context), lambda i, t: True)


def edge_plane_point(region, rv3d, mouse, a, b):
    """Point under ``mouse`` on the plane through world edge a-b that faces the view best (Append's new points)."""
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    e = (b - a)
    d = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
    n = d - e.normalized() * d.dot(e.normalized()) if e.length > 1e-12 else d
    if n.length < 1e-6:
        n = d
    hit = geometry.intersect_line_plane(origin, origin + ray, a, n.normalized())
    return hit if hit is not None else view3d_utils.region_2d_to_location_3d(region, rv3d, mouse, (a + b) / 2)


# --- live state (drawn by _draw_view) -------------------------------------------------------------------

STATE = {"kind": None, "ob": None, "items": [], "hover": None}


def reset_state():
    STATE.update(kind=None, ob=None, items=[], hover=None)


def tool_active(context, tool):
    return preselect.tool_id(context) == tool


def _world_items(ob):
    """World points of the Append items (an edge = its two start vertices)."""
    out = []
    if ob is None:
        return out
    mw = ob.matrix_world
    bm = bmesh.from_edit_mesh(ob.data)
    bm.edges.ensure_lookup_table()
    for it in STATE["items"]:
        if it[0] == 'EDGE':
            if it[1] < len(bm.edges):
                out += [mw @ v.co for v in edge_start(bm.edges[it[1]])]
        else:
            out.append(mw @ Vector(it[1]))
    return out


def _lines(region, pts, rgb, px):
    if len(pts) < 2:
        return
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", px)
    shader.uniform_float("color", (*rgb, 1.0))
    batch_for_shader(shader, 'LINES', {"pos": pts}).draw(shader)


def _points(pts, rgb, px):
    if not pts:
        return
    shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
    gpu.state.point_size_set(px)
    shader.uniform_float("color", (*rgb, 1.0))
    batch_for_shader(shader, 'POINTS', {"pos": pts}).draw(shader)


def _border_segments(ob):
    mw = ob.matrix_world
    bm = bmesh.from_edit_mesh(ob.data)
    return [tuple(mw @ v.co) for e in bm.edges if e.is_boundary and not e.hide for v in e.verts]


def _draw_view():
    context = bpy.context
    try:
        create = tool_active(context, CREATE_TOOL)
        append = context.mode == 'EDIT_MESH' and tool_active(context, APPEND_TOOL)
        if not (create or append):
            return
        region = context.region
        scale = _ui_scale(context)
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        if append:
            for ob in context.objects_in_mode_unique_data:
                if ob.type == 'MESH':
                    _lines(region, _border_segments(ob), BORDER_RGB, LINE_PX * 1.5 * scale)
        if STATE["kind"] == 'CREATE':
            pts = [tuple(p) for p in STATE["items"]]
        elif STATE["kind"] == 'APPEND':
            pts = [tuple(p) for p in _world_items(bpy.data.objects.get(STATE["ob"] or ""))]
        else:
            pts = []
        if len(pts) > 1:
            _lines(region, [q for a, b in zip(pts, pts[1:]) for q in (a, b)], POINT_RGB, LINE_PX * scale)
        hover = STATE["hover"]
        if pts and hover is not None:
            hp = tuple(hover)
            _lines(region, [pts[-1], hp, hp, pts[0]], PREVIEW_RGB, LINE_PX * scale)
        _points(pts, POINT_RGB, POINT_PX * scale)
        gpu.state.blend_set('NONE')
    except (ReferenceError, AttributeError, IndexError, ValueError, KeyError):
        pass


_handles = []


def _redraw(context):
    if context.area is not None:
        context.area.tag_redraw()


def _view_ok(context):
    r = context.region
    return r is not None and r.type == 'WINDOW' and context.region_data is not None


# --- object creation -------------------------------------------------------------------------------------

def create_polygon_object(context, points, s=None):
    """The new ``polySurfaceN`` from world ``points`` (Create Polygon completion). Returns the object or None."""
    from . import mesh_maya, material
    s = s or settings(context)
    pts = polygon_points(points, s.cp_divisions, s.cp_keep_planar)
    if len(pts) < 3:
        return None
    me = bpy.data.meshes.new(BASE_NAME)
    bm = bmesh.new()
    if build_polygon(bm, pts, s.cp_texture) is None:
        bm.free()
        bpy.data.meshes.remove(me)
        return None
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(BASE_NAME, me)
    context.view_layer.active_layer_collection.collection.objects.link(ob)
    mesh_maya._maya_rename(ob, BASE_NAME)
    material.give_default(ob)
    if context.view_layer.objects.active is not None and context.view_layer.objects.active.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for other in context.selected_objects:
        other.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    return ob


# --- operators ------------------------------------------------------------------------------------------

STATUS_CREATE = ("Create Polygon: click to place points, Enter to complete, Backspace: remove the last point, "
                 "middle-drag: move the last point, Esc: cancel")
STATUS_APPEND = ("Append to Polygon: click a border edge, then points or another border edge, Enter to complete, "
                 "Backspace: remove the last point, Esc: cancel")


class _PolySession:
    """Shared modal of Create Polygon / Append to Polygon: points while the tool stays."""
    kind = 'CREATE'

    def _mouse(self, event):
        return (event.mouse_region_x, event.mouse_region_y)

    def _end(self, context, result):
        reset_state()
        _redraw(context)
        context.workspace.status_text_set(None)
        return result

    def _limit(self, context):
        s = settings(context)
        if self.kind == 'CREATE':
            return s.cp_limit_points if s.cp_limit_on else -1
        return s.ap_limit_points if s.ap_limit_on else -1

    def _count(self):
        return len(STATE["items"]) if self.kind == 'CREATE' else len(_world_items(bpy.data.objects.get(STATE["ob"])))

    def _start(self, context, event):
        if not _view_ok(context) or event.alt:
            return {'PASS_THROUGH'}
        reset_state()
        STATE["kind"] = self.kind
        if not self._press(context, event):
            reset_state()
            return {'PASS_THROUGH'}
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(STATUS_CREATE if self.kind == 'CREATE' else STATUS_APPEND)
        _redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not _view_ok(context) or not tool_active(context, CREATE_TOOL if self.kind == 'CREATE' else APPEND_TOOL):
            return self._end(context, {'CANCELLED'})
        mouse = self._mouse(event)
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if self._drag is not None:
                self._move(context, mouse, self._drag)
            else:
                STATE["hover"] = self._hover_point(context, mouse)
            _redraw(context)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and not event.alt:
            if event.value == 'PRESS':
                self._press(context, event)
                _redraw(context)
                return self._check_limit(context)
            if event.value == 'RELEASE':
                self._drag = None
                return {'RUNNING_MODAL'}
        if event.type == 'MIDDLEMOUSE' and not (event.alt or event.ctrl or event.shift):
            if event.value == 'PRESS' and self._last_free() is not None:
                self._drag = self._last_free()
                return {'RUNNING_MODAL'}
            if event.value == 'RELEASE' and self._drag is not None:
                self._drag = None
                return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type in {'BACK_SPACE', 'DEL'}:
            self._pop()
            _redraw(context)
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type in {'RET', 'NUMPAD_ENTER'}:
            return self._finish(context)
        if event.value == 'PRESS' and event.type == 'ESC':
            return self._end(context, {'CANCELLED'})
        return {'PASS_THROUGH'}

    def _check_limit(self, context):
        limit = self._limit(context)
        if limit > 0 and self._count() >= limit:
            return self._finish(context)
        return {'RUNNING_MODAL'}


class ALLSET_OT_create_polygon(_PolySession, bpy.types.Operator):
    """Maya Create Polygon: click to place points, Enter to make the polygon (a new polySurface object).
    Backspace removes the last point, middle-drag moves it, Esc cancels"""
    bl_idname = "allset.create_polygon"
    bl_label = "Create Polygon"
    bl_options = {'REGISTER', 'UNDO'}
    kind = 'CREATE'

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode in {'OBJECT', 'EDIT_MESH'}

    def invoke(self, context, event):
        self._drag = None
        return self._start(context, event)

    def _hover_point(self, context, mouse):
        return construction_point(context, context.region, context.region_data, mouse) if STATE["items"] else None

    def _press(self, context, event):
        p = construction_point(context, context.region, context.region_data, self._mouse(event))
        if p is None:
            return False
        STATE["items"].append(p)
        self._drag = len(STATE["items"]) - 1
        return True

    def _move(self, context, mouse, index):
        p = construction_point(context, context.region, context.region_data, mouse)
        if p is not None and index < len(STATE["items"]):
            STATE["items"][index] = p

    def _last_free(self):
        return len(STATE["items"]) - 1 if STATE["items"] else None

    def _pop(self):
        if STATE["items"]:
            STATE["items"].pop()

    def _finish(self, context):
        points = list(STATE["items"])
        if len(_dedupe(points)) < 3:
            self.report({'WARNING'}, "Create Polygon: place at least 3 points")
            return {'RUNNING_MODAL'} if points else self._end(context, {'CANCELLED'})
        was_edit = context.mode == 'EDIT_MESH'
        ob = create_polygon_object(context, points)
        self._end(context, {'FINISHED'})
        if ob is None:
            return {'CANCELLED'}
        if was_edit:     # the new object is selected in object mode: keep Maya's tool there too
            try:
                bpy.ops.wm.tool_set_by_id(name=CREATE_TOOL, space_type='VIEW_3D')
            except RuntimeError:
                pass
        results.result(self, f"Created {ob.name}")
        return {'FINISHED'}


class ALLSET_OT_append_polygon(_PolySession, bpy.types.Operator):
    """Maya Append to Polygon: click a border edge, then points or another border edge, Enter adds the face"""
    bl_idname = "allset.append_polygon"
    bl_label = "Append to Polygon"
    bl_options = {'REGISTER', 'UNDO'}
    kind = 'APPEND'

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        self._drag = None
        return self._start(context, event)

    def _ob(self):
        return bpy.data.objects.get(STATE["ob"]) if STATE["ob"] else None

    def _first_edge_world(self):
        ob = self._ob()
        first = next((it for it in STATE["items"] if it[0] == 'EDGE'), None)
        if ob is None or first is None:
            return None
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        a, b = edge_start(bm.edges[first[1]])
        return ob.matrix_world @ a.co, ob.matrix_world @ b.co

    def _free_point(self, context, mouse):
        ends = self._first_edge_world()
        if ends is None:
            return None
        return edge_plane_point(context.region, context.region_data, mouse, *ends)

    def _hover_point(self, context, mouse):
        return self._free_point(context, mouse) if STATE["items"] else None

    def _press(self, context, event):
        region, rv3d = context.region, context.region_data
        mouse = self._mouse(event)
        obs = [o for o in context.objects_in_mode_unique_data if o.type == 'MESH']
        if STATE["ob"] is not None:
            obs = [o for o in obs if o.name == STATE["ob"]]
        for ob in obs:
            i = border_edge_at(context, region, rv3d, mouse, ob)
            if i is not None:
                if any(it == ('EDGE', i) for it in STATE["items"]):
                    return True
                STATE["ob"] = ob.name
                STATE["items"].append(('EDGE', i))
                self._drag = None
                return True
        if not STATE["items"]:
            self.report({'WARNING'}, "Append to Polygon: click a border edge of the selected mesh first")
            return False
        w = self._free_point(context, mouse)
        if w is None:
            return False
        ob = self._ob()
        STATE["items"].append(('POINT', tuple(ob.matrix_world.inverted_safe() @ w)))
        self._drag = len(STATE["items"]) - 1
        return True

    def _move(self, context, mouse, index):
        w = self._free_point(context, mouse)
        ob = self._ob()
        if w is not None and ob is not None and index < len(STATE["items"]) and STATE["items"][index][0] == 'POINT':
            STATE["items"][index] = ('POINT', tuple(ob.matrix_world.inverted_safe() @ w))

    def _last_free(self):
        k = len(STATE["items"]) - 1
        return k if k >= 0 and STATE["items"][k][0] == 'POINT' else None

    def _pop(self):
        if STATE["items"]:
            STATE["items"].pop()
        if not STATE["items"]:
            STATE["ob"] = None

    def _finish(self, context):
        ob = self._ob()
        if ob is None:
            return self._end(context, {'CANCELLED'})
        s = settings(context)
        bm = bmesh.from_edit_mesh(ob.data)
        face = append_face(bm, list(STATE["items"]), s.ap_divisions, s.ap_keep_planar, s.ap_texture)
        if face is None:
            self.report({'WARNING'}, "Append to Polygon: the face needs at least 3 different points")
            return {'RUNNING_MODAL'}
        for el in (*bm.verts, *bm.edges, *bm.faces):
            el.select = False
        face.select = True
        bmesh.update_edit_mesh(ob.data)
        preselect.invalidate()
        return self._end(context, {'FINISHED'})


class ALLSET_OT_poly_tool_exit(bpy.types.Operator):
    """Leave the tool for the Select tool (Maya Esc / Q)"""
    bl_idname = "allset.poly_tool_exit"
    bl_label = "Exit Tool"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        reset_state()
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box", space_type='VIEW_3D')
        return {'FINISHED'}


def _open_tool_settings():
    try:
        bpy.ops.allset.editor_toggle(editor='TOOL_SETTINGS', show=True)
    except (RuntimeError, AttributeError):
        pass


class ALLSET_OT_create_polygon_start(bpy.types.Operator):
    """Maya Mesh Tools > Create Polygon: click points in the view, Enter makes a new polygon object"""
    bl_idname = "allset.create_polygon_start"
    bl_label = "Create Polygon Tool"
    bl_options = {'REGISTER'}

    option_box: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        if context.mode not in {'OBJECT', 'EDIT_MESH'}:
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                pass
        try:
            bpy.ops.wm.tool_set_by_id(name=CREATE_TOOL, space_type='VIEW_3D')
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex).strip())
            return {'CANCELLED'}
        if self.option_box:
            _open_tool_settings()
        return {'FINISHED'}


class ALLSET_OT_append_polygon_start(bpy.types.Operator):
    """Maya Mesh Tools > Append to Polygon: click a border edge of the selected mesh, then points, Enter adds a face"""
    bl_idname = "allset.append_polygon_start"
    bl_label = "Append to Polygon Tool"
    bl_options = {'REGISTER'}

    option_box: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        ob = context.active_object
        if ob is None or ob.type != 'MESH':
            ob = next((o for o in context.selected_objects if o.type == 'MESH'), None)
        if ob is None:
            self.report({'WARNING'}, "Append to Polygon: select a polygon mesh first.")
            return {'CANCELLED'}
        from . import maya_errors
        if context.mode != 'EDIT_MESH' and maya_errors.refuse_hidden(self, ob):     # #187
            return {'CANCELLED'}
        if context.mode != 'EDIT_MESH':
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            context.view_layer.objects.active = ob
            ob.select_set(True)
            bpy.ops.object.mode_set('EXEC_DEFAULT', True, mode='EDIT')    # own undo step (step 129)
        try:
            bpy.ops.wm.tool_set_by_id(name=APPEND_TOOL, space_type='VIEW_3D')
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex).strip())
            return {'CANCELLED'}
        if self.option_box:
            _open_tool_settings()
        return {'FINISHED'}


class ALLSET_OT_poly_tools_reset(bpy.types.Operator):
    """Reset the tool's options to Maya's factory values"""
    bl_idname = "allset.poly_tools_reset"
    bl_label = "Reset Tool"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    kind: EnumProperty(items=[(k, k, "") for k in SETTINGS], options={'SKIP_SAVE'})

    def execute(self, context):
        reset_settings(settings(context), self.kind)
        return {'FINISHED'}


classes = (ALLSET_PG_poly_tools, ALLSET_OT_create_polygon, ALLSET_OT_append_polygon, ALLSET_OT_poly_tool_exit,
           ALLSET_OT_create_polygon_start, ALLSET_OT_append_polygon_start, ALLSET_OT_poly_tools_reset)


def register_props():
    bpy.types.Scene.allset_poly_tools = bpy.props.PointerProperty(type=ALLSET_PG_poly_tools)


def unregister_props():
    del bpy.types.Scene.allset_poly_tools


def register_handlers():
    if not _handles:
        _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw_view, (), 'WINDOW', 'POST_VIEW'))


def unregister_handlers():
    while _handles:
        bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), 'WINDOW')
    reset_state()
