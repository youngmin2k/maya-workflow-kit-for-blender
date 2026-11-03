# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya marquee: edit-mode box / lasso selection also picks occluded components
.

Maya's marquee selects everything inside the rectangle, hidden or not, unless
"Camera based selection" is on (``selectPrefUseDepth false``).
Blender's edit-mode box
select skips occluded elements unless the view's X-ray flag is set; the flag
alone is enough, so with X-ray alpha 1.0 surfaces stay opaque (checked in
tests/gui/gui_step30_selection.py). The flag shows hidden wires and lights the
header button, so it is only set while the drag runs:

``allset.select_through`` sits in front of ``view3d.select_box`` /
``select_lasso`` in the select tool keymaps (same LMB CLICK_DRAG event), sets
the flag and returns PASS_THROUGH so the select operator gets the event; a
timer puts the view back once that operator's modal has ended.
"""

import bpy

from .. import live_refs

MODES = {'EDIT_MESH'}
SELECT_MODALS = {"VIEW3D_OT_select_box", "VIEW3D_OT_select_lasso"}
_TICK = 0.05
_GIVE_UP = 1.0   # s without seeing the select modal: restore anyway

# space pointer -> [space pointer, window pointer, flag attr, alpha attr, old alpha, seen modal, waited s]: pointers,
# looked up each tick (a Space / Window kept after its window closed crashes, #36)
_active = {}


def _attrs(shading):
    if shading.type == 'WIREFRAME':
        return "show_xray_wireframe", "xray_alpha_wireframe"
    return "show_xray", "xray_alpha"


def begin(context):
    """Set the X-ray flag of this 3D View for one drag; False if not needed."""
    from .. import preferences
    try:
        if not preferences.get().select_through:
            return False
    except KeyError:
        return False
    space = context.space_data
    if context.mode not in MODES or space is None or space.type != 'VIEW_3D':
        return False
    shading = space.shading
    flag, alpha = _attrs(shading)
    if getattr(shading, flag) or space.as_pointer() in _active:
        return False   # X-ray already on: Blender selects through by itself
    _active[space.as_pointer()] = [space.as_pointer(), live_refs.pointer(context.window), flag, alpha,
                                   getattr(shading, alpha), False, 0.0]
    setattr(shading, flag, True)
    setattr(shading, alpha, 1.0)   # surfaces stay opaque
    if not bpy.app.timers.is_registered(_watch):
        bpy.app.timers.register(_watch, first_interval=_TICK)
    return True


def _lookup_space(space_ptr, win_ptr):
    return live_refs.find_space(space_ptr, win_ptr or None)[2]


def _lookup_window(win_ptr):
    return live_refs.window(win_ptr)


def _restore(entry):
    space_ptr, win_ptr, flag, alpha, old_alpha = entry[:5]
    space = _lookup_space(space_ptr, win_ptr)
    if space is None:       # its window or area is gone
        return
    try:
        setattr(space.shading, flag, False)
        setattr(space.shading, alpha, old_alpha)
    except ReferenceError:
        pass


def _running(win_ptr):
    window = _lookup_window(win_ptr)
    if window is None:
        return False
    try:
        return any(op.bl_idname in SELECT_MODALS for op in window.modal_operators)
    except ReferenceError:
        return False


def _watch():
    for key, entry in list(_active.items()):
        running = _running(entry[1])
        entry[5] = entry[5] or running
        entry[6] += _TICK
        if (entry[5] and not running) or (not entry[5] and entry[6] >= _GIVE_UP):
            _restore(entry)
            del _active[key]
    return _TICK if _active else None


def restore_all():
    from . import joint_marquee
    joint_marquee.cancel_all()
    from . import lattice_pick
    lattice_pick.cancel_all()
    for entry in _active.values():
        _restore(entry)
    _active.clear()
    if bpy.app.timers.is_registered(_watch):
        bpy.app.timers.unregister(_watch)


class ALLSET_OT_select_through(bpy.types.Operator):
    """Let this edit-mode box / lasso drag also select hidden components (Maya marquee)"""
    bl_idname = "allset.select_through"
    bl_label = "Marquee Selects Hidden Components"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        begin(context)
        from . import joint_marquee
        joint_marquee.begin(context)      # joints drawn by the kit: Maya's marquee rules once the drag ends
        from . import lattice_pick         # #274: a deformed lattice's points boxed where they are drawn
        if lattice_pick.box_takes(context):
            lattice_pick.start_box(context, event)
            return {'FINISHED'}
        lattice_pick.begin_box(context)
        return {'PASS_THROUGH'}


classes = (ALLSET_OT_select_through,)
