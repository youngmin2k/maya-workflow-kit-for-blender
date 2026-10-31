# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya click / marquee modifiers in the Graph Editor, Dope Sheet and UV Editor.

Maya (Graph Editor / Dope Sheet / Outliner clicks): marquee Shift = toggle (XOR), Ctrl =
deselect, Ctrl+Shift = add, in all three; a click: Shift = toggle, Ctrl+Shift = add (never removes); Ctrl =
deselect in the Dope Sheet and UV Editor, but in the Graph Editor Ctrl+click acts like a plain click, and a plain
click on an already selected key keeps the selection (so several keys drag together).

Blender has toggle / SUB / ADD but no XOR box in these editors and no "add only" / "deselect" click there, so a
first-place operator per variant snapshots the selection, lets Blender's own selection run (clicks: called from here
with Blender's toggle; boxes: the keymap's own item runs after this one passes through, as mode SET) and then writes
the Maya result from the before / after states. The rules are pure set functions (``RULES``) so tests check them
without a mouse.
"""

import bpy
from bpy.props import EnumProperty

from .. import compat

EDITORS = {   # editor -> (area type, click operator, box operator bl_idname as listed in Window.modal_operators)
    'OUTLINER': ('OUTLINER', "outliner.item_activate", "OUTLINER_OT_select_box"),
    'GRAPH': ('GRAPH_EDITOR', "graph.clickselect", "GRAPH_OT_select_box"),
    'DOPE': ('DOPESHEET_EDITOR', "action.clickselect", "ACTION_OT_select_box"),
    'UV': ('IMAGE_EDITOR', "uv.select", "UV_OT_select_box"),
}


# --- the Maya rules on before / after selections -------------------------------------------------------------------

def rule_xor(before, after):
    """Marquee Shift: Blender ran the box as SET, so ``after`` = what the box caught; Maya toggles those."""
    return before ^ after


def rule_add(before, after):
    """Ctrl+Shift click: Blender toggled the clicked item; Maya only ever adds."""
    return before | after


def rule_deselect(before, after):
    """Ctrl click: Blender toggled the clicked item (the one that changed); Maya deselects it."""
    return before - (before ^ after)


def rule_keep(before, after):
    """Graph Editor plain / Ctrl click: Blender replaced the selection with the clicked key; on a key that was already
    selected Maya keeps the whole selection, elsewhere the replace stands."""
    if after and after <= before:
        return before
    return after


RULES = {'XOR': rule_xor, 'ADD': rule_add, 'DESELECT': rule_deselect, 'KEEP': rule_keep}


def rule_outliner_toggle(before, after, clicked):
    """Outliner Ctrl+click (Maya: a Qt toggle). Blender's extend click deselects only the active item; on a selected
    item that isn't active it just makes it active — Maya deselects it."""
    if clicked is not None and clicked in before and clicked in after:
        return after - {clicked}
    return after


# --- object selection (Outliner) -----------------------------------------------------------------------------------

def object_state():
    vl = bpy.context.view_layer
    return frozenset(o.name for o in vl.objects if o is not None and o.select_get())


def set_object_state(selected):
    for o in bpy.context.view_layer.objects:
        if o is not None and o.select_get() != (o.name in selected):
            o.select_set(o.name in selected)


# --- keyframe selection (Graph Editor / Dope Sheet) ----------------------------------------------------------------

_ANIM_COLLECTIONS = ("objects", "meshes", "shape_keys", "materials", "cameras", "lights", "scenes", "worlds",
                     "node_groups", "armatures", "curves", "lattices", "textures")


def _fcurves():
    seen = set()
    for name in _ANIM_COLLECTIONS:
        for idb in getattr(bpy.data, name, ()):
            for fc in compat.id_fcurves(idb):
                if fc.as_pointer() not in seen:
                    seen.add(fc.as_pointer())
                    yield fc


def key_items():
    """{(fcurve pointer, key index): keyframe point} for every key of the file's animation."""
    return {(fc.as_pointer(), i): kp for fc in _fcurves() for i, kp in enumerate(fc.keyframe_points)}


def key_state(items=None):
    items = key_items() if items is None else items
    return frozenset(k for k, kp in items.items() if kp.select_control_point)


def set_key_state(selected, items=None):
    items = key_items() if items is None else items
    for k, kp in items.items():
        on = k in selected
        if kp.select_control_point != on:
            kp.select_control_point = on
        if not on:
            kp.select_left_handle = kp.select_right_handle = False


# --- UV selection (UV Editor) ---------------------------------------------------------------------------------------

def _edit_meshes():
    for ob in bpy.context.scene.objects if bpy.context.scene else ():
        if ob.type == 'MESH' and ob.mode == 'EDIT':
            yield ob


def _bmesh(ob):
    import bmesh
    return bmesh.from_edit_mesh(ob.data)


def uv_sync():
    ts = bpy.context.scene.tool_settings if bpy.context.scene else None
    return bool(ts and ts.use_uv_select_sync)


def uv_state():
    """UV Editor selection: (object, loop index) of selected UV corners; with UV sync on, (object, vertex index)."""
    out = set()
    for ob in _edit_meshes():
        bm = _bmesh(ob)
        if uv_sync():
            out.update((ob.name, v.index) for v in bm.verts if v.select)
            continue
        uv = bm.loops.layers.uv.active
        if uv is None:
            continue
        for f in bm.faces:
            for loop in f.loops:
                if compat.uv_vert_selected(loop, uv):
                    out.add((ob.name, loop.index))
    return frozenset(out)


def set_uv_state(selected):
    import bmesh
    for ob in _edit_meshes():
        bm = _bmesh(ob)
        if uv_sync():
            for v in bm.verts:
                v.select = (ob.name, v.index) in selected
            bm.select_flush(True)
            bm.select_flush(False)
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
            continue
        uv = bm.loops.layers.uv.active
        if uv is None:
            continue
        for f in bm.faces:
            for loop in f.loops:
                compat.set_uv_vert_selected(loop, uv, (ob.name, loop.index) in selected)
        for f in bm.faces:                    # an edge is selected when both of its corners are
            for loop in f.loops:
                on = compat.uv_vert_selected(loop, uv) and compat.uv_vert_selected(loop.link_loop_next, uv)
                compat.set_uv_edge_selected(loop, uv, on)
        bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)


def state(editor):
    if editor == 'OUTLINER':
        return object_state()
    return uv_state() if editor == 'UV' else key_state()


def set_state(editor, selected):
    if editor == 'OUTLINER':
        set_object_state(selected)
    elif editor == 'UV':
        set_uv_state(selected)
    else:
        set_key_state(selected)


def _redraw(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in ('GRAPH_EDITOR', 'DOPESHEET_EDITOR', 'IMAGE_EDITOR', 'VIEW_3D'):
                area.tag_redraw()


# --- clicks ------------------------------------------------------------------------------------------------------------

_EDITOR_ITEMS = [(k, k.title(), "") for k in EDITORS]
_RULE_ITEMS = [(k, k.title(), "") for k in ('ADD', 'DESELECT', 'KEEP', 'CTRL', 'TOGGLE')]


def rule_ctrl(before, after):
    """Graph Editor Ctrl click: like a plain click on a key; on empty space the selection stays."""
    return before if not after else rule_keep(before, after)


RULES['CTRL'] = rule_ctrl


def _finish_click():
    p = _PENDING.pop("click", None)
    if p is None:
        return None
    # every rule leaves an unchanged selection alone, so a press nothing selected with needs no check
    after = state(p["editor"])
    if p["rule"] == 'TOGGLE':
        active = bpy.context.view_layer.objects.active
        final = rule_outliner_toggle(p["before"], after, active.name if active is not None else None)
    else:
        final = RULES[p["rule"]](p["before"], after)
    if final != after:
        set_state(p["editor"], final)
        try:
            _redraw(bpy.context)
        except AttributeError:
            pass
    return None


class ALLSET_OT_select_2d_click(bpy.types.Operator):
    """Maya click modifiers in this editor (Ctrl+Shift adds, Ctrl deselects; a Graph Editor click on a selected key
    keeps the selection): remembers the selection, lets Blender's click run (the press stays free for a drag), then
    writes Maya's result"""
    bl_idname = "allset.select_2d_click"
    bl_label = "Maya Click Select"
    bl_options = {'INTERNAL'}

    editor: EnumProperty(items=_EDITOR_ITEMS, options={'SKIP_SAVE'})
    rule: EnumProperty(items=_RULE_ITEMS, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        area_type, _click, _box = EDITORS[self.editor]
        if context.area is None or context.area.type != area_type:
            return {'PASS_THROUGH'}
        _PENDING["click"] = {"editor": self.editor, "rule": self.rule, "before": state(self.editor)}
        if not bpy.app.timers.is_registered(_finish_click):
            bpy.app.timers.register(_finish_click, first_interval=0.0)
        return {'PASS_THROUGH'}


# --- boxes (Shift = XOR) ------------------------------------------------------------------------------------------------

_PENDING = {}


def _last_pointer(wm):
    return wm.operators[-1].as_pointer() if len(wm.operators) else 0


def _modal_running(wm, idname):
    return any(op.bl_idname == idname for win in wm.windows for op in win.modal_operators)


def _finish_box():
    p = _PENDING.get("box")
    if p is None:
        return None
    wm = bpy.context.window_manager
    if p["started"] is False:
        last = wm.operators[-1].as_pointer() if len(wm.operators) else 0
        p["started"] = _modal_running(wm, p["idname"]) or last != p["last"]
        p["ticks"] += 1
        if not p["started"] and p["ticks"] < 40:
            return 0.02
    if _modal_running(wm, p["idname"]):
        return 0.02
    _PENDING.pop("box", None)
    last = wm.operators[-1] if len(wm.operators) else None
    if last is None or last.as_pointer() == p["last"] or last.bl_idname != p["idname"]:
        return None                                     # cancelled / a tweak moved keys instead: leave it
    after = state(p["editor"])
    final = rule_xor(p["before"], after)
    if final != after:
        set_state(p["editor"], final)
        try:
            _redraw(bpy.context)
        except AttributeError:
            pass
    return None


class ALLSET_OT_select_2d_box(bpy.types.Operator):
    """Maya Shift+marquee = toggle: remembers the selection, Blender's box (mode Set) runs, then the box's items are
    toggled against what was selected"""
    bl_idname = "allset.select_2d_box"
    bl_label = "Maya Marquee Toggle"
    bl_options = {'INTERNAL'}

    editor: EnumProperty(items=_EDITOR_ITEMS, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        area_type, _click, box = EDITORS[self.editor]
        if context.area is None or context.area.type != area_type:
            return {'PASS_THROUGH'}
        if self.editor == 'UV' and getattr(context.space_data, "mode", 'UV') != 'UV':
            return {'PASS_THROUGH'}
        _PENDING["box"] = {"editor": self.editor, "before": state(self.editor), "idname": box,
                           "last": _last_pointer(context.window_manager), "started": False, "ticks": 0}
        if not bpy.app.timers.is_registered(_finish_box):
            bpy.app.timers.register(_finish_box, first_interval=0.02)
        return {'PASS_THROUGH'}


classes = (ALLSET_OT_select_2d_click, ALLSET_OT_select_2d_box)


def unregister_timers():
    _PENDING.clear()
    for fn in (_finish_box, _finish_click):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
