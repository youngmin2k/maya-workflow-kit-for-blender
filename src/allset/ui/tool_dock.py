# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Tool Settings as a docked column left of the viewport.

Maya's Tool Settings is a dock control on the left of the main window (docked
left in Maya 2022). The kit's dock is a
Properties editor on its Tool tab, split off the left edge of the main 3D View, with its header and navigation bar
hidden: the Tool tab draws the 3D View "Tool" panels, i.e. ``tool_settings.ALLSET_PT_tool_settings`` (Maya sections)
and, for tools without Maya sections, Blender's own tool panels. The dock is recognised by its state (Tool tab and no
header), so it survives saving and reloading the file. ToggleToolSettings shows / hides it (Maya: visible ->
hidden -> visible); closing = ``screen.area_close`` (the viewport gets its width back).

GUI facts: ``screen.area_split(direction='VERTICAL', factor=f)`` with f < 0.5 puts
the new area on the left with width f x the old width; ``SpaceProperties.context`` can only be set the tick after the
area became a Properties editor (its enum is empty before); ``screen.region_toggle(region_type='NAVIGATION_BAR')``
hides the tab column. ``screen.area_close`` hangs in background mode, so ``close`` is GUI only.
"""

import bpy

from .. import live_refs

WIDTH = 280          # unscaled px (Maya's narrow panels are 260 by default; its Tool Settings 460)
MAX_SHARE = 0.35     # of the main viewport's width
_pending = {}        # area pointer -> True while a new dock waits for its first tick


def is_dock(area):
    if area is None or area.type != 'PROPERTIES':
        return False
    space = area.spaces.active
    if space.show_region_header or space.context != 'TOOL':
        return False
    from .maya_dock import ROLE_FLAGS     # a Maya panel's dock area is a Tool tab too: role flag set
    return not any(getattr(space, flag, False) for flag in ROLE_FLAGS.values())


def find(screen):
    """The Tool Settings dock area of ``screen`` (or None)."""
    for area in (screen.areas if screen else ()):
        if is_dock(area) or area.as_pointer() in _pending:
            return area
    return None


def shown(screen):
    return find(screen) is not None


def _main_view(screen):
    from .status_line import main_view3d
    return main_view3d(screen)


def configure(area, window=None):
    """Make ``area`` (already a Properties editor) the Tool Settings dock. True when done."""
    space = area.spaces.active
    try:
        space.context = 'TOOL'
    except TypeError:          # the space hasn't been initialised yet
        return False
    for prop in space.bl_rna.properties:
        ident = prop.identifier
        if ident.startswith("show_properties_") and ident != "show_properties_tool":
            setattr(space, ident, False)
    # Changing the visible context flags can make Blender fall back to Object.
    # Select Tool again after those updates so the new dock opens on its content.
    space.context = 'TOOL'
    space.show_region_header = False
    nav = next((r for r in area.regions if r.type == 'NAVIGATION_BAR'), None)
    if nav is not None and nav.width > 1 and window is not None:
        try:
            with bpy.context.temp_override(window=window, area=area):
                bpy.ops.screen.region_toggle(region_type='NAVIGATION_BAR')
        except (RuntimeError, TypeError):
            pass
    area.tag_redraw()
    return True


def open_dock(context, window=None, width=None):
    """Split the main viewport and put the dock on its left. Returns the new area or None."""
    window = window or context.window
    screen = window.screen if window is not None else context.screen
    if find(screen) is not None:
        return find(screen)
    area, region = _main_view(screen)
    if area is None or region is None:
        return None
    scale = context.preferences.system.ui_scale or 1.0      # 0 in background
    factor = min(MAX_SHARE, (width or WIDTH) * scale / max(area.width, 1))
    before = {a.as_pointer() for a in screen.areas}
    with context.temp_override(window=window, screen=screen, area=area, region=region):
        if bpy.ops.screen.area_split(direction='VERTICAL', factor=factor) != {'FINISHED'}:
            return None
    new = next((a for a in screen.areas if a.as_pointer() not in before), None)
    if new is None:
        return None
    new.ui_type = 'PROPERTIES'
    if configure(new, window):
        return new
    key = new.as_pointer()
    win_ptr = live_refs.pointer(window)
    _pending[key] = True

    def later(tries=[20]):
        # pointers, looked up each tick: a closed window's area must not be touched (#36)
        win, area = live_refs.find_area(key, win_ptr or None)
        try:
            if area is None:       # area or window gone
                done = True
            else:
                with bpy.context.temp_override(window=win):
                    done = configure(area, win)
        except ReferenceError:
            done = True
        tries[0] -= 1
        if done or tries[0] <= 0:
            _pending.pop(key, None)
            return None
        return 0.05
    bpy.app.timers.register(later, first_interval=0.0)
    return new


def close_dock(context, window=None):
    """Close the dock (GUI only). True when there was one."""
    window = window or context.window
    screen = window.screen if window is not None else context.screen
    area = find(screen)
    if area is None:
        return False
    _pending.pop(area.as_pointer(), None)
    if bpy.app.background:      # screen.area_close hangs without a UI
        return False
    with context.temp_override(window=window, screen=screen, area=area):
        bpy.ops.screen.area_close()
    return True


def show(context, width=None):
    """Maya Tool Settings from a Tool Box double-click (#3): a Tool Settings dock that is open in any
    window (docked or torn off) is redrawn — Blender can't raise an OS window — else the dock opens left of this
    window's viewport. Returns the dock area (or None)."""
    for window in context.window_manager.windows:
        area = find(window.screen)
        if area is not None:
            area.tag_redraw()
            return area
    return open_dock(context, width=width)


def toggle(context, show_only=False):
    """Maya ToggleToolSettings (``show_only``: open without closing). True = shown after."""
    screen = context.window.screen if context.window is not None else context.screen
    if shown(screen):
        if show_only:
            return True
        close_dock(context)
        return False
    return open_dock(context) is not None
