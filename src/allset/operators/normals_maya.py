# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya 2022 Mesh Display normal commands: Set Vertex Normal, Lock / Unlock Normals, Average, Set to Face.

Maya rules on explicit meshes.

Maya keeps a normal per vertex-face (corner) with a "locked" (frozen, user) flag; Blender's custom split normals are
the same thing: a corner with a custom normal keeps it, a corner without one (custom value (0, 0) in its normal
space) follows the computed normal. So locked = custom, unlocked = auto, and every command rewrites the mesh's
custom normals with ``Mesh.normals_split_custom_set`` (an unlocked corner gets the computed normal). Blender can't tell a locked corner whose
normal equals the computed one from an unlocked one (such a lock is lost; it looks the same).

Which corners: Object Mode = every corner of the selected meshes; Edit Mode = the corners of the selected vertices
(Maya's conversion of a vertex selection); Set to Face = the selected faces' corners.
"""

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty
from mathutils import Vector

from .. import results, undo_steps

AVERAGE_DISTANCE = 0.1      # Maya Average Normals Options factory distance (polyAverageNormalTol)
SET_NORMAL = (1.0, 0.0, 0.0)  # Maya Set Vertex Normal Options factory value (polySetNormalX / Y / Z)


# --- pure rules (tests/test_step189_normals.py) --------------------------------------------------------------

def unit(v):
    v = Vector(v)
    return tuple(v.normalized()) if v.length > 1e-12 else (0.0, 0.0, 0.0)


def set_vertex_normal(normals, locked, corners, xyz):
    """Maya Set Vertex Normal (polyNormalPerVertex -xyz): the corners get the unit ``xyz`` and are locked."""
    n = unit(xyz)
    for c in corners:
        normals[c] = n
        locked[c] = True


def average(normals, locked, groups):
    """Maya Average (polyAverageNormal, prenormalize): every corner of a group of vertices (a selected vertex and the
    selected vertices within the distance) gets the normalised sum of the group's unit corner normals, locked."""
    for corners in groups:
        n = unit(sum((Vector(unit(normals[c])) for c in corners), Vector()))
        for c in corners:
            normals[c] = n
            locked[c] = True


def distance_groups(positions, chosen, corners_of, distance):
    """Groups of the chosen vertices: vertices within ``distance`` (Maya -distance, <= so coincident vertices join at 0)
    are averaged together (union-find over pairs)."""
    chosen = sorted(chosen)
    parent = {v: v for v in chosen}

    def find(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for i, a in enumerate(chosen):
        for b in chosen[i + 1:]:
            if (Vector(positions[a]) - Vector(positions[b])).length <= distance + 1e-9:
                parent[find(a)] = find(b)
    groups = {}
    for v in chosen:
        groups.setdefault(find(v), []).extend(corners_of[v])
    return [sorted(g) for _r, g in sorted(groups.items())]


# --- Blender mesh access ----------------------------------------------------------------------------------------

def locked_corners(me):
    """Per corner: has a custom (locked) normal."""
    attr = me.attributes.get("custom_normal")
    if attr is None or not me.has_custom_normals:
        return [False] * len(me.loops)
    if attr.data_type == 'INT16_2D':
        return [tuple(d.value) != (0, 0) for d in attr.data]
    return [Vector(d.vector).length > 1e-9 for d in attr.data]   # free normals: a stored vector


def current(me):
    return [tuple(n.vector) for n in me.corner_normals], locked_corners(me)


def computed(me):
    """The corner normals Blender computes for ``me`` without custom normals."""
    plain = me.copy()
    try:
        attr = plain.attributes.get("custom_normal")
        if attr is not None:
            plain.attributes.remove(attr)
        return [tuple(n.vector) for n in plain.corner_normals]
    finally:
        bpy.data.meshes.remove(plain)


def write(me, normals, locked):
    """Custom normals = the locked corners' normals; the others get the computed normal (stored as "no custom
    normal": a zero vector isn't reliably taken as auto on hard edges). No locked corner = none at all."""
    attr = me.attributes.get("custom_normal")
    if not any(locked):
        if attr is not None:
            me.attributes.remove(attr)
        return
    auto = computed(me)
    me.normals_split_custom_set([normals[i] if locked[i] else auto[i] for i in range(len(me.loops))])


def _targets(context):
    if context.mode == 'EDIT_MESH':
        return [o for o in context.objects_in_mode_unique_data if o.type == 'MESH']
    return [o for o in context.selected_objects if o.type == 'MESH']


class _Selection:
    """Selected vertices / faces read in Edit Mode, then Object Mode for the custom-normal writes (Mesh API)."""

    def __init__(self, context):
        self.edit = context.mode == 'EDIT_MESH'
        self.obs = _targets(context)
        self.sel = {}
        for ob in self.obs:
            if self.edit:
                bm = bmesh.from_edit_mesh(ob.data)
                self.sel[ob.name] = ({v.index for v in bm.verts if v.select},
                                     {f.index for f in bm.faces if f.select})
            else:
                me = ob.data
                self.sel[ob.name] = (set(range(len(me.vertices))), set(range(len(me.polygons))))
        if self.edit:
            bpy.ops.object.mode_set(mode='OBJECT')

    def close(self):
        if self.edit:
            bpy.ops.object.mode_set(mode='EDIT')

    def items(self):
        for ob in self.obs:
            verts, faces = self.sel[ob.name]
            yield ob, verts, faces


def corners_of_verts(me):
    out = {}
    for li, loop in enumerate(me.loops):
        out.setdefault(loop.vertex_index, []).append(li)
    return out


def _empty_warning(op, what):
    op.report({'WARNING'}, f"Select {what} (or a mesh in Object Mode).")
    return {'CANCELLED'}


@undo_steps.no_redo_panel
class ALLSET_OT_set_vertex_normal(bpy.types.Operator):
    """Set the normal of the selected vertices to a direction and lock it (Maya Mesh Display > Set Vertex Normal)"""
    bl_idname = "allset.set_vertex_normal"
    bl_label = "Set Vertex Normal"
    bl_options = {'REGISTER', 'UNDO'}

    x: FloatProperty(name="X", default=SET_NORMAL[0], options={'SKIP_SAVE'})
    y: FloatProperty(name="Y", default=SET_NORMAL[1], options={'SKIP_SAVE'})
    z: FloatProperty(name="Z", default=SET_NORMAL[2], options={'SKIP_SAVE'})

    def execute(self, context):
        if Vector((self.x, self.y, self.z)).length < 1e-12:
            self.report({'WARNING'}, "The normal can't be zero.")
            return {'CANCELLED'}
        sel = _Selection(context)
        done = 0
        try:
            for ob, verts, _faces in sel.items():
                me = ob.data
                of = corners_of_verts(me)
                corners = [c for v in verts for c in of.get(v, ())]
                if not corners:
                    continue
                normals, locked = current(me)
                set_vertex_normal(normals, locked, corners, (self.x, self.y, self.z))
                write(me, normals, locked)
                done += 1
        finally:
            sel.close()
        if not done:
            return _empty_warning(self, "vertices")
        results.result(self, f"polyNormalPerVertex -xyz {self.x:g} {self.y:g} {self.z:g}")
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_lock_normals(bpy.types.Operator):
    """Lock (freeze) the normals of the selected vertices (Maya Mesh Display > Lock Normals / Unlock Normals)"""
    bl_idname = "allset.lock_normals"
    bl_label = "Lock Normals"
    bl_options = {'REGISTER', 'UNDO'}

    unlock: BoolProperty(name="Unlock", default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        sel = _Selection(context)
        done = 0
        try:
            for ob, verts, _faces in sel.items():
                me = ob.data
                of = corners_of_verts(me)
                corners = [c for v in verts for c in of.get(v, ())]
                if not corners:
                    continue
                normals, locked = current(me)
                for c in corners:
                    locked[c] = not self.unlock
                write(me, normals, locked)
                done += 1
        finally:
            sel.close()
        if not done:
            return _empty_warning(self, "vertices")
        results.result(self, "polyNormalPerVertex -ufn true" if self.unlock else "polyNormalPerVertex -fn true")
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_average_normals(bpy.types.Operator):
    """Average the normals of the selected vertices, joining vertices closer than the distance (Maya Mesh Display >
    Average)"""
    bl_idname = "allset.average_normals"
    bl_label = "Average Normals"
    bl_options = {'REGISTER', 'UNDO'}

    distance: FloatProperty(name="Distance", default=AVERAGE_DISTANCE, min=0.0, options={'SKIP_SAVE'})

    def execute(self, context):
        sel = _Selection(context)
        done = 0
        try:
            for ob, verts, _faces in sel.items():
                me = ob.data
                if not verts:
                    continue
                normals, locked = current(me)
                positions = [tuple(v.co) for v in me.vertices]
                groups = distance_groups(positions, verts, corners_of_verts(me), self.distance)
                average(normals, locked, groups)
                write(me, normals, locked)
                done += 1
        finally:
            sel.close()
        if not done:
            return _empty_warning(self, "vertices")
        results.result(self, f"polyAverageNormal -distance {self.distance:g}")
        return {'FINISHED'}


@undo_steps.no_redo_panel
class ALLSET_OT_set_to_face_normal(bpy.types.Operator):
    """Give the selected faces their face normal at every corner (Maya Mesh Display > Set to Face)"""
    bl_idname = "allset.set_to_face_normal"
    bl_label = "Set to Face Normals"
    bl_options = {'REGISTER', 'UNDO'}

    user_normal: BoolProperty(name="Set user normal", default=False, options={'SKIP_SAVE'},
                              description="Lock the face normals (Maya -setUserNormal); off = hard edges, unlocked")

    def execute(self, context):
        sel = _Selection(context)
        done = 0
        try:
            for ob, _verts, faces in sel.items():
                me = ob.data
                if not faces:
                    continue
                normals, locked = current(me)
                for fi in faces:
                    poly = me.polygons[fi]
                    for li in poly.loop_indices:
                        normals[li] = tuple(poly.normal)
                        locked[li] = self.user_normal
                edges = {ek for fi in faces for ek in me.polygons[fi].edge_keys}
                for e in me.edges:
                    if e.key in edges:
                        e.use_edge_sharp = True     # Maya: the faces' edges become hard (cube case)
                write(me, normals, locked)
                done += 1
        finally:
            sel.close()
        if not done:
            return _empty_warning(self, "faces")
        results.result(self, "polySetToFaceNormal -setUserNormal" if self.user_normal else "polySetToFaceNormal")
        return {'FINISHED'}


classes = (ALLSET_OT_set_vertex_normal, ALLSET_OT_lock_normals, ALLSET_OT_average_normals,
           ALLSET_OT_set_to_face_normal)
