# SPDX-License-Identifier: GPL-3.0-or-later
"""Channel Box in component mode: the selected points' rows.

Maya 2022: with
points selected the Channel Box shows the shape's name, a ``CVs (click to show)`` line and INPUTS; a click on that
line shows a table — one row per selected point (its index, X, Y, Z) — and the line reads ``CVs (click to hide)``.
The table stays open for the next selection. Edges / faces selected: no CVs line.

Maya's values are the point tweaks (``pnts``, 0 on an untweaked cube); Blender keeps no tweak layer, so the rows
show the vertex positions in object space, in display units, and typing moves the vertex (relative entry ``+=1``
works like Maya's).

A lattice in edit mode shows its selected points the same way, by their point number, with their positions in the
lattice's own space (a unit cube, -0.5 .. 0.5: plain numbers, not lengths).
"""

import bmesh
import bpy
from bpy.props import BoolProperty, StringProperty

from . import cb_entry

MAX_POINTS = 64      # rows with text fields; more selected points get a "+N" line
AXES = "xyz"

_state = {"points": []}     # the drawn point indices, in vertex order (getters read them; module state, not ID data)


def edit_mesh(ob):
    if ob is None or ob.type != 'MESH' or ob.mode != 'EDIT':
        return None
    try:
        return bmesh.from_edit_mesh(ob.data)
    except (ValueError, RuntimeError, ReferenceError):
        return None


def edit_lattice(ob):
    if ob is None or ob.type != 'LATTICE' or ob.mode != 'EDIT':
        return None
    return ob.data


def selected_points(ob):
    """Indices of the selected vertices of ``ob``'s edit mesh / selected points of its edit lattice ([] when
    neither is in edit mode)."""
    lt = edit_lattice(ob)
    if lt is not None:
        return [i for i, p in enumerate(lt.points) if p.select]
    bm = edit_mesh(ob)
    if bm is None:
        return []
    return [v.index for v in bm.verts if v.select]


def points_shown(ob):
    """Maya's CVs line: points (vertex mode) are selected — not edges / faces."""
    if edit_lattice(ob) is not None:
        return any(p.select for p in ob.data.points)
    if ob is None or ob.type != 'MESH':
        return False
    vert, _edge, _face = bpy.context.tool_settings.mesh_select_mode
    return vert and _count(ob) > 0


def _count(ob):
    # Mesh.total_vert_sel reads the edit BMesh's count in edit mode: no Python loop over the vertices per redraw
    return ob.data.total_vert_sel if ob.mode == 'EDIT' else 0


def has_selection(ob):
    """Something selected in component mode (Maya: nothing selected = the empty Channel Box)."""
    if ob is None:
        return False
    if ob.type == 'MESH':
        return _count(ob) > 0
    data = ob.data
    if ob.type in {'CURVE', 'SURFACE'}:
        return any(p.select for s in data.splines for p in s.points) or any(
            p.select_control_point for s in data.splines for p in s.bezier_points)
    if ob.type == 'LATTICE':
        return any(p.select for p in data.points)
    return True


def _value(slot, axis):
    """(object, point coordinates (a vector), value kind) of the table row ``slot``, or (None, None, None)."""
    from . import channel_box
    ob = channel_box.lead()
    pts = _state["points"]
    if slot >= len(pts):
        return None, None, None
    lt = edit_lattice(ob)
    if lt is not None:
        if pts[slot] >= len(lt.points):
            return None, None, None
        return ob, lt.points[pts[slot]].co_deform, "NONE"
    bm = edit_mesh(ob)
    if bm is None:
        return None, None, None
    bm.verts.ensure_lookup_table()
    if pts[slot] >= len(bm.verts):
        return None, None, None
    return ob, bm.verts[pts[slot]].co, "LENGTH"


def _get(slot, axis):
    def get(_self):
        _ob, co, kind = _value(slot, axis)
        if co is None:
            return ""
        return cb_entry.format_value(co[AXES.index(axis)], kind, bpy.context.scene)
    return get


def _set(slot, axis):
    def set_(_self, text):
        ob, co, kind = _value(slot, axis)
        if co is None:
            return
        i = AXES.index(axis)
        try:
            value = cb_entry.parse_entry(text, co[i], kind, bpy.context.scene)
        except (ValueError, TypeError, SyntaxError, NameError):
            return
        co[i] = value
        if ob.type == 'LATTICE':
            ob.data.update_tag()
            ob.update_tag()
        else:
            bmesh.update_edit_mesh(ob.data, loop_triangles=True, destructive=False)
    return set_


class ALLSET_PG_cb_points(bpy.types.PropertyGroup):
    __annotations__ = {f"p{slot}_{axis}": StringProperty(name=axis.upper(), get=_get(slot, axis),
                                                         set=_set(slot, axis), options={'SKIP_SAVE'})
                       for slot in range(MAX_POINTS) for axis in AXES}


class ALLSET_OT_cb_points_toggle(bpy.types.Operator):
    """Show or hide the selected points' values (Maya: click the CVs line)"""
    bl_idname = "allset.cb_points_toggle"
    bl_label = "CVs"
    bl_options = {'INTERNAL'}       # UI state, no undo step (Maya)

    def execute(self, context):
        wm = context.window_manager
        wm.allset_cb_points = not wm.allset_cb_points
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'PROPERTIES':
                    area.tag_redraw()
        return {'FINISHED'}


def draw(lines, context, ob):
    """The CVs line and, when open, the table (header + one line per selected point)."""
    if not points_shown(ob):
        return
    wm = context.window_manager
    opened = wm.allset_cb_points
    r = lines.row()
    if r is not None:
        name = r.row(align=True)
        name.alignment = 'LEFT'
        name.operator(ALLSET_OT_cb_points_toggle.bl_idname,
                      text="CVs (click to hide)" if opened else "CVs (click to show)", emboss=False)
    if not opened:
        return
    pts = selected_points(ob)
    _state["points"] = pts[:MAX_POINTS]
    r = lines.row()
    if r is not None:
        split = r.split(factor=0.16, align=True)
        split.label(text="")
        cols = split.row(align=True)
        for axis in AXES:
            cols.label(text=axis.upper())
    props = context.scene.allset_cb_points
    for slot, index in enumerate(_state["points"]):
        r = lines.row()
        if r is None:
            continue
        split = r.split(factor=0.16, align=True)
        split.label(text=str(index))
        cols = split.row(align=True)
        for axis in AXES:
            cols.prop(props, f"p{slot}_{axis}", text="")
    if len(pts) > MAX_POINTS:
        r = lines.row()
        if r is not None:
            r.active = False
            r.label(text=f"+{len(pts) - MAX_POINTS}")


classes = (ALLSET_PG_cb_points, ALLSET_OT_cb_points_toggle)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # Scene, not WindowManager: UI edits of WM properties push no undo step
    bpy.types.Scene.allset_cb_points = bpy.props.PointerProperty(type=ALLSET_PG_cb_points)
    bpy.types.WindowManager.allset_cb_points = BoolProperty(name="CVs Shown", options={'SKIP_SAVE'})


def unregister():
    _state["points"] = []
    del bpy.types.WindowManager.allset_cb_points
    del bpy.types.Scene.allset_cb_points
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
