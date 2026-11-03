# SPDX-License-Identifier: GPL-3.0-or-later
"""IPR in its own window, like Maya's IPR button.

Maya's IPR renders the current frame into a separate render window that updates while the scene changes; the panel
the user works in keeps its own display. Blender's interactive render is a 3D View in Rendered shading, so IPR opens
a new window with a copy of the main 3D View in Rendered shading (overlays, gizmos, toolbar and sidebar off: only the
picture). The copy keeps looking where the main view looks. IPR again (or closing the window) stops it.

Without a window (background runs) IPR falls back to the main viewport's Rendered shading.
"""

import bpy

from .. import live_refs

KIND = "ipr"                 # window_places name: the window reopens where it was last closed
FOLLOW_TICK = 0.2            # s between view copies from the main view

_state = {"win": 0, "src": 0}    # pointers: the IPR window, the 3D View area it follows

# View values copied from the main view (RegionView3D / SpaceView3D)
REGION_KEYS = ("view_location", "view_rotation", "view_distance", "view_perspective",
               "view_camera_offset", "view_camera_zoom")
SPACE_KEYS = ("lens", "clip_start", "clip_end", "camera")


def window():
    """The open IPR window, else None."""
    return live_refs.window(_state["win"])


def is_open():
    return window() is not None


def view_area(win):
    """The 3D View area of the IPR window."""
    if win is None or win.screen is None:
        return None
    return next((a for a in win.screen.areas if a.type == 'VIEW_3D'), None)


def _value(v):
    return v.copy() if hasattr(v, "copy") else v


def _same(a, b, eps=1e-6):
    """Equal view values; numbers within ``eps`` (a copied rotation reads back renormalised)."""
    if isinstance(a, str) or not hasattr(a, "__len__"):
        if isinstance(a, float) and isinstance(b, float):
            return abs(a - b) <= eps
        return a == b
    return len(a) == len(b) and all(abs(x - y) <= eps for x, y in zip(a, b))


def copy_view(src_space, dst_space):
    """Give ``dst_space`` the view of ``src_space``; True when something changed."""
    changed = False
    for owner_src, owner_dst, keys in ((src_space.region_3d, dst_space.region_3d, REGION_KEYS),
                                       (src_space, dst_space, SPACE_KEYS)):
        if owner_src is None or owner_dst is None:
            continue
        for key in keys:
            if not hasattr(owner_src, key):
                continue
            new = getattr(owner_src, key)
            old = getattr(owner_dst, key)
            if not _same(old, new):
                setattr(owner_dst, key, _value(new))
                changed = True
    return changed


def setup_view(space):
    """The IPR picture: Rendered shading, nothing drawn over it."""
    space.shading.type = 'RENDERED'
    space.overlay.show_overlays = False
    space.show_gizmo = False
    for flag in ("show_region_toolbar", "show_region_ui", "show_region_tool_header"):
        if getattr(space, flag, False):
            setattr(space, flag, False)


def _follow():
    win = window()
    area = view_area(win)
    if area is None:
        _state["win"] = 0
        return None
    _w, src = live_refs.find_area(_state["src"])
    if src is not None and src.type == 'VIEW_3D':
        try:
            if copy_view(src.spaces.active, area.spaces.active):
                area.tag_redraw()
        except (AttributeError, ReferenceError, TypeError):
            pass
    return FOLLOW_TICK


def _setup_later(ptr, tries=20):
    """Region flags set inside the operator don't stick on a new window: set them again from a timer."""
    state = {"n": tries}

    def tick():
        area = view_area(live_refs.window(ptr))
        if area is None:
            return None
        setup_view(area.spaces.active)
        area.tag_redraw()
        state["n"] -= 1
        return 0.05 if state["n"] > 0 else None

    bpy.app.timers.register(tick, first_interval=0.01)


def open_window(context, area):
    """Copy ``area`` (the main 3D View) into the IPR window; the window, or None (failed or opens later)."""
    from ..operators import menu_extras
    new = menu_extras.open_window(context, area, KIND)
    if new is None:
        return None
    _state["win"] = new.as_pointer()
    _state["src"] = area.as_pointer()
    target = view_area(new)
    if target is not None:
        setup_view(target.spaces.active)
    _setup_later(_state["win"])
    if not bpy.app.timers.is_registered(_follow):
        bpy.app.timers.register(_follow, first_interval=FOLLOW_TICK)
    return new


def close():
    """Close the IPR window (from a timer: it may be the window the operator runs in)."""
    from . import marked_window
    win = window()
    _state["win"] = 0
    if win is not None:
        marked_window.close_later(win)


def register():
    _state["win"] = _state["src"] = 0


def unregister():
    if bpy.app.timers.is_registered(_follow):
        bpy.app.timers.unregister(_follow)
    _state["win"] = _state["src"] = 0
