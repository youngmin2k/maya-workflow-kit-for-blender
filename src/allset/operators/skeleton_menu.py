# SPDX-License-Identifier: GPL-3.0-or-later
"""Skeleton menu commands with Maya's meaning (Issue #163).

Maya:

- Insert Joint: a new joint at the clicked joint (translate / jointOrient / rotate 0 = the joint's own frame), under
  it, on top of all its children (their world kept); the tool then drags it. Works on an end joint too.
- Remove Joint: the children go under the joint's parent with their world kept (jointOrient absorbs the frame); the
  joint's skin influence is dropped and the other weights are left as they are (not renormalised).
- Disconnect Joint: the joint becomes a root (world kept), a new end joint stays at its old place under the old
  parent with the joint's world frame.
- Connect Joint: the first joint must be a root ("The child joint must be a root joint."). Connect mode (factory)
  moves that skeleton (pure translation, world frames kept) so its root sits on the second joint and parents it to
  the second joint's parent; parent mode parents it under the second joint keeping its world.

A kit joint is a bone (head = the joint) whose Maya frame is its bone frame turned by ``joints.MAYA_FRAME``: every
command keeps the Maya frames of the joints it touches and stores what the bones can't take.
"""

import json

import bpy
from bpy.props import EnumProperty, BoolProperty, StringProperty
from bpy_extras import view3d_utils
from mathutils import Vector

from .. import results
from . import joints
from .joint_edit import FRAME_TOL, local_frame, quat_between

EPS = 1e-6


def _store(eb, frame):
    """Keep Maya frame ``frame`` (armature space, columns Maya X, Y, Z) on edit bone ``eb``."""
    base = eb.matrix.to_3x3().normalized() @ joints.JOINT_AXES
    if max((base.col[i] - frame.col[i]).length for i in range(3)) < FRAME_TOL:
        if joints.MAYA_FRAME in eb:
            del eb[joints.MAYA_FRAME]
    else:
        eb[joints.MAYA_FRAME] = quat_between(base, frame)


def _aim(eb, tail, frame):
    """Point ``eb`` at ``tail`` (rolled so its Z is near Maya Y) and keep Maya ``frame``."""
    if (tail - eb.head).length > EPS:
        eb.tail = tail
    eb.align_roll(frame.col[1])
    _store(eb, frame)


def _end_tail(eb_head, frame, length):
    return eb_head + frame.col[0].normalized() * max(length, 1e-3)


def _new_joint(ob, ebs, like):
    eb = ebs.new(joints.next_joint_name(extra={e.name for e in ebs}))
    eb.inherit_scale = like.inherit_scale
    joints.stamp_last(eb)
    return eb


def _reparent(eb, parent):
    """Re-hang ``eb`` under ``parent`` keeping where it is (connected only when its head sits on the tail); it becomes
    the newest child (Maya child order)."""
    eb.use_connect = False
    eb.parent = parent
    joints.stamp_last(eb)
    if parent is not None and (parent.tail - eb.head).length < EPS:
        eb.use_connect = True


def _done(ob, frames):
    """After the edit: Blender re-derives bone matrices in float32 on leaving edit mode — store against ``frames``."""
    joints.fix_frames(ob, frames)


# --- Insert Joint -----------------------------------------------------------------------------------

def insert_joint(ob, name):
    """Edit mode: a new joint at joint ``name`` with its Maya frame, between it and all its children; returns the new
    joint's name and {name: Maya frame} of the joints to keep."""
    ebs = ob.data.edit_bones
    j = ebs[name]
    fj = local_frame(j)
    kids = list(j.children)
    n = _new_joint(ob, ebs, j)
    n.head = j.head.copy()
    first = next((k for k in kids if (k.head - j.head).length > EPS), None)
    n.tail = first.head.copy() if first is not None else _end_tail(j.head, fj, j.length * 0.5)
    n.parent = j
    n.use_connect = False
    for k in kids:
        _reparent(k, n)
    _aim(n, n.tail, fj)
    _store(j, fj)
    return n.name, {j.name: fj, n.name: fj}


def place_inserted(ob, name, point, frames):
    """Edit mode: move the inserted joint ``name`` to armature-space ``point`` (Insert Joint Tool drag): its children
    stay, its parent's tail follows; Maya frames of both from ``frames``."""
    ebs = ob.data.edit_bones
    n = ebs[name]
    j = n.parent
    fn = frames[name]
    p = Vector(point)
    kids = list(n.children)
    for k in kids:
        k.use_connect = False
    n.use_connect = False
    old = n.tail - n.head
    n.head = p
    first = next((k for k in kids if (k.head - p).length > EPS), None)
    n.tail = first.head.copy() if first is not None else p + (old if old.length > EPS else fn.col[0])
    _aim(n, n.tail, fn)
    for k in kids:
        _reparent(k, n)
    if j is not None:
        if (p - j.head).length > EPS:
            j.tail = p
            n.use_connect = True
        _aim(j, j.tail, frames[j.name])


# --- Remove Joint -----------------------------------------------------------------------------------

def _skinned_meshes(ob):
    return [o for o in bpy.data.objects if o.type == 'MESH'
            and any(m.type == 'ARMATURE' and m.object == ob for m in o.modifiers)]


def remove_joints(ob, names):
    """Edit mode: remove the joints; children re-hung to the parent with their world kept. Returns ({name: frame}
    to keep, removed names). Vertex groups are removed by ``drop_influences`` (object data, any mode)."""
    ebs = ob.data.edit_bones
    frames, removed = {}, []
    for name in names:
        j = ebs.get(name)
        if j is None:
            continue
        parent = j.parent
        kids = list(j.children)
        for k in kids:
            frames[k.name] = local_frame(k)
        aimed = parent is not None and (parent.tail - j.head).length < EPS
        if parent is not None:
            frames.setdefault(parent.name, local_frame(parent))
        for k in kids:
            k.use_connect = False
            k.parent = parent
            joints.stamp_last(k)
        if aimed:
            first = next((k for k in kids if (k.head - parent.head).length > EPS), None)
            if first is not None:
                _aim(parent, first.head.copy(), frames[parent.name])
                for k in kids:
                    _reparent(k, parent)
        frames.pop(name, None)
        ebs.remove(j)
        removed.append(name)
    for name, f in frames.items():
        eb = ebs.get(name)
        if eb is not None:
            _store(eb, f)
    return frames, removed


def drop_influences(ob, names):
    """Maya removes the joint's influence and leaves the other weights alone."""
    n = 0
    for mesh in _skinned_meshes(ob):
        for name in names:
            vg = mesh.vertex_groups.get(name)
            if vg is not None:
                mesh.vertex_groups.remove(vg)
                n += 1
    from .skin_basics import drop_bind_pose_members      # ... and the bindPose member
    drop_bind_pose_members(ob, names)
    return n


# --- Disconnect Joint -------------------------------------------------------------------------------

def disconnect_joint(ob, name):
    """Edit mode: joint ``name`` becomes a root (world kept), a new end joint takes its old place under the old parent.
    Returns (new end joint name or None for a root, {name: frame})."""
    ebs = ob.data.edit_bones
    j = ebs[name]
    parent = j.parent
    if parent is None:
        return None, {}
    fj = local_frame(j)
    e = _new_joint(ob, ebs, j)
    e.head = j.head.copy()
    seg = j.head - parent.head
    e.tail = j.head + seg * 0.5 if seg.length > EPS else _end_tail(j.head, fj, j.length * 0.5)
    connected = j.use_connect
    j.use_connect = False
    j.parent = None
    e.parent = parent
    e.use_connect = connected
    joints.stamp_last(j)          # a new root: last among the roots (Maya: a new world node)
    _aim(e, e.tail, fj)
    _store(j, fj)
    return e.name, {j.name: fj, e.name: fj}


# --- Connect Joint ----------------------------------------------------------------------------------

ROOT_ERROR = "The child joint must be a root joint."


def connect_joint(ob, src, dst, mode='CONNECT'):
    """Edit mode, one armature: connect root joint ``src`` to joint ``dst``. Returns {name: frame}."""
    ebs = ob.data.edit_bones
    s, d = ebs[src], ebs[dst]
    if s.parent is not None:
        raise RuntimeError(ROOT_ERROR)
    if s == d or d in s.children_recursive:
        raise RuntimeError(f"{dst} is below {src}")
    tree = [s, *s.children_recursive]
    frames = {b.name: local_frame(b) for b in tree}
    if mode == 'CONNECT':
        delta = d.head - s.head                          # a pure translation of the whole skeleton
        conn = {b.name: b.use_connect for b in tree}
        for b in tree:
            b.use_connect = False
        for b in tree:
            b.head += delta
            b.tail += delta
        for b in tree:
            b.use_connect = conn[b.name]
        target = d.parent
    else:
        target = d
    _reparent(s, target)
    for b in tree:
        _store(b, frames[b.name])
    return frames


def join_skeleton(context, dst_ob, src_ob):
    """Join armature ``src_ob`` into ``dst_ob`` (object mode); meshes skinned to it follow."""
    meshes = [(o, m.name) for o in bpy.data.objects if o.type == 'MESH'
              for m in o.modifiers if m.type == 'ARMATURE' and m.object == src_ob]
    for o in context.view_layer.objects:
        o.select_set(o in (dst_ob, src_ob))
    context.view_layer.objects.active = dst_ob
    bpy.ops.object.join()
    for o, mod in meshes:
        m = o.modifiers.get(mod)
        if m is not None:
            m.object = dst_ob


# --- operators --------------------------------------------------------------------------------------

def _armature(context):
    return joints._armature(context)


class _InMode:
    """Edit mode around a block, then back to ``mode`` (and Maya frames fixed after leaving edit mode)."""

    def __init__(self, ob):
        self.ob, self.mode, self.frames = ob, ob.mode, {}

    def __enter__(self):
        if self.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        return self

    def __exit__(self, *exc):
        if self.mode != 'EDIT':
            bpy.ops.object.mode_set(mode=self.mode)
            _done(self.ob, self.frames)


def picked(ob):
    """The joints the user picked (Maya selection): in Edit mode a picked joint selects its whole subtree (or only its
    head with Preserve Children, joint_selection), so only the picked tops count."""
    if ob.mode != 'EDIT':
        return joints.selected_joint_names(ob)
    from .joint_selection import _edit_picked
    return [eb.name for eb in _edit_picked(ob)]


def _select_only(ob, names):
    if ob.mode == 'EDIT':
        from .joint_edit import preserve_children
        from .joint_selection import _pick_shape, _set_edit
        for eb in ob.data.edit_bones:
            _set_edit(eb, False)
        for name in names:
            if name in ob.data.edit_bones:
                _pick_shape(ob.data.edit_bones[name], True, preserve_children())
        if names:
            ob.data.edit_bones.active = ob.data.edit_bones.get(names[-1])
        return
    cb = joints._cb()
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name in names)
    if names and names[-1] in ob.data.bones:
        ob.data.bones.active = ob.data.bones[names[-1]]


class ALLSET_OT_remove_joint(bpy.types.Operator):
    """Maya Remove Joint: delete the selected joints; their children move up to the parent and stay where they are"""
    bl_idname = "allset.remove_joint"
    bl_label = "Remove Joint"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return _armature(context) is not None

    def execute(self, context):
        ob = _armature(context)
        names = picked(ob)
        if not names:
            self.report({'WARNING'}, "Select the joints to remove")
            return {'CANCELLED'}
        with _InMode(ob) as m:
            frames, removed = remove_joints(ob, names)
            m.frames = frames
        drop_influences(ob, removed)
        results.result(self, f"Removed {len(removed)} joint(s)")
        return {'FINISHED'}


class ALLSET_OT_disconnect_joint(bpy.types.Operator):
    """Maya Disconnect Joint: the selected joint becomes the root of its own skeleton, a new end joint stays behind"""
    bl_idname = "allset.disconnect_joint"
    bl_label = "Disconnect Joint"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return _armature(context) is not None

    def execute(self, context):
        ob = _armature(context)
        names = picked(ob)
        if not names:
            self.report({'WARNING'}, "Select the joint to disconnect")
            return {'CANCELLED'}
        made, done = [], []
        with _InMode(ob) as m:
            for name in names:
                end, frames = disconnect_joint(ob, name)
                if end is not None:
                    made.append(end)
                    done.append(name)
                    m.frames.update(frames)
        if not done:
            self.report({'WARNING'}, "The joint is already a root joint")
            return {'CANCELLED'}
        _select_only(ob, done)
        results.result(self, f"Disconnected {', '.join(done)}")
        return {'FINISHED'}


CONNECT_MODES = (("CONNECT", "Connect joint", "Move the first skeleton's root onto the second joint and parent it to "
                  "that joint's parent"),
                 ("PARENT", "Parent joint", "Parent the first skeleton's root under the second joint where it is"))


class ALLSET_OT_connect_joint(bpy.types.Operator):
    """Maya Connect Joint: select a root joint, then the joint to connect it to"""
    bl_idname = "allset.connect_joint"
    bl_label = "Connect Joint Options"
    bl_options = {'UNDO'}

    mode: EnumProperty(name="Mode", items=CONNECT_MODES, default="CONNECT")
    option_box: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return _armature(context) is not None

    def invoke(self, context, event):
        if self.option_box:
            return context.window_manager.invoke_props_dialog(self, width=320, confirm_text="Connect")
        joints._load_options(self, "connect_joint", ("mode",))
        return self.execute(context)

    def draw(self, context):
        self.layout.prop(self, "mode", expand=True)

    def _pick(self, context):
        """(source armature, source root, target armature, target joint) from the selection (target = active)."""
        dst_ob = _armature(context)
        dst = joints.active_joint_name(dst_ob)
        objs = [o for o in getattr(context, "objects_in_mode", [dst_ob]) if o.type == 'ARMATURE'] or [dst_ob]
        if dst_ob not in objs:
            objs.insert(0, dst_ob)
        src = [(o, n) for o in objs for n in picked(o) if not (o == dst_ob and n == dst)]
        return dst_ob, dst, src

    def execute(self, context):
        dst_ob, dst, src = self._pick(context)
        if dst is None or len(src) != 1:
            self.report({'WARNING'}, "Select a root joint, then the joint to connect it to")
            return {'CANCELLED'}
        src_ob, name = src[0]
        bone = src_ob.data.edit_bones.get(name) if src_ob.mode == 'EDIT' else src_ob.data.bones.get(name)
        if bone is None or bone.parent is not None:
            self.report({'ERROR'}, ROOT_ERROR)
            return {'CANCELLED'}
        mode = dst_ob.mode
        if src_ob != dst_ob:
            bpy.ops.object.mode_set(mode='OBJECT')
            join_skeleton(context, dst_ob, src_ob)
            bpy.ops.object.mode_set(mode=mode)
        with _InMode(dst_ob) as m:
            try:
                m.frames = connect_joint(dst_ob, name, dst, self.mode)
            except RuntimeError as ex:
                self.report({'ERROR'}, str(ex))
                return {'CANCELLED'}
        joints._save_options(self, "connect_joint", ("mode",))
        results.result(self, f"Connected {name} to {dst}")
        return {'FINISHED'}


DRAG_PX = 3
INSERT_STATUS = "Insert Joint Tool: click a joint and drag to place the new joint — Enter / Q to finish"


class ALLSET_OT_insert_joint_tool(bpy.types.Operator):
    """Maya Insert Joint Tool: click a joint and drag to place a new joint between it and its children"""
    bl_idname = "allset.insert_joint_tool"
    bl_label = "Insert Joint Tool"
    bl_options = {'UNDO'}

    joint: StringProperty(options={'SKIP_SAVE', 'HIDDEN'}, description="Insert under this joint without clicks")
    point: StringProperty(options={'SKIP_SAVE', 'HIDDEN'}, description="JSON world point of the new joint")

    def execute(self, context):
        """Scripts: insert under ``joint`` of the active skeleton, optionally moved to ``point``."""
        ob = context.active_object
        if ob is None or ob.type != 'ARMATURE' or self.joint not in ob.data.bones:
            self.report({'WARNING'}, "Insert Joint: click a joint")
            return {'CANCELLED'}
        with _InMode(ob) as m:
            name, m.frames = insert_joint(ob, self.joint)
            if self.point:
                p = ob.matrix_world.inverted() @ Vector(json.loads(self.point))
                place_inserted(ob, name, p, m.frames)
        _select_only(ob, [name])
        results.result(self, f"Inserted {name}")
        return {'FINISHED'}

    def invoke(self, context, event):
        if context.window is None:
            return {'CANCELLED'}
        self._drag = None            # (armature, new joint, frames, area, region, depth point)
        self._press_at = None
        self._made = []
        self._modes = {}             # armature name -> mode before the tool put it in edit mode
        self._frames = {}
        context.workspace.status_text_set(INSERT_STATUS)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _press(self, context, event):
        hit = joints.view_under(context.window, event.mouse_x, event.mouse_y)
        if hit is None:
            return False
        area, region = hit
        coord = (event.mouse_x - region.x, event.mouse_y - region.y)
        arms = [o for o in context.view_layer.objects if o.type == 'ARMATURE' and o.visible_get()]
        scale = context.preferences.system.ui_scale or 1.0
        picked = joints.pick_branch_joint(region, region.data, arms, coord, joints.BRANCH_MIN_PX * scale)
        if picked is None:
            return False
        ob, name = picked
        with context.temp_override(window=context.window, area=area, region=region):
            if context.active_object is not ob:
                if context.mode != 'OBJECT' and context.active_object is not None:
                    bpy.ops.object.mode_set(mode='OBJECT')
                for o in context.selected_objects:
                    o.select_set(False)
                ob.select_set(True)
                context.view_layer.objects.active = ob
            if ob.mode != 'EDIT':
                self._modes.setdefault(ob.name, ob.mode)
                bpy.ops.object.mode_set(mode='EDIT')
        new, frames = insert_joint(ob, name)
        self._frames.setdefault(ob.name, {}).update(frames)
        self._press_at = (event.mouse_x, event.mouse_y)
        head = ob.matrix_world @ ob.data.edit_bones[new].head
        self._drag = (ob, new, frames, area, region, head)
        self._made.append(new)
        area.tag_redraw()
        return True

    def _move(self, event):
        # a click without a drag leaves the new joint on the clicked one (Maya); 3 px = Blender's drag threshold
        if self._press_at is not None:
            if max(abs(event.mouse_x - self._press_at[0]), abs(event.mouse_y - self._press_at[1])) < DRAG_PX:
                return
            self._press_at = None
        ob, new, frames, area, region, depth = self._drag
        coord = (event.mouse_x - region.x, event.mouse_y - region.y)
        p = view3d_utils.region_2d_to_location_3d(region, region.data, coord, depth)
        place_inserted(ob, new, ob.matrix_world.inverted() @ p, frames)
        area.tag_redraw()

    def _finish(self, context):
        context.workspace.status_text_set(None)
        if not self._made:
            return {'CANCELLED'}
        ob = context.active_object
        if ob is not None and ob.type == 'ARMATURE':
            names = [n for n in self._made if n in ob.data.edit_bones]
            mode = self._modes.get(ob.name)
            if mode not in (None, 'EDIT', 'OBJECT') and ob.mode == 'EDIT':
                hit = joints.ALLSET_OT_joint_tool._any_view(context)
                override = dict(window=context.window, area=hit[0], region=hit[1]) if hit else {}
                with context.temp_override(**override):
                    bpy.ops.object.mode_set(mode=mode)
                _done(ob, self._frames.get(ob.name, {}))
            _select_only(ob, names[-1:])
        results.result(self, f"Inserted {', '.join(self._made)}")
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type in {'RET', 'NUMPAD_ENTER', 'ESC', 'Q'} and event.value == 'PRESS' and self._drag is None:
            return self._finish(context)
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS' and not (event.alt or event.ctrl or event.shift or event.oskey):
                if self._press(context, event):
                    return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE' and self._drag is not None:
                self._move(event)
                self._drag = None
                return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE' and self._drag is not None:
            self._move(event)
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


classes = (ALLSET_OT_insert_joint_tool, ALLSET_OT_remove_joint, ALLSET_OT_disconnect_joint, ALLSET_OT_connect_joint)
