# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Modify > Align: Snap Align Objects, Snap Together Tool, Make Live, Match
Transformations.

Maya:

- S9 Point to Point: the object owning the first point moves (no rotation) so that point
  lands on the last one.
- S10/S11 2 / 3 Points to 2 / 3 Points: move + rotate so the points line up (first on first,
  the rest give the direction / plane).
- S11 Align Objects (default options): world X only, mid, to the average.
- S12 Snap Together Tool: click a surface point on the object to move, then a point on the
  target: the object moves there and turns so the two normals face each other.
- S13 Make Live: a live surface the moves snap onto; "No Live Surface" in the Status Line.

Points: in object mode the pivots (Blender origins) of the selected objects, the active
one (Maya's last selected) being the target; in mesh edit mode each mesh's selected
vertices in selection order (``select_history``), the active object's being the target.
"""

import math

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector

from .. import results

EPS = 1e-9


# --- maths (bpy-free apart from mathutils) -------------------------------------------------------

def _frame(points):
    """Orthonormal frame (3x3, columns) of 2 or 3 points: X along p0->p1, Z = plane normal."""
    x = points[1] - points[0]
    if x.length < EPS:
        return None
    x = x.normalized()
    if len(points) > 2:
        z = x.cross(points[2] - points[0])
        if z.length < EPS:
            z = None
        else:
            z = z.normalized()
    else:
        z = None
    if z is None:
        helper = Vector((0, 0, 1)) if abs(x.z) < 0.9 else Vector((0, 1, 0))
        z = x.cross(helper).cross(x).normalized()
        z = -z if z.dot(helper) < 0 else z
    y = z.cross(x).normalized()
    return Matrix((x, y, z)).transposed()


def points_transform(src, dst):
    """World matrix that takes ``src`` points onto ``dst`` (1: move, 2: move + aim, 3: + plane)."""
    n = min(len(src), len(dst))
    if n == 0:
        return Matrix.Identity(4)
    if n == 1:
        return Matrix.Translation(dst[0] - src[0])
    fs, fd = _frame(src[:n]), _frame(dst[:n])
    if fs is None or fd is None:
        return Matrix.Translation(dst[0] - src[0])
    if n == 2:
        # 2 points: only turn the p0->p1 direction onto the target direction (shortest arc)
        a = (src[1] - src[0]).normalized()
        b = (dst[1] - dst[0]).normalized()
        rot = a.rotation_difference(b).to_matrix()
    else:
        rot = fd @ fs.transposed()
    m = rot.to_4x4()
    return Matrix.Translation(dst[0]) @ m @ Matrix.Translation(-src[0])


def bbox_world(ob):
    corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = Vector(tuple(min(c[i] for c in corners) for i in range(3)))
    hi = Vector(tuple(max(c[i] for c in corners) for i in range(3)))
    return lo, hi


# --- selections ---------------------------------------------------------------------------------

def _ordered_verts(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    hist = [e for e in bm.select_history if isinstance(e, bmesh.types.BMVert)]
    rest = [v for v in bm.verts if v.select and v not in hist]
    return [ob.matrix_world @ v.co for v in hist + rest]


def point_sets(context):
    """(movers [(object, points)], target points) or None."""
    active = context.view_layer.objects.active
    if context.mode == 'EDIT_MESH':
        obs = [ob for ob in context.objects_in_mode_unique_data if ob.type == 'MESH']
        target = [ob for ob in obs if ob == active]
        movers = [ob for ob in obs if ob != active]
        if not target or not movers:
            return None
        return [(ob, _ordered_verts(ob)) for ob in movers], _ordered_verts(target[0])
    sel = [ob for ob in context.selected_objects]
    if active is None or active not in sel or len(sel) < 2:
        return None
    return ([(ob, [ob.matrix_world.translation.copy()]) for ob in sel if ob != active],
            [active.matrix_world.translation.copy()])


def snap_points(context, count):
    """Snap Align Objects > Point to Point / 2 Points / 3 Points. Returns the moved count."""
    sets = point_sets(context)
    if sets is None:
        return 0
    movers, target = sets
    done = 0
    for ob, pts in movers:
        n = min(count, len(pts), len(target))
        if n == 0:
            continue
        m = points_transform(pts[:n], target[:n])
        if ob.parent is None or ob.parent not in [o for o, _p in movers]:
            ob.matrix_world = m @ ob.matrix_world
            done += 1
    return done


def align_objects(context, axes=(True, False, False), mode='MID'):
    """Snap Align Objects > Align Objects with the default options (like Maya, S11): along world
    ``axes``, the bounding boxes' min / mid / max lined up at their average."""
    obs = list(context.selected_objects)
    if len(obs) < 2:
        return 0
    boxes = {ob: bbox_world(ob) for ob in obs}

    def key(bb, i):
        lo, hi = bb
        return lo[i] if mode == 'MIN' else hi[i] if mode == 'MAX' else (lo[i] + hi[i]) / 2

    for i, on in enumerate(axes):
        if not on:
            continue
        avg = sum(key(bb, i) for bb in boxes.values()) / len(obs)
        for ob, bb in boxes.items():
            d = Vector((0, 0, 0))
            d[i] = avg - key(bb, i)
            ob.matrix_world = Matrix.Translation(d) @ ob.matrix_world
    return len(obs)


# --- Match Transformations ------------------------------------------------------------------------

# A joint's Maya X / Y / Z = the bone's Y / Z / X, an object's Maya X / Y / Z = Blender X / Z / -Y,
# so an object lined up with a joint's Maya axes has world = bone world @ Rz(+90) (control shapes use the same turn).
_BONE_TO_OBJECT = Matrix.Rotation(math.pi / 2, 4, 'Z')


def _maya_frame(node):
    """World matrix of ``node`` (Object / PoseBone) in an object's axis convention (Maya Match compares Maya axes)."""
    if isinstance(node, bpy.types.PoseBone):
        return node.id_data.matrix_world @ node.matrix @ _BONE_TO_OBJECT
    return node.matrix_world.copy()


def _set_maya_frame(node, m):
    if isinstance(node, bpy.types.PoseBone):
        node.matrix = node.id_data.matrix_world.inverted_safe() @ m @ _BONE_TO_OBJECT.inverted()
    else:
        node.matrix_world = m


def match_lead(context):
    """(lead, others) of Maya Match Transformations: the last selected node is the lead. A joint lead = the active pose
    bone in pose mode (picking a joint enters Pose mode, the objects picked before stay selected), or the
    active bone of an active armature in object mode."""
    lead = context.view_layer.objects.active
    if lead is None:
        return None, []
    others = [ob for ob in context.selected_objects if ob is not lead]
    if lead.type == 'ARMATURE' and lead.pose is not None:
        pb = None
        if lead.mode == 'POSE':
            pb = context.active_pose_bone
            others += [b for b in (context.selected_pose_bones or ()) if b != pb and b.id_data == lead]
        elif lead.data.bones.active is not None:
            pb = lead.pose.bones.get(lead.data.bones.active.name)
        if pb is not None:
            return pb, others
    return lead, others


def match_transform(context, translate=True, rotate=True, scale=True):
    lead, others = match_lead(context)
    if lead is None or not others:
        return 0
    lt, lr, ls = _maya_frame(lead).decompose()
    for node in others:
        t, r, s = _maya_frame(node).decompose()
        _set_maya_frame(node, Matrix.LocRotScale(lt if translate else t, lr if rotate else r, ls if scale else s))
        if isinstance(node, bpy.types.PoseBone):
            context.view_layer.update()      # the next bone's frame may hang below this one
    return len(others)


class _ObjOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in ('OBJECT', 'EDIT_MESH')


class ALLSET_OT_snap_points(_ObjOp, bpy.types.Operator):
    """Move (and turn) the first selected object so its points land on the last selected
    object's points (Maya Modify > Snap Align Objects > Point to Point / 2 / 3 Points)"""
    bl_idname = "allset.snap_points"
    bl_label = "Snap Points"

    count: IntProperty(name="Points", default=1, min=1, max=3)

    @classmethod
    def description(cls, context, props):
        return {1: "Point to Point: move the object so its point lands on the target point",
                2: "2 Points to 2 Points: move and turn so two points line up",
                3: "3 Points to 3 Points: move and turn so three points line up"}[props.count]

    def execute(self, context):
        n = snap_points(context, self.count)
        if not n:
            self.report({'WARNING'}, "Select points on the object to move, then on the target (last)")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_align_objects(bpy.types.Operator):
    """Line the selected objects up along world X at the middle of their bounding boxes
    (Maya Modify > Snap Align Objects > Align Objects, factory options)"""
    bl_idname = "allset.align_objects"
    bl_label = "Align Objects"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name="Align Mode", items=(('MIN', "Min", ""), ('MID', "Mid", ""), ('MAX', "Max", "")),
                       default='MID')
    axis_x: BoolProperty(name="World X", default=True)
    axis_y: BoolProperty(name="World Y", default=False)
    axis_z: BoolProperty(name="World Z", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        if not align_objects(context, (self.axis_x, self.axis_y, self.axis_z), self.mode):
            self.report({'WARNING'}, "Select two or more objects")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_match_transform(bpy.types.Operator):
    """Match the transforms of the selected objects to the last selected one
    (Maya Modify > Match Transformations)"""
    bl_idname = "allset.match_transform"
    bl_label = "Match Transformations"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(items=(('ALL', "All Transforms", ""), ('TRANSLATE', "Translation", ""),
                              ('ROTATE', "Rotation", ""), ('SCALE', "Scaling", "")), default='ALL')

    @classmethod
    def poll(cls, context):
        return context.mode in ('OBJECT', 'POSE')

    def execute(self, context):
        k = self.kind
        n = match_transform(context, k in ('ALL', 'TRANSLATE'), k in ('ALL', 'ROTATE'), k in ('ALL', 'SCALE'))
        if not n:
            self.report({'WARNING'}, "Select the objects, then the target last")
            return {'CANCELLED'}
        return {'FINISHED'}


# --- Make Live (S13) ------------------------------------------------------------------------------

def make_live(context, ob):
    from . import live
    live.set_objects(context.scene, [ob] if ob else [])


class ALLSET_OT_make_live(bpy.types.Operator):
    """Make the selected surface live: moves snap onto it. With nothing selected the live
    surface is cleared (Maya Modify > Make Live)"""
    bl_idname = "allset.make_live"
    bl_label = "Make Live"
    bl_options = {'REGISTER', 'UNDO'}

    toggle: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'},
                                   description="Status Line magnet: while something is live, turn Make Live off")

    @classmethod
    def poll(cls, context):
        from . import live
        return context.mode == 'OBJECT' or (context.mode == 'EDIT_MESH' and bool(live.objects(context.scene)))

    def invoke(self, context, event):
        if event.type == 'MIDDLEMOUSE':
            return bpy.ops.allset.live_list('EXEC_DEFAULT', False, action='RECENT')
        return self.execute(context)

    def execute(self, context):
        from . import live
        targets = live.selected(context) if context.mode == 'OBJECT' else []
        if self.toggle and live.objects(context.scene):
            targets = []                # Maya's Status Line magnet turns Make Live off whatever is selected
        try:
            live.set_objects(context.scene, targets)
        except ValueError as ex:
            self.report({'WARNING'}, str(ex))
            return {'CANCELLED'}
        label = live.text(context.scene)
        results.result(self, f"Live surface: {label}" if targets else "No Live Surface")
        from ..ui import view_message
        # Maya's Make Live message (topCenter).
        view_message.show(context, f"{label} is <hl>live</hl>." if targets else "Make Live is <hl>off</hl>.",
                          'TOP_CENTER')
        return {'FINISHED'}


# --- Snap Together Tool (S12) ------------------------------------------------------------------

def surface_hit(context, region, rv3d, coord):
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    depsgraph = context.evaluated_depsgraph_get()
    ok, loc, normal, _i, ob, _m = context.scene.ray_cast(depsgraph, origin, direction)
    if not ok:
        return None
    return ob.original if hasattr(ob, "original") else ob, loc, normal.normalized()


def snap_together_matrix(src_point, src_normal, dst_point, dst_normal, orient=True):
    """World matrix that puts ``src_point`` on ``dst_point`` with the normals facing each other."""
    if not orient:
        return Matrix.Translation(dst_point - src_point)
    rot = src_normal.rotation_difference(-dst_normal).to_matrix().to_4x4()
    return Matrix.Translation(dst_point) @ rot @ Matrix.Translation(-src_point)


class ALLSET_OT_snap_together(bpy.types.Operator):
    """Click a point on the object to move, then a point on the target: the object moves
    there and turns so the surfaces face each other (Maya Modify > Snap Together Tool)"""
    bl_idname = "allset.snap_together"
    bl_label = "Snap Together Tool"
    bl_options = {'UNDO'}

    set_orientation: BoolProperty(name="Set Orientation", default=True)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def _view(self, context, event):
        for area in context.window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for region in area.regions:
                if (region.type == 'WINDOW' and region.x <= event.mouse_x < region.x + region.width
                        and region.y <= event.mouse_y < region.y + region.height):
                    return area, region, region.data
        return None, None, None

    def invoke(self, context, event):
        self._first = None
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Snap Together Tool: click a point on the object to move "
                                          "(Esc / right-click: cancel)")
        return {'RUNNING_MODAL'}

    def _end(self, context):
        context.workspace.status_text_set(None)

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._end(context)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            area, region, rv3d = self._view(context, event)
            if region is None or rv3d is None:
                return {'PASS_THROUGH'}
            coord = (event.mouse_x - region.x, event.mouse_y - region.y)
            hit = surface_hit(context, region, rv3d, coord)
            if hit is None:
                return {'RUNNING_MODAL'}
            if self._first is None:
                self._first = hit
                context.workspace.status_text_set(f"Snap Together Tool: now click the target point "
                                                  f"(moving {hit[0].name})")
                return {'RUNNING_MODAL'}
            ob, p0, n0 = self._first
            _ob1, p1, n1 = hit
            m = snap_together_matrix(p0, n0, p1, n1, self.set_orientation)
            ob.matrix_world = m @ ob.matrix_world
            self._end(context)
            return {'FINISHED'}
        return {'PASS_THROUGH'} if event.type.startswith(('WHEEL', 'MIDDLEMOUSE', 'MOUSEMOVE', 'TRACKPAD')) \
            or event.alt else {'RUNNING_MODAL'}


classes = (ALLSET_OT_snap_points, ALLSET_OT_align_objects, ALLSET_OT_match_transform,
           ALLSET_OT_make_live, ALLSET_OT_snap_together)


def register_props():
    from . import live
    bpy.types.Scene.allset_live = PointerProperty(
        type=bpy.types.Object, name="Live Surface",
        description="First live surface (legacy script compatibility)", update=live.compatibility_changed)
    live.register()


def unregister_props():
    from . import live
    live.unregister()
    del bpy.types.Scene.allset_live


# --- Step Snap (Move/Rotate/Scale tool option, S3) -----------------------------------------------

STEP_FLAGS = {'TRANSLATE': "use_snap_translate", 'ROTATE': "use_snap_rotate", 'RESIZE': "use_snap_scale"}
MAYA_ROTATE_STEP = 0.2617993877991494      # 15 degrees (Rotate tool snapValue, S3)


# Issue #139: Blender's use_snap_translate / rotate / scale ("Affect") switch *all* snapping off for that
# transform, not only the increment. Step Snap Off used to clear use_snap_translate, so Snap to Grid / Points on the
# Status Line looked on but Move never snapped. The kit now keeps its per-tool Step Snap state in a scene ID property
# and leaves a transform's Affect flag on while any other snap mode (grid / curve / point / live) is on.
STEP_PROP = "allset_step_snap"
OTHER_SNAPS = ('GRID', 'VERTEX', 'EDGE', 'FACE', 'FACE_PROJECT', 'FACE_NEAREST', 'VOLUME', 'EDGE_MIDPOINT',
               'EDGE_PERPENDICULAR')


def _record(ts):
    scene = ts.id_data
    return dict(scene.get(STEP_PROP, {})) if scene is not None else {}


def _store(ts, rec):
    if ts.id_data is not None:
        ts.id_data[STEP_PROP] = rec


def step_snap_mode(ts, kind):
    """'OFF' / 'RELATIVE' / 'ABSOLUTE' for the tool ``kind`` (Maya Step Snap)."""
    if not (ts.use_snap and 'INCREMENT' in ts.snap_elements and getattr(ts, STEP_FLAGS[kind])):
        return 'OFF'
    own = _record(ts).get(kind)
    if own in ('OFF', 'RELATIVE', 'ABSOLUTE'):
        return own
    return 'ABSOLUTE' if ts.use_snap_grid_absolute else 'RELATIVE'


# Issue #153: Maya keeps Relative / Absolute per tool (Move / Rotate /
# Scale tool snapRelative), Blender has one Absolute Grid Snap flag
# for every transform. The kit keeps each tool's mode in STEP_PROP and puts it into Blender's flag when a transform
# of that tool can start: the tool becomes active (tool_keys._watch), an LMB press on the manipulator
# (manip.ALLSET_OT_manip_press), an MMB drag (manip_mmb), and when the user picks the mode of the active tool.
TOOL_KINDS = {"builtin.move": 'TRANSLATE', "builtin.rotate": 'ROTATE', "builtin.scale": 'RESIZE'}


def absolute_offered(scene, kind):
    """Maya offers Move's Absolute step snap only while its axis orientation is World (Move Tool Settings);
    Rotate and Scale always offer it."""
    if kind != 'TRANSLATE':
        return True
    from ..ui import manipulator
    return manipulator.slot_type(scene, kind) == 'GLOBAL'


def apply_tool(ts, kind):
    """Blender's shared Absolute Grid Snap flag = the stored mode of tool ``kind`` (no change without one)."""
    if kind not in STEP_FLAGS:
        return False
    own = _record(ts).get(kind)
    if own not in ('RELATIVE', 'ABSOLUTE'):
        return False
    want = own == 'ABSOLUTE'
    if ts.use_snap_grid_absolute != want:
        ts.use_snap_grid_absolute = want
        return True
    return False


def active_kind(context):
    """'TRANSLATE' / 'ROTATE' / 'RESIZE' of the active 3D View tool, else None."""
    workspace = getattr(context, "workspace", None)
    if workspace is None:
        return None
    try:
        tool = workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except (AttributeError, RuntimeError, TypeError):
        return None
    return TOOL_KINDS.get(tool.idname) if tool is not None else None


def apply_active(context):
    kind = active_kind(context)
    return apply_tool(context.scene.tool_settings, kind) if kind and context.scene else False


def other_snaps_on(ts):
    """Any snap mode besides the increment step is on (grid / point / curve / live)."""
    return ts.use_snap and bool(set(ts.snap_elements) & set(OTHER_SNAPS))


def heal_affect(ts):
    """Turn the Move / Rotate / Scale Affect flags back on wherever Step Snap isn't the reason they are off: with
    a grid / point / curve snap on, Blender would otherwise ignore it for that transform (#139)."""
    if not other_snaps_on(ts):
        return 0
    n = 0
    for kind, flag in STEP_FLAGS.items():
        if not getattr(ts, flag):
            setattr(ts, flag, True)
            n += 1
    return n


def settle_affect(ts):
    """After the Status Line snap set changed: with a grid / point / curve snap on, every Affect flag is on (#139);
    with none left, a tool whose Step Snap the user turned Off gets its Affect flag back off — otherwise it kept
    stepping by another tool's increment while showing Off."""
    if other_snaps_on(ts):
        return heal_affect(ts)
    n = 0
    for kind, mode in _record(ts).items():
        flag = STEP_FLAGS.get(kind)
        if mode == 'OFF' and flag and getattr(ts, flag):
            setattr(ts, flag, False)
            n += 1
    return n


def set_step_snap(ts, kind, mode):
    if mode == 'TOGGLE':
        mode = 'OFF' if step_snap_mode(ts, kind) != 'OFF' else 'RELATIVE'
    rec = _record(ts)
    rec[kind] = mode
    _store(ts, rec)
    if mode == 'OFF':
        # tools whose Step Snap the user turned on (Blender's Affect flags are on by default for all three)
        stepping = [k for k in STEP_FLAGS if k != kind and rec.get(k) in ('RELATIVE', 'ABSOLUTE')
                    and step_snap_mode(ts, k) != 'OFF']
        elements = set(ts.snap_elements) if ts.use_snap else set()
        if not stepping:
            elements.discard('INCREMENT')
        # the Affect flag stays on while a grid / point / curve snap is on: it would switch those off too
        setattr(ts, STEP_FLAGS[kind], bool(elements - {'INCREMENT'}))
        if elements:
            ts.snap_elements = elements
        else:
            ts.use_snap = False
        return 'OFF'
    # #153: the other tools keep their own Step Snap — one never set stays Off instead of following
    # Blender's shared increment snap (Maya: a tool context's -snap is its own)
    was_snapping = ts.use_snap and 'INCREMENT' in ts.snap_elements
    for other, flag in STEP_FLAGS.items():
        if other == kind or rec.get(other) in ('RELATIVE', 'ABSOLUTE', 'OFF'):
            continue
        if was_snapping and getattr(ts, flag):
            rec[other] = 'ABSOLUTE' if ts.use_snap_grid_absolute else 'RELATIVE'   # what it showed: keep it
            continue
        rec[other] = 'OFF'
        if not other_snaps_on(ts):
            setattr(ts, flag, False)
    _store(ts, rec)
    ts.snap_elements = set(ts.snap_elements if ts.use_snap else ()) | {'INCREMENT'}
    ts.use_snap = True
    setattr(ts, STEP_FLAGS[kind], True)
    # this tool's own mode; Blender's shared flag follows it until another tool's transform starts
    ts.use_snap_grid_absolute = mode == 'ABSOLUTE'
    if kind == 'ROTATE' and abs(ts.snap_angle_increment_3d - 0.0872664600610733) < 1e-6:
        ts.snap_angle_increment_3d = MAYA_ROTATE_STEP     # Blender's 5 degrees -> the kit's 15
    return mode


class ALLSET_OT_step_snap(bpy.types.Operator):
    """Maya Step Snap of the Move / Rotate / Scale tool: off, relative to the start, or to
    absolute steps (Discrete Move / Rotate / Snap Scale)"""
    bl_idname = "allset.step_snap"
    bl_label = "Step Snap"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(items=(('TRANSLATE', "Move", ""), ('ROTATE', "Rotate", ""), ('RESIZE', "Scale", "")))
    mode: EnumProperty(items=(('OFF', "Off", ""), ('RELATIVE', "Relative", ""), ('ABSOLUTE', "Absolute", ""),
                              ('TOGGLE', "Toggle", "")))

    def execute(self, context):
        got = set_step_snap(context.scene.tool_settings, self.kind, self.mode)
        results.result(self, f"Step snap {got.lower()}")
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()
        return {'FINISHED'}


classes += (ALLSET_OT_step_snap,)
