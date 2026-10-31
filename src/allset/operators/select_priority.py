# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya selection priority for object-mode clicks.

Maya picks the overlapping candidate of the highest type priority (``selectPrefPriorityMode
"animation"``; ikHandle 10, joint 9, nurbsCurve 4, everything else 2),
occluded or not. Blender's ``view3d.select`` picks by
depth, so a control curve or a joint in front of (or behind) a mesh can lose to the mesh.

``allset.select_priority`` sits in front of viewport click selection. Individual joint hits enter
Pose mode directly; clicks away from a skeleton release Pose/Edit mode for native object picking.
In Object mode, ordinary candidates still use Blender's native pick and cycling. With the Selection Priority
preference off, an Object-mode click is only taken when it hits a joint.
"""

import math

import bpy
import numpy as np

from .. import compat
from . import control_shapes
from .preselect import project, segment_distance

# selection priority (like Maya) for the kit's object kinds; anything else is 2.
IK_HANDLE, JOINT, CURVE, DEFAULT = 10, 9, 4, 2
RADIUS_PX = 5.0     # a click box of half-width 4: half diagonal ~5.7
BONE_WIDTH = 0.1    # octahedral bone: widest at 0.1 x length (Blender's bone shape)


# --- pure helpers (tests/test_step76_select_priority.py) -----------------------------------------------

def priority(kind):
    """Maya priority of a kit object kind: 'IK_HANDLE', 'ARMATURE', 'CURVE' or anything else."""
    return {'IK_HANDLE': IK_HANDLE, 'ARMATURE': JOINT, 'CURVE': CURVE}.get(kind, DEFAULT)


def rank(hits, radius):
    """The winning ``(name, priority, distance)`` of ``hits`` within ``radius`` that beats priority 2:
    highest priority, then nearest on screen, then name; None when nothing qualifies."""
    ok = [h for h in hits if h[2] <= radius and h[1] > DEFAULT]
    return min(ok, key=lambda h: (-h[1], h[2], h[0])) if ok else None


def bone_width(t, width):
    """Half thickness of an octahedral bone at parameter ``t`` (0 head .. 1 tail): ``width`` at 0.1,
    tapering to 0 at both ends."""
    return np.where(t < BONE_WIDTH, width * t / BONE_WIDTH, width * (1.0 - t) / (1.0 - BONE_WIDTH))


def segments_hit(mouse, a, b, front, width=None):
    """Smallest screen distance from ``mouse`` to the segments a[i]-b[i] with both ends in front of the
    view, less the bone thickness when ``width`` (per segment, at its widest) is given; inf when none."""
    if len(a) == 0:
        return float("inf")
    dist, t = segment_distance(mouse, a, b)
    if width is not None:
        dist = dist - bone_width(t, width)
    dist = np.where(front, dist, np.inf)
    return float(dist.min())


def shape_hit(mouse, xa, xb, front):
    """Screen distance from ``mouse`` to a Custom Shape's projected wire (segments xa-xb, both ends in front)."""
    return segments_hit(mouse, xa, xb, front)


def pick_joint(context, ob, mouse, radius):
    """``joint_selection.pick`` for pose / object mode with Custom Shapes: a bone that has one is hit on its drawn
    wire (projected evaluated shape segments), not on the octahedron Blender doesn't draw for it."""
    from . import joint_selection
    from ..ui import maya_joints
    if maya_joints.is_maya_view(context.space_data, getattr(getattr(context, "window", None), "workspace", None)):
        return maya_joints.pick(context, ob, mouse, radius)    # joints drawn like Maya's: a click hits the wire
    shaped = any(pb.custom_shape is not None for pb in ob.pose.bones)
    if ob.mode == 'EDIT' or not shaped or not control_shapes.shows_custom_shapes(ob):
        return joint_selection.pick(context, ob, mouse, radius)
    depsgraph = context.evaluated_depsgraph_get()
    persp = np.asarray(context.region_data.perspective_matrix, dtype=np.float64)
    region = context.region
    candidates = []
    for pb in ob.pose.bones:
        bone = pb.bone
        if (compat.bone_hidden(pb) or bone.hide_select or (bone.collections and
                not any(c.is_visible_effectively for c in bone.collections))):
            continue
        if pb.custom_shape is not None:
            a, b = control_shapes.shape_segments(ob, pb, depsgraph)
            if len(a) == 0:
                continue
            xa, fa = project(a, persp, region.width, region.height)
            xb, fb = project(b, persp, region.width, region.height)
            d = shape_hit(mouse, xa, xb, fa & fb)
            if d <= radius:
                candidates.append((False, d, pb.name))      # the drawn wire is an exact hit, like a joint head
            continue
        points = np.asarray([ob.matrix_world @ pb.head, ob.matrix_world @ pb.tail])
        screen, front = project(points, persp, region.width, region.height)
        if not all(front):
            continue
        distance, t = segment_distance(mouse, screen[:1], screen[1:])
        width = BONE_WIDTH * np.linalg.norm(screen[1] - screen[0]) if ob.data.display_type == 'OCTAHEDRAL' else 0
        shaft = max(0.0, float(distance[0] - bone_width(t, width)[0]))
        head = float(np.linalg.norm(screen[0] - mouse))
        if min(head, shaft) <= radius:
            candidates.append((head > radius, head if head <= radius else shaft, pb.name))
    return min(candidates)[2] if candidates else None


# --- scene -------------------------------------------------------------------------------------------------

def ik_targets(scene):
    """Objects that are an IK constraint's target (Maya ikHandle; kit ``ikHandleN``)."""
    out = set()
    for ob in scene.objects:
        if ob.type != 'ARMATURE' or ob.pose is None:
            continue
        for pb in ob.pose.bones:
            for con in pb.constraints:
                if con.type == 'IK' and con.target is not None and con.target.type != 'ARMATURE':
                    out.add(con.target.name)
    return out


def kind_of(ob, targets):
    if ob.name in targets:
        return 'IK_HANDLE'
    return ob.type if ob.type in ('ARMATURE', 'CURVE') else 'OTHER'


def _selectable(ob, space, view_layer):
    viewport = {"viewport": space} if isinstance(space, bpy.types.SpaceView3D) else {}   # tests: no view
    if ob.hide_select or not ob.visible_get(view_layer=view_layer, **viewport):
        return False
    key = ob.type.lower()
    return (getattr(space, "show_object_viewport_" + key, True)
            and getattr(space, "show_object_select_" + key, True))


def _segments(ob, kind, depsgraph):
    """World-space segments (a, b, reach) of what is drawn for ``ob``; reach = widest half thickness
    per unit of length (bones)."""
    mw = ob.matrix_world
    if kind == 'ARMATURE':
        # a bone with a Custom Shape is drawn as that shape's wire, not the octahedron
        a, b, reach = [], [], []
        shapes = control_shapes.shows_custom_shapes(ob)
        for pb in ob.pose.bones:
            bone = pb.bone
            if compat.bone_hidden(pb) or (len(bone.collections) and not any(c.is_visible_effectively for c in bone.collections)):
                continue
            if shapes and pb.custom_shape is not None:
                sa, sb = control_shapes.shape_segments(ob, pb, depsgraph)
                a.extend(sa)
                b.extend(sb)
                reach.extend([0.0] * len(sa))
                continue
            a.append(mw @ pb.head)
            b.append(mw @ pb.tail)
            reach.append(BONE_WIDTH)
        return a, b, np.asarray(reach, dtype=np.float64)
    if kind == 'CURVE':
        ev = ob.evaluated_get(depsgraph)
        me = ev.to_mesh()
        try:
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            ed = np.empty(len(me.edges) * 2, dtype=np.int64)
            me.edges.foreach_get("vertices", ed)
            ed = ed.reshape(-1, 2)
        finally:
            ev.to_mesh_clear()
        if len(co):
            m = np.array(mw, dtype=np.float64)
            co = co @ m[:3, :3].T + m[:3, 3]
        return co[ed[:, 0]], co[ed[:, 1]], 0.0
    # IK handle empty: the plain axes it draws (other empty shapes approximated by their axes)
    size = ob.empty_display_size if ob.type == 'EMPTY' else 0.0
    o = mw.translation
    a, b = [], []
    for axis in range(3):
        d = mw.col[axis].xyz * size
        a.append(o - d)
        b.append(o + d)
    return a, b, 0.0


def hits(context, region, rv3d, mouse):
    """``(name, priority, screen distance)`` for every selectable object above priority 2."""
    space, view_layer = context.space_data, context.view_layer
    depsgraph = context.evaluated_depsgraph_get()
    targets = ik_targets(context.scene)
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    from ..ui import maya_joints
    maya_view = maya_joints.is_maya_view(space, getattr(getattr(context, "window", None), "workspace", None))
    out = []
    for ob in context.scene.objects:   # view_layer.objects can yield None after removals
        kind = kind_of(ob, targets)
        pri = priority(kind)
        if pri <= DEFAULT or not _selectable(ob, space, view_layer):
            continue
        if kind == 'ARMATURE' and maya_view:
            d = min(maya_joints.screen_distance(context, ob, mouse).values(), default=float("inf"))
            out.append((ob.name, pri, d))
            continue
        a, b, reach = _segments(ob, kind, depsgraph)
        if len(a) == 0:
            continue
        xa, fa = project(np.asarray(a, dtype=np.float64), persp, region.width, region.height)
        xb, fb = project(np.asarray(b, dtype=np.float64), persp, region.width, region.height)
        width = reach * np.hypot(*(xb - xa).T) if np.any(reach) else None
        d = segments_hit(mouse, xa, xb, fa & fb, width)
        out.append((ob.name, pri, max(d, 0.0)))
    return out


def apply(context, ob, shift, ctrl):
    """Maya click modifiers: none = replace, Shift = toggle,
    Ctrl = deselect, Ctrl+Shift = add. Selecting makes ``ob`` the lead (active)."""
    view_layer = context.view_layer
    if ctrl and not shift:
        ob.select_set(False)
        return
    if shift and not ctrl and ob.select_get():
        ob.select_set(False)
        return
    if not shift and not ctrl:
        for other in context.selected_objects:
            if other != ob:
                other.select_set(False)
    ob.select_set(True)
    view_layer.objects.active = ob


def _enabled(context):
    from .. import preferences
    return preferences.get(context).select_priority


class ALLSET_OT_select_priority(bpy.types.Operator):
    """Click selection with Maya's priority: IK handles, joints and curves win over meshes"""
    bl_idname = "allset.select_priority"
    bl_label = "Select (Maya Priority)"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        from ..ui import toolbox
        space, region = context.space_data, context.region
        if (context.mode not in {'OBJECT', 'POSE', 'EDIT_ARMATURE'} or space is None or space.type != 'VIEW_3D' or region is None
                or region.type != 'WINDOW' or toolbox.is_toolbox(space)):
            return {'PASS_THROUGH'}
        rv3d = context.region_data
        if rv3d is None:
            return {'PASS_THROUGH'}
        scale = context.preferences.system.ui_scale or 1.0
        from . import joint_selection
        mouse = (event.mouse_region_x, event.mouse_region_y)
        radius = RADIUS_PX * scale
        # In component mode native bone picking keeps endpoint and connected-bone semantics.
        # A click away from the skeleton releases the edit-mode lock.
        if context.mode == 'EDIT_ARMATURE':
            ob = context.active_object
            name = pick_joint(context, ob, mouse, radius)
            if name is not None:
                if joint_selection.joint_mode(ob) == 'EDIT':
                    # #156: a joint of a skeleton shown in Edit mode is picked like a Maya joint (its
                    # subtree moves with it), not as Blender's head / tail point
                    selected = joint_selection.select(context, ob, name, event.shift, event.ctrl)
                    return self._finish_pick(context, event, selected)
                return {'PASS_THROUGH'}
            joint_selection.select_object_at(context, mouse, event.shift, event.ctrl)
            active = context.active_object
            return self._finish_pick(context, event, active is not None and active.select_get())
        enabled = _enabled(context)
        best = rank(hits(context, region, rv3d, mouse), radius) if enabled else None
        if best is None:
            if not enabled and context.mode == 'OBJECT':
                # Selection Priority off: only a click on a joint is the kit's (a Maya
                # joint is its own node: pick it, not the whole armature); every other click is Blender's own pick.
                for ob in context.visible_objects:
                    if ob.type != 'ARMATURE' or ob.hide_select:
                        continue
                    name = pick_joint(context, ob, mouse, radius)
                    if name is not None:
                        selected = joint_selection.select(context, ob, name, event.shift, event.ctrl)
                        return self._finish_pick(context, event, selected)
                return {'PASS_THROUGH'}
            if context.mode == 'POSE':
                # Priority can be disabled without disabling direct joint selection in the rig.
                ob = context.active_object
                name = pick_joint(context, ob, mouse, radius)
                if name is not None:
                    selected = joint_selection.select(context, ob, name, event.shift, event.ctrl)
                    return self._finish_pick(context, event, selected)
                return self._pose_miss(context, event, ob, mouse)
            return {'PASS_THROUGH'}
        ob = context.scene.objects[best[0]]
        if ob.type == 'ARMATURE':
            name = pick_joint(context, ob, mouse, radius)
            if name is None:
                # The coarse armature hit includes unselectable bones; let native picking decide.
                if context.mode == 'POSE':
                    return self._pose_miss(context, event, context.active_object, mouse)
                return {'PASS_THROUGH'}
            selected = joint_selection.select(context, ob, name, event.shift, event.ctrl)
        else:
            joint_selection.leave(context, clear_selection=not (event.shift or event.ctrl))
            apply(context, ob, event.shift, event.ctrl)
            selected = ob.select_get()
        return self._finish_pick(context, event, selected)

    def _pose_miss(self, context, event, ob, mouse):
        """A Pose-mode click that hit no control (#171). Maya has no selection mode to leave: a click whose
        click box holds no curve / joint picks the object under it, else clears the selection
        (a click on empty space selects nothing). So: another object under the click ->
        leave Pose and select it (Blender can't pick another object from Pose); nothing -> stay in Pose, bones
        deselected (Shift / Ctrl: nothing changes)."""
        from ..ui import toolbox
        from . import joint_selection
        other = toolbox._other_object_under_click(context, ob, *mouse) if ob is not None else None
        if other is not None:
            joint_selection.select_object_at(context, mouse, event.shift, event.ctrl)
            active = context.active_object
            return self._finish_pick(context, event, active is not None and active.select_get())
        if not (event.shift or event.ctrl):
            joint_selection.clear(context)
            for area in context.screen.areas if context.screen else ():
                area.tag_redraw()
        return {'FINISHED'}

    def _finish_pick(self, context, event, selected):
        if event.value == 'PRESS' and selected:
            # Tweak tool: this press is consumed, so Blender makes no CLICK_DRAG from it — start the
            # tweak's move ourselves once the mouse leaves the drag threshold
            self._start = (event.mouse_x, event.mouse_y)
            self._threshold = context.preferences.inputs.drag_threshold_mouse * (context.preferences.system.ui_scale or 1.0)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            if math.hypot(event.mouse_x - self._start[0], event.mouse_y - self._start[1]) >= self._threshold:
                bpy.ops.transform.translate('INVOKE_DEFAULT', release_confirm=True)
                return {'FINISHED'}
            return {'RUNNING_MODAL'}
        if event.type in {'LEFTMOUSE', 'ESC', 'RIGHTMOUSE'} and event.value in {'RELEASE', 'PRESS'}:
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


classes = (ALLSET_OT_select_priority,)
