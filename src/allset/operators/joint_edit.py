# SPDX-License-Identifier: GPL-3.0-or-later
"""Moving a joint keeps every Maya frame (Issue #160).

Maya 2026: W on a joint changes only its
translate, its subtree follows, and **no jointOrient changes** — the parent's X stops aiming at the moved child.
Preserve Children (``cmds.move(preserveChildPosition=True)``) keeps the children's world positions instead. A Blender
bone always points at its tail, so moving a connected child re-aims the parent bone; the joint's Maya frame is then
written back into ``joints.MAYA_FRAME`` (the bone-relative frame the FBX writer already reads).

``process`` runs from tool_keys' 0.25 s watch in Edit Armature mode: while no transform runs it snapshots every bone's
(head, tail, roll, MAYA_FRAME, Maya frame); a bone whose head or tail afterwards moved with the same MAYA_FRAME (= it
was only moved: W, the Channel Box Translate, redo of such a move) gets its old Maya frame back. Orient (roll only, no
head / tail change) and kit commands that write MAYA_FRAME are left alone; the Joint Tool modal drops the snapshot.
"""

import bpy
from mathutils import Matrix, Quaternion

from . import joints

TRANSLATE_OPS = frozenset({"TRANSFORM_OT_translate"})
SKIP_MODALS = ("TRANSFORM_OT_", "ALLSET_OT_joint_tool", "ALLSET_OT_insert_joint_tool")
EPS = 1e-6

_snap = {"ob": None, "bones": {}, "op": None}


def preserve_children(context=None):
    """Maya Preserve Children (Move tool, off by default) = Blender's own "Preserve Children" tool setting
    (``use_transform_skip_children``, Tool Settings > Move Settings, carried across files by ui/scene_carry): one
    setting for objects and joints, as in Maya. Blender only reads it for objects; for joints the kit selects the
    picked joints head-only (joint_selection.reshape)."""
    scene = getattr(context or bpy.context, "scene", None)
    return scene is not None and scene.tool_settings.use_transform_skip_children


def _q(eb):
    q = eb.get(joints.MAYA_FRAME)
    return tuple(q) if q is not None and len(q) == 4 else None


def snapshot(ob):
    """{bone: (head, tail, roll, MAYA_FRAME, Maya frame in armature space)} of an armature in edit mode."""
    return {eb.name: (eb.head.copy(), eb.tail.copy(), eb.roll, _q(eb), local_frame(eb)) for eb in ob.data.edit_bones}


def local_frame(eb):
    """The joint's Maya frame in armature space (columns = Maya X, Y, Z): bone frame @ JOINT_AXES @ MAYA_FRAME."""
    f = eb.matrix.to_3x3().normalized() @ joints.JOINT_AXES
    q = _q(eb)
    return f @ Quaternion(q).to_matrix() if q is not None else f


# A Maya frame is stored with a joint only when its bone is off by more than this (a bone carries ~1e-7 float32
# noise; storing that would mark every joint "turned" for FBX / Mirror)
FRAME_TOL = 1e-6


def quat_between(base, frame):
    """[w, x, y, z] of base^T @ frame in float64 (mathutils' float32 quaternion is ~1e-6 off near identity)."""
    import numpy as np
    b = np.array([[base[r][c] for c in range(3)] for r in range(3)], dtype=np.float64)
    f = np.array([[frame[r][c] for c in range(3)] for r in range(3)], dtype=np.float64)
    u, _s, vt = np.linalg.svd(b)
    b = u @ vt                                          # orthonormalise the float32 bone frame
    m = b.T @ f
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0:
        k = 2.0 * np.sqrt(1.0 + t)
        q = [0.25 * k, (m[2, 1] - m[1, 2]) / k, (m[0, 2] - m[2, 0]) / k, (m[1, 0] - m[0, 1]) / k]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        k = 2.0 * np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
        q = [(m[2, 1] - m[1, 2]) / k, 0.25 * k, (m[0, 1] + m[1, 0]) / k, (m[0, 2] + m[2, 0]) / k]
    elif m[1, 1] > m[2, 2]:
        k = 2.0 * np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
        q = [(m[0, 2] - m[2, 0]) / k, (m[0, 1] + m[1, 0]) / k, 0.25 * k, (m[1, 2] + m[2, 1]) / k]
    else:
        k = 2.0 * np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
        q = [(m[1, 0] - m[0, 1]) / k, (m[0, 2] + m[2, 0]) / k, (m[1, 2] + m[2, 1]) / k, 0.25 * k]
    n = float(np.sqrt(sum(c * c for c in q)))
    return [float(c) / n for c in q]


def _set_local_frame(eb, frame):
    base = eb.matrix.to_3x3().normalized() @ joints.JOINT_AXES
    q = quat_between(base, frame)
    # judged by the axes, not q.angle: a float32 quaternion's angle reads 0 below ~1e-6 (a bone near -Y
    # left 2.8e-6 unstored)
    if _frame_error(base, frame) < FRAME_TOL:
        if joints.MAYA_FRAME in eb:
            del eb[joints.MAYA_FRAME]
    else:
        eb[joints.MAYA_FRAME] = q


def _frame_error(a, b):
    return max((a.col[i] - b.col[i]).length for i in range(3))


def keep_frames(ob, before, names=None):
    """Write back the Maya frames of ``before`` (snapshot) for ``names`` (default all) whose frame turned; the names
    rewritten."""
    out = []
    for eb in ob.data.edit_bones:
        if (names is not None and eb.name not in names) or eb.name not in before:
            continue
        frame = before[eb.name][4]
        if _frame_error(local_frame(eb), frame) > EPS:
            _set_local_frame(eb, frame)
            out.append(eb.name)
    return out


def only_moved(ob, before):
    """Bones whose head or tail moved while their MAYA_FRAME stayed (a translate, not an orient)."""
    out = set()
    for eb in ob.data.edit_bones:
        old = before.get(eb.name)
        if old is None:
            continue
        head, tail, _roll, q, _f = old
        # the roll is not a sign of an orient here: Blender's edit-bone transform re-rolls the selected bones it
        # re-aims (Preserve Children moves a head only). Orient Joint changes the roll but no head / tail.
        if _q(eb) != q:
            continue
        if (eb.head - head).length > EPS or (eb.tail - tail).length > EPS:
            out.add(eb.name)
    return out


def _op_key(wm):
    ops = wm.operators
    if not len(ops):
        return None
    return (ops[-1].as_pointer(), len(ops), ops[-1].bl_idname)


def _edit_armature(context):
    ob = getattr(context, "active_object", None)
    if ob is None or ob.type != 'ARMATURE' or ob.mode != 'EDIT':
        return None
    return ob


def process(context):
    """tool_keys watch: restore the Maya frames a translate turned; then re-snapshot. Returns the bones rewritten."""
    wm = context.window_manager
    ob = _edit_armature(context)
    if ob is None:
        _snap.update(ob=None, bones={})
        return []
    running = [op.bl_idname for w in wm.windows for op in w.modal_operators]
    if any(i.startswith("TRANSFORM_OT_") for i in running):
        return []                                   # a move is running: keep the snapshot from before it
    if any(i.startswith(SKIP_MODALS[1:]) for i in running):
        _snap.update(ob=None, bones={})             # the Joint Tool lays bones out itself
        return []
    pcp = preserve_children(context)
    if _snap.get("pcp") is not None and pcp != _snap["pcp"]:
        from . import joint_selection
        joint_selection.reshape(context, ob, pcp)   # the Tool Settings check box changed: re-shape the pick
    _snap["pcp"] = pcp
    key = _op_key(wm)
    out = []
    if _snap["ob"] == ob.name and _snap["bones"]:
        new_op = key != _snap["op"]
        if not new_op or (key is not None and key[2] in TRANSLATE_OPS):
            moved = only_moved(ob, _snap["bones"])
            if moved:
                out = keep_frames(ob, _snap["bones"], moved)
                if out:
                    from ..ui import maya_dock
                    maya_dock.redraw()                  # the Channel Box Translate is read from the kept frame
    _snap.update(ob=ob.name, bones=snapshot(ob), op=key)
    return out


TICK = 0.05
_timer = {"on": False}


def _tick():
    try:
        context = bpy.context
        if context.mode != 'EDIT_ARMATURE':
            _snap.update(ob=None, bones={})
            _timer["on"] = False
            return None
        process(context)
    except (AttributeError, RuntimeError, ReferenceError):
        pass
    return TICK


def watch():
    """Keep watching while Edit Armature mode lasts (tool_keys' watch starts it; a fast tick so a move followed at once
    by F8 / E is still caught before the mode changes)."""
    if not _timer["on"]:
        _timer["on"] = True
        bpy.app.timers.register(_tick, first_interval=TICK)


def rebase(context=None):
    """Forget the snapshot (call after a kit edit that sets frames on purpose)."""
    _snap.update(ob=None, bones={})


# --- Channel Box Translate (Edit mode) -------------------------------------------------------------------------

def joint_translate(eb):
    """Maya translate of a joint in rest (Blender length, armature space): the head in the parent's Maya frame. A top
    joint's translate is its position, in the kit's Z-up axes like every object Translate (the
    same numbers as the Pose-mode Channel Box, ``channel_box.root_translate``)."""
    if eb.parent is None:
        return eb.head.copy()
    return local_frame(eb.parent).transposed() @ (eb.head - eb.parent.head)


def _move_head(eb, head):
    if eb.use_connect and eb.parent is not None:
        eb.parent.tail = head
    eb.head = head


def set_joint_translate(ob, eb, t, preserve=False):
    """Move joint ``eb`` so its Maya translate is ``t`` (Blender length): its subtree follows (``preserve`` = Maya
    Preserve Children: only the joint); every Maya frame stays."""
    from mathutils import Vector
    t = Vector(t)
    base = Matrix.Identity(3) if eb.parent is None else local_frame(eb.parent)
    origin = Vector((0.0, 0.0, 0.0)) if eb.parent is None else eb.parent.head
    head = origin + base @ t
    delta = head - eb.head
    if delta.length < 1e-9:
        return False
    before = snapshot(ob)
    if preserve:
        _move_head(eb, head)
    else:
        # targets first: setting a bone's tail also moves its connected children's heads (RNA)
        moves = [(b, b.head + delta, b.tail + delta) for b in (eb, *eb.children_recursive)]
        for b, h, t in moves:
            b.head, b.tail = h, t
        if eb.use_connect and eb.parent is not None:
            eb.parent.tail = eb.head
    keep_frames(ob, before)
    rebase()
    return True


def lead_joint(context=None):
    ob = _edit_armature(context or bpy.context)
    if ob is None:
        return None, None
    eb = ob.data.edit_bones.active
    return (ob, eb) if eb is not None else (ob, None)


def _translate_get(axis):
    def get(self):
        from ..ui import cb_entry
        ob, eb = lead_joint()
        if eb is None:
            return ""
        return cb_entry.format_value(joint_translate(eb)[axis], "LENGTH", self)
    return get


def _translate_set(axis):
    def set_(self, text):
        from ..ui import cb_entry
        ob, eb = lead_joint()
        if eb is None:
            return
        t = joint_translate(eb)
        try:
            t[axis] = cb_entry.parse_entry(text, t[axis], "LENGTH", self)
        except (ValueError, TypeError):
            return
        set_joint_translate(ob, eb, t, preserve_children())
    return set_


AXES = "xyz"


def _ssc_get(self):
    return self.inherit_scale == 'NONE'


def _ssc_set(self, value):
    # Maya segmentScaleCompensate on = Blender inherit_scale NONE, off = FULL (Blender 4.5,
    # ALIGNED is not Maya)
    self.inherit_scale = 'NONE' if value else 'FULL'


def register():
    bpy.types.Bone.allset_ssc = bpy.props.BoolProperty(
        name="Segment Scale Compensate", get=_ssc_get, set=_ssc_set,
        description="Maya: the child joint isn't scaled by its parent joint's scale")
    for i, a in enumerate(AXES):
        setattr(bpy.types.Scene, f"allset_joint_t{a}",
                bpy.props.StringProperty(name=f"Translate {a.upper()}", get=_translate_get(i), set=_translate_set(i),
                                         options={'SKIP_SAVE'}))


def unregister():
    if hasattr(bpy.types.Bone, "allset_ssc"):
        del bpy.types.Bone.allset_ssc
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _timer["on"] = False
    for a in AXES:
        if hasattr(bpy.types.Scene, f"allset_joint_t{a}"):
            delattr(bpy.types.Scene, f"allset_joint_t{a}")
    _snap.update(ob=None, bones={}, op=None, pcp=None)
