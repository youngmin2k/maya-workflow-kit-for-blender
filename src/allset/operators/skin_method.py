# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya skinCluster Skinning Method (Issue #167): Classic Linear / Dual Quaternion / Weight Blended.

Maya 2026 (numbers
in tests/test_step250_skin_method.py): Dual Quaternion = DQ skinning with hemisphere alignment, scale blended linearly
before the rigid DQ (dqsSupportNonRigid 0, factory); Weight Blended = per vertex (1 - b) * linear + b * DQ with the
skinCluster's blendWeights b (factory 0 = linear).

Blender: Dual Quaternion = the Armature modifier's Preserve Volume (equal to Maya's vertices, see the test);
Weight Blended = the skin's Armature modifier (linear) followed by a second Armature modifier of the same skeleton
with Preserve Volume and Multi Modifier, mixed by the vertex group ``blendWeights`` (Blender's multi modifier: same
input as the previous modifier, result = lerp(previous, this, group weight) — Maya's formula). The second modifier is a
part of the skin: hidden from INPUTS and from the skin lists (``is_part``).
"""

import bpy

BLEND_GROUP = "blendWeights"           # Maya skinCluster.blendWeights (a vertex group, not an influence)
METHODS = ("CLASSIC_LINEAR", "DUAL_QUATERNION", "WEIGHT_BLENDED")
MAYA_VALUE = {"CLASSIC_LINEAR": 0, "DUAL_QUATERNION": 1, "WEIGHT_BLENDED": 2}   # skinCluster.skinningMethod
PART_SUFFIX = ".dqBlend"


def is_part(md):
    """The Weight Blended DQ half of a skin."""
    return (md.type == 'ARMATURE' and md.use_multi_modifier and md.vertex_group == BLEND_GROUP
            and md.name.endswith(PART_SUFFIX))


def _main(mesh):
    return next((m for m in mesh.modifiers if m.type == 'ARMATURE' and m.object is not None and not is_part(m)),
                None)


def part_of(mesh):
    return next((m for m in mesh.modifiers if is_part(m)), None)


def method_of(mesh):
    md = _main(mesh)
    if md is None:
        return None
    if part_of(mesh) is not None:
        return "WEIGHT_BLENDED"
    return "DUAL_QUATERNION" if md.use_deform_preserve_volume else "CLASSIC_LINEAR"


def set_method(mesh, method):
    """Give the mesh's skin Maya's skinning method; returns the method set (None = no skin)."""
    md = _main(mesh)
    if md is None:
        return None
    part = part_of(mesh)
    if method != "WEIGHT_BLENDED":
        if part is not None:
            mesh.modifiers.remove(part)
        md.use_deform_preserve_volume = method == "DUAL_QUATERNION"
        return method
    md.use_deform_preserve_volume = False
    if mesh.vertex_groups.get(BLEND_GROUP) is None:
        mesh.vertex_groups.new(name=BLEND_GROUP)          # blend weights start at 0: linear until painted
    if part is None:
        part = mesh.modifiers.new(md.name + PART_SUFFIX, 'ARMATURE')
    part.object = md.object
    part.use_vertex_groups = md.use_vertex_groups
    part.use_bone_envelopes = md.use_bone_envelopes
    part.use_deform_preserve_volume = True
    part.use_multi_modifier = True
    part.vertex_group = BLEND_GROUP
    part.invert_vertex_group = False
    i, j = list(mesh.modifiers).index(md), list(mesh.modifiers).index(part)
    if j != i + 1:
        with bpy.context.temp_override(object=mesh):
            bpy.ops.object.modifier_move_to_index(modifier=part.name, index=i + 1 if j > i else i)
    return method


def set_blend_weights(mesh, weights):
    """Maya blendWeights per vertex (``weights`` = {vertex index: b} or a list)."""
    vg = mesh.vertex_groups.get(BLEND_GROUP) or mesh.vertex_groups.new(name=BLEND_GROUP)
    items = weights.items() if isinstance(weights, dict) else enumerate(weights)
    for i, b in items:
        if b > 0.0:
            vg.add([int(i)], float(b), 'REPLACE')
        else:
            vg.remove([int(i)])
    return vg


# --- the Attribute Editor's Skinning Method (skinCluster tab) ----------------------------------------------

_ITEMS = (("CLASSIC_LINEAR", "Classic Linear", "Linear blend of the joint matrices"),
          ("DUAL_QUATERNION", "Dual Quaternion", "Volume-preserving blend (Blender Preserve Volume)"),
          ("WEIGHT_BLENDED", "Weight Blended", "Per vertex mix of linear and dual quaternion by blendWeights"))


def _get(ob):
    return METHODS.index(method_of(ob) or "CLASSIC_LINEAR")


def _set(ob, value):
    set_method(ob, METHODS[value])


def register_props():
    bpy.types.Object.allset_skinning_method = bpy.props.EnumProperty(
        name="Skinning Method", items=_ITEMS, get=_get, set=_set,
        description="Maya skinCluster Skinning Method")


def unregister_props():
    if hasattr(bpy.types.Object, "allset_skinning_method"):
        del bpy.types.Object.allset_skinning_method
