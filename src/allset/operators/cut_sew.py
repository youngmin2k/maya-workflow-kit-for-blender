# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya 3D Cut and Sew UV Tool.

UV > 3D Cut and Sew UV Tool switches to edge mode; in the 3D View an LMB drag
along edges cuts the UVs there, Ctrl+drag sews; tool keys x / s / d = Cut / Sew / Unfold + Layout (Maya
hotkeys); shell borders (Texture Borders) show thick. The cut / sew themselves are ``uv_tools.cut`` /
``sew``; the edge under the mouse is the pre-selection pick, so the red highlight is the edge a press takes.
"""

import bmesh
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from .. import results
from . import preselect, uv_tools

TOOL = "allset.cut_sew_tool"
STEP_PX = 4.0                         # drag samples: every 4 px between two mouse events
END_PX = 6.0                          # drag samples this close to an edge end don't count: at a corner the
                                      # side edges are as near as the next edge of the path
STROKE_RGB = (1.0, 0.85, 0.1)         # the edges a stroke collected (Maya draws the cut path yellow)
BORDER_RGB = (0.95, 0.95, 0.95)       # shell borders, thick (Maya Texture Borders)
BORDER_PX = 3.0
STROKE_PX = 3.0

ACTIONS = (("CUT", "Cut", "Maya: drag along edges cuts the UVs"),
           ("SEW", "Sew", "Maya: Ctrl+drag sews"),
           ("SELECT", "Select", "Shift+drag adds the edges to the selection (for x / s / d)"))


# --- pure helpers (tests/test_step79_cut_sew.py) ------------------------------------------------------

def stroke_points(a, b, step=STEP_PX):
    """Points from ``a`` (exclusive) to ``b`` (inclusive) at most ``step`` px apart."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = max(1, int((dx * dx + dy * dy) ** 0.5 // step) + 1)
    return [(a[0] + dx * k / n, a[1] + dy * k / n) for k in range(1, n + 1)]


def near_end(mouse, a, b, px=END_PX):
    """True when ``mouse`` is within ``px`` of either screen end ``a`` / ``b`` of an edge."""
    return any(p is not None and (p[0] - mouse[0]) ** 2 + (p[1] - mouse[1]) ** 2 <= px * px for p in (a, b))


def border_edges(bm, uv):
    """Edges on a UV shell border: a mesh border, or the two faces' UVs differ at a vertex (Maya Texture Borders)."""
    out = []
    for e in bm.edges:
        if e.hide:
            continue
        fs = [f for f in e.link_faces if not f.hide]
        if len(fs) == 1 or e.seam:     # a cut edge (seam) shows at once, also inside a shell
            out.append(e)
        elif len(fs) == 2:
            a, b = fs
            if not all(uv_tools._same(uv_tools._uv_at(a, v, uv), uv_tools._uv_at(b, v, uv)) for v in e.verts):
                out.append(e)
    return out


def apply(bm, uv, edges, action):
    """Cut / sew / select ``edges`` of one mesh; returns how many edges changed."""
    if action == "CUT":
        uv_tools.cut(bm, uv, edges)
        return len(edges)
    if action == "SEW":
        return uv_tools.sew(bm, uv, edges)
    for e in edges:
        e.select_set(True)
    return len(edges)


# --- drawing: shell borders while the tool is active, the stroke while dragging ------------------------

_border_cache = {}          # object pointer -> world line points
_stroke = {"edges": {}}     # object pointer -> set of edge indices (the running stroke)
_handle = []


def tool_active(context):
    return context.mode == 'EDIT_MESH' and preselect.tool_id(context) == TOOL


def _border_lines(ob):
    key = ob.as_pointer()
    lines = _border_cache.get(key)
    if lines is None:
        bm = bmesh.from_edit_mesh(ob.data)
        uv = bm.loops.layers.uv.active
        mw = ob.matrix_world
        lines = []
        if uv is not None:
            for e in border_edges(bm, uv):
                lines += [tuple(mw @ e.verts[0].co), tuple(mw @ e.verts[1].co)]
        _border_cache[key] = lines
    return lines


def _lines(shader, region, pts, rgb, px):
    if not pts:
        return
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", px)
    shader.uniform_float("color", (*rgb, 1.0))
    batch_for_shader(shader, 'LINES', {"pos": pts}).draw(shader)


def _draw():
    context = bpy.context
    try:
        if not tool_active(context):
            return
        scale = context.preferences.system.ui_scale or 1.0
        region = context.region
        shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')
        for ob in context.objects_in_mode_unique_data or ():
            if ob.type == 'MESH':
                _lines(shader, region, _border_lines(ob), BORDER_RGB, BORDER_PX * scale)
        gpu.state.depth_test_set('NONE')
        for ptr, idx in _stroke["edges"].items():
            c = preselect._cache_of(ptr)
            if c is None:
                continue
            pts = []
            for i in idx:
                pts += [tuple(c.co[c.edges[i, 0]]), tuple(c.co[c.edges[i, 1]])]
            _lines(shader, region, pts, STROKE_RGB, STROKE_PX * scale)
        gpu.state.blend_set('NONE')
    except (ReferenceError, AttributeError, IndexError):
        _border_cache.clear()


@bpy.app.handlers.persistent
def _invalidate(_scene=None, depsgraph=None):
    if depsgraph is not None and not any(
            isinstance(u.id, (bpy.types.Mesh, bpy.types.Object)) and (u.is_updated_geometry or u.is_updated_transform)
            for u in depsgraph.updates):
        return
    _border_cache.clear()


# --- operators ---------------------------------------------------------------------------------------

def _objects_by_ptr(context):
    return {ob.as_pointer(): ob for ob in context.objects_in_mode_unique_data or () if ob.type == 'MESH'}


class ALLSET_OT_cut_sew_stroke(bpy.types.Operator):
    """Drag along edges to cut their UVs; Ctrl = sew, Shift = select (Maya 3D Cut and Sew UV Tool)"""
    bl_idname = "allset.cut_sew_stroke"
    bl_label = "Cut / Sew UV Stroke"
    bl_options = {'UNDO'}

    action: bpy.props.EnumProperty(items=ACTIONS, name="Action", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.area is not None and context.area.type == 'VIEW_3D'

    def _collect(self, context, pts, first=False):
        from bpy_extras.view3d_utils import location_3d_to_region_2d
        from mathutils import Vector
        region, rv3d = context.region, context.region_data
        end = END_PX * (context.preferences.system.ui_scale or 1.0)
        for p in pts:
            hit = preselect.pick(context, region, rv3d, p)
            if hit is None or hit[1] != 'EDGE':
                continue
            if not first:
                c = preselect._cache_of(hit[0])
                if c is not None:
                    a, b = (location_3d_to_region_2d(region, rv3d, Vector(c.co[c.edges[hit[2], k]])) for k in (0, 1))
                    if near_end(p, a, b, end):
                        continue
            _stroke["edges"].setdefault(hit[0], set()).add(hit[2])

    def invoke(self, context, event):
        if context.region is None or context.region.type != 'WINDOW' or context.region_data is None:
            return {'PASS_THROUGH'}
        mode = tuple(context.scene.tool_settings.mesh_select_mode)
        if not mode[1]:        # Maya's tool works on edges: the pick follows the select mode
            context.scene.tool_settings.mesh_select_mode = (False, True, False)
        _stroke["edges"] = {}
        self._mouse = (event.mouse_region_x, event.mouse_region_y)
        self._collect(context, [self._mouse], first=True)
        if not _stroke["edges"]:
            return {'PASS_THROUGH'}     # not on an edge: Blender's select (tool fallback)
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            _stroke["edges"] = {}
            context.area.tag_redraw()
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            mouse = (event.mouse_region_x, event.mouse_region_y)
            self._collect(context, stroke_points(self._mouse, mouse))
            self._mouse = mouse
            context.area.tag_redraw()
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return self._finish(context)
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        stroke, _stroke["edges"] = _stroke["edges"], {}
        obs = _objects_by_ptr(context)
        done = 0
        for ptr, idx in stroke.items():
            ob = obs.get(ptr)
            if ob is None:
                continue
            bm = bmesh.from_edit_mesh(ob.data)
            bm.edges.ensure_lookup_table()
            uv = bm.loops.layers.uv.verify()
            edges = [bm.edges[i] for i in sorted(idx) if i < len(bm.edges)]
            done += apply(bm, uv, edges, self.action)
            bmesh.update_edit_mesh(ob.data)
        preselect.invalidate()
        _border_cache.clear()
        context.area.tag_redraw()
        if not done and self.action == "SEW":
            results.result(self, "No UV shells to sew along these edges")
        return {'FINISHED'}


class ALLSET_OT_uv_unfold_layout(bpy.types.Operator):
    """Unfold the UV shells, then lay them out (Maya 3D Cut and Sew d: UnfoldUV + LayoutUV)"""
    bl_idname = "allset.uv_unfold_layout"
    bl_label = "Unfold and Layout"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        s = uv_tools.settings(context)
        n = 0
        for ob in uv_tools._edit_meshes(context):
            n += uv_tools.unfold(context, ob)
            uv_tools.layout(context, ob, s.shell_padding, s.map_size)
        return {'FINISHED'} if n else {'CANCELLED'}


def _view3d_area(context):
    for window in ([context.window] if context.window else []) + list(context.window_manager.windows):
        areas = [a for a in window.screen.areas if a.type == 'VIEW_3D'] if window else []
        if areas:
            return window, max(areas, key=lambda a: a.width * a.height)
    return None, None


class ALLSET_OT_cut_sew_tool_set(bpy.types.Operator):
    """Edit the UVs on the model: drag along edges to cut, Ctrl+drag to sew (Maya 3D Cut and Sew UV Tool)"""
    bl_idname = "allset.cut_sew_tool_set"
    bl_label = "3D Cut and Sew UV Tool"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH'

    def execute(self, context):
        from . import maya_errors
        if context.mode != 'EDIT_MESH' and maya_errors.refuse_hidden(self, context.active_object):     # #187
            return {'CANCELLED'}
        window, area = _view3d_area(context)
        if area is None:
            self.report({'WARNING'}, "No 3D View to cut and sew in")
            return {'CANCELLED'}
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with context.temp_override(window=window, area=area, region=region):
            if context.mode != 'EDIT_MESH':
                bpy.ops.object.mode_set(mode='EDIT')
            context.scene.tool_settings.mesh_select_mode = (False, True, False)   # Maya 3D Cut and Sew tool: edges
            bpy.ops.wm.tool_set_by_id(name=TOOL)
        self.report({'INFO'}, "3D Cut and Sew UV Tool: drag = cut, Ctrl+drag = sew, x / s / d = Cut / Sew / Unfold")
        return {'FINISHED'}


classes = (ALLSET_OT_cut_sew_stroke, ALLSET_OT_uv_unfold_layout, ALLSET_OT_cut_sew_tool_set)


def register_handlers():
    if not _handle:
        _handle.append(bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW'))
    if _invalidate not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_invalidate)


def unregister_handlers():
    while _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle.pop(), 'WINDOW')
    if _invalidate in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_invalidate)
    _border_cache.clear()
    _stroke["edges"] = {}
