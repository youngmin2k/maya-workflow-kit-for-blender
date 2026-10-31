# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Shape Editor window (Issue #119).

Maya: menu bar, a toolbar (Create Blend Shape, Add Target, search) and a tree of blendShape nodes with their targets
(visibility dot, name, weight field + slider, Edit, Key). Blender: a blendShape node = the base
mesh's Key datablock (named ``blendShapeN``), its targets = the key blocks after the Basis, weight =
``KeyBlock.value``, visibility = ``not KeyBlock.mute``, Edit (sculptTarget) = the target is the object's active shape
key (moving vertices in Edit Mode then writes into it, Blender's own behaviour). Blender has no envelope: the node row
shows 1.000 read-only.

The window = ``marked_window`` kind SHAPE_EDITOR; menus from ``editor_menu_data`` ("Shape Editor"), actions from
``editor_menu_map``.
"""

import contextlib

import bpy
from bpy.props import EnumProperty, StringProperty
from mathutils import kdtree

from . import marked_window

KIND = "SHAPE_EDITOR"
EDITOR = "Shape Editor"
_collapsed = set()          # blendShape rows the user folded (UI state only, like Maya's tree)


# --- model ------------------------------------------------------------------------------------------------------------

def owner(key):
    """The object a Key belongs to (its mesh's first user in the scene, else anywhere)."""
    scene = bpy.context.scene
    for coll in (scene.objects if scene is not None else (), bpy.data.objects):
        for ob in coll:
            if ob.type == 'MESH' and ob.data.shape_keys == key:
                return ob
    return None


def blend_shapes(scene):
    """[(key, object)] for every mesh in the scene with shape keys (Maya lists every blendShape node, SE3)."""
    out, seen = [], set()
    for ob in scene.objects:
        if ob.type == 'MESH' and ob.data.shape_keys is not None and ob.data.shape_keys not in seen:
            seen.add(ob.data.shape_keys)
            out.append((ob.data.shape_keys, ob))
    return out


def current(context):
    """The Shape Editor's current row: (key, target index or None), or (None, None)."""
    text = context.window_manager.allset_se_current
    name, _, index = text.partition("/")
    key = bpy.data.shape_keys.get(name) if name else None
    if key is None:
        return None, None
    if index.isdigit() and 0 < int(index) < len(key.key_blocks):
        return key, int(index)
    return key, None


def editing(key):
    """The name of ``key``'s target in Edit, else "" (SE6: one target at a time, remembered in ``allset_se_edit``)."""
    if key is None:
        return ""
    name = bpy.context.window_manager.allset_se_edit.partition("/")[0]
    ob = owner(key) if name == key.name else None
    if ob is None or not 0 < ob.active_shape_key_index < len(key.key_blocks):
        return ""
    return key.key_blocks[ob.active_shape_key_index].name


def _key_of(context):
    """The blendShape Add Target / Add Selection work on: the current row's, else the selected mesh's (SE2)."""
    key, _ = current(context)
    if key is not None:
        return key
    obs = [context.active_object, *getattr(context, "selected_objects", ())]
    for ob in obs:
        if ob is not None and ob.type == 'MESH' and ob.data.shape_keys is not None:
            return ob.data.shape_keys
    return None


def _targets(context, whole_node=True):
    """[(key, index)] the menu commands act on: the current target, or every target of the current blendShape row
    (``whole_node``), else the selected mesh's targets."""
    key, index = current(context)
    if key is not None and index is not None:
        return [(key, index)]
    if key is None:
        key = _key_of(context)
    if key is None or not whole_node:
        return []
    return _target_indices(key)


def _target_indices(key):
    """[(key, index)] of ``key``'s Maya targets (hidden in-between / fix keys left out)."""
    from ..operators import blend_shapes_227
    hidden = blend_shapes_227.helper_names(key)
    return [(key, i) for i in range(1, len(key.key_blocks)) if key.key_blocks[i].name not in hidden]


@contextlib.contextmanager
def _object_mode(ob):
    """Run data edits of ``ob``'s shape keys in Object Mode (the edit BMesh would overwrite them on exit)."""
    was_edit = ob is not None and ob.mode == 'EDIT'
    if was_edit:
        with bpy.context.temp_override(active_object=ob, object=ob, selected_objects=[ob],
                                       selected_editable_objects=[ob]):
            bpy.ops.object.mode_set(mode='OBJECT')
    try:
        yield
    finally:
        if was_edit:
            with bpy.context.temp_override(active_object=ob, object=ob, selected_objects=[ob],
                                           selected_editable_objects=[ob]):
                bpy.ops.object.mode_set(mode='EDIT')


def edit_off(context):
    """Maya ``cmds.sculptTarget(edit=True, target=-1)``: the target in Edit goes back to the Basis (SE6)."""
    wm = context.window_manager
    name = wm.allset_se_edit.partition("/")[0]
    key = bpy.data.shape_keys.get(name) if name else None
    ob = owner(key) if key is not None else None
    if ob is not None:
        ob.active_shape_key_index = 0
    wm.allset_se_edit = ""


def edit_on(context, key, index):
    """Put target ``index`` of ``key`` into Edit (sculptTarget): the object's active shape key; only one at a time."""
    edit_off(context)
    ob = owner(key)
    if ob is None:
        return False
    ob.active_shape_key_index = index
    ob.use_shape_key_edit_mode = True
    context.window_manager.allset_se_edit = f"{key.name}/{key.key_blocks[index].name}"
    return True


def add_target_name(key, ob):
    """Maya's Add Target name: the base duplicate's name — one past the highest ``<base><N>`` node name
    (pCube1 -> pCube2) — and the next number while that name is already a target of this blendShape."""
    from ..operators import naming
    base = naming.base_name(ob.name)
    n = naming.next_number(base, {o.name for o in bpy.data.objects})
    names = {kb.name for kb in key.key_blocks}
    while f"{base}{n}" in names:
        n += 1
    return f"{base}{n}"


def unique_target_name(key, name):
    """Maya Shape Editor target naming (behaviour): ``name``, else name1,
    name2 ... until no target has it."""
    names = {kb.name for kb in key.key_blocks}
    out, i = name, 1
    while out in names:
        out, i = f"{name}{i}", i + 1
    return out


def _coords(points):
    flat = [0.0] * (len(points) * 3)
    points.foreach_get("co", flat)
    return [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]


def _write(points, coords):
    points.foreach_set("co", [c for p in coords for c in p])


def _partners(base, axis):
    """Mirror partner of each base point across the object's ``axis`` plane (None = no partner)."""
    tree = kdtree.KDTree(len(base))
    for i, p in enumerate(base):
        tree.insert(p, i)
    tree.balance()
    size = max((max(abs(c) for c in p) for p in base), default=1.0) or 1.0
    tol = 1e-4 * size
    out = []
    for p in base:
        q = list(p)
        q[axis] = -q[axis]
        _co, j, dist = tree.find(q)
        out.append(j if j is not None and dist <= tol else None)
    return out, tol


def _mirrored(delta, axis):
    d = list(delta)
    d[axis] = -d[axis]
    return d


def flip(key, index, axis=0):
    """Maya Flip Target: the target's move goes to the other side of the ``axis`` plane (left <-> right)."""
    base = _coords(key.reference_key.data)
    kb = key.key_blocks[index]
    co = _coords(kb.data)
    delta = [[c - b for c, b in zip(p, q)] for p, q in zip(co, base)]
    partners, _tol = _partners(base, axis)
    out = []
    for i, j in enumerate(partners):
        d = _mirrored(delta[j], axis) if j is not None else delta[i]
        out.append([b + x for b, x in zip(base[i], d)])
    _write(kb.data, out)


def mirror(key, index, axis=0, direction='POSITIVE'):
    """Maya Mirror Target: one side's move copied onto the other (POSITIVE = +axis -> -axis); points on the plane
    lose their move across it."""
    base = _coords(key.reference_key.data)
    kb = key.key_blocks[index]
    co = _coords(kb.data)
    delta = [[c - b for c, b in zip(p, q)] for p, q in zip(co, base)]
    partners, tol = _partners(base, axis)
    sign = 1.0 if direction == 'POSITIVE' else -1.0
    out = []
    for i, j in enumerate(partners):
        side = base[i][axis] * sign
        d = delta[i]
        if side < -tol and j is not None:
            d = _mirrored(delta[j], axis)
        elif abs(side) <= tol:
            d = list(d)
            d[axis] = 0.0
        out.append([b + x for b, x in zip(base[i], d)])
    _write(kb.data, out)


def redraw(context):
    marked_window.redraw(context, KIND)


# --- operators ------------------------------------------------------------------------------------------------------

class ALLSET_OT_shape_editor(bpy.types.Operator):
    """Open the Shape Editor: blendShape nodes (shape keys) with their targets' weights, Edit and Key
    (Maya Windows > Animation Editors > Shape Editor)"""
    bl_idname = "allset.shape_editor"
    bl_label = "Shape Editor"

    def execute(self, context):
        if context.window is None:
            return {'CANCELLED'}
        if marked_window.open_window(context, KIND) is None:
            from . import window_places
            if not window_places.deferred():     # opens on a later tick (#203)
                self.report({'ERROR'}, "Could not open the Shape Editor window")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_shape_pick(bpy.types.Operator):
    """Select this row in the Shape Editor"""
    bl_idname = "allset.shape_pick"
    bl_label = "Select Shape"

    key: StringProperty(options={'SKIP_SAVE'})
    index: bpy.props.IntProperty(default=0, options={'SKIP_SAVE'})
    extend: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'},
                                   description="Add this target to the picked targets (Ctrl / Shift+click)")

    def invoke(self, context, event):
        if event.ctrl or event.shift:
            self.extend = True
        return self.execute(context)

    def execute(self, context):
        wm = context.window_manager
        wm.allset_se_current = (f"{self.key}/{self.index}" if self.index > 0 else self.key) if self.key else ""
        # the picked targets in pick order (Add / Set as Combination Target read them)
        if hasattr(wm, "allset_se_picked"):
            key = bpy.data.shape_keys.get(self.key) if self.key else None
            names = []
            if key is not None and 0 < self.index < len(key.key_blocks):
                name = key.key_blocks[self.index].name
                old, _, rest = wm.allset_se_picked.partition("/")
                names = [n for n in rest.split("	") if n and n != name] if self.extend and old == key.name else []
                names.append(name)
            wm.allset_se_picked = f"{key.name}/" + "	".join(names) if names else ""
        redraw(context)
        return {'FINISHED'}


class ALLSET_OT_shape_expand(bpy.types.Operator):
    """Show or hide this blendShape's targets"""
    bl_idname = "allset.shape_expand"
    bl_label = "Expand"

    key: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        if self.key in _collapsed:
            _collapsed.discard(self.key)
        else:
            _collapsed.add(self.key)
        redraw(context)
        return {'FINISHED'}


class ALLSET_OT_shape_create(bpy.types.Operator):
    """Create a blendShape deformer (no targets) on the selected meshes (Maya Create Blend Shape)"""
    bl_idname = "allset.shape_create"
    bl_label = "Create Blend Shape"
    bl_options = {'UNDO'}

    def execute(self, context):
        from ..operators import naming
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not meshes and context.active_object is not None and context.active_object.type == 'MESH':
            meshes = [context.active_object]
        if not meshes:
            self.report({'WARNING'}, "Select a mesh to create a blendShape on")
            return {'CANCELLED'}
        made, had = [], []
        for ob in meshes:
            if ob.data.shape_keys is not None:
                had.append(ob)      # Blender has one Key per mesh
                continue
            with _object_mode(ob):
                ob.shape_key_add(name="Basis", from_mix=False)
            key = ob.data.shape_keys
            taken = {k.name for k in bpy.data.shape_keys if k != key}
            key.name = f"blendShape{naming.next_number('blendShape', taken)}"   # SE4: one past the highest
            made.append(key)
        if had:
            self.report({'WARNING'}, f"{', '.join(o.name for o in had)} already has a blendShape "
                                     f"({', '.join(o.data.shape_keys.name for o in had)}): Blender keeps one per mesh")
        if not made:
            return {'CANCELLED'}
        context.window_manager.allset_se_current = made[-1].name
        redraw(context)
        return {'FINISHED'}


class ALLSET_OT_shape_add_target(bpy.types.Operator):
    """Add a target to the selected blendShape: a copy of the base, weight 1, in Edit (Maya Add Target)"""
    bl_idname = "allset.shape_add_target"
    bl_label = "Add Target"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        key = _key_of(context)
        return key is not None and owner(key) is not None

    def execute(self, context):
        key = _key_of(context)
        ob = owner(key)
        name = add_target_name(key, ob)
        with _object_mode(ob):
            kb = ob.shape_key_add(name=name, from_mix=False)    # SE5: zero delta
            kb.value = 1.0
        edit_on(context, key, len(key.key_blocks) - 1)
        context.window_manager.allset_se_current = f"{key.name}/{len(key.key_blocks) - 1}"
        redraw(context)
        return {'FINISHED'}


class ALLSET_OT_shape_add_selection(bpy.types.Operator):
    """Add the other selected meshes as targets of the selected blendShape (Maya Add Selection as Target)"""
    bl_idname = "allset.shape_add_selection"
    bl_label = "Add Selection as Target"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return _key_of(context) is not None

    def execute(self, context):
        key = _key_of(context)
        ob = owner(key)
        n = len(key.reference_key.data)
        picked = [o for o in context.selected_objects if o.type == 'MESH' and o != ob]
        good = [o for o in picked if len(o.data.vertices) == n]
        bad = [o for o in picked if o not in good]
        if not good:
            self.report({'ERROR'}, "No target mesh selected" if not bad else
                        f"{', '.join(o.name for o in bad)}: a different vertex count than {ob.name}")
            return {'CANCELLED'}
        with _object_mode(ob):
            for o in good:
                kb = ob.shape_key_add(name=unique_target_name(key, o.name), from_mix=False)
                _write(kb.data, _coords(o.data.vertices))
                # Maya Add Target from the selection: no Edit, weight reset to 0
                kb.value = 0.0
        if bad:
            self.report({'WARNING'}, f"Skipped (different vertex count): {', '.join(o.name for o in bad)}")
        redraw(context)
        return {'FINISHED'}


class _TargetOp:
    key: StringProperty(options={'SKIP_SAVE'})
    target: StringProperty(options={'SKIP_SAVE'})

    def picked(self, context, whole_node=True):
        if self.key:
            key = bpy.data.shape_keys.get(self.key)
            if key is None:
                return []
            i = key.key_blocks.find(self.target) if self.target else -1
            return [(key, i)] if i > 0 else (_target_indices(key) if whole_node else [])
        return _targets(context, whole_node)


class ALLSET_OT_shape_edit(_TargetOp, bpy.types.Operator):
    """Edit this target: moving the base's vertices in Edit Mode writes into it (Maya Edit / sculptTarget)"""
    bl_idname = "allset.shape_edit"
    bl_label = "Edit Target"
    bl_options = {'UNDO'}

    def execute(self, context):
        picked = self.picked(context, whole_node=False)
        if not picked:
            self.report({'WARNING'}, "Select a target to edit")
            return {'CANCELLED'}
        key, index = picked[0]
        if editing(key) == key.key_blocks[index].name:
            edit_off(context)
        else:
            edit_on(context, key, index)
        redraw(context)
        return {'FINISHED'}


class ALLSET_OT_shape_key(_TargetOp, bpy.types.Operator):
    """Set a key on the selected targets' weights at the current time (Maya Shapes > Key)"""
    bl_idname = "allset.shape_key"
    bl_label = "Key"
    bl_options = {'UNDO'}

    def execute(self, context):
        picked = self.picked(context)
        if not picked:
            self.report({'WARNING'}, "Select targets to key")
            return {'CANCELLED'}
        frame = context.scene.frame_current
        from ..operators import graph_key_menu
        for key, i in picked:
            kb = key.key_blocks[i]
            kb.keyframe_insert("value", frame=frame)
            try:
                graph_key_menu.after_insert(kb, "value", -1, frame)
            except (AttributeError, RuntimeError, TypeError):
                pass
        redraw(context)
        return {'FINISHED'}


class ALLSET_OT_shape_reset(_TargetOp, bpy.types.Operator):
    """Set the selected targets' weights to 0 (Maya Shapes > Reset)"""
    bl_idname = "allset.shape_reset"
    bl_label = "Reset"
    bl_options = {'UNDO'}

    def execute(self, context):
        picked = self.picked(context)
        if not picked:
            self.report({'WARNING'}, "Select targets to reset")
            return {'CANCELLED'}
        for key, i in picked:
            key.key_blocks[i].value = 0.0
        redraw(context)
        return {'FINISHED'}


class ALLSET_OT_shape_duplicate(_TargetOp, bpy.types.Operator):
    """Duplicate the selected target: a copy named <target>_Copy (Maya Shapes > Duplicate Target)"""
    bl_idname = "allset.shape_duplicate"
    bl_label = "Duplicate Target"
    bl_options = {'UNDO'}

    def execute(self, context):
        picked = self.picked(context, whole_node=False)
        if not picked:
            self.report({'WARNING'}, "Select a target to duplicate")
            return {'CANCELLED'}
        for key, i in picked:
            ob = owner(key)
            src = key.key_blocks[i]
            # Maya Shape Editor Duplicate Target (behaviour): name <target>_Copy, made unique
            # (_Copy1, _Copy2 ...); the copy's weight stays 0
            name = unique_target_name(key, src.name + "_Copy")
            with _object_mode(ob):
                kb = ob.shape_key_add(name=name, from_mix=False)
                _write(kb.data, _coords(src.data))
                kb.value = 0.0
                kb.slider_min, kb.slider_max = src.slider_min, src.slider_max
                kb.vertex_group = src.vertex_group
        redraw(context)
        return {'FINISHED'}


AXES = (('X', "X", "Across the YZ plane"), ('Y', "Y", "Across the XZ plane"), ('Z', "Z", "Across the XY plane"))


class ALLSET_OT_shape_flip(_TargetOp, bpy.types.Operator):
    """Flip the selected targets: their deformation moves to the other side (Maya Shapes > Flip Target)"""
    bl_idname = "allset.shape_flip"
    bl_label = "Flip Target"
    bl_options = {'UNDO'}

    axis: EnumProperty(name="Symmetry axis", items=AXES, default='X')

    def execute(self, context):
        picked = self.picked(context, whole_node=False)
        if not picked:
            self.report({'WARNING'}, "Select a target to flip")
            return {'CANCELLED'}
        for key, i in picked:
            with _object_mode(owner(key)):
                flip(key, i, "XYZ".index(self.axis))
        return {'FINISHED'}


class ALLSET_OT_shape_mirror(_TargetOp, bpy.types.Operator):
    """Mirror the selected targets: one side's deformation copied onto the other (Maya Shapes > Mirror Target)"""
    bl_idname = "allset.shape_mirror"
    bl_label = "Mirror Target"
    bl_options = {'UNDO'}

    axis: EnumProperty(name="Symmetry axis", items=AXES, default='X')
    direction: EnumProperty(name="Direction", items=(('POSITIVE', "+ to -", "Copy the + side onto the - side"),
                                                     ('NEGATIVE', "- to +", "Copy the - side onto the + side")),
                            default='POSITIVE')

    def execute(self, context):
        picked = self.picked(context, whole_node=False)
        if not picked:
            self.report({'WARNING'}, "Select a target to mirror")
            return {'CANCELLED'}
        for key, i in picked:
            with _object_mode(owner(key)):
                mirror(key, i, "XYZ".index(self.axis), self.direction)
        return {'FINISHED'}


# --- the window's panel ---------------------------------------------------------------------------------------------

def _keyed_icon(key, kb, frame):
    from .. import compat
    path = f'key_blocks["{kb.name}"].value'
    fc = next((f for f in compat.id_fcurves(key) if f.data_path == path), None)
    if fc is None:
        return 'DECORATE_ANIMATE'
    return 'DECORATE_KEYFRAME' if any(abs(k.co.x - frame) < 1e-4 for k in fc.keyframe_points) else 'DECORATE_ANIMATE'


def draw_toolbar(layout, context):
    row = layout.row(align=False)
    tools = row.row(align=True)
    tools.operator("allset.shape_create", text="Create Blend Shape")
    tools.operator("allset.shape_add_target", text="Add Target")
    row.prop(context.window_manager, "allset_se_filter", text="", icon='VIEWZOOM')


def _columns(layout):
    split = layout.split(factor=0.42, align=True)
    name = split.row(align=True)
    rest = split.split(factor=0.68, align=True)
    return name, rest.row(align=True), rest.row(align=True)


def draw_tree(layout, context):
    wm = context.window_manager
    cur_key, cur_index = current(context)
    text = wm.allset_se_filter.strip().lower()
    frame = context.scene.frame_current
    col = layout.column(align=True)
    name, weight, buttons = _columns(col)
    name.label(text="Name")
    weight.label(text="Weight/Drivers")
    buttons.label(text="Edit   Key")
    items = blend_shapes(context.scene)
    if not items:
        col.label(text="No blendShape: select a mesh and Create Blend Shape", icon='INFO')
        return
    for key, _ob in items:
        name, weight, buttons = _columns(col)
        open_ = key.name not in _collapsed
        op = name.operator("allset.shape_expand", text="", icon='TRIA_DOWN' if open_ else 'TRIA_RIGHT', emboss=False)
        op.key = key.name
        here = cur_key == key and cur_index is None
        if here:
            name.prop(key, "name", text="")
        else:
            pick = name.operator("allset.shape_pick", text=key.name, icon='SHAPEKEY_DATA', emboss=False)
            pick.key, pick.index = key.name, 0
        envelope = weight.row(align=True)
        envelope.enabled = False             # Blender has no envelope: 1.000, read-only
        envelope.label(text="1.000")
        buttons.label(text="")
        if not open_:
            continue
        in_edit = editing(key)
        from ..operators import blend_shapes_227 as bs
        hidden = bs.helper_names(key)
        ibs, combos = bs.inbetweens(key), bs.combinations(key)
        picked = picked_targets(context, key)
        for i, kb in enumerate(key.key_blocks):
            if i == 0 or kb.name in hidden or (text and text not in kb.name.lower()):
                continue
            name, weight, buttons = _columns(col)
            name.label(text="", icon='BLANK1')
            name.prop(kb, "mute", text="", invert_checkbox=True, emboss=False,
                      icon='HIDE_ON' if kb.mute else 'HIDE_OFF')
            if cur_key == key and cur_index == i:
                name.prop(kb, "name", text="")
            else:
                on = kb.name in picked
                pick = name.operator("allset.shape_pick", text=kb.name, emboss=on, depress=on,
                                     icon='AUTOMERGE_ON' if kb.name in combos else 'NONE')
                pick.key, pick.index = key.name, i
            field = weight.row(align=True)
            field.scale_x = 0.55
            field.prop(kb, "value", text="")
            if kb.name in combos:
                # a combination target: its weight is driven by the driver targets (Maya combinationShape)
                inputs, method = combos[kb.name]
                label = next(m[1] for m in bs.METHODS if m[0] == method)
                op = weight.operator_menu_enum("allset.shape_combination_method", "method", text=label)
                op.key, op.target = key.name, kb.name
            else:
                weight.prop(kb, "value", text="", slider=True)
            is_edit = in_edit == kb.name
            edit = buttons.row(align=True)
            edit.alert = is_edit                 # Maya draws the Edit button red while sculpting
            op = edit.operator("allset.shape_edit", text="Edit", depress=is_edit)
            op.key, op.target = key.name, kb.name
            op = buttons.operator("allset.shape_key", text="", icon=_keyed_icon(key, kb, frame), emboss=False)
            op.key, op.target = key.name, kb.name
            for w, label in ibs.get(kb.name, ()):
                _draw_inbetween(col, key, kb, w, label, in_edit)


def _draw_inbetween(col, key, kb, w, label, in_edit):
    """An in-between row under its target (Maya shows in-betweens as the target's children with their weight)."""
    from ..operators import blend_shapes_227 as bs
    hb = key.key_blocks.get(bs.ib_name(kb.name, w))
    if hb is None:
        return
    name, weight, buttons = _columns(col)
    name.label(text="", icon='BLANK1')
    name.label(text="", icon='BLANK1')
    name.label(text=label, icon='IPO_LINEAR')
    shown = weight.row(align=True)
    shown.enabled = False                # the in-between weight is fixed (blendShapeChangeInBetweenWeight: not here)
    shown.label(text=f"{w:.3f}")
    op = weight.operator("allset.shape_remove_inbetween", text="", icon='X', emboss=False)
    op.key, op.target, op.weight = key.name, kb.name, w
    is_edit = in_edit == hb.name
    edit = buttons.row(align=True)
    edit.alert = is_edit
    op = edit.operator("allset.shape_edit", text="Edit", depress=is_edit)
    op.key, op.target = key.name, hb.name
    buttons.label(text="", icon='BLANK1')


def picked_targets(context, key):
    """Targets picked in the Shape Editor for ``key``, else the current target."""
    wm = context.window_manager
    name, _, rest = getattr(wm, "allset_se_picked", "").partition("/")
    if key is not None and name == key.name:
        return [n for n in rest.split("	") if n and key.key_blocks.get(n) is not None]
    cur, index = current(context)
    return [cur.key_blocks[index].name] if cur == key and index is not None else []


class ALLSET_PT_shape_editor(bpy.types.Panel):
    """Maya's Shape Editor (a marked Properties Tool tab in its own window)"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"            # = drawn by the Properties Tool tab
    bl_label = "Shape Editor"
    bl_options = {'HIDE_HEADER'}
    bl_order = -300

    @classmethod
    def poll(cls, context):
        return marked_window.context_kind(context) == KIND

    def draw(self, context):
        layout = self.layout
        marked_window.draw_menu_bar(layout, context, EDITOR)
        draw_toolbar(layout, context)
        draw_tree(layout, context)


classes = (ALLSET_OT_shape_editor, ALLSET_OT_shape_pick, ALLSET_OT_shape_expand, ALLSET_OT_shape_create,
           ALLSET_OT_shape_add_target, ALLSET_OT_shape_add_selection, ALLSET_OT_shape_edit, ALLSET_OT_shape_key,
           ALLSET_OT_shape_reset, ALLSET_OT_shape_duplicate, ALLSET_OT_shape_flip, ALLSET_OT_shape_mirror,
           ALLSET_PT_shape_editor)

_WM_PROPS = ("allset_se_current", "allset_se_edit", "allset_se_filter")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.allset_se_current = StringProperty(name="Shape Editor row",
                                          description="The Shape Editor's current row: <blendShape>[/<target index>]")
    wm.allset_se_edit = StringProperty(name="Target in Edit", description="<blendShape>/<target> being sculpted")
    wm.allset_se_filter = StringProperty(name="Search", description="Show only targets whose name contains this",
                                         options={'TEXTEDIT_UPDATE'})


def unregister():
    for name in _WM_PROPS:
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _collapsed.clear()
