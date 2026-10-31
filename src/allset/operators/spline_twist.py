# SPDX-License-Identifier: GPL-3.0-or-later
"""Spline IK Twist / Roll / Twist Type like Maya (Issue #166).

Maya 2026 ikSplineSolver (numbers in
tests/test_step249_spline_twist.py): the handle's Twist is spread over the joints between the root and the end joint —
joint k of n (root 0, end n) turns about its own X by twist * (f(k / (n-1)) - f((k-1) / (n-1))) with the cumulative
curve f of Twist Type: Linear t, Ease In t^3, Ease Out 1 - (1 - t)^3, Ease In Out 3t^2 - 2t^3; Roll turns the root
joint about its X; the end joint gets nothing. (6 joints, twist 100: rx 25 / 25.4 / 25.5 / 24.4 on joints 1-4 — the
spread is per joint, Maya's rx differ from it by the bend's Euler mixing, <= 0.7 deg.)

Kit: a Spline IK handle is the ``SPLINE_IK`` constraint plus an ``ikHandleN`` empty at the end joint (Maya's
selectable handle) holding Twist / Roll / Twist Type as custom properties (Channel Box rows). Blender's Spline IK keeps
each bone's own pose roll about its Y (= Maya joint X), so a driver per chain bone writes the Maya amount into its
rotation Y. Deleting the handle removes the drivers and the constraint (Maya: the solver goes with its handle).
"""

import bpy

from .. import compat  # noqa: F401  (version differences go through compat)

HANDLE = "allset_spline_ik"            # empty ID prop: [armature name, IK bone name, constraint name]
TWIST, ROLL, TWIST_TYPE = "twist", "roll", "twistType"
TYPES = ("Linear", "Ease In", "Ease Out", "Ease In Out")
DEG = 0.017453292519943295


def cumulative(kind, t):
    """Maya twist distribution f(t) of Twist Type ``kind`` (0 Linear, 1 Ease In, 2 Ease Out, 3 Ease In Out)."""
    if kind == 1:
        return t ** 3
    if kind == 2:
        return 1.0 - (1.0 - t) ** 3
    if kind == 3:
        return 3.0 * t * t - 2.0 * t ** 3
    return t


def shares(count, kind):
    """Twist share of chain bones 0 .. count-1 (bone 0 = the root joint, which gets the Roll instead)."""
    inner = count - 1
    out = [0.0]
    for k in range(1, count):
        out.append(cumulative(kind, k / inner) - cumulative(kind, (k - 1) / inner))
    return out


def chain_bones(arm, ik_bone_name, count):
    bones, b = [], arm.pose.bones.get(ik_bone_name)
    for _ in range(count):
        if b is None:
            break
        bones.append(b)
        b = b.parent
    return list(reversed(bones))


def _add_var(drv, name, handle, prop):
    v = drv.variables.new()
    v.name = name
    v.type = 'SINGLE_PROP'
    v.targets[0].id_type = 'OBJECT'
    v.targets[0].id = handle
    v.targets[0].data_path = f'["{prop}"]'


def _drive(arm, pb, handle, k, count):
    pb.rotation_mode = 'XYZ'
    path = f'pose.bones["{pb.name}"].rotation_euler'
    arm.driver_remove(path, 1)
    fc = arm.driver_add(path, 1)
    drv = fc.driver
    drv.type = 'SCRIPTED'
    if k == 0:
        _add_var(drv, "rl", handle, ROLL)
        drv.expression = f"rl*{DEG}"
    else:
        _add_var(drv, "tw", handle, TWIST)
        _add_var(drv, "tt", handle, TWIST_TYPE)
        a = [shares(count, kind)[k] for kind in range(4)]
        # simple expression (no Python auto-run): pick the Twist Type share with comparisons
        drv.expression = (f"tw*((tt<0.5)*{a[0]!r}+(tt>=0.5)*(tt<1.5)*{a[1]!r}"
                          f"+(tt>=1.5)*(tt<2.5)*{a[2]!r}+(tt>=2.5)*{a[3]!r})*{DEG}")
    for m in list(fc.modifiers):
        fc.modifiers.remove(m)
    return fc


def setup(context, arm, ik_bone, con, end_point):
    """The Maya handle for Spline IK ``con`` on ``ik_bone``: ``ikHandleN`` empty at ``end_point`` (world) + drivers."""
    from . import units
    handle = bpy.data.objects.new(con.name, None)
    context.view_layer.active_layer_collection.collection.objects.link(handle)
    if handle.name != con.name:
        con.name = handle.name
    handle.empty_display_type = 'PLAIN_AXES'
    handle.empty_display_size = units.maya_unit(context.scene)
    handle.location = end_point
    handle[TWIST] = 0.0
    handle[ROLL] = 0.0
    handle[TWIST_TYPE] = 0
    ui = handle.id_properties_ui(TWIST_TYPE)
    ui.update(min=0, max=3, description="Maya Twist Type: 0 Linear, 1 Ease In, 2 Ease Out, 3 Ease In Out")
    handle[HANDLE] = [arm.name, ik_bone.name, con.name]
    for k, pb in enumerate(chain_bones(arm, ik_bone.name, con.chain_count)):
        _drive(arm, pb, handle, k, con.chain_count)
    return handle


def handle_of(ob):
    """(armature, IK bone name, constraint) of a kit Spline IK handle, or None."""
    rec = ob.get(HANDLE) if ob is not None else None
    if rec is None or len(rec) != 3:
        return None
    arm = bpy.data.objects.get(rec[0])
    pb = arm.pose.bones.get(rec[1]) if arm is not None and arm.pose is not None else None
    con = pb.constraints.get(rec[2]) if pb is not None else None
    return (arm, rec[1], con) if con is not None else None


def release(objects):
    """Before kit Delete removes ``objects``: a Spline IK handle takes its drivers and constraint with it."""
    for ob in objects:
        found = handle_of(ob)
        if found is None:
            continue
        arm, bone, con = found
        for pb in chain_bones(arm, bone, con.chain_count):
            arm.driver_remove(f'pose.bones["{pb.name}"].rotation_euler', 1)
        arm.pose.bones[bone].constraints.remove(con)
