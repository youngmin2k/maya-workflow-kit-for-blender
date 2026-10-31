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
                 "ACTION_OT_view", "ALLSET_OT_repeat", "ALLSET_OT_hotbox", "ALLSET_OT_mm_", "ALLSET_OT_smart_extrude")
NO_RECORD = {"Edit/Repeat", "Edit/Recent Commands List", "Edit/Undo", "Edit/Redo"}


def _node_edits():
    """bl_idnames of the operators that change a kit history node's values (manipulator, In-View Editor, Channel
    Box INPUTS). Maya's G runs the command again on the new selection, it never repeats a node edit (#184)."""
    from . import extrude
    return {"ALLSET_OT_" + spec.edit_op for spec in extrude.SPECS.values() if spec.edit_op}


def repeatable(idname):
    """Would Maya's G repeat this Blender operator (bl_idname 'MESH_OT_extrude' style)?"""
    return not ("_OT_select" in idname or idname.startswith(SKIP_PREFIXES) or idname in _node_edits())


def _mark(context=None):
    """(count, pointer) of Blender's newest registered operator: what was there when a kit record was made."""
    wm = (context or bpy.context).window_manager
    ops = wm.operators if wm is not None else ()
    return (len(ops), ops[-1].as_pointer()) if len(ops) else (0, 0)


def record(label, action, path=None, context=None):
    """A Maya command finished (menu / shelf / marking menu / option window): remember it for G."""
    if path in NO_RECORD:
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
        if repeatable(op.bl_idname):
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
        return bpy.ops.screen.repeat_last('EXEC_DEFAULT', undo)
    return bpy.ops.screen.repeat_history('EXEC_DEFAULT', undo, index=index)


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
    rows += [(i, ("blender", i, op.bl_label)) for i, op in enumerate(ops) if repeatable(op.bl_idname)]
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
        return {'FINISHED'}


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
