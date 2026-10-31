# SPDX-License-Identifier: GPL-3.0-or-later
"""Skin basics with Maya's meaning (Issue #164): Prune Small Weights, Set Max Influences, Go to Bind Pose,
Maintain max influences. Fixture numbers:
tests/test_step247_skin_basics.py.

A Maya skinCluster influence = a vertex group named like a joint of the mesh's skeleton; a locked influence (Maya
``.liw``) = the vertex group's ``lock_weight``.
"""

import bpy
import numpy as np
from bpy.props import FloatProperty, IntProperty, BoolProperty

from .. import results
from . import skin
from .rig_maya import (MAX_INFLUENCES, MAX_INFLUENCES_PROP, DROPOFF_PROP, _influence_groups, _joint_segments,
                       maya_add_weights)

BIND_POSE = "allset_bind_pose"          # armature ID prop {bone: 16 floats of the pose bone's matrix_basis at bind}
MAINTAIN_MAX = "allset_maintain_max"    # mesh ID prop: Maya skinCluster.maintainMaxInfluences
PRUNE_BELOW = 0.01                      # default Prune Small Weights threshold


# --- weight matrix ----------------------------------------------------------------------------------

def weights(mesh, groups):
    """(V, K) weights of ``groups`` (vertex groups) on every vertex."""
    col = {g.index: j for j, g in enumerate(groups)}
    w = np.zeros((len(mesh.data.vertices), len(groups)))
    for v in mesh.data.vertices:
        for g in v.groups:
            j = col.get(g.group)
            if j is not None:
                w[v.index, j] = g.weight
    return w


def write(mesh, groups, w, rows):
    """Write rows ``rows`` of ``w`` back: zeros leave the group (Maya: no membership for weight 0)."""
    member = {(v.index, g.group) for i in rows for v in [mesh.data.vertices[int(i)]] for g in v.groups}
    for j, vg in enumerate(groups):
        for i in rows:
            value = float(w[i, j])
            if value > 0.0:
                vg.add([int(i)], value, 'REPLACE')
            elif (int(i), vg.index) in member:
                vg.remove([int(i)])


def target_rows(mesh):
    """Maya filterSelected: the selected vertices when some are selected in Edit / Weight Paint (vertex mask), else
    every vertex."""
    me = mesh.data
    if mesh.mode == 'EDIT':
        mesh.update_from_editmode()
    use = mesh.mode == 'EDIT' or (mesh.mode == 'WEIGHT_PAINT' and (me.use_paint_mask_vertex or me.use_paint_mask))
    if use:
        sel = np.zeros(len(me.vertices), dtype=bool)
        me.vertices.foreach_get("select", sel)
        if sel.any():
            return np.flatnonzero(sel)
    return np.arange(len(me.vertices))


class _ObjectData:
    """Vertex group writes need the mesh out of Edit mode; come back afterwards."""

    def __init__(self, mesh):
        self.mesh, self.edit = mesh, mesh.mode == 'EDIT'

    def __enter__(self):
        if self.edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        return self

    def __exit__(self, *exc):
        self.mesh.data.update()
        if self.edit:
            bpy.ops.object.mode_set(mode='EDIT')


# --- Prune Small Weights ----------------------------------------------------------------------------

def prune_matrix(w, locked, below=PRUNE_BELOW):
    """Maya prune on (V, K) weights: unlocked weights < ``below`` -> 0, the unlocked rest rescaled to 1 - locked sum
    ([0.6, 0.005, 0.3, 0.095] -> [0.603015, 0, 0.301508, 0.095477]; a locked small weight stays).
    Returns (new weights, changed row mask)."""
    w = np.array(w, dtype=np.float64)
    locked = np.asarray(locked, dtype=bool)
    cut = (w > 0.0) & (w < below) & ~locked[None, :]
    changed = cut.any(axis=1)
    out = np.where(cut, 0.0, w)
    free = np.where(locked[None, :], 0.0, out)
    rest = 1.0 - (out * locked[None, :]).sum(axis=1)
    total = free.sum(axis=1)
    scale = np.where(changed & (total > 0.0), rest / np.where(total > 0.0, total, 1.0), 1.0)
    out = np.where(locked[None, :], out, out * scale[:, None])
    return out, changed


def prune(mesh, below=PRUNE_BELOW):
    """Prune the skinned mesh's selected (else all) vertices; returns the number of vertices changed."""
    groups = _influence_groups(mesh)
    if not groups:
        return 0
    rows = target_rows(mesh)
    with _ObjectData(mesh):
        w = weights(mesh, groups)
        out, changed = prune_matrix(w[rows], [g.lock_weight for g in groups], below)
        w[rows] = out
        done = rows[changed]
        write(mesh, groups, w, done)
    return len(done)


# --- Set Max Influences / Maintain max influences ---------------------------------------------------

def _world_points(mesh):
    me = mesh.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    mw = np.array(mesh.matrix_world)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def set_max_influences(mesh, n):
    """Maya Set Max Influences: skinCluster.maxInfluences = n and the closest-distance weights recomputed by the Add
    Influence rule without a new influence. Returns the number of vertices written."""
    arm = skin.armature_modifier(mesh).object
    groups = _influence_groups(mesh)
    mesh[MAX_INFLUENCES_PROP] = int(n)
    if not groups:
        return 0
    segs = _joint_segments(arm, [g.name for g in groups])
    if any(g.name not in segs for g in groups):
        return 0
    stored = mesh.get(DROPOFF_PROP) or {}
    dropoffs = [float(stored.get(g.name, skin.DROPOFF)) for g in groups]
    rows = target_rows(mesh)
    with _ObjectData(mesh):
        w = weights(mesh, groups)
        out = maya_add_weights(_world_points(mesh)[rows], w[rows], [segs[g.name] for g in groups],
                               [False] * len(groups), [g.lock_weight for g in groups], dropoffs, int(n))
        w[rows] = out
        write(mesh, groups, w, rows)
    return len(rows)


def enforce_max_matrix(w, locked, n):
    """Maya maintainMaxInfluences: while a vertex has more than ``n`` weighted
    influences, the smallest goes to 0 — unlocked ones first, locked ones last; the freed weight is redistributed to the
    remaining unlocked ones (normalisation)."""
    w = np.array(w, dtype=np.float64)
    locked = np.asarray(locked, dtype=bool)
    for i in np.flatnonzero((w > 0.0).sum(axis=1) > n):
        row = w[i]
        order = sorted(np.flatnonzero(row > 0.0), key=lambda j: (bool(locked[j]), row[j]))
        for j in order[:len(order) - n]:
            row[j] = 0.0
        free = ~locked & (row > 0.0)
        rest = 1.0 - row[locked].sum()
        total = row[free].sum()
        if total > 0.0:
            row[free] *= rest / total
    return w


def enforce_max(mesh):
    """Apply Maintain max influences to a mesh whose skin has it on; returns the vertices changed."""
    if not mesh.get(MAINTAIN_MAX, False):
        return 0
    groups = _influence_groups(mesh)
    if not groups:
        return 0
    n = int(mesh.get(MAX_INFLUENCES_PROP, MAX_INFLUENCES))
    w = weights(mesh, groups)
    rows = np.flatnonzero((w > 0.0).sum(axis=1) > n)
    if not len(rows):
        return 0
    out = enforce_max_matrix(w, [g.lock_weight for g in groups], n)
    write(mesh, groups, out, rows)
    return len(rows)


# --- Go to Bind Pose --------------------------------------------------------------------------------

def store_bind_pose(arm):
    """Maya bindPose: every joint's transform at bind (the pose bones' matrix_basis)."""
    arm[BIND_POSE] = {pb.name: [x for row in pb.matrix_basis for x in row] for pb in arm.pose.bones}


def drop_bind_pose_members(arm, names):
    stored = arm.get(BIND_POSE)
    if stored is None:
        return
    keep = {k: list(v) for k, v in stored.items() if k not in names}
    arm[BIND_POSE] = keep


def forget_bind_pose(arm):
    """Unbind deletes the bind pose once no mesh is skinned to the skeleton (fixture after_unbind bindPoses [])."""
    if BIND_POSE in arm and not any(skin.armature_modifier(o) is not None and skin.armature_modifier(o).object == arm
                                    for o in bpy.data.objects if o.type == 'MESH'):
        del arm[BIND_POSE]


def go_to_bind_pose(arm):
    """Every joint back to its transform at bind (Maya dagPose -restore -global -bindPose); a skeleton without a stored
    bind pose goes to its rest pose (Blender's bind). Returns the number of joints set."""
    from mathutils import Matrix
    stored = arm.get(BIND_POSE) or {}
    n = 0
    for pb in arm.pose.bones:
        v = stored.get(pb.name)
        m = Matrix([list(v)[i:i + 4] for i in range(0, 16, 4)]) if v is not None and len(v) == 16 else Matrix()
        if v is None and BIND_POSE in arm:
            continue                       # not a member of the bind pose (a joint added afterwards): left alone
        pb.matrix_basis = m
        n += 1
    return n


def _skeletons(context):
    out = []
    for ob in [context.active_object, *context.selected_objects]:
        if ob is None:
            continue
        arm = ob if ob.type == 'ARMATURE' else (skin.armature_modifier(ob).object if ob.type == 'MESH'
                                                 and skin.armature_modifier(ob) is not None else None)
        if arm is not None and arm not in out:
            out.append(arm)
    return out


# --- operators --------------------------------------------------------------------------------------

def _skinned_meshes(context):
    out = [o for o in [context.active_object, *context.selected_objects]
           if o is not None and o.type == 'MESH' and skin.armature_modifier(o) is not None]
    return list(dict.fromkeys(out))


class ALLSET_OT_prune_small_weights(bpy.types.Operator):
    """Maya Prune Small Weights: weights below the threshold leave the selected vertices (or the whole skin); the
    rest are normalised. Locked joints keep theirs"""
    bl_idname = "allset.prune_small_weights"
    bl_label = "Prune Weights Options"
    bl_options = {'UNDO'}

    below: FloatProperty(name="Prune below", default=PRUNE_BELOW, min=0.0, max=1.0, precision=4)
    option_box: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return bool(_skinned_meshes(context))

    def invoke(self, context, event):
        if self.option_box:
            return context.window_manager.invoke_props_dialog(self, width=320, confirm_text="Prune")
        from .joints import _load_options
        _load_options(self, "prune_small_weights", ("below",))
        return self.execute(context)

    def execute(self, context):
        from .joints import _save_options
        _save_options(self, "prune_small_weights", ("below",))
        n = sum(prune(m, self.below) for m in _skinned_meshes(context))
        results.result(self, f"Pruned weights on {n} vertices")
        return {'FINISHED'}


class ALLSET_OT_set_max_influences(bpy.types.Operator):
    """Maya Set Max Influences: limit each vertex to this many joints (weights recomputed by distance; locked joints
    keep theirs)"""
    bl_idname = "allset.set_max_influences"
    bl_label = "Set Max Influences"
    bl_options = {'UNDO'}

    max_influences: IntProperty(name="Max influences", default=MAX_INFLUENCES, min=1, max=30)

    @classmethod
    def poll(cls, context):
        return bool(_skinned_meshes(context))

    def invoke(self, context, event):
        from .joints import _load_options
        _load_options(self, "set_max_influences", ("max_influences",))
        return context.window_manager.invoke_props_dialog(self, width=320, confirm_text="Apply")

    def execute(self, context):
        from .joints import _save_options
        _save_options(self, "set_max_influences", ("max_influences",))
        n = sum(set_max_influences(m, self.max_influences) for m in _skinned_meshes(context))
        results.result(self, f"Max influences {self.max_influences} on {n} vertices")
        return {'FINISHED'}


class ALLSET_OT_go_to_bind_pose(bpy.types.Operator):
    """Maya Go to Bind Pose: every joint of the skeleton back to where it was when the skin was bound"""
    bl_idname = "allset.go_to_bind_pose"
    bl_label = "Go to Bind Pose"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(_skeletons(context))

    def execute(self, context):
        arms = _skeletons(context)
        n = sum(go_to_bind_pose(a) for a in arms)
        results.result(self, f"Bind pose: {n} joint(s)")
        return {'FINISHED'}


classes = (ALLSET_OT_prune_small_weights, ALLSET_OT_set_max_influences, ALLSET_OT_go_to_bind_pose)
