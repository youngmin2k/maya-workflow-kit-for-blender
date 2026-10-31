# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Target Weld, Crease Tool and Multi-Cut feel.

- Target Weld (Maya polyMergeVertexContext):
  drag a vertex (an edge in edge mode) onto another one; a dragged vertex that is selected takes every selected
  vertex with it (Maya's tool description). Merge To Target / Center.
- Crease Tool (Maya polyCreaseCtx): MMB drag left / right = less / more crease on the selected
  edges (vertices in vertex mode), shown as Maya's value. Blender stores 0-1 with OpenSubdiv sharpness = 10 * b^2
 , so Maya value c is stored as sqrt(c / 10).
- Multi-Cut: a kit tool (operators/multi_cut.py); its Tool Settings live here
  and it reuses ``edge_ring`` / ``insert_loop`` / ``snap_factor``.
"""

import math

import bmesh
import bpy
import gpu
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty,
                       StringProperty)
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, geometry


PICK_RADIUS = 15          # px at UI scale 1: how far from a vertex / edge a press still picks it
CREASE_PER_PX = 0.02      # Maya crease value per px of horizontal MMB drag (50 px = 1; sensitivity)
MAYA_CREASE_MAX = 10.0    # Blender crease 1.0 = sharpness 10 (and "infinitely" sharp)
MAYA_SNAP_STEP = 10       # Multi-Cut Snap Step %

TARGET_WELD_TOOL = "allset.target_weld_tool"
CREASE_TOOL = "allset.crease_tool"
MULTI_CUT_TOOL = "allset.multi_cut_tool"     # operators/multi_cut.py

_handles = []   # (space type, handle) of draw handlers of running modals (removed on unregister)


# --- settings (Maya Tool Settings of the three tools) ----------------------------------------------

MERGE_TO = (('TARGET', "Target", "Merge at the target vertex"),
            ('CENTER', "Center", "Merge half-way between the vertices"))
CREASE_MODES = (('ABSOLUTE', "Absolute", "Every selected component gets the same crease value"),
                ('RELATIVE', "Relative", "The drag adds to each component's own crease value"))


class ALLSET_PG_mesh_tools(bpy.types.PropertyGroup):
    weld_merge_to: EnumProperty(name="Merge To", default='TARGET', items=MERGE_TO)
    weld_preserve_uvs: BoolProperty(
        name="Preserve UVs", default=True,
        description="The merged vertex keeps the target vertex's UVs")
    crease_mode: EnumProperty(name="Mode", default='ABSOLUTE', items=CREASE_MODES)
    snap_step: IntProperty(
        name="Snap Step %", default=MAYA_SNAP_STEP, min=1, max=100,
        description="Multi-Cut: Shift snaps the cut point along the edge in these steps")
    # Multi-Cut Tool Settings, default values (like Maya)
    smoothing_angle: FloatProperty(
        name="Smoothing Angle", default=180.0, min=0.0, max=180.0, precision=0,
        description="New edges between faces bent more than this are hard (sharp), the rest soft")
    edge_flow: BoolProperty(name="Edge Flow", default=False)
    edge_flow_adjust: FloatProperty(name="Edge Flow Adjust", default=1.0, min=-1.0, max=1.0)
    subdivisions: IntProperty(
        name="Subdivisions", default=1, min=1, max=32,
        description="Each new edge of the cut is split into this many parts")
    ignore_backfaces: BoolProperty(
        name="Ignore Backfaces", default=False,
        description="Slice: only faces facing the camera are cut")
    delete_faces: BoolProperty(
        name="Delete Faces", default=False,
        description="Slice: delete the faces on one side of the slice (the side to the right of the drag)")
    extract_faces: BoolProperty(
        name="Extract Faces", default=False,
        description="Slice: split the faces on one side off and move them by the offset")
    extract_offset: FloatVectorProperty(
        name="Extract Offset", size=3, default=(0.5, 0.5, 0.5),
        description="Slice: how far extracted faces move (Maya X / Y / Z, scene units)")
    slice_plane: EnumProperty(
        name="Slice Along Plane", default='NONE',
        items=(('NONE', "Free", "Slice along the dragged line"),
               ('YZ', "YZ", "A click slices along the world YZ plane through the clicked point"),
               ('ZX', "ZX", "A click slices along the world ZX (Maya ground) plane through the clicked point"),
               ('XY', "XY", "A click slices along the world XY plane through the clicked point")))


def settings(context):
    return context.scene.allset_mesh_tools


def register_props():
    bpy.utils.register_class(ALLSET_PG_mesh_tools)
    bpy.types.Scene.allset_mesh_tools = PointerProperty(type=ALLSET_PG_mesh_tools)


def unregister_props():
    del bpy.types.Scene.allset_mesh_tools
    bpy.utils.unregister_class(ALLSET_PG_mesh_tools)


# --- picking on screen -----------------------------------------------------------------------------

def _ui_scale():
    return bpy.context.preferences.system.ui_scale


def _view(context):
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None or region.type != 'WINDOW':
        return None
    return region, rv3d


def _mesh_objects(context):
    return [o for o in getattr(context, "objects_in_mode_unique_data", ()) if o.type == 'MESH']


def _depth(rv3d, p):
    return -(rv3d.view_matrix @ p).z


def _segment_distance(p, a, b):
    ab = b - a
    n = ab.length_squared
    t = 0.0 if n < 1e-12 else max(0.0, min(1.0, (p - a).dot(ab) / n))
    return (a + ab * t - p).length


def visible_test(context):
    """``f(world point) -> bool``: the point isn't behind a mesh in edit mode, like the pre-selection highlight;
    None (everything visible) while X-ray is on."""
    space = context.space_data
    if space is None or space.type != 'VIEW_3D':
        return None
    from . import multi_cut, preselect
    if preselect._xray(space):
        return None
    cs = preselect.caches(context)
    region, rv3d = context.region, context.region_data
    return lambda w: not multi_cut._occluded(cs, region, rv3d, w, False)


def pick(view, objects, mouse, kind='VERT', radius=PICK_RADIUS, exclude=None, visible=None):
    """(object, element index) of the vertex / edge nearest to ``mouse`` on screen within ``radius`` px.
    ``visible`` (see ``visible_test``) skips hidden elements (an edge by its middle); without it occlusion is not
    checked. Near ties go to the one nearer to the camera."""
    region, rv3d = view
    mouse = Vector(mouse)
    best = None
    for ob in objects:
        bm = bmesh.from_edit_mesh(ob.data)
        mw = ob.matrix_world
        to2d = view3d_utils.location_3d_to_region_2d
        if kind == 'VERT':
            elems = bm.verts
        else:
            elems = bm.edges
        cache = {}

        def screen(v):
            if v.index not in cache:
                w = mw @ v.co
                cache[v.index] = (to2d(region, rv3d, w), w)
            return cache[v.index]
        bm.verts.index_update()
        bm.edges.index_update()
        for e in elems:
            if e.hide or (exclude is not None and exclude == (ob.name, e.index)):
                continue
            if kind == 'VERT':
                p, w = screen(e)
                if p is None:
                    continue
                d = (p - mouse).length
                depth = _depth(rv3d, w)
            else:
                (p0, w0), (p1, w1) = screen(e.verts[0]), screen(e.verts[1])
                if p0 is None or p1 is None:
                    continue
                d = _segment_distance(mouse, p0, p1)
                depth = _depth(rv3d, (w0 + w1) / 2)
            if d > radius:
                continue
            if visible is not None and not visible(w if kind == 'VERT' else (w0 + w1) / 2):
                continue
            key = (round(d / 3), depth)
            if best is None or key < best[0]:
                best = (key, ob, e.index)
    return (best[1], best[2]) if best else (None, -1)


def element_screen(view, ob, kind, index):
    """Screen points of a vertex (one) or an edge (two)."""
    region, rv3d = view
    bm = bmesh.from_edit_mesh(ob.data)
    seq = bm.verts if kind == 'VERT' else bm.edges
    seq.ensure_lookup_table()
    if index >= len(seq):
        return []
    verts = [seq[index]] if kind == 'VERT' else list(seq[index].verts)
    pts = [view3d_utils.location_3d_to_region_2d(region, rv3d, ob.matrix_world @ v.co) for v in verts]
    return [p for p in pts if p is not None]


def edge_factor(view, ob, edge, mouse):
    """Where the view ray under ``mouse`` passes the edge: 0 at ``edge.verts[0]``, 1 at ``edge.verts[1]``."""
    region, rv3d = view
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    p0, p1 = ob.matrix_world @ edge.verts[0].co, ob.matrix_world @ edge.verts[1].co
    hit = geometry.intersect_line_line(p0, p1, origin, origin + direction)
    seg = p1 - p0
    if hit is None or seg.length_squared < 1e-12:
        return 0.5
    return max(0.0, min(1.0, (hit[0] - p0).dot(seg) / seg.length_squared))


def snap_factor(t, step_percent, inner=False):
    """``t`` rounded to Maya's Snap Step %. ``inner``: never the edge's ends (a loop needs a cut inside)."""
    s = max(1, min(100, step_percent)) / 100.0
    t = max(0.0, min(1.0, round(t / s) * s))
    if inner and (t <= 1e-6 or t >= 1.0 - 1e-6):
        if s >= 0.5:
            return 0.5
        t = s if t <= 1e-6 else 1.0 - s
    return t


# --- Target Weld -----------------------------------------------------------------------------------

def weld_vertices(bm, sources, target, merge_to='TARGET', preserve_uvs=True):
    """Merge ``sources`` into ``target`` (bmesh). Returns the remaining vertex (``target``) or None."""
    sources = [v for v in dict.fromkeys(sources) if v is not target and v.is_valid]
    if not sources or not target.is_valid:
        return None
    group = [target, *sources]    # pointmerge keeps the first vertex
    if merge_to == 'CENTER':
        co = sum((v.co for v in group), Vector()) / len(group)
    else:
        co = target.co.copy()
    if preserve_uvs:
        from .. import compat
        compat.pointmerge_facedata(bm, group, target)
    bmesh.ops.pointmerge(bm, verts=group, merge_co=co)
    return target if target.is_valid else None


def weld_edges(bm, source, target, merge_to='TARGET', preserve_uvs=True):
    """Merge edge ``source`` onto edge ``target``: each end goes to the target end it pairs with (the shared
    vertex stays; otherwise the pairing with the shorter total distance). Returns the remaining vertices."""
    if source is target:
        return []
    shared = set(source.verts) & set(target.verts)
    if len(shared) == 2:
        return []
    if shared:
        s = shared.pop()
        pairs = [(source.other_vert(s), target.other_vert(s))]
    else:
        a, b = source.verts
        c, d = target.verts
        straight = (a.co - c.co).length + (b.co - d.co).length
        crossed = (a.co - d.co).length + (b.co - c.co).length
        pairs = [(a, c), (b, d)] if straight <= crossed else [(a, d), (b, c)]
    kept = []
    for src, dst in pairs:
        if merge_to == 'CENTER':
            mid = (src.co + dst.co) / 2
            weld_vertices(bm, [src], dst, 'TARGET', preserve_uvs)
            dst.co = mid
        else:
            weld_vertices(bm, [src], dst, 'TARGET', preserve_uvs)
        kept.append(dst)
    return kept


def weld(bm, kind, source_index, target_index, merge_to='TARGET', preserve_uvs=True):
    """Target Weld on ``bm`` by element indices. A selected source vertex brings every selected vertex."""
    seq = bm.verts if kind == 'VERT' else bm.edges
    seq.ensure_lookup_table()
    n = len(seq)
    if not (0 <= source_index < n and 0 <= target_index < n) or source_index == target_index:
        return []
    src, dst = seq[source_index], seq[target_index]
    if kind == 'VERT':
        sources = [src]
        if src.select:
            sources += [v for v in bm.verts if v.select and v is not dst]
        kept = weld_vertices(bm, sources, dst, merge_to, preserve_uvs)
        kept = [kept] if kept else []
    else:
        kept = weld_edges(bm, src, dst, merge_to, preserve_uvs)
    for v in kept:
        v.select_set(True)
    bm.select_flush_mode()
    return kept


class ALLSET_OT_target_weld(bpy.types.Operator):
    """Drag a vertex or edge onto the target to merge them (Maya Target Weld). A selected vertex takes every
    selected vertex with it"""
    bl_idname = "allset.target_weld"
    bl_label = "Target Weld"
    bl_options = {'UNDO'}

    object: StringProperty(name="Object", options={'SKIP_SAVE', 'HIDDEN'})
    element: EnumProperty(name="Element", items=(('VERT', "Vertex", ""), ('EDGE', "Edge", "")),
                          options={'SKIP_SAVE', 'HIDDEN'})
    source: IntProperty(name="Source", default=-1, options={'SKIP_SAVE', 'HIDDEN'})
    target: IntProperty(name="Target", default=-1, options={'SKIP_SAVE', 'HIDDEN'})
    merge_to: EnumProperty(name="Merge To", items=MERGE_TO, default='TARGET')
    preserve_uvs: BoolProperty(name="Preserve UVs", default=True)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        ob = bpy.data.objects.get(self.object) if self.object else context.edit_object
        if ob is None or ob.type != 'MESH' or ob.mode != 'EDIT':
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(ob.data)
        kept = weld(bm, self.element, self.source, self.target, self.merge_to, self.preserve_uvs)
        if not kept:
            return {'CANCELLED'}
        bmesh.update_edit_mesh(ob.data)
        return {'FINISHED'}

    # --- modal: press on the source, release on the target ---

    def invoke(self, context, event):
        view = _view(context)
        if view is None:
            return {'PASS_THROUGH'}
        ts = context.tool_settings
        mode = tuple(ts.mesh_select_mode)
        self.element = 'EDGE' if mode[1] and not mode[0] else 'VERT'
        radius = PICK_RADIUS * _ui_scale()
        mouse = (event.mouse_region_x, event.mouse_region_y)
        visible = visible_test(context)
        ob, index = pick(view, _mesh_objects(context), mouse, self.element, radius, visible=visible)
        if ob is None:
            return {'PASS_THROUGH'}     # the tool's select fallback gets the press
        s = settings(context)
        self.object, self.source = ob.name, index
        self.merge_to, self.preserve_uvs = s.weld_merge_to, s.weld_preserve_uvs
        self._view, self._radius, self._button = view, radius, event.type
        self._visible = visible
        self._mouse, self._hover = mouse, -1
        self._region = context.region
        self._space = context.space_data
        self._handle = self._space.draw_handler_add(self._draw, (), 'WINDOW', 'POST_PIXEL')
        _handles.append((type(self._space), self._handle))
        context.area.header_text_set("Target Weld: release over the target "
                                     + ("edge" if self.element == 'EDGE' else "vertex"))
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _ob(self):
        return bpy.data.objects.get(self.object)

    def _draw(self):
        if bpy.context.region != self._region:
            return
        ob = self._ob()
        if ob is None or ob.mode != 'EDIT':
            return
        src = element_screen(self._view, ob, self.element, self.source)
        if not src:
            return
        start = sum(src, Vector((0, 0))) / len(src)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(2.0)
        shader.uniform_float("color", (1.0, 0.85, 0.2, 0.9))
        batch_for_shader(shader, 'LINES', {"pos": [start[:], self._mouse]}).draw(shader)
        if self._hover >= 0:
            dst = element_screen(self._view, ob, self.element, self._hover)
            shader.uniform_float("color", (1.0, 0.0, 0.0, 1.0))   # Maya pre-selection red
            if len(dst) == 2:
                gpu.state.line_width_set(4.0)
                batch_for_shader(shader, 'LINES', {"pos": [dst[0][:], dst[1][:]]}).draw(shader)
            elif dst:
                gpu.state.point_size_set(10.0)
                batch_for_shader(shader, 'POINTS', {"pos": [dst[0][:]]}).draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.point_size_set(1.0)
        gpu.state.blend_set('NONE')

    def _target_under(self, mouse):
        ob = self._ob()
        if ob is None:
            return -1
        hit_ob, index = pick(self._view, [ob], mouse, self.element, self._radius, exclude=(ob.name, self.source),
                             visible=self._visible)
        return index if hit_ob is not None else -1

    def _finish(self, context):
        try:
            self._space.draw_handler_remove(self._handle, 'WINDOW')
        except (ValueError, ReferenceError):
            pass
        if (type(self._space), self._handle) in _handles:
            _handles.remove((type(self._space), self._handle))
        if context.area is not None:
            context.area.header_text_set(None)
        self._region.tag_redraw()

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._mouse = (event.mouse_region_x, event.mouse_region_y)
            self._hover = self._target_under(self._mouse)
            self._region.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._finish(context)
            return {'CANCELLED'}
        if event.type == self._button and event.value == 'RELEASE':
            self._mouse = (event.mouse_region_x, event.mouse_region_y)
            self.target = self._target_under(self._mouse)
            self._finish(context)
            if self.target < 0:
                return {'CANCELLED'}
            return self.execute(context)
        return {'RUNNING_MODAL'}


# --- Crease Tool -----------------------------------------------------------------------------------

def maya_to_blender_crease(c):
    """Maya crease value (sharp for c smooth levels) -> Blender crease 0-1 (sharpness = 10 * b^2)."""
    return math.sqrt(max(0.0, min(c, MAYA_CREASE_MAX)) / MAYA_CREASE_MAX)


def blender_to_maya_crease(b):
    return MAYA_CREASE_MAX * b * b


def crease_layer(bm, kind):
    coll, name = (bm.edges.layers.float, "crease_edge") if kind == 'EDGE' else (bm.verts.layers.float, "crease_vert")
    return coll.get(name) or coll.new(name)


def crease_kind(select_mode):
    """Maya creases vertices in vertex mode, edges otherwise (edges of the selected faces in face mode)."""
    v, e, f = select_mode
    return 'VERT' if v and not (e or f) else 'EDGE'


def crease_elements(bm, kind):
    return [v for v in bm.verts if v.select] if kind == 'VERT' else [e for e in bm.edges if e.select]


def crease_values(bm, kind, elems):
    layer = crease_layer(bm, kind)
    return [blender_to_maya_crease(el[layer]) for el in elems]


def set_crease(bm, kind, elems, starts, value, mode='ABSOLUTE'):
    """ABSOLUTE: every element = ``value``; RELATIVE: each start + ``value`` (Maya values, clamped 0-10)."""
    layer = crease_layer(bm, kind)
    for el, start in zip(elems, starts):
        c = value if mode == 'ABSOLUTE' else start + value
        el[layer] = maya_to_blender_crease(c)


class ALLSET_OT_crease_drag(bpy.types.Operator):
    """Crease the selected edges (vertices in vertex mode): MMB drag left = less, right = more (Maya Crease
    Tool). Values are Maya's (sharp for that many smooth levels); Blender stores 0-1"""
    bl_idname = "allset.crease_drag"
    bl_label = "Crease"
    bl_options = {'UNDO'}

    value: FloatProperty(name="Crease Value", default=0.0, min=-MAYA_CREASE_MAX, max=MAYA_CREASE_MAX,
                         description="Maya crease value (Absolute) or the change (Relative)")
    mode: EnumProperty(name="Mode", items=CREASE_MODES, default='ABSOLUTE')

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def _targets(self, context):
        kind = crease_kind(tuple(context.tool_settings.mesh_select_mode))
        out = []
        for ob in _mesh_objects(context):
            bm = bmesh.from_edit_mesh(ob.data)
            crease_layer(bm, kind)      # a new layer invalidates element references: make it first
            elems = crease_elements(bm, kind)
            if elems:
                out.append((ob, bm, kind, elems, crease_values(bm, kind, elems)))
        return out

    def _apply(self, targets, value):
        for ob, bm, kind, elems, starts in targets:
            set_crease(bm, kind, elems, starts, value, self.mode)
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)

    def execute(self, context):
        targets = self._targets(context)
        if not targets:
            self.report({'WARNING'}, "Select components to crease")
            return {'CANCELLED'}
        self._apply(targets, self.value)
        return {'FINISHED'}

    def invoke(self, context, event):
        self.mode = settings(context).crease_mode
        self._targets_ = self._targets(context)
        if not self._targets_:
            self.report({'WARNING'}, "Select components to crease")
            return {'CANCELLED'}
        self._x0 = event.mouse_x
        self._button = event.type
        self._top = max(max(t[4]) for t in self._targets_)   # Absolute starts from the highest value
        self._show(context, self._top if self.mode == 'ABSOLUTE' else 0.0)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _value(self, x):
        delta = (x - self._x0) * CREASE_PER_PX / _ui_scale()
        if self.mode == 'ABSOLUTE':
            return max(0.0, min(MAYA_CREASE_MAX, self._top + delta))
        return max(-MAYA_CREASE_MAX, min(MAYA_CREASE_MAX, delta))

    def _show(self, context, value):
        if context.area is None:
            return
        if self.mode == 'ABSOLUTE':
            text = f"Crease Mode: Absolute   Crease Value: {value:.2f}   (Blender {maya_to_blender_crease(value):.2f})"
        else:
            text = f"Crease Mode: Relative   Crease Change: {value:+.2f}"
        context.area.header_text_set(text + "   - drag left to crease less, right to crease more")

    def _restore(self):
        for ob, bm, kind, elems, starts in self._targets_:
            set_crease(bm, kind, elems, starts, 0.0, 'RELATIVE')
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self.value = self._value(event.mouse_x)
            self._apply(self._targets_, self.value)
            self._show(context, self.value)
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._restore()
            if context.area is not None:
                context.area.header_text_set(None)
            return {'CANCELLED'}
        if event.type == self._button and event.value == 'RELEASE':
            self.value = self._value(event.mouse_x)
            self._apply(self._targets_, self.value)
            if context.area is not None:
                context.area.header_text_set(None)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


# --- Multi-Cut: Ctrl+click edge loop, Shift snap step ----------------------------------------------

def edge_ring(edge, vert, t):
    """{edge: cut position from ``edge.verts[0]``} for the quad ring through ``edge``, cut at ``t`` from ``vert``.
    The ring stops at a face that is not a quad (that face is split by the cut, like Maya's loop end) and at
    borders."""
    out = {edge: t if vert is edge.verts[0] else 1.0 - t}
    for first in edge.link_loops:
        loop, a = first, vert
        while True:
            face = loop.face
            if len(face.verts) != 4:
                break
            opposite = loop.link_loop_next.link_loop_next
            e2 = opposite.edge
            # the end of the opposite edge that shares a side of this quad with ``a``
            a2 = opposite.link_loop_next.vert if loop.vert is a else opposite.vert
            if e2 in out:
                break           # closed ring
            out[e2] = t if a2 is e2.verts[0] else 1.0 - t
            others = [lo for lo in e2.link_loops if lo.face is not face]
            if len(others) != 1:
                break
            loop, a = others[0], a2
    return out


def insert_loop(bm, edge, t):
    """Insert Maya's edge loop through ``edge`` at ``t`` (from ``edge.verts[0]``). Returns the new edges."""
    ring = edge_ring(edge, edge.verts[0], t)
    res = bmesh.ops.subdivide_edges(bm, edges=list(ring), cuts=1, edge_percents=ring, use_grid_fill=True)
    return [e for e in res["geom_inner"] if isinstance(e, bmesh.types.BMEdge)]


class ALLSET_OT_multicut_loop(bpy.types.Operator):
    """Insert an edge loop where you click on the edge (Maya Multi-Cut Ctrl+click; Ctrl+MMB: in the middle,
    Ctrl+Shift: at a Snap Step)"""
    bl_idname = "allset.multicut_loop"
    bl_label = "Insert Edge Loop"
    bl_options = {'UNDO'}

    object: StringProperty(name="Object", options={'SKIP_SAVE', 'HIDDEN'})
    edge: IntProperty(name="Edge", default=-1, options={'SKIP_SAVE', 'HIDDEN'})
    factor: FloatProperty(name="Position", default=0.5, min=0.0, max=1.0, subtype='FACTOR',
                          description="Where the loop cuts the clicked edge")
    center: BoolProperty(name="Center", options={'SKIP_SAVE', 'HIDDEN'})
    snap: BoolProperty(name="Snap Step", options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        ob = bpy.data.objects.get(self.object) if self.object else context.edit_object
        if ob is None or ob.type != 'MESH' or ob.mode != 'EDIT':
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        if not 0 <= self.edge < len(bm.edges) or not 0.0 < self.factor < 1.0:
            return {'CANCELLED'}
        edges = insert_loop(bm, bm.edges[self.edge], self.factor)
        if not edges:
            return {'CANCELLED'}
        limit = math.radians(settings(context).smoothing_angle)   # Multi-Cut Smoothing Angle
        for e in edges:
            if len(e.link_faces) == 2:
                e.smooth = e.calc_face_angle(0.0) <= limit + 1e-6
        bmesh.update_edit_mesh(ob.data)
        return {'FINISHED'}

    def invoke(self, context, event):
        view = _view(context)
        if view is None:
            return {'PASS_THROUGH'}
        mouse = (event.mouse_region_x, event.mouse_region_y)
        ob, index = pick(view, _mesh_objects(context), mouse, 'EDGE', PICK_RADIUS * _ui_scale())
        if ob is None:
            return {'PASS_THROUGH'}
        bm = bmesh.from_edit_mesh(ob.data)
        bm.edges.ensure_lookup_table()
        t = 0.5 if self.center else edge_factor(view, ob, bm.edges[index], mouse)
        if self.snap:
            t = snap_factor(t, settings(context).snap_step, inner=True)
        self.object, self.edge, self.factor = ob.name, index, min(max(t, 0.01), 0.99)
        return self.execute(context)


# ALLSET_PG_mesh_tools is registered by register_props()
classes = (ALLSET_OT_target_weld, ALLSET_OT_crease_drag, ALLSET_OT_multicut_loop)


def clear():
    """Remove draw handlers a running modal left behind (add-on disabled mid-drag)."""
    for space, handle in _handles:
        try:
            space.draw_handler_remove(handle, 'WINDOW')
        except (ValueError, ReferenceError):
            pass
    _handles.clear()
