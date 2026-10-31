# SPDX-License-Identifier: GPL-3.0-or-later
"""Deformer order (Maya ``reorderDeformers``) and Key > Set Blend Shape Target Weight Keys (L17 / L15b).

Maya 2026:
``reorderDeformers A B`` moves **B** to directly before A in evaluation order, so A then runs right after B; when B
already runs right before A, nothing moves and Maya warns "B and A are already in the specified order." With
three clusters (evaluation c1 c2 c3): (c3, c1) -> c2 c1 c3, (c1, c3) -> c3 c1 c2, (c1, c2) -> c2 c1 c3, (c2, c1) ->
warning. The kit's deformers are the object's modifiers (the stack = evaluation order); blend shapes are shape keys,
which Blender always evaluates first (= Maya's automatic Blend Shape placement before the skin) and can't move.
"""

import bpy
from bpy.props import StringProperty

from .. import results, undo_steps


class AlreadyInOrder(ValueError):
    pass


def reorder(order, a, b):
    """New evaluation order after ``reorderDeformers a b`` (``order`` = names, first evaluated first)."""
    order = list(order)
    ia, ib = order.index(a), order.index(b)
    if ia == ib:
        raise ValueError("same deformer")
    if ib + 1 == ia:
        raise AlreadyInOrder(f"{b} and {a} are already in the specified order.")
    order.remove(b)
    order.insert(order.index(a), b)
    return order


def movable(ob):
    """The modifiers the kit shows as Maya deformers / history nodes, in stack order (Channel Box INPUTS)."""
    from ..ui import channel_box
    own = [m for m in channel_box._inputs(ob) if m.id_data == ob]
    return own


def apply_order(ob, names):
    """Move ``ob``'s modifiers so the movable ones follow ``names``; the others keep their stack slots."""
    mods = ob.modifiers
    slots = sorted(i for i, m in enumerate(mods) if m.name in set(names))
    for slot, name in zip(slots, names):
        cur = mods.find(name)
        if cur != slot:
            with bpy.context.temp_override(object=ob):
                bpy.ops.object.modifier_move_to_index(modifier=name, index=slot)


def reorder_deformers(ob, a, b):
    """Maya ``reorderDeformers a b <ob>`` on modifier names ``a`` / ``b``. Raises AlreadyInOrder / ValueError."""
    names = [m.name for m in movable(ob)]
    if a not in names or b not in names:
        raise ValueError(f"{ob.name} has no deformer {a if a not in names else b}")
    new = reorder(names, a, b)
    apply_order(ob, new)
    return new


@undo_steps.no_redo_panel
class ALLSET_OT_reorder_deformers(bpy.types.Operator):
    """Change the order in which two deformers affect the object (Maya reorderDeformers: the first runs right after
    the second)"""
    bl_idname = "allset.reorder_deformers"
    bl_label = "Reorder Deformers"
    bl_options = {'REGISTER', 'UNDO'}

    object: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    first: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    second: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        ob = bpy.data.objects.get(self.object)
        if ob is None:
            return {'CANCELLED'}
        try:
            reorder_deformers(ob, self.first, self.second)
        except AlreadyInOrder as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        except ValueError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        results.result(self, f"reorderDeformers {self.first} {self.second} {ob.name}")
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()
        return {'FINISHED'}


# --- Key > Set Blend Shape Target Weight Keys ------------------------------------------------------------------

def blend_shape_keys(ob):
    """The target shape keys (not the basis) of ``ob``."""
    key = getattr(getattr(ob, "data", None), "shape_keys", None)
    if key is None:
        return []
    from . import blend_shapes_227   # in-between helper keys are driven, not Maya targets
    return blend_shapes_227.target_blocks(key)


def key_target_weights(context, objects):
    """Key every blend shape target weight (shape key Value) of ``objects`` at the current frame; returns the count.
    Maya 2026 keys nothing here,
    so the kit does what the menu name says."""
    frame = context.scene.frame_current
    n = 0
    for ob in objects:
        for kb in blend_shape_keys(ob):
            if kb.keyframe_insert("value", frame=frame):
                n += 1
    return n


# object types with a Maya shape node (mesh, NURBS curve / surface, lattice)
SHAPE_TYPES = {'MESH', 'CURVE', 'SURFACE', 'LATTICE'}


@undo_steps.no_redo_panel
class ALLSET_OT_key_blend_shape_weights(bpy.types.Operator):
    """Set keys on the blend shape target weights of the selected objects (Maya Key > Set Blend Shape Target Weight
    Keys; Blender: the shape key Values)"""
    bl_idname = "allset.key_blend_shape_weights"
    bl_label = "Set Blend Shape Target Weight Keys"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = list(context.selected_objects)
        if not any(ob.type in SHAPE_TYPES for ob in objects):
            # Maya 2026's message for nothing / a plain skeleton
            self.report({'ERROR'}, "No shape was selected.")
            return {'CANCELLED'}
        n = key_target_weights(context, objects)
        if not n:
            self.report({'WARNING'}, "No blend shape targets on the selected objects.")
            return {'CANCELLED'}
        results.result(self, f"Set {n} blend shape target weight key{'s' if n != 1 else ''}")
        return {'FINISHED'}


classes = (ALLSET_OT_reorder_deformers, ALLSET_OT_key_blend_shape_weights)
