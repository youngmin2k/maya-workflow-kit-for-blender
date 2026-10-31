# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya joints: Joint Tool, Orient Joint, Mirror Joints, joint pick-walk and P / Shift+P.

Maya rigging (a Maya joint = a bone of one armature per
skeleton, ``skeleton1`` / ``joint1``, rotate order XYZ, Blender's bone Y points at the child).
A Maya joint is a point and a Blender bone a segment, so N clicks make N
bones: bone K runs from click K to click K+1, the last (Maya's end joint) gets a short tail along the
previous segment.
"""

import json
import re

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector

from .. import results
from .. import undo_steps
from . import joint_preview, naming, units

JOINT_BASE = "joint"
SKELETON_BASE = "skeleton"
STATUS = "Joint Tool: click to place, drag to position. Click a joint to branch. Enter finishes"
AXIS_NOTE = ("Blender joints point their Y axis at the child joint; a Maya frame with another primary axis is "
             "kept with the joint (exported to FBX).")


def _cb():
    from ..ui import channel_box
    return channel_box


# --- placing joints ---------------------------------------------------------------------------

def click_point(region, rv3d, coord):
    """World point for a click (Maya Joint Tool depth): an orthographic view places on the view plane
    through the origin, a perspective view on the ground (z = 0), else at the origin's depth."""
    origin = Vector((0.0, 0.0, 0.0))
    if rv3d.is_perspective:
        start = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        if abs(ray.z) > 1e-6:
            t = -start.z / ray.z
            if t > 0:
                return start + ray * t
    return view3d_utils.region_2d_to_location_3d(region, rv3d, coord, origin)


def taken_joint_names():
    """Joint names of the skeletons that still exist. Maya names are unique among existing nodes: a deleted
    skeleton frees ``joint1`` again (#73) — its armature data stays in ``bpy.data`` with no users until a purge,
    so only armatures an object still uses count."""
    names = set()
    for ob in bpy.data.objects:
        if ob.type != 'ARMATURE' or ob.users == 0:
            continue
        names.update(b.name for b in ob.data.bones)
        if ob.mode == 'EDIT':
            names.update(eb.name for eb in ob.data.edit_bones)
    return names


def next_joint_name(base=JOINT_BASE, extra=()):
    """Lowest free ``jointN`` over every armature (Maya numbers joints scene-wide)."""
    return f"{base}{naming.next_number(base, taken_joint_names() | set(extra))}"


def new_skeleton(context):
    """``skeleton1``: an armature at the origin, selected, active, in edit mode."""
    arm = bpy.data.armatures.new(SKELETON_BASE)
    ob = bpy.data.objects.new(SKELETON_BASE, arm)
    context.view_layer.active_layer_collection.collection.objects.link(ob)
    naming.apply_maya_name(ob, SKELETON_BASE, rename_data=False)
    arm.name = ob.name
    if context.active_object is not None and context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for other in context.selected_objects:
        other.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    return ob


def add_joint(ob, point, parent_name=None, up=Vector((0.0, 0.0, 1.0)), length=1.0):
    """Add a joint (edit bone) at world ``point`` under ``parent_name``; returns its name (the parent's
    name when the click repeats the parent's position). An end joint parent gets its tail moved here."""
    ebs = ob.data.edit_bones
    p = ob.matrix_world.inverted() @ Vector(point)
    parent = ebs.get(parent_name) if parent_name else None
    if parent is not None and (p - parent.head).length < 1e-6:
        return parent.name
    eb = ebs.new(next_joint_name())
    eb.inherit_scale = 'NONE'      # Maya segmentScaleCompensate on (the default; Blender 4.5)
    stamp_last(eb)                 # Maya child order = creation order
    eb.head = p
    if parent is None:
        eb.tail = p + Vector(up).normalized() * length
        return eb.name
    seg = p - parent.head
    if len(parent.children) == 0:
        parent.tail = p                      # the parent was an end joint: it now reaches this one
    eb.parent = parent
    eb.use_connect = (parent.tail - p).length < 1e-6
    eb.tail = p + seg.normalized() * seg.length * 0.5
    return eb.name


def move_joint(ob, name, point, up=Vector((0.0, 0.0, 1.0)), length=1.0):
    """Move the end joint ``name`` (just placed by ``add_joint``) to world ``point`` with the same rules: the bone
    from its parent follows when connected, its own tail keeps half the parent segment (a root: ``length`` along
    ``up``). A point on the parent joint itself is skipped (no zero-length bone). True when moved."""
    eb = ob.data.edit_bones.get(name)
    if eb is None:
        return False
    p = ob.matrix_world.inverted() @ Vector(point)
    parent = eb.parent
    if parent is None:
        eb.head = p
        eb.tail = p + Vector(up).normalized() * length
        return True
    seg = p - parent.head
    if seg.length < 1e-6:
        return False
    if eb.use_connect:
        parent.tail = p
    eb.head = p
    eb.tail = p + seg * 0.5
    return True


def finish(context, ob, names, top=None):
    """Pose mode, new joints rotate XYZ. Maya 2026 selects the top of the branch just made: the
    new chain's root, or ``top`` = the existing joint the chain branched from."""
    if ob.mode != 'POSE':
        bpy.ops.object.mode_set(mode='POSE')
    cb = _cb()
    for pb in ob.pose.bones:
        if pb.name in names:
            pb.rotation_mode = 'XYZ'
        cb.set_bone_selected(pb, False)
    head = top or (names[0] if names else None)
    pb = ob.pose.bones.get(head) if head else None
    if pb is not None:
        cb.set_bone_selected(pb, True)
        ob.data.bones.active = pb.bone


def view_under(window, x, y):
    """(area, WINDOW region) of the 3D View under window position x, y (not the Tool Box column)."""
    from ..ui import toolbox
    if window is None:
        return None
    for area in window.screen.areas:
        if area.type != 'VIEW_3D' or toolbox.is_toolbox(area.spaces.active):
            continue
        for region in area.regions:
            if region.type == 'WINDOW' and region.x <= x < region.x + region.width \
                    and region.y <= y < region.y + region.height:
                return area, region
    return None


# Maya Joint Tool settings the kit honours: Secondary Axis Y with
# Secondary Axis World Orientation +Y (Joint Tool default), Create IK handle off. Blender bones point their Y at the
# child (= Maya Primary Axis X); a joint's Maya Y / Z = the bone's Z / X (rig_tools.local_axis).
SECONDARY_AXES = (("X", "X", "Maya X is the primary axis: not allowed"), ("Y", "Y", "The bone's Z axis"),
                  ("Z", "Z", "The bone's X axis"), ("NONE", "None", "Leave the bone roll as placed"))
# Maya world axis (Y-up) -> Blender world vector (Z-up: X -> X, Y -> Z, Z -> -Y)
WORLD_AXES = {"X": Vector((1.0, 0.0, 0.0)), "Y": Vector((0.0, 0.0, 1.0)), "Z": Vector((0.0, -1.0, 0.0))}

# A Maya joint's axes in its bone's axes: X = bone Y (down the chain), Y = bone Z, Z = bone X (rig_tools.local_axis);
# the kit's FBX writer uses the same mapping (file_io export_args primary 'X' / secondary 'Z').
JOINT_AXES = Matrix(((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
# Maya's world axes in Blender world coordinates (Maya X -> X, Y -> Z, Z -> -Y)
MAYA_WORLD = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))
# A Maya joint frame a bone can't take: a Blender bone always points its Y at the child, a Maya joint's X need not.
# Such joints store their Maya frame relative to the bone's joint frame (``MAYA_FRAME``, quaternion in joint axes) and
# the FBX writer turns the joint by it (fbx_rig.rewrite). Two cases:
# - Orient Joint / Joint Tool (oj xyz, any sao) leave an END joint (no child joint) lined up with the world: joint3
#   jointOrient (0, 7.31, 0) after joint1 (0, 7.01, 0) and joint2 (0, -14.32, 0);
# - Mirror Joints Behavior: the copy's frame is -(reflection x source frame) — its X points back up the chain
#   (joint4 (-180, -7.01, 0), joint5 (0, -14.32, 0) with translate X -8.06), Orientation: the source's frame.
MAYA_FRAME = "allset_maya_frame"


def joint_frame(ob, eb):
    """World rotation of a Maya joint's axes for edit bone ``eb`` (as the bone allows)."""
    return (ob.matrix_world.to_3x3().normalized() @ eb.matrix.to_3x3().normalized()) @ JOINT_AXES


def maya_frame(ob, eb):
    """The joint's Maya frame (world rotation): the bone's joint frame turned by ``MAYA_FRAME``."""
    from mathutils import Quaternion
    q = eb.get(MAYA_FRAME)
    f = joint_frame(ob, eb)
    return f @ Quaternion(q).to_matrix() if q is not None and len(q) == 4 else f


def set_maya_frame(ob, eb, frame):
    """Store ``frame`` (world rotation) as the joint's Maya frame; nothing stored when the bone has it."""
    q = (joint_frame(ob, eb).inverted() @ frame).to_quaternion()
    if q.angle < 1e-7:
        if MAYA_FRAME in eb:
            del eb[MAYA_FRAME]
    else:
        eb[MAYA_FRAME] = list(q)


def store_end_orient(ob, ebs, names):
    """After an orient: joints with a child joint take the bone's frame, end joints Maya's world-aligned one."""
    for name in names:
        eb = ebs.get(name)
        if eb is not None:
            set_maya_frame(ob, eb, joint_frame(ob, eb) if eb.children else MAYA_WORLD)


def maya_frames(ob):
    """{bone name: rotation Matrix in joint axes} of the joints whose Maya frame differs from the bone's."""
    from mathutils import Quaternion
    out = {}
    for b in ob.data.bones:
        q = b.get(MAYA_FRAME)
        if q is not None and len(q) == 4:
            out[b.name] = Quaternion(q).to_matrix()
    return out


# Issue #142: Blender ignores every location constraint on a CONNECTED bone (its head is glued to the
# parent's tail; 4.5: Copy Location / Child Of / Copy Transforms / Limit Location leave it in place, rotation
# constraints work), while a Maya joint's translate is free: Constrain > Point / Parent on a child joint moves it.
# The joint that gets such a constraint is disconnected (only that bone — Joint Tool chains stay connected,
# so moving a joint in edit mode still drags the chain); it stays where it is (rest pose unchanged) and the bone is
# marked ``FREED``. Undo brings the connection back with the constraint.
LOCATION_CONSTRAINTS = frozenset({'COPY_LOCATION', 'CHILD_OF', 'COPY_TRANSFORMS', 'LIMIT_LOCATION', 'LIMIT_DISTANCE',
                                  'SHRINKWRAP', 'FOLLOW_PATH', 'CLAMP_TO', 'FLOOR', 'TRANSFORM', 'PIVOT'})
FREED = "allset_freed_connect"


def location_constrained(arm):
    """Names of the connected bones of ``arm`` that carry a location constraint."""
    out = []
    for b in arm.data.bones:
        if not b.use_connect:
            continue
        pb = arm.pose.bones.get(b.name)
        if pb is not None and any(c.type in LOCATION_CONSTRAINTS and c.enabled for c in pb.constraints):
            out.append(b.name)
    return out


def free_location_constrained(context, arm):
    """Disconnect the bones Blender would hold at the parent's tail despite a location constraint; returns them."""
    names = location_constrained(arm)
    if not names:
        return []
    vl = context.view_layer
    prev = vl.objects.active
    vl.objects.active = arm
    try:
        with _InEditMode(arm) as ebs:
            for name in names:
                eb = ebs.get(name)
                if eb is not None:
                    eb.use_connect = False
                    eb[FREED] = True
    finally:
        vl.objects.active = prev
    return names


def orient_new(ob, names, secondary="Y", world="Y", sign="+", aos=True, to_world=False):
    """Orient the new joints the way Maya's Joint Tool does on finish (Joint Tool default: orientation xyz, secondary
    axis yup, auto orient secondary on): primary X, ``secondary`` Y /
    Z toward the Maya world axis ``world`` / ``sign`` (bend normal with ``aos``), "NONE" = Maya's traditional orient (no
    secondary axis), ``to_world`` = Orient Joint to World. Also writes Maya's variable bone radius. Returns the number of
    joints oriented."""
    if secondary == "X":
        raise RuntimeError("Secondary axis must differ from the primary axis (X)")
    oj = "none" if to_world else ("xzy" if secondary == "Z" else "xyz")
    sao = None if secondary == "NONE" else world.lower() + ("up" if sign == "+" else "down")
    done = {}
    with _InEditMode(ob) as ebs:
        n = orient_bones(ob, ebs, [nm for nm in names if nm in ebs], oj, sao, aos, result=done)
        set_radius(ebs, [nm for nm in names if nm in ebs])
    fix_frames(ob, done)
    return n


def maya_bone_frame(bone):
    """A bone's (Bone or EditBone) Maya frame in armature space: columns Maya X, Y, Z (bone axes, turned by
    ``MAYA_FRAME``)."""
    from mathutils import Quaternion
    m = bone.matrix if isinstance(bone, bpy.types.EditBone) else bone.matrix_local
    f = m.to_3x3().normalized() @ JOINT_AXES
    q = bone.get(MAYA_FRAME)
    return f @ Quaternion(q).to_matrix() if q is not None and len(q) == 4 else f


def armature_world(ob):
    """Maya's world axes in the armature's own space."""
    return ob.matrix_world.to_3x3().normalized().inverted() @ MAYA_WORLD


def _first_child(eb):
    kids = list(eb.children)
    return kids[0] if kids else None


def _rotated(ob, name):
    """Maya skips joints whose rotate isn't zero (1e-10)."""
    pb = ob.pose.bones.get(name) if ob.pose is not None else None
    return pb is not None and pb.matrix_basis.to_quaternion().angle > 1e-9


def fix_frames(ob, frames):
    """After edit mode: Blender rebuilds each bone's matrix through its parent chain in float32 (a few 1e-6 off on
    short bones); store the remainder against the intended Maya ``frames`` {name: frame} in ``MAYA_FRAME``
    of the Bone."""
    if ob.mode == 'EDIT':
        return
    for name, frame in frames.items():
        bone = ob.data.bones.get(name)
        if bone is None:
            continue
        base = bone.matrix_local.to_3x3().normalized() @ JOINT_AXES
        from .joint_edit import FRAME_TOL
        if max((base.col[i] - frame.col[i]).length for i in range(3)) < FRAME_TOL:   # not q.angle (float32)
            if MAYA_FRAME in bone:
                del bone[MAYA_FRAME]
        else:
            from .joint_edit import quat_between
            bone[MAYA_FRAME] = quat_between(base, frame)


def orient_bones(ob, ebs, names, oj="xyz", sao="yup", aos=True, skipped=None, result=None):
    """Write Maya orientJoint frames (operators/joint_orient.py) onto edit bones ``names``: the roll puts the bone's Z
    on Maya Y, and a frame the bone can't take (primary axis not X, an end joint) goes into ``MAYA_FRAME``. Rotated
    joints are skipped (``skipped`` gets (name, reason)). Returns the number oriented."""
    from . import joint_orient
    # Skin-bound joints are oriented too, without a warning. Maya then moves the skinned mesh (bindPreMatrix
    # kept); Blender's skin follows the new rest, so the kit's mesh stays (a kit difference).
    depth = {eb.name: len(eb.parent_recursive) for eb in ebs}
    order = sorted(names, key=lambda nm: depth.get(nm, 0))
    todo = []
    for nm in order:
        if _rotated(ob, nm):
            if skipped is not None:
                skipped.append((nm, "It has non-zero rotations."))
        else:
            todo.append(nm)
    pos = {eb.name: eb.head.copy() for eb in ebs}
    parent_of = {eb.name: (eb.parent.name if eb.parent is not None else None) for eb in ebs}
    first = {eb.name: (c.name if (c := _first_child(eb)) is not None else None) for eb in ebs}
    frames = {eb.name: maya_bone_frame(eb) for eb in ebs}
    old = {k: v.copy() for k, v in frames.items()}
    origin = ob.matrix_world.inverted() @ Vector((0.0, 0.0, 0.0))
    world = armature_world(ob)
    out = joint_orient.orient_frames(todo, pos, parent_of, first, frames, world, oj, sao, aos, origin)
    for nm, f in out.items():
        set_bone_frame(ebs[nm], f)
    # a skipped rotated joint keeps its jointOrient (Maya: jo / rotate unchanged), so it turns with a re-oriented parent
    for nm in order:
        par = parent_of.get(nm)
        if nm in out or par not in out:
            continue
        f = out[par] @ (old[par].transposed() @ old[nm])
        frames[nm] = out[nm] = f
        set_bone_frame(ebs[nm], f)
    if result is not None:
        result.update(out)
    return sum(1 for nm in out if nm in todo)


def set_bone_frame(eb, frame):
    """Give edit bone ``eb`` the Maya frame ``frame`` (armature space): roll its Z onto Maya Y (or the axis least along
    the bone), the rest into ``MAYA_FRAME``."""
    y = (eb.tail - eb.head).normalized()
    target = frame.col[1]
    if abs(y.dot(target)) > 0.999:
        target = frame.col[2] if abs(y.dot(frame.col[2])) < abs(y.dot(frame.col[0])) else frame.col[0]
    eb.align_roll(target)
    from .joint_edit import _set_local_frame
    _set_local_frame(eb, frame)


def set_radius(ebs, names, unit=None):
    """Maya Joint Tool variable bone radius (``allset_radius``, Maya units): from the distance to the first child,
    an end joint copies its parent's."""
    from . import joint_orient
    k = unit or units.maya_unit(bpy.context.scene)
    for nm in names:
        eb = ebs.get(nm)
        if eb is None:
            continue
        child = _first_child(eb)
        if child is not None:
            eb[RADIUS] = joint_orient.radius((child.head - eb.head).length / k)
        elif eb.parent is not None and RADIUS in eb.parent:
            eb[RADIUS] = eb.parent[RADIUS]
        else:
            eb[RADIUS] = 0.5


RADIUS = "allset_radius"


# A Joint Tool click inside a joint's drawn sphere branches from it (Maya 2026: the hit area is the drawn sphere,
# not a fixed radius). Blender draws an octahedral bone's joint as a sphere of radius
# JOINT_SPHERE x the bone length (a connected head: the incoming bone's tail sphere) [I: Blender's bone point shape];
# the floor is Maya's click box (select_priority.RADIUS_PX), also the whole hit area of Stick bones.
JOINT_SPHERE = 0.05
BRANCH_MIN_PX = 5.0


def joint_sphere_radius(arm, bone):
    """World radius of the sphere Blender draws at ``bone``'s head (0 when it draws none: Stick / B-Bone / ...)."""
    scale = max(arm.matrix_world.to_scale())
    maya = bone.get(RADIUS)
    if maya is not None:     # the Maya joint radius (Joint Tool variable bone size) is the click sphere
        # x Display > Animation > Joint Size (Maya jointDisplayScale)
        size = float(getattr(bpy.context.scene, "allset_joint_size", 1.0) or 1.0)
        return float(maya) * units.maya_unit(bpy.context.scene) * scale * size
    if arm.data.display_type != 'OCTAHEDRAL':
        return 0.0
    src = bone.parent if bone.parent is not None and bone.use_connect else bone
    return JOINT_SPHERE * src.length * scale


def pick_branch_joint(region, rv3d, armatures, coord, floor):
    """(armature, bone name) whose head sphere holds ``coord`` (screen px), nearest first; None."""
    from bpy_extras import view3d_utils
    right = rv3d.view_rotation @ Vector((1.0, 0.0, 0.0))
    best, best_d = None, None
    for arm in armatures:
        for bone in arm.data.bones:
            if bone.hide or (bone.collections and not any(c.is_visible_effectively for c in bone.collections)):
                continue
            head = arm.matrix_world @ bone.head_local
            p = view3d_utils.location_3d_to_region_2d(region, rv3d, head)
            if p is None:
                continue
            r = joint_sphere_radius(arm, bone)
            edge = view3d_utils.location_3d_to_region_2d(region, rv3d, head + right * r) if r > 0 else None
            radius = max(floor, (edge - p).length if edge is not None else 0.0)
            d = (Vector(coord) - p).length
            if d <= radius and (best_d is None or d < best_d):
                best, best_d = (arm, bone.name), d
    return best


class ALLSET_OT_joint_tool(bpy.types.Operator):
    """Maya Joint Tool: click in a view to place joints (each one a child of the last), Enter to finish"""
    bl_idname = "allset.joint_tool"
    bl_label = "Joint Tool"
    bl_options = {'UNDO'}

    secondary_axis: EnumProperty(name="Secondary Axis", items=SECONDARY_AXES, default="Y")
    secondary_world: EnumProperty(name="Secondary Axis World Orientation",
                                  items=[(a, a, "") for a in ("X", "Y", "Z")], default="Y")
    secondary_sign: EnumProperty(name="Sign", items=(("+", "+", ""), ("-", "-", "")), default="+")
    # Maya 2025+ Joint Tool default: auto orient secondary on; Orient Joint to World =
    # no orientation
    auto_secondary: BoolProperty(name="Auto orient secondary axis", default=True)
    orient_world: BoolProperty(name="Orient Joint to World", default=False)
    create_ik: BoolProperty(name="Create IK handle", default=False)
    ik_solver: EnumProperty(name="Current solver",
                            items=(("RP", "Rotate-Plane Solver", ""), ("SC", "Single-Chain Solver", "")), default="RP")
    ik_solver_enable: BoolProperty(name="Solver enable", default=True)
    ik_weight: FloatProperty(name="Weight", default=1.0, min=0.01, max=1.0)
    points: StringProperty(options={'SKIP_SAVE', 'HIDDEN'},
                           description="JSON list of world points: place these joints without clicks (scripts)")

    def execute(self, context):
        """Without clicks: a new skeleton with a joint at each of ``points``."""
        try:
            pts = [Vector(p) for p in json.loads(self.points)] if self.points else []
        except (ValueError, TypeError):
            pts = []
        if not pts:
            self.report({'WARNING'}, "Joint Tool: click in a view to place joints")
            return {'CANCELLED'}
        ob = new_skeleton(context)
        names, parent = [], None
        for p in pts:
            name = add_joint(ob, p, parent, length=units.maya_unit(context.scene))
            if name != parent:
                names.append(name)
            parent = name
        self._names, self._ob = names, ob
        return self._finish(context)

    def invoke(self, context, event):
        if context.window is None:
            return {'CANCELLED'}
        # Maya 2022-2027 never branch from a joint selected before the tool starts (joint1 selected, two
        # clicks -> an unparented chain); clicking an existing joint with the tool does
        # (``_branch_from``).
        self._names, self._ob, self._parent, self._top = [], None, None, None
        self._placed, self._redo = [], []   # joints placed by this tool run, newest last / undone ones
        self._swallow = False
        self._drag = None          # (joint name, area pointer, region pointer) while the button is held
        self._cursor = False
        context.workspace.status_text_set(STATUS)
        from .. import command_line
        command_line.MODAL_HELP[self.bl_idname] = STATUS
        joint_preview.start()
        self._hover(context, event)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self, context):
        context.workspace.status_text_set(None)
        joint_preview.stop()
        self._set_cursor(context, False)
        joint_preview.redraw(context.window)

    def _set_cursor(self, context, on):
        """Crosshair while the pointer is over a 3D View (where a click places a joint)."""
        if on == self._cursor or context.window is None:
            return
        if on:
            context.window.cursor_modal_set('CROSSHAIR')
        else:
            context.window.cursor_modal_restore()
        self._cursor = on

    def _sync_preview(self):
        st = joint_preview.STATE
        try:
            st["ob"] = self._ob.name if self._ob is not None else None
        except ReferenceError:
            st["ob"] = None
        st["names"] = list(self._names)
        st["top"] = self._top
        st["current"] = self._parent

    def _hover(self, context, event):
        """Preview state for the pointer: where a click would place the next joint, or the joint it would branch
        from."""
        st = joint_preview.STATE
        st["dragging"] = self._drag is not None
        hit = view_under(context.window, event.mouse_x, event.mouse_y) if context.window is not None else None
        self._set_cursor(context, hit is not None)
        if hit is None:
            st.update(region=0, point=None, branch=None)
        else:
            _area, region = hit
            coord = (event.mouse_x - region.x, event.mouse_y - region.y)
            branch = None
            if self._ob is None:
                arms = [o for o in context.view_layer.objects if o is not None and o.type == 'ARMATURE' and o.visible_get()]
                scale = context.preferences.system.ui_scale or 1.0
                if arms:
                    found = pick_branch_joint(region, region.data, arms, coord, BRANCH_MIN_PX * scale)
                    branch = (found[0].name, found[1]) if found else None
            point = click_point(region, region.data, coord)
            st.update(region=region.as_pointer(), point=tuple(point), branch=branch)
        self._sync_preview()
        joint_preview.redraw(context.window)

    def _drag_to(self, context, event):
        """Move the joint placed by the press with the pointer (Maya: the joint follows until release)."""
        from .. import live_refs
        name, area_ptr, region_ptr = self._drag
        area = live_refs.area(area_ptr, context.window)
        region = live_refs.region(area, region_ptr)
        if region is None or self._ob is None:
            return
        rv3d = region.data
        coord = (event.mouse_x - region.x, event.mouse_y - region.y)
        point = click_point(region, rv3d, coord)
        up = rv3d.view_rotation @ Vector((0.0, 1.0, 0.0))
        move_joint(self._ob, name, point, up=up, length=units.maya_unit(context.scene))
        joint_preview.redraw(context.window)

    def _place(self, context, event):
        hit = view_under(context.window, event.mouse_x, event.mouse_y)
        if hit is None:
            return False
        area, region = hit
        rv3d = region.data
        coord = (event.mouse_x - region.x, event.mouse_y - region.y)
        self._drag = None
        if self._ob is None and self._branch_from(context, area, region, coord):
            return True
        point = click_point(region, rv3d, coord)
        up = rv3d.view_rotation @ Vector((0.0, 1.0, 0.0))
        self._redo.clear()
        name = self._add_at(context, area, region, point, up)
        if name is not None:
            self._drag = (name, area.as_pointer(), region.as_pointer())
        return True

    def _add_at(self, context, area, region, point, up):
        """Place the next joint at world ``point``; returns its name (None when the click repeats the current
        joint). Each placed joint is remembered so undo inside the tool can take it back."""
        created = self._ob is None
        if created:
            with context.temp_override(window=context.window, area=area, region=region):
                self._ob = new_skeleton(context)
        if self._ob.mode != 'EDIT':
            with context.temp_override(window=context.window, area=area, region=region):
                bpy.ops.object.mode_set(mode='EDIT')
        parent = self._ob.data.edit_bones.get(self._parent) if self._parent else None
        tail = parent.tail.copy() if parent is not None and len(parent.children) == 0 else None
        name = add_joint(self._ob, point, self._parent, up=up, length=units.maya_unit(context.scene))
        if name == self._parent:
            return None
        self._names.append(name)
        self._placed.append((name, self._parent, tail, Vector(point), Vector(up), created))
        self._parent = name
        area.tag_redraw()
        return name

    def _undo_joint(self, context):
        """Undo inside the tool (like Maya): take back the last joint this run placed; the skeleton goes when its
        first joint does. The tool keeps running."""
        if not self._placed or self._ob is None:
            return
        name, parent, tail, point, up, created = self._placed.pop()
        self._drag = None
        hit = self._any_view(context)
        override = dict(window=context.window, area=hit[0], region=hit[1]) if hit else dict(window=context.window)
        ob = self._ob
        with context.temp_override(**override):
            if ob.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            ebs = ob.data.edit_bones
            eb = ebs.get(name)
            if eb is not None:
                ebs.remove(eb)
            pe = ebs.get(parent) if parent else None
            if pe is not None and tail is not None:
                pe.tail = tail
            if name in self._names:
                self._names.remove(name)
            self._parent = parent
            self._redo.append((point, up))
            if created:
                bpy.ops.object.mode_set(mode='OBJECT')
                arm = ob.data
                bpy.data.objects.remove(ob)
                if arm.users == 0:
                    bpy.data.armatures.remove(arm)
                self._ob, self._parent, self._names, self._placed = None, None, [], []
        if hit:
            hit[0].tag_redraw()

    def _redo_joint(self, context):
        """Redo inside the tool: place the joint the last undo took back."""
        if not self._redo:
            return
        point, up = self._redo.pop()
        hit = self._any_view(context)
        if hit is not None:
            self._add_at(context, hit[0], hit[1], point, up)

    def _check_alive(self):
        """The skeleton or its joints can be removed behind the tool (Edit > Undo, a script): forget what is
        gone instead of touching removed data."""
        if self._ob is None:
            return
        try:
            ebs = self._ob.data.edit_bones if self._ob.mode == 'EDIT' else None
        except ReferenceError:
            self._names, self._ob, self._parent, self._top = [], None, None, None
            self._placed, self._redo, self._drag = [], [], None
            return
        if ebs is None:
            return
        self._names = [n for n in self._names if n in ebs]
        self._placed = [e for e in self._placed if e[0] in ebs]
        if self._parent is not None and self._parent not in ebs:
            self._parent = self._names[-1] if self._names else self._top
        if self._drag is not None and self._drag[0] not in ebs:
            self._drag = None

    def _branch_from(self, context, area, region, coord):
        """The first click on an existing joint: the new joints go under it (Maya Joint Tool). True when hit."""
        arms = [o for o in context.view_layer.objects if o is not None and o.type == 'ARMATURE' and o.visible_get()]
        scale = context.preferences.system.ui_scale or 1.0
        hit = pick_branch_joint(region, region.data, arms, coord, BRANCH_MIN_PX * scale) if arms else None
        if hit is None:
            return False
        arm, name = hit
        with context.temp_override(window=context.window, area=area, region=region):
            if context.mode != 'OBJECT' and context.active_object is not None:
                bpy.ops.object.mode_set(mode='OBJECT')
            for o in context.selected_objects:
                o.select_set(False)
            arm.select_set(True)
            context.view_layer.objects.active = arm
            bpy.ops.object.mode_set(mode='EDIT')
        self._ob, self._parent, self._top = arm, name, name
        area.tag_redraw()
        return True

    def modal(self, context, event):
        self._check_alive()
        if event.value == 'PRESS' and event.type in {'Z', 'Y'} and not (event.alt or event.oskey):
            plain = not (event.ctrl or event.shift)
            if (event.type == 'Z' and (plain or (event.ctrl and not event.shift))):
                self._undo_joint(context)
                self._hover(context, event)
                return {'RUNNING_MODAL'}
            if (event.type == 'Z' and event.shift) or (event.type == 'Y' and event.ctrl and not event.shift):
                self._redo_joint(context)
                self._hover(context, event)
                return {'RUNNING_MODAL'}
        # Maya 2026 ends the tool on Enter / Q / W / E / R with the branch top selected; Enter and Q leave the Select
        # Tool, W / E / R their tool.
        enter = event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS'
        if enter or (event.type in {'Q', 'W', 'E', 'R'} and event.value == 'PRESS'
                     and not (event.alt or event.ctrl or event.shift or event.oskey)):
            result = self._done(context)
            tool = {'Q': 'builtin.select_box', 'W': 'builtin.move',
                    'E': 'builtin.rotate', 'R': 'builtin.scale'}.get(event.type, 'builtin.select_box')
            hit = view_under(context.window, event.mouse_x, event.mouse_y) or self._any_view(context)
            if hit is not None and 'FINISHED' in result:
                with context.temp_override(window=context.window, area=hit[0], region=hit[1]):
                    bpy.ops.wm.tool_set_by_id(name=tool)
                # this command picked the Pose-mode tool itself; the one-tool carry must not
                # replace it with the placing mode's Select tool on the first Pose visit
                from . import tool_keys
                tool_keys._seen[context.mode] = tool
                tool_keys._mode[0] = context.mode
            return result
        if event.type == 'ESC' and event.value == 'PRESS':
            if not self._names:
                self._end(context)
                return {'CANCELLED'}
            return self._done(context)
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if self._drag is not None:
                self._drag_to(context, event)
                return {'RUNNING_MODAL'}
            self._hover(context, event)
            return {'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS' and not (event.alt or event.ctrl or event.shift or event.oskey):
                if self._place(context, event):
                    self._swallow = True
                    self._hover(context, event)
                    return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE' and self._swallow:
                self._swallow = False
                if self._drag is not None:
                    self._drag_to(context, event)
                    self._drag = None
                self._hover(context, event)
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    @staticmethod
    def _any_view(context):
        from ..ui import toolbox
        if context.window is None:          # no window (background, #158)
            return None
        return next(((a, r) for a in context.window.screen.areas
                     if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)
                     for r in a.regions if r.type == 'WINDOW'), None)

    def _done(self, context):
        self._end(context)
        if self._ob is None or not self._names:
            return {'CANCELLED'}
        hit = self._any_view(context)
        override = dict(window=context.window, area=hit[0], region=hit[1]) if hit else dict(window=context.window)
        with context.temp_override(**override):
            return self._finish(context)

    def _finish(self, context):
        ob, names = self._ob, self._names
        try:
            orient_new(ob, names, self.secondary_axis, self.secondary_world, self.secondary_sign,
                       self.auto_secondary, self.orient_world)
        except RuntimeError as ex:
            self.report({'WARNING'}, str(ex))
        finish(context, ob, names, getattr(self, "_top", None))
        msg = f"Created {len(names)} joint(s) in {ob.name}"
        if self.create_ik and len(names) >= 2:
            from .skin import create_ik
            handle = create_ik(context, ob, (names[0], 'HEAD'), (names[-1], 'HEAD'), self.ik_solver,
                               self.ik_solver_enable, self.ik_weight)
            if handle is not None:
                msg += f" and {handle.name}"
        results.result(self, msg)
        return {'FINISHED'}


# --- edit-mode helpers ------------------------------------------------------------------------

def _armature(context):
    ob = context.active_object
    return ob if ob is not None and ob.type == 'ARMATURE' and ob.mode in {'POSE', 'EDIT'} else None


def selected_joint_names(ob):
    """The joints the user picked. In Edit mode (the Move tool) a picked joint selects its whole subtree
    so W carries the children: the Skeleton menu / P act on the picked joints only, like Maya's selection (
    clicking joint1 then P / Mirror / Orient saw joint1's children as picked too)."""
    if ob.mode == 'EDIT':
        from .joint_selection import _edit_picked
        picked = [eb.name for eb in _edit_picked(ob)]
        return picked or [eb.name for eb in ob.data.edit_bones if eb.select]
    cb = _cb()
    return [pb.name for pb in ob.pose.bones if cb.bone_selected(pb)]


def active_joint_name(ob):
    if ob.mode == 'EDIT':
        act = ob.data.edit_bones.active
    else:
        act = ob.data.bones.active
    return act.name if act is not None else None


class _InEditMode:
    """Run a block in armature edit mode and come back to the mode it started in."""

    def __init__(self, ob):
        self.ob, self.mode = ob, ob.mode

    def __enter__(self):
        if self.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        return self.ob.data.edit_bones

    def __exit__(self, *exc):
        if self.mode != 'EDIT':
            bpy.ops.object.mode_set(mode=self.mode)


def with_descendants(ebs, names):
    out = []
    for name in names:
        eb = ebs.get(name)
        if eb is None:
            continue
        for b in [eb, *eb.children_recursive]:
            if b.name not in out:
                out.append(b.name)
    return out


# --- Orient Joint ---------------------------------------------------------------------------

# Maya secondary world orientation (Y-up) -> Blender calculate_roll type (Z-up: Maya X->X, Y->Z, Z->-Y)
SAO_ROLL = {"X+": 'GLOBAL_POS_X', "X-": 'GLOBAL_NEG_X', "Y+": 'GLOBAL_POS_Z', "Y-": 'GLOBAL_NEG_Z',
            "Z+": 'GLOBAL_NEG_Y', "Z-": 'GLOBAL_POS_Y'}
_AXES = [(a, a, "") for a in ("X", "Y", "Z")]


def orient(ob, names, sao, children=True, oj="xyz", aos=True, skipped=None):
    """Maya Skeleton > Orient Joint (``cmds.joint(edit=True, oj=oj, sao=sao, aos=..., ch=True, zso=True)``; default xyz
    / yup / aos on / children on): ``sao`` "Y+" .. "Z-" (kit enum), "NONE" = no
    secondary world axis (Maya's traditional orient), ``oj`` "none" = Orient Joint to World. Rotated / skinned joints
    are skipped (``skipped``). Returns the number oriented."""
    if oj != "none" and sao not in SAO_ROLL and sao != "NONE":
        return 0
    maya_sao = None if sao == "NONE" else sao[0].lower() + ("up" if sao[1] == "+" else "down")
    done = {}
    with _InEditMode(ob) as ebs:
        targets = with_descendants(ebs, names) if children else [n for n in names if n in ebs]
        n = orient_bones(ob, ebs, targets, oj, maya_sao, aos, skipped, done) if targets else 0
    fix_frames(ob, done)
    return n


def _load_options(op, key, names):
    """The values last used (like Maya's saved options): Blender doesn't remember properties of operators run from Python."""
    from .option_windows import saved
    for name, value in (saved("op_" + key) or {}).items():
        if name in names:
            try:
                setattr(op, name, value)
            except (TypeError, ValueError):
                pass


def _save_options(op, key, names):
    from .option_windows import store
    store("op_" + key, {name: getattr(op, name) for name in names})


class ALLSET_OT_orient_joint(bpy.types.Operator):
    """Maya Orient Joint: orient the joints from their positions (primary axis down the chain, secondary axis by the
    bend or a world direction)"""
    bl_idname = "allset.orient_joint"
    bl_label = "Orient Joint Options"
    bl_options = {'UNDO'}

    to_world: BoolProperty(name="Orient Joint to World", default=False)
    primary: EnumProperty(name="Primary Axis", items=_AXES, default="X")
    secondary: EnumProperty(name="Secondary Axis", items=_AXES, default="Y")
    world: EnumProperty(name="Secondary Axis World Orientation",
                        items=[(k, k, "") for k in SAO_ROLL] + [("NONE", "None", "No secondary axis world "
                                                                 "orientation: Maya's orient from the bend alone")],
                        default="Y+")
    auto_secondary: BoolProperty(name="Auto orient secondary axis", default=True,
                                 description="Maya 2025+: the secondary axis follows the bend of the chain, turned "
                                             "toward the world orientation")
    children: BoolProperty(name="Orient Children of Joint", default=True)
    option_box: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    OPTIONS = ("to_world", "primary", "secondary", "world", "auto_secondary", "children")

    @classmethod
    def poll(cls, context):
        return _armature(context) is not None

    def invoke(self, context, event):
        # Maya: a plain menu click runs with the saved options, the option box opens the window (the
        # dialog on every click kept the keyboard until closed). Blender keeps the last values.
        if self.option_box:
            return context.window_manager.invoke_props_dialog(self, width=360, confirm_text="Orient")
        _load_options(self, "orient_joint", self.OPTIONS)
        return self.execute(context)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "to_world")
        col = lay.column()
        col.enabled = not self.to_world
        col.prop(self, "primary")
        col.prop(self, "secondary")
        col.prop(self, "world")
        col.prop(self, "auto_secondary")
        lay.prop(self, "children")

    def execute(self, context):
        ob = _armature(context)
        names = selected_joint_names(ob)
        if not names:
            self.report({'WARNING'}, "Select joints to orient")
            return {'CANCELLED'}
        if not self.to_world and self.primary == self.secondary:
            self.report({'ERROR'}, "Secondary axis must differ from the primary axis")
            return {'CANCELLED'}
        _save_options(self, "orient_joint", self.OPTIONS)
        oj = "none" if self.to_world else (self.primary + self.secondary
                                           + ({"X", "Y", "Z"} - {self.primary, self.secondary}).pop()).lower()
        skipped = []
        orient(ob, names, self.world, self.children, oj, self.auto_secondary, skipped)
        for name, why in skipped:
            self.report({'WARNING'}, f"Skipping {name}: {why}")     # Maya's warning
        if skipped:
            # Maya ends with this one, naming the first rotated joint up the hierarchy
            self.report({'WARNING'}, f"Cannot perform joint orientation. Transform {skipped[0][0]} has non-zero "
                                     "rotations.")
        # Maya 2026 prints only the command echo (joint -e -oj xyz -sao yup -aos -ch -zso;), no result line
        # (Maya): the result field is cleared
        results.result(self, "")
        return {'FINISHED'}


# --- Mirror Joints ----------------------------------------------------------------------------

# Maya mirror plane (Y-up) -> Blender reflection (Z-up): YZ = x, XY = Maya z = Blender -y, XZ = Maya y = z
PLANES = {"XY": (1.0, -1.0, 1.0), "YZ": (-1.0, 1.0, 1.0), "XZ": (1.0, 1.0, -1.0)}


def mirrored_name(name, search, replace, taken):
    new = name.replace(search, replace) if search and search in name else name
    if new == name or new in taken:
        base = naming.base_name(new)
        new = f"{base}{naming.next_number(base, taken)}"
    return new


def mirror(ob, names, plane="XY", behavior=True, search="", replace=""):
    """Mirror the joints and their hierarchies across a plane through the world origin; returns the new names."""
    r = Matrix.Diagonal(PLANES[plane])
    mw = ob.matrix_world
    refl = mw.inverted().to_3x3() @ r @ mw.to_3x3()        # the world reflection in armature space
    origin = mw.inverted() @ (r @ (mw @ Vector((0.0, 0.0, 0.0))))
    new_names = []
    with _InEditMode(ob) as ebs:
        chain = with_descendants(ebs, names)
        taken = taken_joint_names() | {eb.name for eb in ebs}
        made = {}
        for name in chain:                                     # parents come before children
            src = ebs[name]
            rot = refl @ src.matrix.to_3x3()
            rot.col[0 if behavior else 2] *= -1.0              # right-handed again (Behavior = symmetrize)
            dst = ebs.new(mirrored_name(name, search, replace, taken))
            stamp_last(dst)
            taken.add(dst.name)
            dst.head = refl @ src.head + origin
            dst.tail = refl @ src.tail + origin
            m = rot.to_4x4()
            m.translation = dst.head
            dst.matrix = m
            # Maya's frame of the copy (see MAYA_FRAME): Behavior -(R F), Orientation F (world reflection R)
            f = maya_frame(ob, src)
            set_maya_frame(ob, dst, (r.to_3x3() @ f) * -1.0 if behavior else f)
            parent = src.parent
            if parent is not None and parent.name in made:
                dst.parent = ebs[made[parent.name]]
                dst.use_connect = src.use_connect
            else:
                dst.parent = parent
            made[name] = dst.name
            new_names.append(dst.name)
    if ob.mode != 'EDIT':
        copy_rotate(ob, made)
    return new_names


def _maya_axes(bone):
    """Maya joint axes in the bone's own coordinates (JOINT_AXES turned by ``MAYA_FRAME``)."""
    from mathutils import Quaternion
    q = bone.get(MAYA_FRAME)
    return JOINT_AXES @ Quaternion(q).to_matrix() if q is not None and len(q) == 4 else JOINT_AXES.copy()


def copy_rotate(ob, pairs):
    """Maya Mirror Joints copies the rotate values (both functions:
    dst r = src r). ``pairs`` {source: copy}; same Maya rotate in
    each joint's own axes, also when their bones differ from their Maya frames."""
    for src, dst in pairs.items():
        ps, pd = ob.pose.bones.get(src), ob.pose.bones.get(dst)
        if ps is None or pd is None:
            continue
        a_s, a_d = _maya_axes(ps.bone), _maya_axes(pd.bone)
        r_m = a_s.transposed() @ ps.matrix_basis.to_3x3() @ a_s
        q = (a_d @ r_m @ a_d.transposed()).to_quaternion()
        # a Maya joint rotates by Euler values: the copy keeps the source's order, XYZ otherwise
        euler = ps.rotation_mode not in ('QUATERNION', 'AXIS_ANGLE')
        pd.rotation_mode = ps.rotation_mode if euler else 'XYZ'
        pd.rotation_euler = q.to_euler(pd.rotation_mode, ps.rotation_euler) if euler else q.to_euler('XYZ')


class ALLSET_OT_mirror_joints(bpy.types.Operator):
    """Maya Mirror Joints: copy the selected joints and their children across a plane through the origin"""
    bl_idname = "allset.mirror_joints"
    bl_label = "Mirror Joints Options"
    bl_options = {'UNDO'}

    # default XY
    plane: EnumProperty(name="Mirror Across", items=[(k, k, "") for k in ("XY", "YZ", "XZ")], default="XY")
    function: EnumProperty(name="Mirror Function", items=(("BEHAVIOR", "Behavior", "Mirrored joints rotate "
                                                           "the opposite way (Blender symmetrize)"),
                                                          ("ORIENTATION", "Orientation", "Mirrored joints keep the "
                                                           "same axes")), default="BEHAVIOR")
    search: StringProperty(name="Search For")
    replace: StringProperty(name="Replace With")
    option_box: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return _armature(context) is not None

    def invoke(self, context, event):
        # Maya: a plain menu click runs with the saved options, the option box opens the window (the
        # dialog on every click kept the keyboard until closed). Blender keeps the last values.
        if self.option_box:
            return context.window_manager.invoke_props_dialog(self, width=360, confirm_text="Mirror")
        _load_options(self, "mirror_joints", ("plane", "function", "search", "replace"))
        return self.execute(context)

    def draw(self, context):
        lay = self.layout
        lay.prop(self, "plane", expand=True)
        lay.prop(self, "function", expand=True)
        lay.label(text="Replacement names for duplicated joints")
        lay.prop(self, "search")
        lay.prop(self, "replace")

    def execute(self, context):
        ob = _armature(context)
        names = selected_joint_names(ob)
        if not names:
            self.report({'WARNING'}, "Select the joints to mirror")
            return {'CANCELLED'}
        _save_options(self, "mirror_joints", ("plane", "function", "search", "replace"))
        new = mirror(ob, names, self.plane, self.function == "BEHAVIOR", self.search, self.replace)
        results.result(self, f"Mirrored {len(new)} joint(s)")
        return {'FINISHED'}


# --- joint pick-walk and parenting --------------------------------------------------------------

# Maya's pick walk walks the DAG and
# goes into hidden nodes; with controller tags it follows the controller
# hierarchy. Kit controller tags live on data Bones (operators/controllers.py). An untagged armature treats
# bones whose bone collections are all hidden as "not a control" and walks past them (preference
# pick_walk_skip_hidden_collections; Maya walks into hidden display layers — kit difference). Bones
# hidden one by one (h) are walked into like Maya.
CONTROLLER = "allset_controller"
CONTROLLER_PARENT = "allset_controller_parent"


# Issue #165: Maya's pickWalk goes down to the first child and sideways through the siblings in the
# parent's child order, wrapping at the ends (SELECT_PICK: spine's children L_arm, R_arm,
# neck — L_arm left -> neck, neck right -> L_arm). Maya's child order = creation order, a re-parented node goes last.
# Blender keeps bones in creation order (``arm.bones``, the edit-bone list); the kit stamps ``CHILD_ORDER`` on a bone
# it re-parents (P, Connect / Remove / Disconnect / Insert Joint) with the armature's next number, so it sorts last.
CHILD_ORDER = "allset_child_order"


def child_order_key(bone):
    """Sort key of a bone (Bone or EditBone) among its siblings: Maya child order."""
    stamp = bone.get(CHILD_ORDER)
    if stamp is not None:
        return float(stamp)
    bones = bone.id_data.edit_bones if isinstance(bone, bpy.types.EditBone) else bone.id_data.bones
    try:
        return float(bones.find(bone.name))
    except (AttributeError, ReferenceError):
        return 0.0


def stamp_last(eb):
    """Mark edit bone / bone ``eb`` as its parent's newest child (Maya parent puts a re-parented node last)."""
    arm = eb.id_data
    bones = arm.edit_bones if arm.is_editmode else arm.bones
    used = [float(b.get(CHILD_ORDER)) for b in bones if b.get(CHILD_ORDER) is not None]
    eb[CHILD_ORDER] = max([len(bones)] + used) + 1.0


def _by_name(bones):
    """Siblings in Maya child order (the name is historical: it used to sort by name)."""
    return sorted(bones, key=child_order_key)


def _wrap(sibs, bone, direction):
    names = [b.name for b in sibs]
    if len(sibs) < 2 or bone.name not in names:
        return bone
    return sibs[(names.index(bone.name) + (1 if direction == "RIGHT" else -1)) % len(sibs)]


def collection_hidden(bone):
    """The bone is in bone collections and none of them is shown (a bone in no collection is always shown)."""
    cols = bone.collections
    return len(cols) > 0 and not any(c.is_visible_effectively for c in cols)


def has_controllers(arm):
    """The armature data has kit controller tags (Control > Tag As Controller / Parent Controller)."""
    return any(b.get(CONTROLLER) for b in arm.bones)


def controller_parent(bone):
    name = bone.get(CONTROLLER_PARENT)
    return bone.id_data.bones.get(name) if name else None


def controller_children(bone):
    return _by_name(b for b in bone.id_data.bones if b.get(CONTROLLER_PARENT) == bone.name)


def _dag_walk(bone, direction):
    if direction == "UP":
        return bone.parent or bone
    if direction == "DOWN":
        kids = _by_name(bone.children)
        return kids[0] if kids else bone
    sibs = bone.parent.children if bone.parent else [b for b in bone.id_data.bones if b.parent is None]
    return _wrap(_by_name(sibs), bone, direction)


def _controller_walk(bone, direction):
    """Maya's controller rule: the controller hierarchy where it is set, else the DAG."""
    up = controller_parent(bone)
    if direction == "UP":
        return up or bone.parent or bone
    if direction == "DOWN":
        kids = controller_children(bone)
        return kids[0] if kids else _dag_walk(bone, "DOWN")
    if up is not None:
        return _wrap(controller_children(up), bone, direction)
    return _dag_walk(bone, direction)


def visible_ancestor(bone):
    """Nearest ancestor not hidden by its bone collections, or None."""
    p = bone.parent
    while p is not None and collection_hidden(p):
        p = p.parent
    return p


def visible_below(bones):
    """Nearest descendants not hidden by collections under ``bones`` (depth-first, each level sorted by name)."""
    out = []
    for b in _by_name(bones):
        if collection_hidden(b):
            out.extend(visible_below(b.children))
        else:
            out.append(b)
    return out


def _visible_walk(bone, direction):
    if direction == "UP":
        return visible_ancestor(bone) or bone
    if direction == "DOWN":
        kids = visible_below(bone.children)
        return kids[0] if kids else bone
    up = visible_ancestor(bone)
    sibs = visible_below(up.children if up is not None
                         else [b for b in bone.id_data.bones if b.parent is None])
    if bone.name not in {b.name for b in sibs}:      # the bone itself is hidden by a collection
        return _dag_walk(bone, direction)
    return _wrap(sibs, bone, direction)


# Issue #145: in a Rigify rig 63 % of the controls hang on hidden MCH
# bones, so the nearest shown ancestor of upper_arm_fk.L is tweak_spine.003, not shoulder.L. The
# Rigify rule (ORG hierarchy projection): a generated rig (data property ``rig_id``) without kit tags gets
# controller parents computed from its ORG bones (never stored, so Tag / Parent Controller still win): control C ->
# its ORG twin (C's name without the variant word: upper_arm_fk.L -> ORG-upper_arm.L, tweak_spine.003 ->
# ORG-spine.003) -> up the ORG parents to the first one with a shown control twin, same variant first
# (upper_arm_fk.L -> shoulder.L, forearm_fk.L -> upper_arm_fk.L, tweak_spine.003 -> tweak_spine.002). Controls with no
# ORG twin (torso, chest, hand_ik.L ...) keep the shown-ancestor rule.
_VARIANTS = ("_fk", "_ik", "_tweak", "_master", "_parent")
_RIGIFY_MAPS = {}


def is_rigify_rig(arm):
    return bool(arm.get("rig_id")) and any(b.name.startswith("ORG-") for b in arm.bones)


_VARIANT_RE = re.compile(r"(_fk|_ik|_tweak|_master|_parent)(?=\.|$)")


def _split_variant(name):
    """(ORG base name, variant) of a Rigify control name: upper_arm_fk.L -> (upper_arm.L, '_fk'),
    f_index.01_master.L -> (f_index.01.L, '_master'), tweak_spine.003 -> (spine.003, 'tweak_')."""
    if name.startswith("tweak_"):
        return name[len("tweak_"):], "tweak_"
    m = _VARIANT_RE.search(name)
    if m is None:
        return name, ""
    return name[:m.start()] + name[m.end():], m.group(1)


def _with_variant(base, v):
    if v == "tweak_":
        return ["tweak_" + base]
    cuts = [i for i, ch in enumerate(base) if ch == "."] + [len(base)]
    return [base[:i] + v + base[i:] for i in cuts]


def _twin_names(base, variant):
    """Control names for ORG base ``base``: the same variant first, then the plain name, then the others."""
    out = _with_variant(base, variant) if variant else []
    out.append(base)
    for v in (*_VARIANTS, "tweak_"):
        if v != variant:
            out += _with_variant(base, v)
    return out


def rigify_parents(arm):
    """{control name: controller parent name or None} of a Rigify rig (shown controls only; cached per state)."""
    shown = {b.name for b in arm.bones if not collection_hidden(b) and not b.name.startswith(("ORG-", "MCH-", "DEF-"))}
    key = (hash(tuple(b.name for b in arm.bones)),
           tuple(sorted(c.name for c in arm.collections_all if c.is_visible_effectively)))
    got = _RIGIFY_MAPS.get(arm.name)
    if got is not None and got[0] == key:
        return got[1]
    bones = arm.bones
    out = {}
    for name in shown:
        base, variant = _split_variant(name)
        org = bones.get("ORG-" + base)
        parent = None
        p = org.parent if org is not None else None
        while p is not None and parent is None:
            if p.name.startswith("ORG-"):
                parent = next((n for n in _twin_names(p.name[4:], variant) if n in shown and n != name), None)
            p = p.parent
        if parent is None:
            up = visible_ancestor(bones[name])
            parent = up.name if up is not None else None
        out[name] = parent
    for name in list(out):                      # a loop (not expected) makes that control a root
        seen, cur = set(), name
        while cur is not None and cur not in seen:
            seen.add(cur)
            cur = out.get(cur)
        if cur is not None:
            out[name] = None
    _RIGIFY_MAPS[arm.name] = (key, out)
    return out


def _mapped_walk(bone, direction, parents):
    bones = bone.id_data.bones
    if bone.name not in parents:                    # a hidden helper selected by hand: plain DAG
        return _dag_walk(bone, direction)
    up = parents[bone.name]
    if direction == "UP":
        return bones[up] if up is not None else bone
    if direction == "DOWN":
        kids = _by_name(bones[n] for n, p in parents.items() if p == bone.name)
        return kids[0] if kids else bone
    sibs = _by_name(bones[n] for n, p in parents.items() if p == up)
    return _wrap(sibs, bone, direction)


def walk_bone(bone, direction, skip_hidden=False):
    """Bone reached from ``bone`` (data Bone) by a Maya arrow key (Up / Down / Left / Right, siblings wrap).

    Controller-tagged armature = the controller rule; else ``skip_hidden`` (the preference) walks a Rigify rig's
    controls by its ORG hierarchy and other armatures past bones hidden by their bone collections; else
    the plain DAG (parent, first child by name, siblings by name)."""
    if has_controllers(bone.id_data):
        return _controller_walk(bone, direction)
    if skip_hidden and is_rigify_rig(bone.id_data):
        return _mapped_walk(bone, direction, rigify_parents(bone.id_data))
    if skip_hidden:
        return _visible_walk(bone, direction)
    return _dag_walk(bone, direction)


def _skip_hidden_pref(context):
    from .. import preferences
    try:
        return preferences.get(context).pick_walk_skip_hidden_collections
    except (KeyError, AttributeError):
        return True


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_pick_walk_joint(bpy.types.Operator):
    """Walk the joint selection through the skeleton (Maya arrow keys)"""
    bl_idname = "allset.pick_walk_joint"
    bl_label = "Pick Walk Joint"
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(items=(("UP", "Up", ""), ("DOWN", "Down", ""), ("LEFT", "Left", ""),
                                   ("RIGHT", "Right", "")), name="Direction")

    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE' and _cb().lead(context) is not None

    def execute(self, context):
        cb = _cb()
        lead = cb.lead(context)
        skip = _skip_hidden_pref(context)
        picked = []
        for pb in cb.targets(context):
            to = walk_bone(pb.bone, self.direction, skip)
            key = (pb.id_data.name, to.name)
            if key not in picked:
                picked.append(key)
        for arm in cb.pose_objects(context):
            for pb in arm.pose.bones:
                cb.set_bone_selected(pb, False)
        for arm_name, bone_name in picked:
            cb.set_bone_selected(bpy.data.objects[arm_name].pose.bones[bone_name], True)
        if lead is not None:
            lead.id_data.data.bones.active = walk_bone(lead.bone, self.direction, skip)
        return {'FINISHED'}


def parent_joints(ob, names, parent_name):
    """Parent the joints to ``parent_name`` keeping where they are (Maya P); None = unparent."""
    n = 0
    with _InEditMode(ob) as ebs:
        parent = ebs.get(parent_name) if parent_name else None
        for name in names:
            eb = ebs.get(name)
            if eb is None or eb is parent:
                continue
            if parent is not None and (parent == eb or eb in parent.parent_recursive):
                continue                                       # would make a loop
            eb.use_connect = False
            eb.parent = parent
            stamp_last(eb)
            n += 1
    return n


class ALLSET_OT_parent_joint(bpy.types.Operator):
    """Parent the selected joints to the last selected one, keeping their place (Maya P)"""
    bl_idname = "allset.parent_joint"
    bl_label = "Parent Joints"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _armature(context) is not None

    def execute(self, context):
        ob = _armature(context)
        active = active_joint_name(ob)
        names = [n for n in selected_joint_names(ob) if n != active]
        if active is None or not names:
            self.report({'WARNING'}, "Select the child joints, then the parent joint last")
            return {'CANCELLED'}
        results.result(self, f"Parented {parent_joints(ob, names, active)} joint(s) to {active}")
        return {'FINISHED'}


class ALLSET_OT_unparent_joint(bpy.types.Operator):
    """Unparent the selected joints, keeping their place (Maya Shift+P)"""
    bl_idname = "allset.unparent_joint"
    bl_label = "Unparent Joints"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _armature(context) is not None

    def execute(self, context):
        ob = _armature(context)
        n = parent_joints(ob, selected_joint_names(ob), None)
        results.result(self, f"Unparented {n} joint(s)")
        return {'FINISHED'}


classes = (ALLSET_OT_joint_tool, ALLSET_OT_orient_joint, ALLSET_OT_mirror_joints, ALLSET_OT_pick_walk_joint,
           ALLSET_OT_parent_joint, ALLSET_OT_unparent_joint)
