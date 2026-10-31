# SPDX-License-Identifier: GPL-3.0-or-later
"""Quaternion / axis-angle rotations shown as Rotate X / Y / Z (Issue #131).

A received rig keeps its rotation mode (Rigify / FBX bones are
QUATERNION) — the Channel Box *shows* Euler and *writes* the quaternion back. Maya's rotation channels are always
Rotate X / Y / Z. Shown values are converted compatible with the last value
shown for that node (``Quaternion.to_euler(order, compat)``): a typed 270 comes back as 270, not -90 (2000 random
inputs within 0.002 deg). The last shown Euler is kit state, never written to the file.

``euler_curve`` is the same compat chain over a sequence of quaternions — the rule the rig FBX export
uses to rebuild rotation curves.
"""

from mathutils import Euler, Quaternion

EULER_MODES = frozenset({'XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'})
SHOWN_ORDER = 'XYZ'          # rotate order xyz by default, like Maya

_shown = {}                  # node key -> last Euler shown / typed (radians)


def is_euler(node):
    return node.rotation_mode in EULER_MODES


def _key(node):
    owner = node.id_data
    return (owner.as_pointer(), getattr(node, "name", "")) if node is not owner else (owner.as_pointer(), "")


def quaternion_of(node):
    """The node's rotation as a quaternion (QUATERNION or AXIS_ANGLE nodes)."""
    if node.rotation_mode == 'QUATERNION':
        return Quaternion(node.rotation_quaternion)
    angle, *axis = node.rotation_axis_angle
    return Quaternion(axis, angle) if any(axis) else Quaternion()


def write_quaternion(node, q):
    if node.rotation_mode == 'QUATERNION':
        cur = Quaternion(node.rotation_quaternion)
        if cur.dot(q) < 0.0:          # keep the stored sign continuous (no flip in the F-curves)
            q = -q
        node.rotation_quaternion = q
    else:
        axis, angle = q.to_axis_angle()
        node.rotation_axis_angle = (angle, *axis)


def _same(a, b, eps=2e-6):
    """Same rotation (q and -q too); compares components: an angle from acos is noise near 1 in float32."""
    return (max(abs(x - y) for x, y in zip(a, b)) < eps) or (max(abs(x + y) for x, y in zip(a, b)) < eps)


def euler_from(q, compat=None, order=SHOWN_ORDER):
    """Euler of quaternion ``q`` closest to ``compat`` (Maya-style continuous angles)."""
    return q.to_euler(order, compat) if compat is not None else q.to_euler(order)


def shown_euler(node):
    """Rotate X / Y / Z the Channel Box shows for a non-Euler node (radians)."""
    q = quaternion_of(node)
    prev = _shown.get(_key(node))
    if prev is not None and _same(prev.to_quaternion(), q):
        return prev.copy()                       # the user's own numbers stay exactly as typed
    e = euler_from(q, prev)
    _shown[_key(node)] = e.copy()
    return e


def set_component(node, index, value):
    """Type ``value`` (radians) into Rotate X / Y / Z of a non-Euler node; writes the quaternion."""
    e = shown_euler(node)
    e[index] = value
    write_quaternion(node, Euler(e, SHOWN_ORDER).to_quaternion())
    _shown[_key(node)] = Euler(e, SHOWN_ORDER)


def curve_path(node):
    return "rotation_quaternion" if node.rotation_mode == 'QUATERNION' else "rotation_axis_angle"


def euler_curve(quats, order=SHOWN_ORDER, start=None):
    """Continuous Euler angles for a sequence of quaternions (each compat with the one before)."""
    out, prev = [], start
    for q in quats:
        prev = euler_from(Quaternion(q), prev, order)
        out.append(prev.copy())
    return out


def forget():
    _shown.clear()
