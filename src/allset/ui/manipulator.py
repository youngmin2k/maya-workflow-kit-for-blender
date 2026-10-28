# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya-shaped Move / Rotate / Scale manipulators (docs/steps/step_59.md 「계획」 5).

Blender's transform gizmo (``VIEW3D_GGT_xform_gizmo``) is C and its shape can't be
changed (research/blender/api_limits.md:62): thick axes, small cones, a white centre
circle. Maya's (research/maya/workflows/pivot_snap.md M1-M7, shots ``manip_*.png``):

- Move: thin axis lines with cones, a hollow centre square (free move), filled
  plane handles (normal-axis colour), the active handle drawn yellow (M2).
- Rotate: axis rings (front half), a camera ring, a grey trackball — Blender's C rotate gizmo
  already has this layout, so the Rotate tool keeps it (with the axis colours of the user's theme: the kit never
  writes a theme). The Move / Scale handles here use Maya's own axis colours (``MAYA_AXIS``, step 142).
- Scale: axis lines with cubes at the ends, a yellow centre cube, plane handles.
- Pivot edit mode (D / Insert): Move plus small rings to orient the pivot (M7).
- Constant screen size, Maya 108 px for the Move Y arrow at manipGlobalScale 1.5 (M3, M4).

``ALLSET_GGT_xform`` draws that and runs Blender's own transform operators from each
handle (``target_set_operator``), so snapping, constraints, numeric input, Smart
Duplicate/Extrude (step 22/26) and the active handle (step 28) keep working. It becomes
the widget of the Move and Scale tools in object and mesh edit mode by swapping their
ToolDefs in ``VIEW3D_PT_tools_active._tools`` for copies with another ``widget`` (same
idname, so ``wm.tool_set_by_id`` still finds them); tools already active are set up
again. Everything is put back on unregister.
"""

import bmesh
import bpy
from bpy.types import Gizmo, GizmoGroup
from mathutils import Matrix, Vector

GROUP = "ALLSET_GGT_xform"
GIZMO = "ALLSET_GT_maya_handle"
MODES = ('OBJECT', 'EDIT_MESH')
# Rotate keeps Blender's C gizmo: its axis rings (front half), camera ring and trackball already
# have Maya's layout (M5) and take the theme's axis colours; a Python dial can't clip the back half
# the same way (measured, docs/steps/step_59.md 「한 것」). Delegated.
TOOLS = {"builtin.move": 'TRANSLATE', "builtin.scale": 'RESIZE'}
# Orientation slot per tool kind (Blender: 0 default, 1 move, 2 rotate, 3 scale).
SLOT = {'TRANSLATE': 1, 'ROTATE': 2, 'RESIZE': 3}
KINDS = {"builtin.move": 'TRANSLATE', "builtin.rotate": 'ROTATE', "builtin.scale": 'RESIZE'}

# Arrow length in px at gizmo_size 75 and UI scale 1: Maya's Move Y arrow at manipGlobalScale 1.5
# (pivot_snap.md M4). Shapes are built in "arrow units" (arrow length = 1).
ARROW_PX = 108.0
# Shape sizes in arrow units, measured on shots/manip_move.png / manip_scale.png (M4).
CENTER_HALF = 0.083      # hollow centre square: 18 px
CONE_LEN, CONE_R = 0.13, 0.045
LINE_START = 0.0
# Plane handles (step 185): Maya's YZ / XY squares in research/maya/screens/02_cube_selected_move.png span 0.52-0.68
# arrow units along both axes (pixels solved into axis coordinates, tmp probe docs/steps/step_185.md): a 1 px rim in the
# axis colour around a translucent fill (pixels over the #767676 top face: red #b6655f, blue #5f63db).
PLANE_AT, PLANE_HALF = 0.60, 0.08
CUBE_AT, CUBE_HALF = 0.85, 0.05
CENTER_CUBE_HALF = 0.06
PIVOT_RING_R = 0.32      # pivot orientation rings (M7, offset 50)
PICK_R = 0.05            # half width of the invisible pick shape around a thin line
YELLOW = (1.0, 1.0, 0.0)  # hovered handle (displayColor manipCurrent #ffff00)
# Active handle and centre as Maya draws them on screen (step 185): #fdff88 for the active handle, the centre
# light blue #64dcff while an axis is active (research/maya/workflows/pivot_snap/shots/manip_move_active_center.png,
# manip_move_active_x.png, 02_cube_selected_move.png, 06_scale_manip.png: 81 px of #fdff88 / #64dcff in the square).
ACTIVE = (0xfd / 255, 1.0, 0x88 / 255)
CENTER_IDLE = (0x64 / 255, 0xdc / 255, 1.0)
ALPHA = 1.0
PLANE_FILL = 0.65         # fill alpha; the fill colour is the axis colour lightened toward white by PLANE_LIGHTEN
PLANE_LIGHTEN = 0.35

AXES = {'X': Vector((1, 0, 0)), 'Y': Vector((0, 1, 0)), 'Z': Vector((0, 0, 1))}


# --- shape geometry (pure, testable headless) ---------------------------------------------------

def _square(cx, cy, half, z=0.0):
    a, b, c, d = ((cx - half, cy - half, z), (cx + half, cy - half, z),
                  (cx + half, cy + half, z), (cx - half, cy + half, z))
    return [a, b, c, a, c, d]


def _square_outline(half):
    pts = [(-half, -half, 0), (half, -half, 0), (half, half, 0), (-half, half, 0)]
    out = []
    for i in range(4):
        out += [pts[i], pts[(i + 1) % 4]]
    return out


def _cone(base, tip, r, n=12):
    import math
    tris = []
    ring = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        tris += [(x0, y0, base), (x1, y1, base), (0, 0, tip)]
        tris += [(x0, y0, base), (0, 0, base), (x1, y1, base)]
    return tris


def _box(c, half):
    """Triangles of an axis-aligned cube centred at ``c``."""
    x, y, z = c
    v = [(x + sx * half, y + sy * half, z + sz * half) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    faces = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))
    tris = []
    for a, b, cc, d in faces:
        tris += [v[a], v[b], v[cc], v[a], v[cc], v[d]]
    return tris


def _bar(z0, z1, r):
    """Triangles of a thin square bar along +Z (pick shape of a line)."""
    return _box_span((-r, -r, z0), (r, r, z1))


def _box_span(lo, hi):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    faces = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))
    tris = []
    for a, b, c, d in faces:
        tris += [v[a], v[b], v[c], v[a], v[c], v[d]]
    return tris


def _ring(r, n=64):
    import math
    pts = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), 0.0) for i in range(n)]
    out = []
    for i in range(n):
        out += [pts[i], pts[(i + 1) % n]]
    return out


def _disc(r, n=48):
    import math
    pts = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), 0.0) for i in range(n)]
    tris = []
    for i in range(n):
        tris += [(0, 0, 0), pts[i], pts[(i + 1) % n]]
    return tris


def _band(r, w, n=64):
    """Flat ring band (pick shape of a ring)."""
    import math
    tris = []
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        p = [((r - w) * math.cos(a0), (r - w) * math.sin(a0), 0), ((r + w) * math.cos(a0), (r + w) * math.sin(a0), 0),
             ((r + w) * math.cos(a1), (r + w) * math.sin(a1), 0), ((r - w) * math.cos(a1), (r - w) * math.sin(a1), 0)]
        tris += [p[0], p[1], p[2], p[0], p[2], p[3]]
    return tris


def shapes(kind):
    """(draw shapes [(type, verts)], pick shape (type, verts)) of a handle in arrow units.

    Axis handles point along local +Z; plane handles lie in the local XY plane; view-facing
    handles (centre, view ring, trackball) are in the local XY plane facing +Z."""
    if kind == 'ARROW':
        base = 1.0 - CONE_LEN
        return ([('LINES', [(0, 0, LINE_START), (0, 0, base)]), ('TRIS', _cone(base, 1.0, CONE_R))],
                ('TRIS', _bar(CENTER_HALF, base, PICK_R) + _cone(base, 1.0, CONE_R * 1.6)))
    if kind == 'SCALE_AXIS':
        return ([('LINES', [(0, 0, LINE_START), (0, 0, CUBE_AT - CUBE_HALF)]),
                 ('TRIS', _box((0, 0, CUBE_AT), CUBE_HALF))],
                ('TRIS', _bar(CENTER_HALF, CUBE_AT, PICK_R) + _box((0, 0, CUBE_AT), CUBE_HALF * 1.6)))
    if kind == 'PLANE':      # fill first, then the rim (ALLSET_GT_maya_handle.draw)
        rim = [(x + PLANE_AT, y + PLANE_AT, z) for x, y, z in _square_outline(PLANE_HALF)]
        return ([('TRIS', _square(PLANE_AT, PLANE_AT, PLANE_HALF)), ('LINES', rim)],
                ('TRIS', _square(PLANE_AT, PLANE_AT, PLANE_HALF * 1.4)))
    if kind == 'CENTER':
        return ([('LINES', _square_outline(CENTER_HALF))], ('TRIS', _square(0, 0, CENTER_HALF * 1.2)))
    if kind == 'CENTER_CUBE':
        return ([('TRIS', _box((0, 0, 0), CENTER_CUBE_HALF))], ('TRIS', _box((0, 0, 0), CENTER_CUBE_HALF * 1.4)))
    if kind == 'PIVOT_CENTER':
        return ([('LINES', _square_outline(CENTER_HALF)), ('LINES', _ring(CENTER_HALF * 0.55, 24))],
                ('TRIS', _square(0, 0, CENTER_HALF * 1.2)))
    if kind == 'PIVOT_RING':
        return ([('LINES', _ring(PIVOT_RING_R))], ('TRIS', _band(PIVOT_RING_R, PICK_R * 0.8)))
    raise ValueError(kind)


# --- where and how the manipulator sits --------------------------------------------------------

def _edit_points(context):
    """World positions of the selected vertices of the meshes in edit mode, and the active
    element's centre (or None)."""
    pts, active = [], None
    obs = context.objects_in_mode_unique_data or ([context.edit_object] if context.edit_object else [])
    for ob in obs:
        if ob is None or ob.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(ob.data)
        mw = ob.matrix_world
        pts += [mw @ v.co for v in bm.verts if v.select and not v.hide]
        if ob == context.edit_object and active is None:
            el = bm.select_history.active
            if isinstance(el, bmesh.types.BMVert):
                active = mw @ el.co
            elif isinstance(el, bmesh.types.BMEdge):
                active = mw @ ((el.verts[0].co + el.verts[1].co) / 2)
            elif isinstance(el, bmesh.types.BMFace):
                active = mw @ el.calc_center_median()
    return pts, active


def _object_points(context):
    obs = [ob for ob in context.selected_objects if ob.visible_get()]
    active = context.view_layer.objects.active
    act = active.matrix_world.translation.copy() if active is not None and active in obs else None
    return [ob.matrix_world.translation.copy() for ob in obs], act


def center_of(points, active, pivot_point, cursor):
    """Manipulator position for Blender's pivot point setting (what the transform uses)."""
    if not points:
        return None
    if pivot_point == 'CURSOR':
        return cursor.copy()
    if pivot_point == 'ACTIVE_ELEMENT' and active is not None:
        return active
    if pivot_point == 'BOUNDING_BOX_CENTER':
        lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
        hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
        return (lo + hi) / 2
    total = Vector()
    for p in points:
        total += p
    return total / len(points)


def slot_type(scene, kind):
    """Orientation type the manipulator of ``kind`` uses (a per-tool slot, else the default)."""
    slots = scene.transform_orientation_slots
    t = slots[SLOT[kind]].type
    return slots[0].type if t == 'DEFAULT' else t


def pivot_frame(context, kind):
    """(centre, 3x3 axes, orientation type) of the manipulator of ``kind``: where it draws and how its axes point
    (step 85: Shift+MMB picks one of these axes). Centre None = nothing selected."""
    scene = context.scene
    otype = slot_type(scene, kind)
    if context.mode == 'EDIT_MESH':
        pts, act = _edit_points(context)
    else:
        pts, act = _object_points(context)
    center = center_of(pts, act, scene.tool_settings.transform_pivot_point, scene.cursor.location)
    return center, axes_of(context, otype, context.region_data), otype


def _edit_normal_axes(context):
    """Approximation of Blender's NORMAL orientation of the selection (docs/steps/step_59.md)."""
    ob = context.edit_object
    if ob is None or ob.type != 'MESH':
        return None
    bm = bmesh.from_edit_mesh(ob.data)
    n = Vector()
    faces = [f for f in bm.faces if f.select]
    for f in faces:
        n += f.normal
    if n.length < 1e-9:
        for v in bm.verts:
            if v.select:
                n += v.normal
    if n.length < 1e-9:
        return None
    nm = ob.matrix_world.to_3x3().inverted_safe().transposed()
    z = (nm @ n).normalized()
    edges = [e for e in bm.edges if e.select] or [e for f in faces for e in f.edges]
    t = None
    if edges:
        e = max(edges, key=lambda e: e.calc_length())
        t = ob.matrix_world.to_3x3() @ (e.verts[1].co - e.verts[0].co)
        t = t - z * t.dot(z)
    if t is None or t.length < 1e-9:
        t = Vector((0, 0, 1)) if abs(z.z) < 0.9 else Vector((0, 1, 0))
        t = t - z * t.dot(z)
    y = t.normalized()
    x = y.cross(z).normalized()
    return Matrix((x, y, z)).transposed()


def axes_of(context, otype, rv3d=None):
    """3x3 world axes of an orientation type (columns = X, Y, Z)."""
    ident = Matrix.Identity(3)
    active = context.view_layer.objects.active
    if otype == 'GLOBAL':
        return ident
    if otype == 'VIEW' and rv3d is not None:
        return rv3d.view_rotation.to_matrix()
    if otype == 'CURSOR':
        return context.scene.cursor.matrix.to_3x3().normalized()
    if otype == 'NORMAL' and context.mode == 'EDIT_MESH':
        m = _edit_normal_axes(context)
        if m is not None:
            return m
    if otype == 'PARENT':
        if active is not None and active.parent is not None:
            return active.parent.matrix_world.to_3x3().normalized()
        return ident
    if otype in ('LOCAL', 'NORMAL', 'GIMBAL'):
        return active.matrix_world.to_3x3().normalized() if active is not None else ident
    custom = context.scene.transform_orientation_slots[0].custom_orientation
    for slot in context.scene.transform_orientation_slots:
        if slot.type == otype and slot.custom_orientation is not None:
            custom = slot.custom_orientation
            break
    if custom is not None and custom.name == otype:
        return custom.matrix.copy().normalized()
    return ident


def _axis_rot(axis):
    """Rotation taking local +Z to the frame axis ``axis``."""
    if axis == 'X':
        return Matrix.Rotation(1.5707963267948966, 3, 'Y')
    if axis == 'Y':
        return Matrix.Rotation(-1.5707963267948966, 3, 'X')
    return Matrix.Identity(3)


# Plane handles: local XY plane -> the frame plane; (constraint axes, colour axis = normal).
PLANES = {'XY': ((True, True, False), 'Z', Matrix.Identity(3)),
          'YZ': ((False, True, True), 'X', Matrix(((0, 0, 1), (1, 0, 0), (0, 1, 0)))),
          'XZ': ((True, False, True), 'Y', Matrix(((1, 0, 0), (0, 0, 1), (0, 1, 0))))}


def active_tool(context):
    if context.mode not in MODES:
        return None
    try:
        return context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except (AttributeError, TypeError):
        return None


def tool_kind(context):
    tool = active_tool(context)
    if tool is None or tool.widget != GROUP:
        return None
    if tool.idname == 'builtin.rotate' and pivot_edit(context):
        return 'TRANSLATE'
    return TOOLS.get(tool.idname)


def pivot_edit(context):
    return context.mode == 'OBJECT' and context.scene.tool_settings.use_transform_data_origin


def _has_selection(context):
    if context.mode == 'OBJECT':
        return any(ob.visible_get() for ob in context.selected_objects)
    for ob in context.objects_in_mode_unique_data or ():
        if ob.type == 'MESH' and ob.data.total_vert_sel:
            return True
    return False


# Step 142 (#76): kit-fixed Maya axis colours instead of the user's theme gizmo axes (Blender's #ff3653 / #8adb00 /
# #3b64a5, ΔE00 15 / 8 / 21 from Maya; research/maya/screens/compare_step134_s100/viewport.md). Maya's manipulator as
# drawn: X #e60000, Y #00e600 (displayRGBColor manipX / manipY, research/maya/colors.json manip_x / manip_y), Z #0000ff
# (the Z line as rendered, colors.json manip_z_rendered at 02_cube_selected_move.png (799, 484); the displayRGBColor
# "Zaxis" #4a92ff is the grid / view axis light blue). The active and the hovered handle stay Maya's yellow
# (displayColor manipCurrent #ffff00; hover = #ffff00, research/maya/screens/compare/delta_e.md gizmo_hi). Gizmo colours
# are sRGB like the theme values they replace (the gizmo shaders convert). Rotate keeps Blender's C gizmo, whose rings
# read the theme's axis colours: Python can't recolour it without writing the theme (decision 13), so it keeps the
# user's theme colours (recorded, docs/steps/step_142_ui.md).
MAYA_AXIS = {'X': "#e60000", 'Y': "#00e600", 'Z': "#0000ff"}


def _srgb(hex_str):
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def axis_colours():
    """{'X' / 'Y' / 'Z': sRGB (r, g, b)} of the Maya manipulator axes (kit-fixed, whatever the theme is)."""
    return {axis: _srgb(value) for axis, value in MAYA_AXIS.items()}


def plane_fill(colour):
    """Fill colour of a plane handle: the rim colour lightened toward white (Maya 02: red rim, pinkish fill)."""
    return tuple(c + (1.0 - c) * PLANE_LIGHTEN for c in colour[:3])


def _active_handle(kind):
    """The remembered handle of ``kind`` (operators/manip.HANDLES, step 28): None = centre."""
    from ..operators import manip
    return manip.HANDLES.get(kind)


def _is_active(kind, handle_axes):
    h = _active_handle(kind)
    if h is None:
        return handle_axes is None
    return handle_axes is not None and tuple(h.get("constraint_axis", ())) == handle_axes


class ALLSET_GT_maya_handle(Gizmo):
    """One Maya manipulator handle: custom shapes, picked with a fatter invisible shape."""
    bl_idname = GIZMO

    __slots__ = ("draw_shapes", "pick_shape", "handle_kind", "handle_role", "handle_axis")

    def build(self, kind):
        self.handle_kind = kind
        draw, pick = shapes(kind)
        self.draw_shapes = [self.new_custom_shape(t, v) for t, v in draw]
        self.pick_shape = self.new_custom_shape(*pick)

    def draw(self, context):
        if getattr(self, "handle_kind", None) == 'PLANE':
            self._draw_plane()
            return
        for sh in getattr(self, "draw_shapes", ()):
            self.draw_custom_shape(sh)

    def _draw_plane(self):
        """Maya plane handle: translucent lightened fill + solid rim (draw_custom_shape takes one colour)."""
        import gpu
        colour = self.color_highlight if self.is_highlight else self.color
        alpha = self.alpha_highlight if self.is_highlight else self.alpha
        fill = plane_fill(colour)
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(self.line_width)
        for i, (batch, shader) in enumerate(getattr(self, "draw_shapes", ())):
            shader.bind()
            shader.uniform_float("color", (*fill, alpha * PLANE_FILL) if i == 0 else (*colour, alpha))
            with gpu.matrix.push_pop():
                gpu.matrix.multiply_matrix(self.matrix_world)
                batch.draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')

    def draw_select(self, context, select_id):
        sh = getattr(self, "pick_shape", None)
        if sh is not None:
            self.draw_custom_shape(sh, select_id=select_id)


# Maya = / - (operators/manip.ALLSET_OT_manip_size): the kit manipulator's own size factor for this session. Not
# Blender's gizmo_size preference, which the kit never writes (step 130).
SIZE = [1.0]


def scale_basis(context):
    """World size of one arrow unit is set by the draw scale; this is the px factor."""
    return ARROW_PX / 75.0 * context.preferences.view.gizmo_size * SIZE[0] / BASE_PX_PER_UNIT


# Pixels one gizmo unit spans with use_draw_scale and scale_basis 1 at gizmo_size 75 (measured, step 59).
BASE_PX_PER_UNIT = 75.0


class ALLSET_GGT_xform(GizmoGroup):
    bl_idname = GROUP
    bl_label = "Maya Manipulator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    # TOOL_FALLBACK_KEYMAP like Blender's transform gizmo: without it the tool loses its select
    # fallback (a marquee in empty space does nothing, measured).
    bl_options = {'3D', 'PERSISTENT', 'TOOL_FALLBACK_KEYMAP'}

    @classmethod
    def setup_keymap(cls, keyconfig):
        # Same keymap as Blender's transform gizmo: the Maya keyconfig's Smart Duplicate / Extrude
        # and active-handle items sit in front of gizmo_tweak there (step 22/26/28).
        return keyconfig.keymaps.new(name="Generic Gizmo Maybe Drag", space_type='EMPTY', region_type='WINDOW')

    @classmethod
    def poll(cls, context):
        space = context.space_data
        if space is None or space.type != 'VIEW_3D' or not space.show_gizmo or not space.show_gizmo_tool:
            return False
        if tool_kind(context) is None or not _has_selection(context):
            return False
        from . import in_view
        return not in_view.manip_visible(context)   # Maya: the extrude manipulator replaces it (step 65)

    def setup(self, context):
        self.handles = []      # (gizmo, role, data)
        self._built_for = None

    def _clear(self):
        for gz, _role, _data in self.handles:
            self.gizmos.remove(gz)
        self.handles = []

    def _new(self, kind, role=None, axis=None):
        gz = self.gizmos.new(GIZMO)
        gz.build(kind)
        gz.handle_role, gz.handle_axis = role, axis       # read by operators/manip.py Ctrl+LMB (step 85)
        gz.use_draw_scale = True
        gz.use_draw_modal = True
        gz.use_tooltip = False                           # Maya manipulators show no tooltip (#98)
        gz.line_width = 1.5
        gz.color_highlight = YELLOW
        gz.alpha = gz.alpha_highlight = ALPHA
        return gz

    def _dial(self):
        gz = self.gizmos.new("GIZMO_GT_dial_3d")
        gz.use_draw_scale = True
        gz.use_draw_modal = True
        gz.use_tooltip = False                           # Maya manipulators show no tooltip (#98)
        gz.line_width = 1.5
        gz.color_highlight = YELLOW
        gz.alpha = gz.alpha_highlight = ALPHA
        return gz

    def _build(self, context, kind, pivot):
        self._clear()
        if kind == 'TRANSLATE':
            for ax in 'XYZ':
                self.handles.append((self._new('ARROW', 'AXIS', ax), 'AXIS', ax))
            for pl in PLANES:
                self.handles.append((self._new('PLANE', 'PLANE', pl), 'PLANE', pl))
            self.handles.append((self._new('PIVOT_CENTER' if pivot else 'CENTER', 'CENTER'), 'CENTER', None))
            if pivot:
                for ax in 'XYZ':
                    self.handles.append((self._dial(), 'PIVOT_RING', ax))
        elif kind == 'RESIZE':
            for ax in 'XYZ':
                self.handles.append((self._new('SCALE_AXIS', 'AXIS', ax), 'AXIS', ax))
            for pl in PLANES:
                self.handles.append((self._new('PLANE', 'PLANE', pl), 'PLANE', pl))
            self.handles.append((self._new('CENTER_CUBE', 'CENTER'), 'CENTER', None))
        self._built_for = (kind, pivot)
        self._ops_for = None

    def _bind_ops(self, kind, otype, frame=None):
        """Point each handle at Blender's transform with its constraint and orientation."""
        op = {'TRANSLATE': "transform.translate", 'RESIZE': "transform.resize"}[kind]
        for gz, role, data in self.handles:
            if role == 'AXIS':
                axes = tuple(a == data for a in 'XYZ')
                props = gz.target_set_operator(op)
                props.constraint_axis = axes
                self._orient(props, otype, frame)
                props.release_confirm = True
            elif role == 'PLANE':
                props = gz.target_set_operator(op)
                props.constraint_axis = PLANES[data][0]
                self._orient(props, otype, frame)
                props.release_confirm = True
            elif role == 'CENTER':
                props = gz.target_set_operator(op)
                props.release_confirm = True
            elif role == 'PIVOT_RING':
                # D mode: turn the pivot about its own axes (Maya pivot orientation handle, M7)
                props = gz.target_set_operator("transform.rotate")
                props.orient_axis = data
                props.orient_type = 'LOCAL'
                props.constraint_axis = tuple(a == data for a in 'XYZ')
                props.release_confirm = True
        self._ops_for = (kind, otype)

    @staticmethod
    def _orient(props, otype, frame):
        # Gizmo operator properties expose built-in enum values on Blender 5.2.
        # Supply the picked component axes explicitly for custom orientations.
        builtin = {'GLOBAL', 'LOCAL', 'NORMAL', 'GIMBAL', 'VIEW', 'CURSOR', 'PARENT'}
        props.orient_type = otype if otype in builtin else 'GLOBAL'
        props.orient_matrix_type = 'GLOBAL'
        props.orient_matrix = Matrix.Identity(3) if otype in builtin else frame

    def draw_prepare(self, context):
        kind = tool_kind(context)
        if kind is None:
            return
        pivot = kind == 'TRANSLATE' and pivot_edit(context)
        if self._built_for != (kind, pivot):
            self._build(context, kind, pivot)
        scene = context.scene
        otype = slot_type(scene, kind)
        rv3d = context.region_data
        frame = axes_of(context, otype, rv3d)
        if self._ops_for != (kind, otype) or otype not in {'GLOBAL', 'LOCAL', 'NORMAL', 'GIMBAL', 'VIEW', 'CURSOR', 'PARENT'}:
            self._bind_ops(kind, otype, frame=frame)
        if context.mode == 'EDIT_MESH':
            pts, act = _edit_points(context)
        else:
            pts, act = _object_points(context)
        center = center_of(pts, act, scene.tool_settings.transform_pivot_point, scene.cursor.location)
        hide = center is None
        view = rv3d.view_rotation.to_matrix() if rv3d is not None else Matrix.Identity(3)
        colours = axis_colours()
        s = scale_basis(context)
        for gz, role, data in self.handles:
            gz.hide = hide
            if hide:
                continue
            gz.scale_basis = s
            if role == 'AXIS':
                rot = frame @ _axis_rot(data)
                active = _is_active(kind, tuple(a == data for a in 'XYZ'))
                gz.color = ACTIVE if active else colours[data]
            elif role == 'PLANE':
                axes, normal, local = PLANES[data]
                rot = frame @ local
                gz.color = ACTIVE if _is_active(kind, axes) else colours[normal]
            elif role == 'CENTER':
                # Maya: the centre (free move / uniform scale) is the active handle by default, drawn #fdff88;
                # light blue while an axis or plane is active (step 185)
                rot = frame if kind == 'RESIZE' else view
                gz.color = ACTIVE if _is_active(kind, None) else CENTER_IDLE
            else:   # PIVOT_RING
                rot = axes_of(context, 'LOCAL', rv3d) @ _axis_rot(data)
                gz.color = colours[data]
                gz.scale_basis = s * PIVOT_RING_R
            gz.matrix_basis = Matrix.Translation(center) @ rot.to_4x4()


classes = (ALLSET_GT_maya_handle, ALLSET_GGT_xform)


# --- Tool Settings: Maya Move / Rotate / Scale Settings (pivot_snap.md P12, P13, S3, S5) --------

TITLES = {'TRANSLATE': "Move Settings", 'ROTATE': "Rotate Settings", 'RESIZE': "Scale Settings"}


def draw_tool_settings(self, context):
    """Appended to the active tool panel (the Status Line / W-menu Tool Settings popup)."""
    tool = active_tool(context)
    kind = KINDS.get(tool.idname) if tool is not None else None
    if kind is None:
        return
    from ..operators import snap_align
    scene = context.scene
    ts = scene.tool_settings
    layout = self.layout
    layout.separator()
    layout.label(text=TITLES[kind])
    col = layout.column(align=True)
    col.prop(scene.transform_orientation_slots[SLOT[kind]], "type", text="Axis Orientation")
    col.prop(ts, "transform_pivot_point", text="Pivot")
    row = layout.row(align=True)
    row.label(text="Step Snap")
    mode = snap_align.step_snap_mode(ts, kind)
    for m in ('OFF', 'RELATIVE', 'ABSOLUTE'):
        cell = row.row(align=True)
        # step 263: Move offers Absolute only with World axes (Maya, 060_messages_ui.md B5)
        cell.enabled = m != 'ABSOLUTE' or snap_align.absolute_offered(scene, kind)
        op = cell.operator("allset.step_snap", text=m.title(), depress=mode == m)
        op.kind, op.mode = kind, m
    if kind == 'ROTATE':
        layout.prop(ts, "snap_angle_increment_3d", text="Step")
    else:
        # Blender's increment is the grid step: 1 Maya unit in the Maya Workflow Kit template (step 25).
        layout.label(text="Step: one grid unit", icon='SNAP_INCREMENT')
    if kind == 'TRANSLATE':
        # Blender snapping always keeps the selection's spacing (Maya's default; off = not possible).
        layout.label(text="Retain Component Spacing", icon='CHECKBOX_HLT')
    if context.mode == 'OBJECT':
        layout.label(text="Pivot")
        row = layout.row(align=True)
        row.operator("allset.pivot_toggle", text="Edit Pivot", icon='OBJECT_ORIGIN',
                     depress=ts.use_transform_data_origin)
        row.operator("allset.reset_pivot", text="Reset")
        row.operator("allset.bake_pivot", text="Bake")


# --- tool widget swap ---------------------------------------------------------------------------

_saved = {}   # mode -> original tool list


def _swap_items(items):
    out = []
    for it in items:
        if isinstance(it, tuple) and not hasattr(it, "idname"):
            out.append(tuple(_swap_items(it)))
        elif getattr(it, "idname", None) in TOOLS and getattr(it, "widget", None) == "VIEW3D_GGT_xform_gizmo":
            out.append(it._replace(widget=GROUP))
        else:
            out.append(it)
    return out


def _panel():
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active
    return VIEW3D_PT_tools_active


def patch_tools():
    cls = _panel()
    for mode in MODES:
        if mode in _saved:
            continue
        items = cls._tools[mode]
        _saved[mode] = items
        cls._tools[mode] = type(items)(_swap_items(items))


def unpatch_tools():
    cls = _panel()
    for mode, items in _saved.items():
        cls._tools[mode] = items
    _saved.clear()


def _find_item(mode, idname):
    cls = _panel()
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
    for item, _index in ToolSelectPanelHelper._tools_flatten_with_tool_index(
            cls.tools_from_context(bpy.context, mode=mode)):
        if item is not None and item.idname == idname:
            return item
    return None


def resetup(tool, mode, widget=None):
    """Set ``tool`` (a WorkSpaceTool of ``mode``) up again from the current ToolDef: the gizmo
    group a tool uses is copied at activation, so a swapped ToolDef needs this."""
    item = _find_item(mode, tool.idname)
    if item is None:
        return False
    fallback = _find_item(mode, tool.idname_fallback) if tool.idname_fallback else None
    keymap_fallback = (fallback and fallback.keymap and fallback.keymap[0]) or ""
    if keymap_fallback:
        keymap_fallback += " (fallback)"
    tool.setup(idname=item.idname, keymap=item.keymap[0] if item.keymap is not None else "",
               cursor=item.cursor or 'DEFAULT', options=item.options or set(),
               gizmo_group=(item.widget or "") if widget is None else widget, brush_type=item.brush_type or 'ANY',
               data_block=item.data_block or "", operator=item.operator or "", index=tool.index,
               idname_fallback=tool.idname_fallback, keymap_fallback=keymap_fallback)
    return True


def refresh_pivot_tool(context):
    """Rotate uses the pivot edit handles during D / Insert, then its normal rings again."""
    tool = active_tool(context)
    if context.mode == 'OBJECT' and tool is not None and tool.idname == 'builtin.rotate':
        resetup(tool, context.mode, widget=GROUP if pivot_edit(context) else None)


def stale(tool, patched):
    """True when an active transform tool still carries the other gizmo group."""
    if tool is None or tool.idname not in TOOLS:
        return False
    want = GROUP if patched else "VIEW3D_GGT_xform_gizmo"
    return tool.widget != want


def ensure_tools(patched=True):
    """Set up again every workspace's Move/Rotate/Scale tool whose gizmo group is stale."""
    done = 0
    for ws in bpy.data.workspaces:
        for mode in MODES:
            try:
                tool = ws.tools.from_space_view3d_mode(mode, create=False)
            except (TypeError, RuntimeError):
                continue
            if tool is not None and tool.idname == 'builtin.rotate':
                editing = (patched and mode == 'OBJECT' and ws == bpy.context.workspace
                           and bpy.context.scene.tool_settings.use_transform_data_origin)
                if (tool.widget == GROUP) != editing:
                    try:
                        done += resetup(tool, mode, widget=GROUP if editing else None)
                    except (TypeError, RuntimeError, AttributeError) as ex:
                        print("allset: pivot tool setup failed", tool.idname, ex)
                continue
            if stale(tool, patched):
                try:
                    done += resetup(tool, mode)
                except (TypeError, RuntimeError, AttributeError) as ex:
                    print("allset: tool setup failed", tool.idname, ex)
    return done


def _ensure_timer():
    try:
        ensure_tools(bool(_saved))
    except (ReferenceError, AttributeError):
        pass
    return 0.5 if _saved else None


@bpy.app.handlers.persistent
def _on_load_post(_dummy):
    ensure_tools(bool(_saved))


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_PT_active_tool.append(draw_tool_settings)
    patch_tools()
    bpy.app.timers.register(_ensure_timer, first_interval=0.1, persistent=True)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    SIZE[0] = 1.0
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    if bpy.app.timers.is_registered(_ensure_timer):
        bpy.app.timers.unregister(_ensure_timer)
    unpatch_tools()
    try:
        ensure_tools(False)
    except (ReferenceError, AttributeError):
        pass
    bpy.types.VIEW3D_PT_active_tool.remove(draw_tool_settings)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
