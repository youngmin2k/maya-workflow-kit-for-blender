# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Scale manipulator drag (#200): the centre handle and the axis handles.

Maya:

- Centre handle (uniform scale): ``f = 1 + dx · wpp / R``. ``dx`` = horizontal mouse movement since the press
  (vertical movement does nothing), ``wpp`` = world length of one region pixel at the manipulator pivot's depth,
  ``R`` = distance from the pivot to the farthest corner of the world axis-aligned bounding box of the lead
  object's geometry (object mode) or of the selected components. Moving right by R on screen doubles the scale;
  moving left by R reaches 0 and further left goes negative (no clamp, no dead zone). Every selected node gets
  the same factor; where the press lands inside the handle and the manipulator size don't matter.
- Axis handle: ``f = 1 + d · D_tip / (L · D0)`` on that axis only. ``d`` = movement along the handle's screen
  direction, ``L`` = the handle's screen length (90 px at UI scale 1 and the default manipulator size, whatever the
  camera distance or the object size), ``D0`` / ``D_tip`` = view depth of the pivot / of the handle tip (a handle
  pointing toward the camera is a little less sensitive; equal in front / side views).
- Plane handle: both plane axes by ``f = 1 + d · D_Q / (0.44 · L · D0)``, ``d`` = movement along the screen
  direction of the point ``Q`` 0.44 handle lengths out on the plane's diagonal.
- Ctrl at the press on an axis handle scales the other two axes by that handle's factor; Ctrl on the centre or a
  plane handle changes nothing; Shift duplicates first (Smart Duplicate, step 22). Keys pressed during the drag
  change nothing, and nothing slows down or snaps the drag.
- MMB drag anywhere with an axis / plane as the active handle: the same at half speed; with the centre: the same.
- Object mode: every selected object scales about its own pivot; ``R`` includes the lead's children.
- A move whose factor lands within 1e-5 of 0 is skipped (the previous value stays), so a drag never writes a scale
  of exactly 0; a channel that already was 0 becomes 1e-12.

Blender's ``transform.resize`` scales by the ratio of the mouse's and the press point's distances to the pivot, so a
press on the centre handle (a few px from the pivot) made every px multiply the scale and shrinking near 0 was out
of reach. ``allset.manip_scale`` computes Maya's factor and runs ``transform.resize`` EXEC with it: on each move
after putting back the state saved at the press (no undo, not registered), and once more on release with
``undo=True`` — one undo step, and the registered resize keeps what the active handle (step 28) and the Smart
Duplicate / Extrude watcher (step 22 / 26) read. So Blender's pivot point, orientation, proportional editing and
mesh symmetry apply exactly as in its own resize.
"""

import math

import bpy

# bl_idname of the modal, for code that waits while a transform runs (it is a transform without the TRANSFORM_OT_
# prefix).
MODAL_ID = "ALLSET_OT_manip_scale"
# Modal transforms: Blender's and the kit's own drags (manipulator scale, pivot edit, component scale, live move).
TRANSFORM_MODALS = ("TRANSFORM_OT_", MODAL_ID, "ALLSET_OT_pivot_translate", "ALLSET_OT_pivot_rotate",
                    "ALLSET_OT_component_scale", "ALLSET_OT_live_translate")

MODES = (('CENTER', "Centre", "Uniform scale (centre handle)"),
         ('AXIS', "Axis", "Scale along one axis (axis handle)"),
         ('PLANE', "Plane", "Scale the two axes of a plane (plane handle)"))
PLANES = ('XY', 'YZ', 'XZ')
PLANE_REACH = 0.44       # the plane handle's anchor on its diagonal, in axis handle lengths
MMB_SLOWER = 2.0         # MMB drag anywhere: axis / plane handles at half speed
ZERO_BAND = 1e-5         # a factor this close to 0 is skipped
ZERO_SCALE = 1e-12       # what a scale channel that was 0 becomes
AXIS_PX = 90.0           # Maya's axis handle length per unit of scale change at UI scale 1, default size
GIZMO_SIZE_DEFAULT = 75  # Blender's default gizmo size (the kit's equivalent of the default manipulator size in Maya)
STEP = 0.1               # Blender's increment for scale snapping
FALLBACK_R_PX = 100.0    # a selection with no extent (one vertex): 100 px on screen per unit
TINY = 1e-9
LAST = {}                # the last drag: press point (region px), wpp, R, axis length, factor (read by tests)


# --- maths (no bpy) ------------------------------------------------------------------------------------------

def uniform_factor(dx, wpp, radius):
    """Maya centre-handle factor for a horizontal drag of ``dx`` px."""
    return 1.0 + dx * wpp / radius


def axis_factor(d, length):
    """Maya axis-handle factor for a drag of ``d`` px along the handle (``length`` = px per unit of change)."""
    return 1.0 + d / length


def farthest_corner(pivot, lo, hi):
    """Distance from ``pivot`` to the farthest corner of the box ``lo`` .. ``hi``."""
    return math.sqrt(sum(max(abs(lo[i] - pivot[i]), abs(hi[i] - pivot[i])) ** 2 for i in range(3)))


def bounds(points):
    """(lo, hi) of 3D points, or None."""
    pts = list(points)
    if not pts:
        return None
    return (tuple(min(p[i] for p in pts) for i in range(3)), tuple(max(p[i] for p in pts) for i in range(3)))


def along(drag, screen_dir):
    """Signed length of ``drag`` along ``screen_dir``; a direction of no length (axis pointing at the viewer)
    counts the horizontal movement."""
    ln = math.hypot(screen_dir[0], screen_dir[1]) if screen_dir is not None else 0.0
    if ln < 1e-6:
        return float(drag[0])
    return (drag[0] * screen_dir[0] + drag[1] * screen_dir[1]) / ln


def axis_length_px(ui_scale, gizmo_size, size=1.0):
    """Screen length of one unit of axis scale change: 90 px at the default manipulator size, following
    Blender's gizmo size, the kit's = / - size and the UI scale."""
    return AXIS_PX * (ui_scale or 1.0) * gizmo_size / GIZMO_SIZE_DEFAULT * size


def quantise(f, step=STEP):
    return round(f / step) * step


def depth_axis_factor(d, length, depth0, depth_tip):
    """Maya axis / plane factor with the depth term: ``d`` px along the handle, ``length`` = screen px per unit of
    change at the pivot, ``depth0`` / ``depth_tip`` = view depths of the pivot / of the handle point."""
    if depth0 <= TINY or depth_tip <= TINY:
        return axis_factor(d, length)
    return 1.0 + d * depth_tip / (length * depth0)


def channels(mode, axis='X', plane='XY', others=False):
    """Which of X / Y / Z the drag scales."""
    if mode == 'AXIS':
        return tuple((a != axis) if others else (a == axis) for a in 'XYZ')
    if mode == 'PLANE':
        return tuple(a in plane for a in 'XYZ')
    return (True, True, True)


def value_of(mask, f):
    return tuple(f if m else 1.0 for m in mask)


def constraint_of(mask):
    return (False, False, False) if all(mask) else tuple(mask)


def skip_factor(f):
    """A factor Maya doesn't write (within ZERO_BAND of 0)."""
    return abs(f) < ZERO_BAND


# --- what the drag reads and what it puts back --------------------------------------------------------------------

def supported(context):
    """The kit drag runs in object mode and mesh edit mode; elsewhere (and with Blender options it can't put
    back) Blender's own resize runs, as before."""
    ts = context.scene.tool_settings
    if context.mode == 'OBJECT':
        if ts.use_transform_data_origin or ts.use_transform_skip_children or ts.use_transform_pivot_point_align:
            return False
        return any(ob.visible_get() for ob in context.selected_objects)
    if context.mode == 'EDIT_MESH':
        return True
    return False


def _other_snap(ts):
    from . import snap_align
    return ts.use_snap and getattr(ts, "use_snap_scale", True) and snap_align.other_snaps_on(ts)


def lead_object(context):
    active = context.view_layer.objects.active
    sel = [ob for ob in context.selected_objects if ob.visible_get()]
    if active is not None and active in sel:
        return active
    return sel[-1] if sel else None


def object_points(context, ob):
    """World points whose bounding box is the object's world bounding box (evaluated geometry)."""
    from mathutils import Vector
    deps = context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    mw = ev.matrix_world
    if ob.type == 'EMPTY':
        s = ob.empty_display_size
        return [mw @ Vector((x, y, z)) for x in (-s, s) for y in (-s, s) for z in (-s, s)]
    if ob.type == 'MESH':
        try:
            me = ev.to_mesh()
        except RuntimeError:
            me = None
        if me is not None:
            try:
                n = len(me.vertices)
                if n:
                    import numpy as np
                    co = np.empty(n * 3, dtype=np.float64)
                    me.vertices.foreach_get("co", co)
                    m = np.array(mw, dtype=np.float64)
                    world = co.reshape(n, 3) @ m[:3, :3].T + m[:3, 3]
                    # the two corners of the world box are enough for its bounds
                    return [Vector(world.min(axis=0)), Vector(world.max(axis=0))]
            finally:
                ev.to_mesh_clear()
    return [mw @ Vector(c) for c in ev.bound_box]


def radius(context, pivot):
    """Maya's R: pivot to the farthest corner of the world box of the lead object with its children / of the
    selected components."""
    if context.mode == 'EDIT_MESH':
        from ..ui import manipulator
        pts, _act = manipulator._edit_points(context)
    else:
        ob = lead_object(context)
        pts = []
        for o in ([ob] + list(ob.children_recursive)) if ob is not None else ():
            if o is ob or o.visible_get():
                pts.extend(object_points(context, o))
    box = bounds(pts)
    return farthest_corner(pivot, *box) if box is not None else 0.0


def world_per_pixel(region, rv3d, pivot):
    """World length of one region px at the depth of ``pivot``: a short step along the view's horizontal at the
    pivot, projected (persp: 2 depth tan(fov / 2) / width wherever the pivot is on screen; ortho: view width /
    width)."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    from mathutils import Vector
    right = rv3d.view_rotation @ Vector((1.0, 0.0, 0.0))
    eps = max(rv3d.view_distance, 1e-6) * 1e-3
    p0 = location_3d_to_region_2d(region, rv3d, pivot)
    p1 = location_3d_to_region_2d(region, rv3d, pivot + right * eps)
    if p0 is None or p1 is None:
        return None
    px = (p1 - p0).length
    return eps / px if px > 1e-9 else None


def screen_dir(region, rv3d, pivot, point):
    """Screen vector from ``pivot`` to ``point`` (region px), or None."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    p0 = location_3d_to_region_2d(region, rv3d, pivot)
    p1 = location_3d_to_region_2d(region, rv3d, point)
    if p0 is None or p1 is None:
        return None
    return (p1[0] - p0[0], p1[1] - p0[1])


def view_depth(rv3d, point):
    """Distance of ``point`` in front of the view along its axis; 1 in ortho views (no depth term there)."""
    if not rv3d.is_perspective:
        return 1.0
    return -(rv3d.view_matrix @ point).z


def _mirror_on(ob):
    me = ob.data
    return any(getattr(me, f"use_mirror_{a}", False) for a in "xyz")


def save_state(context):
    """State to put back before each preview: matrix_basis of the selected objects, or the coordinates of the
    (selected, or all with proportional editing / symmetry) vertices of every mesh in edit mode."""
    import bmesh
    if context.mode == 'OBJECT':
        return {'mode': 'OBJECT', 'objects': [(ob.name, ob.matrix_basis.copy()) for ob in context.selected_objects]}
    ts = context.scene.tool_settings
    meshes = []
    for ob in context.objects_in_mode_unique_data or ():
        if ob.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        every = ts.use_proportional_edit or _mirror_on(ob)
        coords = [(v.index, v.co.copy()) for v in bm.verts if every or v.select]
        meshes.append((ob.name, coords))
    return {'mode': 'EDIT_MESH', 'meshes': meshes}


def restore(state):
    import bmesh
    if state['mode'] == 'OBJECT':
        for name, m in state['objects']:
            ob = bpy.data.objects.get(name)
            if ob is not None:
                ob.matrix_basis = m
        return
    for name, coords in state['meshes']:
        ob = bpy.data.objects.get(name)
        if ob is None or ob.mode != 'EDIT':
            continue
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        n = len(bm.verts)
        for i, co in coords:
            if i < n:
                bm.verts[i].co = co
        bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)


class _Quiet:
    """Tool settings a preview must not act on (keys, merges, UVs it can't put back): off while a preview resize
    runs; the final call uses them."""
    NAMES = ("use_keyframe_insert_auto", "use_mesh_automerge", "use_transform_correct_face_attributes")

    def __init__(self, ts):
        self.ts, self.old = ts, {}

    def __enter__(self):
        for n in self.NAMES:
            if getattr(self.ts, n, False):
                self.old[n] = True
                setattr(self.ts, n, False)
        return self

    def __exit__(self, *_exc):
        for n, v in self.old.items():
            setattr(self.ts, n, v)
        return False


class _OwnPivots:
    """Object mode: each selected object scales about its own pivot (Maya), whatever Blender's pivot point: its
    location stays as it was (scaling about an object's own pivot never moves it). Blender's resize follows
    Individual Origins when it runs from a 3D View; without one (background) it scales about the median, so the
    locations are put back too."""

    def __init__(self, context):
        obj_mode = context.mode == 'OBJECT'
        self.obs = list(context.selected_objects) if obj_mode else []
        self.ts = context.scene.tool_settings if obj_mode else None
        self.locs, self.old = [], None

    def __enter__(self):
        self.locs = [ob.location.copy() for ob in self.obs]
        if self.ts is not None and self.ts.transform_pivot_point != 'INDIVIDUAL_ORIGINS':
            self.old = self.ts.transform_pivot_point
            self.ts.transform_pivot_point = 'INDIVIDUAL_ORIGINS'
        return self

    def __exit__(self, *_exc):
        if self.old is not None:
            self.ts.transform_pivot_point = self.old
        for ob, loc in zip(self.obs, self.locs):
            if ob.location != loc:
                ob.location = loc
        return False


def zero_channels(context):
    """{object name: indices of its scale channels that are 0} of the selected objects (object mode)."""
    if context.mode != 'OBJECT':
        return {}
    out = {}
    for ob in context.selected_objects:
        idx = tuple(i for i in range(3) if ob.scale[i] == 0.0)
        if idx:
            out[ob.name] = idx
    return out


def fix_zero(zeros, mask):
    """Maya: a dragged scale channel that was 0 becomes ZERO_SCALE."""
    for name, idx in zeros.items():
        ob = bpy.data.objects.get(name)
        if ob is None:
            continue
        for i in idx:
            if mask[i] and abs(ob.scale[i]) < ZERO_SCALE * 0.5:
                ob.scale[i] = ZERO_SCALE


def apply(context, f, mask=(True, True, True), orient_type='GLOBAL', final=False):
    """Scale the selection by ``f`` on the channels of ``mask`` with Blender's resize (from the state as it is
    now). ``final`` = the one call with an undo step that gets registered."""
    kwargs = {"value": value_of(mask, f), "constraint_axis": constraint_of(mask), "snap": False}
    if orient_type:
        kwargs["orient_type"] = orient_type
    if context.mode == 'EDIT_MESH':
        kwargs["mirror"] = True     # transform.* exec reads the mesh mirror flags only with mirror (step 36)
    if final:
        with _OwnPivots(context):
            res = bpy.ops.transform.resize('EXEC_DEFAULT', True, **kwargs)
        ops = context.window_manager.operators
        if 'FINISHED' in res and len(ops) and ops[-1].bl_idname == "TRANSFORM_OT_resize":
            # an EXEC resize registers all three axes whatever it was given: write the handle's constraint back,
            # which the active handle (manip.remember_last_op) and G repeat read
            ops[-1].properties.constraint_axis = kwargs["constraint_axis"]
        return res
    with _Quiet(context.scene.tool_settings), _OwnPivots(context):
        return bpy.ops.transform.resize('EXEC_DEFAULT', **kwargs)


def drag_factor(op, mx, my):
    """Factor for the mouse at region (mx, my) during the drag of ``op``'s settings."""
    dx, dy = mx - op._press[0], my - op._press[1]
    if op._mode in ('AXIS', 'PLANE'):
        f = depth_axis_factor(along((dx, dy), op._dir), op._len, op._depth0, op._depth_tip)
    else:
        f = uniform_factor(dx, op._wpp, op._radius)
    if op._snap:
        f = quantise(f)
    if getattr(op, "_clamp", False) and f < 0.0:
        f = 0.0                     # Prevent Negative Scale: a component scale stops flat at zero
    return f


class ALLSET_OT_manip_scale(bpy.types.Operator):
    """Drag the Scale manipulator the Maya way: the centre scales uniformly by the horizontal drag, an axis or
    plane handle by the drag along it"""
    bl_idname = "allset.manip_scale"
    bl_label = "Scale"
    # not REGISTER / UNDO: the final transform.resize call is the registered operator and the one undo step
    bl_options = {'INTERNAL', 'BLOCKING'}

    mode: bpy.props.EnumProperty(items=MODES, default='CENTER', options={'SKIP_SAVE'})
    axis: bpy.props.EnumProperty(items=[(a, a, "") for a in 'XYZ'], default='X', options={'SKIP_SAVE'})
    plane: bpy.props.EnumProperty(items=[(p, p, "") for p in PLANES], default='XY', options={'SKIP_SAVE'})
    others: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'},
                                   description="Ctrl on an axis handle: scale the other two axes")
    orient_type: bpy.props.StringProperty(default="", options={'SKIP_SAVE'})
    button: bpy.props.EnumProperty(items=(('LEFTMOUSE', "Left", ""), ('MIDDLEMOUSE', "Middle", "")),
                                   default='LEFTMOUSE', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def _mask(self):
        return channels(self.mode, self.axis, self.plane, self.others)

    def _fallback(self, context):
        kwargs = {"release_confirm": True}
        mask = self._mask()
        if not all(mask):
            kwargs["constraint_axis"] = constraint_of(mask)
        if self.orient_type:
            kwargs["orient_type"] = self.orient_type
        try:
            return bpy.ops.transform.resize('INVOKE_DEFAULT', **kwargs)
        except (RuntimeError, TypeError):
            return {'CANCELLED'}

    def _handle_dir(self, region, rv3d, center, frame, wpp):
        """(screen direction, view depth of the handle point) of the axis handle / the plane anchor."""
        reach = self._len * wpp                     # the handle's world length at the pivot's depth
        if self.mode == 'AXIS':
            point = center + frame.col['XYZ'.index(self.axis)].normalized() * reach
        else:
            a1, a2 = (frame.col['XYZ'.index(a)].normalized() for a in self.plane)
            point = center + (a1 + a2) * (PLANE_REACH * reach / math.sqrt(2.0))
        return screen_dir(region, rv3d, center, point), view_depth(rv3d, point)

    def invoke(self, context, event):
        from ..ui import manipulator
        region, rv3d = context.region, context.region_data
        if region is None or rv3d is None or not supported(context) or _other_snap(context.scene.tool_settings):
            return self._fallback(context)
        center, frame, otype = manipulator.pivot_frame(context, 'RESIZE')
        if center is None:
            return {'CANCELLED'}
        if not self.orient_type:
            self.orient_type = otype
        self._mode, self._channels = self.mode, self._mask()
        # Maya reads the centre drag at the lead's pivot (object mode: every object scales about its own)
        pivot = center
        if context.mode == 'OBJECT':
            lead = lead_object(context)
            if lead is not None:
                pivot = lead.matrix_world.translation.copy()
        wpp = world_per_pixel(region, rv3d, pivot)
        if not wpp:
            return self._fallback(context)
        self._wpp = wpp
        r = radius(context, pivot)
        self._radius = r if r > TINY else wpp * FALLBACK_R_PX
        prefs = context.preferences
        length = axis_length_px(prefs.system.ui_scale, prefs.view.gizmo_size, manipulator.SIZE[0])
        self._len = length
        self._dir, self._depth0, self._depth_tip = None, 1.0, 1.0
        if self.mode in ('AXIS', 'PLANE'):
            wpp_c = world_per_pixel(region, rv3d, center) or wpp      # the handles are drawn at the manipulator
            self._dir, self._depth_tip = self._handle_dir(region, rv3d, center, frame, wpp_c)
            self._depth0 = view_depth(rv3d, center)
            if self.mode == 'PLANE':
                self._len = length * PLANE_REACH
            if self.button == 'MIDDLEMOUSE':
                self._len *= MMB_SLOWER
        from . import snap_align
        self._snap = snap_align.step_snap_mode(context.scene.tool_settings, 'RESIZE') != 'OFF'
        from . import component_scale
        # Prevent Negative Scale: every handle (axis, Ctrl other axes, plane, centre) stops components at zero, so a
        # selection can be scaled flat or onto its pivot (Maya); object mode keeps negative scaling
        self._clamp = component_scale.enabled(context)
        # the press point: a drag event (gizmo) is handled once the mouse passed the drag threshold
        px, py = event.mouse_x, event.mouse_y
        if event.value == 'CLICK_DRAG':
            px, py = getattr(event, "mouse_prev_press_x", px), getattr(event, "mouse_prev_press_y", py)
        self._press = (px - region.x, py - region.y)
        self._state = save_state(context)
        self._zeros = zero_channels(context)
        self._f = 1.0
        self._region_xy = (region.x, region.y)
        LAST.clear()
        LAST.update(press=self._press, wpp=self._wpp, radius=self._radius, length=self._len, dir=self._dir,
                    depth0=self._depth0, depth_tip=self._depth_tip, mode=self._mode, channels=self._channels,
                    factor=1.0)
        context.window_manager.modal_handler_add(self)
        self._update(context, event)
        return {'RUNNING_MODAL'}

    def _update(self, context, event):
        f = drag_factor(self, event.mouse_x - self._region_xy[0], event.mouse_y - self._region_xy[1])
        if f == self._f or (skip_factor(f) and not (self._clamp and f == 0.0)):
            return
        self._f = LAST["factor"] = f
        restore(self._state)
        try:
            apply(context, f, self._channels, self.orient_type)
            fix_zero(self._zeros, self._channels)
        except RuntimeError as ex:
            print("allset: scale preview failed", ex)
        if context.area is not None:
            context.area.header_text_set(f"Scale: {f:.4f}")
            context.area.tag_redraw()

    def _end(self, context):
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._update(context, event)
            return {'RUNNING_MODAL'}
        if event.type == self.button and event.value == 'RELEASE':
            restore(self._state)
            try:
                apply(context, self._f, self._channels, self.orient_type, final=True)
                fix_zero(self._zeros, self._channels)
            except RuntimeError as ex:
                print("allset: scale failed", ex)
            self._end(context)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            restore(self._state)
            self._end(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


classes = (ALLSET_OT_manip_scale,)
