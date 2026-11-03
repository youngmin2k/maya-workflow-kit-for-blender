# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Tool Box: the 3D View toolbar shows Maya's tools in every mode.

Maya's Tool Box is a narrow column left of the
Outliner: Select, Lasso, Paint Select, Move, Rotate, Scale, the last non-sacred tool, then quick layout
buttons and an Outliner toggle. Here:

- ``VIEW3D_PT_tools_active.draw`` is wrapped so that, while it draws, ``tools_from_context`` yields the
  Maya list (``maya_tools``). Only drawing is filtered: ``wm.tool_set_by_id`` looks tools up through
  ``tools_from_context`` too, so replacing ``_tools`` would stop the shelf / menus / keys from
  activating tools that are not in the Tool Box (Multi-Cut, Quad Draw, ...). Modes without the Maya
  tools (sculpt and paint modes) keep Blender's list.
- ``ALLSET_PT_toolbox_layouts`` adds the quick layout buttons under the tools.
- The Maya Workflow Kit template has a Tool Box column: a narrow 3D View showing only its toolbar (``is_toolbox``),
  with every object type hidden in that view (nothing drawn behind the tools; box / lasso select there
  touch nothing). A click under the tools reaches that view's WINDOW region and ``view3d.select`` would
  still deselect everything, so ``allset.toolbox_guard`` sits in front of it in the
  "3D View" keymap. Its overlays are off, so the kit's own drawing (grid, view furniture, selection
  wire) skips it as well.
"""

import math

import bpy
from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active as TOOLBAR

from .. import compat, switch
from ..operators import tool_keys, view

# Maya 2022 Tool Box order: Select, Lasso, Paint Select, Move, Rotate, Scale.
MAYA_TOOLS = ("builtin.select_box", "builtin.select_lasso", "builtin.select_circle",
              "builtin.move", "builtin.rotate", "builtin.scale")

_saved = {}
_drawing = [False]
# True while Maya's Skin Paint Mode (Select / Paint Select) sets a select tool inside weight paint: those
# tools then stay in paint instead of leaving it like the Tool Box's Select / Move / ... (operators/weight_paint.py)
KEEP_PAINT = [False]


def _enabled(context):
    from .. import preferences
    try:
        return preferences.get(context).maya_toolbox
    except KeyError:
        return False


def is_toolbox(space):
    """True for the Maya Workflow Kit template's Tool Box column (= tools/make_startup.py is_toolbox_space). Not keyed on
    its overlays: a column whose overlays got turned on is still the column (``settle`` turns them off again)."""
    return (space is not None and space.type == 'VIEW_3D' and space.show_region_toolbar
            and not space.show_region_header and not space.show_region_ui and not space.show_object_viewport_mesh)


def settle(space, prefs=None):
    """Keep the column a solid tool strip: overlays off (else the grid axis lines show through it) and a flat
    background in the toolbar's theme colour, so any width left beside the tools (the column is wider than one
    toolbar column until ALLSET_OT_fit_columns has fitted it) reads as part of the Tool Box, not as a viewport.
    Returns True when something changed."""
    prefs = prefs or bpy.context.preferences
    # the viewport background colour is scene linear, theme colours are display (sRGB) values (an sRGB
    # 0.188 written as is shows as 119/255)
    rgb = tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                for c in tuple(compat.toolbar_back(prefs.themes[0]))[:3])
    shading = space.shading
    changed = False
    if space.overlay.show_overlays:
        space.overlay.show_overlays = False
        changed = True
    if shading.background_type != 'VIEWPORT':
        shading.background_type = 'VIEWPORT'
        changed = True
    if any(abs(a - b) > 1e-4 for a, b in zip(shading.background_color, rgb)):
        shading.background_color = rgb
        changed = True
    return changed


def _flat(items):
    for item in items:
        if type(item) is tuple:
            yield from (i for i in item if i is not None)
        elif item is not None:
            yield item


def maya_tools(blender_items, mode):
    """The Tool Box for one mode from Blender's tool items (ToolDefs, groups, None), or None when the
    mode lacks the Maya tools. The last slot is the last non-sacred tool used in that mode (Maya's
    last non-sacred tool; tool_keys.LAST, the Y key's memory). Tools other add-ons registered for the mode
    follow, so they stay reachable."""
    by_id = {t.idname: t for t in _flat(blender_items)}
    picked = [by_id[i] for i in MAYA_TOOLS if i in by_id]
    if not any(t.idname == "builtin.move" for t in picked):
        return None
    out = picked + [None]
    last = tool_keys.LAST.get(mode)
    if last in by_id and last not in MAYA_TOOLS:
        out.append(by_id[last])
    others = [t for t in by_id.values() if is_other_addon_tool(t.idname) and t.idname != last]
    if others:     # tools other add-ons registered stay in the toolbar, after the Maya tools
        out += ([] if out[-1] is None else [None]) + others
    return out


def is_other_addon_tool(idname):
    """A tool another add-on registered (not one of Blender's, not one of the kit's)."""
    return not (idname.startswith("builtin") or idname.startswith("allset."))


def kit_icons_on(items, context):
    """The Tool Box column's Maya tools with the kit-drawn Maya icons (#23): each ToolDef copy names a
    kit-only icon that ``kit_icons.tool_icon_name`` put into Blender's toolbar icon cache. Only the drawn copy
    changes (tool switching looks tools up by idname); the last-tool slot and tools without a kit glyph keep
    Blender's icon."""
    from . import kit_icons
    out = []
    for item in items:
        name = kit_icons.tool_icon_name(item.idname, context) if item is not None and item.idname in MAYA_TOOLS             else None
        out.append(item._replace(icon=name) if name else item)
    return out


def _tools_from_context(cls, context, mode=None):
    original = _saved["tools_from_context"].__func__
    if _drawing[0] and mode is None:
        items = list(original(cls, context))
        if context.mode == 'PAINT_WEIGHT':
            # Maya's global selection/transform tools leave Artisan painting.
            # Blender hides some of these tools in paint mode; draw their
            # Object-mode definitions and release paint before activation.
            paint_items = list(_flat(items))
            object_items = list(original(cls, context, mode='OBJECT'))
            maya = maya_tools(object_items, 'OBJECT')
            if maya is not None:
                current = context.workspace.tools.from_space_view3d_mode('PAINT_WEIGHT', create=False)
                brush = next((t for t in paint_items if current is not None and t.idname == current.idname), None)
                if brush is not None and brush.idname not in MAYA_TOOLS:
                    maya.append(brush)
        else:
            maya = maya_tools(items, context.mode)
        if maya is not None:
            if is_toolbox(context.space_data):
                maya = kit_icons_on(maya, context)
            yield from maya
            return
    yield from original(cls, context, mode)


# --- double-click a tool = its Tool Settings (#3; Maya 2022 Tool Box) -------------------------------------
# A toolbar icon is a UI button: a double click never reaches a keymap, but each click runs wm.tool_set_by_id, whose
# execute imports bl_ui.space_toolsystem_common.activate_by_id when it runs ($S\startup\bl_operators\wm.py:2338-2347;
# a DOUBLE_CLICK the button doesn't take comes back as a PRESS). That module function is wrapped: the same tool set
# twice from a 3D View toolbar button within the double-click time opens the Tool Settings. A toolbar button runs its
# operator in the view's WINDOW region like a key does, so the toolbar's layout carries a context member
# (``_draw_begin``: ``context_pointer_set``) that only its buttons' operators see.

TOOLBAR_MEMBER = "allset_toolbar"
_last_click = [None, 0.0]     # (tool idname, time.monotonic()) of the last toolbar click


def note_tool_click(context, idname, now=None):
    """Remember a tool set from a toolbar button; True when it completes a double click (then forgotten)."""
    import time
    if getattr(context, TOOLBAR_MEMBER, None) is None:     # a key / menu / script: never a double click
        _last_click[:] = [None, 0.0]
        return False
    now = time.monotonic() if now is None else now
    limit = context.preferences.inputs.mouse_double_click_time / 1000.0
    hit = _last_click[0] == idname and 0.0 <= now - _last_click[1] <= limit
    _last_click[:] = [None, 0.0] if hit else [idname, now]
    return hit


def _show_tool_settings_later(window):
    ptr = window.as_pointer() if window is not None else 0

    def later():
        from . import tool_dock
        wm = bpy.context.window_manager
        win = next((w for w in wm.windows if w.as_pointer() == ptr), None) or (wm.windows[0] if wm.windows else None)
        if win is None:
            return None
        try:
            with bpy.context.temp_override(window=win):
                tool_dock.show(bpy.context)
        except (RuntimeError, ReferenceError, TypeError):
            pass
        return None
    bpy.app.timers.register(later, first_interval=0.0)


def _make_activate_by_id(original):
    def activate_by_id(context, space_type, idname, *, as_fallback=False):
        if (space_type == 'VIEW_3D' and context.mode == 'PAINT_WEIGHT'
                and idname in MAYA_TOOLS and not as_fallback and not KEEP_PAINT[0]):
            from ..operators.skin import leave_weight_paint
            leave_weight_paint(context)
        done = original(context, space_type, idname, as_fallback=as_fallback)
        if done and space_type == 'VIEW_3D' and note_tool_click(context, idname):
            _show_tool_settings_later(getattr(context, "window", None))
        return done
    activate_by_id._allset_wrapped = True
    return activate_by_id


def _draw_begin(self, context):
    """Prepended to the toolbar's draw: Blender's own draw (ToolSelectPanelHelper.draw) lists the Maya tools while
    the flag is on. A prepend / append pair, not a replaced draw. Also marks the toolbar's buttons for the
    double-click watch."""
    _drawing[0] = _enabled(context)
    if context.space_data is not None and context.space_data.type == 'VIEW_3D':
        self.layout.context_pointer_set(TOOLBAR_MEMBER, context.space_data)


def _draw_end(self, context):
    _drawing[0] = False


class ALLSET_OT_toolbox_guard(bpy.types.Operator):
    """Ignore clicks under the Tool Box column's tools (they would deselect everything)"""
    bl_idname = "allset.toolbox_guard"
    bl_label = "Tool Box Click"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return {'FINISHED'} if is_toolbox(context.space_data) else {'PASS_THROUGH'}


# --- column width -----------------------------------------------------------------------------

# Blender's toolbar is one 56 px column at scale 1 (UI_TOOLBAR_MARGIN + UI_TOOLBAR_COLUMN = 0.5 * 32 +
# 1.25 * 32, interface UI_interface.hh). Area sizes don't
# follow the UI scale: the template's column fits the toolbar at the Maya density (effective scale 1.0,
# "Maya Density" preset). At a larger scale it is resized to one toolbar column with screen.area_move,
# whose poll fails while the mouse is over any region (screen.active_region): the column stayed
# empty at Windows 125 % without the density preset. So ALLSET_OT_fit_columns
# puts the cursor on the area edge for a moment (the poll passes there), moves the edge and
# puts the cursor back; until then the main view of that screen shows its own toolbar.
TOOLBAR_PX = 56
RETINA_EXTRA_PX = 4  # px more per pixel-size step above 1 (column_width)
SHELF_PX = 64        # = tools/make_startup.py SHELF_PX
OUTLINER_PX = 260    # Maya's narrow panel width = the template Outliner at scale 1
TIME_SLIDER_PX = 36  # = tools/make_startup.py TIME_SLIDER_PX (the Time Slider ruler at scale 1)


def time_slider_area(screen):
    """The Maya Workflow Kit layout's Time Slider: a Timeline with the Time Slider buttons in its sidebar."""
    from .time_slider import has_slider_panel
    return next((a for a in screen.areas if a.type == 'DOPESHEET_EDITOR' and a.ui_type == 'TIMELINE'
                 and has_slider_panel(a.spaces.active, a)), None)
_FIT_TICK = 0.5
_fallback = set()   # screens whose main view shows its toolbar because the column is too narrow


def column_width(context=None):
    """One toolbar column at the current scale. A Retina display (pixel size 2) needs 4 px more than 56 x the scale,
    or Blender hides the toolbar (#248: 112 px empty, 116 px shown at scale 2)."""
    system = (context or bpy.context).preferences.system
    return round(TOOLBAR_PX * system.ui_scale) + RETINA_EXTRA_PX * max(0, int(system.pixel_size) - 1)


# The right tab stack (ui/maya_dock.py STACK area, #60, #78): 280 px with the Channel Box raised (a 260 px
# panel + the vertical tab strip; = tools/make_startup.py's old DOCK_PX 260 + 17), 480 px with the Attribute Editor
# raised (the AE is a wide panel). The kit's tabs are a Maya-style
# vertical strip too (maya_dock.draw_strip), so the stack is as wide as the raised panel needs: the Channel Box / Modeling
# Toolkit stack at least 277 px x the scale (wider when the Channel Box labels need it), the Attribute Editor
# stack 480 px x the scale (Maya resizes the stack when its tab changes, ``tab_changed``).
DOCK_MAYA_PX = 277
DOCK_MAX_PX = 480
WIDE_KINDS = ('ATTRIBUTE_EDITOR',)   # wide panels (460 px by default)
# px between neighbouring areas: 3 at UI scale 1.0, 5 at 1.5 (the area edge grows with the scale)
GAP_PX = 8
# the main viewport keeps at least this (x UI scale) after the Tool Box column and Outliner are fitted too: a 1600 px
# window at UI scale 1.5 keeps a 439 px viewport
MIN_VIEW_PX = 280
# the longest channel labels the Channel Box shows by default (polyCube / polyCylinder / polySphere INPUTS)
LONG_LABELS = ("Subdivisions Height", "Subdivisions Width", "Subdivisions Depth", "Subdivisions Axis",
               "Subdivisions Caps")
FONT_PT = 11         # Blender's widget font (Preferences > Interface > Text Rendering: ui_styles[0].widget.points)


def _unit(scale, pixel_size=1.0):
    """Blender's widget unit UI_UNIT_X in px (= toolbar_fit.unit)."""
    from .toolbar_fit import unit
    return unit(scale, pixel_size)


def text_px(text, scale):
    """Width of ``text`` in the UI font at ``scale`` (blf; about 7 px a character when blf can't measure)."""
    try:
        import blf
        blf.size(0, FONT_PT * scale)
        w = blf.dimensions(0, text)[0]
        if w > 0:
            return w
    except Exception:
        pass
    return len(text) * 7 * scale


def dock_need(scale, pixel_size=1.0, measure=text_px):
    """{"labels", "ae_menu"}: px the tab stack needs at ``scale`` so the Channel Box labels aren't truncated and the
    AE menu bar is one row, both left of the vertical tab strip (``maya_dock.reserved_px``)."""
    from . import attribute_editor, maya_dock
    u = _unit(scale, pixel_size)
    strip = maya_dock.reserved_px(scale)
    label = max(measure(t, scale) for t in LONG_LABELS)
    # the label column is half the content column (the panel margin 0.8 U each side of it)
    labels = 2 * (label + 0.8 * u) + 0.8 * u + strip
    # = attribute_editor.fits: the width at which the AE menu bar is drawn on one row
    ae = (sum(len(text) * 7 + 14 for text, _m in attribute_editor.MENU_BAR) + 20) * scale + strip
    return {"labels": math.ceil(labels), "ae_menu": math.ceil(ae)}


def dock_width(scale, pixel_size=1.0, measure=text_px, kind='CHANNEL_BOX'):
    """The tab stack width at ``scale`` with ``kind`` raised: Maya's Attribute Editor stack for the AE (at least its
    one-row menu bar), else what the Channel Box needs, at least Maya's Channel Box stack (never above the AE's)."""
    need = dock_need(scale, pixel_size, measure)
    top = round(DOCK_MAX_PX * scale)
    if kind in WIDE_KINDS:
        return max(top, need["ae_menu"])
    return min(top, max(round(DOCK_MAYA_PX * scale), need["labels"]))


MAX_WARPS = 3        # cursor-warp fits per screen and file load
_warps = {}          # screen name -> fits started since the last load
_running = [False]
# #53: the fit only resizes a layout as it was loaded (or as it was when the UI scale changed). A move whose poll
# failed used to wait and run the first time the poll passed: right after the next area split (a split clears
# screen.active_region), so opening the Tool Settings dock at UI scale 1.25 moved the Outliner edge 45 px into it
# and closing the dock left the viewport 45 px narrower; later it also
# undid the user's own Outliner / shelf row sizes whenever the mouse crossed an area gap.
_state = {}          # screen name -> [ui scale, area pointers, armed, monotonic time armed]
# #155: a fit that could not run at once (no cursor warp, the mouse over a region) waited
# and ran at the next area split mid-session — after Four View or a dialog the shelf row, Outliner, Channel Box and
# Time Slider jumped under the pointer. The fit is a load-time adjustment: it only runs within FIT_WINDOW seconds
# of the screen being loaded / first seen / the UI scale changing.
FIT_WINDOW = 3.0


def _armed(screen, scale):
    """True while ``screen`` may still be fitted: same areas as when it was first seen / loaded / the UI scale
    changed, not fitted yet and within FIT_WINDOW seconds of that. Once its areas change (split, close, dock,
    tear-off) it stays off for this scale."""
    import time
    # the viewport panels don't count — the four view (ui/four_view.py) splits / joins them without
    # touching the columns
    areas = frozenset(a.as_pointer() for a in screen.areas
                      if not (a.type == 'VIEW_3D' and not is_toolbox(a.spaces.active)))
    state = _state.get(screen.name)
    now = time.monotonic()
    if state is None or state[0] != scale:
        _state[screen.name] = [scale, areas, True, now]
        return True
    if state[2] and (state[1] != areas or now - state[3] > FIT_WINDOW):
        state[2] = False
    return state[2]


def _disarm(screen):
    state = _state.get(screen.name)
    if state is not None:
        state[2] = False


def _move_edge(window, area, x, y, delta, edge, pending):
    """Move the edge through (x, y) by ``delta``; when the poll fails, remember ``edge`` (a window point in the
    gap between the areas) for ALLSET_OT_fit_columns."""
    with bpy.context.temp_override(window=window, screen=window.screen, area=area):
        if not bpy.ops.screen.area_move.poll():
            pending.setdefault(window.as_pointer(), (window, edge))
            return False
        return bpy.ops.screen.area_move(x=x, y=y, delta=delta) == {'FINISHED'}


def _dock_target(window, scale, pixel_size, kind):
    """(stack area, fitted width with ``kind`` raised) for the layout's stack right of the main viewport, or None
    (torn off, a user layout)."""
    from . import maya_dock
    from .status_line import main_view3d
    screen = window.screen
    dock = maya_dock.find_stack(screen)
    main, _r = main_view3d(screen)
    if dock is None or main is None or abs(main.x + main.width - dock.x) > GAP_PX or dock.x <= 2:
        return None
    want = dock_width(scale, pixel_size, kind=kind)
    # never squeeze the viewport below MIN_VIEW_PX once the column and Outliner left of it are fitted as well (a small
    # window keeps a narrower dock)
    left = 0
    column = next((a for a in screen.areas if a.type == 'VIEW_3D' and is_toolbox(a.spaces.active)), None)
    if column is not None:
        left += column_width() - column.width
        outl = next((a for a in screen.areas if a.type == 'OUTLINER' and abs(a.x - (column.x + column.width)) <= GAP_PX
                     and abs(a.x + a.width - main.x) <= GAP_PX), None)
        if outl is not None:
            left += round(OUTLINER_PX * scale) - outl.width
    return dock, min(want, dock.width + max(0, main.width - left - round(MIN_VIEW_PX * scale)))


def _fit_dock(window, scale, pixel_size, pending, kind=None):
    """Move the left edge of the Maya tab stack right of the main viewport to ``dock_width`` for the raised tab
    (#60, #78). True while it is off its fitted place (moved now or pending)."""
    from . import maya_dock
    target = _dock_target(window, scale, pixel_size, kind or maya_dock.current_tab())
    if target is None:
        return False
    dock, want = target
    if abs(dock.width - want) <= 2:
        return False
    y = dock.y + dock.height // 2
    _move_edge(window, dock, dock.x, y, dock.width - want, (dock.x - 1, y), pending)
    return True


# Maya resizes its tab stack when another tab is raised (280 px Channel Box, 480 px Attribute Editor; #78). The kit
# does the same once per tab change, only while the stack still has the kit's width for the tab it showed (a stack the
# user resized keeps its size) and only right away: the edge moves now when area_move polls, else through the cursor
# fit (ALLSET_OT_fit_columns) while ``_tab_target`` names the tab, never later (#53).
_tab_target = {}     # screen name -> kind the stack is being fitted to


def tab_changed(window, old, new):
    """The stack area of ``window`` drew ``new`` after ``old`` (maya_dock.tab_drawn, called while drawing: the
    resize runs from a timer)."""
    if (old in WIDE_KINDS) == (new in WIDE_KINDS):
        return
    from .. import live_refs
    ptr = live_refs.pointer(window)

    def later():
        try:
            _tab_fit(live_refs.window(ptr), old, new)
        except Exception:
            import traceback
            traceback.print_exc()
        return None
    bpy.app.timers.register(later, first_interval=0.0)


def _tab_fit(window, old, new):
    """Resize the stack of ``window`` from the width for ``old`` to the width for ``new`` (see ``tab_changed``)."""
    if window is None or _running[0]:
        return
    context = bpy.context
    system = context.preferences.system
    scale, pixel = system.ui_scale, system.pixel_size
    before = _dock_target(window, scale, pixel, old)
    if before is None or abs(before[0].width - before[1]) > 3:
        return            # not the layout's stack, or the user sized it
    pending = {}
    if not _fit_dock(window, scale, pixel, pending, new) or not pending or not auto_warp():
        return
    _tab_target[window.screen.name] = new
    _w, edge = pending[window.as_pointer()]
    with context.temp_override(window=window, screen=window.screen):
        bpy.ops.allset.fit_columns('INVOKE_DEFAULT', x=edge[0], y=edge[1])


def fit_columns(start_fit=True):
    """Tool Box column = one toolbar column at the current UI scale (or the main view's toolbar); the
    shelf row = 64 px times the UI scale. Returns {window pointer: (window, edge point)} of the moves whose
    poll failed; with ``start_fit`` a ALLSET_OT_fit_columns is started for the first of them."""
    from .status_line import main_view3d
    context = bpy.context
    want = column_width(context)
    pending = {}
    from .shelf import shelf_row_area
    scale = context.preferences.system.ui_scale
    for window in context.window_manager.windows:
        screen = window.screen
        armed = _armed(screen, scale)
        if window.workspace is not None and switch.USER_KEY in window.workspace:
            armed = False        # a workspace the user saved keeps the sizes it was saved with
        needed = False       # an edge of this screen is off its fitted place
        # the Maya shelf row (tab row + icon row, 64 px at scale 1): grow it downwards
        row = shelf_row_area(screen)
        if row is not None and row.spaces.active.show_region_header:
            # the shelf row draws its tab strip in the WINDOW region (layouts saved before carry a header)
            with context.temp_override(window=window, screen=screen, area=row):
                row.spaces.active.show_region_header = False
        if row is not None:
            d = round(SHELF_PX * scale) - row.height
            if abs(d) > 2 and armed:
                needed = True
                _move_edge(window, row, row.x + row.width // 2, row.y, -d,
                           (row.x + row.width // 2, row.y - 1), pending)
        # the Time Slider (#109): its ruler keeps 36 px times the UI scale. The template area has a
        # fixed height, so at UI 1.25 the taller header left a 29 px ruler that Blender's current-frame box filled
        # (look_compare time_slider_current): grow it upwards
        slider = time_slider_area(screen)
        if slider is not None:
            hdr = next((r.height for r in slider.regions if r.type == 'HEADER'), 0)
            d = round(TIME_SLIDER_PX * scale) + hdr - slider.height
            if abs(d) > 2 and armed:
                needed = True
                top = slider.y + slider.height
                _move_edge(window, slider, slider.x + slider.width // 2, top, d,
                           (slider.x + slider.width // 2, top + 1), pending)
        tab = _tab_target.get(screen.name)
        if tab is not None:      # a tab-change resize under way (only while its cursor fit runs)
            if not _fit_dock(window, scale, context.preferences.system.pixel_size, pending, tab):
                _tab_target.pop(screen.name, None)
        elif armed and _fit_dock(window, scale, context.preferences.system.pixel_size, pending):
            needed = True
        column = next((a for a in screen.areas if a.type == 'VIEW_3D' and is_toolbox(a.spaces.active)), None)
        if column is None:
            if armed and not needed:
                _disarm(screen)
            continue
        if settle(column.spaces.active, context.preferences):
            column.tag_redraw()
        if not armed:
            pass
        elif abs(column.width - want) > 1 and column.x + column.width < window.width - 2:
            needed = True
            _move_edge(window, column, column.x + column.width, column.y + column.height // 2,
                       want - column.width, (column.x + column.width + 1, column.y + column.height // 2), pending)
        elif abs(column.width - want) <= 1:
            # the layout Outliner right of the column keeps Maya's panel width at this scale (widening the column
            # took its pixels)
            outl = next((a for a in screen.areas if a.type == 'OUTLINER' and abs(a.x - (column.x + column.width)) <= GAP_PX
                         and a.height >= column.height - 4), None)
            wo = round(OUTLINER_PX * scale)
            if outl is not None and abs(outl.width - wo) > 2 and outl.x + outl.width < window.width - 2:
                needed = True
                _move_edge(window, outl, outl.x + outl.width, outl.y + outl.height // 2, wo - outl.width,
                           (outl.x + outl.width + 1, outl.y + outl.height // 2), pending)
        if armed and not needed:
            _disarm(screen)      # fitted: the user's own edge moves stay
        narrow = column.width < want - 1
        main, _r = main_view3d(screen)
        if main is None or main == column:
            continue
        key = screen.name
        # The property update re-inits the area through the context window: a timer runs with the last active
        # window, which may just have been closed (crash in WM_window_get_active_workspace) — so set it
        # with this window in the context. Only the kit's own fallback is undone: a toolbar the user showed (T)
        # stays (PR #125 synced it to the column width every fit).
        if narrow and key not in _fallback and not main.spaces.active.show_region_toolbar:
            with context.temp_override(window=window, screen=screen, area=main):
                main.spaces.active.show_region_toolbar = True
            _fallback.add(key)
        elif not narrow and key in _fallback:
            with context.temp_override(window=window, screen=screen, area=main):
                main.spaces.active.show_region_toolbar = False
            _fallback.discard(key)
    if start_fit and pending and not _running[0] and auto_warp():
        window, edge = next(iter(pending.values()))
        key = window.screen.name
        if _warps.get(key, 0) < MAX_WARPS:
            _warps[key] = _warps.get(key, 0) + 1
            with context.temp_override(window=window, screen=window.screen):
                bpy.ops.allset.fit_columns('INVOKE_DEFAULT', x=edge[0], y=edge[1])
    return pending


def auto_warp():
    """The cursor fit runs by itself except in event-simulated sessions (GUI tests, dogfood): they own the mouse,
    and a warp in the middle of a scripted step closes its menus. ALLSET_FIT_WARP=1 turns it on there."""
    import os
    return not bpy.app.use_event_simulate or os.environ.get("ALLSET_FIT_WARP") == "1"


def _warp(window, x, y):
    window.cursor_warp(x, y)
    if bpy.app.use_event_simulate:   # event simulation drops the OS mouse move a warp makes
        window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)


class ALLSET_OT_fit_columns(bpy.types.Operator):
    """Resize the Tool Box column / shelf row: the cursor sits on the area edge (where screen.area_move polls)
    for a few timer ticks, then goes back"""
    bl_idname = "allset.fit_columns"
    bl_label = "Fit Maya Layout Columns"
    bl_options = {'INTERNAL'}

    x: bpy.props.IntProperty(options={'SKIP_SAVE'})
    y: bpy.props.IntProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        self._back = (event.mouse_x, event.mouse_y)
        self._n = 0
        self._window = context.window
        self._at = (self.x, self.y)
        _warp(context.window, self.x, self.y)
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        _running[0] = True
        return {'RUNNING_MODAL'}

    def _finish(self, context, event):
        context.window_manager.event_timer_remove(self._timer)
        _running[0] = False
        _tab_target.clear()        # a tab-change fit is done or given up: never applied later (#53)
        if (event.mouse_x, event.mouse_y) == self._at:   # the user didn't move the mouse meanwhile
            _warp(self._window, *self._back)
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        self._n += 1
        try:
            left = fit_columns(start_fit=False)
        except Exception:
            left = {}
        item = left.get(self._window.as_pointer())
        if item is None or self._n > 24:
            return self._finish(context, event)
        if item[1] != self._at:   # the next edge (column, then Outliner, then shelf row)
            if (event.mouse_x, event.mouse_y) != self._at:   # the user moved the mouse: stop here
                return self._finish(context, event)
            self._at = item[1]
            _warp(self._window, *item[1])
        return {'PASS_THROUGH'}


def _fit_tick():
    try:
        fit_columns()
    except Exception:   # a timer that raises is dropped: keep it running
        pass
    return _FIT_TICK


@bpy.app.handlers.persistent
def _fit_after_load(*_args):
    _warps.clear()
    _state.clear()       # a loaded layout may be fitted again: its areas as loaded, before any split (#53)
    try:
        scale = bpy.context.preferences.system.ui_scale
        for window in bpy.context.window_manager.windows:
            _armed(window.screen, scale)
    except (AttributeError, ReferenceError):
        pass
    if not bpy.app.background:
        bpy.app.timers.register(lambda: _fit_tick() and None, first_interval=0.0)


# --- quick layouts (Maya 2022 Tool Box) ---------------------------------------------------

class ALLSET_OT_quick_layout(bpy.types.Operator):
    """Maya Tool Box quick layout button"""
    bl_idname = "allset.quick_layout"
    bl_label = "Quick Layout"
    bl_options = {'INTERNAL'}

    layout: bpy.props.EnumProperty(items=(
        ('SINGLE', "Single Perspective View", "One perspective view (Maya quick layout 1)"),
        ('FOUR', "Four View", "Top, perspective, front and side views (Maya quick layout 2)"),
        ('FRONT_PERSP', "Front/Persp", "Front and perspective views side by side (Maya quick layout 3): "
                                       "not available, a Blender 3D View splits only into four"),
    ))

    @classmethod
    def description(cls, context, props):
        return {
            "SINGLE": "Single Perspective View", "FOUR": "Four View. " + view.FOUR_VIEW_NOTE,
            "FRONT_PERSP": "Front/Persp: not available (a Blender 3D View splits only into four)"}[props.layout]

    def execute(self, context):
        if self.layout == 'FRONT_PERSP':
            return {'CANCELLED'}
        from .panel_menus import main_region
        from .status_line import main_view3d
        area, _r = main_view3d(context.screen)
        if area is None:
            # no 3D View panel (the one panel left is a Graph Editor ...): the layout itself
            from . import four_view
            done = four_view.set_layout(context, context.window, self.layout == 'FOUR')
            return {'FINISHED'} if done else {'CANCELLED'}
        key = "LAYOUT_SINGLE" if self.layout == 'SINGLE' else "LAYOUT_FOUR"
        with context.temp_override(area=area, region=main_region(area)):
            return bpy.ops.allset.panel_set(key=key)


def outliner_areas(screen):
    return [a for a in (screen.areas if screen else ()) if a.type == 'OUTLINER']


def floating_outliners(context):
    """Other windows that hold only Outliners (Maya's floating Outliner)."""
    return [w for w in context.window_manager.windows
            if w != context.window and w.screen.areas and all(a.type == 'OUTLINER' for a in w.screen.areas)]


def outliner_shown(context):
    """True while the Tool Box Outliner button is on: an Outliner in this window or floating."""
    return bool(outliner_areas(context.screen)) or bool(floating_outliners(context))


def _beside_column(screen):
    """The largest area right of this screen's Tool Box column (where the layout's Outliner docks), or None."""
    column = next((a for a in screen.areas if a.type == 'VIEW_3D' and is_toolbox(a.spaces.active)), None)
    if column is None:
        return None
    edge = column.x + column.width
    near = [a for a in screen.areas if a != column and abs(a.x - edge) <= GAP_PX
            and a.y < column.y + column.height and column.y < a.y + a.height]
    return max(near, key=lambda a: a.width * a.height, default=None)


def dock_outliner(context, window):
    """Split the area right of the Tool Box column and put a Maya Outliner on its left. The new area or None."""
    screen = window.screen
    area = _beside_column(screen)
    if area is None:
        return None
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    scale = context.preferences.system.ui_scale or 1.0      # 0 in background
    factor = min(0.45, OUTLINER_PX * scale / max(area.width, 1))
    before = {a.as_pointer() for a in screen.areas}
    with context.temp_override(window=window, screen=screen, area=area, region=region):
        if bpy.ops.screen.area_split(direction='VERTICAL', factor=factor) != {'FINISHED'}:
            return None
    new = next((a for a in screen.areas if a.as_pointer() not in before), None)
    if new is None:
        return None
    new.ui_type = 'OUTLINER'
    from . import maya_outliner
    maya_outliner.setup(new.spaces.active)
    return new


def _close_windows_later(pointers):
    from .. import live_refs

    def tick():
        for ptr in pointers:
            win = live_refs.window(ptr)
            if win is not None:
                with bpy.context.temp_override(window=win):
                    bpy.ops.wm.window_close()
        return None
    bpy.app.timers.register(tick, first_interval=0.0)


class ALLSET_OT_toggle_outliner(bpy.types.Operator):
    """Show or hide the Outliner"""
    bl_idname = "allset.toggle_outliner"
    bl_label = "Outliner"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        window = context.window
        if window is None:
            return {'CANCELLED'}
        screen = window.screen
        docked = outliner_areas(screen)
        if docked:
            if bpy.app.background:      # screen.area_close hangs without a UI
                return {'CANCELLED'}
            area = docked[0]
            with context.temp_override(window=window, screen=screen, area=area):
                bpy.ops.screen.area_close()
            return {'FINISHED'}
        floating = floating_outliners(context)
        if floating:
            _close_windows_later([w.as_pointer() for w in floating])
            return {'FINISHED'}
        if dock_outliner(context, window) is not None:
            return {'FINISHED'}
        # no Tool Box column here: the Outliner opens in its own window
        return bpy.ops.allset.open_editor(ui_type='OUTLINER')


class ALLSET_OT_viewport_search(bpy.types.Operator):
    """Open Blender command search using the actual modeling viewport, not the tool strip."""
    bl_idname = "allset.viewport_search"
    bl_label = "Search Commands"
    bl_description = "Search Blender commands in the main modeling viewport (F3)"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        from .status_line import main_view3d
        area, region = main_view3d(context.screen)
        if area is None or region is None:
            self.report({'WARNING'}, "No modeling viewport found")
            return {'CANCELLED'}
        # Search uses its invocation context for poll and dispatch. The narrow
        # dedicated toolbox is itself a VIEW_3D but has no useful model region.
        with context.temp_override(window=context.window, area=area, region=region):
            return bpy.ops.wm.search_menu('INVOKE_DEFAULT')

    def execute(self, context):
        return self.invoke(context, None)


class ALLSET_OT_armature_mode(bpy.types.Operator):
    """Switch the selected skeleton between Object, Edit, and Pose modes"""
    bl_idname = 'allset.armature_mode'
    bl_label = 'Armature Mode'
    bl_options = {'INTERNAL'}

    mode: bpy.props.EnumProperty(items=[
        ('OBJECT', 'Object Mode', 'Select the entire skeleton'),
        ('EDIT', 'Edit Mode', 'Edit bones and joint positions'),
        ('POSE', 'Pose Mode', 'Select and pose joints'),
    ])

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return obj is not None and obj.type == 'ARMATURE'

    def execute(self, context):
        from .status_line import main_view3d
        obj = context.view_layer.objects.active
        if obj is None or obj.type != 'ARMATURE':
            return {'CANCELLED'}
        if obj.mode == self.mode:
            return {'FINISHED'}
        from ..operators import maya_errors
        if self.mode != 'OBJECT' and maya_errors.refuse_hidden(self, obj):     # #187
            return {'CANCELLED'}
        area, region = main_view3d(context.screen)
        try:
            if area is not None and region is not None:
                with context.temp_override(window=context.window, area=area, region=region):
                    bpy.ops.object.mode_set(mode=self.mode)
            else:
                bpy.ops.object.mode_set(mode=self.mode)
        except (RuntimeError, ValueError) as ex:
            self.report({'WARNING'}, f'Unable to switch armature mode: {ex}')
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_MT_armature_modes(bpy.types.Menu):
    """Switch joint/object modes from the main viewport header."""
    bl_idname = 'ALLSET_MT_armature_modes'
    bl_label = 'Armature Mode'

    def draw(self, context):
        obj = context.view_layer.objects.active
        for mode, label, icon in (
            ('OBJECT', 'Object Mode', 'OBJECT_DATAMODE'),
            ('EDIT', 'Edit Mode', 'EDITMODE_HLT'),
            ('POSE', 'Pose Mode', 'POSE_HLT'),
        ):
            row = self.layout.row()
            row.enabled = obj is not None and obj.mode != mode
            row.operator('allset.armature_mode', text=label, icon=icon).mode = mode


def _draw_armature_mode_header(self, context):
    """Prominent, outlined armature mode picker with an explicit chevron. Maya has no mode picker in any version:
    only drawn with the add-on preference ``armature_mode_header`` on."""
    from . import armature_mode_pulse
    from .. import preferences
    armature_mode_pulse.forget(context)
    if not _enabled(context) or not getattr(preferences.get(context), "armature_mode_header", False):
        return
    obj = context.view_layer.objects.active
    if obj is None or obj.type != 'ARMATURE':
        return
    from .status_line import main_view3d
    area, _ = main_view3d(context.screen)
    if context.area != area or is_toolbox(context.space_data):
        return
    mode_label = {'OBJECT': 'OBJECT', 'EDIT': 'EDIT JOINTS', 'POSE': 'POSE JOINTS'}.get(obj.mode, 'JOINT MODE')
    mode_icon = {'OBJECT': 'OBJECT_DATAMODE', 'EDIT': 'EDITMODE_HLT', 'POSE': 'POSE_HLT'}.get(obj.mode, 'ARMATURE_DATA')
    # Header menus normally hide their dropdown affordance; place a chevron
    # explicitly alongside the text, inside a single framed toolbar group.
    frame = self.layout.row(align=True)
    frame.ui_units_x = armature_mode_pulse.CUSTOM_UNITS
    # This control is first in the header, giving its pulse a stable local
    # footprint even in the kit's custom Maya header and narrow viewports.
    armature_mode_pulse.mark(context)
    frame.label(text='', icon='ARMATURE_DATA')
    frame.menu('ALLSET_MT_armature_modes', text=mode_label + '  ▾', icon=mode_icon)


# Track active-object transitions rather than forcing Pose Mode continuously.
# This leaves the user free to switch to Edit/Object manually in the dropdown.
_last_armature_target = {}
_AUTO_MODE_TICK = 0.18


def _auto_armature_tick():
    if bpy.app.background:
        return None
    try:
        for window in bpy.context.window_manager.windows:
            screen = window.screen
            if not screen:
                continue
            from .status_line import main_view3d
            area, region = main_view3d(screen)
            key = window.as_pointer()
            if area is None or region is None:
                _last_armature_target.pop(key, None)
                continue
            with bpy.context.temp_override(window=window, area=area, region=region):
                ctx = bpy.context
                if not _enabled(ctx):
                    _last_armature_target.pop(key, None)
                    continue
                ob = ctx.view_layer.objects.active
                target = ob.as_pointer() if ob and ob.type == 'ARMATURE' and ob.select_get() else None
                if key not in _last_armature_target:
                    _last_armature_target[key] = target
                    continue
                previous = _last_armature_target[key]
                if target == previous:
                    continue
                _last_armature_target[key] = target
                if target is not None and ob.mode == 'OBJECT':
                    from ..operators import joint_selection
                    try:
                        # #156: the Move tool on an unskinned skeleton then switches it to
                        # Edit mode (joint_selection.sync_tool_mode, tool_keys watch)
                        bpy.ops.object.mode_set(mode='POSE')
                    except (RuntimeError, ValueError):
                        pass
                    else:
                        # B4: a skeleton picked from the Outliner / Select All shows its root joint
                        if joint_selection.select_roots_if_empty(ob):
                            for a in window.screen.areas:
                                a.tag_redraw()
                elif target is None and ob and (ob.mode == 'POSE' or (ob.type == 'ARMATURE' and ob.mode == 'EDIT')):
                    try:
                        bpy.ops.object.mode_set(mode='OBJECT')
                    except (RuntimeError, ValueError):
                        pass
    except (RuntimeError, ReferenceError, AttributeError):
        pass
    return _AUTO_MODE_TICK


def _click_hits_joint(context, obj, x, y):
    """Whether a viewport click is on a visible armature bone (screen pixels).

    Unlike checking selection flags, this also handles Blender retaining edit-bone
    selection when the user clicks a blank part of the viewport.
    """
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    from mathutils import Vector

    region = context.region
    space = context.space_data
    if not space or space.type != 'VIEW_3D' or region.type != 'WINDOW':
        return True  # Never change modes if the target region is uncertain.
    rv3d = space.region_3d
    if rv3d is None:
        return True
    def shown(bone):    # hidden bone collections hide their bones too (#171: ORG / MCH bones gave false hits)
        return not (bone.collections and not any(c.is_visible_effectively for c in bone.collections))
    if obj.mode == 'EDIT':
        segments = ((b.head, b.tail) for b in obj.data.edit_bones if not b.hide and shown(b))
    else:
        segments = ((b.head, b.tail) for b in obj.pose.bones if not b.bone.hide and shown(b.bone))

    point = Vector((x, y))
    # Bone handles have nonzero screen size; allow a modest hit margin.
    margin = 15.0 * context.preferences.system.ui_scale
    margin_sq = margin * margin
    matrix = obj.matrix_world
    for head, tail in segments:
        p = location_3d_to_region_2d(region, rv3d, matrix @ head)
        q = location_3d_to_region_2d(region, rv3d, matrix @ tail)
        if p is None or q is None:
            continue
        delta = q - p
        fraction = max(0.0, min(1.0, (point - p).dot(delta) / max(delta.length_squared, 1e-9)))
        if (point - (p + fraction * delta)).length_squared <= margin_sq:
            return True
    return False



def _other_object_under_click(context, armature, x, y):
    """Find another selectable scene mesh under a viewport click.

    Blender's regular object picking cannot change the active object while an
    armature is in Edit Mode. Ray-cast instead, then switch mode before selecting.
    """
    from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
    from mathutils import Vector

    region = context.region
    rv3d = context.space_data.region_3d
    coord = Vector((x, y))
    origin = region_2d_to_origin_3d(region, rv3d, coord)
    direction = region_2d_to_vector_3d(region, rv3d, coord)
    depsgraph = context.evaluated_depsgraph_get()
    hit, _point, _normal, _index, obj, _matrix = context.scene.ray_cast(
        depsgraph, origin, direction, distance=1.0e6)
    if not hit or obj is None:
        return None
    original = getattr(obj, 'original', obj)
    if original == armature or not original.visible_get(view_layer=context.view_layer):
        return None
    if original.name not in context.view_layer.objects or original.hide_select:
        return None
    return original


class ALLSET_OT_pose_empty_click(bpy.types.Operator):
    """Exit joint modes on an actual empty click in the main 3D viewport."""
    bl_idname = 'allset.pose_empty_click'
    bl_label = 'Maya Joint Empty Click Watch'
    bl_options = {'INTERNAL'}
    _area_ptr = None
    _press = None

    def invoke(self, context, event):
        self._area_ptr = context.area.as_pointer()
        self._press = None
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not _enabled(context) or context.area is None or context.area.as_pointer() != self._area_ptr:
            _pose_watch_areas.discard(self._area_ptr)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE':
            return {'PASS_THROUGH'}
        # A click, not a box-select, drag, or transform-gizmo movement.
        if event.value == 'PRESS':
            self._press = (event.mouse_region_x, event.mouse_region_y) if (
                context.region and context.region.type == 'WINDOW'
                and not (event.shift or event.ctrl or event.alt or event.oskey)) else None
            return {'PASS_THROUGH'}
        if event.value != 'RELEASE':
            return {'PASS_THROUGH'}
        press = self._press
        self._press = None
        if press is None or context.region is None or context.region.type != 'WINDOW':
            return {'PASS_THROUGH'}
        x, y = event.mouse_region_x, event.mouse_region_y
        if min(x, y) < 0 or x >= context.region.width or y >= context.region.height:
            return {'PASS_THROUGH'}
        if (x - press[0]) ** 2 + (y - press[1]) ** 2 > 36:
            return {'PASS_THROUGH'}

        # pointers, looked up when the timer runs: the window may close in between (#36)
        win_ptr, area_ptr = context.window.as_pointer(), context.area.as_pointer()

        def check():
            from .. import live_refs
            win, area = live_refs.find_area(area_ptr, win_ptr)
            try:
                if area is None:
                    return None
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region is None:
                    return None
                with bpy.context.temp_override(window=win, area=area, region=region):
                    ctx = bpy.context
                    obj = ctx.view_layer.objects.active
                    # Pose mode: select_priority decides every click (a control stays in Pose; #171 —
                    # head-tail lines missed custom-shape controls and dropped Pose ~60 ms after the pick)
                    if obj is not None and obj.type == 'ARMATURE' and obj.mode == 'EDIT':
                        # Give joints priority even if a mesh is visible behind them.
                        if not _click_hits_joint(ctx, obj, x, y):
                            other = _other_object_under_click(ctx, obj, x, y)
                            bpy.ops.object.mode_set(mode='OBJECT')
                            if other is not None:
                                # Edit Mode locks Blender's normal object selection.
                                # Explicitly transfer selection after leaving the mode.
                                for selected in tuple(ctx.selected_objects):
                                    selected.select_set(False)
                                other.select_set(True)
                                ctx.view_layer.objects.active = other
                            area.tag_redraw()
            except (ReferenceError, RuntimeError, AttributeError, TypeError, ValueError):
                pass
            return None
        # Delay until Blender's own selection event has finished.
        bpy.app.timers.register(check, first_interval=0.06)
        return {'PASS_THROUGH'}


_pose_watch_areas = set()


def _ensure_pose_watch():
    if bpy.app.background:
        return None
    try:
        for window in bpy.context.window_manager.windows:
            from .status_line import main_view3d
            area, region = main_view3d(window.screen)
            if area is None or region is None:
                continue
            ptr = area.as_pointer()
            if ptr in _pose_watch_areas:
                continue
            with bpy.context.temp_override(window=window, area=area, region=region):
                if _enabled(bpy.context):
                    bpy.ops.allset.pose_empty_click('INVOKE_DEFAULT')
                    _pose_watch_areas.add(ptr)
    except (RuntimeError, ReferenceError, AttributeError):
        pass
    return 1.0


# Outliner clicks occur in a separate editor, so the viewport's modal click
# watcher cannot detect them. Observe actual Outliner object-row selection.
_outliner_watch_areas = set()


class ALLSET_OT_joint_outliner_select(bpy.types.Operator):
    """Leave armature joint mode when a different object is picked in the Outliner."""
    bl_idname = 'allset.joint_outliner_select'
    bl_label = 'Maya Joint Outliner Selection Watch'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self._area_ptr = context.area.as_pointer()
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        area = context.area
        if (area is None or area.as_pointer() != self._area_ptr
                or area.type != 'OUTLINER' or not _enabled(context)):
            _outliner_watch_areas.discard(self._area_ptr)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'RELEASE':
            return {'PASS_THROUGH'}
        if context.region is None or context.region.type != 'WINDOW':
            return {'PASS_THROUGH'}
        # pointers, looked up when the timer runs: the window may close in between (#36)
        win_ptr, area_ptr = context.window.as_pointer(), area.as_pointer()

        # Blender updates selected_ids on completion of the Outliner click.
        def after_selection():
            from .. import live_refs
            win, area = live_refs.find_area(area_ptr, win_ptr)
            try:
                if area is None or area.type != 'OUTLINER':
                    return None
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region is None:
                    return None
                with bpy.context.temp_override(window=win, area=area, region=region):
                    ctx = bpy.context
                    if not _enabled(ctx):
                        return None
                    selected = [item for item in ctx.selected_ids if isinstance(item, bpy.types.Object)]
                    if len(selected) != 1:
                        return None
                    target = selected[0]
                    active = ctx.view_layer.objects.active
                    if (active is None or active.type != 'ARMATURE'
                            or active.mode not in {'EDIT', 'POSE'} or target == active
                            or target.name not in ctx.view_layer.objects
                            or target.hide_select):
                        return None
                    from .status_line import main_view3d
                    view, view_region = main_view3d(win.screen)
                    if view is None or view_region is None:
                        return None
                    with bpy.context.temp_override(window=win, area=view, region=view_region):
                        bpy.ops.object.mode_set(mode='OBJECT')
                        for ob in tuple(ctx.view_layer.objects.selected):
                            ob.select_set(False)
                        target.select_set(True)
                        ctx.view_layer.objects.active = target
                        _last_armature_target[win.as_pointer()] = None
                        view.tag_redraw()
                    area.tag_redraw()
            except (RuntimeError, ReferenceError, AttributeError, TypeError, ValueError):
                pass
            return None
        bpy.app.timers.register(after_selection, first_interval=0.06)
        return {'PASS_THROUGH'}


def _ensure_outliner_watch():
    if bpy.app.background:
        return None
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type != 'OUTLINER' or area.as_pointer() in _outliner_watch_areas:
                    continue
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region is None:
                    continue
                with bpy.context.temp_override(window=win, area=area, region=region):
                    if _enabled(bpy.context):
                        bpy.ops.allset.joint_outliner_select('INVOKE_DEFAULT')
                        _outliner_watch_areas.add(area.as_pointer())
    except (RuntimeError, ReferenceError, AttributeError):
        pass
    return 1.0


class ALLSET_PT_toolbox_layouts(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_label = "Quick Layouts"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        return _enabled(context)

    def draw(self, context):
        col = self.layout.column(align=True)
        col.scale_y = 1.75   # = the tool buttons (ToolSelectPanelHelper.draw_cls scale_y)
        # kit-drawn Maya layout icons (#23; Blender's icon until the glyph is made)
        from .kit_icons import button
        op = ALLSET_OT_quick_layout.bl_idname
        button(col, op, "layout:SINGLE", 'VIEW_PERSPECTIVE', text="").layout = 'SINGLE'
        button(col, op, "layout:FOUR", 'VIEW_ORTHO', text="").layout = 'FOUR'
        sub = col.row()
        sub.enabled = False   # Front/Persp needs a two-pane split: no Blender equivalent
        button(sub, op, "layout:FRONT_PERSP", 'SPLIT_VERTICAL', text="").layout = 'FRONT_PERSP'
        col.separator()
        # Maya's Outliner check box: shows / hides the Outliner (pressed while one is shown)
        button(col, ALLSET_OT_toggle_outliner.bl_idname, "layout:OUTLINER", 'OUTLINER', text="",
               depress=outliner_shown(context))
        # Maya 2022.1+: the Search icon under the layout / Outliner buttons, after a divider (Maya 2022.1 Tool Box);
        # it opens Blender's command search (Maya Ctrl+F = SearchEngine).
        col.separator()
        col.operator_context = 'INVOKE_DEFAULT'
        col.operator('allset.viewport_search', text='', icon='VIEWZOOM')


classes = (ALLSET_OT_toolbox_guard, ALLSET_OT_fit_columns, ALLSET_OT_quick_layout, ALLSET_OT_toggle_outliner, ALLSET_OT_viewport_search, ALLSET_OT_armature_mode, ALLSET_MT_armature_modes, ALLSET_OT_pose_empty_click, ALLSET_OT_joint_outliner_select, ALLSET_PT_toolbox_layouts)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _saved["tools_from_context"] = TOOLBAR.__dict__["tools_from_context"]
    TOOLBAR.tools_from_context = classmethod(_tools_from_context)
    TOOLBAR.prepend(_draw_begin)
    bpy.types.VIEW3D_HT_header.prepend(_draw_armature_mode_header)
    if not bpy.app.background:
        bpy.app.timers.register(_auto_armature_tick, first_interval=0.5, persistent=True)
        bpy.app.timers.register(_ensure_pose_watch, first_interval=1.0, persistent=True)
        bpy.app.timers.register(_ensure_outliner_watch, first_interval=1.0, persistent=True)
    TOOLBAR.append(_draw_end)
    from bl_ui import space_toolsystem_common as stc
    _saved["activate_by_id"] = stc.activate_by_id
    stc.activate_by_id = _make_activate_by_id(stc.activate_by_id)
    if not bpy.app.background and not bpy.app.timers.is_registered(_fit_tick):
        bpy.app.timers.register(_fit_tick, first_interval=_FIT_TICK, persistent=True)
    bpy.app.handlers.load_post.append(_fit_after_load)


def unregister():
    _running[0] = False
    _tab_target.clear()
    _last_armature_target.clear()
    _pose_watch_areas.clear()
    _outliner_watch_areas.clear()
    for timer in (_auto_armature_tick, _ensure_pose_watch, _ensure_outliner_watch):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    if _fit_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_fit_after_load)
    if bpy.app.timers.is_registered(_fit_tick):
        bpy.app.timers.unregister(_fit_tick)
    TOOLBAR.tools_from_context = _saved.pop("tools_from_context")
    from bl_ui import space_toolsystem_common as stc
    if "activate_by_id" in _saved:
        stc.activate_by_id = _saved.pop("activate_by_id")
    _last_click[:] = [None, 0.0]
    bpy.types.VIEW3D_HT_header.remove(_draw_armature_mode_header)
    TOOLBAR.remove(_draw_begin)
    TOOLBAR.remove(_draw_end)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
