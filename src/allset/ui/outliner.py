# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Outliner as a UIList in the 3D View sidebar (category "Outliner").

Maya Outliner as it starts: no shapes,
DAG objects only, no auto expand; Maya transform / shape nodes;
Blender's Outliner tree is C: a UIList is the
way to a custom tree, without drag and drop.

Rows (``WindowManager.allset_outliner_rows``) are rebuilt outside drawing
(ID data can't be written while drawing): from the depsgraph / load handlers
and from this module's operators, skipped when nothing they show changed.

Joints: a Maya joint is a bone, so an
expanded armature lists its bones as JOINT rows in bone hierarchy order; clicking one enters
pose mode and selects that bone.

Sets: kit sets (``operators/sets.py``) follow the DAG rows as SET rows; clicking one selects
its members.
"""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, StringProperty

from .. import compat, depsgraph_filter

CATEGORY = "Outliner"
_state = {"sig": None, "busy": False}


def _target(row):
    if row.kind == 'SET':
        return None
    return bpy.data.objects.get(row.object)


def _set(row):
    from ..operators import sets
    return sets.get(row.object) if row.kind == 'SET' else None


def _bone(row):
    ob = _target(row)
    if ob is None or ob.type != 'ARMATURE':
        return None
    return ob.data.bones.get(row.bone)


def _get_label(self):
    if self.kind == 'SET':
        return self.object
    ob = _target(self)
    if ob is None:
        return self.object
    if self.kind == 'JOINT':
        return self.bone
    if self.kind == 'SHAPE':
        return ob.data.name if ob.data is not None else ""
    return ob.name


def _set_label(self, value):
    coll = _set(self)
    if coll is not None and value:
        coll.name = value
        self.object = coll.name
        return
    ob = _target(self)
    if ob is None or not value:
        return
    if self.kind == 'JOINT':
        bone = _bone(self)
        if bone is not None:
            bone.name = value
            self.bone = bone.name
        return
    if self.kind == 'SHAPE' and ob.data is not None:
        ob.data.name = value
    else:
        ob.name = value
        self.object = ob.name   # Blender may have added a suffix


class ALLSET_PG_outliner_row(bpy.types.PropertyGroup):
    kind: EnumProperty(items=(('OBJECT', "Object", ""), ('SHAPE', "Shape", ""), ('JOINT', "Joint", ""),
                              ('SET', "Set", "")))
    object: StringProperty()
    bone: StringProperty()       # JOINT: bone name
    depth: IntProperty()
    has_children: BoolProperty()
    label: StringProperty(name="Name", get=_get_label, set=_set_label)


# --- rows ------------------------------------------------------------------------------------

def dag_rows(scene, shapes):
    """[(kind, object name, depth, has children, bone name)] in Maya DAG order: roots in scene
    order, children depth first; collapsed objects (and joints) hide their children. An
    armature's bones come first under it, like the joints under a Maya skeleton group."""
    order = {ob: i for i, ob in enumerate(scene.objects)}
    # Object.children scans every object in the file: once per object made each depsgraph update O(n^2)
    # (620 objects = 65 ms per update)
    children = {}
    for ob in order:
        if ob.parent in order:
            children.setdefault(ob.parent, []).append(ob)
    rows = []

    def visit_bone(ob, bone, depth):
        rows.append(('JOINT', ob.name, depth, bool(bone.children), bone.name))
        if bone.allset_expanded:
            for child in bone.children:
                visit_bone(ob, child, depth + 1)

    def visit(ob, depth):
        kids = sorted(children.get(ob, ()), key=order.get)
        shape = shapes and ob.data is not None
        roots = [b for b in ob.data.bones if b.parent is None] if ob.type == 'ARMATURE' else []
        rows.append(('OBJECT', ob.name, depth, bool(kids) or shape or bool(roots), ""))
        if ob.allset_expanded:
            if shape:
                rows.append(('SHAPE', ob.name, depth + 1, False, ""))
            for bone in roots:
                visit_bone(ob, bone, depth + 1)
            for c in kids:
                visit(c, depth + 1)

    for ob in sorted((o for o in order if o.parent is None or o.parent not in order), key=order.get):
        visit(ob, 0)
    from ..operators import sets
    rows.extend(('SET', coll.name, 0, False, "") for coll in sets.all_sets())   # Maya: sets after the DAG
    return rows


def rebuild(context=None, force=False):
    context = context or bpy.context
    wm, scene = context.window_manager, context.scene
    if scene is None or not hasattr(wm, "allset_outliner_rows") or _state["busy"]:
        return False
    rows = dag_rows(scene, wm.allset_outliner_shapes)
    sig = (scene.name, tuple(rows))
    if not force and sig == _state["sig"] and len(wm.allset_outliner_rows) == len(rows):
        return False
    _state["busy"] = True
    try:
        coll = wm.allset_outliner_rows
        coll.clear()
        for kind, name, depth, has, bone in rows:
            it = coll.add()
            it.kind, it.object, it.depth, it.has_children, it.bone = kind, name, depth, has, bone
        _state["sig"] = sig
    finally:
        _state["busy"] = False
    return True


@persistent
def _on_depsgraph(scene, depsgraph):
    # #191: the rows are names / parents / membership / bones — a move, a mesh edit or a selection change
    # can't change them, and building the rows walks the whole scene (1.6 ms per update at 620 objects)
    if depsgraph_filter.outliner_skip(depsgraph):
        return
    _bump()
    rebuild()


@persistent
def _on_undo(_dummy):
    _bump()
    rebuild()


def _bump():
    _state["version"] = _state.get("version", 0) + 1


def structure_version():
    """Goes up whenever names, parents, membership or bones may have changed (any update the row check doesn't skip,
    load, undo, redo): code that derives something from the scene's structure keeps it until this changes."""
    return _state.get("version", 0)


@persistent
def _on_load(_dummy):
    _bump()
    _state["sig"] = None
    rebuild(force=True)


# --- selection ---------------------------------------------------------------------------------

def _get_index(self):
    ob = bpy.context.view_layer.objects.active
    bone = None
    if ob is not None and ob.type == 'ARMATURE' and ob.mode == 'POSE' and ob.data.bones.active:
        bone = ob.data.bones.active.name
    for i, row in enumerate(self.allset_outliner_rows):
        if ob is None or row.object != ob.name:
            continue
        if (row.kind == 'JOINT' and row.bone == bone) or (row.kind == 'OBJECT' and bone is None):
            return i
    return -1


def _set_index(self, value):
    rows = self.allset_outliner_rows
    if 0 <= value < len(rows):
        select_rows(bpy.context, rows, value, 'REPLACE')


def _select(ob, state=True):
    """``select_set``; False if ``ob`` is not in the view layer. (Checking
    ``view_layer.objects.get`` instead misses objects linked since the last
    view layer sync.)"""
    try:
        ob.select_set(state)
        return True
    except RuntimeError:
        return False


def _pose_bone(row):
    ob = _target(row)
    return ob.pose.bones.get(row.bone) if ob is not None and ob.pose is not None else None


def _enter_pose(context, ob):
    """Make ``ob`` the active armature in pose mode (Maya: picking a joint just selects it)."""
    vl = context.view_layer
    if ob.mode == 'POSE' and vl.objects.active == ob:
        return True
    if context.mode != 'OBJECT' and context.active_object is not None:
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in context.selected_objects:
        o.select_set(False)
    if not _select(ob):
        return False
    vl.objects.active = ob
    if not ob.visible_get():           # a hidden skeleton: picked, but Blender can't pose it (#187)
        return False
    bpy.ops.object.mode_set(mode='POSE')
    return ob.mode == 'POSE'


def select_joint_rows(context, rows, index, mode, anchor=None):
    """A JOINT row: pose mode on its armature, then select the bone (Ctrl toggle, Shift range
    among the same armature's joint rows)."""
    from .channel_box import bone_selected, set_bone_selected
    row = rows[index]
    ob, pb = _target(row), _pose_bone(row)
    if ob is None or pb is None or not _enter_pose(context, ob):
        return
    if mode == 'TOGGLE':
        set_bone_selected(pb, not bone_selected(pb))
        if bone_selected(pb):
            ob.data.bones.active = pb.bone
        return
    picked = [pb]
    if mode == 'RANGE' and anchor is not None and 0 <= anchor < len(rows):
        lo, hi = sorted((anchor, index))
        picked = [_pose_bone(r) for r in list(rows)[lo:hi + 1]
                  if r.kind == 'JOINT' and r.object == row.object]
    else:
        for other in ob.pose.bones:
            set_bone_selected(other, False)
    for b in picked:
        if b is not None:
            set_bone_selected(b, True)
    ob.data.bones.active = pb.bone


def select_rows(context, rows, index, mode, anchor=None):
    """Maya Outliner selection: REPLACE (click), TOGGLE (Ctrl), RANGE (Shift, from
    ``anchor`` = the active row)."""
    vl = context.view_layer
    if rows[index].kind == 'JOINT':
        return select_joint_rows(context, rows, index, mode, anchor)
    if rows[index].kind == 'SET':
        from ..operators import sets
        coll = _set(rows[index])
        if coll is not None:
            sets.select_members(context, coll, {'TOGGLE': 'TOGGLE', 'RANGE': 'ADD'}.get(mode, 'REPLACE'))
        return
    ob = bpy.data.objects.get(rows[index].object)
    if ob is None:
        return
    if context.mode != 'OBJECT' and context.active_object is not None:
        from ..operators import joint_selection
        joint_selection.leave(context, clear_selection=mode == 'REPLACE')
    if mode == 'TOGGLE':
        if _select(ob, not ob.select_get()) and ob.select_get():
            vl.objects.active = ob
        return
    if mode == 'RANGE' and anchor is not None and 0 <= anchor < len(rows):
        lo, hi = sorted((anchor, index))
        for row in list(rows)[lo:hi + 1]:
            o = bpy.data.objects.get(row.object)
            if o is not None:
                _select(o)
        vl.objects.active = ob
        return
    for o in context.selected_objects:
        o.select_set(False)
    if _select(ob):
        vl.objects.active = ob


class ALLSET_OT_outliner_select(bpy.types.Operator):
    """Select (Ctrl: toggle, Shift: range), like Maya's Outliner"""
    bl_idname = "allset.outliner_select"
    bl_label = "Outliner Select"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()
    mode: EnumProperty(items=(('REPLACE', "Replace", ""), ('TOGGLE', "Toggle", ""),
                              ('RANGE', "Range", "")))

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'POSE', 'EDIT_ARMATURE'}

    def invoke(self, context, event):
        self.mode = 'TOGGLE' if event.ctrl else 'RANGE' if event.shift else 'REPLACE'
        return self.execute(context)

    def execute(self, context):
        wm = context.window_manager
        rows = wm.allset_outliner_rows
        if not 0 <= self.index < len(rows):
            return {'CANCELLED'}
        select_rows(context, rows, self.index, self.mode, anchor=wm.allset_outliner_index)
        return {'FINISHED'}


class ALLSET_OT_outliner_expand(bpy.types.Operator):
    """Expand / collapse (Shift: with all descendants)"""
    bl_idname = "allset.outliner_expand"
    bl_label = "Expand"
    bl_options = {'INTERNAL'}

    name: StringProperty()
    bone: StringProperty()
    recursive: BoolProperty()

    def invoke(self, context, event):
        self.recursive = event.shift
        return self.execute(context)

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob is None:
            return {'CANCELLED'}
        if self.bone:
            bone = ob.data.bones.get(self.bone) if ob.type == 'ARMATURE' else None
            if bone is None:
                return {'CANCELLED'}
            state = not bone.allset_expanded
            for b in ([bone, *bone.children_recursive] if self.recursive else [bone]):
                b.allset_expanded = state
            rebuild(context)
            return {'FINISHED'}
        state = not ob.allset_expanded
        for o in ([ob, *ob.children_recursive] if self.recursive else [ob]):
            o.allset_expanded = state
        rebuild(context)
        return {'FINISHED'}


class ALLSET_OT_outliner_refresh(bpy.types.Operator):
    """Rebuild the Outliner rows"""
    bl_idname = "allset.outliner_refresh"
    bl_label = "Refresh"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        rebuild(context, force=True)
        return {'FINISHED'}


# --- drawing -------------------------------------------------------------------------------------

_ICONS = set()


def icon_for(row, ob):
    if row.kind == 'JOINT':
        return 'BONE_DATA'
    if not _ICONS:
        _ICONS.update(bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys())
    name = f"OUTLINER_DATA_{ob.type}" if row.kind == 'SHAPE' else f"OUTLINER_OB_{ob.type}"
    return name if name in _ICONS else ('OBJECT_DATA' if row.kind == 'SHAPE' else 'OBJECT_DATAMODE')


class ALLSET_UL_outliner(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        row = layout.row(align=True)
        if item.kind == 'SET':
            row.label(text="", icon='BLANK1')
            op = row.operator(ALLSET_OT_outliner_select.bl_idname, text="", icon='GROUP', emboss=False)
            op.index = index
            row.prop(item, "label", text="", emboss=False)
            return
        ob = _target(item)
        if ob is None:
            row.label(text=item.object)
            return
        for _ in range(item.depth):
            row.label(text="", icon='BLANK1')
        bone = _bone(item) if item.kind == 'JOINT' else None
        if item.kind == 'JOINT' and bone is None:
            row.label(text=item.bone)
            return
        if item.has_children:
            expanded = (bone or ob).allset_expanded
            op = row.operator(ALLSET_OT_outliner_expand.bl_idname, text="", emboss=False,
                              icon='DISCLOSURE_TRI_DOWN' if expanded else 'DISCLOSURE_TRI_RIGHT')
            op.name = ob.name
            op.bone = item.bone
        else:
            row.label(text="", icon='BLANK1')
        if bone is not None:
            from .channel_box import bone_selected
            pb = ob.pose.bones.get(bone.name)
            selected = ob.mode == 'POSE' and pb is not None and bone_selected(pb)
            visible = ob.visible_get() and not (compat.bone_hidden(pb) if pb is not None else bone.hide)
        else:
            selected, visible = ob.select_get(), ob.visible_get()
        op = row.operator(ALLSET_OT_outliner_select.bl_idname, text="", icon=icon_for(item, ob),
                          emboss=False, depress=selected)
        op.index = index
        sub = row.row()
        sub.active = visible   # hidden = grey text (Maya)
        sub.prop(item, "label", text="", emboss=False)

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flags = bpy.types.UI_UL_list.filter_items_by_name(
            self.filter_name, self.bitflag_filter_item, items, "label") if self.filter_name else []
        return flags, []


def _shapes_changed(self, context):
    rebuild(context)


classes = (ALLSET_PG_outliner_row, ALLSET_OT_outliner_select, ALLSET_OT_outliner_expand,
           ALLSET_OT_outliner_refresh, ALLSET_UL_outliner)
# ALLSET_PT_outliner (a 3D View sidebar list, shown when the dock-only option was off) went with the sidebar dock
#: the Outliner is the layout's own Outliner area / floating window.


def _first_rebuild():
    rebuild(force=True)
    return None


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.allset_outliner_rows = CollectionProperty(type=ALLSET_PG_outliner_row, options={'SKIP_SAVE'})
    wm.allset_outliner_index = IntProperty(get=_get_index, set=_set_index, options={'SKIP_SAVE'})
    wm.allset_outliner_shapes = BoolProperty(
        name="Shapes", description="Show shape nodes (object data) under their transforms (Maya "
                                   "Display > Shapes)", update=_shapes_changed, options={'SKIP_SAVE'})
    bpy.types.Object.allset_expanded = BoolProperty(
        name="Expanded", description="Expanded in the Maya Outliner", options={'HIDDEN'})
    bpy.types.Bone.allset_expanded = BoolProperty(
        name="Expanded", description="Joint expanded in the Maya Outliner", options={'HIDDEN'})
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.handlers.undo_post.append(_on_undo)
    bpy.app.handlers.redo_post.append(_on_undo)
    _state["sig"] = None
    bpy.app.timers.register(_first_rebuild, first_interval=0.0)


def unregister():
    if bpy.app.timers.is_registered(_first_rebuild):
        bpy.app.timers.unregister(_first_rebuild)
    bpy.app.handlers.redo_post.remove(_on_undo)
    bpy.app.handlers.undo_post.remove(_on_undo)
    bpy.app.handlers.load_post.remove(_on_load)
    bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    del bpy.types.Bone.allset_expanded
    del bpy.types.Object.allset_expanded
    wm = bpy.types.WindowManager
    del wm.allset_outliner_shapes
    del wm.allset_outliner_index
    del wm.allset_outliner_rows
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _state["sig"] = None
