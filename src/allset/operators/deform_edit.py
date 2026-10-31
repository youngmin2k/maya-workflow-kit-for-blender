# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Deform menu edit items: Wire > Add / Remove / Reset / Show Base Wire / Parent Base Wire / Wire
Dropoff Locator, ShrinkWrap > Set Target / Remove Target / Add surfaces / Remove surfaces, Lattice > Reset Lattice /
Remove Lattice Tweaks, Prune Membership > Cluster / Lattice / Wire, Point On Curve.

Maya behaviour (Wire Edit / Shrink Wrap / Dropoff Locator
selection rules and messages). The kit wire: operators/wire_deformer.py.
"""

import bpy
from bpy.props import EnumProperty, FloatProperty, StringProperty

from .. import results
from .. import undo_steps
from . import deformers, wire_deformer


# --- wire ---------------------------------------------------------------------------------------------------------

MSG = {   # Maya's own messages
    "ADD": "Found no curves to add.",
    "REMOVE": "Must select curves to be removed.",
    "RESET": "Must select wire curves to be reset.",
    "SHOW_BASE": "Must select a wire curve.",
    "PARENT_BASE": "Must select a wire curve.",
    "LOCATOR": "Select a param point on a wire curve",
}


def _wires(curves, node=""):
    """[(object, modifier)] of the kit wires driven by ``curves`` (only node ``node`` when given)."""
    out = []
    for c in curves:
        out += [(o, md) for o, md in wire_deformer.wires_of_curve(c) if not node or md.name == node]
    return out


def wire_add(context, node=""):
    """Maya Wire > Add: the selected curves join the wire of the last selected (active) wire curve: every object it
    deforms gets one more wire influence with the same weights (Maya: wire1's next index)."""
    active = context.view_layer.objects.active
    new = [o for o in context.selected_objects if o.type == 'CURVE' and o is not active]
    existing = _wires([active], node) if active is not None and active.type == 'CURVE' else []
    if not existing and node:
        existing = [(o, md) for o in context.scene.objects for md in getattr(o, "modifiers", ())
                    if wire_deformer.is_wire(md) and md.name == node]
    if not new or not existing:
        raise RuntimeError(MSG["ADD"])
    made = 0
    for ob, md in existing:
        for curve in new:
            name = f"{md.name}{curve.name}"            # one influence per curve; weights = the node's group
            if ob.modifiers.get(name) is not None:
                continue
            extra = wire_deformer.add_wire(context, ob, curve, name, md.name if md.name in ob.vertex_groups else "",
                                           wire_deformer.get(md, "Dropoff Distance") or 1.0,
                                           wire_deformer.get(md, "Envelope") or 1.0,
                                           wire_deformer.get(md, "Rotation") or 1.0)
            extra.show_expanded = False
            made += 1
    return made


def wire_remove(context, node=""):
    curves = [o for o in context.selected_objects if o.type == 'CURVE']
    found = _wires(curves, node)
    if not found:
        raise RuntimeError(MSG["REMOVE"])
    for _ob, md in found:
        wire_deformer.remove(md)
    return len(found)


def wire_reset(context, node=""):
    curves = [o for o in context.selected_objects if o.type == 'CURVE']
    found = _wires(curves, node)
    if not found:
        raise RuntimeError(MSG["RESET"])
    done = set()
    for _ob, md in found:
        curve = wire_deformer.get(md, "Wire")
        if curve is not None and curve.name not in done and wire_deformer.reset(md):
            done.add(curve.name)
    return len(done)


def wire_show_base(context, node=""):
    """Maya Show Base Wire: the base wires show and join the selection (curve1, curve1BaseWire)."""
    curves = [o for o in context.selected_objects if o.type == 'CURVE']
    found = _wires(curves, node)
    if not found:
        raise RuntimeError(MSG["SHOW_BASE"])
    bases = []
    for _ob, md in found:
        base = wire_deformer.get(md, "Base Wire")
        if base is not None and base not in bases:
            base.hide_viewport = False
            base.hide_set(False)
            base.select_set(True)
            bases.append(base)
    return len(bases)


def wire_parent_base(context, node=""):
    """Maya Parent Base Wire ("group wire and base wire"): the base wire follows the wire curve's
    transform, so moving the curve object carries both and only its shape edits deform."""
    curves = [o for o in context.selected_objects if o.type == 'CURVE']
    found = _wires(curves, node)
    if not found:
        raise RuntimeError(MSG["PARENT_BASE"])
    n = 0
    for _ob, md in found:
        curve, base = wire_deformer.get(md, "Wire"), wire_deformer.get(md, "Base Wire")
        if curve is None or base is None or base.parent == curve:
            continue
        mw = base.matrix_world.copy()
        base.parent = curve
        base.matrix_world = mw
        n += 1
    return n


WIRE_ACTIONS = {"ADD": wire_add, "REMOVE": wire_remove, "RESET": wire_reset, "SHOW_BASE": wire_show_base,
                "PARENT_BASE": wire_parent_base}


@undo_steps.no_redo_panel
class ALLSET_OT_wire_edit(bpy.types.Operator):
    """Maya Deform > Wire > Add / Remove / Reset / Show Base Wire / Parent Base Wire on the selected wire curves"""
    bl_idname = "allset.wire_edit"
    bl_label = "Wire Edit"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=[(k, k.replace("_", " ").title(), "") for k in WIRE_ACTIONS], options={'SKIP_SAVE'})
    node: StringProperty(name="Wire node", options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return f"Maya Deform > Wire > {props.action.replace('_', ' ').title()}"

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            n = WIRE_ACTIONS[self.action](context, self.node.strip())
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        results.result(self, str(n))
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_wire_dropoff_locator(bpy.types.Operator):
    """A dropoff locator at the selected point of a wire curve: Percent scales the dropoff distance there
    (Maya Deform > Wire > Wire Dropoff Locator)"""
    bl_idname = "allset.wire_dropoff_locator"
    bl_label = "Wire Dropoff Locator"
    bl_options = {'REGISTER', 'UNDO'}

    envelope: FloatProperty(name="Envelope", default=1.0, min=0.0, max=1.0, options={'SKIP_SAVE'})
    percent: FloatProperty(name="Percent", default=1.0, min=0.0, soft_max=10.0, options={'SKIP_SAVE'})
    node: StringProperty(name="Wire node", options={'SKIP_SAVE'})

    def execute(self, context):
        curve = context.active_object
        points = []
        if curve is not None and curve.type == 'CURVE' and context.mode == 'EDIT_CURVE':
            bpy.ops.object.mode_set(mode='OBJECT')
            for sp in curve.data.splines:
                if sp.type == 'BEZIER':
                    points += [curve.matrix_world @ p.co for p in sp.bezier_points if p.select_control_point]
                else:
                    points += [curve.matrix_world @ p.co.to_3d() for p in sp.points if p.select]
        found = _wires([curve], self.node.strip()) if curve is not None and curve.type == 'CURVE' else []
        if not points or not found:
            self.report({'WARNING'}, MSG["LOCATOR"])
            return {'CANCELLED'}
        made = []
        for pt in points:
            param = wire_deformer.nearest_param(curve, pt)
            for _ob, md in found:
                try:
                    made.append(wire_deformer.add_locator(context, md, param, self.percent, self.envelope))
                except RuntimeError as ex:
                    self.report({'WARNING'}, str(ex))
                    return {'CANCELLED'}
        deformers._select_only(context, made, made[-1])
        return {'FINISHED'}


# --- ShrinkWrap ----------------------------------------------------------------------------------------------------

SW_MSG_SET = "Select at least one surface (or shrinkwrap node) and a target object."
SW_MSG_ADD = "Select at least one surface to add and the target object/shrinkwrap node."


def _shrinkwraps(ob):
    return [md for md in getattr(ob, "modifiers", ()) if deformers.base_of(md) == "shrinkWrap"]


def shrink_wrap_edit(context, action):
    """Maya Deform > Shrink Wrap edit commands: the surfaces are selected first, the target last
    (the active object)."""
    target = context.view_layer.objects.active
    surfaces = [o for o in context.selected_objects if o is not target and o.type in deformers._DEFORMABLE]
    if action in ("SET_TARGET", "ADD_SURFACES") and (target is None or target.type != 'MESH' or not surfaces):
        raise RuntimeError(SW_MSG_SET if action == "SET_TARGET" else SW_MSG_ADD)
    n = 0
    if action == "SET_TARGET":
        for ob in surfaces:
            for md in _shrinkwraps(ob):
                md.target = target
                n += 1
    elif action == "REMOVE_TARGET":
        for ob in surfaces + ([target] if target is not None else []):
            for md in _shrinkwraps(ob):
                if md.target is not None:
                    md.target = None
                    n += 1
    elif action == "ADD_SURFACES":
        # the node = a kit shrinkWrap that already wraps onto the target (its settings travel with it)
        model = next((md for o in context.scene.objects for md in _shrinkwraps(o) if md.target == target), None)
        if model is None:
            raise RuntimeError(f"No shrinkwrap deformer is associated with surface {target.name}.")
        for ob in surfaces:
            if any(md.name == model.name for md in ob.modifiers):
                continue
            md = deformers._add(ob, model.name, 'SHRINKWRAP', None)
            for key in ("target", "wrap_method", "wrap_mode", "use_positive_direction", "use_negative_direction",
                        "use_project_x", "use_project_y", "use_project_z", "offset"):
                setattr(md, key, getattr(model, key))
            n += 1
    elif action == "REMOVE_SURFACES":
        names = {md.name for md in _shrinkwraps(target)} if target is not None else set()
        for ob in surfaces:
            for md in _shrinkwraps(ob):
                if md.target == target or md.name in names:
                    vg = ob.vertex_groups.get(md.vertex_group) if md.vertex_group else None
                    ob.modifiers.remove(md)
                    if vg is not None:
                        ob.vertex_groups.remove(vg)
                    n += 1
    if not n:
        raise RuntimeError(f"No shrinkwrap deformer is associated with surface "
                           f"{(surfaces[0] if surfaces else target).name if (surfaces or target) else ''}.")
    return n


SW_ACTIONS = ("SET_TARGET", "REMOVE_TARGET", "ADD_SURFACES", "REMOVE_SURFACES")


@undo_steps.no_redo_panel
class ALLSET_OT_shrink_wrap_edit(bpy.types.Operator):
    """Maya Deform > ShrinkWrap > Set Target / Remove Target / Add surfaces / Remove surfaces: surfaces first, the
    target object last"""
    bl_idname = "allset.shrink_wrap_edit"
    bl_label = "ShrinkWrap Edit"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=[(k, k.replace("_", " ").title(), "") for k in SW_ACTIONS], options={'SKIP_SAVE'})

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            shrink_wrap_edit(context, self.action)
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Lattice -------------------------------------------------------------------------------------------------------

def _kit_lattices(context):
    """{lattice object: [lattice modifiers]} for the selected kit lattices / deformed objects."""
    out = {}
    for ob in context.selected_objects:
        if ob.type == 'LATTICE':
            for md in deformers.driven_modifiers(ob):
                out.setdefault(ob, []).append(md)
        for md in getattr(ob, "modifiers", ()):
            if deformers.base_of(md) == "ffd" and md.object is not None:
                out.setdefault(md.object, []).append(md)
    return out


def lattice_edit(context, action):
    """Remove Lattice Tweaks: the lattice points back on its grid (the transform stays); Reset Lattice: also the
    lattice back to its base (Maya ffd1Base; the kit's ``<ffd>Base`` Hook keeps the transform it was made with)."""
    found = _kit_lattices(context)
    if not found:
        raise RuntimeError("Select a lattice or an object it deforms.")
    for lob, mds in found.items():
        for p in lob.data.points:
            p.co_deform = p.co
        if action == "RESET":
            for md in mds:
                hk = md.id_data.modifiers.get(f"{md.name}Base")
                if hk is not None and hk.type == 'HOOK':
                    lob.matrix_world = md.id_data.matrix_world @ hk.matrix_inverse.inverted()
                    break
        lob.data.update_tag()
    return len(found)


@undo_steps.no_redo_panel
class ALLSET_OT_lattice_edit(bpy.types.Operator):
    """Maya Deform > Lattice > Reset Lattice / Remove Lattice Tweaks"""
    bl_idname = "allset.lattice_edit"
    bl_label = "Lattice Edit"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=(('RESET', "Reset Lattice", ""), ('REMOVE_TWEAKS', "Remove Lattice Tweaks", "")),
                         options={'SKIP_SAVE'})

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            lattice_edit(context, self.action)
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Prune Membership -----------------------------------------------------------------------------------------------

PRUNE_NONE = "No components could be pruned."      # Maya's message


def prune(context, kind):
    """Points with weight 0 leave the deformer's vertex group (they don't move: Maya's prune drops points the
    deformer leaves alone). Returns the number of points pruned."""
    cands = deformers._paint_candidates(context)
    n = 0
    for ob, prefer in cands:
        group = deformers.paint_group(ob, kind, prefer)
        vg = ob.vertex_groups.get(group) if group else None
        if vg is None:
            continue
        drop = [v.index for v in ob.data.vertices for g in v.groups if g.group == vg.index and g.weight <= 1e-6]
        if drop:
            vg.remove(drop)
            n += len(drop)
    return n


@undo_steps.no_redo_panel
class ALLSET_OT_prune_membership(bpy.types.Operator):
    """Remove the points this deformer doesn't move (weight 0) from it (Maya Deform > Prune Membership)"""
    bl_idname = "allset.prune_membership"
    bl_label = "Prune Membership"
    bl_options = {'REGISTER', 'UNDO'}

    kind: StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        n = prune(context, self.kind)
        if not n:
            results.result(self, PRUNE_NONE)
            return {'CANCELLED'}
        results.result(self, f"{n} points pruned")
        return {'FINISHED'}


# --- Point On Curve ---------------------------------------------------------------------------------------------------

def point_on_curve(context, weight=1.0):
    """Maya Deform > Point On Curve: a locator at each selected curve point that pulls the curve through it (Maya's
    leastSquaresModifier moves the CVs; the kit hooks the selected control point, ``weight`` = Point weight)."""
    curve = context.active_object
    if curve is None or curve.type != 'CURVE' or context.mode != 'EDIT_CURVE':
        raise RuntimeError("Select an edit point on a curve.")
    bpy.ops.object.mode_set(mode='OBJECT')
    picks = []
    index = 0
    for sp in curve.data.splines:
        if sp.type == 'BEZIER':
            for p in sp.bezier_points:
                if p.select_control_point:
                    picks.append((index + 1, p.co.copy()))      # a Bezier point = 3 hook indices: the knot
                index += 3
        else:
            for p in sp.points:
                if p.select:
                    picks.append((index, p.co.to_3d()))
                index += 1
    if not picks:
        bpy.ops.object.mode_set(mode='EDIT')
        raise RuntimeError("Select an edit point on a curve.")
    made = []
    for idx, co in picks:
        loc = bpy.data.objects.new(deformers.new_name("locator"), None)
        loc.empty_display_type = 'PLAIN_AXES'
        context.view_layer.active_layer_collection.collection.objects.link(loc)
        loc.location = curve.matrix_world @ co
        context.view_layer.update()
        hk = curve.modifiers.new(f"leastSquaresModifier{len(made) + 1}", 'HOOK')
        hk.object = loc
        hk.vertex_indices_set([idx])
        hk.strength = float(weight)
        hk.center = co
        hk.matrix_inverse = loc.matrix_world.inverted() @ curve.matrix_world
        made.append(loc)
    deformers._select_only(context, made, made[-1])                 # Maya: locator1
    return made


@undo_steps.no_redo_panel
class ALLSET_OT_point_on_curve(bpy.types.Operator):
    """A locator on the selected curve point that moves the curve with it (Maya Deform > Point On Curve)"""
    bl_idname = "allset.point_on_curve"
    bl_label = "Point On Curve"
    bl_options = {'REGISTER', 'UNDO'}

    weight: FloatProperty(name="Point weight", default=1.0, min=0.0, max=1.0, options={'SKIP_SAVE'})

    def execute(self, context):
        try:
            point_on_curve(context, self.weight)
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (ALLSET_OT_wire_edit, ALLSET_OT_wire_dropoff_locator, ALLSET_OT_shrink_wrap_edit, ALLSET_OT_lattice_edit,
           ALLSET_OT_prune_membership, ALLSET_OT_point_on_curve)
