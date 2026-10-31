# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's docking model: every Maya panel is its own area or window, torn off by its ::::: handle
.

Maya builds every UI element as a dockable ``workspaceControl``; the right column is one tab stack of Channel Box /
Layer Editor, Attribute Editor and Modeling Toolkit, and a panel's
dotted handle tears it off into a floating window. Here:

- **Dock areas.** A Maya panel lives in its own Properties editor on the Tool tab, header and tab column hidden (the
  Tool tab draws 3D View "Tool"-category panels), never in the viewport's sidebar. The area's role is kept
  in the space's hidden tab flags (``ROLE_FLAGS``: Tool tab + one flag), so it survives saving and ``area_dupli``
  (the copy keeps context, flags and the hidden header). The Tool Settings dock (``tool_dock``) is the
  Tool tab with no role flag.
- **Stack.** The ``STACK`` area shows Maya's vertical tab strip on its right edge and the selected tab
  (``WindowManager.allset_dock``); kinds that have a floating window leave the strip.
- **Tear off / dock.** The handle row (``ALLSET_OT_dock_handle``) on a docked panel opens a floating window with only
  that panel (``area_dupli`` + role); on a floating panel it offers Dock (close the window, the panel goes back) and
  Close. A floating window closed by its OS button docks back by itself (the stack only hides kinds that float).
  Cross-window drag and drop isn't possible from Python: a click replaces Maya's drag.
- **Menus.** Kit Maya menus start with Maya's dotted tear-off line: a floating ``MENU`` window draws that menu's items
  as buttons (the menu id per window is kept in memory, ``_torn_menus``; a MENU window loaded from a file closes).
"""

import math

import bpy
from bpy.props import EnumProperty, StringProperty

from .. import i18n, live_refs

KINDS = ('CHANNEL_BOX', 'ATTRIBUTE_EDITOR', 'MODELING_TOOLKIT')
LABELS = {'CHANNEL_BOX': "Channel Box / Layer Editor", 'ATTRIBUTE_EDITOR': "Attribute Editor",
          'MODELING_TOOLKIT': "Modeling Toolkit", 'TOOL_SETTINGS': "Tool Settings", 'OUTLINER': "Outliner"}
# Role marker = Tool tab + exactly one of these hidden tab flags (invisible: the tab column is hidden).
ROLE_FLAGS = {'STACK': "show_properties_world", 'CHANNEL_BOX': "show_properties_physics",
              'ATTRIBUTE_EDITOR': "show_properties_effects", 'MODELING_TOOLKIT': "show_properties_particles",
              'MENU': "show_properties_texture"}
WIDTH = 260                  # unscaled px: Maya-style narrow panels
HANDLE = ":" * 8            # Maya's dotted grip on a workspaceControl (plain ASCII: every UI font has it)
TEAR_LINE = "- " * 18        # Maya's tear-off line at the top of a menu (``-to true``)

_torn_menus = {}             # window pointer -> (menu idname, label)
_pending = {}                # area pointer -> role it waits for (a new Properties space has no tab list yet)


# --- roles ---------------------------------------------------------------------------------------------------------

def _flags(space):
    return [p.identifier for p in space.bl_rna.properties if p.identifier.startswith("show_properties_")]


def role(area):
    """'STACK' / a KINDS member / 'MENU' for a kit dock area, else None (the Tool Settings dock has no role)."""
    if area is None or area.type != 'PROPERTIES':
        return None
    space = area.spaces.active
    if space.show_region_header or not space.show_properties_tool:
        return None
    on = [name for name, flag in ROLE_FLAGS.items() if getattr(space, flag, False)]
    if len(on) != 1:
        return None
    from .. import compat
    if any(getattr(space, f) for f in _flags(space)
           if f not in ("show_properties_tool", ROLE_FLAGS[on[0]]) and f not in compat.LATER_PROPERTIES_TABS):
        return None
    return on[0]


def set_role(area, name, window=None):
    """Make ``area`` (a Properties editor) a kit dock area with role ``name``. True when done; a space that hasn't
    drawn yet can't take the Tool tab, so callers retry (``set_role_later``)."""
    space = area.spaces.active
    try:
        space.context = 'TOOL'
    except TypeError:
        return False
    for flag in _flags(space):
        setattr(space, flag, flag == "show_properties_tool" or flag == ROLE_FLAGS.get(name))
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


def set_role_later(area, name, window=None, tries=40):
    if set_role(area, name, window):
        return
    key = area.as_pointer()
    win_ptr = live_refs.pointer(window)
    _pending[key] = name
    state = {"n": tries}

    def tick():
        # pointers, looked up each tick: a closed window's area must not be touched (#36)
        win, area_ = live_refs.find_area(key, win_ptr or None)
        try:
            if area_ is None:
                done = True
            elif win_ptr:
                with bpy.context.temp_override(window=win):
                    done = set_role(area_, name, win)
            else:
                done = set_role(area_, name, None)
        except ReferenceError:
            done = True
        state["n"] -= 1
        if done or state["n"] <= 0:
            _pending.pop(key, None)
            return None
        return 0.05
    bpy.app.timers.register(tick, first_interval=0.0)


def area_role(context):
    return role(getattr(context, "area", None))


def is_floating(window, wm=None):
    """A window holding a single area (Maya's floating panel), not the first window."""
    wm = wm or bpy.context.window_manager
    return window is not None and len(window.screen.areas) == 1 and wm.windows[0] != window


# --- stack ---------------------------------------------------------------------------------------------------------

def floating_kinds(wm=None):
    wm = wm or bpy.context.window_manager
    out = set()
    for window in wm.windows:
        for area in window.screen.areas:
            r = role(area)
            if r in KINDS:
                out.add(r)
    return out


def stack_tabs(wm=None):
    floating = floating_kinds(wm)
    return [k for k in KINDS if k not in floating]


def current_tab(wm=None):
    wm = wm or bpy.context.window_manager
    tabs = stack_tabs(wm)
    want = getattr(wm, "allset_dock", 'CHANNEL_BOX')
    return want if want in tabs else (tabs[0] if tabs else None)


def shown_kind(context):
    """The Maya panel this dock area shows (None: nothing)."""
    r = area_role(context)
    if r == 'STACK':
        return current_tab(context.window_manager)
    return r


def find_stack(screen):
    """The tab-stack area of ``screen`` (also one made this tick whose role is still pending)."""
    return next((a for a in (screen.areas if screen else ())
                 if role(a) == 'STACK' or _pending.get(a.as_pointer()) == 'STACK'), None)


def kind_visible(wm, kind):
    """The panel shows somewhere: the selected tab of a stack, or a floating window of its own."""
    if kind in floating_kinds(wm):
        return True
    if current_tab(wm) != kind:
        return False
    return any(find_stack(w.screen) is not None for w in wm.windows)


def _main_view(screen):
    from .status_line import main_view3d
    return main_view3d(screen)


def main_window(wm=None):
    """The window with the main Maya viewport (the first non-floating window)."""
    wm = wm or bpy.context.window_manager
    for window in wm.windows:
        if not is_floating(window, wm) and _main_view(window.screen)[0] is not None:
            return window
    return wm.windows[0] if wm.windows else None


def split_side(context, window, side, width, ui_type):
    """Split ``window``'s main viewport and return the new area on ``side`` ('LEFT' / 'RIGHT') of ``width`` unscaled
    px (VERTICAL factor < 0.5 = new area left, factor > 0.5 = new area right, ``1 - factor`` wide)."""
    screen = window.screen
    area, region = _main_view(screen)
    if area is None or region is None:
        return None
    scale = context.preferences.system.ui_scale or 1.0
    share = min(0.4, width * scale / max(area.width, 1))
    factor = share if side == 'LEFT' else 1.0 - share
    before = {a.as_pointer() for a in screen.areas}
    with context.temp_override(window=window, screen=screen, area=area, region=region):
        if bpy.ops.screen.area_split(direction='VERTICAL', factor=factor) != {'FINISHED'}:
            return None
    new = next((a for a in screen.areas if a.as_pointer() not in before), None)
    if new is not None:
        new.ui_type = ui_type
    return new


def open_stack(context, window=None):
    """The stack area right of ``window``'s viewport (made if missing)."""
    window = window or main_window(context.window_manager)
    if window is None:
        return None
    stack = find_stack(window.screen)
    if stack is not None:
        return stack
    new = split_side(context, window, 'RIGHT', WIDTH, 'PROPERTIES')
    if new is not None:
        set_role_later(new, 'STACK', window)
    return new


def close_area(context, window, area):
    """``screen.area_close`` (GUI only: it hangs in background)."""
    if bpy.app.background or area is None:
        return False
    with context.temp_override(window=window, screen=window.screen, area=area):
        return bpy.ops.screen.area_close() == {'FINISHED'}


def close_window_later(window):
    """Close a window from a timer (closing the window an operator runs in would pull the context away)."""
    ptr = live_refs.pointer(window)

    def tick():
        window = live_refs.window(ptr)
        try:
            if window is not None:
                with bpy.context.temp_override(window=window):
                    bpy.ops.wm.window_close()
        except (ReferenceError, RuntimeError):
            pass
        return None
    bpy.app.timers.register(tick, first_interval=0.0)


def show(context, kind):
    """Maya Windows > ... : raise the panel (stack tab), else open it floating when the layout has no stack."""
    wm = context.window_manager
    wm.allset_dock = kind          # the stack's tab (also when the panel floats: it comes back there)
    if kind in floating_kinds(wm):
        return 'FLOATING'
    window = main_window(wm)
    if window is not None and find_stack(window.screen) is not None:
        redraw()
        return 'DOCKED'
    # No tab stack in this layout: one floating dock window switches between the panels (Ctrl+A flips it between
    # Attribute Editor and Channel Box instead of opening a window per press)
    for w in wm.windows:
        if is_floating(w, wm) and role(w.screen.areas[0]) in KINDS:
            set_role(w.screen.areas[0], kind, w)
            redraw()
            return 'FLOATING'
    return 'FLOATING' if open_floating(context, kind) is not None else None


def toggle(context, kind, show_only=False):
    """Maya Windows > UI Elements toggle: a hidden or tabbed-behind panel is raised; a shown one is hidden (its
    floating window closed, or the tab stack closed when it is the stack's tab). Returns True = shown after."""
    wm = context.window_manager
    if kind_visible(wm, kind):
        if show_only:
            return True
        for window in list(wm.windows):
            if is_floating(window, wm) and role(window.screen.areas[0]) == kind:
                close_window_later(window)
                return False
        window = main_window(wm)
        stack = find_stack(window.screen) if window is not None else None
        if stack is not None:
            close_area(context, window, stack)
        return False
    window = main_window(wm)
    if window is not None and find_stack(window.screen) is None and _main_view(window.screen)[0] is not None:
        wm.allset_dock = kind
        with context.temp_override(window=window):
            open_stack(bpy.context, window)
        return True
    return show(context, kind) is not None


def open_floating(context, kind):
    """A floating window with only ``kind`` (no stack to raise it in)."""
    from ..operators.menu_extras import open_window
    window = context.window or main_window(context.window_manager)
    if window is None:
        return None
    area = max(window.screen.areas, key=lambda a: a.width * a.height, default=None)
    if area is None:
        return None
    new = open_window(context, area)
    if new is None:
        return None
    target = new.screen.areas[0]
    target.ui_type = 'PROPERTIES'
    set_role_later(target, kind, new)
    return new


# --- tear off / dock -----------------------------------------------------------------------------------------------
# Issue #4: Blender has no API to size or place a window, and ``screen.area_dupli`` opens a window of the copied
# area's size. So the source area is first split (``area_split`` HORIZONTAL, factor > 0.5 = the new area on top,
# 1 - factor tall) to the content height computed by ``layout_measure``; that top piece is
# copied a tick later (a split area has no size before the screen refreshed: a copy in the same call opened a
# default-size window) and closed again, which gives the source its height back.

MIN_ROWS = 6                 # a torn-off window is never shorter than this ...
PAD_ROWS = 1.5               # ... and gets the region's top / bottom margins on top of its content
MIN_KEEP_PX = 40             # Blender keeps a split's other part at least about a header high


def content_height(context, n_rows, limit):
    """Window height (px) for ``n_rows`` rows of content, clamped to [MIN_ROWS rows, ``limit``]."""
    from . import layout_measure
    rows = max(MIN_ROWS, (n_rows or 0) + PAD_ROWS)
    return min(layout_measure.px(rows, context), limit)


def panel_rows(context, area=None):
    """Rows the Maya panel in ``area`` draws now (estimated for the Outliner / Tool Settings), or None."""
    from . import layout_measure
    area = area or context.area
    if area is not None and area.type == 'OUTLINER':
        n = sum(1 for _ in context.scene.objects) + 7       # objects + the startup rows Maya lists + header
        return min(n, 40)
    if role(area) is None:
        from . import tool_dock
        return 24 if tool_dock.is_dock(area) else None     # Tool Settings: Move / Rotate / Scale settings
    return layout_measure.rows(ALLSET_PT_maya_dock.draw, context)


def menu_rows(context, idname):
    """Rows a torn-off menu window shows: handle + title + the menu's items."""
    from . import layout_measure
    cls = getattr(bpy.types, idname, None)
    if cls is None:
        return None
    _drawing_torn[0] = True           # the torn copy has no tear-off line
    try:
        n = layout_measure.rows(cls.draw, context)
    finally:
        _drawing_torn[0] = False
    return None if n is None else n + 2


def sized_window(context, window, area, height, then, tries=20):
    """Open a window copying ``area`` about ``height`` px tall (the area's full height when it isn't taller), then
    call ``then(new_window)`` (now or from a timer). Returns True when a window is (being) made."""
    from ..operators.menu_extras import open_window
    if bpy.app.background or area is None:
        return False
    full = area.height
    if height >= full - MIN_KEEP_PX:
        with context.temp_override(window=window):
            new = open_window(bpy.context, area)
        if new is None:
            return False
        then(new)
        return True
    screen = window.screen
    before = {a.as_pointer() for a in screen.areas}
    factor = 1.0 - height / max(full, 1)
    with context.temp_override(window=window, screen=screen, area=area):
        if bpy.ops.screen.area_split(direction='HORIZONTAL', factor=factor) != {'FINISHED'}:
            return False
    piece_ptr = next((a.as_pointer() for a in screen.areas if a.as_pointer() not in before), None)
    if piece_ptr is None:
        return False
    state = {"n": tries}
    win_ptr = window.as_pointer()

    def tick():
        try:
            wm = bpy.context.window_manager
            win = next((w for w in wm.windows if w.as_pointer() == win_ptr), None)
            if win is None:
                return None
            piece = next((a for a in win.screen.areas if a.as_pointer() == piece_ptr), None)
            if piece is None:
                return None
            if piece.height <= 1 and state["n"] > 0:    # the screen hasn't refreshed the split yet
                state["n"] -= 1
                return 0.02
            with bpy.context.temp_override(window=win):
                new = open_window(bpy.context, piece)
            close_area(bpy.context, win, piece)          # the source gets its height back
            if new is not None:
                then(new)
        except ReferenceError:
            pass
        return None
    bpy.app.timers.register(tick, first_interval=0.02)
    return True


def _area_by_pointer(window, ptr):
    try:
        return next((a for a in window.screen.areas if a.as_pointer() == ptr), None)
    except ReferenceError:
        return None


def tear_off(context, area=None):
    """Tear the panel in ``area`` off into a floating window sized to the panel (issue #4). Returns True when the
    window is (being) made, None when this area can't be torn off."""
    from . import tool_dock
    area = area or context.area
    window = context.window
    wm = context.window_manager
    r = role(area)
    if r != 'STACK' and not (area is not None and (tool_dock.is_dock(area) or area.type == 'OUTLINER')):
        return None
    height = content_height(context, panel_rows(context, area), area.height)
    area_ptr = area.as_pointer()
    if r == 'STACK':
        kind = current_tab(wm)
        if kind is None:
            return None
        rest = [k for k in stack_tabs(wm) if k != kind]

        def then(new):
            set_role_later(new.screen.areas[0], kind, new)
            if rest:
                bpy.context.window_manager.allset_dock = rest[0]
            else:                                   # an empty tab stack goes away, like Maya's
                close_area(bpy.context, window, _area_by_pointer(window, area_ptr))
            redraw()
        return True if sized_window(context, window, area, height, then) else None
    outliner = area.type == 'OUTLINER'

    def then(new):
        if outliner:
            from . import maya_outliner
            maya_outliner.setup(new.screen.areas[0].spaces.active)
        close_area(bpy.context, window, _area_by_pointer(window, area_ptr))
    return True if sized_window(context, window, area, height, then) else None


def dock(context, window=None):
    """Put the floating panel in ``window`` back into the main window's layout and close the window."""
    window = window or context.window
    area = window.screen.areas[0] if window and window.screen.areas else None
    if area is None:
        return False
    r = role(area)
    main = main_window(context.window_manager)
    main_ptr = live_refs.pointer(main)
    if r == 'MENU':
        _torn_menus.pop(window.as_pointer(), None)
    elif r in KINDS:
        close_window_later(window)

        def back():
            main = live_refs.window(main_ptr)
            try:
                bpy.context.window_manager.allset_dock = r
                if main is not None:
                    with bpy.context.temp_override(window=main):
                        open_stack(bpy.context, main)
                redraw()
            except ReferenceError:
                pass
            return None
        bpy.app.timers.register(back, first_interval=0.05)
        return True
    else:
        from . import tool_dock
        kind = 'TOOL_SETTINGS' if tool_dock.is_dock(area) else ('OUTLINER' if area.type == 'OUTLINER' else None)
        if kind is None or main is None:
            return False
        close_window_later(window)

        def back():
            main = live_refs.window(main_ptr)
            if main is None:
                return None
            try:
                with bpy.context.temp_override(window=main):
                    if kind == 'TOOL_SETTINGS':
                        tool_dock.open_dock(bpy.context, main)
                    elif not any(a.type == 'OUTLINER' for a in main.screen.areas):
                        new = split_side(bpy.context, main, 'LEFT', WIDTH, 'OUTLINER')
                        if new is not None:
                            from . import maya_outliner
                            maya_outliner.setup(new.spaces.active)
            except ReferenceError:
                pass
            return None
        bpy.app.timers.register(back, first_interval=0.05)
        return True
    close_window_later(window)
    return True


def tear_menu(context, idname, label):
    """Maya's menu tear-off: a floating window listing the menu's items, as tall as the menu (issue #4)."""
    window = main_window(context.window_manager) or context.window
    # Maya's torn-off menus are a narrow column: copy a narrow side panel (the tallest, so any menu fits), the
    # viewport only when there is none
    side = [a for a in window.screen.areas if a.type in {'PROPERTIES', 'OUTLINER'} and a.height > 200]
    area = max(side, key=lambda a: a.height) if side else _main_view(window.screen)[0]
    if area is None:
        return None
    with context.temp_override(window=window):
        height = content_height(bpy.context, menu_rows(bpy.context, idname), area.height)

    def then(new):
        _torn_menus[new.as_pointer()] = (idname, label)
        target = new.screen.areas[0]
        target.ui_type = 'PROPERTIES'
        set_role_later(target, 'MENU', new)
    with context.temp_override(window=window):
        return True if sized_window(bpy.context, window, area, height, then) else None


def redraw():
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PROPERTIES':
                    area.tag_redraw()
    except (AttributeError, ReferenceError):
        pass


# --- operators -----------------------------------------------------------------------------------------------------

class ALLSET_OT_dock_handle(bpy.types.Operator):
    """Maya panel handle: click to tear this panel off into a floating window; on a floating panel, dock it back"""
    bl_idname = "allset.dock_handle"
    bl_label = "Panel Handle"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if is_floating(context.window, context.window_manager):
            context.window_manager.popup_menu(_draw_float_menu, title=_float_title(context))
            return {'FINISHED'}
        return self.execute(context)

    def execute(self, context):
        if tear_off(context) is None:
            self.report({'WARNING'}, "This panel can't be torn off")
            return {'CANCELLED'}
        return {'FINISHED'}


def _float_title(context):
    r = area_role(context)
    if r in LABELS:
        return LABELS[r]
    if r == 'MENU':
        return _torn_menus.get(context.window.as_pointer(), ("", "Menu"))[1]
    return LABELS['OUTLINER'] if context.area and context.area.type == 'OUTLINER' else LABELS['TOOL_SETTINGS']


def _draw_float_menu(self, context):
    layout = self.layout
    if area_role(context) != 'MENU':
        layout.operator(ALLSET_OT_dock_back.bl_idname, text="Dock", icon='DOCUMENTS').action = 'DOCK'
    layout.operator(ALLSET_OT_dock_back.bl_idname, text="Close", icon='X').action = 'CLOSE'


class ALLSET_OT_dock_back(bpy.types.Operator):
    """Dock this floating panel again (or close it)"""
    bl_idname = "allset.dock_back"
    bl_label = "Dock Panel"
    bl_options = {'INTERNAL'}

    action: EnumProperty(items=(('DOCK', "Dock", ""), ('CLOSE', "Close", "")), options={'SKIP_SAVE'})

    def execute(self, context):
        if self.action == 'CLOSE':
            _torn_menus.pop(context.window.as_pointer(), None)
            close_window_later(context.window)   # a closed panel window docks back by itself (stack tabs)
            return {'FINISHED'}
        return {'FINISHED'} if dock(context) else {'CANCELLED'}


class ALLSET_OT_dock_tab(bpy.types.Operator):
    """Show this panel in the tab stack"""
    bl_idname = "allset.dock_tab"
    bl_label = "Dock Tab"
    bl_options = {'INTERNAL'}

    kind: EnumProperty(items=[(k, LABELS[k], "") for k in KINDS])

    def execute(self, context):
        context.window_manager.allset_dock = self.kind
        redraw()
        return {'FINISHED'}


class ALLSET_OT_panel_show(bpy.types.Operator):
    """Show this Maya panel: raise it where it is docked, else open it as a floating window (Maya Windows menu)"""
    bl_idname = "allset.panel_show"
    bl_label = "Show Panel"
    bl_options = {'INTERNAL'}

    panel: EnumProperty(items=[(k, LABELS[k], "") for k in (*KINDS, 'OUTLINER', 'TOOL_SETTINGS')])

    def execute(self, context):
        if self.panel in KINDS:
            return {'FINISHED'} if show(context, self.panel) else {'CANCELLED'}
        wm = context.window_manager
        if self.panel == 'TOOL_SETTINGS':
            from . import tool_dock
            if any(tool_dock.is_dock(a) for w in wm.windows for a in w.screen.areas):
                return {'FINISHED'}
            tool_dock.toggle(context, show_only=True)
            return {'FINISHED'}
        # Outliner: docked in this layout or already floating = shown; else a floating Maya Outliner
        if any(a.type == 'OUTLINER' for w in wm.windows for a in w.screen.areas):
            return {'FINISHED'}
        return bpy.ops.allset.open_editor(ui_type='OUTLINER')


class ALLSET_OT_menu_tear_off(bpy.types.Operator):
    """Tear off this menu into a floating window (Maya's dotted line at the top of a menu)"""
    bl_idname = "allset.menu_tear_off"
    bl_label = "Tear Off"
    bl_options = {'INTERNAL'}

    menu: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        cls = getattr(bpy.types, self.menu, None)
        if cls is None:
            return {'CANCELLED'}
        menu, label = self.menu, cls.bl_label

        def later():   # after the menu has closed
            try:
                tear_menu(bpy.context, menu, label)
            except Exception as ex:
                print("Maya Workflow Kit: menu tear-off failed:", ex)
            return None
        bpy.app.timers.register(later, first_interval=0.0)
        return {'FINISHED'}


def draw_tear_line(layout, idname):
    """Maya's dotted first line of a menu (click = tear off)."""
    if _drawing_torn[0]:
        return
    from . import draw_safe     # the operator may be missing (a half-registered kit): the menu still draws (#199)
    draw_safe.op(layout, ALLSET_OT_menu_tear_off.bl_idname, text=TEAR_LINE, emboss=False).menu = idname


_drawing_torn = [False]


def drawing_torn():
    """True while a torn-off menu window draws its menu's items."""
    return _drawing_torn[0]


# --- panel ---------------------------------------------------------------------------------------------------------

def draw_handle(layout, context=None, tabs=False):
    """The top row of a Maya panel: Maya's dotted grip (click = tear off / dock) and, in the tab stack, the tabs
    (Maya's title / tab row above the editor's menu bar)."""
    row = layout.row(align=True)
    grip = row.row(align=True)
    grip.alignment = 'LEFT'
    if tabs and context is not None:
        # Blender splits an expanded row into equal tabs ("Channel Box / Layer Editor" was cut while "Attribute
        # Editor" got twice its text): each tab gets its text's width (the same rule sizes the dock,
        # ui/toolbox.dock_need)
        row.alignment = 'LEFT'
        grip.ui_units_x = text_units(context, HANDLE, GRIP_PAD)
    grip.operator(ALLSET_OT_dock_handle.bl_idname, text=HANDLE, emboss=False)
    if tabs and context is not None:
        current = current_tab(context.window_manager)
        for kind in stack_tabs(context.window_manager):
            tab = row.row(align=True)
            tab.ui_units_x = text_units(context, i18n.iface(LABELS[kind]), TAB_PAD)
            tab.operator(ALLSET_OT_dock_tab.bl_idname, text=LABELS[kind], depress=(kind == current)).kind = kind


TAB_PAD = 1.0       # UI units around a tab's text
GRIP_PAD = 1.5


def text_units(context, text, pad):
    """Width of ``text`` in Blender's UI font (11 pt x UI scale) in UI units, plus ``pad`` units."""
    import blf
    system = context.preferences.system
    s = system.ui_scale or 1.0
    u = math.floor(18.0 * s + 0.5) + 2 * system.pixel_size
    blf.size(0, 11.0 * s)
    return blf.dimensions(0, text)[0] / max(u, 1) + pad


# --- vertical tab strip (#78) ----------------------------------------------------------------------------
# Maya's stack tabs are a vertical strip on the stack's right edge, so the stack is only as wide as its panel
# (tabs from the content top, the text + a small margin at each end, close together, reading top to bottom; the
# raised tab in the panel colour, lowered tabs and the strip darker). Blender can't lay a button out rotated, so the
# strip is drawn here
# (POST_PIXEL, blf rotation) in a column the panel content keeps clear of (``content_layout``), and a click on it goes
# to ``ALLSET_OT_dock_strip_click`` (first in "View2D Buttons List", like ui/outliner_sets.py's rows). Chosen over
# a width that follows the raised tab with horizontal tabs: the tab row alone needed 466 px at UI scale 1.
STRIP_PX = 18          # strip width at UI scale 1 (Blender's UI font is a little taller)
STRIP_GAP_PX = 6       # between the content and the strip
STRIP_TOP_PX = 4       # first tab below the region's top
TAB_END_PX = 11        # around a tab's text
TAB_GAP_PX = 2
STRIP_SHADE = 0.63     # strip background x the region background
TAB_SHADE = 0.81       # lowered tab x the region background
TEXT_LOWERED = 0.62    # lowered tab text x the theme text colour
PANEL_MARGIN_U = 0.4   # Blender's panel margin on each side of a Properties region, in widget units

_drawn = {}            # stack area pointer -> the tab drawn last (draw -> tab change -> dock width, toolbox)
_strip_handle = []


def _ui_unit(scale, pixel_size=1.0):
    from .toolbar_fit import unit
    return unit(scale, pixel_size)


def strip_px(scale):
    return round(STRIP_PX * scale)


def reserved_px(scale):
    """Region px the stack's content leaves free at the right for the strip (strip + gap)."""
    return strip_px(scale) + round(STRIP_GAP_PX * scale)


def area_reserved_px(context):
    """``reserved_px`` in a tab-stack area, else 0 (what a content width rule subtracts from ``region.width``)."""
    if area_role(context) != 'STACK':
        return 0
    return reserved_px(context.preferences.system.ui_scale or 1.0)


def content_factor(width, scale, pixel_size=1.0):
    """Split factor of the stack's content column so it ends ``STRIP_GAP_PX`` left of the strip, for a region
    ``width`` px wide (the panel layout spans the region minus Blender's margin on each side)."""
    margin = PANEL_MARGIN_U * _ui_unit(scale, pixel_size)
    span = width - 2 * margin
    if span <= 1:
        return 1.0
    return max(0.0, min(1.0, (width - reserved_px(scale) - margin) / span))


class StripClear:
    """The stack panel's root layout kept left of the strip: every item drawn into it goes into its own split
    (content | an empty strip column). One split column for everything would move every row: a nested column spaces
    its items by the style's ``buttonspacey``, the panel's root by ``templatespace`` (the Channel Box rows
    came 4 px closer each at UI scale 1.5, and the GUI tests' row offsets missed). Attributes go to the root."""

    __slots__ = ("_root", "_factor")

    def __init__(self, root, factor):
        object.__setattr__(self, "_root", root)
        object.__setattr__(self, "_factor", factor)

    def __getattr__(self, name):
        value = getattr(self._root, name)
        if not callable(value):
            return value

        def call(*args, **kw):
            split = self._root.split(factor=self._factor)
            col = split.column()
            split.column()             # the strip's column: empty, drawn over by draw_strip
            return getattr(col, name)(*args, **kw)
        return call

    def __setattr__(self, name, value):
        setattr(self._root, name, value)


def content_layout(layout, context):
    """The layout the stack's panel draws into: left of the strip."""
    region = context.region
    if region is None or region.width <= 1:
        return layout
    system = context.preferences.system
    f = content_factor(region.width, system.ui_scale or 1.0, system.pixel_size)
    if f <= 0.2 or f >= 1.0:
        return layout
    return StripClear(layout, f)


def strip_tabs(kinds, width, height, scale, measure=None):
    """[(kind, x0, y0, x1, y1)] region rects of the strip's tabs (y up, first tab at the top)."""
    if measure is None:
        from .toolbox import text_px as measure
    x1 = width
    x0 = width - strip_px(scale)
    y = height - round(STRIP_TOP_PX * scale)
    out = []
    for kind in kinds:
        length = math.ceil(measure(i18n.iface(LABELS[kind]), scale) + 2 * TAB_END_PX * scale)
        out.append((kind, x0, y - length, x1, y))
        y -= length + round(TAB_GAP_PX * scale)
    return out


def strip_hit(kinds, width, height, scale, x, y, measure=None):
    """(inside the strip, kind of the tab at region point (x, y) or None)."""
    if x < width - strip_px(scale) or x > width:
        return False, None
    for kind, _x0, y0, _x1, y1 in strip_tabs(kinds, width, height, scale, measure):
        if y0 <= y <= y1:
            return True, kind
    return True, None


def tab_drawn(context, kind):
    """Remember the tab a stack area drew; a change resizes the stack Maya's way (toolbox.tab_changed)."""
    area = context.area
    if area is None or kind is None:
        return
    key = area.as_pointer()
    old = _drawn.get(key)
    _drawn[key] = kind
    if old is not None and old != kind and context.window is not None:
        from . import toolbox
        toolbox.tab_changed(context.window, old, kind)


def _strip_colours(context):
    th = context.preferences.themes[0]
    try:
        back = tuple(th.properties.space.back)[:3]
        text = tuple(th.properties.space.text)[:3]
    except AttributeError:
        back, text = (0.19, 0.19, 0.19), (0.9, 0.9, 0.9)
    lift = dock_lift(context)
    return tuple(min(1.0, c + lift) for c in back), text


# Maya-style dock grey #444444 (Blender's factory Properties grey is #303030). The kit
# ships no theme, so the dock areas are lifted by the difference after drawing: an additive grey over the
# region raises the background to #444444 and the value fields with it (#1d1d1d -> #313131); text stays
# near white. Only a theme darker than that is lifted, never a light one.
MAYA_DOCK_GREY = 0x44 / 255.0
TINTED_ROLES = {'STACK', 'CHANNEL_BOX', 'ATTRIBUTE_EDITOR', 'MODELING_TOOLKIT'}


def dock_lift(context):
    """The sRGB grey added over a Maya dock (0 when the preference is off or the theme is already as light)."""
    from .. import preferences
    try:
        on = preferences.get().maya_dock_colors
    except Exception:
        on = True
    if not on:
        return 0.0
    th = context.preferences.themes[0]
    try:
        back = tuple(th.properties.space.back)[:3]
    except AttributeError:
        return 0.0
    d = MAYA_DOCK_GREY - max(back)
    return d if 0.0 < d <= 0.2 else 0.0


def draw_tint():
    """Lift a Maya dock area to Maya's grey (``dock_lift``): one additive quad over the WINDOW region."""
    context = bpy.context
    area, region = context.area, context.region
    if region is None or region.type != 'WINDOW' or role(area) not in TINTED_ROLES:
        return
    d = dock_lift(context)
    if d <= 0.0:
        return
    import gpu
    w, h = region.width, region.height
    hole = _list_hole(context, region) if shown_kind(context) == 'CHANNEL_BOX' else None
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ADDITIVE')
    try:
        for x0, y0, x1, y1 in _around(hole, w, h):
            _fill(shader, x0, y0, x1, y1, (d, d, d, 1.0))
    finally:
        gpu.state.blend_set('NONE')


def _around(hole, w, h):
    """Rects covering (0, 0, w, h) except ``hole`` (x0, y0, x1, y1)."""
    if hole is None:
        return [(0, 0, w, h)]
    x0, y0, x1, y1 = hole
    return [r for r in ((0, 0, w, y0), (0, y1, w, h), (0, y0, x0, y1), (x1, y0, w, y1)) if r[2] > r[0] and r[3] > r[1]]


def dark_span(values, limit):
    """(first, last) index of the values below ``limit`` (0-255), or None."""
    idx = [i for i, v in enumerate(values) if v < limit]
    return (idx[0], idx[-1]) if idx else None


def dark_top(values, start, limit, gap):
    """Highest index from ``start`` upward still in the dark block: dark values with no run of more than ``gap``
    lighter ones between them and ``start`` (a selected layer row inside the list doesn't end it)."""
    top, light = start, 0
    for i in range(start, len(values)):
        if values[i] < limit:
            top, light = i, 0
        else:
            light += 1
            if light > gap:
                break
    return top


_hole_row = {}    # region pointer -> framebuffer row that last crossed the list body


def _list_hole(context, region):
    """The Layer Editor list body (Blender's list grey is already as dark): left unlifted. Found in the drawn
    pixels — one row near the region bottom for its sides, one column inside its left edge for its top."""
    import gpu
    scale = context.preferences.system.ui_scale or 1.0
    try:
        back = max(tuple(context.preferences.themes[0].properties.space.back)[:3])
    except AttributeError:
        return None
    limit = back * 255.0 - 4.0
    from . import channel_box
    le_top = int(region.height * (1.0 - channel_box.cb_share(region, channel_box._unit(context))))
    # the list ends 14 px x scale above the region bottom in a tall dock, higher in a shorter one (the
    # Time Slider grew at UI 1.25 and the list bottom left the sampled row): sample upwards, the last hit first
    fb = gpu.state.active_framebuffer_get()
    key = region.as_pointer()
    first = max(1, round(14 * scale))
    rows = [_hole_row.get(key)] + list(range(first, round(64 * scale), max(1, round(4 * scale))))
    span, ys = None, first
    for ys in rows:
        if ys is None or le_top <= ys + 10:
            continue
        try:
            row = fb.read_color(0, ys, region.width, 1, 4, 0, 'UBYTE').to_list()
        except ValueError:
            return None
        span = dark_span([px[0] for px in row[0]], limit)
        if span is not None and span[1] - span[0] >= 40 * scale:
            break
        span = None
    if span is None:
        _hole_row.pop(key, None)
        return None
    _hole_row[key] = ys
    x0, x1 = span
    try:
        col = fb.read_color(x0 + 1, 0, 1, le_top, 4, 0, 'UBYTE').to_list()
    except ValueError:
        return None
    values = [c[0][0] for c in col]
    if values[ys] >= limit:
        return None
    top = dark_top(values, ys, limit, round(30 * scale))
    bottom = ys
    while bottom > 0 and values[bottom - 1] < limit:
        bottom -= 1
    return (x0, bottom, x1 + 1, top + 1)


def draw_strip():
    context = bpy.context
    area, region = context.area, context.region
    if region is None or region.type != 'WINDOW' or role(area) != 'STACK':
        return
    import blf
    import gpu
    scale = context.preferences.system.ui_scale or 1.0
    current = current_tab(context.window_manager)
    tabs = strip_tabs(stack_tabs(context.window_manager), region.width, region.height, scale)
    back, text = _strip_colours(context)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    x0 = region.width - strip_px(scale)
    _fill(shader, x0, 0, region.width, region.height, (*(c * STRIP_SHADE for c in back), 1.0))
    blf.size(0, 11.0 * scale)
    cap = blf.dimensions(0, "X")[1]
    blf.enable(0, blf.ROTATION)
    blf.rotation(0, -math.pi / 2)     # clockwise: reads top to bottom, letter tops to the right (Maya)
    try:
        for kind, tx0, ty0, tx1, ty1 in tabs:
            raised = kind == current
            _fill(shader, tx0, ty0, tx1, ty1, (*(back if raised else tuple(c * TAB_SHADE for c in back)), 1.0))
            colour = text if raised else tuple(c * TEXT_LOWERED for c in text)
            blf.color(0, *colour, 1.0)
            blf.position(0, round((tx0 + tx1) / 2 - cap / 2), ty1 - round(TAB_END_PX * scale), 0)
            blf.draw(0, i18n.iface(LABELS[kind]))
    finally:
        blf.disable(0, blf.ROTATION)
        gpu.state.blend_set('NONE')


def _fill(shader, x0, y0, x1, y1, rgba):
    from gpu_extras.batch import batch_for_shader
    batch = batch_for_shader(shader, 'TRIS', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]},
                             indices=[(0, 1, 2), (0, 2, 3)])
    shader.uniform_float("color", rgba)
    batch.draw(shader)


def _strip_callback():
    try:
        draw_tint()
        draw_strip()
    except Exception:     # a draw error would repeat every redraw
        import traceback
        traceback.print_exc()


class ALLSET_OT_dock_strip_click(bpy.types.Operator):
    """Maya tab strip of the dock: click a tab to raise that panel"""
    bl_idname = "allset.dock_strip_click"
    bl_label = "Dock Tab Strip"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.region is not None and context.region.type == 'WINDOW' and area_role(context) == 'STACK'

    def invoke(self, context, event):
        region = context.region
        wm = context.window_manager
        inside, kind = strip_hit(stack_tabs(wm), region.width, region.height,
                                 context.preferences.system.ui_scale or 1.0,
                                 event.mouse_region_x, event.mouse_region_y)
        if not inside:
            return {'PASS_THROUGH'}
        if kind is not None and kind != current_tab(wm):
            wm.allset_dock = kind
            redraw()
        return {'FINISHED'}


class ALLSET_PT_maya_dock(bpy.types.Panel):
    """A Maya panel in its own dock area or floating window (Channel Box / Layer Editor, Attribute Editor, Modeling
    Toolkit, torn-off menus)"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"           # = drawn by the Properties Tool tab (like Tool Settings)
    bl_label = "Maya Panel"
    bl_options = {'HIDE_HEADER'}
    bl_order = -200

    @classmethod
    def poll(cls, context):
        return area_role(context) is not None

    def draw(self, context):
        layout = self.layout
        r = area_role(context)
        if r == 'MENU':
            draw_handle(layout)
            draw_torn_menu(layout, context)
            return
        if r == 'STACK':
            # #78: Maya's tabs are the vertical strip on the stack's right edge (draw_strip); the content
            # keeps clear of it
            layout = content_layout(layout, context)
        draw_handle(layout, context)
        kind = shown_kind(context)
        if r == 'STACK':
            tab_drawn(context, kind)
        if kind is None:
            layout.label(text="Every panel of this tab stack is in its own window")
            return
        from . import channel_box
        if kind == 'CHANNEL_BOX':
            units = channel_box.ALLSET_PT_channel_box.body(layout, context)
            channel_box.fill_pane(layout, context, units)
            from . import set_driven_key    # its lists fit the room the Channel Box leaves (#77)
            set_driven_key.remember_room(context, units)
            from . import layer_editor      # Maya's Layer Editor under the Channel Box (or the Set Driven Key window)
            layer_editor.ALLSET_PT_layer_editor.draw(_Holder(layout), context)
        elif kind == 'ATTRIBUTE_EDITOR':
            from . import attribute_editor
            attribute_editor.draw_panel(layout, context)
        elif kind == 'MODELING_TOOLKIT':
            from . import modeling_toolkit
            modeling_toolkit.draw(layout, context)


def draw_torn_menu(layout, context):
    entry = _torn_menus.get(context.window.as_pointer()) if context.window else None
    if entry is None:
        layout.label(text="This torn-off menu ended with its session")
        return
    cls = getattr(bpy.types, entry[0], None)
    if cls is None:
        return
    layout.label(text=entry[1])
    col = layout.column(align=True)
    col.alignment = 'LEFT'           # items left-aligned like the menu (not centred buttons)
    col.emboss = 'PULLDOWN_MENU'
    _drawing_torn[0] = True
    try:
        cls.draw(_Holder(_LeftItems(col)), context)
    finally:
        _drawing_torn[0] = False


class _Holder:
    def __init__(self, layout):
        self.layout = layout


# Maya's torn-off menu reads like the menu, every item's text from the left edge. Outside a menu Blender
# centres an operator button's text (plain, press-and-hold for the option box, radio choice; sub-menu rows, labels
# and check boxes stay left), and ``column.alignment`` doesn't change that: a row aligned LEFT around the button
# sizes it to its text, which then starts at the left. The hotkey / option box column (``menu_sets.item_texts``) is
# in the text, so it still lines up; the rows keep their height (``menu_rows``).
_CENTRED = ("operator", "operator_menu_hold", "prop_enum")


class _LeftItems:
    """The torn-off menu's column: each centred button in its own left-aligned row, the rest as drawn."""

    def __init__(self, col):
        object.__setattr__(self, "_col", col)

    def __getattr__(self, name):
        if name not in _CENTRED:
            return getattr(self._col, name)

        def left(*args, **kwargs):
            row = self._col.row(align=True)
            row.alignment = 'LEFT'
            return getattr(row, name)(*args, **kwargs)
        return left

    def __setattr__(self, name, value):
        setattr(self._col, name, value)


def _close_stale_menus():
    """MENU windows restored from a file have no menu to show (the id lives in memory): close them."""
    wm = bpy.context.window_manager
    for window in list(wm.windows):
        if window.as_pointer() in _torn_menus:
            continue
        if len(window.screen.areas) == 1 and role(window.screen.areas[0]) == 'MENU':
            close_window_later(window)
    return None


@bpy.app.handlers.persistent
def _on_load(*_args):
    _torn_menus.clear()
    _drawn.clear()          # area pointers of the old file may be reused
    if not bpy.app.background:
        bpy.app.timers.register(_close_stale_menus, first_interval=0.2)


def close_floating():
    """Switch to Blender: close windows whose only area is a kit role (they would show Blender's Tool tab)."""
    wm = bpy.context.window_manager
    for window in list(wm.windows):
        if is_floating(window, wm) and role(window.screen.areas[0]) is not None:
            close_window_later(window)
    _torn_menus.clear()


classes = (ALLSET_OT_dock_handle, ALLSET_OT_dock_back, ALLSET_OT_dock_tab, ALLSET_OT_panel_show,
           ALLSET_OT_menu_tear_off, ALLSET_OT_dock_strip_click, ALLSET_PT_maya_dock)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_post.append(_on_load)
    _strip_handle.append(bpy.types.SpaceProperties.draw_handler_add(_strip_callback, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if bpy.app.timers.is_registered(_close_stale_menus):
        bpy.app.timers.unregister(_close_stale_menus)
    while _strip_handle:
        bpy.types.SpaceProperties.draw_handler_remove(_strip_handle.pop(), 'WINDOW')
    _drawn.clear()
    _torn_menus.clear()
    _pending.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
