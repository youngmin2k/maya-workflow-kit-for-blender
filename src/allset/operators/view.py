# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya camera/view feel: ortho tumble lock, Alt+Shift axis-locked tumble/track, framing in all views,
view-change undo (``[`` / ``]``), Space-tap four-view toggle.
"""

import bpy
from mathutils import Vector

from .. import results
from . import framing, units

# --- tumble -------------------------------------------------------------------


def tumble_locked(rv3d, lock):
    """Maya top/front/side views do not tumble."""
    return bool(lock) and rv3d.view_perspective == 'ORTHO' and rv3d.is_orthographic_side_view


def camera_navigation(context):
    """Maya: tumbling a view that looks through a camera moves that camera (#9). Blender leaves the camera view
    unless the view's Lock Camera to View is on, so turn it on there; a Maya-locked camera (locked channels) stays
    put because Blender's camera lock keeps locked channels."""
    space, rv3d = context.space_data, context.region_data
    if space is not None and space.type == 'VIEW_3D' and rv3d is not None and rv3d.view_perspective == 'CAMERA':
        space.lock_camera = True


class ALLSET_OT_tumble(bpy.types.Operator):
    """Tumble the view (Maya Alt+LMB); locked in axis-aligned ortho views"""
    bl_idname = "allset.tumble"
    bl_label = "Tumble"

    @classmethod
    def poll(cls, context):
        return context.region_data is not None

    def invoke(self, context, event):
        from .. import preferences
        if tumble_locked(context.region_data, preferences.get(context).lock_ortho_tumble):
            return {'FINISHED'}
        camera_navigation(context)
        bpy.ops.view3d.rotate('INVOKE_DEFAULT')
        return {'FINISHED'}


def emulated_alt_drag(context):
    """True when a middle press is really Alt+LMB turned into a middle drag by Blender's Emulate 3 Button Mouse
    (with Alt as its modifier): the converted press carries no Alt, but the Alt key is still held. None-safe: an
    OS that can't tell whether Alt is held gives False, so a real middle drag is never taken."""
    inputs = context.preferences.inputs
    if not getattr(inputs, "use_mouse_emulate_3_button", False):
        return False
    if getattr(inputs, "mouse_emulate_3_button_modifier", 'ALT') != 'ALT':
        return False
    from . import keystate
    return bool(keystate.is_down('LEFT_ALT') or keystate.is_down('RIGHT_ALT'))


class ALLSET_OT_emulated_tumble(bpy.types.Operator):
    """Alt+LMB tumble while Emulate 3 Button Mouse is on (Blender delivers that drag as a middle drag)"""
    bl_idname = "allset.emulated_tumble"
    bl_label = "Tumble (Emulated Middle Mouse)"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.region_data is not None

    def invoke(self, context, event):
        if event.alt or not emulated_alt_drag(context):
            return {'PASS_THROUGH'}
        return ALLSET_OT_tumble.invoke(self, context, event)


# --- Alt+RMB dolly (#51) -----------------------------------------------------------------
# Maya dollies with a left / right drag. Blender's view3d.zoom reads the drag axis from the
# user preferences (Vertical by default), which the kit no longer writes (#40), so the drag is read here.
DOLLY_PX_PER_DOUBLING = 150.0     # px of drag (at UI scale 1) that halve / double the view distance


def dolly_distance(distance0, dx, dy, ui_scale=1.0, invert=False):
    """View distance after a dolly drag of (dx, dy) px from ``distance0``: right (or up) = in,
    left (or down) = in with ``invert`` (Blender's Invert Zoom Direction preference)."""
    step = (dx + dy) / (DOLLY_PX_PER_DOUBLING * max(ui_scale, 0.1))
    return distance0 * (2.0 ** (step if invert else -step))


def invert_zoom(context):
    """Blender's Preferences > Input > Invert Zoom Direction (drag zoom), read only (#295)."""
    return bool(getattr(context.preferences.inputs, "invert_mouse_zoom", False))


class ALLSET_OT_dolly(bpy.types.Operator):
    """Dolly the view in / out with a left / right drag (Maya Alt+RMB)"""
    bl_idname = "allset.dolly"
    bl_label = "Dolly"
    bl_options = {'GRAB_CURSOR', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return context.region_data is not None

    def invoke(self, context, event):
        rv3d = context.region_data
        if rv3d.view_perspective == 'CAMERA':
            camera_navigation(context)           # through a camera: Blender's zoom moves it (#9)
            bpy.ops.view3d.zoom('INVOKE_DEFAULT')
            return {'FINISHED'}
        self._start = (event.mouse_x, event.mouse_y)
        self._d0 = rv3d.view_distance
        # the button that started it: RMB for Alt+RMB, LMB for the Dolly Tool (ui/camera_tools.py)
        self._button = event.type if event.type in {'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE'} else 'RIGHTMOUSE'
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        rv3d = context.region_data
        if event.type == 'MOUSEMOVE':
            dx = event.mouse_x - self._start[0]
            dy = event.mouse_y - self._start[1]
            rv3d.view_distance = dolly_distance(self._d0, dx, dy, context.preferences.system.ui_scale or 1.0,
                                                invert_zoom(context))
            context.area.tag_redraw()
        elif event.type == self._button and event.value == 'RELEASE':
            return {'FINISHED'}
        elif event.type == 'ESC' and event.value == 'PRESS':
            rv3d.view_distance = self._d0
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


# --- Alt+RMB dolly in the UV / Image Editor (B4) ---------------------------------
# Maya dollies 2D panels with Alt+RMB too. IC's image.view_zoom reads the drag axis
# from Blender's Zoom Axis preference (factory Vertical), so like allset.dolly the drag is read here and applied with
# a plain image.view_zoom call with a factor (centred, like Blender's factory "Zoom to Mouse Position" off).


def dolly_zoom_factor(dx, dy, ui_scale=1.0, invert=False):
    """Zoom factor for a drag step of (dx, dy) px: the inverse of ``dolly_distance`` (right / up = in,
    reversed with ``invert``)."""
    step = (dx + dy) / (DOLLY_PX_PER_DOUBLING * max(ui_scale, 0.1))
    return 2.0 ** (-step if invert else step)


class ALLSET_OT_dolly_2d(bpy.types.Operator):
    """Zoom the UV / Image Editor in / out with a left / right drag (Maya Alt+RMB dolly)"""
    bl_idname = "allset.dolly_2d"
    bl_label = "Dolly 2D"
    bl_options = {'GRAB_CURSOR', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'IMAGE_EDITOR'

    def invoke(self, context, event):
        self._last = (event.mouse_x, event.mouse_y)
        # the button that started it ends it (modal() reads this)
        self._button = event.type if event.type in {'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE'} else 'RIGHTMOUSE'
        self._zoom0 = tuple(context.space_data.zoom)
        self.applied = 1.0
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def step(self, context, dx, dy):
        """Zoom by one drag step."""
        factor = dolly_zoom_factor(dx, dy, context.preferences.system.ui_scale or 1.0, invert_zoom(context))
        if abs(factor - 1.0) > 1e-6:
            bpy.ops.image.view_zoom('EXEC_DEFAULT', factor=factor)
            self.applied *= factor
        return factor

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            dx, dy = event.mouse_x - self._last[0], event.mouse_y - self._last[1]
            self._last = (event.mouse_x, event.mouse_y)
            self.step(context, dx, dy)
            context.area.tag_redraw()
        elif event.type == self._button and event.value == 'RELEASE':
            return {'FINISHED'}
        elif event.type == 'ESC' and event.value == 'PRESS':
            zoom = context.space_data.zoom[0] or 1.0     # zoom limits may have kept some steps out
            bpy.ops.image.view_zoom('EXEC_DEFAULT', factor=self._zoom0[0] / zoom if self._zoom0[0] else 1.0)
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


# --- Alt+Shift drag: tumble / track locked to one axis ---------------------
# Maya : the first dominant drag direction (horizontal or
# vertical) is kept for the whole drag.

AXIS_THRESHOLD = 4   # px of movement before the axis is chosen


def choose_axis(dx, dy, threshold=AXIS_THRESHOLD):
    """'H', 'V' or None (not moved far enough yet)."""
    if max(abs(dx), abs(dy)) < threshold:
        return None
    return 'H' if abs(dx) >= abs(dy) else 'V'


def locked_offset(axis, dx, dy):
    """The drag offset kept for ``axis``."""
    return (dx, 0) if axis == 'H' else (0, dy)


def tumble_rotation(axis, dx, dy, rotation0, sensitivity):
    """Blender turntable rotation (view3d_navigate_rotate: Z by x, view right axis by y),
    one axis only. Returns the new ``view_rotation``."""
    from mathutils import Quaternion
    if axis == 'H':
        return Quaternion((0.0, 0.0, 1.0), -sensitivity * dx) @ rotation0
    right = rotation0 @ Vector((1.0, 0.0, 0.0))
    return Quaternion(right, sensitivity * dy) @ rotation0


class ALLSET_OT_view_axis_lock(bpy.types.Operator):
    """Tumble or track the view along one axis only (Maya Alt+Shift+drag)"""
    bl_idname = "allset.view_axis_lock"
    bl_label = "Axis-Locked Tumble/Track"
    bl_options = {'BLOCKING'}

    mode: bpy.props.EnumProperty(items=(("TUMBLE", "Tumble", ""), ("TRACK", "Track", "")))

    @classmethod
    def poll(cls, context):
        return context.region_data is not None and context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        from .. import preferences
        rv3d = context.region_data
        if self.mode == "TUMBLE" and tumble_locked(rv3d, preferences.get(context).lock_ortho_tumble):
            return {'FINISHED'}
        self._button = event.type
        self._start = (event.mouse_region_x, event.mouse_region_y)
        self._rot0 = rv3d.view_rotation.copy()
        self._loc0 = rv3d.view_location.copy()
        self._axis = None
        inputs = context.preferences.inputs
        self._sens = inputs.view_rotate_sensitivity_turntable / max(context.preferences.system.ui_scale, 0.1)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _apply(self, context, x, y):
        rv3d = context.region_data
        dx, dy = x - self._start[0], y - self._start[1]
        if self._axis is None:
            self._axis = choose_axis(dx, dy)
            if self._axis is None:
                return
        ox, oy = locked_offset(self._axis, dx, dy)
        if self.mode == "TUMBLE":
            rv3d.view_rotation = tumble_rotation(self._axis, ox, oy, self._rot0, self._sens)
            return
        from bpy_extras.view3d_utils import region_2d_to_location_3d
        sx, sy = self._start
        a = region_2d_to_location_3d(context.region, rv3d, (sx, sy), self._loc0)
        b = region_2d_to_location_3d(context.region, rv3d, (sx + ox, sy + oy), self._loc0)
        rv3d.view_location = self._loc0 - (b - a)

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            self._apply(context, event.mouse_region_x, event.mouse_region_y)
            context.area.tag_redraw()
        elif event.type == self._button and event.value == 'RELEASE':
            return {'FINISHED'}
        elif event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            rv3d = context.region_data
            rv3d.view_rotation, rv3d.view_location = self._rot0, self._loc0
            context.area.tag_redraw()
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


# --- framing ------------------------------------------------------------------


def view3d_window_regions(window):
    """(area, region) for every 3D view WINDOW region (quad views: all four)."""
    for area in window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type == 'WINDOW':
                yield area, region


# Object types whose evaluated bounding box is framed; others count as a point.
_BOX_TYPES = {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'CURVES', 'POINTCLOUD', 'VOLUME',
              'GREASEPENCIL', 'LATTICE', 'ARMATURE'}


def _object_points(ob, depsgraph):
    mw = ob.matrix_world
    if ob.type in _BOX_TYPES:
        ev = ob.evaluated_get(depsgraph)
        return [mw @ Vector(c) for c in ev.bound_box]
    return [mw.translation.copy()]


def _visible(ob, view_layer, v3d):
    try:
        return ob.visible_get(view_layer=view_layer) and ob.visible_in_viewport_get(v3d)
    except RuntimeError:   # not in this view layer
        return False


def frame_points(context, v3d, selected, children, exclude=None):
    """World points to frame (Maya F / Ctrl+Shift+F / A), or None if this mode is left to
    Blender's own operator (curve/armature edit, pose, paint and sculpt modes). ``exclude``: an object left out
    (the camera a view looks through)."""
    vl, dg = context.view_layer, context.evaluated_depsgraph_get()
    mode = context.mode
    if not selected:   # A / Shift+A: every visible object, in any mode (Maya Frame All)
        return [p for ob in vl.objects if ob != exclude and _visible(ob, vl, v3d) for p in _object_points(ob, dg)]
    if mode == 'EDIT_MESH':
        pts = []
        objs = list(context.objects_in_mode_unique_data)
        for ob in objs:
            ob.update_from_editmode()
            mw = ob.matrix_world
            pts.extend(mw @ v.co for v in ob.data.vertices if v.select)
        if pts:
            return pts
        # No components selected: frame the objects (Maya frames the whole shape).
        return [p for ob in objs for p in _object_points(ob, dg)] or None
    if mode != 'OBJECT':
        return None
    objs = [ob for ob in vl.objects if ob != exclude and _visible(ob, vl, v3d)]
    sel = [ob for ob in objs if ob.select_get()]
    if children:
        seen = {ob.name for ob in sel}
        for ob in list(sel):
            for ch in ob.children_recursive:
                if ch.name not in seen and _visible(ch, vl, v3d):
                    seen.add(ch.name)
                    sel.append(ch)
    objs = sel or objs    # nothing selected: Maya F frames everything
    return [p for ob in objs for p in _object_points(ob, dg)]


def _others(area, region):
    return [(r.x, r.y, r.width, r.height) for r in area.regions
            if r.type in {'UI', 'TOOLS', 'HEADER', 'TOOL_HEADER', 'ASSET_SHELF',
                          'ASSET_SHELF_HEADER'} and r != region]


def visible_bounds(area, region):
    """Region-local (x0, y0, x1, y1) not covered by the sidebar/toolbar (Region Overlap)."""
    return framing.visible_rect((region.x, region.y, region.width, region.height),
                                _others(area, region))


def frame_region(context, area, region, selected=True, children=False):
    """Frame in one 3D view region the Maya way (fit 0.95 of the part not under the
    sidebar/toolbar). Falls back to Blender's view_selected / view_all."""
    rv3d, v3d = region.data, area.spaces.active
    points = None
    if rv3d is not None and rv3d.view_perspective == 'CAMERA':
        # Maya: F / A in a camera view move that camera (#9); Blender's view_selected would leave the camera view
        cam = view_camera(context, v3d)
        if cam is None:
            return False
        points = frame_points(context, v3d, selected, children, exclude=cam)
        if not points:
            return False
        if not frame_camera(context, cam, points):
            return False
        try:
            bpy.ops.ed.undo_push(message="Frame Camera")
        except RuntimeError:
            pass
        return True
    if rv3d is not None:
        points = frame_points(context, v3d, selected, children)
    if not points:
        with context.temp_override(area=area, region=region):
            if selected:
                return bpy.ops.view3d.view_selected() == {'FINISHED'}
            return bpy.ops.view3d.view_all(center=False) == {'FINISHED'}
    rect = visible_bounds(area, region)
    loc, dist = framing.fit(points, rv3d.view_rotation, rv3d.window_matrix.copy(),
                            rv3d.view_distance, rv3d.view_perspective == 'ORTHO',
                            (region.width, region.height), rect,
                            min_half=framing.MIN_HALF * units.maya_unit(context.scene))
    rv3d.view_location = loc
    rv3d.view_distance = dist
    region.tag_redraw()
    return True


def view_camera(context, v3d):
    """The object a camera view looks through (the view's local camera or the scene camera)."""
    if v3d.use_local_camera and v3d.camera is not None:
        return v3d.camera
    return context.scene.camera


def camera_projection(context, cam):
    """(window matrix, (width, height)) of the camera's frame at the render resolution."""
    r = context.scene.render
    w, h = max(r.resolution_x, 1), max(r.resolution_y, 1)
    win = cam.calc_matrix_camera(context.evaluated_depsgraph_get(), x=w, y=h,
                                 scale_x=r.pixel_aspect_x, scale_y=r.pixel_aspect_y)
    return win, (w, h)


def frame_camera(context, cam, points):
    """Move ``cam`` so ``points`` fill 0.95 of its frame, keeping its orientation (Maya framing in a camera
    view dollies / tracks the camera; an orthographic camera changes its width). A locked camera (Maya Lock Camera,
    ui/panel_menus.camera_locked) stays. Returns True when the camera moved."""
    if all(cam.lock_location):
        return False
    mw = cam.matrix_world
    loc0, rot, scale = mw.decompose()
    rot = rot.normalized()
    ortho = cam.type == 'CAMERA' and cam.data.type == 'ORTHO'
    win, size = camera_projection(context, cam) if cam.type == 'CAMERA' else (None, None)
    if win is None:
        return False
    centre = sum((Vector(p) for p in points), Vector()) / len(points)
    forward = rot @ Vector((0.0, 0.0, -1.0))
    dist0 = max((centre - loc0).dot(forward), 1e-3)
    loc, dist = framing.fit(points, rot, win, dist0, ortho, size, (0.0, 0.0, size[0], size[1]),
                            min_half=framing.MIN_HALF * units.maya_unit(context.scene))
    if ortho:
        cam.data.ortho_scale *= dist / dist0
        dist = dist0
    from mathutils import Matrix
    new = loc + rot @ Vector((0.0, 0.0, dist))
    cam.matrix_world = Matrix.LocRotScale(new, rot, scale)
    return True


class ALLSET_OT_frame(bpy.types.Operator):
    """Frame the selection (or everything) in this view with Maya's fit (F, A, Ctrl+Shift+F)"""
    bl_idname = "allset.frame"
    bl_label = "Frame"

    # SKIP_SAVE: keymap items set only some of these; a remembered children=True from
    # Ctrl+Shift+F must not leak into the next Shift+F.
    selected: bpy.props.BoolProperty(name="Selected", default=True, options={'SKIP_SAVE'})
    children: bpy.props.BoolProperty(name="With Children", default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and             context.region is not None and context.region.type == 'WINDOW'

    def execute(self, context):
        ok = frame_region(context, context.area, context.region, self.selected, self.children)
        return {'FINISHED'} if ok else {'CANCELLED'}


class ALLSET_OT_frame_all_views(bpy.types.Operator):
    """Frame the selection (or everything) in every 3D view (Maya Shift+F / Shift+A /
    Ctrl+Shift+F)"""
    bl_idname = "allset.frame_all_views"
    bl_label = "Frame in All Views"

    # SKIP_SAVE: keymap items set only some of these; a remembered children=True from
    # Ctrl+Shift+F must not leak into the next Shift+F.
    selected: bpy.props.BoolProperty(name="Selected", default=True, options={'SKIP_SAVE'})
    children: bpy.props.BoolProperty(name="With Children", default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.window is not None

    def execute(self, context):
        count = 0
        for area, region in view3d_window_regions(context.window):
            count += frame_region(context, area, region, self.selected, self.children)
        return {'FINISHED'} if count else {'CANCELLED'}


# --- view history ---------------------------------------------------------------

_DIGITS = 5


def capture(rv3d):
    """Comparable snapshot of a RegionView3D's view."""
    r = lambda v: round(v, _DIGITS)  # noqa: E731
    return (tuple(map(r, rv3d.view_location)), tuple(map(r, rv3d.view_rotation)),
            r(rv3d.view_distance), rv3d.view_perspective,
            r(rv3d.view_camera_zoom), tuple(map(r, rv3d.view_camera_offset)))


def restore(rv3d, state):
    loc, rot, dist, persp, cam_zoom, cam_offset = state
    rv3d.view_perspective = persp
    rv3d.view_location = loc
    rv3d.view_rotation = rot
    rv3d.view_distance = dist
    rv3d.view_camera_zoom = cam_zoom
    rv3d.view_camera_offset = cam_offset


class ViewHistory:
    """Undo/redo stack of settled view states for one RegionView3D.

    ``observe`` is called periodically with the current state. A change is
    recorded once the view has stayed the same for one more observation
    (navigation or smooth-view animation finished).
    """

    def __init__(self, limit=50):
        self.limit = limit
        self.undo = []
        self.redo = []
        self.stable = None
        self.pending = None

    def _push(self, state):
        self.undo.append(state)
        del self.undo[:-self.limit]
        self.redo.clear()

    def observe(self, state):
        if self.stable is None or state == self.stable:
            self.stable = state
            self.pending = None
            return
        if state != self.pending:
            self.pending = state  # still moving
            return
        self._push(self.stable)
        self.stable = state
        self.pending = None

    def step_back(self, current):
        """State to show for "undo view change", or None."""
        if self.stable is None:  # never observed: nothing to go back to
            self.stable = current
            return None
        if current != self.stable:  # a change not settled/observed yet
            self._push(self.stable)
            self.stable = current
        if not self.undo:
            return None
        self.redo.append(current)
        self.stable = self.undo.pop()
        self.pending = None
        return self.stable

    def step_forward(self, current):
        """State to show for "redo view change", or None."""
        if self.stable is None:
            self.stable = current
            return None
        if current != self.stable:
            self.redo.clear()  # the view moved since the undo: redo is void
            self.observe(current)
            return None
        if not self.redo:
            return None
        self.undo.append(current)
        self.stable = self.redo.pop()
        self.pending = None
        return self.stable


_histories = {}
POLL_INTERVAL = 0.25


def history_for(rv3d):
    key = rv3d.as_pointer()
    h = _histories.get(key)
    if h is None:
        h = _histories[key] = ViewHistory()
    return h


def _all_rv3d():
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            space = area.spaces.active
            yield space.region_3d
            yield from space.region_quadviews


def poll_views():
    """Timer: observe every 3D view; forget views that no longer exist."""
    seen = set()
    for rv3d in _all_rv3d():
        if rv3d is None:
            continue
        seen.add(rv3d.as_pointer())
        history_for(rv3d).observe(capture(rv3d))
    for key in list(_histories):
        if key not in seen:
            del _histories[key]
    return POLL_INTERVAL


class ALLSET_OT_view_history(bpy.types.Operator):
    """Undo or redo a view change (Maya [ and ]); separate from scene undo"""
    bl_idname = "allset.view_history"
    bl_label = "Undo/Redo View Change"

    direction: bpy.props.EnumProperty(items=(("UNDO", "Undo", ""), ("REDO", "Redo", "")))

    @classmethod
    def poll(cls, context):
        return context.region_data is not None

    def execute(self, context):
        rv3d = context.region_data
        h = history_for(rv3d)
        cur = capture(rv3d)
        state = h.step_back(cur) if self.direction == "UNDO" else h.step_forward(cur)
        if state is None:
            results.result(self, "No more view changes")
            return {'CANCELLED'}
        restore(rv3d, state)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


# --- Space tap: four views <-> single view -------------------------------------


# --- Maya-style ortho cameras ----------------------------------------------------------------------------
# The top / front / side cameras show 30 units across (Maya units). Blender's viewport ortho width along the longer side =
# view_distance x 72 / lens (distance 3 cm with lens 70 = 3.086 units across).
# The four view's panels are real 3D View areas that keep their own camera (ui/four_view.py).
MAYA_ORTHO_WIDTH = 30.0
FOUR_VIEW_NOTE = "each panel has its own camera, shading and Show settings, like Maya's"


def ortho_key(rv3d):
    """'TOP' / 'FRONT' / 'SIDE' (+ '-' for the opposite views) of an axis-aligned ortho pane, else None."""
    if rv3d is None or rv3d.view_perspective != 'ORTHO':
        return None
    d = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))     # view direction
    i = max(range(3), key=lambda k: abs(d[k]))
    if abs(d[i]) < 0.999:
        return None
    return ("SIDE", "FRONT", "TOP")[i] + ("-" if d[i] > 0 else "")


def maya_ortho_distance(space, scene=None):
    """view_distance that shows 30 units across an ortho pane of this 3D View."""
    from .units import maya_unit
    return MAYA_ORTHO_WIDTH * maya_unit(scene or bpy.context.scene) * space.lens / 72.0


class ALLSET_OT_toggle_quad_view(bpy.types.Operator):
    """Toggle the four view; leaving it keeps the panel under the cursor (Maya Space tap). Four real panels, each
    with its own camera, shading and Show settings"""
    bl_idname = "allset.toggle_quad_view"
    bl_label = "Toggle Four Views"

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'VIEW_3D'

    def execute(self, context):
        from ..ui import four_view
        four = four_view.is_four(context.window.screen)
        got = four_view.tap(context, context.area, context.window)
        if got in ("four", "single"):
            return {'FINISHED'}
        if got == "failed" and four and bpy.app.background:
            self.report({'WARNING'}, "Leaving the four view needs the Blender window")
        elif got == "failed" and not bpy.app.background:
            self.report({'WARNING'}, "This panel can't be split into the four view here")
        return {'CANCELLED'}


def _persp_store():
    # the hotbox's store (marking/modal.py ALLSET_OT_hb_view): one memory of the persp view per area
    from ..marking import modal
    return modal._persp_views


def remember_persp(area, space):
    """Keep the perspective view of a four view before leaving it (the panel under the cursor may be ortho)."""
    for rv3d in (space.region_3d, *space.region_quadviews):
        if rv3d is not None and rv3d.view_perspective == 'PERSP':
            _persp_store()[area.as_pointer()] = (rv3d.view_rotation.copy(), rv3d.view_location.copy(),
                                                 rv3d.view_distance)
            return


def ensure_persp(area, space):
    """Maya Single Perspective / Four View (#8): the single view (or the four view's top right panel) shows the
    persp camera, never an ortho view: an ortho view gets the last persp view of this area back, else the
    default persp, like Maya (Home)."""
    rv3d = space.region_3d
    if rv3d is None or rv3d.view_perspective != 'ORTHO':
        return
    rv3d.is_orthographic_side_view = False
    rv3d.view_perspective = 'PERSP'
    saved = _persp_store().get(area.as_pointer())
    if saved:
        rv3d.view_rotation, rv3d.view_location, rv3d.view_distance = saved
    else:
        home_view(rv3d, units.maya_unit(bpy.context.scene))
    area.tag_redraw()


def home_view(rv3d, k):
    """Maya Home (viewSet -home): the default camera place, no animation.
    Perspective = Maya's new-scene persp (units.PERSP_EYE, Maya units); orthographic keeps
    its direction and goes back to the origin at the same distance."""
    eye = Vector(units.PERSP_EYE) * k
    rv3d.view_location = (0.0, 0.0, 0.0)
    rv3d.view_distance = eye.length
    if rv3d.view_perspective == 'PERSP':
        rv3d.view_rotation = eye.normalized().to_track_quat('Z', 'Y')


class ALLSET_OT_view_home(bpy.types.Operator):
    """Go to the default view (Maya Home)"""
    bl_idname = "allset.view_home"
    bl_label = "Default View"

    @classmethod
    def poll(cls, context):
        rv3d = context.region_data
        return rv3d is not None and context.area is not None and context.area.type == 'VIEW_3D'             and rv3d.view_perspective != 'CAMERA'

    def execute(self, context):
        home_view(context.region_data, units.maya_unit(context.scene))
        context.region.tag_redraw()
        return {'FINISHED'}


classes = (ALLSET_OT_tumble, ALLSET_OT_emulated_tumble, ALLSET_OT_dolly, ALLSET_OT_dolly_2d, ALLSET_OT_view_axis_lock, ALLSET_OT_frame, ALLSET_OT_frame_all_views, ALLSET_OT_view_history,
           ALLSET_OT_toggle_quad_view, ALLSET_OT_view_home)


def register_timer():
    if not bpy.app.timers.is_registered(poll_views):
        bpy.app.timers.register(poll_views, first_interval=POLL_INTERVAL, persistent=True)


def unregister_timer():
    if bpy.app.timers.is_registered(poll_views):
        bpy.app.timers.unregister(poll_views)
    _histories.clear()
