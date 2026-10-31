# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Ctrl+G group and Edit > Ungroup.

Edit > Group default options (under Parent, Preserve position, pivot at the origin)
creates the group under the common parent with its pivot at the origin; with
nothing selected it makes an empty group. Names are ``group1``, ``group2``, ...

Blender form: an Empty is the group transform. Children are parented the Maya
way: world transform kept, ``matrix_parent_inverse``
left at identity so the child's local values are relative to the group.
"""

import bpy
from mathutils import Matrix

from .. import results
from . import units


def next_group_name(names):
    """Maya's next ``groupN`` given existing object names: one past the highest (no gap filling)."""
    from . import naming
    return f"group{naming.next_number('group', set(names))}"


def common_parent(objects):
    parents = {ob.parent for ob in objects}
    return parents.pop() if len(parents) == 1 else None


def set_parent_keep_world(child, parent):
    """Parent with identity parent-inverse while keeping the world matrix."""
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_parent_inverse = Matrix.Identity(4)
    child.matrix_world = world


def make_group(context, objects):
    """Create a Maya-style group over ``objects``. Returns the new Empty."""
    objects = list(objects)
    parent = common_parent(objects) if objects else None
    if objects and objects[0].users_collection:
        collection = objects[0].users_collection[0]
    else:
        collection = context.collection

    grp = bpy.data.objects.new(next_group_name(o.name for o in bpy.data.objects), None)
    grp.empty_display_type = 'PLAIN_AXES'
    # 1 Maya unit, like a Create locator
    grp.empty_display_size = units.maya_unit(context.scene)
    collection.objects.link(grp)
    if parent is not None:
        # Under the common parent with an identity local transform, so the
        # group pivot sits at the parent's origin (Maya zeroPivot).
        grp.parent = parent
        grp.matrix_parent_inverse = Matrix.Identity(4)
    grp.matrix_basis = Matrix.Identity(4)
    context.view_layer.update()

    from . import skin_follow
    for ob in objects:
        if ob.type == 'ARMATURE':
            skin_follow.ensure(ob)      # its skin moves with the group (meshes bound before the kit's follow)
        set_parent_keep_world(ob, grp)
    return grp


def ungroup(context, groups, world=False, preserve=True):
    """Maya Edit > Ungroup (default Ungroup under Parent, Preserve position on): each group's
    children move under the group's parent (``world``: to the world; the world when it has none) keeping their world
    transform, then the group goes. Preserve position off (``cmds.ungroup(relative=True)``) folds the group's local
    transform into each child's local values instead (grp t 0 5 0, child t 1 2 3 -> child t 1 7 3).
    A selected object that has data of its own (a mesh with
    children) only loses its children. Returns the moved children."""
    moved = []
    for grp in groups:
        kids = list(grp.children)
        target = None if world else grp.parent
        for child in kids:
            if not preserve:
                local = grp.matrix_parent_inverse @ grp.matrix_basis @ child.matrix_parent_inverse @ child.matrix_basis
                child.parent = target
                child.matrix_parent_inverse = Matrix.Identity(4)
                child.matrix_basis = local
            elif target is not None:
                set_parent_keep_world(child, target)
            else:
                world_m = child.matrix_world.copy()
                child.parent = None
                child.matrix_world = world_m
        moved.extend(kids)
        if grp.type == 'EMPTY':
            bpy.data.objects.remove(grp)
    return moved


class ALLSET_OT_ungroup(bpy.types.Operator):
    """Move the children of the selected groups up one level and delete the groups (Maya Ungroup)"""
    bl_idname = "allset.ungroup"
    bl_label = "Ungroup"
    bl_options = {'REGISTER', 'UNDO'}

    under: bpy.props.EnumProperty(
        name="Ungroup Under", options={'SKIP_SAVE'},
        items=(('PARENT', "Parent", "Under the group's parent (Maya Ungroup Options, default)"),
               ('WORLD', "World", "At the top of the hierarchy")))
    preserve_position: bpy.props.BoolProperty(
        name="Preserve Position", default=True, options={'SKIP_SAVE'},
        description="Keep the children where they are (off = the group's transform goes into their local values)")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(ob.children for ob in context.selected_objects)

    def execute(self, context):
        groups = [ob for ob in context.selected_objects if ob.children]
        # Innermost first, so nested selected groups hand their children up step by step.
        groups.sort(key=_depth, reverse=True)
        moved = ungroup(context, groups, self.under == 'WORLD', self.preserve_position)
        context.view_layer.update()
        for ob in moved:
            if ob.name in context.view_layer.objects:
                ob.select_set(True)
        if moved:
            context.view_layer.objects.active = moved[0]
        results.result(self, f"Ungrouped {len(groups)} group(s)")
        return {'FINISHED'}


def _depth(ob):
    n = 0
    while ob.parent is not None:
        ob, n = ob.parent, n + 1
    return n


# A joint inside a bone chain can't be given a group parent here (a bone's parent is another bone of its skeleton).
CHILD_JOINT_WARNING = ("Cannot group joint {name}: only the top (root) joints of a skeleton can go under a group. "
                       "Select the root joint to group the whole skeleton.")
SOME_ROOTS_WARNING = ("Cannot group joint {name} alone: its skeleton has other root joints ({others}) that would move "
                      "with it. Select every root joint of the skeleton.")


def joint_selection(context):
    """Selected joints as ``(skeletons, warning)``: the armature objects whose root joints are picked (pose mode,
    or skeleton edit mode), or a warning text when a picked joint can't be grouped on its own."""
    from . import joints
    skeletons = []
    for ob in context.view_layer.objects:
        if ob is None or ob.type != 'ARMATURE' or ob.mode not in {'POSE', 'EDIT'}:
            continue
        picked = joints.selected_joint_names(ob)
        if not picked:
            continue
        bones = ob.data.edit_bones if ob.mode == 'EDIT' else ob.data.bones
        for name in picked:
            bone = bones.get(name)
            if bone is not None and bone.parent is not None:
                return [], CHILD_JOINT_WARNING.format(name=name)
        roots = [b.name for b in bones if b.parent is None]
        others = [n for n in roots if n not in picked]
        if others:
            return [], SOME_ROOTS_WARNING.format(name=picked[0], others=", ".join(others))
        skeletons.append(ob)
    return skeletons, None


class ALLSET_OT_group(bpy.types.Operator):
    """Group the selected objects under a new transform (Maya Ctrl+G). With root joints selected their skeleton
    goes under the group"""
    bl_idname = "allset.group"
    bl_label = "Group"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'POSE', 'EDIT_ARMATURE'} and context.view_layer is not None

    def execute(self, context):
        skeletons, in_mode = [], set()
        if context.mode != 'OBJECT':
            skeletons, warning = joint_selection(context)
            if warning:
                self.report({'WARNING'}, warning)
                return {'CANCELLED'}
            # a skeleton in pose / edit mode counts through its picked joints only
            in_mode = {ob for ob in context.view_layer.objects if ob is not None and ob.mode != 'OBJECT'}
            bpy.ops.object.mode_set(mode='OBJECT')      # Maya selects the new group (an object)
        objects = skeletons + [ob for ob in context.selected_objects if ob not in in_mode]
        grp = make_group(context, objects)
        for ob in context.selected_objects:
            ob.select_set(False)
        grp.select_set(True)
        context.view_layer.objects.active = grp
        results.result(self, f"Result: {grp.name}")       # Maya: "// Result: group1 //" (the group command's return)
        from ..ui import view_message
        # Maya Edit > Group: success, or an empty group with "select objects first".
        view_message.show(context, f"<hl>{grp.name}</hl> grouped." if objects else
                          f"Nothing selected: <hl>{grp.name}</hl> is empty. <hl>Select</hl> objects before grouping.")
        return {'FINISHED'}


classes = (ALLSET_OT_group, ALLSET_OT_ungroup)
