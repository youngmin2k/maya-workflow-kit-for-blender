# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Duplicate (Ctrl+D), Duplicate Special (Ctrl+Shift+D) and Duplicate with
Transform (Shift+D).

Maya ``duplicateSpecial`` default options (copy,
count 1, group under Parent, T/R = 0, S = 1) and ``shiftD``
(``cmds.duplicate(smartTransform=True)``). Edit > Duplicate Special runs with
the saved options (DuplicateSpecial), no dialog; Blender's Adjust Last Operation
edits them afterwards. Maya duplicates the whole subtree; names count up (``pCube1`` -> ``pCube2``).
"""

import bpy
from bpy.props import EnumProperty, FloatVectorProperty, IntProperty
from mathutils import Euler, Quaternion, Vector

from .. import undo_steps
from . import naming, prim_history
from .freeze import hierarchy
from .group import make_group

# Last duplicates made by this module: {copy name: source name} (smart transform).
PAIRS = {}


def selected_roots(objects):
    chosen = set(objects)
    out = []
    for ob in objects:
        p = ob.parent
        while p is not None and p not in chosen:
            p = p.parent
        if p is None:
            out.append(ob)
    return out


def copy_subtree(root, instance=False):
    """Copy ``root`` and its descendants (data copied, or shared for an instance)."""
    new_of = {}
    for ob in hierarchy([root]):
        new = ob.copy()
        if ob.data is not None and not instance:
            new.data = ob.data.copy()
        if not instance:   # Maya duplicates without the input graph: no polyCube1 on pCube2
            for idb in (new, new.data):
                for key in (prim_history.KEY, prim_history.PART):
                    if idb is not None and key in idb:
                        del idb[key]
        for coll in ob.users_collection:
            coll.objects.link(new)
        if ob is not root:
            new.parent = new_of[ob.parent]   # matrix_parent_inverse copied with the object
        naming.apply_maya_name(new, naming.base_name(ob.name), rename_data=not instance)
        new_of[ob] = new
    return new_of[root]


def offset_channels(ob, k, translate, rotate, scale):
    """k-th copy: channels t + k*T, r + k*R, s * S^k (Maya cumulative offsets)."""
    ob.location = Vector(ob.location) + k * Vector(translate)
    q = Euler(tuple(k * a for a in rotate)).to_quaternion()
    if ob.rotation_mode == 'QUATERNION':
        ob.rotation_quaternion = q @ ob.rotation_quaternion
    elif ob.rotation_mode == 'AXIS_ANGLE':
        angle, *axis = ob.rotation_axis_angle
        axis, angle = (q @ Quaternion(axis, angle)).to_axis_angle()
        ob.rotation_axis_angle = (angle, *axis)
    else:
        ob.rotation_euler = tuple(a + k * b for a, b in zip(ob.rotation_euler, rotate))
    ob.scale = tuple(a * b ** k for a, b in zip(ob.scale, scale))


def _select(context, objects):
    for ob in context.selected_objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    if objects:
        context.view_layer.objects.active = objects[-1]


def duplicate(context, instance=False):
    """Copy every selected root with its subtree in place, Maya names; returns the copies.
    Records source pairs so a following Shift+D repeats the move between them."""
    roots = selected_roots(context.selected_objects)
    made, pairs = [], {}
    for root in roots:
        new = copy_subtree(root, instance)
        made.append(new)
        pairs[new.name] = root.name
    PAIRS.clear()
    PAIRS.update(pairs)
    _select(context, made)
    return made


class ALLSET_OT_duplicate(bpy.types.Operator):
    """Duplicate the selection in place with its children; copies are named the Maya way
    (pCube1 -> pCube2, pCubeShape2) and selected (Maya Edit > Duplicate, Ctrl+D)"""
    bl_idname = "allset.duplicate"
    bl_label = "Duplicate"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        if not duplicate(context):
            self.report({'WARNING'}, "Nothing selected")
            return {'CANCELLED'}
        return {'FINISHED'}


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_duplicate_special(bpy.types.Operator):
    """Duplicate with options: copies or instances, number of copies, offsets per
    copy, where to put them (Maya Edit > Duplicate Special)"""
    bl_idname = "allset.duplicate_special"
    bl_label = "Duplicate Special"
    bl_options = {'REGISTER', 'UNDO'}

    geometry_type: EnumProperty(
        name="Geometry Type",
        items=(('COPY', "Copy", "Copy the geometry"),
               ('INSTANCE', "Instance", "Share the geometry (Blender linked duplicate)")))
    group_under: EnumProperty(
        name="Group Under",
        items=(('PARENT', "Parent", "Same parent as the original"),
               ('WORLD', "World", "At the top of the hierarchy"),
               ('NEW_GROUP', "New Group", "Under a new group")))
    translate: FloatVectorProperty(name="Translate", subtype='TRANSLATION', unit='LENGTH')
    rotate: FloatVectorProperty(name="Rotate", subtype='EULER', unit='ROTATION')
    scale: FloatVectorProperty(name="Scale", default=(1.0, 1.0, 1.0), subtype='XYZ')
    copies: IntProperty(name="Number of Copies", default=1, min=1, soft_max=100, max=10000)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        roots = selected_roots(context.selected_objects)
        if not roots:
            self.report({'WARNING'}, "Nothing selected")
            return {'CANCELLED'}
        made, pairs = [], {}
        for root in roots:
            for k in range(1, self.copies + 1):
                new = copy_subtree(root, self.geometry_type == 'INSTANCE')
                offset_channels(new, k, self.translate, self.rotate, self.scale)
                made.append(new)
                if self.copies == 1:
                    pairs[new.name] = root.name
        context.view_layer.update()
        if self.group_under == 'WORLD':
            from .parenting import unparent
            unparent(made)
        elif self.group_under == 'NEW_GROUP':
            grp = make_group(context, made)
            made = [grp]
        PAIRS.clear()
        PAIRS.update(pairs)
        _select(context, made)
        return {'FINISHED'}


class ALLSET_OT_duplicate_with_transform(bpy.types.Operator):
    """Duplicate and repeat the transform between the last duplicate and its source,
    so repeated use builds an array (Maya Edit > Duplicate with Transform, Shift+D)"""
    bl_idname = "allset.duplicate_with_transform"
    bl_label = "Duplicate with Transform"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        roots = selected_roots(context.selected_objects)
        if not roots:
            self.report({'WARNING'}, "Nothing selected")
            return {'CANCELLED'}
        context.view_layer.update()
        made, pairs = [], {}
        for ob in roots:
            src = bpy.data.objects.get(PAIRS.get(ob.name, ""))
            new = copy_subtree(ob)
            if src is not None and src is not ob:
                delta = ob.matrix_world @ src.matrix_world.inverted_safe()
                new.matrix_world = delta @ ob.matrix_world
            made.append(new)
            pairs[new.name] = ob.name
        PAIRS.clear()
        PAIRS.update(pairs)
        _select(context, made)
        return {'FINISHED'}


classes = (ALLSET_OT_duplicate, ALLSET_OT_duplicate_special, ALLSET_OT_duplicate_with_transform)
