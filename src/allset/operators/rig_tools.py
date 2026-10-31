# SPDX-License-Identifier: GPL-3.0-or-later
"""Rigging menu items with Maya meaning.

- Constrain > Parent / Point / Orient / Scale / Aim ...: Maya order (targets, then the constrained node
  last). In pose mode the constraint goes on the active joint (pose bone), the target is the selected
  control object or joint — not on the armature object.
- Modify > Add / Edit / Delete Attribute (Maya Modify menu Attributes section):
  custom properties on the selected objects / joints,
  which the Channel Box shows as channels.
- Deform > Blend Shape: ``object.join_shapes`` (targets selected, base last = Maya's order).
- Skeleton > Quick Rig: Rigify (bundled with Blender), enabled only after the user confirms.
"""

import re

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from mathutils import Vector

from .. import results
from ..ui import channel_box as cb
from . import constrain_multi, maya_errors

CONSTRAINT_TYPES = (
    ('CHILD_OF', "Parent", "Maya parentConstraint (Child Of; the offset is kept like Maya's Maintain Offset)"),
    ('COPY_LOCATION', "Point", "Maya pointConstraint (Copy Location)"),
    ('COPY_ROTATION', "Orient", "Maya orientConstraint (Copy Rotation)"),
    ('COPY_SCALE', "Scale", "Maya scaleConstraint (Copy Scale)"),
    ('TRACK_TO', "Aim", "Maya aimConstraint (Track To: aims +X at the target, +Y up = Blender +X / +Z)"),
    ('FOLLOW_PATH', "Attach to Motion Path", "Maya motion path (Follow Path)"),
    ('SHRINKWRAP', "Geometry", "Maya geometryConstraint (Shrinkwrap)"),
)
CONSTRAIN_HINT = "Select the control first, then the joint last (joints in pose mode)"
# Maya constraint commands that print "Target list was empty or contained no valid targets." with one node selected
# (Parent, Point / Orient / Scale / Aim / Geometry).
# Attach to Motion Path is another command.
MAYA_TARGET_ERROR = {'CHILD_OF', 'COPY_LOCATION', 'COPY_ROTATION', 'COPY_SCALE', 'TRACK_TO', 'SHRINKWRAP'}


class ALLSET_OT_constrain(bpy.types.Operator):
    """Maya Constrain: select the target(s), then the object or joint to constrain last"""
    bl_idname = "allset.constrain"
    bl_label = "Constrain"
    bl_options = {'REGISTER', 'UNDO'}

    type: EnumProperty(items=CONSTRAINT_TYPES, name="Type")
    # Maya option window values for a multi-target constraint (operators/constrain_multi.py); a one-target
    # constraint is set up afterwards by option_windows._constraint as before
    maintain_offset: EnumProperty(name="Maintain Offset", items=(
        ('DEFAULT', "Default", "Like Maya: on for Parent, off for Point / Orient / Scale"),
        ('ON', "On", ""), ('OFF', "Off", "")), default='DEFAULT', options={'SKIP_SAVE', 'HIDDEN'})
    weight: FloatProperty(name="Weight", default=1.0, min=0.0, options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode in {'OBJECT', 'POSE'}

    def execute(self, context):
        label = next(t[1] for t in CONSTRAINT_TYPES if t[0] == self.type)
        arm = cb.pose_armature(context)
        if arm is not None:
            pb = context.active_pose_bone
            others = [o for o in context.selected_objects if o is not arm]
            bones = [b for b in context.selected_pose_bones or () if b != pb]
            if pb is not None and not (others or bones) and self.type in MAYA_TARGET_ERROR:
                self.report({'ERROR'}, maya_errors.NO_TARGETS)       # Maya: one joint selected
                return {'CANCELLED'}
            if pb is None or not (others or bones):
                self.report({'WARNING'}, CONSTRAIN_HINT)
                return {'CANCELLED'}
            targets = ([(o, "") for o in sorted(others, key=lambda o: o.name)]
                       + [(b.id_data, b.name) for b in sorted(bones, key=lambda b: b.name)])
            if self.type in constrain_multi.TYPES and (len(targets) > 1 or any(
                    constrain_multi.needs_joint_axes(pb, t, sub, self.type) for t, sub in targets)):
                # a joint following an object's rotation also goes through the node builder (Maya axes)
                return self._multi(context, pb, targets, label)
            before = len(pb.constraints)
            bpy.ops.pose.constraint_add_with_targets(type=self.type)
            owner, cons = pb.name, pb.constraints
        else:
            ob = context.active_object
            others = [o for o in context.selected_objects if o is not ob]
            if not others and self.type in MAYA_TARGET_ERROR:
                # Maya with one object selected: an Error
                self.report({'ERROR'}, maya_errors.NO_TARGETS)
                return {'CANCELLED'}
            if not others:
                self.report({'WARNING'}, CONSTRAIN_HINT)
                return {'CANCELLED'}
            if len(others) > 1 and self.type in constrain_multi.TYPES:
                # Maya target order: Blender keeps no selection order, targets go by name (modify_maya.selection_order)
                return self._multi(context, ob, [(o, "") for o in sorted(others, key=lambda o: o.name)], label)
            before = len(ob.constraints)
            if bpy.ops.object.constraint_add_with_targets.poll():
                bpy.ops.object.constraint_add_with_targets(type=self.type)
            else:
                # a hidden object: Maya constrains it like any other (Closest Point), Blender's
                # operator refuses it ("Cannot edit hidden object") -> the same constraint through the data API, with
                # the operator's target (the first other selected object)
                con = ob.constraints.new(self.type)
                if hasattr(con, "target"):
                    con.target = others[0]
            owner, cons = ob.name, ob.constraints
        if len(cons) == before:
            self.report({'WARNING'}, CONSTRAIN_HINT)
            return {'CANCELLED'}
        con = cons[-1]
        if arm is not None:
            from .joints import free_location_constrained
            free_location_constrained(context, arm)       # a Maya child joint's translate is free
            cons = arm.pose.bones[owner].constraints       # the edit-mode round trip renews the pose bones
            con = cons[-1]
        if self.type == 'TRACK_TO':
            con = aim(cons, con, bone=arm is not None)     # default aim like Maya (+X at the target, +Y up)
        target = getattr(con, "target", None)
        sub = getattr(con, "subtarget", "")
        results.result(self, f"{label} constraint on {owner}" +
                    (f" (target {target.name}{'.' + sub if sub else ''})" if target else ""))
        return {'FINISHED'}

    def _multi(self, context, owner, targets, label):
        """Maya multi-target constraint: one node, weighted average of the targets."""
        mo = None if self.maintain_offset == 'DEFAULT' else self.maintain_offset == 'ON'
        constrain_multi.build(context, owner, targets, self.type, mo, self.weight)
        names = ", ".join(constrain_multi.target_label(t, sub) for t, sub in targets)
        owner_name = owner.name
        if isinstance(owner, bpy.types.PoseBone):
            # read names first — the edit-mode round trip makes Python's pose bone references stale
            from .joints import free_location_constrained
            free_location_constrained(context, owner.id_data)
        results.result(self, f"{label} constraint on {owner_name} (targets {names})")
        return {'FINISHED'}


# --- Aim (Maya aimConstraint) -----------------------------------------------------------------------

# aimConstraint defaults: aim vector +X, up vector +Y, world up
# type Vector, world up vector (0, 1, 0). Maya is Y-up: an object's Maya X / Y / Z = Blender X / Z / -Y
#; a joint's Maya X / Y / Z = the bone's Y / Z / X (the bone's Y points at the child, Maya's primary X).
AIM_VECTOR, UP_VECTOR, WORLD_UP = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), "Vector"
# Maya aimConstraint world up types (enum order of the node's worldUpType: Scene Up / Object Up / Object Rotation Up /
# Vector / None, command default Vector)
WORLD_UP_TYPES = ("Scene up", "Object up", "Object rotation up", "Vector", "None")
AIM_UP = "allset_aim_up"          # helper empty: name of the aim constraint whose up it carries
UP_SUFFIX = " up"                 # the Locked Track that turns an Object up aim about its aim axis


def local_axis(v, bone=False):
    """Maya local vector -> Blender local vector of an object (X, -Z, Y) or a joint / pose bone (Z, X, Y)."""
    x, y, z = v
    return Vector((z, x, y)) if bone else Vector((x, -z, y))


def axis_of(v):
    """('X' | 'Y' | 'Z', +1 | -1) of an axis-aligned vector, None for any other direction."""
    v = Vector(v)
    if v.length < 1e-9:
        return None
    i = max(range(3), key=lambda k: abs(v[k]))
    if any(abs(v[k]) > 1e-6 * abs(v[i]) for k in range(3) if k != i):
        return None
    return "XYZ"[i], (1 if v[i] > 0 else -1)


def _aim_helper(con, name):
    """Hidden empty for an aim's up (constrain_multi's helper collection; it goes when its aim goes)."""
    owner = constrain_multi.owner_of(con)
    h = bpy.data.objects.new(name, None)
    h.empty_display_size = 0.0
    h.hide_viewport = h.hide_render = h.hide_select = True
    constrain_multi._helper_collection().objects.link(h)
    id_ob, _prefix = constrain_multi._id_and_prefix(owner)
    h[constrain_multi.H_OWNER] = id_ob
    h[constrain_multi.H_BONE] = owner.name if isinstance(owner, bpy.types.PoseBone) else ""
    h[constrain_multi.H_CON] = con.name
    h[AIM_UP] = con.name
    constrain_multi._state["armed"] = True
    return h


def is_up_companion(con):
    t = getattr(con, "target", None)
    return con.type == 'LOCKED_TRACK' and con.name.endswith(UP_SUFFIX) and t is not None and AIM_UP in t.keys()


def aim(cons, con, aim_vector=AIM_VECTOR, up_vector=UP_VECTOR, world_up=WORLD_UP, bone=False, up_object=None,
        world_up_vector=(0.0, 1.0, 0.0)):
    """Make ``con`` (a Track To just added to ``cons``) Maya's aim: the owner's ``aim_vector`` points at the target,
    its ``up_vector`` towards the world up w projected across the aim (Maya aimConstraint). Blender:
    - Scene up / Vector (0, 1, 0): Track To up = world Z (= Maya Y);
    - Vector w / Object rotation up (w = worldUpVector x the up object's matrix): Track To with ``use_target_z`` on a
      hidden empty at the aim target whose Z axis is w;
    - Object up (w = up object position - constrained position; no object = the world origin): Damped
      Track + Locked Track (lock = aim axis, track = up axis) at the up object — the same turn about the aim;
    - None = Damped Track (the shortest turn, like Maya).
    Raises RuntimeError for vectors Blender's constraints can't take."""
    a = axis_of(local_axis(aim_vector, bone))
    if a is None:
        raise RuntimeError("Blender aims along an axis: the aim vector must be +-X, +-Y or +-Z")
    track = ("TRACK_" if a[1] > 0 else "TRACK_NEGATIVE_") + a[0]
    if world_up in ("None", "Object up"):
        damped = cons.new('DAMPED_TRACK')
        damped.target, damped.subtarget, damped.influence = con.target, con.subtarget, con.influence
        name = con.name
        cons.remove(con)
        damped.name = name
        damped.track_axis = track
        if world_up == "None":
            return damped
        u = axis_of(local_axis(up_vector, bone))
        if u is None or u[0] == a[0]:
            raise RuntimeError("Blender turns the up vector along a local axis other than the aim vector's")
        h = _aim_helper(damped, f"{name}_upPoint")
        c = h.constraints.new('COPY_LOCATION')     # the up object's position (none: the world origin)
        if up_object is not None:
            c.target = up_object
        else:
            h.constraints.remove(c)
        lock = cons.new('LOCKED_TRACK')
        lock.name = name + UP_SUFFIX
        lock.target = h
        lock.lock_axis = "LOCK_" + a[0]
        lock.track_axis = ("TRACK_" if u[1] > 0 else "TRACK_NEGATIVE_") + u[0]
        lock.influence = damped.influence
        return damped
    u = axis_of(local_axis(up_vector, bone))
    if u is None or u[1] < 0 or u[0] == a[0]:
        raise RuntimeError("Blender's Track To needs an up vector along a positive local axis other than the aim "
                           "vector's")
    con.track_axis = track
    con.up_axis = "UP_" + u[0]
    w = Vector(world_up_vector)
    if world_up == "Scene up" or (world_up == "Vector" and w.length > 1e-12
                                  and (w.normalized() - Vector((0.0, 1.0, 0.0))).length < 1e-9):
        con.use_target_z = False         # world up = world Z (Maya Y): Maya Scene up / Vector (0, 1, 0)
        return con
    if world_up == "Object rotation up" and up_object is None:
        world_up = "Vector"              # worldUpMatrix unconnected = identity: w = the vector (A11 formula)
    target, sub = con.target, con.subtarget
    h = _aim_helper(con, f"{con.name}_upAxis")
    # the empty's Z axis = w: Vector = the world vector, Object rotation up = the up object's matrix times the vector
    zl = local_axis(world_up_vector, False)
    rot = zl.to_track_quat('Z', 'Y').to_matrix().to_4x4() if zl.length > 1e-12 else Vector((0, 0, 1)).to_track_quat(
        'Z', 'Y').to_matrix().to_4x4()
    h.matrix_basis = rot
    if world_up == "Object rotation up":
        child = h.constraints.new('CHILD_OF')
        child.target = up_object
        child.inverse_matrix.identity()
        child.set_inverse_pending = False
    loc = h.constraints.new('COPY_LOCATION')
    loc.target = target
    if sub:
        loc.subtarget = sub
    con.target = h
    con.subtarget = ""
    con.use_target_z = True
    return con


# --- Blend Shape ------------------------------------------------------------------------------------

# Maya Blend Shape Options with a Blender meaning: BlendShape node
# name (= the base's shape key datablock, Maya blendShapeN when empty), Origin Local / World, Check topology, Delete
# targets. Envelope and In-between have no Blender equivalent (the option window lists them as such).
BLEND_ORIGINS = (("LOCAL", "Local", "Targets match the base vertex by vertex in object space"),
                 ("WORLD", "World", "The targets' placement in the scene counts too"))


def same_topology(a, b):
    """Maya Check topology: the same vertex / edge / face counts and the same face corners."""
    ma, mb = a.data, b.data
    if (len(ma.vertices), len(ma.edges), len(ma.polygons)) != (len(mb.vertices), len(mb.edges), len(mb.polygons)):
        return False
    return all(tuple(pa.vertices) == tuple(pb.vertices) for pa, pb in zip(ma.polygons, mb.polygons))


class ALLSET_OT_blend_shape(bpy.types.Operator):
    """Maya Blend Shape: select the target shapes, then the base mesh last (shape keys on the base)"""
    bl_idname = "allset.blend_shape"
    bl_label = "Blend Shape"
    bl_options = {'REGISTER', 'UNDO'}

    node_name: StringProperty(name="BlendShape node", default="")
    origin: EnumProperty(name="Origin", items=BLEND_ORIGINS, default="LOCAL")
    check_topology: BoolProperty(name="Check topology", default=True)
    delete_targets: BoolProperty(name="Delete targets", default=False)

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH' and context.mode == 'OBJECT'

    def execute(self, context):
        base = context.active_object
        targets = [o for o in context.selected_objects if o is not base and o.type == 'MESH']
        if not targets:
            self.report({'WARNING'}, "Select the target shapes, then the base mesh last")
            return {'CANCELLED'}
        n = len(base.data.vertices)
        bad = [o for o in targets if len(o.data.vertices) != n
               or (self.check_topology and not same_topology(base, o))]
        good = [o for o in targets if o not in bad]
        what = "topology" if self.check_topology and all(len(o.data.vertices) == n for o in bad) else "vertex count"
        if not good:
            self.report({'ERROR'}, f"Blend Shape: {', '.join(o.name for o in bad)} "
                                   f"has a different {what} than {base.name}")
            return {'CANCELLED'}
        for o in bad:
            o.select_set(False)
        new_key = base.data.shape_keys is None
        bpy.ops.object.join_shapes()
        key = base.data.shape_keys
        if self.origin == "WORLD":
            to_base = base.matrix_world.inverted()
            for o, kb in zip(good, list(key.key_blocks)[-len(good):]):
                m = to_base @ o.matrix_world
                for i, v in enumerate(o.data.vertices):
                    kb.data[i].co = m @ v.co
        if self.node_name:
            key.name = self.node_name
        elif new_key:
            from . import naming
            taken = {k.name for k in bpy.data.shape_keys if k != key}
            key.name = f"blendShape{naming.next_number('blendShape', taken)}"
        names = [o.name for o in good]
        if self.delete_targets:
            for o in good:
                bpy.data.objects.remove(o)
        msg = f"Blend Shape {key.name} on {base.name}: {', '.join(names)}"
        if bad:
            msg += f" (skipped, different {what}: {', '.join(o.name for o in bad)})"
        self.report({'WARNING'} if bad else {'INFO'}, msg)
        return {'FINISHED'}


# --- Quick Rig -> Rigify ---------------------------------------------------------------------------

RIGIFY = "rigify"
QUICK_RIG_TEXT = ("Blender has no Quick Rig / HumanIK. Rigify (bundled with Blender) adds a human "
                  "meta-rig: fit its guides to the mesh, then Generate Rig (no automatic fitting).")


class ALLSET_OT_quick_rig(bpy.types.Operator):
    """Maya Quick Rig with Blender's Rigify: add a human meta-rig to fit to the mesh, then Generate Rig"""
    bl_idname = "allset.quick_rig"
    bl_label = "Quick Rig (Rigify)"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        if RIGIFY not in context.preferences.addons:
            return context.window_manager.invoke_confirm(
                self, event, title="Enable Rigify?", confirm_text="Enable Rigify",
                message="Quick Rig uses Rigify, an add-on bundled with Blender. Enable it (your "
                        "add-on list changes) and add a human meta-rig?")
        return self.execute(context)

    def execute(self, context):
        if RIGIFY not in context.preferences.addons:
            import addon_utils
            addon_utils.enable(RIGIFY, default_set=True)
            if RIGIFY not in context.preferences.addons:
                self.report({'ERROR'}, "Rigify could not be enabled")
                return {'CANCELLED'}
        if context.mode != 'OBJECT' and context.active_object is not None:
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.armature_human_metarig_add()
        results.result(self, QUICK_RIG_TEXT)
        return {'FINISHED'}


# --- Add / Edit / Delete Attribute ---------------------------------------------------------------

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DATA_TYPES = (('FLOAT', "Float", "Maya double / float"), ('INT', "Integer", "Maya long"),
              ('BOOL', "Boolean", "Maya bool"))


def custom_nodes(context):
    return cb.targets(context)


def selected_custom(context, node):
    return [k[len(cb.CUSTOM_PREFIX):] for k in cb.selected_channels(context)
            if k.startswith(cb.CUSTOM_PREFIX) and k[len(cb.CUSTOM_PREFIX):] in node.keys()]


def set_limits(node, name, kind, use_min, minimum, use_max, maximum, default):
    if kind == 'BOOL':
        node.id_properties_ui(name).update(default=bool(default))
        return
    cast = int if kind == 'INT' else float
    big = 2 ** 31 - 1 if kind == 'INT' else 3.4e38
    lo = cast(minimum) if use_min else -big
    hi = cast(maximum) if use_max else big
    node.id_properties_ui(name).update(min=lo, max=hi, soft_min=lo, soft_max=hi, default=cast(default))


def limits(node, name):
    """(kind, use_min, min, use_max, max, default) of a custom property."""
    value = node[name]
    kind = 'BOOL' if isinstance(value, bool) else 'INT' if isinstance(value, int) else 'FLOAT'
    data = node.id_properties_ui(name).as_dict()
    big = 1e30
    lo, hi = data.get("min", -big), data.get("max", big)
    return (kind, lo > -big and abs(lo) < 2 ** 31 - 1, lo, hi < big and abs(hi) < 2 ** 31 - 1, hi,
            data.get("default", value))


class _AttributeLimits:
    data_type: EnumProperty(items=DATA_TYPES, name="Data Type", default='FLOAT')
    use_min: BoolProperty(name="Minimum", description="Limit the value from below")
    minimum: FloatProperty(name="Minimum", default=0.0)
    use_max: BoolProperty(name="Maximum", description="Limit the value from above")
    maximum: FloatProperty(name="Maximum", default=1.0)
    default: FloatProperty(name="Default", default=0.0)

    def draw_limits(self, layout):
        if self.data_type == 'BOOL':
            layout.prop(self, "default", text="Default (0 / 1)")
            return
        for use, value in (("use_min", "minimum"), ("use_max", "maximum")):
            row = layout.row(align=True)
            row.prop(self, use, text="")
            sub = row.row(align=True)
            sub.active = getattr(self, use)
            sub.prop(self, value)
        layout.prop(self, "default")


class ALLSET_OT_add_attribute(_AttributeLimits, bpy.types.Operator):
    """Maya Add Attribute: a new keyable attribute on the selected objects / joints (a Channel Box channel)"""
    bl_idname = "allset.add_attribute"
    bl_label = "Add Attribute"
    bl_options = {'REGISTER', 'UNDO'}

    long_name: StringProperty(name="Long name", description="Letters, digits and _ (Maya attribute name)")

    @classmethod
    def poll(cls, context):
        return cb.lead(context) is not None

    def invoke(self, context, event):
        node = cb.lead(context)
        return context.window_manager.invoke_props_dialog(self, title=f"Add Attribute: {node.name}",
                                                          confirm_text="OK", width=320)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "long_name")
        lay.row().prop(self, "data_type", expand=True)
        lay.label(text="Numeric Attribute Properties")
        self.draw_limits(lay)

    def execute(self, context):
        name = self.long_name.strip()
        if not NAME_RE.match(name) or name.startswith("allset_"):
            self.report({'ERROR'}, f"Add Attribute: '{name}' is not a valid attribute name "
                                   "(letters, digits and _, not starting with a digit)")
            return {'CANCELLED'}
        nodes = custom_nodes(context)
        added = []
        for node in nodes:
            if name in node.keys():
                self.report({'WARNING'}, f"{node.name} already has an attribute '{name}'")
                continue
            value = self.default
            if self.data_type != 'BOOL':
                if self.use_min:
                    value = max(value, self.minimum)
                if self.use_max:
                    value = min(value, self.maximum)
            node[name] = bool(value) if self.data_type == 'BOOL' else int(value) if self.data_type == 'INT' \
                else float(value)
            set_limits(node, name, self.data_type, self.use_min, self.minimum, self.use_max, self.maximum,
                       value)
            added.append(node.name)
        if not added:
            return {'CANCELLED'}
        cb.rebuild_rows()
        results.result(self, f"Added {cb.nice_name(name)} to {', '.join(added)}")
        return {'FINISHED'}


def _rename_paths(ob, old, new, prefix=""):
    """Animation / driver paths of ``prefix["old"]`` on the object -> ``prefix["new"]``."""
    a, b = f'{prefix}["{old}"]', f'{prefix}["{new}"]'
    ad = ob.animation_data
    if ad is None:
        return
    from .. import compat
    fcs = list(ad.drivers) + compat.id_fcurves(ob)
    for fc in fcs:
        if fc.data_path == a:
            fc.data_path = b


def _rename_driver_targets(id_data, old_path, new_path):
    for ob in bpy.data.objects:
        ad = ob.animation_data
        for fc in (ad.drivers if ad else ()):
            for var in fc.driver.variables:
                for t in var.targets:
                    if t.id == id_data and t.data_path == old_path:
                        t.data_path = new_path


class ALLSET_OT_edit_attribute(_AttributeLimits, bpy.types.Operator):
    """Maya Edit Attribute: rename the attribute selected in the Channel Box and change its limits"""
    bl_idname = "allset.edit_attribute"
    bl_label = "Edit Attribute"
    bl_options = {'REGISTER', 'UNDO'}

    attribute: StringProperty(name="Attribute", options={'SKIP_SAVE'})
    long_name: StringProperty(name="Long name")

    @classmethod
    def poll(cls, context):
        node = cb.lead(context)
        return node is not None and bool(selected_custom(context, node))

    def invoke(self, context, event):
        node = cb.lead(context)
        self.attribute = selected_custom(context, node)[0]
        self.long_name = self.attribute
        (self.data_type, self.use_min, lo, self.use_max, hi, default) = limits(node, self.attribute)
        self.minimum, self.maximum = (lo if self.use_min else 0.0), (hi if self.use_max else 1.0)
        self.default = float(default)
        return context.window_manager.invoke_props_dialog(
            self, title=f"Edit Attribute: {node.name}.{self.attribute}", confirm_text="OK", width=320)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "long_name")
        lay.label(text="Numeric Attribute Properties")
        self.draw_limits(lay)

    def execute(self, context):
        old, new = self.attribute, self.long_name.strip()
        if not old:
            node = cb.lead(context)
            names = selected_custom(context, node) if node else []
            if not names:
                return {'CANCELLED'}
            old = names[0]
            new = new or old
        if not NAME_RE.match(new):
            self.report({'ERROR'}, f"Edit Attribute: '{new}' is not a valid attribute name")
            return {'CANCELLED'}
        for node in custom_nodes(context):
            if old not in node.keys():
                continue
            if new != old:
                if new in node.keys():
                    self.report({'WARNING'}, f"{node.name} already has an attribute '{new}'")
                    continue
                ui = node.id_properties_ui(old).as_dict()
                node[new] = node[old]
                node.id_properties_ui(new).update(**{k: v for k, v in ui.items() if k != "subtype"})
                del node[old]
                ob = node.id_data
                prefix = node.path_from_id() if cb.is_bone(node) else ""
                _rename_paths(ob, old, new, prefix)
                _rename_driver_targets(ob, f'{prefix}["{old}"]', f'{prefix}["{new}"]')
            set_limits(node, new, self.data_type, self.use_min, self.minimum, self.use_max, self.maximum,
                       self.default)
        cb.set_selected_channels([cb.CUSTOM_PREFIX + new if k == cb.CUSTOM_PREFIX + old else k
                                  for k in cb.selected_channels(context)], context)
        return {'FINISHED'}


class ALLSET_OT_delete_attribute(bpy.types.Operator):
    """Maya Delete Attribute: delete the attributes selected in the Channel Box (with their keys and drivers)"""
    bl_idname = "allset.delete_attribute"
    bl_label = "Delete Attribute"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        node = cb.lead(context)
        return node is not None and bool(selected_custom(context, node))

    def execute(self, context):
        names = selected_custom(context, cb.lead(context))
        count = 0
        for node in custom_nodes(context):
            for name in names:
                if name not in node.keys():
                    continue
                key = cb.CUSTOM_PREFIX + name
                ad = node.id_data.animation_data
                fc = cb.driver(node, key)
                if fc is not None:
                    ad.drivers.remove(fc)
                fc = cb.fcurve(node, key)
                if fc is not None:
                    cb._fcurves(node).remove(fc)   # the whole curve, not just this frame's key
                del node[name]
                count += 1
        cb.set_selected_channels([k for k in cb.selected_channels(context)
                                  if k[len(cb.CUSTOM_PREFIX):] not in names], context)
        results.result(self, f"Deleted {count} attribute(s)")
        return {'FINISHED'}


classes = (ALLSET_OT_constrain, ALLSET_OT_blend_shape, ALLSET_OT_quick_rig, ALLSET_OT_add_attribute,
           ALLSET_OT_edit_attribute, ALLSET_OT_delete_attribute)
