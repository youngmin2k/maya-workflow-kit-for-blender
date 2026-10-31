# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Create > Curve Tools drawing tools: CV Curve Tool, EP Curve Tool, Three / Two Point Circular Arc.

Window-level modals like the Joint Tool (operators/joints.py): menus / shelf invoke them from any context and
each click finds the 3D View WINDOW region under the mouse itself (not the Tool Box column). Maya places curve points on
the ground grid in a perspective view (Blender z = 0) and on the view plane through the origin in orthographic views
(same rule as the Joint Tool, ``joints.click_point``).

Keys (Maya curve contexts): LMB press = new point, drag = move it, release = place it; Enter = finish (CV: degree + 1
points, EP: 2 points, else the tool keeps waiting); Backspace / Delete = remove the last point; Esc or a tool key
(q / w / e / r / y) = stop without a curve; MMB drag = move the last placed point (Maya: middle-drag the most recent
point). Snaps while placing or moving a point (Issue #208, operators/curve_snap.py): hold X = grid (Maya grid spacing /
divisions), hold C = the nearest curve / polygon edge under the cursor (dragging slides along it), hold V = the nearest
CV / vertex / pivot; the Status Line snap buttons (Blender's scene snapping) snap too and Ctrl inverts them while
clicking, like Blender. The arcs finish
on the release of their last click (3 / 2 points). The curve itself comes from ``curves_maya`` (``make_cv_curve`` /
``make_ep_curve`` / ``make_arc3`` / ``make_arc2``) and is named ``curveN`` / ``curveShapeN``. UNDO only (no redo panel):
one undo step per finished curve.
"""

import json

import bpy
import gpu
from bpy.props import IntProperty, StringProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import curve_snap, curves_maya, keystate, naming, units

CV, EP, ARC3, ARC2 = "CV", "EP", "ARC3", "ARC2"
LABELS = {CV: "CV Curve Tool", EP: "EP Curve Tool", ARC3: "Three Point Circular Arc", ARC2: "Two Point Circular Arc"}
STATUS = {
    CV: "CV Curve Tool: click to place CVs, Enter to finish, Backspace: remove the last CV, middle-drag: move it "
        "(Esc: stop, hold X / C / V: snap to grid / curve / point)",
    EP: "EP Curve Tool: click to place edit points, Enter to finish, Backspace: remove the last point, middle-drag: "
        "move it (Esc: stop, hold X / C / V: snap to grid / curve / point)",
    ARC3: "Three Point Circular Arc: click the start, a point on the arc and the end "
          "(Esc: stop, hold X / C / V: snap to grid / curve / point)",
    ARC2: "Two Point Circular Arc: click the start and the end (Esc: stop, hold X / C / V: snap to grid / curve / point)",
}
SNAP_KEYS = {'X': "grid", 'C': "curve", 'V': "point"}     # Maya snap holds (curve_snap.GRID / CURVE / POINT)
TOOL_KEYS = {'Q', 'W', 'E', 'R', 'Y', 'T'}
POINT_RGB = (0.95, 0.35, 0.95)      # Maya draws pending CVs / EPs in magenta-ish component colour
LINE_RGB = (0.8, 0.8, 0.8)
POINT_PX = 7.0
LINE_PX = 1.5


# --- pure parts (headless-testable) ------------------------------------------------------------

def needed(kind, degree=3):
    """Points a curve of ``kind`` needs before it can be made."""
    return {CV: degree + 1, EP: 2, ARC3: 3, ARC2: 2}[kind]


def auto_finish(kind):
    """Arcs finish on their last click; CV / EP curves wait for Enter."""
    return kind in (ARC3, ARC2)


class Drawing:
    """The point list of one curve being drawn (world coordinates, scene units)."""

    def __init__(self, kind, degree=3):
        self.kind, self.degree = kind, degree
        self.points = []
        self.dragging = False

    def press(self, p):
        """LMB press: a new point (arcs take no more than their count)."""
        if auto_finish(self.kind) and len(self.points) >= needed(self.kind):
            return False
        self.points.append(Vector(p))
        self.dragging = True
        return True

    def drag(self, p):
        if self.dragging and self.points:
            self.points[-1] = Vector(p)

    def move_last(self, p):
        """MMB drag: the most recent point follows the cursor (Maya)."""
        if self.points and not self.dragging:
            self.points[-1] = Vector(p)
            return True
        return False

    def release(self, p=None):
        """LMB release: the point is placed; True when an arc is complete now."""
        if p is not None:
            self.drag(p)
        was = self.dragging
        self.dragging = False
        return was and auto_finish(self.kind) and len(self.points) >= needed(self.kind)

    def pop(self):
        if self.points:
            self.points.pop()
        self.dragging = False

    def can_finish(self):
        return len(self.points) >= needed(self.kind, self.degree)


def make(context, kind, points, degree=3, sections=8):
    """Make the Maya curve for the clicked ``points`` through curves_maya; named ``curveN``. Arcs: Maya's Arc
    Settings degree 1 / 3 and sections (factory 3 / 8)."""
    pts = [Vector(p) for p in points]
    if kind == CV:
        ob = curves_maya.make_cv_curve(context, pts, degree)
    elif kind == EP:
        ob = curves_maya.make_ep_curve(context, pts, degree)
    else:
        kw = {} if (degree, sections) == (3, 8) else {"sections": sections, "degree": degree}   # factory: as before
        if kind == ARC3:
            ob = curves_maya.make_arc3(context, pts[0], pts[1], pts[2], **kw)
        else:
            ob = curves_maya.make_arc2(context, pts[0], pts[1], **kw)
    if ob is not None:
        naming.apply_maya_name(ob, "curve")
    return ob


def plane_point(region, rv3d, coord):
    """World point for a click: a perspective view hits the ground (z = 0), an orthographic view (or a perspective
    ray that misses the ground) lands on the view plane through the origin (Maya curve tools)."""
    origin = Vector((0.0, 0.0, 0.0))
    if rv3d.is_perspective:
        start = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        if abs(ray.z) > 1e-6:
            t = -start.z / ray.z
            if t > 0:
                p = start + ray * t
                return Vector((p.x, p.y, 0.0))
    p = view3d_utils.region_2d_to_location_3d(region, rv3d, coord, origin)
    d = rv3d.view_matrix.inverted().to_3x3() @ Vector((0.0, 0.0, 1.0))    # view axis (towards the viewer)
    if d.length > 1e-9:
        d.normalize()
        p = p - d * p.dot(d)                                               # exactly on the plane through the origin
    return Vector(0.0 if abs(c) < 1e-9 else c for c in p)


def grid_step(scene=None):
    """Maya X snap step in scene units: grid line spacing / subdivisions (factory 5 / 5 = 1 Maya unit)."""
    try:
        from . import option_windows_display
        g = option_windows_display.grid_settings()
        step = float(g["spacing"]) / max(int(g["divisions"]), 1)
    except (ImportError, KeyError, TypeError, ValueError, AttributeError):
        step = 1.0
    return max(step, 1e-6) * units.maya_unit(scene)


def snap_grid(p, step):
    return Vector(round(c / step) * step for c in p)


# --- preview -----------------------------------------------------------------------------------

STATE = {"points": [], "kind": None, "owner": None}
LAST = {"kind": None, "points": []}       # the last finished drawing (clicked points), for tests / tools
_handles = []


def _draw_view():
    pts = [tuple(p) for p in STATE["points"]]
    if not pts:
        return
    try:
        from ..ui import toolbox
        context = bpy.context
        if toolbox.is_toolbox(context.space_data):
            return
        region = context.region
        scale = context.preferences.system.ui_scale or 1.0
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        if len(pts) > 1:
            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
            shader.uniform_float("viewportSize", (region.width, region.height))
            shader.uniform_float("lineWidth", LINE_PX * scale)
            shader.uniform_float("color", (*LINE_RGB, 1.0))
            batch_for_shader(shader, 'LINES', {"pos": [q for a, b in zip(pts, pts[1:]) for q in (a, b)]}).draw(shader)
        shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
        gpu.state.point_size_set(POINT_PX * scale)
        shader.uniform_float("color", (*POINT_RGB, 1.0))
        batch_for_shader(shader, 'POINTS', {"pos": pts}).draw(shader)
        gpu.state.blend_set('NONE')
    except (ReferenceError, AttributeError, ValueError):
        pass


def _add_handler():
    if not _handles:
        _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw_view, (), 'WINDOW', 'POST_VIEW'))


def _remove_handler():
    while _handles:
        bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), 'WINDOW')


def _redraw(window):
    if window is None:
        return
    for area in window.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


# --- the modal ---------------------------------------------------------------------------------

def _ui_scale(context):
    try:
        return context.preferences.system.ui_scale or 1.0
    except AttributeError:
        return 1.0


class _CurveDrawTool:
    bl_options = {'UNDO'}
    kind = CV
    points: StringProperty(options={'SKIP_SAVE', 'HIDDEN'},
                           description="JSON list of world points: make the curve without clicks (scripts)")

    def _degree(self):
        return 3

    def _sections(self):
        return 8

    def execute(self, context):
        """Without clicks (scripts; a background INVOKE runs this): the curve through ``points`` (JSON world points)."""
        try:
            pts = [Vector(p) for p in json.loads(self.points)] if self.points else []
        except (ValueError, TypeError):
            pts = []
        if len(pts) < needed(self.kind, self._degree()):
            self.report({'WARNING'}, f"{LABELS[self.kind]}: click in a view to place points")
            return {'CANCELLED'}
        if context.active_object is not None and context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        ob = make(context, self.kind, pts[:needed(self.kind)] if auto_finish(self.kind) else pts, self._degree(),
                  self._sections())
        return {'FINISHED'} if ob is not None else {'CANCELLED'}

    def invoke(self, context, event):
        if context.window is None:
            return self.execute(context)
        self._drawing = Drawing(self.kind, self._degree())
        self._held = {}            # held snap key -> curve_snap mode
        self._targets = None       # snap targets, gathered once per press
        self._mmb = False          # MMB drag of the last point
        self._last_view = None
        STATE.update(points=self._drawing.points, kind=self.kind, owner=self)
        _add_handler()
        context.workspace.status_text_set(STATUS[self.kind])
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self, context):
        if STATE["owner"] is self:
            STATE.update(points=[], kind=None, owner=None)
            _remove_handler()
        try:
            context.workspace.status_text_set(None)
        except (AttributeError, ReferenceError):
            pass
        _redraw(context.window)

    def _point(self, context, event):
        from .joints import view_under
        hit = view_under(context.window, event.mouse_x, event.mouse_y)
        if hit is None:
            return None
        area, region = hit
        self._last_view = (area, region)
        rv3d = region.data
        mouse = (event.mouse_x - region.x, event.mouse_y - region.y)
        modes = self._modes(context, event)
        if modes - {curve_snap.GRID}:
            if self._targets is None:
                try:
                    space = area.spaces.active
                except (AttributeError, ReferenceError):
                    space = None
                self._targets = curve_snap.gather(context, space)
            surface = curve_snap.surface_under(context, region, rv3d) if curve_snap.SURFACE in modes else None
            p = curve_snap.snap_to(self._targets, modes, mouse, rv3d.perspective_matrix, region.width,
                                   region.height, curve_snap.CURVE_RADIUS_PX * _ui_scale(context), surface)
            if p is not None:
                return p
        p = plane_point(region, rv3d, mouse)
        if curve_snap.GRID in modes:
            p = snap_grid(p, grid_step(context.scene))
        return p

    def _modes(self, context, event):
        """Snaps for this event: the held X / C / V keys plus Blender's scene snapping (Ctrl inverts it)."""
        ts = context.scene.tool_settings
        return set(self._held.values()) | curve_snap.scene_modes(ts.use_snap, ts.snap_elements, event.ctrl)

    def _drop_released_keys(self):
        """A snap key RELEASE another handler took: drop the hold once the key is up."""
        for key in [k for k in self._held if keystate.is_down(k) is False]:
            del self._held[key]

    def modal(self, context, event):
        d = self._drawing
        if STATE["owner"] is not self:          # another curve tool started: this one stops
            self._end(context)
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.type in SNAP_KEYS and not (event.ctrl or event.alt or event.oskey):
            if event.value == 'PRESS':           # Maya: Shift+x / c / v are the same holds
                if event.type not in self._held:
                    self._held[event.type] = SNAP_KEYS[event.type]
                    self._targets = None
            elif event.value == 'RELEASE':
                self._held.pop(event.type, None)
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE' and self._held:
            self._drop_released_keys()
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            if d.can_finish():
                return self._done(context)
            self.report({'WARNING'}, f"{LABELS[self.kind]}: place at least {needed(self.kind, d.degree)} points")
            return {'RUNNING_MODAL'}
        if event.type in {'BACK_SPACE', 'DEL'} and event.value == 'PRESS':
            d.pop()
            _redraw(context.window)
            return {'RUNNING_MODAL'}
        if event.type == 'ESC' and event.value == 'PRESS':
            self._end(context)
            return {'CANCELLED'}
        if event.type in TOOL_KEYS and event.value == 'PRESS' and not (event.ctrl or event.alt or event.oskey):
            self._end(context)
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE' and (d.dragging or self._mmb):
            p = self._point(context, event)
            if p is not None:
                if self._mmb:
                    d.move_last(p)
                else:
                    d.drag(p)
                _redraw(context.window)
            return {'RUNNING_MODAL'}
        if event.type == 'MIDDLEMOUSE':
            # Maya: middle-drag moves the most recent point (Alt+MMB stays the view track)
            if event.value == 'PRESS' and d.points and not d.dragging \
                    and not (event.alt or event.shift or event.oskey):
                self._targets = None
                p = self._point(context, event)
                if p is not None:
                    self._mmb = True
                    d.move_last(p)
                    _redraw(context.window)
                    return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE' and self._mmb:
                self._mmb = False
                p = self._point(context, event)
                if p is not None:
                    d.move_last(p)
                _redraw(context.window)
                return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE':
            # Ctrl+click places the point with Blender's snapping inverted (Blender's Ctrl snap toggle)
            if event.value == 'PRESS' and not self._mmb and not (event.alt or event.shift or event.oskey):
                self._targets = None
                p = self._point(context, event)
                if p is not None and d.press(p):
                    _redraw(context.window)
                    return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE' and d.dragging:
                p = self._point(context, event)
                complete = d.release(p)
                _redraw(context.window)
                if complete:
                    return self._done(context)
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def _done(self, context):
        d = self._drawing
        pts = list(d.points)
        self._end(context)
        hit = self._last_view
        try:
            ok = hit is not None and hit[0].type == 'VIEW_3D'
        except ReferenceError:
            ok = False
        override = dict(window=context.window, area=hit[0], region=hit[1]) if ok else dict(window=context.window)
        with context.temp_override(**override):
            if context.active_object is not None and context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            ob = make(context, self.kind, pts, d.degree, self._sections())
        if ob is None:
            return {'CANCELLED'}
        LAST.update(kind=self.kind, points=[p.copy() for p in pts])
        from ..command_line import show_result      # Maya prints the result in the Command Line
        show_result(f"Result: {ob.name}")
        return {'FINISHED'}


class ALLSET_OT_cv_curve_tool(_CurveDrawTool, bpy.types.Operator):
    """Maya CV Curve Tool: click to place CVs (drag to move the new one), Enter to finish, Backspace removes the last"""
    bl_idname = "allset.cv_curve_tool"
    bl_label = "CV Curve Tool"
    bl_options = {'UNDO'}
    kind = CV

    degree: IntProperty(name="Curve degree", default=3, min=1, max=7)

    def _degree(self):
        return self.degree


class ALLSET_OT_ep_curve_tool(_CurveDrawTool, bpy.types.Operator):
    """Maya EP Curve Tool: click edit points the curve passes through, Enter to finish, Backspace removes the last"""
    bl_idname = "allset.ep_curve_tool"
    bl_label = "EP Curve Tool"
    bl_options = {'UNDO'}
    kind = EP

    degree: IntProperty(name="Curve degree", default=3, min=1, max=7)

    def _degree(self):
        return self.degree


class ALLSET_OT_arc3_tool(_CurveDrawTool, bpy.types.Operator):
    """Maya Three Point Circular Arc: click the start, a point on the arc and the end"""
    bl_idname = "allset.arc3_tool"
    bl_label = "Three Point Circular Arc"
    bl_options = {'UNDO'}
    kind = ARC3

    degree: IntProperty(name="Circular arc degree", default=3, min=1, max=3)   # Maya: 1 Linear / 3
    sections: IntProperty(name="Sections", default=8, min=4, max=200)

    def _degree(self):
        return 1 if self.degree < 3 else 3

    def _sections(self):
        return self.sections


class ALLSET_OT_arc2_tool(_CurveDrawTool, bpy.types.Operator):
    """Maya Two Point Circular Arc: click the start and the end"""
    bl_idname = "allset.arc2_tool"
    bl_label = "Two Point Circular Arc"
    bl_options = {'UNDO'}
    kind = ARC2

    degree: IntProperty(name="Circular arc degree", default=3, min=1, max=3)
    sections: IntProperty(name="Sections", default=8, min=4, max=200)

    def _degree(self):
        return 1 if self.degree < 3 else 3

    def _sections(self):
        return self.sections


classes = (ALLSET_OT_cv_curve_tool, ALLSET_OT_ep_curve_tool, ALLSET_OT_arc3_tool, ALLSET_OT_arc2_tool)


def unregister_handlers():
    """Drop a running tool's preview (operators/__init__ registers ``classes``)."""
    STATE.update(points=[], kind=None, owner=None)
    _remove_handler()
