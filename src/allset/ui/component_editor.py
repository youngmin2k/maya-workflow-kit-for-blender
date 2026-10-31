# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Component Editor window (Issue #119).

Maya 2022: menu bar Options /
Layout / Help, a tab bar (CE2), a table — Smooth Skins: one column per skinCluster influence + Total, a Hold row, a
shape row, one row per selected vertex (CE3); Polygons: vertex.x / y / z (+ red / green / blue) in object space (CE6) —
and the bottom row "Auto Normalization: Interactive", Load Components / Close (CE4).

Blender: a ``marked_window`` kind "COMPONENT_EDITOR" (a Properties Tool tab in its own window) drawn by
``ALLSET_PT_component_editor``. The cells are Scene proxies (``Scene.allset_ce``: UI edits of Scene properties push undo
steps) whose get / set read and write the live mesh: positions ÷ ``units.maya_unit()`` (Maya units),
weights through ``skin_tools_199._Weights`` with Maya's Interactive normalisation (``normalize``, CE5). The proxy rows
follow the selection from a depsgraph handler → timer while Auto Update is on (CE7); never written in ``draw``.
"""

import bmesh
import bpy
import numpy as np
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from . import marked_window

KIND = "COMPONENT_EDITOR"
EDITOR = "Component Editor"
MAX_ROWS = 1000                 # proxies made per load (a whole dense mesh selected would stall the UI)
POS = ("x", "y", "z")
COLOR = ("r", "g", "b")
POS_LABELS = ("vertex.x", "vertex.y", "vertex.z")
COLOR_LABELS = ("red", "green", "blue")

# CE2: Maya's tabs in order; only Smooth Skins and Polygons have a Blender meaning here.
TABS = (("SPRINGS", "Springs"), ("PARTICLES", "Particles"), ("WEIGHTED_DEFORMER", "Weighted Deformer"),
        ("RIGID_SKINS", "Rigid Skins"), ("BLENDSHAPE", "BlendShape Deformers"), ("SMOOTH_SKINS", "Smooth Skins"),
        ("POLYGONS", "Polygons"), ("ADV_POLYGONS", "AdvPolygons"))
WORKING = {"SMOOTH_SKINS", "POLYGONS"}


def _skin():
    from ..operators import skin_tools_199
    return skin_tools_199


def _unit(scene):
    from ..operators import units
    return units.maya_unit(scene)


# --- CE5: Maya's Interactive normalisation (pure) -------------------------------------------------------------------

def normalize(weights, index, value, locked=()):
    """Weights after setting influence ``index`` to ``value`` (skinPercent -transformValue, normalizeWeights 1): the
    unheld others are scaled to fill 1 − value, held (``locked``) ones keep theirs (Maya:
    [0.8, 0.2, 0] j1 = 0.5 → [0.5, 0.5, 0]; [0.5, 0.5, 0] j3 = 0.3 → [0.35, 0.35, 0.3]).

    Edge cases: value is clamped to [0, 1 − held]; when the unheld others weigh nothing the rest is shared equally by
    them; with no unheld other only the edited weight changes."""
    w = [float(x) for x in weights]
    value = min(max(float(value), 0.0), 1.0)
    held = {k for k in locked if k != index}
    others = [k for k in range(len(w)) if k != index and k not in held]
    if not others:
        w[index] = value
        return w
    rest_total = max(0.0, 1.0 - sum(w[k] for k in held))
    value = min(value, rest_total)
    rest = rest_total - value
    cur = sum(w[k] for k in others)
    for k in others:
        w[k] = w[k] * rest / cur if cur > 1e-12 else rest / len(others)
    w[index] = value
    return w


def cell_text(value):
    """3-decimal cells, like Maya's."""
    return f"{value:.3f}"


# --- reading the live data (no writes: safe in draw / getters) ------------------------------------------------------

def _edit_bm(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    return bm


def meshes(context):
    """Shown meshes, the active one first: the objects in edit mode, else the selected mesh objects."""
    vl = context.view_layer
    act = vl.objects.active
    obs = [o for o in vl.objects if o is not None]
    if act is not None and act.mode == 'EDIT':
        pick = [o for o in obs if o.type == 'MESH' and o.mode == 'EDIT']
    else:
        pick = [o for o in obs if o.type == 'MESH' and o.select_get()]
    if act is not None and act in pick:
        pick.remove(act)
        pick.insert(0, act)
    out, seen = [], set()
    for o in pick:
        if o.data not in seen:
            seen.add(o.data)
            out.append(o)
    return out


def selected_verts(ob):
    """Selected vertex indices in index order (edit mode: the BMesh selection)."""
    if ob.mode == 'EDIT':
        return [v.index for v in _edit_bm(ob).verts if v.select]
    me = ob.data
    sel = np.zeros(len(me.vertices), dtype=bool)
    me.vertices.foreach_get("select", sel)
    return np.flatnonzero(sel).tolist()


def influences(ob):
    """Maya skinCluster influences of ``ob`` (vertex groups that are bones of its skeleton), [] if not skinned."""
    return _skin().influence_names(ob)


def _group_weights(ob, vi):
    """{group index: weight} of vertex ``vi``."""
    if ob.mode == 'EDIT':
        bm = _edit_bm(ob)
        layer = bm.verts.layers.deform.active
        return dict(bm.verts[vi][layer].items()) if layer is not None else {}
    return {g.group: g.weight for g in ob.data.vertices[vi].groups}


def weight(ob, vi, name):
    vg = ob.vertex_groups.get(name)
    return _group_weights(ob, vi).get(vg.index, 0.0) if vg is not None else 0.0


def position(ob, vi, axis, scene):
    co = _edit_bm(ob).verts[vi].co if ob.mode == 'EDIT' else ob.data.vertices[vi].co
    return co["xyz".index(axis)] / _unit(scene)


def color_attribute(ob):
    """The mesh's active colour attribute when it is per vertex (Maya colour per vertex), else None."""
    attr = ob.data.color_attributes.active_color
    return attr if attr is not None and attr.domain == 'POINT' else None


def _color_layer(ob, attr):
    bm = _edit_bm(ob)
    layers = bm.verts.layers.float_color if attr.data_type == 'FLOAT_COLOR' else bm.verts.layers.color
    return bm, layers.get(attr.name)


def color(ob, vi, channel):
    attr = color_attribute(ob)
    if attr is None:
        return 0.0
    k = COLOR.index(channel)
    if ob.mode == 'EDIT':
        bm, layer = _color_layer(ob, attr)
        return bm.verts[vi][layer][k] if layer is not None else 0.0
    return attr.data[vi].color[k]


def table(context, tab, hide_zero=True):
    """The table Maya draws on ``tab`` from the current selection (pure read): {"columns": [...], "hold": [bool per
    influence column], "shapes": [(shape name, [{"label": "vtx[i]", "index": i, "values": [...]}, ...]), ...]}.
    A value is None where a mesh has no such column."""
    scene = context.scene
    shapes = []
    if tab == "SMOOTH_SKINS":
        cols, hold = [], {}
        for ob in meshes(context):
            names = influences(ob)
            if not names:
                continue
            for n in names:
                if n not in cols:
                    cols.append(n)
                hold[n] = hold.get(n, False) or ob.vertex_groups[n].lock_weight
            rows = []
            for vi in selected_verts(ob):
                gw = _group_weights(ob, vi)
                vals = [gw.get(ob.vertex_groups[n].index, 0.0) if n in names else None for n in cols]
                rows.append({"label": f"vtx[{vi}]", "index": vi, "values": vals})
            shapes.append((ob, rows))
        if hide_zero:
            cols = [n for k, n in enumerate(cols)
                    if any((r["values"][k] if k < len(r["values"]) else None) for _ob, rows in shapes for r in rows)]
        out = []
        for ob, rows in shapes:
            names = influences(ob)
            for r in rows:
                gw = _group_weights(ob, r["index"])
                ws = [gw.get(ob.vertex_groups[n].index, 0.0) if n in names else None for n in cols]
                total = sum(gw.get(ob.vertex_groups[n].index, 0.0) for n in names)
                r["values"] = ws + [total]
            out.append((ob.data.name, rows))
        return {"columns": cols + ["Total"], "hold": [hold.get(n, False) for n in cols], "shapes": out}
    if tab == "POLYGONS":
        obs = meshes(context)
        with_color = any(color_attribute(ob) is not None for ob in obs)
        cols = list(POS_LABELS) + (list(COLOR_LABELS) if with_color else [])
        for ob in obs:
            rows = []
            has = color_attribute(ob) is not None
            for vi in selected_verts(ob):
                vals = [position(ob, vi, a, scene) for a in POS]
                if with_color:
                    vals += [color(ob, vi, c) if has else None for c in COLOR]
                rows.append({"label": f"vtx[{vi}]", "index": vi, "values": vals})
            shapes.append((ob.data.name, rows))
        return {"columns": cols, "hold": [], "shapes": shapes}
    return {"columns": [], "hold": [], "shapes": []}


# --- writing ------------------------------------------------------------------------------------------------------

def set_weight(ob, vi, name, value):
    """Set influence ``name`` of vertex ``vi`` with Maya's Interactive normalisation over the skin's influences."""
    names = influences(ob)
    if name not in names:
        return False
    groups = [ob.vertex_groups[n] for n in names]
    w = _skin()._Weights(ob)
    cur = [w.get(vi, g.index) for g in groups]
    locked = {k for k, g in enumerate(groups) if g.lock_weight}
    new = normalize(cur, names.index(name), value, locked)
    for g, x in zip(groups, new):
        w.set(vi, g.index, x)
    w.flush()
    return True


def set_position(ob, vi, axis, value, scene):
    k = "xyz".index(axis)
    v = value * _unit(scene)
    if ob.mode == 'EDIT':
        bm = _edit_bm(ob)
        bm.verts[vi].co[k] = v
        bmesh.update_edit_mesh(ob.data, loop_triangles=True, destructive=False)
    else:
        ob.data.vertices[vi].co[k] = v
        ob.data.update()


def set_color(ob, vi, channel, value):
    attr = color_attribute(ob)
    if attr is None:
        return
    k = COLOR.index(channel)
    if ob.mode == 'EDIT':
        bm, layer = _color_layer(ob, attr)
        if layer is not None:
            c = bm.verts[vi][layer]
            c[k] = value
            bm.verts[vi][layer] = c
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
    else:
        c = list(attr.data[vi].color)
        c[k] = value
        attr.data[vi].color = c
        ob.data.update()


# --- Scene proxies ------------------------------------------------------------------------------------------------

def _cell_get(self):
    ob = bpy.data.objects.get(self.ob)
    if ob is None or ob.type != 'MESH' or self.vert >= len(ob.data.vertices):
        return 0.0
    try:
        if self.kind == 'POS':
            return position(ob, self.vert, self.col, self.id_data)
        if self.kind == 'COLOR':
            return color(ob, self.vert, self.col)
        return weight(ob, self.vert, self.col)
    except (IndexError, ReferenceError, ValueError):
        return 0.0


def _cell_set(self, value):
    ob = bpy.data.objects.get(self.ob)
    if ob is None or ob.type != 'MESH' or self.vert >= len(ob.data.vertices):
        return
    if self.kind == 'POS':
        set_position(ob, self.vert, self.col, value, self.id_data)
    elif self.kind == 'COLOR':
        set_color(ob, self.vert, self.col, value)
    else:
        set_weight(ob, self.vert, self.col, value)


def _hold_get(self):
    ob = bpy.data.objects.get(self.ob)
    vg = ob.vertex_groups.get(self.col) if ob is not None else None
    return vg is not None and vg.lock_weight


def _hold_set(self, value):
    ob = bpy.data.objects.get(self.ob)
    vg = ob.vertex_groups.get(self.col) if ob is not None else None
    if vg is not None:
        vg.lock_weight = value


class ALLSET_PG_ce_cell(bpy.types.PropertyGroup):
    ob: StringProperty()
    vert: IntProperty()
    kind: StringProperty()                 # POS / COLOR / WEIGHT
    col: StringProperty()                  # x y z / r g b / influence name
    value: FloatProperty(name="Value", get=_cell_get, set=_cell_set, precision=3, step=1,
                         description="Component Editor cell")


class ALLSET_PG_ce_hold(bpy.types.PropertyGroup):
    ob: StringProperty()
    col: StringProperty()
    value: BoolProperty(name="Hold", get=_hold_get, set=_hold_set,
                        description="Maya Hold: this influence's weights stay when others are edited")


class ALLSET_PG_ce(bpy.types.PropertyGroup):
    cells: CollectionProperty(type=ALLSET_PG_ce_cell)
    holds: CollectionProperty(type=ALLSET_PG_ce_hold)
    sig: StringProperty()


def signature(context):
    """What the proxy rows depend on: shown meshes, their selected vertices, influences and colour attribute."""
    parts = []
    for ob in meshes(context):
        attr = color_attribute(ob)
        parts.append((ob.name, ob.mode, hash(tuple(selected_verts(ob))), tuple(influences(ob)),
                      attr.name if attr is not None else ""))
    return str(hash(tuple(parts)))


def needs_rebuild(context):
    return context.scene.allset_ce.sig != signature(context)


def rebuild(context):
    """Load the selected components into the proxies (Maya Load Components)."""
    state = context.scene.allset_ce
    state.cells.clear()
    state.holds.clear()
    n = 0
    for ob in meshes(context):
        names = influences(ob)
        for name in names:
            h = state.holds.add()
            h.ob, h.col = ob.name, name
        kinds = [('POS', a) for a in POS]
        if color_attribute(ob) is not None:
            kinds += [('COLOR', c) for c in COLOR]
        kinds += [('WEIGHT', name) for name in names]
        for vi in selected_verts(ob):
            if n >= MAX_ROWS:
                break
            n += 1
            for kind, col in kinds:
                c = state.cells.add()
                c.ob, c.vert, c.kind, c.col = ob.name, vi, kind, col
    state.sig = signature(context)
    marked_window.redraw(context, KIND)


def cell(scene, ob_name, vi, col):
    """The proxy of (object, vertex, column) — column = x / y / z, r / g / b or an influence name; None if not loaded."""
    found = None
    for c in scene.allset_ce.cells:
        if c.ob == ob_name and c.vert == vi and c.col == col:
            if c.kind == 'POS' or found is None:
                found = c
    return found


def hold(scene, ob_name, name):
    return next((h for h in scene.allset_ce.holds if h.ob == ob_name and h.col == name), None)


# --- Auto Update (CE7) ----------------------------------------------------------------------------------------------
_pending = {"timer": False}


def _is_open(context):
    return marked_window.find_window(context, KIND) is not None


def _tick():
    _pending["timer"] = False
    context = bpy.context
    try:
        if context.window_manager.allset_ce_auto_update and _is_open(context) and needs_rebuild(context):
            rebuild(context)
    except (AttributeError, ReferenceError, RuntimeError):
        pass
    return None


@persistent
def _on_depsgraph(scene, _depsgraph=None):
    if _pending["timer"]:
        return
    wm = bpy.context.window_manager
    if wm is None or not getattr(wm, "allset_ce_auto_update", False) or not _is_open(bpy.context):
        return
    _pending["timer"] = True
    bpy.app.timers.register(_tick, first_interval=0.0)


# --- operators ------------------------------------------------------------------------------------------------------

class ALLSET_OT_component_editor(bpy.types.Operator):
    """Open the Component Editor: the selected vertices' skin weights and positions as an editable table
    (Maya Windows > General Editors > Component Editor)"""
    bl_idname = "allset.component_editor"
    bl_label = "Component Editor"

    def execute(self, context):
        if context.window is None:
            return {'CANCELLED'}
        rebuild(context)
        if marked_window.open_window(context, KIND) is None:
            from . import window_places
            if not window_places.deferred():     # opens on a later tick (#203)
                self.report({'ERROR'}, "Could not open the Component Editor window")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_ce_load(bpy.types.Operator):
    """Load the selected components into the Component Editor (Maya Load Components)"""
    bl_idname = "allset.ce_load"
    bl_label = "Load Components"
    bl_options = {'UNDO'}

    def execute(self, context):
        rebuild(context)
        return {'FINISHED'}


class ALLSET_OT_ce_close(bpy.types.Operator):
    """Close the Component Editor window"""
    bl_idname = "allset.ce_close"
    bl_label = "Close"

    def execute(self, context):
        from . import maya_dock
        window = context.window
        if window is None or not any(marked_window.kind_of(a) == KIND for a in window.screen.areas):
            window = marked_window.find_window(context, KIND)
        if window is not None:
            maya_dock.close_window_later(window)
        return {'FINISHED'}


# --- the window's panel ---------------------------------------------------------------------------------------------

def _grid(context, tab, hide_zero):
    """(columns [(key, label)], shapes [(object, [(vi, {col: cell})])]) from the loaded proxies."""
    state = context.scene.allset_ce
    by_ob = {}
    for c in state.cells:
        by_ob.setdefault(c.ob, {}).setdefault(c.vert, {})[c.col if c.kind != 'POS' else "pos:" + c.col] = c
    shapes = []
    for name, verts in by_ob.items():
        ob = bpy.data.objects.get(name)
        if ob is not None and ob.type == 'MESH':
            shapes.append((ob, sorted(verts.items())))
    if tab == "POLYGONS":
        cols = [("pos:" + a, lab) for a, lab in zip(POS, POS_LABELS)]
        if any("r" in row for _ob, rows in shapes for _vi, row in rows):
            cols += list(zip(COLOR, COLOR_LABELS))
        return cols, shapes
    cols = []
    skinned = []
    for ob, rows in shapes:
        names = influences(ob)
        if not names:
            continue
        skinned.append((ob, rows))
        cols += [(n, n) for n in names if (n, n) not in cols]
    if hide_zero:
        cols = [(k, lab) for k, lab in cols
                if any(row[k].value > 0.0 for _ob, rows in skinned for _vi, row in rows if k in row)]
    return cols, skinned


def _label(row, text, units=4.5):
    sub = row.row(align=True)
    sub.ui_units_x = units
    sub.label(text=text)


def draw_table(layout, context, tab, hide_zero):
    if tab not in WORKING:
        layout.label(text="")       # Maya: an empty table on the tabs without a Blender meaning
        return
    cols, shapes = _grid(context, tab, hide_zero)
    box = layout.box()
    col = box.column(align=True)
    if not shapes:
        col.label(text="Select components, then Load Components")
        return
    head = col.row(align=True)
    _label(head, "")
    for _k, lab in cols:
        head.label(text=lab)
    if tab == "SMOOTH_SKINS":
        head.label(text="Total")
    state = context.scene.allset_ce
    for ob, rows in shapes:
        if tab == "SMOOTH_SKINS":
            line = col.row(align=True)
            _label(line, "Hold")
            for k, _lab in cols:
                h = next((h for h in state.holds if h.ob == ob.name and h.col == k), None)
                if h is None:
                    line.label(text="")
                else:
                    line.prop(h, "value", text="on" if h.value else "off", toggle=True)
            line.label(text="")
        shape = col.row(align=True)
        _label(shape, ob.data.name, units=8)
        for vi, row in rows:
            line = col.row(align=True)
            _label(line, f"  vtx[{vi}]")
            total = 0.0
            for k, _lab in cols:
                c = row.get(k)
                if c is None:
                    line.label(text="")
                else:
                    line.prop(c, "value", text="")
            if tab == "SMOOTH_SKINS":
                names = influences(ob)
                total = sum(row[n].value for n in names if n in row)
                line.label(text=cell_text(total))


class ALLSET_PT_component_editor(bpy.types.Panel):
    """Maya's Component Editor (a marked Properties Tool tab in its own window)"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"            # = drawn by the Properties Tool tab (like the Tool Settings dock)
    bl_label = "Component Editor"
    bl_options = {'HIDE_HEADER'}
    bl_order = -300

    @classmethod
    def poll(cls, context):
        return marked_window.context_kind(context) == KIND

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        marked_window.draw_menu_bar(layout, context, EDITOR)
        tabs = layout.row(align=True)
        for key, label in TABS:
            sub = tabs.row(align=True)
            sub.enabled = key in WORKING
            sub.prop_enum(wm, "allset_ce_tab", key, text=label)
        draw_table(layout, context, wm.allset_ce_tab, wm.allset_ce_hide_zero)
        bottom = layout.row()
        bottom.alignment = 'RIGHT'
        bottom.label(text="Auto Normalization:")
        bottom.label(text="Interactive")
        buttons = layout.row(align=True)
        buttons.operator("allset.ce_load", text="Load Components")
        buttons.operator("allset.ce_close", text="Close")


classes = (ALLSET_PG_ce_cell, ALLSET_PG_ce_hold, ALLSET_PG_ce, ALLSET_OT_component_editor, ALLSET_OT_ce_load,
           ALLSET_OT_ce_close, ALLSET_PT_component_editor)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.allset_ce = bpy.props.PointerProperty(type=ALLSET_PG_ce)
    wm = bpy.types.WindowManager
    wm.allset_ce_auto_update = BoolProperty(name="Auto Update", default=True,
                                            description="Reload the Component Editor when the selection changes")
    wm.allset_ce_hide_zero = BoolProperty(name="Hide Zero Columns", default=True,
                                          description="Hide influences that weigh nothing on the shown vertices")
    wm.allset_ce_tab = EnumProperty(name="Component Editor Tab", items=[(k, lab, "") for k, lab in TABS],
                                    default="SMOOTH_SKINS")
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister():
    while _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _pending["timer"] = False
    for name in ("allset_ce_auto_update", "allset_ce_hide_zero", "allset_ce_tab"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    if hasattr(bpy.types.Scene, "allset_ce"):
        del bpy.types.Scene.allset_ce
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
