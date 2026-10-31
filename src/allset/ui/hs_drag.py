# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Hypershade: middle-mouse drag a material swatch from the Browser onto an object in a viewport = assign it
.

Maya: MMB-drag a shader swatch and release it over a surface in a modeling panel; the shader is assigned to that
object (in component mode with faces selected on it: to those faces). The Hypershade is a separate window, so the
3D View under the release is usually in another window.

How (Blender 4.5, tests/gui/gui_step162_hs_drag.py):

- ``allset.hs_swatch_drag`` sits first in "View2D Buttons List" on MIDDLEMOUSE PRESS (that keymap's view2d.pan /
  scroller_activate would take the press otherwise). It passes through unless the region is the Hypershade Browser
  and the press is on a material swatch: its name button is the property ``Material.allset_hs_pick``, read from
  ``context.property`` (the swatch image, ``template_icon``, is no button: nothing to read there).
- It then runs as a window modal. Blender keeps every mouse event in a window that has a modal operator handler,
  even when the cursor is outside it (wm_event_system ``wm_event_cursor_other_windows`` skips such windows, and
  GHOST captures the mouse while a button is down), so the release arrives here with coordinates outside the
  Hypershade window. ``Window.x / y`` place every window on the screen (bottom-left origin like event
  coordinates): the release point is mapped into the window under it, its 3D View WINDOW region, a ray from that
  view's perspective matrix and ``Scene.ray_cast``.
- The material goes on through ``operators/material.assign`` (the kit's material rules).
- While dragging, a small swatch + name follows the cursor in the Browser and in any 3D View it is over.
"""

import blf
import bpy
import gpu
from bpy.props import StringProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .. import live_refs
from ..operators import keystate
from ..operators import material as material_ops

PICK_PROP = "allset_hs_pick"      # = hypershade.PICK_PROP
DRAG = {"window": 0, "point": None, "material": ""}   # screen point (x, y) of the cursor while a drag runs


# --- pure parts (tests/test_step162_hs_drag.py) -------------------------------------------------------------------

def screen_point(window_xy, mouse_xy):
    """Screen pixel of a window-relative mouse position (both bottom-left origin)."""
    return window_xy[0] + mouse_xy[0], window_xy[1] + mouse_xy[1]


def window_under(rects, point, own=None):
    """Key of the window rect (key, x, y, width, height) containing the screen ``point``. Python can't tell which
    window is on top: the window the drag started in wins (it is the one in front while dragging), then the
    others in window-manager order (main window first). None when the point is on no window."""
    hits = [r[0] for r in rects if r[1] <= point[0] < r[1] + r[3] and r[2] <= point[1] < r[2] + r[4]]
    if not hits:
        return None
    return own if own in hits else hits[0]


def ray(perspective_matrix, width, height, x, y):
    """(origin, direction) of the view ray through region pixel (x, y): the near and far clip points unprojected
    with the inverse of the region's perspective matrix (perspective and orthographic alike)."""
    inv = perspective_matrix.inverted()
    nx = 2.0 * x / max(width, 1) - 1.0
    ny = 2.0 * y / max(height, 1) - 1.0

    def unproject(z):
        v = inv @ Vector((nx, ny, z, 1.0))
        return Vector((v.x / v.w, v.y / v.w, v.z / v.w))
    near, far = unproject(-1.0), unproject(1.0)
    return near, (far - near).normalized()


def object_at(scene, depsgraph, origin, direction):
    """The original object the ray hits first (Scene.ray_cast: visible evaluated geometry), or None."""
    hit, _loc, _normal, _index, ob, _matrix = scene.ray_cast(depsgraph, origin, direction)
    if not hit or ob is None:
        return None
    return ob.original if ob.original is not None else ob


def drop(context, mat, ob):
    """Assign ``mat`` to ``ob`` the Maya way (operators/material.assign: faces when ``ob`` is edited in face mode with
    faces selected, else the whole object); {object name: slot} or None when ``ob`` takes no material."""
    if ob is None or mat is None or ob.type not in material_ops.SUPPORTED:
        return None
    return material_ops.assign(context, mat, [ob])


# --- finding the drop target ---------------------------------------------------------------------------------------

def _rects():
    return [(w.as_pointer(), w.x, w.y, w.width, w.height) for w in live_refs.windows()]


def view_under(point, own_ptr=0):
    """(window, area, region, (x, y) in the region) of the 3D View WINDOW region under the screen ``point``, or
    None (no window / not a 3D View / the Tool Box column)."""
    from . import toolbox
    win = live_refs.window(window_under(_rects(), point, own_ptr))
    if win is None or win.screen is None:
        return None
    wx, wy = point[0] - win.x, point[1] - win.y
    for area in win.screen.areas:
        if area.type != 'VIEW_3D' or toolbox.is_toolbox(area.spaces.active):
            continue
        for region in area.regions:
            if region.type == 'WINDOW' and region.x <= wx < region.x + region.width \
                    and region.y <= wy < region.y + region.height:
                return win, area, region, (wx - region.x, wy - region.y)
    return None


def object_under(context, point, own_ptr=0):
    """The object under the screen ``point`` in a 3D View of any window, or None."""
    found = view_under(point, own_ptr)
    if found is None:
        return None
    _win, area, region, (x, y) = found
    rv3d = area.spaces.active.region_3d
    if rv3d is None:
        return None
    origin, direction = ray(rv3d.perspective_matrix, region.width, region.height, x, y)
    return object_at(context.scene, context.evaluated_depsgraph_get(), origin, direction)


def swatch_material(context):
    """The material of the Browser swatch under the mouse, or None. The swatch's name button is the property
    ``Material.allset_hs_pick`` (ui/hypershade.py): ``context.property`` is the only hovered button a keymap
    operator can read (``button_operator`` / ``context_pointer_set`` are absent there)."""
    from . import hypershade
    if hypershade.context_pane(context) != 'BROWSER':
        return None
    return material_of_property(getattr(context, "property", None))


def material_of_property(prop):
    """The material of a hovered ``(data, path, index)`` when it is a Browser swatch button, else None."""
    if not prop or len(prop) < 2:
        return None
    data, path = prop[0], prop[1]
    if isinstance(data, bpy.types.Material) and path == PICK_PROP:
        return data
    return None


def _redraw_all():
    for w in live_refs.windows():
        for area in w.screen.areas if w.screen else ():
            if area.type in {'VIEW_3D', 'PROPERTIES'}:
                area.tag_redraw()


# --- the drag ----------------------------------------------------------------------------------------------------

class ALLSET_OT_hs_swatch_drag(bpy.types.Operator):
    """Maya Hypershade: drag a material swatch with the middle mouse button onto an object to assign it"""
    bl_idname = "allset.hs_swatch_drag"
    bl_label = "Drag Material"
    bl_options = {'INTERNAL', 'UNDO'}     # one undo step for the assignment, no redo panel (Maya has none)

    material: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        mat = bpy.data.materials.get(self.material) if self.material else swatch_material(context)
        if mat is None or context.window is None:
            return {'PASS_THROUGH'}     # view2d.pan / scroller of the region
        win = context.window
        self._win = win.as_pointer()
        self._mat = mat.name
        self._xy = (event.mouse_x, event.mouse_y)
        DRAG.update(window=self._win, material=mat.name, point=screen_point((win.x, win.y), self._xy))
        self._timer = context.window_manager.event_timer_add(0.05, window=win)
        win.cursor_modal_set('HAND')
        context.window_manager.modal_handler_add(self)
        _redraw_all()
        return {'RUNNING_MODAL'}

    def _end(self, context):
        DRAG.update(window=0, point=None, material="")
        context.window_manager.event_timer_remove(self._timer)
        win = live_refs.window(self._win)
        if win is not None:
            win.cursor_modal_restore()
        _redraw_all()

    def _point(self, context):
        win = live_refs.window(self._win)
        return screen_point((win.x, win.y), self._xy) if win is not None else None

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._xy = (event.mouse_x, event.mouse_y)
            DRAG["point"] = self._point(context)
            _redraw_all()
            return {'RUNNING_MODAL'}
        if event.type == 'MIDDLEMOUSE' and event.value == 'RELEASE':
            self._xy = (event.mouse_x, event.mouse_y)
            return self._drop(context)
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._end(context)
            return {'CANCELLED'}
        if event.type == 'TIMER':
            # the release went somewhere else (should not happen: see the module docstring): end without a drop
            if keystate.is_down('MIDDLEMOUSE') is False:
                self._end(context)
                return {'CANCELLED'}
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def _drop(self, context):
        point = self._point(context)
        mat = bpy.data.materials.get(self._mat)
        ob = object_under(context, point, self._win) if point is not None else None
        self._end(context)
        done = drop(context, mat, ob)
        if not done:
            return {'CANCELLED'}
        return {'FINISHED'}


# --- drawing the dragged swatch ----------------------------------------------------------------------------------

def _draw():
    point, name = DRAG["point"], DRAG["material"]
    if point is None or not name:
        return
    context = bpy.context
    win, region = context.window, context.region
    if win is None or region is None:
        return
    x = point[0] - win.x - region.x
    y = point[1] - win.y - region.y
    if not (0 <= x < region.width and 0 <= y < region.height):
        return
    mat = bpy.data.materials.get(name)
    s = context.preferences.system.ui_scale or 1.0
    size = round(24 * s)
    x0, y0 = x + round(10 * s), y - round(10 * s) - size
    colour = tuple(mat.diffuse_color[:3]) + (1.0,) if mat is not None else (0.5, 0.5, 0.5, 1.0)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    for rect, col in (((x0 - 1, y0 - 1, size + 2, size + 2), (0.0, 0.0, 0.0, 0.8)), ((x0, y0, size, size), colour)):
        rx, ry, rw, rh = rect
        batch = batch_for_shader(shader, 'TRI_FAN', {"pos": ((rx, ry), (rx + rw, ry), (rx + rw, ry + rh),
                                                            (rx, ry + rh))})
        shader.uniform_float("color", col)
        batch.draw(shader)
    gpu.state.blend_set('NONE')
    font = 0
    blf.size(font, 11 * s)
    blf.color(font, 1.0, 1.0, 1.0, 1.0)
    blf.position(font, x0 + size + round(4 * s), y0 + size // 2 - round(4 * s), 0)
    blf.draw(font, name)


_handles = []
classes = (ALLSET_OT_hs_swatch_drag,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for space in (bpy.types.SpaceView3D, bpy.types.SpaceProperties):
        _handles.append((space, space.draw_handler_add(_draw, (), 'WINDOW', 'POST_PIXEL')))


def unregister():
    while _handles:
        space, handle = _handles.pop()
        space.draw_handler_remove(handle, 'WINDOW')
    DRAG.update(window=0, point=None, material="")
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
