# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya G / Edit > Repeat / Recent Commands for every Maya command, not only key operators.

Maya 2022: a menu item run from the UI goes into ``repeatLast``
(Create > Polygon Primitives > Cube → "CreatePolygonCube", G makes the next cube); an option window's Apply records the
command with its options (label "PolyPrimitive"); commands run by a script are not
recorded; Edit > Repeat reads ``Repeat "<label>"``; Recent Commands lists the history.

Blender's G (``screen.repeat_last``) repeats the last *registered* operator, and the kit's menu / shelf / marking-menu
commands are never registered (``marking/modal.run_action`` calls operators from Python, undo_steps.py:4-6). So the kit
keeps its own record of Maya commands (``record``) next to Blender's operator list: G repeats whichever is newer —
the kit record unless a repeatable Blender operator was registered after it (key commands such as Ctrl+E,
Ctrl+D). Selection, transform, view, undo and screen operators never count: Maya's repeatLast doesn't take selection
clicks or manipulator drags; a manipulator drag on a kit node (Ctrl+E then drag) is a node edit, so
G after it extrudes the new selection (like Maya; #184).
"""

import bpy

from .. import results

MAX = 30                     # history kept (Maya's Recent Commands list is a short history)
HISTORY = []                 # oldest first: {"label", "action", "path", "mark"}
# Blender operators Maya's repeatLast never records (selection, manipulator / transform, view, undo, UI).
SKIP_PREFIXES = ("TRANSFORM_OT_", "VIEW3D_OT_view", "VIEW3D_OT_zoom", "VIEW3D_OT_move", "VIEW3D_OT_rotate",
                 "VIEW3D_OT_dolly", "VIEW3D_OT_navigate", "VIEW3D_OT_walk", "VIEW3D_OT_fly", "VIEW3D_OT_localview",
                 "ED_OT_", "SCREEN_OT_", "WM_OT_", "OUTLINER_OT_", "UI_OT_", "IMAGE_OT_view", "GRAPH_OT_view",
                 "ACTION_OT_view", "ALLSET_OT_repeat", "ALLSET_OT_hotbox", "ALLSET_OT_mm_", "ALLSET_OT_smart_extrude",
                 "ALLSET_OT_inview_", "ALLSET_OT_attribute_field_", "ALLSET_OT_node_attribute_apply",
                 "ALLSET_OT_cb_virtual_slider", "ALLSET_OT_option_editor_")
NO_RECORD = {"Edit/Repeat", "Edit/Recent Commands List", "Edit/Undo", "Edit/Redo"}
# These kit operators implement selection/display or manipulator drags, just like
# the native operators excluded above. They are UI state, not another modeling command.
NON_COMMANDS = frozenset({
    "OBJECT_OT_mode_set", "OBJECT_OT_editmode_toggle",
    "ALLSET_OT_component_mode", "ALLSET_OT_component_mask", "ALLSET_OT_toggle_sel_mode",
    "ALLSET_OT_convert_selection", "ALLSET_OT_select_convert", "ALLSET_OT_uv_component",
    "ALLSET_OT_display_mode", "ALLSET_OT_smooth_preview", "ALLSET_OT_smooth_level",
    "ALLSET_OT_frame", "ALLSET_OT_frame_all_views", "ALLSET_OT_view_history", "ALLSET_OT_view_home",
    "ALLSET_OT_toggle_quad_view", "ALLSET_OT_tumble", "ALLSET_OT_dolly", "ALLSET_OT_dolly_2d",
    "ALLSET_OT_box_zoom", "ALLSET_OT_camera_mode_toggle",
    "ALLSET_OT_component_scale", "ALLSET_OT_live_translate",
    "ALLSET_OT_pivot_translate", "ALLSET_OT_pivot_rotate", "ALLSET_OT_pivot_pick",
    "ALLSET_OT_pivot_exit", "ALLSET_OT_pivot_option", "ALLSET_OT_menu_tool", "ALLSET_OT_last_tool",
})


def _node_edits():
    """bl_idnames of the operators that change a kit history node's values (manipulator, In-View Editor, Channel
    Box INPUTS). Maya's G runs the command again on the new selection, it never repeats a node edit (#184)."""
    from . import extrude
    return {"ALLSET_OT_" + spec.edit_op for spec in extrude.SPECS.values() if spec.edit_op}


def repeatable(idname):
    """Would Maya's G repeat this Blender operator (bl_idname 'MESH_OT_extrude' style)?"""
    return not (idname in NON_COMMANDS or "_OT_select" in idname
                or idname.startswith(SKIP_PREFIXES) or idname in _node_edits())


def _recordable(action):
    """Apply the same command filter to menu/shelf actions as to key operators.

    Resolve item wrappers so Select > All and RMB > Face do not replace an
    extrusion, while a wrapped modeling command still records its saved action.
    """
    from ..ui import menu_map
    seen = set()
    while True:
        spec = menu_map.normalize(action)
        if spec is None or spec[0] not in {"op", "v3d"}:
            return False
        _kind, target, props = spec
        if target not in {"allset.menu_item", "allset.component_command", "allset.menu_whole_mesh"}:
            break
        item = props.get("item")
        if item in seen:
            return False
        seen.add(item)
        action = menu_map.MAP.get(item)
    # Smart Extrude explicitly saves a completed operation with its final values;
    # its registered drag helper remains excluded from Blender's history.
    if target == "allset.smart_extrude":
        return True
    namespace, name = target.split(".", 1)
    return repeatable(namespace.upper() + "_OT_" + name)


def _operator_repeatable(op):
    if not repeatable(op.bl_idname):
        return False
    if op.bl_idname in {"ALLSET_OT_component_command", "ALLSET_OT_menu_whole_mesh"}:
        return _recordable(("item", op.properties.item))
    return True


def _mark(context=None):
    """(count, pointer) of Blender's newest registered operator: what was there when a kit record was made."""
    wm = (context or bpy.context).window_manager
    ops = wm.operators if wm is not None else ()
    return (len(ops), ops[-1].as_pointer()) if len(ops) else (0, 0)


def record(label, action, path=None, context=None):
    """A Maya command finished (menu / shelf / marking menu / option window): remember it for G."""
    if path in NO_RECORD or not _recordable(action):
        return
    entry = {"label": label or "Maya Command", "action": action, "path": path, "mark": _mark(context)}
    if HISTORY and HISTORY[-1]["action"] == action and HISTORY[-1]["path"] == path:
        HISTORY[-1] = entry          # the same command again: one row, newest position
    else:
        HISTORY.append(entry)
    del HISTORY[:-MAX]


def _blender_after(context, mark):
    """Newest repeatable Blender operator registered after ``mark`` (index in wm.operators), or None."""
    ops = context.window_manager.operators
    for i in range(len(ops) - 1, -1, -1):
        op = ops[i]
        if mark is not None and op.as_pointer() == mark[1]:
            return None
        if _operator_repeatable(op):
            return i
    return None


def last(context):
    """("kit", entry) / ("blender", operator index) / None: what G repeats now."""
    entry = HISTORY[-1] if HISTORY else None
    idx = _blender_after(context, entry["mark"] if entry else None)
    if idx is not None:
        return ("blender", idx)
    return ("kit", entry) if entry else None


def label(context):
    """Edit > Repeat label: Maya 'Repeat "<label>"', plain "Repeat" when there is nothing to repeat."""
    what = last(context)
    if what is None:
        return "Repeat"
    if what[0] == "kit":
        return f'Repeat "{what[1]["label"]}"'
    return f'Repeat "{context.window_manager.operators[what[1]].bl_label}"'


def run_entry(context, entry):
    from ..marking.modal import run_action
    return run_action(context, entry["action"], path=entry["path"])


def run_blender(context, index, undo=True):
    """Repeat Blender's registered operator ``index`` (screen.repeat_history counts like wm.operators)."""
    ops = context.window_manager.operators
    if index == len(ops) - 1:
        bpy.ops.screen.repeat_last('EXEC_DEFAULT', undo)
    else:
        bpy.ops.screen.repeat_history('EXEC_DEFAULT', undo, index=index)
    # Blender's screen.repeat_last returns CANCELLED even after a successful
    # replay, to keep the wrapper itself out of the operator/undo history.
    return {'FINISHED'}


def repeat(context, inside_undo_op=False):
    """Maya G. ``inside_undo_op``: called from an UNDO operator (Shift+G), which makes the undo step itself."""
    what = last(context)
    if what is None:
        return None
    if what[0] == "kit":
        if inside_undo_op:
            from .. import undo_steps
            with undo_steps.nested():
                return run_entry(context, what[1])
        return run_entry(context, what[1])
    return run_blender(context, what[1], undo=not inside_undo_op)


def recent(context, limit=15):
    """Recent Commands rows, newest first: (kind, key, label) — kit records and repeatable Blender operators in the
    order they happened (a kit record sits after the Blender operator that was newest when it was made)."""
    ops = context.window_manager.operators
    by_ptr = {op.as_pointer(): i for i, op in enumerate(ops)}
    rows = []
    for k, entry in enumerate(HISTORY):
        pos = by_ptr.get(entry["mark"][1], -1) if entry["mark"][0] else -1
        rows.append((pos + 0.5, ("kit", k, entry["label"])))
    rows += [(i, ("blender", i, op.bl_label)) for i, op in enumerate(ops) if _operator_repeatable(op)]
    rows.sort(key=lambda r: r[0], reverse=True)
    return [r[1] for r in rows[:limit]]


class ALLSET_OT_repeat_last(bpy.types.Operator):
    """Repeat the last command: menu, shelf and marking-menu items too (Maya G)"""
    bl_idname = "allset.repeat_last"
    bl_label = "Repeat Last"
    # neither REGISTER (G must not become the command G repeats) nor UNDO (the repeated command makes the step)
    bl_options = set()

    def execute(self, context):
        try:
            res = repeat(context)
        except RuntimeError as ex:
            from . import maya_errors
            maya_errors.report_nested(self, ex)       # a Maya Error stays an Error
            return {'CANCELLED'}
        if res is None:
            results.result(self, "Nothing to repeat")
            return {'CANCELLED'}
        # A repeated command may start its own modal handler. This wrapper does
        # not own that handler, so it finishes while the command keeps running.
        return {'CANCELLED'} if res == {'CANCELLED'} else {'FINISHED'}


class ALLSET_OT_repeat_item(bpy.types.Operator):
    """Run a Recent Commands entry again"""
    bl_idname = "allset.repeat_item"
    bl_label = "Repeat Command"
    bl_options = {'INTERNAL'}

    kind: bpy.props.StringProperty(options={'SKIP_SAVE'})
    index: bpy.props.IntProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        try:
            if self.kind == "kit":
                if not 0 <= self.index < len(HISTORY):
                    return {'CANCELLED'}
                entry = HISTORY[self.index]
                res = run_entry(context, entry)
                if isinstance(res, set) and 'FINISHED' in res:
                    record(entry["label"], entry["action"], entry["path"], context)
            else:
                res = run_blender(context, self.index)
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex).strip().splitlines()[-1])
            return {'CANCELLED'}
        return {'FINISHED'} if isinstance(res, set) and 'FINISHED' in res else {'CANCELLED'}


class ALLSET_MT_recent_commands(bpy.types.Menu):
    """Maya Recent Commands: click one to run it again (newest first)"""
    bl_idname = "ALLSET_MT_recent_commands"
    bl_label = "Recent Commands"

    def draw(self, context):
        layout = self.layout
        rows = recent(context)
        if not rows:
            layout.label(text="No recent commands")
        for kind, key, text in rows:
            op = layout.operator(ALLSET_OT_repeat_item.bl_idname, text=text)
            op.kind, op.index = kind, key


classes = (ALLSET_OT_repeat_last, ALLSET_OT_repeat_item, ALLSET_MT_recent_commands)


@bpy.app.handlers.persistent
def _on_load(*_args):
    HISTORY.clear()          # the records point at another file's data


def register_handlers():
    bpy.app.handlers.load_post.append(_on_load)


def unregister_handlers():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    HISTORY.clear()
