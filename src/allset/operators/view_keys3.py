# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya view keys, batch 3: Alt+A cycle display, Alt+P camera persp / ortho, Alt+arrows 1-pixel move,
` hold = tweak mode, \\ hold = 2D pan / zoom.

Maya-style hotkeys: Alt+A display cycle,
CameraModeToggle (orthographic / perspective), Alt+arrow pixel move, ` tweak mode,
\\ 2D pan / zoom.
"""

import math

import bpy
from mathutils import Vector

from .. import undo_steps
from . import keystate

# --- Alt+A: cycle display ------------------------------------------------------------------------------------
# Global cycle state (starts at 0): 0 -> joint X-ray on, everything shown (1),
# 1 -> joint X-ray off, everything shown (2), 2 -> joints and curves hidden, meshes only (0).
CYCLE = {0: ("XRAY_JOINTS", 1), 1: ("ALL", 2), 2: ("MESHES", 0)}
CYCLE_LABELS = {"XRAY_JOINTS": "X-Ray Joints", "ALL": "Joints, Curves and Meshes", "MESHES": "Meshes Only"}
_cycle = {"index": 0, "in_front": {}}


def cycle_next(index):
    """(mode to show, next index) for the current cycle index."""
    return CYCLE[index]


def _armatures(scene):
    return [ob for ob in scene.objects if ob.type == 'ARMATURE']


def apply_display(context, space, mode):
    """Show ``mode`` in one 3D View. Joint X-ray = the armatures' In Front (Blender has no per-view joint X-ray):
    the previous values come back when the mode leaves X-ray."""
    scene = context.scene
    saved = _cycle["in_front"]
    if mode == "XRAY_JOINTS":
        for ob in _armatures(scene):
            saved.setdefault(ob.name, ob.show_in_front)
            ob.show_in_front = True
    else:
        for name, value in list(saved.items()):
            ob = bpy.data.objects.get(name)
            if ob is not None:
                ob.show_in_front = value
        saved.clear()
    show = mode != "MESHES"
    space.show_object_viewport_armature = show
    space.show_object_viewport_curve = show
    space.show_object_viewport_mesh = True
    from ..ui import curve_controls        # curve-shaped bone controls follow
    curve_controls.sync(space, scene)


class ALLSET_OT_cycle_display(bpy.types.Operator):
    """Cycle the view's display: X-ray joints / joints, curves and meshes / meshes only (Maya Alt+A)"""
    bl_idname = "allset.cycle_display"
    bl_label = "Cycle Display Mode"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'VIEW_3D'

    def execute(self, context):
        mode, nxt = cycle_next(_cycle["index"])
        apply_display(context, context.space_data, mode)
        _cycle["index"] = nxt
        from ..ui import view_message
        view_message.show(context, CYCLE_LABELS[mode])
        context.area.tag_redraw()
        return {'FINISHED'}


# --- Alt+P: camera persp / ortho (CameraModeToggle) --------------------------------------------------------

def ortho_scale_for(distance, fov):
    """Orthographic width that shows at ``distance`` what a perspective camera with horizontal ``fov`` shows."""
    return 2.0 * max(distance, 1e-6) * math.tan(fov / 2.0)


class ALLSET_OT_camera_mode_toggle(bpy.types.Operator):
    """Switch the view's camera between perspective and orthographic, keeping the view (Maya Alt+P)"""
    bl_idname = "allset.camera_mode_toggle"
    bl_label = "Camera Mode Toggle"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'VIEW_3D' \
            and context.region_data is not None

    def execute(self, context):
        rv3d = context.region_data
        cam = context.space_data.camera or context.scene.camera
        if rv3d.view_perspective == 'CAMERA' and cam is not None and cam.type == 'CAMERA':
            data = cam.data
            if data.type == 'ORTHO':
                data.type = 'PERSP'
            else:
                forward = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
                d = (rv3d.view_location - cam.matrix_world.translation).dot(forward)
                if d <= 1e-6:
                    from . import units
                    d = 10.0 * units.maya_unit()
                data.ortho_scale = ortho_scale_for(d, data.angle)
                data.type = 'ORTHO'
            return {'FINISHED'}
        bpy.ops.view3d.view_persportho()
        return {'FINISHED'}


# --- Alt+arrows: move the selection one pixel (pixelMove) ---------------------------------------------------

def pixel_delta(region, rv3d, center, dx, dy):
    """World vector that moves ``center`` by (dx, dy) pixels on screen, in the view plane through it."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d
    p = location_3d_to_region_2d(region, rv3d, center)
    if p is None:
        return None
    return region_2d_to_location_3d(region, rv3d, p + Vector((dx, dy)), center) - center


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_pixel_move(bpy.types.Operator):
    """Move the selection one pixel in the view plane (Maya Alt+arrow keys)"""
    bl_idname = "allset.pixel_move"
    bl_label = "Move One Pixel"
    bl_options = {'REGISTER', 'UNDO'}

    dx: bpy.props.IntProperty(name="X", default=0, options={'SKIP_SAVE'})
    dy: bpy.props.IntProperty(name="Y", default=0, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.region_data is not None \
            and context.mode in {'OBJECT', 'EDIT_MESH', 'EDIT_CURVE', 'EDIT_ARMATURE', 'POSE', 'EDIT_LATTICE'}

    def execute(self, context):
        from ..ui import manipulator
        center, _frame, _otype = manipulator.pivot_frame(context, 'TRANSLATE')
        if center is None:
            return {'CANCELLED'}
        delta = pixel_delta(context.region, context.region_data, center, self.dx, self.dy)
        if delta is None:
            return {'CANCELLED'}
        bpy.ops.transform.translate(value=delta, orient_type='GLOBAL')
        return {'FINISHED'}


# --- ` hold: tweak mode -------------------------------------------------------------------------------------
# Maya turns tweak mode on for Select / Move / Rotate / Scale (the Select tool becomes Move); Blender's Tweak tool
# (builtin.select: click-drag moves what is under the mouse) is that mode.
TWEAK_FROM = {"builtin.select_box", "builtin.select_circle", "builtin.select_lasso", "builtin.move",
              "builtin.rotate", "builtin.scale", "builtin.transform"}
TWEAK_TOOL = "builtin.select"
POLL = 0.05


def _tool(context):
    tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    return tool.idname if tool is not None else None


class ALLSET_OT_tweak_hold(bpy.types.Operator):
    """Tweak mode while held: click-drag moves what is under the mouse without selecting it first (Maya `)"""
    bl_idname = "allset.tweak_hold"
    bl_label = "Tweak Mode (hold)"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        if event.value != 'PRESS':
            return {'CANCELLED'}
        before = _tool(context)
        if before not in TWEAK_FROM:
            return {'PASS_THROUGH'}
        self._before, self._key, self._area = before, event.type, context.area
        bpy.ops.wm.tool_set_by_id(name=TWEAK_TOOL)
        self._timer = context.window_manager.event_timer_add(POLL, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        context.window_manager.event_timer_remove(self._timer)
        try:
            region = next((r for r in self._area.regions if r.type == 'WINDOW'), None)
            with context.temp_override(area=self._area, region=region):
                if _tool(context) == TWEAK_TOOL:
                    bpy.ops.wm.tool_set_by_id(name=self._before)
        except (ReferenceError, RuntimeError, TypeError):
            pass
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == self._key:
            return self._finish(context) if event.value == 'RELEASE' else {'RUNNING_MODAL'}
        if event.type == 'TIMER' and keystate.is_down(self._key) is False:
            window = context.window
            from .manip_scale import TRANSFORM_MODALS
            if window is not None and any(op.bl_idname.startswith(TRANSFORM_MODALS) for op in window.modal_operators):
                return {'PASS_THROUGH'}       # the release went to a tweak drag: wait for it to end
            return self._finish(context)
        return {'PASS_THROUGH'}


# --- \ hold: 2D pan / zoom -------------------------------------------------------------------------------
# Blender's camera view offset / zoom move the camera view without touching the render, like Maya's film-back
# 2D Pan/Zoom; a user view has none.
ZOOM_PER_PX = 0.25          # view_camera_zoom units per pixel of MMB drag
NOTICE = "2D Pan/Zoom: look through a camera (Blender pans / zooms the camera view only)"


def camera_offset_after(offset, dx, dy, region_w, region_h, zoom):
    """view_camera_offset after an LMB drag of (dx, dy) px: the camera frame follows the mouse."""
    # view_camera_offset is in camera-frame units (1 = frame width at zoom factor 1); zoom factor = (sqrt2 + z/50)^2 / 4
    factor = ((math.sqrt(2.0) + zoom / 50.0) ** 2) / 4.0
    scale = 2.0 * factor * max(region_w, region_h)
    return offset[0] - dx / scale, offset[1] - dy / scale


class ALLSET_OT_pan_zoom_hold(bpy.types.Operator):
    """2D pan / zoom while held: LMB drag pans, MMB drag zooms the camera view, the camera stays (Maya \\)"""
    bl_idname = "allset.pan_zoom_hold"
    bl_label = "2D Pan/Zoom (hold)"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.region_data is not None

    def invoke(self, context, event):
        if event.value != 'PRESS':
            return {'CANCELLED'}
        rv3d = context.region_data
        if rv3d.view_perspective != 'CAMERA':
            from ..ui import notices
            notices.show(NOTICE)
            return {'CANCELLED'}
        self._key, self._rv3d, self._region = event.type, rv3d, context.region
        self._drag, self._last = None, None
        self._timer = context.window_manager.event_timer_add(POLL, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        context.window_manager.event_timer_remove(self._timer)
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == self._key:
            if event.value == 'RELEASE' and self._drag is None:
                return self._finish(context)
            return {'RUNNING_MODAL'}
        if event.type in {'LEFTMOUSE', 'MIDDLEMOUSE'}:
            if event.value == 'PRESS':
                self._drag, self._last = event.type, (event.mouse_x, event.mouse_y)
                return {'RUNNING_MODAL'}
            if event.value == 'RELEASE' and self._drag == event.type:
                self._drag = None
                if keystate.is_down(self._key) is False:
                    return self._finish(context)
                return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE' and self._drag is not None:
            dx, dy = event.mouse_x - self._last[0], event.mouse_y - self._last[1]
            self._last = (event.mouse_x, event.mouse_y)
            rv3d, region = self._rv3d, self._region
            if self._drag == 'LEFTMOUSE':
                rv3d.view_camera_offset = camera_offset_after(tuple(rv3d.view_camera_offset), dx, dy,
                                                              region.width, region.height, rv3d.view_camera_zoom)
            else:
                rv3d.view_camera_zoom = max(-30.0, min(600.0, rv3d.view_camera_zoom + (dx + dy) * ZOOM_PER_PX))
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'TIMER' and self._drag is None and keystate.is_down(self._key) is False:
            return self._finish(context)
        return {'RUNNING_MODAL'} if self._drag is not None else {'PASS_THROUGH'}


classes = (ALLSET_OT_cycle_display, ALLSET_OT_camera_mode_toggle, ALLSET_OT_pixel_move, ALLSET_OT_tweak_hold,
           ALLSET_OT_pan_zoom_hold)
