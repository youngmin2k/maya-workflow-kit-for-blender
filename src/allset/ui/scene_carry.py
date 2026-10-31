# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's tool settings and UI don't come from the scene file (issues #63 #64).

Global tool settings (#64): Maya keeps each tool context's settings in its preferences
and symmetry / soft select in global options, so they survive File > New Scene / Open. Blender keeps them per scene (``Scene.tool_settings``, the transform orientation
slots, the kit's scene property groups), and a new / opened file brings its own. Like the selection masks
(``ui/status_line._masks_before_load``), load_pre reads them from the current scene and load_post writes them into
every scene of the loaded file — every load: File > Open, Open Recent, Revert, New Scene (the kit's startup.blend) and
Blender's File > New. What is carried is ``TOOL_SETTINGS`` / ``SCENE_GROUPS`` / ``SCENE_PROPS`` / the orientation
slots / the soft select radius (in Maya units) / the pivot options (``WM_PROPS``). Soft select on / off is already one
global state (``operators/soft_select.py``), and Smart Duplicate / Extrude are add-on preferences.

Maya layout on Open (#63): Maya's UI is built at startup from the workspace, never from the scene file.
With Maya mode on and the add-on preference ``maya_layout_on_open``, a file opened
in a non-Maya workspace gets the Maya layout from a timer after load_post (``switch.enter_layout`` runs an operator:
not inside the load) — the file's own Maya layout workspace when it has one, else the bundled one appended.
"""

import bpy

from .. import live_refs

# ToolSettings attributes Maya keeps as tool / global options (Move / Rotate / Scale settings;
# snapping toggles of the Status Line; soft selection falloff).
TOOL_SETTINGS = (
    "use_snap", "snap_elements", "use_snap_translate", "use_snap_rotate", "use_snap_scale",
    "use_snap_grid_absolute", "snap_angle_increment_3d",                # step snap (operators/snap_align.py)
    "transform_pivot_point",                                             # Rotate / Scale center
    "use_transform_skip_children", "use_transform_correct_face_attributes",   # Preserve Children / UVs
    "proportional_edit_falloff", "use_proportional_connected", "use_proportional_projected",  # soft select
)
# Scene property groups of the kit that hold Maya tool options (all their saved properties are carried).
SCENE_GROUPS = ("allset_symmetry", "allset_mesh_tools", "allset_uv")
SCENE_PROPS = ("allset_auto_key",)          # Maya autoKeyframe -state is a global option
# Transform orientation types that exist in every scene; a custom one ("Maya Pivot") is scene data and stays the
# file's own.
BUILTIN_ORIENTATIONS = {"GLOBAL", "LOCAL", "NORMAL", "GIMBAL", "VIEW", "CURSOR", "PARENT"}
WM_PROPS = ("allset_pin_pivot", "allset_snap_pivot_pos", "allset_snap_pivot_ori")   # operators/pivot_menu.OPTIONS

_carried = {}


# --- tool settings ---------------------------------------------------------------------------------------

def _group_values(group):
    out = {}
    for prop in group.bl_rna.properties:
        name = prop.identifier
        if name == "rna_type" or prop.is_readonly or prop.type in {'POINTER', 'COLLECTION'} \
                or prop.is_skip_save:
            continue
        value = getattr(group, name)
        out[name] = set(value) if isinstance(value, set) else (tuple(value) if hasattr(value, "__len__")
                                                                and not isinstance(value, str) else value)
    return out


def _maya_unit(scene):
    from ..operators import units
    return units.maya_unit(scene)


def read(scene, wm=None):
    """The global Maya tool settings of ``scene`` (and the window manager's pivot options) as plain values."""
    ts = scene.tool_settings
    state = {"tool_settings": {}, "groups": {}, "props": {}, "slots": [], "wm": {}}
    for name in TOOL_SETTINGS:
        if hasattr(ts, name):
            value = getattr(ts, name)
            state["tool_settings"][name] = set(value) if isinstance(value, set) else value
    state["soft_radius"] = ts.proportional_size / _maya_unit(scene)      # Maya units: a cm and an m file agree
    for name in SCENE_GROUPS:
        group = getattr(scene, name, None)
        if group is not None:
            state["groups"][name] = _group_values(group)
    for name in SCENE_PROPS:
        if hasattr(scene, name):
            state["props"][name] = getattr(scene, name)
    state["step_snap"] = dict(scene.get("allset_step_snap", {}))    # per-tool Step Snap (snap_align.STEP_PROP)
    for slot in scene.transform_orientation_slots:
        state["slots"].append((slot.type if slot.type in BUILTIN_ORIENTATIONS else None,
                               getattr(slot, "use", None)))
    if wm is not None:
        for name in WM_PROPS:
            if hasattr(wm, name):
                state["wm"][name] = getattr(wm, name)
    return state


def _set(owner, name, value):
    try:
        if getattr(owner, name) != value:
            setattr(owner, name, value)
    except (AttributeError, TypeError, ValueError):
        pass


def write(scene, state, wm=None):
    """Put ``state`` (from ``read``) into ``scene``."""
    if not state:
        return
    ts = scene.tool_settings
    for name, value in state["tool_settings"].items():
        _set(ts, name, value)
    radius = state.get("soft_radius")
    if radius:
        _set(ts, "proportional_size", max(1e-6, radius * _maya_unit(scene)))
    for name, values in state["groups"].items():
        group = getattr(scene, name, None)
        if group is None:
            continue
        for key, value in values.items():
            _set(group, key, value)
    for name, value in state["props"].items():
        _set(scene, name, value)
    if "step_snap" in state:
        scene["allset_step_snap"] = state["step_snap"]
    slots = scene.transform_orientation_slots
    for i, (kind, use) in enumerate(state["slots"][:len(slots)]):
        if kind is not None:
            _set(slots[i], "type", kind)
        if use is not None and hasattr(slots[i], "use"):
            _set(slots[i], "use", use)
    if wm is not None:
        for name, value in state["wm"].items():
            _set(wm, name, value)


_session = {"loaded": False}     # a file was loaded since Maya mode registered


def _in_maya_layout():
    from .. import switch
    window = _first_window()
    ws = window.workspace if window is not None else getattr(bpy.context, "workspace", None)
    return switch.is_maya_workspace(ws)


def carries_from_current():
    """The current scene holds the session's Maya tool settings: a file was loaded since Maya mode came on (that
    load already carried / started them), or the window shows the Maya layout. Not Blender's startup scene right after
    Blender started: its Blender defaults (Median Point pivot, Global Rotate axis) must not replace the Maya-style
    defaults of the kit's New Scene (the first Maya scene of a session starts from the default settings, like Maya)."""
    return _session["loaded"] or _in_maya_layout()


@bpy.app.handlers.persistent
def _before_load(*_args):
    _carried.pop("state", None)
    try:
        if carries_from_current():
            _carried["state"] = read(bpy.context.scene, bpy.context.window_manager)
    except (AttributeError, ReferenceError):
        pass


@bpy.app.handlers.persistent
def _after_load(*_args):
    state = _carried.pop("state", None)
    try:
        wm = bpy.context.window_manager
        from ..operators import snap_align
        for scene in bpy.data.scenes:
            write(scene, state, wm)
            snap_align.heal_affect(scene.tool_settings)    # #139: files saved with Move snapping cut off by Step Snap
    except (AttributeError, ReferenceError):
        pass
    _session["loaded"] = True
    _arm_layout()


# --- Maya layout on Open ---------------------------------------------------------------------------------

def wants_layout(maya_mode, option, filepath, active_is_maya, background=False):
    """True when a load should be followed by the Maya layout: Maya mode on, the option on, a file with a path (the
    kit's New Scene and Blender's File > New / startup file are untitled: their layout is left to first_start /
    the user), shown in a workspace that isn't the Maya layout, and a UI."""
    return bool(maya_mode and option and filepath and not active_is_maya and not background)


def _prefs():
    from .. import preferences
    try:
        return preferences.get()
    except KeyError:
        return None


def _first_window():
    wins = live_refs.windows()
    return wins[0] if wins else None


_pending = {"tries": 0}
RETRIES = 20


def _arm_layout():
    prefs = _prefs()
    window = _first_window()
    from .. import switch
    active = switch.is_maya_workspace(window.workspace) if window is not None else False
    if not wants_layout(prefs is not None and prefs.maya_mode, prefs is not None and prefs.maya_layout_on_open,
                        bpy.data.filepath, active, bpy.app.background):
        return
    _pending["tries"] = 0
    if not bpy.app.timers.is_registered(_layout_tick):
        bpy.app.timers.register(_layout_tick, first_interval=0.0)


def maya_workspace():
    """A Maya layout workspace already in the file (its own template one first, then one a switch appended)."""
    from .. import switch
    found = [ws for ws in bpy.data.workspaces if switch.is_maya_workspace(ws)]
    found.sort(key=lambda ws: (switch.PREV_KEY in ws, switch.template_of(ws) != switch.TEMPLATE_WORKSPACE))
    return found[0] if found else None


def show_maya_layout(window):
    """The Maya layout in ``window``: the file's own Maya workspace, else the bundled one appended. Returns the
    workspace or None. The selection masks (applied by load_post to the file's views) are copied onto the
    new views too."""
    from .. import switch
    from . import status_line
    if window is None or switch.is_maya_workspace(window.workspace):
        return None
    with bpy.context.temp_override(window=window, screen=window.screen):
        masks = status_line.session_masks()
    ws = maya_workspace()
    if ws is not None:
        # switch.enter_layout looks only for a workspace without PREV_KEY: a file saved with the appended Maya
        # workspace in the background would get a second one
        window.workspace = ws
    else:
        ws = switch.enter_layout(window)
    status_line.apply_masks(masks)
    return ws


def _layout_tick():
    window = _first_window()
    if window is None or window.screen is None:
        _pending["tries"] += 1
        return 0.1 if _pending["tries"] < RETRIES else None
    prefs = _prefs()
    if prefs is None or not prefs.maya_mode or not prefs.maya_layout_on_open:
        return None
    try:
        show_maya_layout(window)
    except Exception as ex:      # a timer that raises is dropped silently: say why
        print("Maya Workflow Kit: Maya layout on open failed:", ex)
    return None


def register():
    _session["loaded"] = False
    bpy.app.handlers.load_pre.append(_before_load)
    bpy.app.handlers.load_post.append(_after_load)


def unregister():
    for handlers, fn in ((bpy.app.handlers.load_pre, _before_load), (bpy.app.handlers.load_post, _after_load)):
        if fn in handlers:
            handlers.remove(fn)
    if bpy.app.timers.is_registered(_layout_tick):
        bpy.app.timers.unregister(_layout_tick)
    _carried.clear()
    _session["loaded"] = False
