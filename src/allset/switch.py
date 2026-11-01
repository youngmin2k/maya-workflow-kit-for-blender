# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya ⇄ Blender switch.

The extension stays enabled; "Maya mode" is the set of sub-packages ``__init__.MODE``
(keymap, UI, operators, ...). Switching off unregisters them, which puts
back everything they registered (``tests/test_enable_disable.py`` enforces it), switching on
registers them again. Only this module and the preferences stay registered in Blender
mode, so the switch is always there: a small toggle at the right of the top bar, the
add-on preferences, Edit (Blender) / Windows > Settings/Preferences (Maya) menu items that
the menu search finds, and Ctrl+Alt+Shift+M (free in Blender, Industry Compatible and
Maya's standard hotkeys).

Nothing persistent: Maya mode writes none of Blender's preferences and
nothing outside the extension's folders, so switching off / disabling / removing needs no snapshot or restore —
unregistering the Maya mode modules takes back everything they registered.

Layout: switching on in a file that has no Maya layout appends the layout workspace of the startup.blend
bundled inside the extension (``app_template.STARTUP``) (named "Maya-style") and activates it; switching off goes back to the previous
workspace and deletes the appended one. Scenes and objects are never touched.
"""

import os

import bpy

from . import results
from . import live_refs

WORKSPACE = "Maya-style"


TEMPLATE_WORKSPACE = "General"
PREV_KEY = "allset_switch_prev"
SHORTCUT = ('M', {"ctrl": True, "alt": True, "shift": True})


# --- mode on / off ------------------------------------------------------------------------------

def _prefs_addon():
    from . import preferences
    return preferences.get()


def is_on():
    try:
        return bool(_prefs_addon().maya_mode)
    except KeyError:
        return False


def _template_blend():
    from .app_template import STARTUP
    return STARTUP


def _window_override(window):
    return {"window": window, "screen": window.screen}


def is_maya_workspace(ws):
    """A workspace that already is the Maya layout (appended by the switch or a Maya Workflow Kit file)."""
    if ws is None:
        return False
    if PREV_KEY in ws or TEMPLATE_KEY in ws or USER_KEY in ws:     # TEMPLATE_KEY: any Maya workspace of the template
        return True
    for screen in ws.screens:
        for area in screen.areas:
            space = area.spaces.active
            if area.type == 'IMAGE_EDITOR' and getattr(space, "mask", None) is not None \
                    and space.mask.name.startswith(".Allset"):
                return True
    return False


def _fit_views(ws, scene, saved_unit=0.01):
    """The template views are in cm (Maya unit 0.01 BU; a saved workspace: the Maya unit it was saved with): keep
    them on the same Maya-unit scene."""
    from .operators import units
    ratio = units.maya_unit(scene) / (saved_unit or 0.01)
    for screen in ws.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type != 'VIEW_3D':
                    continue
                # The tool header is Maya's panel toolbar in views with a header; the Tool Box column has
                # neither. Set it explicitly: an appended screen came back with it shown. Only a
                # change is written (Modeling - Expert keeps a header without the toolbar row; writing a
                # region flag of a screen no window shows crashes Blender in ED_area_init in -b).
                if space.show_region_tool_header and not space.show_region_header:
                    space.show_region_tool_header = False
                for key, value in units.clip(scene).items():
                    setattr(space, key, value)
                space.overlay.grid_scale = units.grid_scale(scene)
                if abs(ratio - 1.0) > 1e-9:
                    for rv3d in (space.region_3d, *space.region_quadviews):
                        rv3d.view_location = rv3d.view_location * ratio
                        rv3d.view_distance *= ratio


def enter_layout(window):
    """Append and activate the Maya layout workspace in ``window`` (unless it already is one)."""
    if window is None or is_maya_workspace(window.workspace):
        return None
    own = [ws for ws in bpy.data.workspaces if PREV_KEY not in ws and is_maya_workspace(ws)]
    own.sort(key=lambda ws: template_of(ws) != TEMPLATE_WORKSPACE)     # Maya Classic first
    own = own[0] if own else None
    if own is not None:
        # the file's own Maya layout (a Maya Workflow Kit template file left by a switch to Blender): back to it,
        # nothing appended twice (#19); the user's workspace is remembered for the way back (#185)
        if window.workspace is not None:
            own[BLENDER_PREV_KEY] = window.workspace.name
        window.workspace = own
        return own
    prev = window.workspace.name
    ws = append_workspace(window, TEMPLATE_WORKSPACE)
    if ws is None:
        return None
    ws[PREV_KEY] = prev
    ws.name = WORKSPACE
    return ws


TEMPLATE_KEY = "allset_template"      # the template workspace a Maya workspace was made from
USER_KEY = "allset_user_workspace"    # a workspace the user saved (Save Current Workspace As): its name
USER_UNIT_KEY = "allset_user_unit"    # the Maya unit of the scene it was saved in


def append_workspace(window, template_name, filepath=None, idname=None):
    """Append the template workspace ``template_name`` (General, Animation, ... tools/make_startup.MAYA_WORKSPACES) into
    the open file and show it in ``window``: its Status Line / Shelf masks and cm views are set up (#81). With
    ``filepath`` / ``idname``: workspace ``idname`` of that file (a saved workspace, ``template_name`` None)."""
    before = set(bpy.data.workspaces)
    libs = set(bpy.data.libraries)
    with bpy.context.temp_override(**_window_override(window)):
        bpy.ops.workspace.append_activate(idname=idname or template_name, filepath=filepath or _template_blend())
    if filepath is not None:
        # the appended workspace is local: the saved file's library entry isn't needed
        def same(path):
            return os.path.normcase(os.path.normpath(bpy.path.abspath(path))) ==                 os.path.normcase(os.path.normpath(filepath))
        for lib in [lib for lib in bpy.data.libraries if lib not in libs and same(lib.filepath)]:
            if not _linked_from(lib):
                bpy.data.libraries.remove(lib)
    new = [ws for ws in bpy.data.workspaces if ws not in before]
    if not new:
        return None
    ws = new[0]
    if template_name is not None:
        ws[TEMPLATE_KEY] = template_name
    window.workspace = ws
    # region flag writes call ED_area_init, which reads the context window's workspace (None after a file load in
    # -b crashed Blender)
    with bpy.context.temp_override(**_window_override(window)):
        _mark_strips(ws)
        _fit_views(ws, window.scene, ws.get(USER_UNIT_KEY, 0.01))
    return ws


def _linked_from(lib):
    """True when some data of the open file is still linked from library ``lib``."""
    for attr in dir(bpy.data):
        coll = getattr(bpy.data, attr, None)
        if attr == "libraries" or not isinstance(coll, bpy.types.bpy_prop_collection):
            continue
        if any(getattr(i, "library", None) == lib for i in coll):
            return True
    return False


def template_of(ws):
    """The template name of a Maya workspace (None: not one of the kit's Maya workspaces)."""
    if ws is None or USER_KEY in ws:      # a saved workspace isn't a template's copy
        return None
    name = ws.get(TEMPLATE_KEY)
    if isinstance(name, str) and name:
        return name
    return TEMPLATE_WORKSPACE if is_maya_workspace(ws) else None


def reset_workspace(window, ws=None):
    """Maya Windows > Workspaces > Reset Current Workspace (#81): the current Maya workspace is replaced by a fresh
    copy from the bundled template (same name, same way back to Blender's layout); the old one is deleted once the
    window shows the new one. Returns the new workspace (None: not a Maya workspace)."""
    if window is None:
        return None
    old = ws or window.workspace
    template = template_of(old)
    if template is None:
        return None
    name, prev = old.name, old.get(PREV_KEY)
    old.name = name + " (old)"
    ws = append_workspace(window, template)
    if ws is None:
        old.name = name
        return None
    ws.name = name
    if prev is not None:
        ws[PREV_KEY] = prev
    gone = old.name
    if window.workspace == old:
        _delete_later(window, gone, [])
    else:
        _delete_workspace(window, gone, [])
    return ws


STRIP_MASKS = (".AllsetStrip", ".AllsetShelf")   # ui/shelf.MARKER, SHELF_MARKER (top to bottom)
MASK_KEY = "allset_switch_masks"


def _mark_strips(ws):
    """Appending a workspace doesn't bring the Masks its Image Editors point to, and those mark the
    Status Line row and the Shelf row (ui/shelf.is_strip): load them and point the two
    top Image Editors (Status Line above the Shelf) at them again."""
    missing = [m for m in STRIP_MASKS if m not in bpy.data.masks]
    if missing:
        with bpy.data.libraries.load(_template_blend(), link=False) as (src, dst):
            dst.masks = [m for m in missing if m in src.masks]
        ws[MASK_KEY] = missing
    for screen in ws.screens:
        rows = sorted((a for a in screen.areas if a.type == 'IMAGE_EDITOR'), key=lambda a: -a.y)
        for area, name in zip(rows, STRIP_MASKS):
            mask = bpy.data.masks.get(name)
            if mask is not None:
                area.spaces.active.mask = mask


def leave_layout(window):
    """Back to the workspace from before ``enter_layout``; the appended one is deleted."""
    if window is None:
        return False
    ws = window.workspace
    if ws is None:
        return False
    if PREV_KEY not in ws:
        return _leave_template_layout(window) if is_maya_workspace(ws) else False
    prev = bpy.data.workspaces.get(ws[PREV_KEY]) or next(
        (w for w in bpy.data.workspaces if w != ws and not is_maya_workspace(w)), None)
    if prev is None:
        return False
    window.workspace = prev
    added = list(ws.get(MASK_KEY, ()))
    name = ws.name
    if window.workspace == ws:
        # The window changes workspace on its next event loop: delete the old one after that. Deleting the
        # screen the window still draws crashed Blender 5.1 (screen_draw_move_highlight, GUI sweep).
        _delete_later(window, name, added)
    else:
        _delete_workspace(window, name, added)
    return True


BLENDER_LAYOUT_KEY = "allset_blender_layout"
BLENDER_PREV_KEY = "allset_blender_prev"     # on a template Maya workspace: the user's workspace before it (#185)
# Blender's embedded factory startup file: what Add Workspace > General appends from (workspace_edit.cc
# workspace_append_button, BLO_EMBEDDED_STARTUP_BLEND)
EMBEDDED_STARTUP = "<startup.blend>"
# The workspace the user's own file showed when a new Maya scene replaced it (first_start.new_maya_scene).
START_WORKSPACE = {"name": None}


def user_startup_file():
    """The user's own Blender startup file (File > Defaults > Save Startup File), or None. Only read: its workspaces
    come back when a new Maya scene had replaced the user's file (#185)."""
    config = os.environ.get("BLENDER_USER_CONFIG")
    if not config:
        base = os.environ.get("BLENDER_USER_RESOURCES") or bpy.utils.resource_path('USER')
        config = os.path.join(base, "config")
    path = os.path.join(config, "startup.blend")
    return path if os.path.isfile(path) else None


def _users_workspace(window):
    """A workspace of the user's already in the file: the one the user had before the Maya layout, else the one
    last brought back, else any workspace that isn't a Maya one (#185)."""
    ws = window.workspace
    names = [ws.get(BLENDER_PREV_KEY)] if ws is not None else []
    names.append(START_WORKSPACE["name"])
    for name in names:
        found = bpy.data.workspaces.get(name) if name else None
        if found is not None and not is_maya_workspace(found):
            return found
    marked = [w for w in bpy.data.workspaces if BLENDER_LAYOUT_KEY in w]
    if marked:
        return marked[0]
    return next((w for w in bpy.data.workspaces if not is_maya_workspace(w)), None)


def _append_workspaces(path, names):
    """Append the workspaces ``names`` of ``path`` as data (marked BLENDER_LAYOUT_KEY); returns {name in path:
    workspace}. Not ``workspace.append_activate``: in the UI each of those switches the window to the workspace it
    appended once the event loop runs, after the switch has chosen the one to show (#185)."""
    before = set(bpy.data.workspaces)
    try:
        with bpy.data.libraries.load(path, link=False) as (_src, dst):
            dst.workspaces = list(names)
    except (OSError, RuntimeError) as ex:
        print("Maya Workflow Kit: workspaces not appended:", ex)
        return {}
    out = {}
    for name, ws in zip(names, dst.workspaces):
        if ws is not None and ws not in before:
            ws[BLENDER_LAYOUT_KEY] = True
            out[name] = ws
    return out


def _users_startup_workspaces(window):
    """The workspaces of the user's own startup file appended to the open file; returns the one to show (the one
    the user's file showed, else Layout, else the first), or None when there is no user startup file."""
    path = user_startup_file()
    if path is None:
        return None
    try:
        with bpy.data.libraries.load(path) as (src, _dst):
            names = list(src.workspaces)
    except (OSError, RuntimeError) as ex:
        print("Maya Workflow Kit: startup file not read:", ex)
        return None
    got = _append_workspaces(path, names)
    for name in (START_WORKSPACE["name"], "Layout"):
        if name in got:
            return got[name]
    return next(iter(got.values()), None)


def blender_target(window):
    """The workspace a switch to Blender shows in ``window`` when its Maya layout came with the file (no workspace
    to go back to): the user's workspace if the file has one, else the user's own startup workspaces appended,
    else Blender's factory Layout (#19, #185)."""
    target = _users_workspace(window) or _users_startup_workspaces(window)
    if target is not None:
        return target
    before = set(bpy.data.workspaces)
    try:
        with bpy.context.temp_override(**_window_override(window)):
            bpy.ops.workspace.append_activate(idname="Layout", filepath=EMBEDDED_STARTUP)
    except RuntimeError as ex:
        print("Maya Workflow Kit: Blender layout not appended:", ex)
        return None
    new = [w for w in bpy.data.workspaces if w not in before]
    if not new:
        return None
    new[0][BLENDER_LAYOUT_KEY] = True
    return new[0]


def _leave_template_layout(window):
    """The window shows the Maya layout of a Maya Workflow Kit template file (no workspace to go back to): give it
    the user's workspace (``blender_target``), appended once and reused. The Maya one stays in the file for the way
    back (``enter_layout``)."""
    target = blender_target(window)
    if target is None:
        return False
    window.workspace = target
    return True


def _delete_workspace(window, name, added):
    ws = bpy.data.workspaces.get(name)
    # workspace.delete removes the window's active workspace whatever the override says: remove the
    # left one as data once no window shows it (4.5 and 5.1 GUI)
    if ws is not None and all(w.workspace != ws for w in _windows()):
        bpy.data.batch_remove(ids=[ws])
    for mask_name in added:                  # masks the switch loaded go too: the file is as before
        mask = bpy.data.masks.get(mask_name)
        if mask is not None:
            bpy.data.masks.remove(mask)


def drop_workspace(window, ws):
    """Remove workspace ``ws`` from the open file (once ``window`` no longer shows it)."""
    name = ws.name + " (old)" if not ws.name.endswith(" (old)") else ws.name
    ws.name = name
    if window.workspace == ws:
        _delete_later(window, ws.name, [])
    else:
        _delete_workspace(window, ws.name, [])


def _delete_later(window, name, added, tries=40):
    ptr = window.as_pointer()
    left = [tries]

    def tick():
        win = live_refs.window(ptr)
        ws = bpy.data.workspaces.get(name)
        if win is None or ws is None:
            _forget_timer(tick)
            return None
        left[0] -= 1
        if win.workspace == ws and left[0] > 0:
            return 0.05
        _delete_workspace(win, name, added)
        _forget_timer(tick)
        return None
    _timers.append(tick)
    bpy.app.timers.register(tick, first_interval=0.05)


# Timers this module started (closures): unregister() stops any still pending, so nothing of the kit runs after it.
_timers = []


def _forget_timer(fn):
    if fn in _timers:
        _timers.remove(fn)


def _windows():
    wm = bpy.context.window_manager
    return list(wm.windows) if wm is not None else []


def _mode_modules():
    from . import MODE
    return MODE


# The Maya mode modules registered right now, in order (#198 #199). ``unregister_mode`` takes back exactly
# these, so a half-done register or a module that raises on unregister can't leave Maya menus behind.
_mode_done = []


def register_mode():
    """Register the Maya mode modules all or nothing: on an exception the ones already registered are taken back
    and the exception is raised again (``_registered[0]`` stays False)."""
    from . import safe_reg
    if _mode_done:                  # a previous half state: start clean
        unregister_mode()
    safe_reg.register_all(_mode_modules(), _mode_done)
    _registered[0] = True


def unregister_mode():
    """Take back every Maya mode module that is registered (whatever ``_registered[0]`` says). Returns the names of
    modules whose unregister raised (the others still went)."""
    from . import safe_reg
    failed = safe_reg.unregister_all(_mode_done)
    _registered[0] = False
    return failed


def preferences_off():
    """Maya mode off in the add-on preference (after a failed start, so the switch shows Blender)."""
    try:
        prefs = _prefs_addon()
        if prefs.maya_mode:
            prefs.maya_mode = False
    except Exception:
        pass


# Why the last switch to Maya mode failed (None = it didn't): shown in the console, a report and the preferences.
last_error = [None]


def _report_failure(ex):
    text = f"Maya mode could not start ({type(ex).__name__}: {ex}). Blender stays as it was; see the system console"
    last_error[0] = text
    print("Maya Workflow Kit:", text)
    if bpy.app.background:
        return
    try:
        def draw(menu, _context):
            menu.layout.label(text="Maya mode could not start: Blender stays as it was.", icon='ERROR')
            menu.layout.label(text=f"{type(ex).__name__}: {ex}"[:160])
            menu.layout.label(text="Details: Window > Toggle System Console.")
        bpy.context.window_manager.popup_menu(draw, title="Maya Workflow Kit", icon='ERROR')
    except Exception:
        pass


def stop_playback():
    """Stop animation playback in every window before a switch: the keymap and the timeline header change under
    a running playback otherwise. Returns the number of windows stopped."""
    stopped = 0
    if bpy.app.background:
        return 0
    for window in _windows():
        screen = window.screen
        if screen is None or not screen.is_animation_playing:
            continue
        try:
            with bpy.context.temp_override(window=window, screen=screen):
                bpy.ops.screen.animation_cancel(restore_frame=False)
            stopped += 1
        except RuntimeError:
            pass
    return stopped


def set_mode(on, layout=True):
    """Switch Maya mode on / off now (no restart). The open file's scenes are not touched; Blender's preferences
    are never written: switching off unregisters the Maya mode modules, which takes back everything
    they registered."""
    prefs = _prefs_addon()
    stop_playback()
    if on and prefs.maya_mode and _registered[0]:
        # already on (a start with Maya mode saved on keeps the user's workspace): the Maya button puts the Maya
        # keys back in place and opens the Maya layout
        from . import keymap
        keymap.activate()
        keymap.keep_first_now()
        if layout and not bpy.app.background:
            for window in _windows()[:1]:
                enter_layout(window)
        _redraw()
        return False
    if on == bool(prefs.maya_mode) and (on == _registered[0]):
        return False
    if on:
        if not _registered[0]:
            try:
                register_mode()
            except Exception as ex:      # rolled back already: plain Blender, Maya mode stays off
                preferences_off()
                _report_failure(ex)
                _redraw()
                return False
        last_error[0] = None
        prefs.maya_mode = True
        from . import keymap
        keymap.activate()
        if layout and not bpy.app.background:
            for window in _windows()[:1]:
                enter_layout(window)
    else:
        try:
            from .ui import maya_dock
            maya_dock.close_floating()     # floating Maya panels would show Blender's Tool tab
        except Exception:
            pass
        try:
            from .ui import four_view
            four_view.collapse_all(bpy.context)   # the four panels back to one, the screen as it was
        except Exception:
            pass
        if layout:
            for window in _windows():
                leave_layout(window)
        prefs.maya_mode = False
        unregister_mode()      # whatever is recorded as registered, also after a half-done switch (#198)
    # The mode is this add-on's own setting: marked for Blender's Auto-Save Preferences like a change made in the
    # Preferences editor (no Blender setting is written).
    bpy.context.preferences.is_dirty = True
    _redraw()
    return True


_registered = [False]


def _redraw():
    for window in _windows():
        for area in window.screen.areas:
            area.tag_redraw()


# --- UI -----------------------------------------------------------------------------------------

_pending = []


def _apply_pending():
    while _pending:
        on, layout = _pending.pop(0)
        try:
            set_mode(on, layout=layout)
        except Exception as ex:   # never leave a timer raising forever
            print("Maya Workflow Kit: switch failed:", ex)
            import traceback
            traceback.print_exc()
    return None


def request(on, layout=True):
    """Switch from a timer, after the calling operator / draw has finished."""
    _pending.append((on, layout))
    if not bpy.app.timers.is_registered(_apply_pending):
        bpy.app.timers.register(_apply_pending, first_interval=0.0)


class ALLSET_OT_switch_mode(bpy.types.Operator):
    """Switch between Maya mode (Maya keymap, layout and menus) and plain Blender.
    Nothing in the open file's scenes changes; Blender's preferences are never changed"""
    bl_idname = "allset.switch_mode"
    bl_label = "Switch Maya / Blender"
    bl_options = {'REGISTER'}

    mode: bpy.props.EnumProperty(
        name="Mode", items=(('TOGGLE', "Toggle", ""), ('MAYA', "Maya", ""), ('BLENDER', "Blender", "")),
        default='TOGGLE', options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        if props.mode == 'MAYA':
            return "Switch to Maya mode: Maya keymap, layout and menus (Ctrl+Alt+Shift+M)"
        if props.mode == 'BLENDER':
            return "Switch back to plain Blender: Blender's own keymap, layout and menus (Ctrl+Alt+Shift+M)"
        return "Switch between Maya mode and plain Blender (Ctrl+Alt+Shift+M)"

    def execute(self, context):
        on = (not is_on()) if self.mode == 'TOGGLE' else self.mode == 'MAYA'
        request(on)
        results.result(self, "Maya mode" if on else "Blender mode")
        return {'FINISHED'}


def draw_topbar_switch(self, context):
    """Top bar, right: [Maya | Blender] (both modes)."""
    region = context.region
    if region is None or region.alignment != 'RIGHT':
        return
    on = is_on()
    # Maya's menu bar has nothing here: flat text, the current mode bright and the other dim
    row = self.layout.row(align=True)
    row.scale_x = 0.85
    sub = row.row(align=True)
    sub.active = on
    sub.operator(ALLSET_OT_switch_mode.bl_idname, text="Maya", emboss=False).mode = 'MAYA'
    row.label(text="|")
    sub = row.row(align=True)
    sub.active = not on
    sub.operator(ALLSET_OT_switch_mode.bl_idname, text="Blender", emboss=False).mode = 'BLENDER'


def draw_edit_menu(self, context):
    """Blender's Edit menu: found by the menu search (F3) in Blender mode."""
    if is_on():
        return
    self.layout.separator()
    self.layout.operator(ALLSET_OT_switch_mode.bl_idname, text="Switch to Maya Mode",
                         icon='EVENT_M').mode = 'MAYA'


classes = (ALLSET_OT_switch_mode,)
_keymaps = []


def _add_shortcut():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    km = kc.keymaps.new(name="Window", space_type='EMPTY', region_type='WINDOW')
    key, mods = SHORTCUT
    kmi = km.keymap_items.new(ALLSET_OT_switch_mode.bl_idname, key, 'PRESS', **mods)
    kmi.properties.mode = 'TOGGLE'
    _keymaps.append((km, kmi))


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_HT_upper_bar.append(draw_topbar_switch)
    bpy.types.TOPBAR_MT_edit.append(draw_edit_menu)
    _add_shortcut()


def unregister():
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _keymaps.clear()
    bpy.types.TOPBAR_MT_edit.remove(draw_edit_menu)
    bpy.types.TOPBAR_HT_upper_bar.remove(draw_topbar_switch)
    for fn in (_apply_pending, *_timers):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    _timers.clear()
    _pending.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
