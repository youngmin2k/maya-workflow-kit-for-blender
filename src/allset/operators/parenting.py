# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya P / Shift+P: parent to the last selected, unparent to the world.

Maya ``parentPreserve 1`` /
``unparentPreserve 1``: the world transform is kept and the child's local
values are recomputed relative to the new parent.
That is the default ("Maya" Parent Mode, parent inverse = identity); the
"Blender" mode keeps Blender's parent inverse (``object.parent_set``).
"""

import bpy
from mathutils import Matrix

from .. import undo_steps

EPS = 1e-6


def is_ancestor(ob, other):
    """True if ``ob`` is ``other`` or one of its ancestors."""
    p = other
    while p is not None:
        if p is ob:
            return True
        p = p.parent
    return False


def set_parent_maya(child, parent):
    """Parent keeping the world matrix with the local values relative to the parent.

    The parent inverse stays identity unless the local matrix has shear (rotated
    child under a non-uniformly scaled parent): Maya stores that in ``shear``,
    Blender channels can't, so the residual goes into the parent inverse and the
    channels hold the closest translate/rotate/scale.
    """
    world = child.matrix_world.copy()
    local = parent.matrix_world.inverted_safe() @ world
    t, q, s = local.decompose()
    trs = Matrix.LocRotScale(t, q, s)
    residual = local @ trs.inverted_safe()
    exact = all(abs(residual[i][j] - (1.0 if i == j else 0.0)) < EPS
                for i in range(4) for j in range(4))
    child.parent = parent
    child.matrix_parent_inverse = Matrix.Identity(4) if exact else residual
    child.matrix_world = world


def set_parent_relative(child, parent):
    """Maya Parent / Unparent with Preserve position off (``cmds.parent(relative=True)``): the child keeps its local
    values, so it moves with the new parent (t 1 2 3 under a parent at 10 0 0 stays t 1 2 3)."""
    basis = child.matrix_basis.copy()
    child.parent = parent
    child.matrix_parent_inverse = Matrix.Identity(4)
    child.matrix_basis = basis


def parent_maya(children, parent, preserve=True):
    """Parent ``children`` under ``parent`` keeping their world matrices (``preserve`` off: their local values).
    Returns (parented, skipped cycles)."""
    done, cycles = [], []
    for ob in children:
        if ob is parent:
            continue
        if is_ancestor(ob, parent):
            cycles.append(ob)
            continue
        if preserve:
            set_parent_maya(ob, parent)
        else:
            set_parent_relative(ob, parent)
        done.append(ob)
    _to_end(done)
    return done, cycles


def _to_end(objects):
    """Maya lists a re-parented node last among its new siblings (Outliner order, ui/outliner_order.py)."""
    if objects and bpy.context.scene is not None:
        from ..ui import outliner_order
        outliner_order.to_end(objects, bpy.context.scene)


def unparent(objects, preserve=True):
    done = 0
    moved = [ob for ob in objects if ob.parent is not None]
    _to_end(moved)
    for ob in objects:
        if ob.parent is None:
            continue
        if not preserve:
            set_parent_relative(ob, None)
            done += 1
            continue
        world = ob.matrix_world.copy()
        ob.parent = None
        ob.matrix_parent_inverse = Matrix.Identity(4)
        ob.matrix_world = world
        done += 1
    return done


def _mode(context):
    from .. import preferences
    try:
        return preferences.get(context).parent_mode
    except KeyError:
        return 'MAYA'


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_parent(bpy.types.Operator):
    """Parent the selected objects under the last selected one, keeping them in place
    (Maya Edit > Parent, P)"""
    bl_idname = "allset.parent"
    bl_label = "Parent"
    bl_options = {'REGISTER', 'UNDO'}

    preserve_position: bpy.props.BoolProperty(
        name="Preserve Position", default=True, options={'SKIP_SAVE'},
        description="Keep the children where they are (Maya Parent Options; off = keep their local values)")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        parent = context.view_layer.objects.active
        children = [ob for ob in context.selected_objects if ob is not parent]
        if parent is None or not parent.select_get() or not children:
            self.report({'WARNING'}, "Select the children, then the parent last")
            return {'CANCELLED'}
        if _mode(context) == 'BLENDER':
            cycles = [ob for ob in children if is_ancestor(ob, parent)]
            if cycles:
                self.report({'WARNING'}, f"Cannot parent {parent.name} under its own child")
                return {'CANCELLED'}
            if not self.preserve_position:
                return bpy.ops.object.parent_no_inverse_set(keep_transform=False)
            return bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
        context.view_layer.update()
        done, cycles = parent_maya(children, parent, self.preserve_position)
        if cycles:
            self.report({'WARNING'}, "Skipped (parent is their descendant): "
                        + ", ".join(ob.name for ob in cycles))
        return {'FINISHED'} if done else {'CANCELLED'}


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_unparent(bpy.types.Operator):
    """Move the selected objects to the world, keeping them in place
    (Maya Edit > Unparent, Shift+P)"""
    bl_idname = "allset.unparent"
    bl_label = "Unparent"
    bl_options = {'REGISTER', 'UNDO'}

    preserve_position: bpy.props.BoolProperty(
        name="Preserve Position", default=True, options={'SKIP_SAVE'},
        description="Keep the objects where they are (Maya Unparent Options; off = keep their local values)")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        context.view_layer.update()
        unparent(context.selected_objects, self.preserve_position)
        return {'FINISHED'}


classes = (ALLSET_OT_parent, ALLSET_OT_unparent)
