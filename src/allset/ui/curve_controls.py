# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Show > NURBS Curves for rig controls drawn as bone custom shapes (Issue #173).

In the kit's model a Maya NURBS control is a bone with a curve custom shape. Blender draws a custom shape as part
of its armature, so the view's curve filter
(``SpaceView3D.show_object_viewport_curve``) hides curve *objects* only (NURBS Curves off, nothing selected: the
bone's circle is still drawn; Show > Joints off hides it). Blender has no
per-view switch for custom shapes, so the kit hides those bones (pose-bone hide, every view) and marks them; turning
NURBS Curves back on un-hides only marked bones, like Show > IK Handles (ui/panel_menus.show_ik_handles).
"""

import bpy

from .. import compat

MARK = "allset_hidden_by_curves"
CURVE_TYPES = {'CURVE'}          # Maya NURBS Curves; SURFACE / mesh shapes belong to other Show rows


def is_curve_control(pb):
    shape = pb.custom_shape
    return shape is not None and shape.type in CURVE_TYPES


def controls(scene):
    """Pose bones of the scene's armatures whose custom shape is a curve."""
    out = []
    for ob in scene.objects:
        if ob is None or ob.type != 'ARMATURE' or ob.pose is None:
            continue
        out.extend(pb for pb in ob.pose.bones if is_curve_control(pb))
    return out


def show(scene, on):
    """Show (on) or hide the curve-shaped controls. Hiding marks the bones it hid; showing un-hides only those."""
    for pb in controls(scene):
        if on:
            if pb.get(MARK):
                compat.set_bone_hidden(pb, False)
                del pb[MARK]
        elif not compat.bone_hidden(pb):
            compat.set_bone_hidden(pb, True)
            pb[MARK] = True


def sync(space, scene):
    """Make the controls follow this view's NURBS Curves flag (call after a kit path changed it)."""
    flag = getattr(space, "show_object_viewport_curve", None)
    if flag is None or scene is None:
        return
    show(scene, flag)


def hidden_by_kit(scene):
    return any(pb.get(MARK) for pb in controls(scene))


def release_all():
    """Disable: show again every bone the kit hid (the user's own hidden bones stay)."""
    for scene in bpy.data.scenes:
        for pb in controls(scene):
            if pb.get(MARK):
                compat.set_bone_hidden(pb, False)
                del pb[MARK]
