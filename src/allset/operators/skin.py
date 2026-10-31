# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya IK handles and skinning: IK Handle Tool, Pole Vector, Bind / Unbind Skin, Paint Skin Weights, Copy /
Mirror Skin Weights, Copy / Paste Vertex Weights.

Maya rigging: skin = Armature modifier + vertex
groups named after the joints). A Maya joint is a bone's head (or the
tail of a chain end); Blender's IK pulls a bone's tail, so a Maya IK handle on end joint J is an IK
constraint on the bone whose tail is J.
"""


import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras import view3d_utils
from mathutils import Vector

from .. import results
from .. import compat
from . import naming, units

PICK_RADIUS = 25          # px at UI scale 1.0
IK_STATUS = "IK Handle Tool: click the start joint, then the end joint (Esc: cancel)"
# The kit's IK is an IK constraint on the bone that ends at the end joint (no effector node); Maya answers the
# ikHandle command with its node names in the Command Line result field (#100: no Blender note in the status bar).


def _cb():
    from ..ui import channel_box
    return channel_box


# --- joints (Maya points) on bones -----------------------------------------------------------

def joints_of(arm):
    """[(bone name, 'HEAD' | 'TAIL', world position)]: every bone head, plus the tails of chain ends."""
    mw = arm.matrix_world
    out = []
    for pb in arm.pose.bones:
        out.append((pb.name, 'HEAD', mw @ pb.head))
        if not pb.children:
            out.append((pb.name, 'TAIL', mw @ pb.tail))
    return out


def pick_joint(region, rv3d, armatures, coord, radius):
    """(armature, (bone, 'HEAD'|'TAIL')) of the joint nearest ``coord`` on screen within ``radius`` px."""
    best, best_d = None, radius
    for arm in armatures:
        for name, end, pos in joints_of(arm):
            p = view3d_utils.location_3d_to_region_2d(region, rv3d, pos)
            if p is None:
                continue
            d = (Vector(coord) - p).length
            if d < best_d:
                best, best_d = (arm, (name, end)), d
    return best


def _incoming(arm, joint):
    """The bone whose tail is the joint (None for a root joint)."""
    name, end = joint
    pb = arm.pose.bones[name]
    if end == 'TAIL':
        return pb
    parent = pb.parent
    if parent is not None and (parent.tail - pb.head).length < 1e-5:
        return parent
    return None


def ik_chain(arm, start, end):
    """(IK bone, chain_count) for a Maya IK from joint ``start`` to joint ``end``, or None."""
    if start[1] == 'TAIL':
        return None
    first = arm.pose.bones[start[0]]
    ik_bone = _incoming(arm, end)
    if ik_bone is None:
        return None
    count, b = 1, ik_bone
    while b is not None and b != first:
        b = b.parent
        count += 1
    return (ik_bone, count) if b == first else None


def joint_position(arm, joint):
    pb = arm.pose.bones[joint[0]]
    return arm.matrix_world @ (pb.tail if joint[1] == 'TAIL' else pb.head)


# Maya IK Handle Tool factory settings: Rotate-Plane solver, solver enabled,
# weight 1. Blender's IK constraint: RP = plain IK (pole vector: Constrain > Pole Vector), SC = the chain end follows
# the handle's rotation (``use_rotation``; the handle starts turned like the end joint so nothing jumps).
IK_SOLVERS = (("RP", "Rotate-Plane Solver", "Maya ikRPsolver: Blender IK, the pole vector (Constrain > Pole Vector) "
               "turns the chain plane"),
              ("SC", "Single-Chain Solver", "Maya ikSCsolver: Blender IK whose chain end follows the handle's "
               "rotation"))


def create_ik(context, arm, start, end, solver="RP", solver_enable=True, weight=1.0):
    """IK constraint + ``ikHandleN`` empty at the end joint; returns the handle (None = not a chain)."""
    chain = ik_chain(arm, start, end)
    if chain is None:
        return None
    ik_bone, count = chain
    handle = bpy.data.objects.new("ikHandle", None)
    context.view_layer.active_layer_collection.collection.objects.link(handle)
    naming.apply_maya_name(handle, "ikHandle", rename_data=False)
    handle.empty_display_type = 'PLAIN_AXES'
    handle.empty_display_size = units.maya_unit(context.scene)
    if solver == "SC":
        handle.rotation_euler = (arm.matrix_world @ ik_bone.matrix).to_euler()   # the end joint's orientation
    handle.location = joint_position(arm, end)
    con = ik_bone.constraints.new('IK')
    con.name = handle.name
    con.target = handle
    con.chain_count = count
    con.use_tail = True
    con.use_rotation = solver == "SC"
    con.weight = max(0.01, weight)               # Blender's IK weight range starts at 0.01
    con.mute = not solver_enable
    from . import ik_fk
    ik_fk.ensure_blend(arm, ik_bone, con)           # Maya Ik Blend on the handle
    if solver == "RP":
        # Maya ikRPsolver: default pole vector + Twist channels, the pole helper, Blender's pole angle
        from . import ik_rp
        ik_rp.setup(context, arm, ik_bone, con, handle)
    if context.active_object is not None and context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in context.selected_objects:
        ob.select_set(False)
    handle.select_set(True)
    context.view_layer.objects.active = handle       # Maya: the new handle is selected, W moves it
    return handle


def selected_pair(context):
    """(start, end) joints from two selected pose bones (the ancestor starts, the active ends), or None."""
    cb = _cb()
    arm = cb.pose_armature(context)
    if arm is None:
        return None
    sel = [pb for pb in arm.pose.bones if cb.bone_selected(pb)]
    act = arm.data.bones.active
    if len(sel) != 2 or act is None:
        return None
    end = arm.pose.bones[act.name]
    start = sel[0] if sel[1] == end else sel[1]
    return arm, (start.name, 'HEAD'), (end.name, 'HEAD')


class ALLSET_OT_ik_handle(bpy.types.Operator):
    """Maya IK Handle Tool: click the start joint, then the end joint (or select both joints first)"""
    bl_idname = "allset.ik_handle"
    bl_label = "IK Handle Tool"
    bl_options = {'UNDO'}

    solver: EnumProperty(name="Current solver", items=IK_SOLVERS, default="RP")
    solver_enable: BoolProperty(name="Solver enable", default=True)
    weight: FloatProperty(name="Weight", default=1.0, min=0.01, max=1.0)

    def execute(self, context):
        """Without clicks: the two selected joints (scripts, and invoke when two are selected)."""
        pair = selected_pair(context)
        if pair is None:
            self.report({'WARNING'}, "Select the start joint, then the end joint (pose mode)")
            return {'CANCELLED'}
        return self._make(context, *pair)

    def invoke(self, context, event):
        if selected_pair(context) is not None or context.window is None:
            return self.execute(context)
        self._start = None
        self._swallow = False
        context.workspace.status_text_set(IK_STATUS)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _make(self, context, arm, start, end):
        handle = create_ik(context, arm, start, end, self.solver, self.solver_enable, self.weight)
        if handle is None:
            self.report({'WARNING'}, "The end joint must be below the start joint in the same skeleton")
            return {'CANCELLED'}
        from ..command_line import show_result
        show_result(f"Result: {handle.name}")
        return {'FINISHED'}

    def _pick(self, context, event):
        from .joints import view_under
        hit = view_under(context.window, event.mouse_x, event.mouse_y)
        if hit is None:
            return None
        area, region = hit
        arms = [o for o in context.view_layer.objects if o.type == 'ARMATURE' and o.visible_get()]
        radius = PICK_RADIUS * context.preferences.system.ui_scale
        return pick_joint(region, region.data, arms, (event.mouse_x - region.x, event.mouse_y - region.y),
                          radius)

    def modal(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            context.workspace.status_text_set(None)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS' and not (event.alt or event.ctrl or event.shift):
                hit = self._pick(context, event)
                if hit is None:
                    return {'PASS_THROUGH'} if not self._swallow else {'RUNNING_MODAL'}
                self._swallow = True
                arm, joint = hit
                if self._start is None or self._start[0] != arm:
                    self._start = (arm, joint)
                    return {'RUNNING_MODAL'}
                context.workspace.status_text_set(None)
                with context.temp_override(window=context.window):
                    return self._make(context, arm, self._start[1], joint)
            if event.value == 'RELEASE' and self._swallow:
                self._swallow = False
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


# --- Pole Vector ------------------------------------------------------------------------------

def _signed_angle(v1, v2, normal):
    a = v1.angle(v2)
    return -a if normal.dot(v1.cross(v2)) < 0 else a


def pole_angle(arm, con_bone, count, pole_location):
    """IK pole angle that keeps the chain where it is (first chain bone's X axis to the pole plane)."""
    mw = arm.matrix_world
    base = con_bone
    for _ in range(count - 1):
        base = base.parent
    m = mw @ base.matrix
    head, tail = m.translation, mw @ base.tail
    x_axis = m.to_3x3().col[0]
    ik_tail = mw @ con_bone.tail
    pole_normal = (ik_tail - head).cross(pole_location - head)
    projected = pole_normal.cross(tail - head)
    return _signed_angle(x_axis, projected, tail - head)


def _chain_heads(arm, con_bone, count):
    out, b = [], con_bone
    for _ in range(count):
        if b is None:
            break
        out.append(arm.matrix_world @ b.head)
        out.append(arm.matrix_world @ b.tail)
        b = b.parent
    return out


def set_pole(context, arm, pb, con, pole):
    """Maya poleVectorConstraint: the handle's pole vector = target − start joint, so the
    chain plane turns to face the target like Maya's. A kit RP handle keeps its pole helper (twist still applies);
    another IK constraint gets the target as its pole with Blender's pole angle for Maya's plane (the old
    "move the chain least" search kept the chain where it was, which Maya doesn't). Returns the chain's movement."""
    from . import ik_rp
    from .ik_fk import chain
    count = max(con.chain_count, 1)
    context.view_layer.update()
    before = _chain_heads(arm, pb, count)
    handle = con.target
    if handle is not None and ik_rp.HELPER in handle:
        ik_rp.set_pole_object(handle, pole)
    else:
        bones = chain(pb, con)
        inv = (arm.matrix_world @ bones[0].matrix @ bones[0].bone.matrix_local.inverted()).to_3x3().inverted()
        start = arm.matrix_world @ bones[0].head
        bend, _straight = ik_rp._rest_bend(bones, inv @ (pole.matrix_world.translation - start))
        con.pole_target = pole
        con.pole_angle = ik_rp.pole_angle(arm, bones, bend)
    context.view_layer.update()
    return sum((p - q).length for p, q in zip(before, _chain_heads(arm, pb, count)))


def ik_constraints_on(target):
    """[(armature, pose bone, IK constraint)] whose IK target is ``target``."""
    out = []
    for ob in bpy.data.objects:
        if ob.type != 'ARMATURE' or ob.pose is None:
            continue
        for pb in ob.pose.bones:
            for con in pb.constraints:
                if con.type == 'IK' and con.target == target:
                    out.append((ob, pb, con))
    return out


class ALLSET_OT_pole_vector(bpy.types.Operator):
    """Maya Pole Vector constraint: select the pole object, then the IK handle"""
    bl_idname = "allset.pole_vector"
    bl_label = "Pole Vector"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object is not None

    def execute(self, context):
        handle = context.active_object
        poles = [o for o in context.selected_objects if o is not handle]
        found = ik_constraints_on(handle)
        if not poles or not found:
            self.report({'WARNING'}, "Select the pole object, then the IK handle")
            return {'CANCELLED'}
        pole = poles[0]
        for arm, pb, con in found:
            set_pole(context, arm, pb, con, pole)
        results.result(self, f"{pole.name} is the pole vector of {handle.name}")
        return {'FINISHED'}


# --- Bind / Unbind Skin -------------------------------------------------------------------------

def _skin_part(m):
    from .skin_method import is_part     # Weight Blended's DQ half is part of the skin, not a second one
    return is_part(m)


def armature_modifier(mesh):
    return next((m for m in mesh.modifiers if m.type == 'ARMATURE' and m.object is not None and not _skin_part(m)),
                None)


def armature_modifiers(mesh):
    """Every skin (Armature modifier with a skeleton) of a mesh, stack order = Maya's skinCluster chain from the
    first bound (the kit makes one, a received file may hold more — shown read-only)."""
    return [m for m in getattr(mesh, "modifiers", ()) if m.type == 'ARMATURE' and m.object is not None
            and not _skin_part(m)]


# Maya Bind Skin options the kit honours: Normalize weights is kept on the
# mesh (Interactive = Blender's Auto Normalize while painting), Colorize skeleton = a bone colour per joint
# (Unbind Skin's "Remove joint colors" takes them away), Remove unused influences = drop joints that weigh nothing.
NORMALIZE_PROP = "allset_normalize"
NORMALIZE = (("NONE", "None", "Weights are left as painted"),
             ("INTERACTIVE", "Interactive", "Painting a joint takes weight from the others (Blender Auto Normalize)"),
             ("POST", "Post", "Weights are normalised when the skin is used, not while painting"))
JOINT_COLORS = tuple(f"THEME{i:02d}" for i in range(1, 16))


def colorize(arm, on=True):
    """Maya Colorize skeleton: each joint its own colour (Blender bone colour palettes), or back to none."""
    for i, bone in enumerate(arm.data.bones):
        bone.color.palette = JOINT_COLORS[i % len(JOINT_COLORS)] if on else 'DEFAULT'


def normalize_mode(mesh):
    return mesh.get(NORMALIZE_PROP, "INTERACTIVE")


# Maya Bind Skin "Bind method". Closest distance is the default method (like Maya): weight of joint i on a vertex is
# distance(world vertex, joint i's segments) ** -dropoff, the segments run from the joint to each child joint (an end
# joint is a point), dropoff = skinCluster dropoffRate (factory 4), the largest ``max influences`` kept, normalised.
# World space: an object's non-uniform scale doesn't matter (#94 - Blender's bone heat on a mesh with Scale Y 8 and
# one height subdivision left joint2 with no weights). Heat Map = Blender's automatic weights (bone heat).
BIND_METHODS = (("CLOSEST_DISTANCE", "Closest distance", "Default bind (like Maya): weights fall off with the distance to "
                 "each joint"),
                ("CLOSEST_HIERARCHY", "Closest in hierarchy", "Only the joints next to the closest one in the "
                 "skeleton (and the end joints) take weight"),
                ("HEAT_MAP", "Heat Map", "Blender's automatic weights (bone heat)"))
DROPOFF = 4.0
# Maya treats a vertex within 1e-4 of joints as on them: those share it equally
# (the kit used 1e-9 before)
ON_JOINT = 1e-4
SKINNING = (("CLASSIC_LINEAR", "Classic linear", "Weights blend the joint matrices (the default, like Maya)"),
            ("DUAL_QUATERNION", "Dual quaternion", "Volume-preserving blend (Blender Preserve Volume)"),
            ("WEIGHT_BLENDED", "Weight blended", "Per vertex mix of linear and dual quaternion by the blendWeights "
             "vertex group (0 = linear until painted)"))


def joint_segments(arm, bones=None):
    """{bone name: [(a, b) world segment]}: Maya joint = the bone head, its segments go to each child joint (child
    bone head); a bone without children is an end joint (a point). ``bones`` limits which joints get weights."""
    mw = arm.matrix_world
    out = {}
    for bone in arm.data.bones:
        if not bone.use_deform or (bones is not None and bone.name not in bones):
            continue
        a = mw @ bone.head_local
        out[bone.name] = [(a, mw @ c.head_local) for c in bone.children] or [(a, a)]
    return out


def closest_distance_weights(points, segments, dropoff=DROPOFF, max_influences=5, hierarchy=None):
    """(names, weights (V, J)) for world ``points`` (V, 3) - the Maya closest-distance rule above. ``hierarchy`` =
    {name: (parent name or None, [child names])} turns on Maya's Closest in hierarchy (``hierarchy_candidates``)."""
    import numpy as np
    names = list(segments)
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    dist = np.full((len(pts), len(names)), np.inf)
    for j, name in enumerate(names):
        for a, b in segments[name]:
            a = np.asarray(a, dtype=np.float64)
            ab = np.asarray(b, dtype=np.float64) - a
            ll = float(ab @ ab)
            t = np.clip((pts - a) @ ab / ll, 0.0, 1.0)[:, None] if ll > 0.0 else 0.0
            dist[:, j] = np.minimum(dist[:, j], np.linalg.norm(pts - (a + t * ab), axis=1))
    if hierarchy is not None:
        dist = np.where(hierarchy_candidates(dist, names, hierarchy, max_influences), dist, np.inf)
    on = dist <= ON_JOINT
    with np.errstate(divide='ignore'):
        w = np.where(on.any(axis=1)[:, None], on.astype(np.float64), dist ** -float(dropoff))
    w = np.where(np.isfinite(w), w, 0.0)
    if 0 < max_influences < len(names):
        cut = np.argsort(-w, axis=1)[:, max_influences:]
        np.put_along_axis(w, cut, 0.0, axis=1)
    total = w.sum(axis=1, keepdims=True)
    return names, np.divide(w, total, out=np.zeros_like(w), where=total > 0)


def hierarchy_candidates(dist, names, hierarchy, max_influences):
    """Maya Closest in hierarchy (bind_hier2, error <= 3.9e-16): per vertex the
    closest joint *with children*; candidates = its breadth-first list (each listed joint's children, then its parent,
    at most ``max_influences`` joints) plus every end joint. (V, J) bool mask."""
    import numpy as np
    col = {n: j for j, n in enumerate(names)}
    kids = {n: [c for c in hierarchy[n][1] if c in col] for n in names}
    par = {n: hierarchy[n][0] if hierarchy[n][0] in col else None for n in names}
    ends = np.array([not kids[n] for n in names])
    inner = [j for j, n in enumerate(names) if kids[n]]
    mask = np.tile(ends, (len(dist), 1))
    if not inner:
        return np.ones_like(mask)
    cache = {}
    for i, j in enumerate(np.asarray(inner)[np.argmin(dist[:, inner], axis=1)]):
        lst = cache.get(j)
        if lst is None:
            lst, k = [names[j]], 0
            while k < len(lst) and len(lst) < max_influences:
                for c in kids[lst[k]]:
                    if c not in lst and len(lst) < max_influences:
                        lst.append(c)
                p = par[lst[k]]
                if len(lst) < max_influences and p is not None and p not in lst:
                    lst.append(p)
                k += 1
            lst = cache[j] = [col[n] for n in lst]
        mask[i, lst] = True
    return mask


def joint_hierarchy(arm, names):
    bones = arm.data.bones
    return {n: (bones[n].parent.name if bones[n].parent is not None else None, [c.name for c in bones[n].children])
            for n in names}


def _bind_closest(arm, mesh, bones, max_influences, dropoff=DROPOFF, hierarchy=False):
    import numpy as np
    me = mesh.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    mw = np.array(mesh.matrix_world)
    pts = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    segs = joint_segments(arm, bones)
    names, w = closest_distance_weights(pts, segs, dropoff, max_influences,
                                        joint_hierarchy(arm, list(segs)) if hierarchy else None)
    every = list(range(len(me.vertices)))
    for j, name in enumerate(names):
        vg = mesh.vertex_groups.get(name) or mesh.vertex_groups.new(name=name)
        vg.remove(every)
        for value in np.unique(w[:, j]):
            if value > 0.0:
                vg.add(np.flatnonzero(w[:, j] == value).tolist(), float(value), 'REPLACE')
    md = armature_modifier(mesh)
    if md is None:
        md = mesh.modifiers.new("Armature", 'ARMATURE')   # same stack place as Blender's parenting (deformers first)
    md.object = arm
    md.use_vertex_groups = True


def name_skin_cluster(mesh):
    """Maya names each bind's deformer skinCluster1, skinCluster2 ... scene-wide (two binds give skinCluster1 /
    skinCluster2, #97): a skin modifier with Blender's automatic name gets the next free number."""
    md = armature_modifier(mesh)
    if md is None or md.name.startswith("skinCluster"):
        return md
    import re
    used = {int(m.group(1)) for ob in bpy.data.objects for mod in getattr(ob, "modifiers", ())
            for m in [re.fullmatch(r"skinCluster(\d+)", mod.name)] if m}
    n = 1
    while n in used:
        n += 1
    md.name = f"skinCluster{n}"
    return md


def bind_skin(context, arm, meshes, max_influences=5, only_bones=None, normalize="INTERACTIVE",
              remove_unused=True, colorize_skeleton=True, method="CLOSEST_DISTANCE", dropoff=DROPOFF,
              skinning="CLASSIC_LINEAR", maintain_max=True):
    """Smooth bind (Maya skinCluster): the meshes stay where they are in the hierarchy. Also stores Maya's bind pose
    (Go to Bind Pose), maxInfluences / maintainMaxInfluences / dropoffRate on the mesh."""
    for mesh in meshes:
        mesh.pop(PAINT_SEEN, None)          # a new skin: Paint Skin Weights starts on its first influence (238)
    if context.active_object is not None and context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    if method == "HEAT_MAP":
        for ob in context.selected_objects:
            ob.select_set(False)
        for ob in (*meshes, arm):
            ob.select_set(True)
        context.view_layer.objects.active = arm
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
        arm.select_set(False)
        context.view_layer.objects.active = meshes[-1]
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')   # Maya doesn't parent the skin to the joints
    else:
        for mesh in meshes:
            _bind_closest(arm, mesh, only_bones, max_influences, dropoff, method == "CLOSEST_HIERARCHY")
    for mesh in meshes:
        name_skin_cluster(mesh)
    bones = {b.name for b in arm.data.bones}
    for mesh in meshes:
        if only_bones:
            for vg in list(mesh.vertex_groups):
                if vg.name in bones and vg.name not in only_bones:
                    mesh.vertex_groups.remove(vg)
        context.view_layer.objects.active = mesh
        if method == "HEAT_MAP" and mesh.vertex_groups:
            bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=max_influences)
            bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
        if remove_unused:
            from .rig_maya import unused_influences
            for name in unused_influences(mesh):
                mesh.vertex_groups.remove(mesh.vertex_groups[name])
        mesh[NORMALIZE_PROP] = normalize
        from . import rig_maya, skin_basics
        mesh[rig_maya.MAX_INFLUENCES_PROP] = int(max_influences)
        mesh[skin_basics.MAINTAIN_MAX] = bool(maintain_max)
        if float(dropoff) != DROPOFF:
            mesh[rig_maya.DROPOFF_PROP] = {vg.name: float(dropoff) for vg in influences(mesh)}
        from . import skin_method
        skin_method.set_method(mesh, skinning)       # Classic linear / Dual quaternion / Weight blended
    context.view_layer.update()
    for mesh in meshes:
        unpose_mesh(arm, mesh)
    from . import skin_basics, skin_follow
    skin_basics.store_bind_pose(arm)
    for mesh in meshes:
        skin_follow.attach(mesh, arm)       # the skin moves with the skeleton object / a group above it (Maya)
    if colorize_skeleton:
        colorize(arm)
    arm.select_set(True)
    return meshes


def unpose_mesh(arm, mesh):
    """Maya binds in the current pose: a chain posed by hand or bent by an IK handle / pole vector must not move the
    mesh. Blender deforms from the rest pose, so each vertex gets the base position that the current pose deforms back
    to where it is (the inverse of its weighted bone matrix, Blender's linear blend). Returns how many vertices moved
    (0 when the skeleton is at rest)."""
    from mathutils import Matrix
    bones = {}
    for pb in arm.pose.bones:
        if not pb.bone.use_deform:
            continue
        m = pb.matrix @ pb.bone.matrix_local.inverted()
        bones[pb.name] = m
    if not bones or all(_near_identity(m) for m in bones.values()):
        return 0
    me = mesh.data
    if me.shape_keys is not None or not me.vertices:
        return 0
    to_arm = arm.matrix_world.inverted() @ mesh.matrix_world
    from_arm = to_arm.inverted()
    names = {vg.index: vg.name for vg in mesh.vertex_groups}
    moved = 0
    for v in me.vertices:
        total, blend = 0.0, Matrix(((0.0,) * 4,) * 4)
        for g in v.groups:
            m = bones.get(names.get(g.group))
            if m is None or g.weight <= 0.0:
                continue
            blend += m * g.weight
            total += g.weight
        if total <= 0.0:
            continue
        blend = from_arm @ (blend * (1.0 / total)) @ to_arm
        try:
            v.co = blend.inverted() @ v.co
        except ValueError:
            continue
        moved += 1
    me.update()
    return moved


def _near_identity(m, eps=1e-6):
    from mathutils import Matrix
    ident = Matrix.Identity(4)
    return all(abs(m[i][j] - ident[i][j]) < eps for i in range(4) for j in range(4))


QUESTION = {"mesh": None}                 # the last mesh the second-skin question was asked for (tests)
SECOND_SKIN_NOTE = ("Blender keeps one skin per mesh here: FBX and game engines read one. To add joints to this "
                    "skin use Skin > Edit Influences > Add Influence; a second Armature modifier can be added by "
                    "hand in Properties > Modifiers.")


def question_text(name):
    """Maya's Bind Skin question."""
    return f"There is already a skin cluster on {name}.\nDo you want to create another?"


class ALLSET_OT_skin_cluster_question(bpy.types.Operator):
    """Maya Bind Skin Options question for a mesh that already has a skin"""
    bl_idname = "allset.skin_cluster_question"
    bl_label = "Bind Skin Options"
    bl_options = {'INTERNAL'}

    mesh: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Bind Skin Options")
        for line in question_text(self.mesh).split("\n"):
            layout.label(text=line, icon='QUESTION' if line.startswith("There") else 'NONE')
        row = layout.row(align=True)
        yes = row.row(align=True)
        yes.enabled = False
        yes.operator("allset.skin_cluster_answer", text="Yes")
        row.operator("allset.skin_cluster_answer", text="No")
        from ..ui import chrome
        box = layout.box()
        chrome.paragraph(box, context, SECOND_SKIN_NOTE, width=400)

    def execute(self, context):
        return {'FINISHED'}


class ALLSET_OT_skin_cluster_answer(bpy.types.Operator):
    """No: leave the mesh with its one skin"""
    bl_idname = "allset.skin_cluster_answer"
    bl_label = "No"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'FINISHED'}


class ALLSET_OT_bind_skin(bpy.types.Operator):
    """Maya Bind Skin: the selected skeleton and meshes, in any order (closest distance weights, no parenting)"""
    bl_idname = "allset.bind_skin"
    bl_label = "Bind Skin"
    bl_options = {'REGISTER', 'UNDO'}

    bind_to: EnumProperty(name="Bind To", items=(("HIERARCHY", "Joint Hierarchy", "Every joint of the skeleton"),
                                                 ("SELECTED", "Selected Joints", "Only the joints selected in "
                                                  "pose mode")), default="HIERARCHY")
    bind_method: EnumProperty(name="Bind method", items=BIND_METHODS, default="CLOSEST_DISTANCE")
    skinning: EnumProperty(name="Skinning method", items=SKINNING, default="CLASSIC_LINEAR")
    max_influences: IntProperty(name="Max Influences", default=5, min=1, max=30)
    # Maya 2026 Bind Skin Options factory (Maintain max influences on, dropoff 4.0, slider 0.1-10)
    maintain_max: BoolProperty(name="Maintain max influences", default=True)
    dropoff: FloatProperty(name="Dropoff rate", default=DROPOFF, min=0.1, max=100.0, soft_max=10.0, precision=1)
    normalize: EnumProperty(name="Normalize weights", items=NORMALIZE, default="INTERACTIVE")
    remove_unused: BoolProperty(name="Remove unused influences", default=True)
    colorize: BoolProperty(name="Colorize skeleton", default=True)

    def execute(self, context):
        cb = _cb()
        arm = cb.pose_armature(context)
        picked = [pb.name for pb in arm.pose.bones if cb.bone_selected(pb)] if arm is not None else []
        sel = list(context.selected_objects)
        if arm is None:
            arm = next((o for o in sel if o.type == 'ARMATURE'), None)
            if arm is not None and arm.mode == 'EDIT':
                # an unskinned skeleton's joints are picked in Edit mode
                picked = [eb.name for eb in arm.data.edit_bones if eb.select]
        meshes = [o for o in sel if o.type == 'MESH']
        if not sel and not picked:
            from .maya_errors import SELECT_TO_BIND        # Maya 2026
            self.report({'ERROR'}, SELECT_TO_BIND)
            return {'CANCELLED'}
        if arm is None:
            # Maya: no joint in the selection (only an IK handle / a curve ...) is an Error
            from .maya_errors import MUST_SELECT_JOINT
            self.report({'ERROR'}, MUST_SELECT_JOINT)
            return {'CANCELLED'}
        if not meshes:
            from .maya_errors import BINDABLE_IN_SELECTION   # Maya: an Error, joints only
            self.report({'ERROR'}, BINDABLE_IN_SELECTION)
            return {'CANCELLED'}
        skinned = [m for m in meshes if armature_modifier(m) is not None]
        if skinned:
            # Maya 2024+ asks before a second skinCluster; the kit
            # keeps one skin per mesh — the question with Yes greyed and the Blender way
            QUESTION["mesh"] = skinned[0].name
            if context.window is not None:
                bpy.ops.allset.skin_cluster_question('INVOKE_DEFAULT', mesh=skinned[0].name)
            self.report({'WARNING'}, question_text(skinned[0].name).replace("\n", " "))
            return {'CANCELLED'}
        only = set(picked) if self.bind_to == "SELECTED" and picked else None
        bind_skin(context, arm, meshes, self.max_influences, only, self.normalize, self.remove_unused, self.colorize,
                  self.bind_method, self.dropoff, self.skinning, self.maintain_max)
        results.result(self, f"Bound {len(meshes)} mesh(es) to {arm.name}")
        return {'FINISHED'}


# Maya Detach Skin Options: History Delete history (default) / Keep history /
# Bake history, Coloring: Remove joint colors on.
UNBIND_HISTORY = (("DELETE", "Delete history", "Remove the skin and the joints' weights"),
                  ("KEEP", "Keep history", "Remove the skin, keep the joints' weights (vertex groups)"),
                  ("BAKE", "Bake history", "Keep the current deformed shape as the mesh, then remove the skin"))


def unbind(context, mesh, history="DELETE"):
    """Detach one mesh's skin (Armature modifiers); returns the skeletons it was bound to."""
    arms = []
    for mod in [m for m in mesh.modifiers if m.type == 'ARMATURE']:
        arm = mod.object
        if arm is not None and arm not in arms:
            arms.append(arm)
        if history == "BAKE" and arm is not None:
            with context.temp_override(object=mesh, active_object=mesh):
                bpy.ops.object.modifier_apply(modifier=mod.name)
        else:
            mesh.modifiers.remove(mod)
        if history != "KEEP" and arm is not None:
            bones = {b.name for b in arm.data.bones}
            from .skin_method import BLEND_GROUP      # the skinCluster's blendWeights go with it
            for vg in [g for g in mesh.vertex_groups if g.name in bones or g.name == BLEND_GROUP]:
                mesh.vertex_groups.remove(vg)
    if NORMALIZE_PROP in mesh:
        del mesh[NORMALIZE_PROP]
    from . import skin_basics, skin_follow
    skin_follow.detach(mesh, keep_shape=history == "BAKE")
    for arm in arms:
        skin_basics.forget_bind_pose(arm)
    return arms


class ALLSET_OT_unbind_skin(bpy.types.Operator):
    """Maya Unbind Skin: remove the Armature modifier (and, by default, the joint weight groups)"""
    bl_idname = "allset.unbind_skin"
    bl_label = "Unbind Skin"
    bl_options = {'REGISTER', 'UNDO'}

    history: EnumProperty(name="History", items=UNBIND_HISTORY, default="DELETE")
    remove_colors: BoolProperty(name="Remove joint colors", default=True)

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == 'MESH' and armature_modifier(o)]
        if meshes and context.active_object is not None and context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        arms = []
        for mesh in meshes:
            arms += [a for a in unbind(context, mesh, self.history) if a not in arms]
        if self.remove_colors:
            for arm in arms:
                still = any(m.object == arm for o in bpy.data.objects if o.type == 'MESH'
                            for m in o.modifiers if m.type == 'ARMATURE')
                if not still:          # Maya removes the colours of joints no skin uses any more
                    colorize(arm, False)
        results.result(self, f"Unbound {len(meshes)} skin(s)")
        return {'FINISHED'} if meshes else {'CANCELLED'}


# --- Paint Skin Weights --------------------------------------------------------------------------

def skinned_mesh(context):
    ob = context.active_object
    if ob is not None and ob.type == 'MESH' and armature_modifier(ob):
        return ob
    return next((o for o in context.selected_objects if o.type == 'MESH' and armature_modifier(o)), None)


def influences(mesh, mod=None):
    """Vertex groups that are joints of the mesh's skeleton (Maya: the skinCluster influences); ``mod`` = one skin."""
    mod = mod or armature_modifier(mesh)
    if mod is None:
        return []
    bones = {b.name for b in mod.object.data.bones}
    return [vg for vg in mesh.vertex_groups if vg.name in bones]


PAINT_SEEN = "allset_paint_seen"      # the mesh's skin was painted once (Maya: keep the picked influence)


def first_influence(mesh):
    """The influence Maya hilites first: the skeleton's joints depth first from the root (armature bone order for
    siblings), the first that is an influence."""
    mod = armature_modifier(mesh)
    if mod is None or mod.object is None:
        return None
    groups = {vg.name: vg for vg in influences(mesh, mod)}
    todo = [b for b in mod.object.data.bones if b.parent is None]
    while todo:
        b = todo.pop(0)
        if b.name in groups:
            return groups[b.name]
        todo[0:0] = list(b.children)
    return None


def leave_weight_paint(context):
    """Release paint and its helper skeleton; retain the painted mesh as the selection."""
    if context.mode != 'PAINT_WEIGHT':
        return False
    mesh = context.active_object
    mod = armature_modifier(mesh) if mesh is not None else None
    arm = mod.object if mod is not None else None
    bpy.ops.object.mode_set(mode='OBJECT')
    if arm is not None and arm.name in context.view_layer.objects:
        if arm.mode == 'POSE':
            context.view_layer.objects.active = arm
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            finally:
                context.view_layer.objects.active = mesh
        arm.select_set(False)
    if mesh is not None:
        mesh.select_set(True)
        context.view_layer.objects.active = mesh
    return True


def set_view_tool(context, name):
    """Tool changes from the dock/menu also target the real modeling viewport."""
    from ..ui.status_line import main_view3d
    area, region = main_view3d(context.screen)
    if area is not None and region is not None:
        with context.temp_override(window=context.window, area=area, region=region):
            return bpy.ops.wm.tool_set_by_id(name=name, space_type='VIEW_3D')
    return bpy.ops.wm.tool_set_by_id(name=name, space_type='VIEW_3D')


class ALLSET_OT_weight_paint_exit(bpy.types.Operator):
    """Leave Paint Skin Weights and activate Maya's Select, Move, Rotate, or Scale tool"""
    bl_idname = "allset.weight_paint_exit"
    bl_label = "Leave Paint Skin Weights"
    bl_options = {'REGISTER', 'UNDO'}

    tool: EnumProperty(items=(
        ('builtin.select_box', 'Select', 'Q: leave painting and select objects'),
        ('builtin.move', 'Move', 'W: leave painting and move objects'),
        ('builtin.rotate', 'Rotate', 'E: leave painting and rotate objects'),
        ('builtin.scale', 'Scale', 'R: leave painting and scale objects'),
    ), default='builtin.select_box', options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'PAINT_WEIGHT'

    def execute(self, context):
        leave_weight_paint(context)
        return set_view_tool(context, self.tool)


# Maya Paint Skin Weights Tool settings with a Blender meaning; the window
# (operators/option_windows_rig.py) passes them, a plain menu click leaves the brush as the user set it in the dock.
PAINT_OPERATIONS = (("REPLACE", "Replace", "Blender brush blend Mix"), ("ADD", "Add", "Blender brush blend Add"),
                    ("SCALE", "Scale", "Blender brush blend Multiply"), ("SMOOTH", "Smooth", "Blender's Blur tool"))
PAINT_BLEND = {"REPLACE": 'MIX', "ADD": 'ADD', "SCALE": 'MUL'}
PAINT_PROFILES = (("GAUSSIAN", "Gaussian", "Smooth falloff"), ("SOFT", "Soft", "Sphere falloff"),
                  ("SOLID", "Solid", "Constant: no falloff"))
PROFILE_CURVE = {"GAUSSIAN": 'SMOOTH', "SOFT": 'SPHERE', "SOLID": 'CONSTANT'}
PAINT_FIELDS = ("operation", "profile", "normalize", "opacity", "value", "radius", "screen_projection",
                "show_wireframe", "xray_joints")


def _brush_set(brush, name, value):
    """Set a weight paint brush setting; False when the brush can't be edited (a linked asset)."""
    try:
        setattr(brush, name, value)
        return True
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return False


def apply_paint_settings(context, mesh, arm, v):
    """Maya tool values ``v`` (PAINT_FIELDS) -> the weight paint tool, brush, unified settings and overlays.
    Returns the names Blender refused (e.g. a brush that is a linked asset)."""
    ts = context.tool_settings
    ups = compat.unified_paint_settings(ts, "weight_paint")
    refused = []
    if v["operation"] == "SMOOTH":
        try:
            from .weight_paint import activate_brush
            activate_brush(context, 'BLUR')
        except (RuntimeError, TypeError):
            refused.append("operation")
    else:
        try:
            from .weight_paint import activate_brush
            activate_brush(context, 'DRAW')
        except (RuntimeError, TypeError):
            pass
    brush = ts.weight_paint.brush
    if brush is not None:
        if v["operation"] in PAINT_BLEND and not _brush_set(brush, "blend", PAINT_BLEND[v["operation"]]):
            refused.append("operation")
        curve_prop = compat.brush_falloff_props(brush)[0]
        if not _brush_set(brush, curve_prop, PROFILE_CURVE[v["profile"]]):
            refused.append("profile")
    # Maya Value / Opacity / Radius(U) are tool settings: Blender's unified paint settings hold them for every brush
    ups.use_unified_weight = ups.use_unified_strength = ups.use_unified_size = True
    ups.weight = max(0.0, min(1.0, v["value"]))
    ups.strength = max(0.0, min(1.0, v["opacity"]))
    if v["screen_projection"]:
        ups.use_locked_size = 'VIEW'
    else:
        ups.use_locked_size = 'SCENE'            # Maya's radius is a world size (cm) unless Screen projection is on
        compat.set_unprojected_radius(ups, max(1e-4, v["radius"] * units.maya_unit(context.scene)))
    if v["normalize"] is not None:              # None: deformer weights, never normalized
        mesh[NORMALIZE_PROP] = v["normalize"]
        ts.use_auto_normalize = v["normalize"] == "INTERACTIVE"
    else:
        ts.use_auto_normalize = False
    space = context.space_data
    if space is not None and space.type == 'VIEW_3D':
        space.overlay.show_paint_wire = v["show_wireframe"]
    if arm is not None:
        arm.show_in_front = v["xray_joints"]
    return refused


class ALLSET_OT_paint_skin_weights(bpy.types.Operator):
    """Maya Paint Skin Weights: weight paint the skinned mesh with its skeleton posable (Ctrl+click picks a joint)"""
    bl_idname = "allset.paint_skin_weights"
    bl_label = "Paint Skin Weights"
    bl_options = {'REGISTER', 'UNDO'}

    operation: EnumProperty(name="Paint operation", items=PAINT_OPERATIONS, default="REPLACE", options={'SKIP_SAVE'})
    profile: EnumProperty(name="Profile", items=PAINT_PROFILES, default="SOFT", options={'SKIP_SAVE'})
    normalize: EnumProperty(name="Normalize Weights", items=NORMALIZE, default="INTERACTIVE", options={'SKIP_SAVE'})
    opacity: FloatProperty(name="Opacity", default=1.0, min=0.0, max=1.0, options={'SKIP_SAVE'})
    value: FloatProperty(name="Value", default=1.0, min=0.0, max=1.0, options={'SKIP_SAVE'})
    radius: FloatProperty(name="Radius(U)", default=1.0, min=0.0001, options={'SKIP_SAVE'})
    screen_projection: BoolProperty(name="Screen projection", default=False, options={'SKIP_SAVE'})
    show_wireframe: BoolProperty(name="Show wireframe", default=True, options={'SKIP_SAVE'})
    xray_joints: BoolProperty(name="XRay Joints", default=True, options={'SKIP_SAVE'})
    settings: BoolProperty(name="Apply Tool Settings", default=False, options={'SKIP_SAVE', 'HIDDEN'},
                           description="Apply the Maya tool settings above (the option window); a plain click keeps "
                                       "the brush as it is")
    classic: BoolProperty(name="Classic Tool", default=False, options={'SKIP_SAVE', 'HIDDEN'},
                          description="Start the paint tool even when the mesh has skin layers (Skin Tools paints "
                                      "through it)")

    def _settings(self, context, mesh):
        if not self.settings:
            return
        refused = apply_paint_settings(context, mesh, armature_modifier(mesh).object,
                                       {k: getattr(self, k) for k in PAINT_FIELDS})
        if refused:
            self.report({'WARNING'}, "Blender kept its own " + ", ".join(refused) + " (the brush is a linked asset)")

    def execute(self, context):
        if context.mode == 'PAINT_WEIGHT':
            if self.settings:               # the option window while painting: new settings, stay in the tool
                mesh = context.active_object
                if mesh is not None and armature_modifier(mesh):
                    self._settings(context, mesh)
                return {'FINISHED'}
            leave_weight_paint(context)
            set_view_tool(context, 'builtin.select_box')
            return {'FINISHED'}
        mesh = skinned_mesh(context)
        if mesh is None:
            self.report({'WARNING'}, "Select a skinned mesh (Skin > Bind Skin first)")
            return {'CANCELLED'}
        # like Maya's Skin Tools: once the skin has layers, Paint Skin Weights opens Skin Tools (its Paint button
        # paints a layer); the option window still sets up the classic tool
        from . import skin_layers
        if not self.classic and not self.settings and skin_layers.is_initialized(mesh):
            try:
                return bpy.ops.allset.skin_tools()
            except RuntimeError as ex:
                self.report({'WARNING'}, str(ex))
                return {'CANCELLED'}
        arm = armature_modifier(mesh).object
        if context.active_object is not None and context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for ob in context.selected_objects:
            ob.select_set(False)
        arm.select_set(True)
        mesh.select_set(True)
        context.view_layer.objects.active = mesh
        bpy.ops.paint.weight_paint_toggle()              # the skeleton goes to pose mode with it
        current = context.workspace.tools.from_space_view3d_mode('PAINT_WEIGHT', create=False)
        # Older sessions may have left a selection/transform tool remembered
        # inside paint mode. Re-entering the paint tool must restore a brush.
        from ..ui.toolbox import MAYA_TOOLS
        if current is None or not current.idname or current.idname in MAYA_TOOLS:
            set_view_tool(context, 'builtin.brush')
        # Maya hilites the first influence (joint1, the skeleton's root) the first time the tool opens on a skin and
        # keeps the picked one afterwards. Bind Skin leaves
        # Blender's last made group (the last joint) active: the first entry picks by hierarchy (#146).
        first = first_influence(mesh)
        if first is not None and (mesh.vertex_groups.active is None or not mesh.get(PAINT_SEEN)):
            mesh.vertex_groups.active_index = first.index
        mesh[PAINT_SEEN] = True
        # Maya keeps a vertex selection made before the tool and floods only it
        # (Maya): Blender shows that selection only with the vertex
        # mask on. A full selection is the whole mesh anyway, so the mask stays as it was then.
        shown = [v.select for v in mesh.data.vertices if not v.hide]
        if any(shown) and not all(shown) and not mesh.data.use_paint_mask:
            mesh.data.use_paint_mask_vertex = True
        # Maya Bind Skin makes the skinCluster with Normalize Weights = Interactive (normalizeWeights 1): painting a
        # joint takes weight from the others so every vertex keeps a total of 1 (#20). Blender's factory
        # Auto Normalize is off; Skin > Normalize Weights > Disable still turns it off while painting. The skin's own
        # mode comes from Bind Skin's Normalize weights.
        context.tool_settings.use_auto_normalize = normalize_mode(mesh) == "INTERACTIVE"
        self._settings(context, mesh)
        return {'FINISHED'}


class ALLSET_OT_flood_weights(bpy.types.Operator):
    """Flood the current operation and opacity into the active influence, respecting masks and locked weights"""
    bl_idname = "allset.flood_weights"
    bl_label = "Flood"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return context.mode == 'PAINT_WEIGHT' and ob is not None and ob.vertex_groups.active is not None

    def execute(self, context):
        from .weight_paint import flood
        try:
            return flood(context)
        except (ValueError, RuntimeError) as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}


# --- Copy / Mirror Skin Weights, Copy / Paste Vertex Weights -----------------------------------------

# Maya Copy Skin Weights Options: Surface Association -> Blender Data Transfer
# vertex mapping; Influence Association 1-3 = how a source joint finds its destination joint when the two meshes use
# different skeletons (tried in order; one skeleton = every joint is itself).
SURFACE_ASSOCIATION = (("CLOSEST_POINT", "Closest point on surface", "Interpolated from the nearest face"),
                       ("RAY_CAST", "Ray cast", "Along the vertex normal onto the source"),
                       ("CLOSEST_COMPONENT", "Closest component", "The nearest source vertex"))
VERT_MAPPING = {"CLOSEST_POINT": 'POLYINTERP_NEAREST', "RAY_CAST": 'POLYINTERP_VNORPROJ', "CLOSEST_COMPONENT": 'NEAREST'}
INFLUENCE_ASSOCIATION = (("CLOSEST_JOINT", "Closest joint", "The destination joint nearest the source joint"),
                         ("CLOSEST_BONE", "Closest bone", "The destination bone nearest the source joint"),
                         ("ONE_TO_ONE", "One to one", "The joint at the same place in the hierarchy"),
                         ("NAME", "Name", "The joint with the same name"),
                         ("NONE", "None", "No further association"))


def _hierarchy_order(arm):
    out = []

    def walk(bone):
        out.append(bone.name)
        for child in bone.children:
            walk(child)
    for root in [b for b in arm.data.bones if b.parent is None]:
        walk(root)
    return out


def _segment_distance(p, a, b):
    ab = b - a
    t = 0.0 if ab.length_squared < 1e-12 else max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length


def associate(src_arm, dst_arm, name, modes=("CLOSEST_JOINT",)):
    """The destination joint for source joint ``name`` (Maya influence association), or None."""
    if src_arm == dst_arm:
        return name if name in dst_arm.data.bones else None
    bone = src_arm.data.bones.get(name)
    if bone is None:
        return None
    head = src_arm.matrix_world @ bone.head_local
    dst = dst_arm.data.bones
    for mode in modes:
        if mode == "NAME" and name in dst:
            return name
        if mode == "ONE_TO_ONE":
            order, other = _hierarchy_order(src_arm), _hierarchy_order(dst_arm)
            i = order.index(name)
            if i < len(other):
                return other[i]
        if mode == "CLOSEST_JOINT" and len(dst):
            return min(dst, key=lambda b: (dst_arm.matrix_world @ b.head_local - head).length).name
        if mode == "CLOSEST_BONE" and len(dst):
            mw = dst_arm.matrix_world
            return min(dst, key=lambda b: _segment_distance(head, mw @ b.head_local, mw @ b.tail_local)).name
    return None


def remap_influences(mesh, src_arm, dst_arm, names, modes):
    """Move the copied weights of source joints ``names`` onto their associated destination joints."""
    if src_arm == dst_arm:
        return
    weights = {}
    for name in names:
        vg = mesh.vertex_groups.get(name)
        if vg is None:
            continue
        for v in mesh.data.vertices:
            for g in v.groups:
                if g.group == vg.index and g.weight > 0.0:
                    weights.setdefault(name, []).append((v.index, g.weight))
        mesh.vertex_groups.remove(vg)
    for name, pairs in weights.items():
        target = associate(src_arm, dst_arm, name, modes)
        if target is None:
            continue
        vg = mesh.vertex_groups.get(target) or mesh.vertex_groups.new(name=target)
        for i, w in pairs:
            vg.add([i], w, 'ADD')


class ALLSET_OT_copy_skin_weights(bpy.types.Operator):
    """Maya Copy Skin Weights: select the source mesh, then the destination"""
    bl_idname = "allset.copy_skin_weights"
    bl_label = "Copy Skin Weights"
    bl_options = {'REGISTER', 'UNDO'}

    surface: EnumProperty(name="Surface Association", items=SURFACE_ASSOCIATION, default="CLOSEST_POINT")
    influence1: EnumProperty(name="Influence Association 1", items=INFLUENCE_ASSOCIATION, default="CLOSEST_JOINT")
    influence2: EnumProperty(name="Influence Association 2", items=INFLUENCE_ASSOCIATION, default="NONE")
    influence3: EnumProperty(name="Influence Association 3", items=INFLUENCE_ASSOCIATION, default="NONE")
    normalize: BoolProperty(name="Normalize", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        dst = context.active_object
        srcs = [o for o in context.selected_objects if o is not dst and o.type == 'MESH' and armature_modifier(o)]
        if dst is None or dst.type != 'MESH' or not srcs:
            self.report({'WARNING'}, "Select the skinned source mesh, then the destination mesh")
            return {'CANCELLED'}
        src_arm = armature_modifier(srcs[0]).object
        if armature_modifier(dst) is None:
            mod = dst.modifiers.new("Armature", 'ARMATURE')
            mod.object = src_arm
        dst_arm = armature_modifier(dst).object
        src_names = [vg.name for vg in influences(srcs[0])]
        bpy.ops.object.data_transfer(use_reverse_transfer=True, data_type='VGROUP_WEIGHTS', use_create=True,
                                     vert_mapping=VERT_MAPPING[self.surface],
                                     # reverse transfer swaps the two layer enums
                                     layers_select_src='NAME', layers_select_dst='ALL')
        if dst_arm != src_arm:
            modes = [m for m in (self.influence1, self.influence2, self.influence3) if m != "NONE"]
            # the transfer wrote the weights under the source joints' names: move them to the associated joints
            remap_influences(dst, src_arm, dst_arm, src_names, modes)
        if self.normalize:
            from .rig_maya import normalize
            normalize(dst)
        results.result(self, f"Copied skin weights to {dst.name}")
        return {'FINISHED'}


# Maya mirror plane (Y-up) -> Blender axis index (Z-up): YZ = x, XY = Maya z = Blender y, XZ = Maya y = Blender z
PLANE_AXIS = {"YZ": 0, "XY": 1, "XZ": 2}


def _reflect(v, axis):
    v = Vector(v)
    v[axis] = -v[axis]
    return v


# Maya Mirror Skin Weights Options: Influence Association 1 = Closest joint / One to one /
# Label (factory Closest joint), 2 = None / the same (factory None). One to one pairs a joint with itself inside one
# skeleton, so the kit offers Closest joint and Label.
MIRROR_INFLUENCE = (("CLOSEST_JOINT", "Closest joint", "The joint nearest the mirrored place of the joint"),
                    ("LABEL", "Label", "The joint with the same type label on the other side (Skeleton > Joint "
                     "Labelling): Left <-> Right"))
MIRROR_INFLUENCE_2 = (("NONE", "None", "No further association"),) + MIRROR_INFLUENCE


def _mirror_label_partner(arm, bone, reflected, labels):
    """Label association: the bone on the other side with the same type (Other: same other type); several = the one
    nearest the mirrored place (fingers of one type pair by place). Center / None side = the joint itself.
    None = no label to match."""
    side, typ, other, _d = labels.get_label(bone)
    if typ == labels.T_NONE:
        return None
    if side in (labels.CENTER, labels.NO_SIDE):
        return bone.name
    want = labels.RIGHT if side == labels.LEFT else labels.LEFT
    mw = arm.matrix_world
    cands = [b for b in arm.data.bones
             if labels.get_label(b)[:2] == (want, typ) and (typ != labels.T_OTHER or labels.get_label(b)[2] == other)]
    if not cands:
        return None
    return min(cands, key=lambda b: (mw @ b.head_local - reflected).length).name


def mirror_group_names(arm, axis, tol=1e-3, modes=("CLOSEST_JOINT",), unmatched=None):
    """Joint name -> its partner on the other side, by Maya influence association ``modes`` tried in order.

    Closest joint = the joint whose head is nearest the mirrored head (no tolerance, an unmirrored skeleton
    still pairs; a joint on the plane pairs with itself). Label = ``_mirror_label_partner``. A joint no mode pairs
    falls back to Closest joint and is added to ``unmatched`` (Maya warns "Not all influences could be matched")."""
    from . import joint_labels as labels
    mw = arm.matrix_world
    bones = list(arm.data.bones)
    heads = {b.name: mw @ b.head_local for b in bones}
    tails = {b.name: mw @ b.tail_local for b in bones}
    out = {}
    for b in bones:
        rh, rt = _reflect(heads[b.name], axis), _reflect(tails[b.name], axis)
        closest = min(bones, key=lambda o: ((heads[o.name] - rh).length, (tails[o.name] - rt).length)).name
        partner = None
        for mode in modes:
            if mode == "CLOSEST_JOINT":
                partner = closest
            elif mode == "LABEL":
                partner = _mirror_label_partner(arm, b, rh, labels)
            if partner is not None:
                break
        if partner is None:
            partner = closest
            if unmatched is not None:
                unmatched.append(b.name)
        out[b.name] = partner
    return out


def surface_weights(mesh, points, groups, w):
    """Weights at world ``points`` from the closest point on the mesh surface: the barycentric mix of that triangle's
    vertices (Maya Surface Association "Closest point on surface").
    ``w`` = (V, K) vertex weights of ``groups``. Returns (P, K)."""
    import numpy as np
    from mathutils import geometry
    from mathutils.bvhtree import BVHTree
    me = mesh.data
    me.calc_loop_triangles()
    mw = mesh.matrix_world
    co = [mw @ v.co for v in me.vertices]
    tris = [tuple(t.vertices) for t in me.loop_triangles]
    tree = BVHTree.FromPolygons(co, tris, all_triangles=True)
    out = np.zeros((len(points), len(groups)))
    for i, p in enumerate(points):
        hit, _n, t, _d = tree.find_nearest(p)
        if hit is None:
            continue
        a, b, c = tris[t]
        bary = geometry.barycentric_transform(hit, co[a], co[b], co[c], (1, 0, 0), (0, 1, 0), (0, 0, 1))
        out[i] = bary[0] * w[a] + bary[1] * w[b] + bary[2] * w[c]
    return out


def mirror_weights(mesh, axis=0, positive_to_negative=True, modes=("CLOSEST_JOINT",), unmatched=None, only=None,
                   normalize=False):
    """Copy the weights of one side onto the other (Maya Mirror Skin Weights, factory Closest point on surface): each
    destination vertex takes the weights at the closest surface point to its mirror image (barycentric), every joint
    renamed to its mirror partner; vertices on the plane are left alone. ``only`` = Maya filterSelected: just these
    destination vertices are written (a selected source vertex writes nothing);
    ``normalize`` = the option's Normalize (factory off). Count of vertices written."""
    import numpy as np
    from . import skin_basics
    mod = armature_modifier(mesh)
    pair = mirror_group_names(mod.object, axis, modes=modes, unmatched=unmatched) if mod and mod.object else {}
    groups = list(mesh.vertex_groups)
    if not groups:
        return 0
    mw = mesh.matrix_world
    verts = mesh.data.vertices
    world = [mw @ v.co for v in verts]
    eps = 1e-6
    dst = [i for i, p in enumerate(world) if (p[axis] < -eps if positive_to_negative else p[axis] > eps)]
    if only is not None:
        keep = {int(i) for i in only}
        dst = [i for i in dst if i in keep]
    if not dst:
        return 0
    w = skin_basics.weights(mesh, groups)                  # read before any write (faces across the plane)
    got = surface_weights(mesh, [_reflect(world[i], axis) for i in dst], groups, w)
    col = {g.name: j for j, g in enumerate(groups)}
    out = w.copy()
    out[dst] = 0.0
    for j, g in enumerate(groups):
        k = col.get(pair.get(g.name, g.name))
        if k is not None:
            out[dst, k] += got[:, j]
    out[np.abs(out) < 1e-12] = 0.0
    if normalize:
        infl = [j for j, g in enumerate(groups) if g.name in mod.object.data.bones] if mod and mod.object else []
        total = out[np.ix_(dst, infl)].sum(axis=1, keepdims=True)
        out[np.ix_(dst, infl)] = np.divide(out[np.ix_(dst, infl)], total, out=out[np.ix_(dst, infl)],
                                           where=total > 0)
    skin_basics.write(mesh, groups, out, dst)
    skin_basics.enforce_max(mesh)
    return len(dst)


class ALLSET_OT_mirror_skin_weights(bpy.types.Operator):
    """Maya Mirror Skin Weights: copy one side's weights onto the other, joints paired by position"""
    bl_idname = "allset.mirror_skin_weights"
    bl_label = "Mirror Skin Weights"
    bl_options = {'REGISTER', 'UNDO'}

    plane: EnumProperty(name="Mirror Across", items=[(k, k, "") for k in ("XY", "YZ", "XZ")], default="YZ")
    positive_to_negative: BoolProperty(name="Direction: Positive to Negative", default=True)
    influence1: EnumProperty(name="Influence Association 1", items=MIRROR_INFLUENCE, default="CLOSEST_JOINT")
    influence2: EnumProperty(name="Influence Association 2", items=MIRROR_INFLUENCE_2, default="NONE")
    # off by default (Mirror Skin Weights Options)
    normalize: BoolProperty(name="Normalize", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'PAINT_WEIGHT', 'EDIT_MESH'}

    def execute(self, context):
        mesh = skinned_mesh(context)
        if mesh is None:
            self.report({'WARNING'}, "Select a skinned mesh")
            return {'CANCELLED'}
        modes = [m for m in (self.influence1, self.influence2) if m != "NONE"]
        unmatched = []
        from . import skin_basics
        rows = skin_basics.target_rows(mesh)             # Maya filterSelected: selected vertices, else all
        only = rows if len(rows) < len(mesh.data.vertices) else None
        with skin_basics._ObjectData(mesh):
            n = mirror_weights(mesh, PLANE_AXIS[self.plane], self.positive_to_negative, modes, unmatched, only,
                               self.normalize)
        if unmatched:
            self.report({'WARNING'}, "Not all influences could be matched up using the selected association "
                        "options. Weight transfer may be problematic near the unmatched influences.")
        else:
            results.result(self, f"Mirrored the weights of {n} vertices")
        return {'FINISHED'}


_VERTEX_CLIPBOARD = {}


def _edit_bmesh(context):
    ob = context.edit_object
    if ob is None or ob.type != 'MESH':
        return None, None, None
    bm = bmesh.from_edit_mesh(ob.data)
    return ob, bm, bm.verts.layers.deform.verify()


class ALLSET_OT_copy_vertex_weights(bpy.types.Operator):
    """Maya Copy Vertex Weights: remember the active vertex's joint weights"""
    bl_idname = "allset.copy_vertex_weights"
    bl_label = "Copy Vertex Weights"

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        ob, bm, layer = _edit_bmesh(context)
        act = bm.select_history.active
        if not isinstance(act, bmesh.types.BMVert):
            act = next((v for v in bm.verts if v.select), None)
        if act is None:
            self.report({'WARNING'}, "Select a vertex")
            return {'CANCELLED'}
        names = {vg.index: vg.name for vg in ob.vertex_groups}
        _VERTEX_CLIPBOARD.clear()
        _VERTEX_CLIPBOARD.update({names[i]: w for i, w in act[layer].items() if i in names})
        results.result(self, f"Copied {len(_VERTEX_CLIPBOARD)} weight(s)")
        return {'FINISHED'}


class ALLSET_OT_paste_vertex_weights(bpy.types.Operator):
    """Maya Paste Vertex Weights: give the selected vertices the copied joint weights"""
    bl_idname = "allset.paste_vertex_weights"
    bl_label = "Paste Vertex Weights"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and bool(_VERTEX_CLIPBOARD)

    def execute(self, context):
        ob, bm, layer = _edit_bmesh(context)
        idx = {}
        for name in _VERTEX_CLIPBOARD:
            vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
            idx[name] = vg.index
        n = 0
        for v in bm.verts:
            if v.select:
                dv = v[layer]
                dv.clear()
                for name, w in _VERTEX_CLIPBOARD.items():
                    dv[idx[name]] = w
                n += 1
        bmesh.update_edit_mesh(ob.data)
        results.result(self, f"Pasted weights on {n} vertices")
        return {'FINISHED'}



class ALLSET_OT_reset_skin_weights(bpy.types.Operator):
    """Maya Reset Default Weights: give the skinned mesh its bind weights again (closest distance, the joints it is
    bound to, at most as many influences as each vertex has now, at least 5)"""
    bl_idname = "allset.reset_skin_weights"
    bl_label = "Reset Default Weights"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mesh = skinned_mesh(context)
        if mesh is None:
            self.report({'WARNING'}, "Select a skinned mesh")
            return {'CANCELLED'}
        mode = mesh.mode
        if mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
        md = armature_modifier(mesh)
        bones = {vg.name for vg in mesh.vertex_groups if md.object.data.bones.get(vg.name) is not None}
        most = max((sum(1 for g in v.groups if g.weight > 0) for v in mesh.data.vertices), default=0)
        _bind_closest(md.object, mesh, bones or None, max(5, most))
        mesh.data.update()
        if mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}

class ALLSET_OT_move_skinned_joints(bpy.types.Operator):
    """Maya Skin > Move Skinned Joints: reposition the joints of a skinned skeleton without deforming the mesh (the
    new place becomes the bind). Run it again, press F8 or pick another tool mode to go back to posing"""
    bl_idname = "allset.move_skinned_joints"
    bl_label = "Move Skinned Joints"
    bl_options = {'UNDO'}

    def execute(self, context):
        from . import joint_selection
        ob = context.active_object
        if ob is not None and ob.type == 'MESH':
            md = armature_modifier(ob)
            ob = md.object if md is not None else None
        if ob is None or ob.type != 'ARMATURE' or not joint_selection.is_skinned(ob):
            self.report({'WARNING'}, "Select a skinned skeleton or a skinned mesh")   # Maya: "No skinned joints"
            return {'CANCELLED'}
        if not ob.visible_get():
            self.report({'WARNING'}, f"{ob.name} is hidden: show the skeleton first")
            return {'CANCELLED'}
        on = move_skinned_joints(context, ob, not ob.get(joint_selection.MOVE_SKINNED))
        results.result(self, "Move Skinned Joints " + ("on: move the joints, run it again to pose" if on else "off"))
        return {'FINISHED'}


def move_skinned_joints(context, arm, on):
    """Maya moveJointsMode: on = the skeleton in Edit mode, its picked joints
    kept; off = back to Pose mode. The Armature modifier deforms by pose x rest^-1, so moving the rest at the rest
    pose leaves the mesh where it is and the new rest is the bind (Maya rewrites bindPreMatrix)."""
    from . import joint_selection
    picked = [pb.name for pb in arm.pose.bones if _cb().bone_selected(pb)] if arm.mode == 'POSE' else []
    if context.active_object is not None and context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in context.selected_objects:
        if ob != arm:
            ob.select_set(False)
    arm.select_set(True)
    context.view_layer.objects.active = arm
    if on:
        arm[joint_selection.MOVE_SKINNED] = True
        bpy.ops.object.mode_set(mode='EDIT')
        for eb in arm.data.edit_bones:
            eb.select = eb.select_head = eb.select_tail = False
        for i, name in enumerate(picked):
            joint_selection.select_edit(context, arm, name, shift=i > 0)
        if not picked:
            joint_selection.select_roots_if_empty(arm)
    else:
        arm.pop(joint_selection.MOVE_SKINNED, None)
        bpy.ops.object.mode_set(mode='POSE')
        joint_selection.select_roots_if_empty(arm)
    return on


classes = (ALLSET_OT_move_skinned_joints, ALLSET_OT_reset_skin_weights, ALLSET_OT_ik_handle, ALLSET_OT_pole_vector, ALLSET_OT_skin_cluster_question,
           ALLSET_OT_skin_cluster_answer, ALLSET_OT_bind_skin, ALLSET_OT_unbind_skin,
           ALLSET_OT_paint_skin_weights, ALLSET_OT_weight_paint_exit, ALLSET_OT_flood_weights, ALLSET_OT_copy_skin_weights, ALLSET_OT_mirror_skin_weights,
           ALLSET_OT_copy_vertex_weights, ALLSET_OT_paste_vertex_weights)
