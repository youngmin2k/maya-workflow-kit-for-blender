# SPDX-License-Identifier: GPL-3.0-or-later
"""The Maya layout as a new file, "Make Blender Maya" and starting Blender in the Maya layout.

- ``allset.new_maya_scene`` ("New Scene in Maya Layout"): a new untitled file read from the layout file bundled inside
  the extension (``app_template.STARTUP``) with ``wm.read_homefile(filepath=...)``. Unlike the app template of
  older versions nothing is copied into the user's scripts folder, and the preferences are kept.
- ``allset.make_maya``: "Start in Maya Layout" on (this add-on's own setting) and the Maya layout now: a new Maya
  scene when the open file is untouched, else the layout workspace appended to the open file
  (``switch.enter_layout``). It writes none of Blender's preferences: the Maya theme, splash, density, font, wire,
  navigation, undo and panel presets of older versions are gone.
- Start in the Maya layout: armed on register, the first load_post (Blender's startup file, loaded right after the
  add-ons register) opens a new Maya scene when Blender started without a file; the first timer tick disarms it, so
  File > New later is left alone.

Operators never load a file themselves (Blender crashed reporting an operator whose class was re-registered
meanwhile): ``open_layout_later`` does it from a timer after the operator has returned.
"""

import bpy
from bpy.app.handlers import persistent

from . import app_template, preferences

_armed = [False]


def new_maya_scene(options=None):
    """Replace the open file with a new untitled file in the Maya layout (not from inside an operator), with the
    New Scene Options: ``options`` (the option window's values) or the saved ones and the New Scene Time."""
    _armed[0] = False      # this load is the Maya layout: the start hook must not load it again (#47)
    from .operators import option_windows
    if options is None:
        options, full = option_windows.new_scene_values()
    else:
        full = True
    old = bpy.context.scene
    before = option_windows.scene_units(old) if old is not None else None
    win = _window()
    from . import switch
    if win is not None and win.workspace is not None:
        # shown again by a switch to Blender (#185); from the Maya layout: the workspace before it (#307)
        name = win.workspace.name if not switch.is_maya_workspace(win.workspace) else win.workspace.get(switch.PREV_KEY)
        prev = bpy.data.workspaces.get(name) if isinstance(name, str) else None
        if prev is not None and not switch.is_maya_workspace(prev):
            switch.START_WORKSPACE["name"] = prev.name
    if win is None:
        res = bpy.ops.wm.read_homefile(filepath=app_template.STARTUP, load_ui=True)
    else:
        with bpy.context.temp_override(window=win, screen=win.screen):
            res = bpy.ops.wm.read_homefile(filepath=app_template.STARTUP, load_ui=True)
    # Maya's startup cameras persp / top / front / side head the new scene's DAG (#117)
    from .operators import startup_cameras
    scene = bpy.context.scene or (bpy.data.scenes[0] if bpy.data.scenes else None)
    if scene is not None:
        startup_cameras.ensure(scene, scene.view_layers[0])
        option_windows.apply_new_scene(scene, options, full, before)
    return res


def make(context, open_layout=True):
    """Everything "Make Blender Maya" does to the kit's own settings; ``open_layout`` also loads a new Maya scene
    (only outside an operator: use ``open_layout_later`` from one)."""
    prefs = preferences.get(context)
    prefs.start_in_maya_layout = True
    prefs.welcome_done = True
    # This add-on's own settings changed: marked for Blender's Auto-Save Preferences (never saved by the kit)
    context.preferences.is_dirty = True
    if open_layout:
        new_maya_scene()


def open_layout_later():
    """Open a new file with the Maya layout once the calling operator has finished."""
    if not bpy.app.timers.is_registered(_open_layout):
        bpy.app.timers.register(_open_layout, first_interval=0.01)


def show_layout(window):
    """The Maya layout in ``window`` now: a new Maya scene when the open file is untouched (later, from a timer),
    else its layout workspace appended to the open file."""
    if window is None or bpy.app.background:
        return
    if not bpy.data.is_dirty and not bpy.data.filepath:
        open_layout_later()
    else:
        from . import switch
        switch.enter_layout(window)


class ALLSET_OT_make_maya(bpy.types.Operator):
    """Start Blender in the Maya layout from now on and show the Maya layout: a new Maya scene when the open file
    is untouched, else the Maya layout added to this file. Blender's preferences are not changed"""
    bl_idname = "allset.make_maya"
    bl_label = "Make Blender Maya"
    bl_options = {'INTERNAL'}

    open_layout: bpy.props.BoolProperty(name="Open Maya Layout", default=True, options={'SKIP_SAVE'})

    def execute(self, context):
        make(context, open_layout=False)
        if self.open_layout:
            show_layout(context.window)
        return {'FINISHED'}


class ALLSET_OT_new_maya_scene(bpy.types.Operator):
    """Start a new file in the Maya layout (centimetre scene, Maya views, Status Line, shelf, Channel Box).
    A modified scene asks first: Save / Don't Save / Cancel"""
    bl_idname = "allset.new_maya_scene"
    bl_label = "New Scene in Maya Layout"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        # Maya's "Save changes?" dialog before File > New Scene / Ctrl+N (#57; ui/save_prompt.py)
        from .ui import save_prompt
        return save_prompt.ask(context, new_maya_scene)

    def execute(self, context):
        open_layout_later()
        return {'FINISHED'}


class ALLSET_OT_maya_layout_here(bpy.types.Operator):
    """Add the Maya layout to the open file as a workspace and show it (the scenes are not changed)"""
    bl_idname = "allset.maya_layout_here"
    bl_label = "Maya Layout in This File"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        from . import switch
        if switch.enter_layout(context.window) is None and not switch.is_maya_workspace(context.window.workspace):
            return {'CANCELLED'}
        return {'FINISHED'}


def _window():
    wm = bpy.context.window_manager
    return wm.windows[0] if wm and wm.windows else None


@persistent
def _on_load_post(*_args):
    if not _armed[0]:
        return
    _armed[0] = False
    try:
        prefs = preferences.get()
    except KeyError:
        return
    if prefs.start_in_maya_layout and not bpy.data.filepath and not bpy.app.background:
        open_layout_later()


def _open_layout():
    if _window() is None:
        return 0.1
    new_maya_scene()
    return None


def _disarm():
    _armed[0] = False
    return None


classes = (ALLSET_OT_make_maya, ALLSET_OT_new_maya_scene, ALLSET_OT_maya_layout_here)
_timers = (_open_layout, _disarm)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_post.append(_on_load_post)
    if bpy.app.background:
        return
    _armed[0] = True
    bpy.app.timers.register(_disarm, first_interval=0.0)


def unregister():
    for fn in _timers:
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    _armed[0] = False
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
