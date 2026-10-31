# SPDX-License-Identifier: GPL-3.0-or-later
"""RMB list DG Traversal / Inputs / Outputs.

Maya fills these submenus from the dependency graph when they open (Maya 2022
RMB marking menu). The kit's graph is what the Channel Box INPUTS and the Attribute Editor tabs already
show: the last kit extrusion (polyExtrudeFace1), the modifiers (Maya deformers / poly nodes), the primitive's creation
node (polyCube1), the constraints; the shape (mesh data) and its shading groups. ``nodes(ob)`` turns them into the
bpy-free data ``marking/menus.with_nodes`` builds the submenus from.

- An Inputs / Outputs node = Maya ``cmds.select(node, add=True)``: the object stays selected, the Channel Box opens the
  node under INPUTS and the Attribute Editor tab follows; its option box = the
  Attribute Editor on that node.
- Enable / Disable All = Maya ``nodeState`` 0 / 2 (has no effect): the modifiers' viewport + render switches, the
  constraints' enabled flag. Blender has no switch for the kit's extrusion / creation node: those are left alone.
- Outputs of an object = the nodes of other objects that use it (Maya's lattice / handle / constraint target future:
  ffd1, bend1, the constraint node). A plain cube has none, like Maya.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from .. import results


def _ae():
    from ..ui import attribute_editor
    return attribute_editor


def _cb():
    from ..ui import channel_box
    return channel_box


def input_nodes(ob):
    """[(Maya node name, Maya node type, owner object, AE tab key, Channel Box node key, struct)] in the Channel Box
    INPUTS order (newest first): extrusion, modifiers, creation node, constraints."""
    ae, cb = _ae(), _cb()
    out = []
    rec = ae.history_record(ob)
    if rec is not None:
        out.append((rec.name, rec.spec.node_type, ob, "H", cb.history_node(rec.name), None))
    for md in cb._inputs(ob):
        owner = md.id_data
        try:
            name, mtype = ae.modifier_node(owner, md)
        except ValueError:
            name, mtype = md.name, md.type.lower()
        out.append((name, mtype, owner, "M:" + md.name, cb.mod_node(md), md))
    from ..operators import prim_history
    _owner, node = prim_history.node_of(ob)
    if node is not None:
        out.append((node["name"], node["type"], ob, "CH", cb.history_node(node["name"]), None))
    for con in cb.constraints(ob):
        out.append((cb.constraint_node_name(ob, con), cb.maya_constraint_type(con, con.type.lower()), ob,
                    "C:" + con.name, cb.con_node(ob, con), con))
    return out


def _uses(struct, ob):
    """``struct`` (a modifier / constraint) points at object ``ob``."""
    for p in struct.bl_rna.properties:
        if p.type == 'POINTER' and getattr(p.fixed_type, "identifier", "") == 'Object':
            try:
                if getattr(struct, p.identifier) == ob:
                    return True
            except AttributeError:
                pass
    return False


def output_nodes(ob):
    """Nodes of other objects that use ``ob`` (same tuple form as ``input_nodes``)."""
    ae, cb = _ae(), _cb()
    out = []
    for other in bpy.context.scene.objects:
        if other is None or other == ob:
            continue
        for md in getattr(other, "modifiers", ()):
            if _uses(md, ob):
                try:
                    name, mtype = ae.modifier_node(other, md)
                except ValueError:
                    name, mtype = md.name, md.type.lower()
                out.append((name, mtype, other, "M:" + md.name, cb.mod_node(md), md))
        for con in cb.constraints(other):
            if _uses(con, ob):
                out.append((cb.constraint_node_name(other, con), cb.maya_constraint_type(con, con.type.lower()),
                            other, "C:" + con.name, cb.con_node(other, con), con))
    return out


def nodes(ob):
    """The data ``menus.with_nodes`` builds DG Traversal / Inputs / Outputs from (None without an object)."""
    if ob is None:
        return None
    ae = _ae()
    ins, outs = input_nodes(ob), output_nodes(ob)
    shape = [(ob.data.name, ob.name, "S")] if getattr(ob, "data", None) is not None else []
    groups = []
    for i, slot in enumerate(ob.material_slots):
        if slot.material is not None:
            from ..operators import material
            groups.append((material.shading_group_name(slot.material), ob.name, f"SG:{i}"))
    named_ins = [(n, owner.name, key) for n, _t, owner, key, _c, _s in ins]
    named_outs = [(n, owner.name, key) for n, _t, owner, key, _c, _s in outs]
    cons = [e for e in named_ins if e[2].startswith("C:")]
    return {
        "object": ob.name,
        "inputs": [(ae.nice_type(t), owner.name, key) for _n, t, owner, key, _c, _s in ins],
        "outputs": [(ae.nice_type(t), owner.name, key) for _n, t, owner, key, _c, _s in outs],
        # Maya's RMB DG Traversal on the transform: History = the shape + what drives the transform; Future = the
        # shape, its shading groups, what uses the object
        "history": shape + cons,
        "future": shape + groups + named_outs,
        "inputs_named": [e for e in named_ins if not e[2].startswith("C:")],
    }


# --- operators -------------------------------------------------------------------------------------------------

def _redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {'VIEW_3D', 'PROPERTIES'}:
                area.tag_redraw()


def _make_lead(context, ob, replace):
    """Maya ``cmds.select(add=True)`` (the object stays in the selection) or ``cmds.select(replace=True)``; the node's
    object becomes the lead so the Channel Box / Attribute Editor show it."""
    if context.mode != 'OBJECT' and context.active_object is not ob:
        bpy.ops.object.mode_set(mode='OBJECT')
    try:
        if replace:
            for o in list(context.selected_objects):
                o.select_set(False)
        ob.select_set(True)
    except RuntimeError:       # not in the view layer
        return False
    context.view_layer.objects.active = ob
    return True


def _find(ob, key):
    """The input / output tuple of ``ob`` with AE key ``key`` (None: shape / shading group / transform)."""
    for e in input_nodes(ob):
        if e[3] == key:
            return e
    return None


class ALLSET_OT_mm_node(bpy.types.Operator):
    """Show this node in the Channel Box and the Attribute Editor (Maya: select the node); option box = the
    Attribute Editor"""
    bl_idname = "allset.mm_node"
    bl_label = "Select Node"
    bl_options = {'REGISTER', 'UNDO'}

    object: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    key: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    replace: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    option_box: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.view_layer is not None

    def execute(self, context):
        ob = bpy.data.objects.get(self.object)
        if ob is None:
            return {'CANCELLED'}
        node = _find(ob, self.key)
        if not _make_lead(context, ob, self.replace):
            self.report({'WARNING'}, f"{self.object} is not in the scene")
            return {'CANCELLED'}
        if node is not None:
            _cb().set_open(ob, node[4])        # Maya: the picked node's attributes open under INPUTS
            _cb().reveal(node[4])
            _cb().rebuild_rows(context)
        _ae().set_tab(context, self.key)
        if self.option_box:
            bpy.ops.allset.dock_show(dock='ATTRIBUTE_EDITOR')
        _redraw(context)
        return {'FINISHED'}


ACTIONS = (('SELECT', "Select", ""), ('ENABLE', "Enable", ""), ('DISABLE', "Disable", ""))


def set_enabled(struct, on):
    """Maya nodeState 0 (normal) / 2 (has no effect); False when the node has no switch."""
    if struct is None:
        return False
    if hasattr(struct, "show_viewport"):
        struct.show_viewport = on
        if hasattr(struct, "show_render"):
            struct.show_render = on
        return True
    if hasattr(struct, "enabled"):     # constraints (4.5: enabled = not mute)
        struct.enabled = on
        return True
    return False


class ALLSET_OT_mm_node_all(bpy.types.Operator):
    """Select, enable or disable every input / output node of the object (Maya Select / Enable / Disable All)"""
    bl_idname = "allset.mm_node_all"
    bl_label = "All Nodes"
    bl_options = {'REGISTER', 'UNDO'}

    object: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    future: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    action: EnumProperty(items=ACTIONS, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        ob = bpy.data.objects.get(self.object)
        if ob is None:
            return {'CANCELLED'}
        found = output_nodes(ob) if self.future else input_nodes(ob)
        if self.action == 'SELECT':
            if not found:
                return {'CANCELLED'}
            owners = []
            for e in found:
                if e[2] not in owners:
                    owners.append(e[2])
            _make_lead(context, owners[0], False)
            for o in owners[1:]:
                try:
                    o.select_set(True)
                except RuntimeError:
                    pass
            for e in found:
                if e[2] == owners[0]:
                    _cb().set_open(owners[0], e[4])
            _cb().rebuild_rows(context)
            _redraw(context)
            return {'FINISHED'}
        n = sum(set_enabled(e[5], self.action == 'ENABLE') for e in found)
        if not found:
            # Maya's message when there is nothing to enable / disable
            self.report({'WARNING'}, f"No nodes to {self.action.lower()}.")
            return {'CANCELLED'}
        results.result(self, f"{self.action.title()}d {n} node{'s' if n != 1 else ''}")
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_mm_node_table(bpy.types.Operator):
    """The object's input / output nodes with their state (Maya All Inputs... / All Outputs...)"""
    bl_idname = "allset.mm_node_table"
    bl_label = "List History"
    bl_options = {'INTERNAL'}

    object: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    future: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        if bpy.data.objects.get(self.object) is None:
            return {'CANCELLED'}
        return context.window_manager.invoke_popup(self, width=round(360 * context.preferences.system.ui_scale))

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        ob = bpy.data.objects.get(self.object)
        layout = self.layout
        word = "output" if self.future else "input"
        layout.label(text=f"List of {word} operations: {self.object}")
        if ob is None:
            return
        found = output_nodes(ob) if self.future else input_nodes(ob)
        if not found:
            layout.label(text="No items to show.")
            return
        col = layout.column(align=True)
        head = col.row()
        head.label(text="")
        head.label(text="Node State")
        ae = _ae()
        from ..operators import deformer_order
        order = [] if self.future else [m.name for m in deformer_order.movable(ob)]
        for name, mtype, owner, key, _cbkey, struct in found:
            row = col.row(align=True)
            if order:
                # Maya: drag a node with MMB in this list = reorderDeformers. The rows are in stack
                # order (first evaluated on top): up = one step earlier, down = one step later; shape keys,
                # extrusions and constraints don't move.
                mod_name = struct.name if isinstance(struct, bpy.types.Modifier) and struct.name in order else None
                i = order.index(mod_name) if mod_name else -1
                arrows = row.row(align=True)
                arrows.scale_x = 0.6
                up = arrows.row(align=True)
                up.enabled = i > 0
                op = up.operator("allset.reorder_deformers", text="", icon='TRIA_UP')
                op.object = ob.name
                if up.enabled:               # reorderDeformers <previous> <this>: this moves right before it
                    op.first, op.second = order[i - 1], mod_name
                down = arrows.row(align=True)
                down.enabled = 0 <= i < len(order) - 1
                op = down.operator("allset.reorder_deformers", text="", icon='TRIA_DOWN')
                op.object = ob.name
                if down.enabled:             # reorderDeformers <this> <next>: the next one moves before this
                    op.first, op.second = mod_name, order[i + 1]
            split = row.split(factor=0.5, align=True)
            op = split.operator(ALLSET_OT_mm_node.bl_idname, text=f"{name} ({ae.nice_type(mtype)})", emboss=False)
            op.object, op.key = owner.name, key
            if struct is None:
                sub = split.row()
                sub.active = False
                sub.label(text="Normal")
            elif hasattr(struct, "show_viewport"):
                split.prop(struct, "show_viewport", text="Normal" if struct.show_viewport else "Has No Effect",
                           toggle=True)
            else:
                split.prop(struct, "enabled", text="Normal" if struct.enabled else "Has No Effect", toggle=True)


class ALLSET_OT_mm_node_label(bpy.types.Operator):
    """Nodes below this line"""
    bl_idname = "allset.mm_node_label"
    bl_label = "Node List"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'CANCELLED'}      # Maya's "History" / "Future" rows have no command


classes = (ALLSET_OT_mm_node, ALLSET_OT_mm_node_all, ALLSET_OT_mm_node_table, ALLSET_OT_mm_node_label)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
