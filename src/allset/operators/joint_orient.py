# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya 2026 Skeleton > Orient Joint (Issue #161): ``cmds.joint(edit=True, oj=..., sao=..., aos=...)`` frames
from joint positions.

Rules (Maya 2026 behaviour, error 0):
- ``oj`` "none" (Orient to World): every frame = the world axes.
- with ``sao``: aim a = toward the first child (a zero-length child: the joint is left as it is); the
  reference w = the world-up axis, or with ``aos`` the bend normal n = (P − P_parent) × (P_child − P) (top joint:
  (P1 − P0) × (P2 − P0)), turned only when n · up < 0 (n · up = 0 keeps n: Maya leaves that tie to rounding); the
  secondary axis = w made perpendicular to a; w ∥ a = the minimal arc from the parent frame. No anti-flip rule.
- without ``sao`` (traditional): c = a × (toward the parent; a top joint: toward the world origin); c = 0 -> the axis of
  a's smallest component in the parent frame (ties: the later axis), made perpendicular to a; rows oj[0] = a,
  oj[2] = c, oj[1] = c × a (even order) / a × c (odd order).
- an end joint takes the parent's frame with ``sao`` + ``aos``, else the world axes; several children: the first; a
  zero-length child: jointOrient 0 (the parent's frame) with a secondary axis, unchanged without.

Everything is in one space (armature space); frames are 3x3 matrices whose columns are the Maya X, Y, Z axes. The Maya
-> Blender axis map is a proper rotation, so the cross-product rules hold unchanged. No bpy here (tests import it).
"""

import math

import numpy as np
from mathutils import Matrix

AXIS = {"x": 0, "y": 1, "z": 2}
EVEN = frozenset({"xyz", "yzx", "zxy"})
ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
SAO = {"xup": (0, 1.0), "xdown": (0, -1.0), "yup": (1, 1.0), "ydown": (1, -1.0), "zup": (2, 1.0), "zdown": (2, -1.0)}
EPS = 1e-9
# Maya flips n only when n . up < 0 (strict); its view-plane clicks are exact, so a chain drawn
# in the front / side view has n . up = 0 and keeps n. The kit's clicks carry float32 noise, so it treats |n . up|
# below this as that 0 (kit input tolerance)
TIE = 1e-6
# The maths runs in float64 (numpy): mathutils is float32, and the bend normal of a nearly straight joint lost 3e-6
# that way. Frames come back as mathutils Matrix (columns = Maya X, Y, Z).


def _v(x):
    return np.array([float(c) for c in x], dtype=np.float64)


def _m(m):
    """mathutils / nested rows -> numpy 3x3 with the same columns."""
    return np.array([[float(m[r][c]) for c in range(3)] for r in range(3)], dtype=np.float64)


def _unit(v):
    return v / np.linalg.norm(v)


def _to_matrix(a):
    return Matrix([[float(a[r][c]) for c in range(3)] for r in range(3)])


def world_up(sao, world):
    """The Maya world axis named by ``sao`` ("yup", "zdown", ...) as a vector in the frames' space (numpy)."""
    k, sign = SAO[sao]
    return _m(world)[:, k] * sign


def _frame(oj, prim, sec):
    """Columns Maya X, Y, Z from the primary (oj[0]) and secondary (oj[1]) unit axes, right-handed."""
    third = np.cross(prim, sec) if oj in EVEN else np.cross(sec, prim)
    m = np.zeros((3, 3))
    m[:, AXIS[oj[0]]], m[:, AXIS[oj[1]]], m[:, AXIS[oj[2]]] = prim, sec, third
    return m


def _traditional(oj, a, b, parent):
    c = np.cross(a, b)
    if np.linalg.norm(c) < EPS:
        mags = np.abs(parent.T @ a)
        low = mags.min()
        k = max(i for i in range(3) if mags[i] <= low + 1e-9)    # ties: the later axis
        e = parent[:, k]
        c = e - a * a.dot(e)
    c = _unit(c)
    # rows oj[0] = a, oj[2] = c, oj[1] = c x a (even) / a x c (odd)
    mid = np.cross(c, a) if oj in EVEN else np.cross(a, c)
    m = np.zeros((3, 3))
    m[:, AXIS[oj[0]]], m[:, AXIS[oj[1]]], m[:, AXIS[oj[2]]] = a, _unit(mid), c
    return m


def _arc(u, v):
    """The minimal rotation taking unit u onto unit v (3x3)."""
    axis = np.cross(u, v)
    s, c = np.linalg.norm(axis), float(u.dot(v))
    if s < 1e-12:
        if c > 0:
            return np.eye(3)
        perp = np.cross(u, np.eye(3)[int(np.argmin(np.abs(u)))])
        axis, s, c = _unit(perp), 0.0, -1.0
        k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        return np.eye(3) + 2.0 * k @ k
    axis = axis / s
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + s * k + (1.0 - c) * k @ k


def _aim(oj, a, w, parent):
    t = w - a * a.dot(w)
    if np.linalg.norm(t) > EPS:
        return _frame(oj, a, _unit(t))
    # w parallel to the aim: only the minimal arc that takes the parent frame's aim axis onto a
    return _arc(_unit(parent[:, AXIS[oj[0]]]), a) @ parent


def orient_frames(names, pos, parent_of, first_child, frames, world, oj="xyz", sao="yup", aos=True, origin=(0, 0, 0)):
    """Maya frames for ``names`` (oriented in this order — parents first).

    ``pos`` {joint: position}, ``parent_of`` {joint: parent or None}, ``first_child`` {joint: first child or None},
    ``frames`` {joint: current frame (Matrix)} (the parents' frames are read from it and the results written back
    into it), ``world`` = the Maya world axes. Returns {joint: frame (Matrix)}."""
    P = {k: _v(v) for k, v in pos.items()}
    W = _m(world)
    F = {}

    def frame_of(name):
        if name in F:
            return F[name]
        return _m(frames[name]) if name in frames else W

    out = {}
    for name in names:
        par = parent_of.get(name)
        pframe = frame_of(par) if par is not None else W
        if oj == "none":
            F[name] = W.copy()
        else:
            child = first_child.get(name)
            if child is None:
                F[name] = pframe.copy() if (sao and aos and par is not None) else W.copy()
            else:
                d = P[child] - P[name]
                if np.linalg.norm(d) < EPS:
                    # Maya: the orient fails for this joint: with a secondary axis
                    # it ends with jointOrient 0 = the parent's (new) frame; the traditional orient leaves its frame
                    if sao is None:
                        continue
                    F[name] = pframe.copy()
                else:
                    a = _unit(d)
                    if sao is None:
                        b = (P[par] - P[name]) if par is not None else (_v(origin) - P[name])
                        F[name] = _traditional(oj, a, b, pframe)
                    else:
                        up = world_up(sao, world)
                        w = up
                        if aos:
                            if par is not None:
                                n = np.cross(P[name] - P[par], d)
                            else:
                                grand = first_child.get(child)
                                n = np.cross(d, P[grand] - P[name]) if grand is not None else np.zeros(3)
                            ln = np.linalg.norm(n)
                            if ln > EPS * max(1.0, float(d.dot(d))):
                                w = -n if (n / ln).dot(up) < -TIE else n
                        F[name] = _aim(oj, a, w, pframe)
        frames[name] = out[name] = _to_matrix(F[name])
    return out


def joint_orient(parent_frame, frame):
    """Maya jointOrient (degrees, xyz) of a joint with ``frame`` under ``parent_frame`` (rotate 0)."""
    rel = parent_frame.transposed() @ frame
    return [math.degrees(v) for v in rel.to_euler('XYZ')]


def radius(length):
    """Maya Joint Tool variable bone radius (length 1 -> 0.5, length 30 -> 2, linear
    in between) for a bone ``length`` in Maya units."""
    return min(2.0, max(0.5, 0.5 + (length - 1.0) / 29.0 * 1.5))
