# SPDX-License-Identifier: GPL-3.0-or-later
"""Pose Space Deformation (Pose Interpolator, Pose Editor).

Maya: Deform > Pose
Space Deformation > Create Pose Interpolator on a joint makes ``<joint>_poseInterpolator`` (driver = the joint, factory
Create neutral poses on, Driver twist axis X, interpolation Linear). A pose = the joint's rotation when it was added;
``poseInterpolatorAddShapePose`` makes a blendShape target named after the pose whose weight is the interpolator's
output, in front of the skinCluster. With Linear and one pose at rz -90 the pose weight is linear in
the **swing** angle between neutral and the pose (rz -5 -> 0.055556, -45 -> 0.5, -90 -> 1.0) and ignores twist about
the driver twist axis ((10..90, 0, -45) -> 0.5, (30, 0, 0) -> 0).

Kit: shape keys + **simple-expression drivers** (no Python auto-run needed):
- interpolator node = an Empty ``<joint>_poseInterpolator`` (display size 0: nothing in the viewport, listed in the
  Outliner like Maya's node) holding ID props (``P_*``); its custom property ``<pose>`` = the pose's output weight
  (Maya ``output[i]``), driven;
- a hidden "tip" Empty parented to the driver bone at the point the twist axis points to (twist X = the bone's tail),
  and per pose a hidden Empty parented to the bone's parent (the armature object for a root bone) left where the tip
  was when the pose was added; both live in ``.AllsetPoseHelpers`` (no scene, fake user — drivers still evaluate them);
- the weight driver: d = LOC_DIFF(tip, pose helper) (world), angle to the pose phi = 2 asin(min(1, d / 2r)),
  weight = max(0, 1 - phi / theta0) with r = head -> tip length and theta0 = the neutral -> pose angle (inline
  constants). Twist about the twist axis doesn't move the tip, so it is ignored like Maya; inside the neutral -> pose
  arc the weight equals Maya's swing ratio exactly. Outside it (past the pose, the other side of neutral, swing in
  another plane) and with several poses Maya's RBF differs (tests/test_step227_pose.py prints the deviations);
- Add Shape = a shape key named after the pose on the skinned mesh, value driver ``w`` = the interpolator's
  ``["<pose>"]`` (Maya connects the output straight to the target weight). Blender shape keys evaluate before every
  modifier, so the corrective sits in front of the Armature modifier like Maya's frontOfChain blendShape.
Maya also outputs neutral / neutralSwing / neutralTwist weights: the kit keeps the neutral pose (Go to Pose) but no
weights for it.
"""


import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from mathutils import Matrix, Vector

MARK = "allset_pose_interpolator"       # on the interpolator Empty: 1
P_ARM = "allset_pi_armature"            # driver armature object
P_BONE = "allset_pi_bone"               # driver bone name
P_TIP = "allset_pi_tip"                 # tip helper Empty
P_AXIS = "allset_pi_twist_axis"         # Maya driver twist axis 0 X / 1 Y / 2 Z
P_NEUTRAL = "allset_pi_neutral"         # {"basis": 16 floats, "tip": 3 floats in the parent space}
P_POSES = "allset_pi_poses"             # {pose: {"helper", "theta0", "basis", "shapes": {"<n>": {"ob", "key"}}}}
P_INTERP = "allset_pi_interpolation"    # Maya interpolation 0 Linear / 1 Gaussian (the kit computes Linear only)
H_OWNER = "allset_pose_helper_of"       # on a helper Empty: its interpolator
HELPERS = ".AllsetPoseHelpers"
SUFFIX = "_poseInterpolator"
NEUTRAL = "neutral"
TWIST_AXES = (('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""))


# --- model ------------------------------------------------------------------------------------------------------------

def is_interpolator(ob):
    return ob is not None and ob.type == 'EMPTY' and bool(ob.get(MARK))


def interpolators():
    return sorted((ob for ob in bpy.data.objects if is_interpolator(ob)), key=lambda o: o.name)


def driver_of(interp):
    """(armature object, pose bone) driving ``interp``, or (None, None)."""
    arm = interp.get(P_ARM)
    if arm is None or arm.pose is None:
        return None, None
    return arm, arm.pose.bones.get(interp.get(P_BONE, ""))


def poses(interp):
    """The user poses' names in creation order."""
    group = interp.get(P_POSES)
    return list(group.keys()) if group is not None else []


def pose_record(interp, name):
    group = interp.get(P_POSES)
    return group.get(name) if group is not None else None


def weight(interp, name):
    """The pose's output weight (the driven ``["<pose>"]`` property)."""
    try:
        return float(interp[name])
    except (KeyError, TypeError, ValueError):
        return 0.0


def _axis_local(pb, axis):
    """Tip offset in the bone's tail frame (BONE parenting puts a child at the tail): the twist axis tip at the
    bone's length from the head. Maya joint X / Y / Z = bone Y / Z / X."""
    length = pb.bone.length
    if axis == 0:
        return Vector((0.0, 0.0, 0.0))
    if axis == 1:
        return Vector((0.0, -length, length))
    return Vector((length, -length, 0.0))


def _tail_frame(arm, pb):
    """World matrix a BONE-parented child of ``pb`` lives in (the bone's pose matrix moved to its tail)."""
    return arm.matrix_world @ pb.matrix @ Matrix.Translation((0.0, pb.length, 0.0))


def _parent_frame(arm, pb):
    """World matrix of the space the pose helpers live in: the parent bone's tail frame, else the armature."""
    if pb.parent is not None:
        return _tail_frame(arm, pb.parent)
    return arm.matrix_world.copy()


def _tip_world(arm, pb, axis):
    return _tail_frame(arm, pb) @ _axis_local(pb, axis)


def _in_parent(arm, pb, world_point):
    return _parent_frame(arm, pb).inverted_safe() @ world_point


def _head_world(arm, pb):
    return arm.matrix_world @ pb.head


def _helper_collection():
    coll = bpy.data.collections.get(HELPERS)
    if coll is None:
        coll = bpy.data.collections.new(HELPERS)
        coll.use_fake_user = True         # in no scene: not in the Outliner / exports; drivers still evaluate it
    return coll


def _helper(name, arm, parent_bone, local, interp):
    h = bpy.data.objects.new(name, None)
    h.empty_display_size = 0.0
    h.hide_viewport = h.hide_render = h.hide_select = True
    _helper_collection().objects.link(h)
    h.parent = arm
    if parent_bone is not None:
        h.parent_type = 'BONE'
        h.parent_bone = parent_bone.name
    h.matrix_parent_inverse = Matrix.Identity(4)
    h.location = local
    h[H_OWNER] = interp
    return h


def _flat(m):
    return [m[i][j] for i in range(4) for j in range(4)]


def _matrix(values):
    v = list(values)
    return Matrix([v[0:4], v[4:8], v[8:12], v[12:16]])


def _angle(a, b):
    if a.length < 1e-9 or b.length < 1e-9:
        return 0.0
    return a.angle(b)


def _update(context=None):
    (context or bpy.context).view_layer.update()


def interpolator_name(bone_name):
    """Maya ``<joint>_poseInterpolator`` (then ``…1``, ``…2`` when taken, Maya's rename rule)."""
    base = bone_name + SUFFIX
    if base not in bpy.data.objects:
        return base
    from . import naming
    return f"{base}{naming.next_number(base, {o.name for o in bpy.data.objects})}"


def create(context, arm, pb, twist_axis=0):
    """Maya Pose Editor Create Pose Interpolator (``<joint>_poseInterpolator``, twist axis): the node + the neutral pose
    (= the bone's pose now, Maya Create neutral poses on)."""
    _update(context)
    interp = bpy.data.objects.new(interpolator_name(pb.name), None)
    interp.empty_display_size = 0.0          # Maya's poseInterpolator shape draws nothing in the viewport
    context.scene.collection.objects.link(interp)
    interp[MARK] = 1
    interp[P_ARM] = arm
    interp[P_BONE] = pb.name
    interp[P_AXIS] = int(twist_axis)
    interp[P_INTERP] = 0
    tip = _helper(f"{interp.name}_tip", arm, pb, _axis_local(pb, twist_axis), interp)
    interp[P_TIP] = tip
    interp[P_NEUTRAL] = {"basis": _flat(pb.matrix_basis),
                         "tip": list(_in_parent(arm, pb, _tip_world(arm, pb, twist_axis)))}
    interp[P_POSES] = {}
    return interp


def _expression(two_r, theta0):
    return f"max(0, 1 - 2*asin(min(1, d/{two_r!r}))/{theta0!r})"


def add_pose(context, interp, name):
    """``poseInterpolatorAddPose``: the bone's pose now becomes pose ``name``; its weight driver is built from the
    neutral -> pose angle. Returns the pose name, or raises ValueError (no driver, pose = neutral, name taken)."""
    arm, pb = driver_of(interp)
    if pb is None:
        raise ValueError("The pose interpolator has no driver joint.")
    if not name or name == NEUTRAL or name in poses(interp) or name.startswith("allset_"):
        raise ValueError(f"A pose named '{name}' already exists.")
    _update(context)
    axis = int(interp.get(P_AXIS, 0))
    tip_w = _tip_world(arm, pb, axis)
    head_p = _in_parent(arm, pb, _head_world(arm, pb))
    neutral_p = Vector(interp[P_NEUTRAL]["tip"])
    pose_p = _in_parent(arm, pb, tip_w)
    theta0 = _angle(neutral_p - head_p, pose_p - head_p)
    if theta0 < 1e-4:
        raise ValueError("The pose is the same as the neutral pose: rotate the joint first.")
    r = (tip_w - _head_world(arm, pb)).length
    helper = _helper(f"{interp.name}_{name}", arm, pb.parent, pose_p, interp)
    group = interp[P_POSES]
    group[name] = {"helper": helper, "theta0": theta0, "two_r": 2.0 * r, "basis": _flat(pb.matrix_basis),
                   "shapes": {}}
    interp[name] = 0.0
    fc = interp.driver_add(f'["{name}"]')
    drv = fc.driver
    drv.type = 'SCRIPTED'
    for v in list(drv.variables):
        drv.variables.remove(v)
    var = drv.variables.new()
    var.name = "d"
    var.type = 'LOC_DIFF'
    var.targets[0].id = interp[P_TIP]
    var.targets[1].id = helper
    drv.expression = _expression(2.0 * r, theta0)
    _update(context)
    return name


def next_pose_name(interp):
    from . import naming
    taken = set(poses(interp))
    return f"pose{naming.next_number('pose', taken)}"


def skinned_meshes(arm):
    """Meshes an Armature modifier of ``arm`` deforms (Maya: the geometry the skinCluster drives)."""
    return [ob for ob in bpy.data.objects if ob.type == 'MESH'
            and any(m.type == 'ARMATURE' and m.object == arm for m in ob.modifiers)]


def shapes_of(interp, name):
    """[(mesh object, key block name)] of the pose's corrective shapes."""
    rec = pose_record(interp, name)
    if rec is None:
        return []
    out = []
    for item in rec["shapes"].values():
        ob = item.get("ob")
        if ob is not None and ob.data.shape_keys is not None and item["key"] in ob.data.shape_keys.key_blocks:
            out.append((ob, item["key"]))
    return out


def add_shape(context, interp, name, mesh):
    """``poseInterpolatorAddShapePose <interp> <pose> "swing" {blendShape}``: shape key ``<pose>`` on ``mesh`` whose
    value is the pose weight. Returns the key block."""
    rec = pose_record(interp, name)
    if rec is None:
        raise ValueError(f"No pose named '{name}'.")
    for ob, key in shapes_of(interp, name):
        if ob == mesh:
            return ob.data.shape_keys.key_blocks[key]
    if mesh.data.shape_keys is None:
        mesh.shape_key_add(name="Basis", from_mix=False)
        mesh.data.shape_keys.name = _blend_shape_name()
    kb = mesh.shape_key_add(name=name, from_mix=False)
    kb.slider_min, kb.slider_max = 0.0, 1.0
    fc = kb.driver_add("value")
    drv = fc.driver
    drv.type = 'SCRIPTED'
    for v in list(drv.variables):
        drv.variables.remove(v)
    var = drv.variables.new()
    var.name = "w"
    var.type = 'SINGLE_PROP'
    var.targets[0].id_type = 'OBJECT'
    var.targets[0].id = interp
    var.targets[0].data_path = f'["{name}"]'
    drv.expression = "w"
    shapes = rec["shapes"]
    shapes[str(len(shapes))] = {"ob": mesh, "key": kb.name}
    _update(context)
    return kb


def _blend_shape_name():
    """The Key datablock = Maya's blendShape node (``blendShapeN``, one past the highest)."""
    from . import naming
    return f"blendShape{naming.next_number('blendShape', {k.name for k in bpy.data.shape_keys})}"


def go_to_pose(context, interp, name):
    """Put the driver joint in pose ``name`` (or the neutral pose)."""
    arm, pb = driver_of(interp)
    if pb is None:
        return False
    rec = interp[P_NEUTRAL] if name == NEUTRAL else pose_record(interp, name)
    if rec is None:
        return False
    pb.matrix_basis = _matrix(rec["basis"])
    _update(context)
    return True


def _remove_shape_driver(ob, key):
    sk = ob.data.shape_keys
    if sk is None or key not in sk.key_blocks:
        return
    kb = sk.key_blocks[key]
    try:
        kb.driver_remove("value")
    except TypeError:
        pass
    kb.value = 0.0


def delete_pose(interp, name):
    """Remove pose ``name``: its helper and drivers; the corrective shape keys stay (Maya keeps the blendShape target)
    with weight 0."""
    rec = pose_record(interp, name)
    if rec is None:
        return False
    for ob, key in shapes_of(interp, name):
        _remove_shape_driver(ob, key)
    try:
        interp.driver_remove(f'["{name}"]')
    except TypeError:
        pass
    helper = rec.get("helper")
    del interp[P_POSES][name]
    if name in interp:
        del interp[name]
    if helper is not None:
        bpy.data.objects.remove(helper)
    return True


def delete(interp):
    """Delete the interpolator node: every pose, the tip helper and the node."""
    for name in poses(interp):
        delete_pose(interp, name)
    tip = interp.get(P_TIP)
    if tip is not None:
        bpy.data.objects.remove(tip)
    bpy.data.objects.remove(interp)
    coll = bpy.data.collections.get(HELPERS)
    if coll is not None and not coll.objects:
        bpy.data.collections.remove(coll)


def selected_joint(context):
    """(armature object, pose bone) of the selected joint: the active pose bone, else an armature's active bone."""
    pb = getattr(context, "active_pose_bone", None)
    if pb is not None:
        return pb.id_data, pb
    ob = context.active_object
    if ob is not None and ob.type == 'ARMATURE' and ob.data.bones.active is not None:
        return ob, ob.pose.bones.get(ob.data.bones.active.name)
    return None, None


# --- current row (Pose Editor) ----------------------------------------------------------------------------------------

def current(context):
    """(interpolator, pose name or "") picked in the Pose Editor; the only / first interpolator when none."""
    wm = context.window_manager
    interp = bpy.data.objects.get(wm.allset_pe_current)
    if not is_interpolator(interp):
        items = interpolators()
        interp = items[0] if items else None
    if interp is None:
        return None, ""
    name = wm.allset_pe_pose
    return interp, (name if name == NEUTRAL or name in poses(interp) else "")


def _redraw(context):
    from ..ui import pose_editor
    pose_editor.redraw(context)


def _resolve(self, context):
    interp = bpy.data.objects.get(self.interpolator) if self.interpolator else current(context)[0]
    return interp if is_interpolator(interp) else None


# --- operators ------------------------------------------------------------------------------------------------------

class ALLSET_OT_pose_interpolator_create(bpy.types.Operator):
    """Create a pose interpolator on the selected joint (Maya Deform > Pose Space Deformation > Create Pose
    Interpolator)"""
    bl_idname = "allset.pose_interpolator_create"
    bl_label = "Create Pose Interpolator"
    bl_options = {'UNDO'}

    neutral: BoolProperty(name="Create neutral poses", default=True, options={'SKIP_SAVE'})
    twist_axis: EnumProperty(name="Driver twist axis", items=TWIST_AXES, default='X')
    option_box: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        if self.option_box:
            return context.window_manager.invoke_props_dialog(self, title="Create Pose Interpolator Options",
                                                              confirm_text="Create")
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        row = layout.row()
        row.enabled = False      # the kit always keeps the neutral pose: its weights are taken from it
        row.prop(self, "neutral")
        layout.row().prop(self, "twist_axis", expand=True)

    def execute(self, context):
        arm, pb = selected_joint(context)
        if pb is None:
            self.report({'WARNING'}, "Select a joint to create a pose interpolator.")
            return {'CANCELLED'}
        interp = create(context, arm, pb, twist_axis=('X', 'Y', 'Z').index(self.twist_axis))
        context.window_manager.allset_pe_current = interp.name
        context.window_manager.allset_pe_pose = ""
        from .. import results
        results.result(self, interp.name)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_pose_editor(bpy.types.Operator):
    """Open the Pose Editor: pose interpolators, their poses and corrective shapes (Maya Windows > Animation Editors >
    Pose Editor)"""
    bl_idname = "allset.pose_editor"
    bl_label = "Pose Editor"

    def execute(self, context):
        from ..ui import marked_window, pose_editor
        if context.window is None:
            return {'CANCELLED'}
        if marked_window.open_window(context, pose_editor.KIND) is None:
            from ..ui import window_places
            if not window_places.deferred():     # opens on a later tick (#203)
                self.report({'ERROR'}, "Could not open the Pose Editor window")
            return {'CANCELLED'}
        return {'FINISHED'}


class _PoseOp:
    interpolator: StringProperty(options={'SKIP_SAVE'})
    pose: StringProperty(options={'SKIP_SAVE'})

    def _target(self, context):
        interp = _resolve(self, context)
        name = self.pose or (current(context)[1] if interp is not None else "")
        return interp, name


class ALLSET_OT_pose_pick(_PoseOp, bpy.types.Operator):
    """Make this the Pose Editor's current row"""
    bl_idname = "allset.pose_pick"
    bl_label = "Pick"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        wm = context.window_manager
        wm.allset_pe_current = self.interpolator
        wm.allset_pe_pose = self.pose
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_pose_add(_PoseOp, bpy.types.Operator):
    """Add the driver joint's current pose to the pose interpolator (Maya Pose Editor > Add Pose)"""
    bl_idname = "allset.pose_add"
    bl_label = "Add Pose"
    bl_options = {'UNDO'}

    name: StringProperty(name="Pose name", options={'SKIP_SAVE'})

    def invoke(self, context, event):
        interp = _resolve(self, context)
        if interp is None:
            return self.execute(context)
        if not self.name:
            self.name = next_pose_name(interp)
        return context.window_manager.invoke_props_dialog(self, title="Add Pose", confirm_text="Add")

    def execute(self, context):
        interp = _resolve(self, context)
        if interp is None:
            self.report({'WARNING'}, "Create or select a pose interpolator first.")
            return {'CANCELLED'}
        try:
            name = add_pose(context, interp, self.name or next_pose_name(interp))
        except ValueError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        context.window_manager.allset_pe_current = interp.name
        context.window_manager.allset_pe_pose = name
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_pose_add_shape(_PoseOp, bpy.types.Operator):
    """Add a corrective shape for this pose on the skinned mesh, then sculpt it in the pose (Maya Pose Editor > Add
    Shape)"""
    bl_idname = "allset.pose_add_shape"
    bl_label = "Add Shape"
    bl_options = {'UNDO'}

    mesh: StringProperty(options={'SKIP_SAVE'})
    edit: BoolProperty(default=True, options={'SKIP_SAVE'})

    def _mesh(self, context, arm):
        if self.mesh:
            return bpy.data.objects.get(self.mesh)
        meshes = skinned_meshes(arm)
        for ob in getattr(context, "selected_objects", ()):
            if ob in meshes:
                return ob
        return meshes[0] if meshes else None

    def execute(self, context):
        interp, name = self._target(context)
        if interp is None or name in ("", NEUTRAL):
            self.report({'WARNING'}, "Select a pose in the Pose Editor first.")
            return {'CANCELLED'}
        arm, _pb = driver_of(interp)
        mesh = self._mesh(context, arm)
        if mesh is None or mesh.type != 'MESH':
            self.report({'WARNING'}, "No skinned mesh for this pose interpolator's joint.")
            return {'CANCELLED'}
        add_shape(context, interp, name, mesh)
        if self.edit:
            edit_shape(context, interp, name, mesh, on=True)
        _redraw(context)
        return {'FINISHED'}


def editing(interp, name):
    """The (mesh, key) of the pose being sculpted, else None."""
    for ob, key in shapes_of(interp, name):
        if ob.mode == 'EDIT' and ob.active_shape_key is not None and ob.active_shape_key.name == key:
            return ob, key
    return None


def edit_shape(context, interp, name, mesh=None, on=True):
    """Maya Edit: go to the pose, make the corrective the active shape key and sculpt it on the posed mesh (Edit Mode
    with the Armature modifier on the cage; Blender maps the moves back into the key). ``on=False`` leaves Edit Mode."""
    found = [(ob, key) for ob, key in shapes_of(interp, name) if mesh is None or ob == mesh]
    if not found:
        return False
    ob, key = found[0]
    if context.object is not None and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    if not on:
        return True
    go_to_pose(context, interp, name)
    for o in context.scene.objects:
        o.select_set(o == ob)
    context.view_layer.objects.active = ob
    ob.active_shape_key_index = list(ob.data.shape_keys.key_blocks.keys()).index(key)
    ob.use_shape_key_edit_mode = True
    for m in ob.modifiers:
        if m.type == 'ARMATURE':
            m.show_in_editmode = m.show_on_cage = True
    bpy.ops.object.mode_set(mode='EDIT')
    return True


class ALLSET_OT_pose_edit(_PoseOp, bpy.types.Operator):
    """Sculpt this pose's corrective shape in the pose (Maya Pose Editor > Edit); again = done"""
    bl_idname = "allset.pose_edit"
    bl_label = "Edit"
    bl_options = {'UNDO'}

    def execute(self, context):
        interp, name = self._target(context)
        if interp is None or not shapes_of(interp, name):
            self.report({'WARNING'}, "This pose has no shape: Add Shape first.")
            return {'CANCELLED'}
        edit_shape(context, interp, name, on=editing(interp, name) is None)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_pose_go(_PoseOp, bpy.types.Operator):
    """Put the driver joint in this pose (Maya Pose Editor > Go to Pose)"""
    bl_idname = "allset.pose_go"
    bl_label = "Go to Pose"
    bl_options = {'UNDO'}

    def execute(self, context):
        interp, name = self._target(context)
        if interp is None or not go_to_pose(context, interp, name or NEUTRAL):
            return {'CANCELLED'}
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_pose_delete(_PoseOp, bpy.types.Operator):
    """Delete this pose (its corrective shape stays, at weight 0) or, with no pose picked, the pose interpolator"""
    bl_idname = "allset.pose_delete"
    bl_label = "Delete"
    bl_options = {'UNDO'}

    def execute(self, context):
        interp, name = self._target(context)
        if interp is None or name == NEUTRAL:
            return {'CANCELLED'}
        if name:
            delete_pose(interp, name)
            context.window_manager.allset_pe_pose = ""
        else:
            delete(interp)
            context.window_manager.allset_pe_current = ""
        _redraw(context)
        return {'FINISHED'}


def _ui_classes():
    from ..ui import pose_editor
    return pose_editor.classes


classes = (ALLSET_OT_pose_interpolator_create, ALLSET_OT_pose_editor, ALLSET_OT_pose_pick, ALLSET_OT_pose_add,
           ALLSET_OT_pose_add_shape, ALLSET_OT_pose_edit, ALLSET_OT_pose_go, ALLSET_OT_pose_delete) + _ui_classes()

_WM_PROPS = ("allset_pe_current", "allset_pe_pose")


def register_props():
    wm = bpy.types.WindowManager
    wm.allset_pe_current = StringProperty(name="Pose Editor interpolator", description="The Pose Editor's current "
                                          "pose interpolator")
    wm.allset_pe_pose = StringProperty(name="Pose Editor pose", description="The Pose Editor's current pose")
    from ..ui import notices, pose_editor
    notices.PANEL_NOTICES.update(pose_editor.NOTICES)


def unregister_props():
    from ..ui import notices, pose_editor
    for key in pose_editor.NOTICES:
        notices.PANEL_NOTICES.pop(key, None)
    for name in _WM_PROPS:
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
