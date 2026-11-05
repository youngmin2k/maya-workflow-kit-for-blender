# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya floating editor windows drawn by a kit panel (Issue #119): Component Editor, Shape Editor,
Connection Editor.

Same mechanism as the Reference Editor (ui/reference_editor.py) and the Hypershade panes: a new
window whose one area is a Properties editor on the Tool tab (header and navigation bar hidden) marked by hidden tab
flags. Each kind has its own flag pair (``KINDS``) — none of them is a ``maya_dock.ROLE_FLAGS`` single flag, the
Hypershade ``MARK`` pair or the Reference Editor's triple, so their checks never match each other. The editor's panel
(``bl_space_type`` VIEW_3D, ``bl_category`` "Tool") polls ``context_kind(context) == kind``.
"""

import bpy

from .. import live_refs

KINDS = {
    "COMPONENT_EDITOR": ("show_properties_object", "show_properties_modifiers"),
    "NORMALS_SIZE": ("show_properties_view_layer", "show_properties_data"),   # operators/poly_display.py
    "SHAPE_EDITOR": ("show_properties_object", "show_properties_data"),
    "CONNECTION_EDITOR": ("show_properties_object", "show_properties_material"),
    "HOTKEY_EDITOR": ("show_properties_bone", "show_properties_bone_constraints"),   # ui/hotkey_editor.py
    "PREFERENCES": ("show_properties_scene", "show_properties_output"),   # Maya Preferences
    "POSE_EDITOR": ("show_properties_object", "show_properties_constraints"),   # ui/pose_editor.py
    "GAME_EXPORTER": ("show_properties_scene", "show_properties_physics"),   # operators/game_exporter.py
    "MARKING_MENU_EDITOR": ("show_properties_bone", "show_properties_data"),   # marking/menu_editor.py
    "HYPERGRAPH": ("show_properties_scene", "show_properties_collection"),   # ui/hypergraph.py
    "SKIN_TOOLS": ("show_properties_bone", "show_properties_modifiers"),   # ui/skin_tools.py
    "COMMAND_OPTIONS": ("show_properties_scene", "show_properties_material"),
}


def _flags(space):
    return [p.identifier for p in space.bl_rna.properties if p.identifier.startswith("show_properties_")]


def kind_of(area):
    """The kit editor kind the Properties ``area`` is marked as, else None."""
    if area is None or area.type != 'PROPERTIES':
        return None
    space = area.spaces.active
    if space.show_region_header or not space.show_properties_tool:
        return None
    from .. import compat
    on = {f for f in _flags(space) if getattr(space, f)} - set(compat.LATER_PROPERTIES_TABS)
    for kind, mark in KINDS.items():
        if on == {"show_properties_tool", *mark}:
            return kind
    return None


def context_kind(context):
    return kind_of(getattr(context, "area", None))


def set_kind(area, kind, window=None):
    """Mark the Properties editor ``area`` as ``kind``; False until its space can take the Tool tab."""
    space = area.spaces.active
    try:
        space.context = 'TOOL'
    except TypeError:
        return False
    for flag in _flags(space):
        setattr(space, flag, flag in ("show_properties_tool", *KINDS[kind]))
    space.show_region_header = False
    nav = next((r for r in area.regions if r.type == 'NAVIGATION_BAR'), None)
    if nav is not None and nav.width > 1 and window is not None and not bpy.app.background:
        try:
            with bpy.context.temp_override(window=window, area=area):
                bpy.ops.screen.region_toggle(region_type='NAVIGATION_BAR')
        except (RuntimeError, TypeError):
            pass
    area.tag_redraw()
    return True


def set_kind_later(window, area, kind, tries=60):
    win_ptr, key = window.as_pointer(), area.as_pointer()
    state = {"n": tries}

    def tick():
        win, area_ = live_refs.find_area(key, win_ptr)   # looked up each tick (#36)
        if area_ is None:
            return None
        with bpy.context.temp_override(window=win):
            done = set_kind(area_, kind, win)
        state["n"] -= 1
        return None if done or state["n"] <= 0 else 0.05
    bpy.app.timers.register(tick, first_interval=0.0)


def find_window(context, kind):
    for w in context.window_manager.windows:
        if any(kind_of(a) == kind for a in w.screen.areas):
            return w
    return None


def areas(context, kind):
    return [a for w in context.window_manager.windows for a in w.screen.areas if kind_of(a) == kind]


def redraw(context, kind):
    for a in areas(context, kind):
        a.tag_redraw()


def open_window(context, kind):
    """A new window with one Properties area marked ``kind`` (Maya: a floating window); the open one if any."""
    found = find_window(context, kind)
    if found is not None:
        return found
    from ..operators import menu_extras
    area = max(context.window.screen.areas, key=lambda a: a.width * a.height, default=None)
    if area is None:
        return None
    window = menu_extras.open_window(context, area, f"marked:{kind}")
    if window is None:
        return None
    target = window.screen.areas[0]
    target.type = 'PROPERTIES'
    if not set_kind(target, kind, window):
        set_kind_later(window, target, kind)
    return window


def draw_menu_bar(layout, context, editor):
    """Maya's flat menu bar at the top of the window (``editor_menu_data`` menus, ``editor_menu_map`` actions)."""
    from . import editor_chrome
    bar = layout.row(align=True)
    bar.alignment = 'LEFT'
    bar.emboss = 'PULLDOWN_MENU'
    editor_chrome.draw_menu_bar(bar, context, editor)


def close_later(window):
    """Close ``window`` from a timer (closing the window an operator runs in, from inside it, is unsafe)."""
    ptr = window.as_pointer()

    def tick():
        win = live_refs.window(ptr)
        if win is not None:
            with bpy.context.temp_override(window=win):
                bpy.ops.wm.window_close()
        return None
    bpy.app.timers.register(tick, first_interval=0.0)


class ALLSET_OT_marked_window_close(bpy.types.Operator):
    """Close this window (Maya's Close button)"""
    bl_idname = "allset.marked_window_close"
    bl_label = "Close"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if context.window is None or context.window == context.window_manager.windows[0]:
            return {'CANCELLED'}
        close_later(context.window)
        return {'FINISHED'}


classes = (ALLSET_OT_marked_window_close,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
