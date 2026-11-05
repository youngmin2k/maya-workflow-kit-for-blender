# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's extrude manipulator, In-View Editor and the INPUTS rows of the last extrusion
.

- Visible while the active edit object's last kit extrusion is valid and its extruded faces are the selection
  (operators/extrude.py). Maya swaps the Move manipulator for the extrude one: the kit Move/Scale manipulator
  (ui/manipulator.py) hides meanwhile.
- The manipulator is a Python gizmo group (Blender's C transform gizmo can't be extended).
  Maya's polyExtrudeFace manipulator in the faces' local frame - three
  arrows (Local Translate X red / Y green / Z blue = the normal), a cube past each cone (Local Scale X / Y / Z), three
  plane handles (two Local Translate values) and a light-blue centre square (uniform Local Scale). Every handle runs
  ``allset.extrude_drag`` with its ``handle``; release = one undo step (``extrude.set_params``). Edge / vertex
  extrusions and bevels keep the single arrow of their ``Spec.arrow``. No Blender tooltips (Maya manipulators have
  none).
- The In-View Editor box is drawn by a POST_PIXEL handler; 2D gizmos only pick its rows (the shelf's way).
  Dragging a row sideways changes the value, a click without a drag types it, Keep Faces Together toggles.
- Channel Box INPUTS: the node and five rows (WindowManager text proxies: a UI edit of a WM property pushes no
  undo step, the edit itself is one) + the "only the last one" notice.
"""

import blf
import bmesh
import bpy
import gpu
from bpy.props import FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector, geometry

from . import cb_entry, manipulator
from ..operators import bevel_maya, extrude, units   # bevel_maya: registers the polyBevel spec
from ..operators import uv_tools  # noqa: F401  registers the polyAutoProj spec

ROW_H = 16          # px at UI scale 1 (Maya In-View rows)
WIDTH = 180
GAP = (150, -6)     # box top-left from the manipulator centre on screen: right of the X / Y handles (
                    # Maya: past the manipulator, 250 px from its centre at a 100 px rotate ring)
FLOAT_STEP = 0.01   # Maya units per px of a sideways drag
DIV_PX = 20         # px per division
KINDS = {"thickness": "NONE", "local_translate_z": "NONE", "offset": "NONE", "divisions": "INT",
         "keep_faces_together": "BOOL"}
# every field of every recorded node (Channel Box text proxies: edge / vertex extrusion, bevel)
ALL_FIELDS = tuple(dict.fromkeys(f for spec in extrude.SPECS.values() for f in spec.fields))
MAX_ROWS = max(len(spec.fields) for spec in extrude.SPECS.values())
BOOL_FIELDS = {f for spec in extrude.SPECS.values() for f, k in spec.kinds.items() if k == "BOOL"}
INT_FIELDS = {f for spec in extrude.SPECS.values() for f, k in spec.kinds.items() if k == "INT"}
RANGES = {"fraction": (0.0, 1.0), "depth": (-1.0, 1.0), "planes": (3, 12), "optimize": (0.0, 1.0),
          "percentage_space": (0.0, 5.0)}
_ = bevel_maya
BG = (0.22, 0.22, 0.22, 0.92)
TITLE_BG = (0.30, 0.30, 0.30, 0.95)
TEXT = (0.86, 0.86, 0.86, 1.0)
HOT = (1.0, 1.0, 0.35, 1.0)        # Maya's highlighted attribute name
YELLOW = (1.0, 1.0, 0.0)

_state = {"hot": 0, "handle": None}


def _scale():
    return bpy.context.preferences.system.ui_scale


# --- what is shown -----------------------------------------------------------------------------------

def record(context):
    """(object, record) when the manipulator / In-View Editor show in this 3D View, else (None, None)."""
    space = getattr(context, "space_data", None)
    if space is None or space.type != 'VIEW_3D':
        return None, None
    from .toolbox import is_toolbox
    if is_toolbox(space):
        return None, None
    from . import in_view_editor
    node = in_view_editor.model_target(context)
    if node is None or not node.spec.in_view:
        return None, None
    return node.ob, node.record


def manip_visible(context):
    return record(context)[1] is not None


def arrow_visible(context):
    rec = record(context)[1]
    return rec is not None and rec.spec.arrow is not None


def _pre_direction(rec):
    """Arrow direction of an edge / vertex extrusion or a bevel, from the mesh before it (cached)."""
    d = getattr(rec, "arrow_dir", None)
    if d is not None:
        return d
    pre = rec.pre
    d = Vector()
    if pre is not None:
        pre.normal_update()
        if rec.spec.kind == 'VERTEX':
            for v in pre.verts:
                if v.select:
                    d += sum((f.normal for f in v.link_faces), Vector()).normalized()
        else:
            for e in pre.edges:
                if e.select:
                    d += extrude.edge_frame(e)[2]
    rec.arrow_dir = d
    return d


def cap_frame(ob, rec):
    """(world centre, world unit normal, world length of one local unit along it) of the extruded faces (edge /
    vertex extrusion: the selection it left, the mean edge / vertex normal; bevel: the bevel's vertices)."""
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    verts = [bm.verts[i] for i in rec.cap_verts if i < len(bm.verts)]
    if rec.spec is not extrude.FACE:
        selected = rec.sel[0] if rec.sel is not None else ()
        verts = [bm.verts[i] for i in selected if i < len(bm.verts)] or verts
    faces = [bm.faces[i] for i in rec.cap_faces if i < len(bm.faces)]
    if not verts:
        return None
    centre = sum((v.co for v in verts), Vector()) / len(verts)
    n = sum((f.normal for f in faces), Vector()) if rec.spec is extrude.FACE else _pre_direction(rec).copy()
    n = n.normalized() if n.length > 1e-9 else Vector((0, 0, 1))
    mw = ob.matrix_world
    nw = mw.to_3x3() @ n
    k = nw.length or 1.0
    return mw @ centre, nw / k, k


def layout(region, anchor, scale, fields=extrude.FIELDS):
    """Box geometry in region pixels: {"box", "title", "rows": [(field, x0, y0, x1, y1)]}."""
    w, h = WIDTH * scale, ROW_H * scale
    n = len(fields) + 1
    x0 = anchor[0] + GAP[0] * scale
    top = anchor[1] + GAP[1] * scale
    x0 = max(4 * scale, min(x0, region.width - w - 4 * scale))
    top = max(n * h + 4 * scale, min(top, region.height - 4 * scale))
    rows = []
    for i, field in enumerate(fields):
        y1 = top - (i + 1) * h
        rows.append((field, x0, y1 - h, x0 + w, y1))
    return {"box": (x0, top - n * h, x0 + w, top), "title": (x0, top - h, x0 + w, top), "rows": rows}


def anchor(context, ob, rec):
    frame = cap_frame(ob, rec)
    if frame is None:
        return None
    p = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, frame[0])
    return (p.x, p.y) if p is not None else None


def current_layout(context):
    from . import in_view_editor
    node, lay = in_view_editor.current_layout(context)
    return (node.record if hasattr(node, 'record') else node), lay


def value_text(rec, field):
    v = rec.params[field]
    if field in BOOL_FIELDS:
        return "On" if v else "Off"
    if field in INT_FIELDS:
        return str(int(v))
    return cb_entry.fmt_number(v)


# --- drawing -----------------------------------------------------------------------------------------

def _rect(x0, y0, x1, y1, colour):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]},
                             indices=[(0, 1, 2), (0, 2, 3)])
    shader.uniform_float("color", colour)
    batch.draw(shader)


def _text(x, y, s, colour, size):
    blf.size(0, size)
    blf.color(0, *colour)
    blf.position(0, x, y, 0)
    blf.draw(0, s)


def draw_box():
    from . import in_view_editor
    in_view_editor.draw()


# --- In-View picking (2D gizmos) -------------------------------------------------------------------

class ALLSET_GT_in_view_row(bpy.types.Gizmo):
    """Row ``row`` of the In-View Editor: picking only (drawn by ``draw_box``)."""
    bl_idname = "ALLSET_GT_in_view_row"
    __slots__ = ("row",)

    def setup(self):
        self.row = 0

    def draw(self, context):
        pass

    def test_select(self, context, location):
        _rec, lay = current_layout(context)
        if lay is None or self.row >= len(lay["rows"]):
            return -1
        reach = 10 * _scale()
        if lay['box'][2]-reach <= location[0] <= lay['box'][2] and lay['box'][1] <= location[1] <= lay['box'][1]+reach:
            return -1
        _f, x0, y0, x1, y1 = lay["rows"][self.row]
        if x0 <= location[0] <= x1 and y0 <= location[1] <= y1:
            return 0
        return -1


class ALLSET_GGT_in_view(bpy.types.GizmoGroup):
    bl_idname = "ALLSET_GGT_in_view"
    bl_label = "Maya In-View Editor"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        from . import in_view_editor
        return in_view_editor.target(context) is not None

    def setup(self, context):
        for i in range(MAX_ROWS):
            gz = self.gizmos.new(ALLSET_GT_in_view_row.bl_idname)
            gz.row = i
            gz.target_set_operator(ALLSET_OT_inview_drag.bl_idname).row = i


# --- the extrude manipulator (3D gizmo) --------------------------------------------------

# Maya 2022 polyExtrudeFace manipulator (top face of a cube,
# local mode): lengths in "arrow units" (centre -> scale cube = 1): cone 0.64 -> 0.86 (radius 0.05), cube half 0.07,
# plane handles centred 0.5 / 0.5 between two axes (half 0.08, translucent with a full-colour rim), hollow centre square
# half 0.12 (20 px at an 83 px Z arrow) in #64dcff, screen facing. Axis colours = the kit Move manipulator's Maya
# colours (manipulator.MAYA_AXIS). Not drawn: Maya's cyan rotate ring (polyExtrudeFace Local Rotate - the
# kit doesn't model it) and its world / local toggle icon (world mode drives Translate / Rotate / Scale, not modelled).
CONE_BASE, CONE_TIP, CONE_R = 0.64, 0.86, 0.05
CUBE_AT, CUBE_HALF = 1.0, 0.07
PLANE_AT, PLANE_HALF = 0.5, 0.08
PLANE_FILL = 0.25
CENTER_HALF = 0.12
CENTER_COLOUR = (0x64 / 255, 0xdc / 255, 1.0)
SCALE_PX = 100.0          # px of mouse travel along a scale handle that doubles the scale
# the extrude manipulator is drawn smaller than the Move one: Z arrow to cube 83 px at a ~27 deg persp elevation
# = ~93 px against the Move Y arrow's 108 px (manipulator.ARROW_PX)
SIZE = 0.86

# handle -> (role, axis or plane, the values it drives)
HANDLES = {
    "TX": ('ARROW', 'X', ("local_translate_x",)),
    "TY": ('ARROW', 'Y', ("local_translate_y",)),
    "TZ": ('ARROW', 'Z', ("local_translate_z",)),
    "SX": ('CUBE', 'X', ("local_scale_x",)),
    "SY": ('CUBE', 'Y', ("local_scale_y",)),
    "SZ": ('CUBE', 'Z', ("local_scale_z",)),
    "PXY": ('PLANE', 'XY', ("local_translate_x", "local_translate_y")),
    "PYZ": ('PLANE', 'YZ', ("local_translate_y", "local_translate_z")),
    "PXZ": ('PLANE', 'XZ', ("local_translate_x", "local_translate_z")),
    "S": ('CENTER', None, ("local_scale_x", "local_scale_y", "local_scale_z")),
}
AXIS_INDEX = {'X': 0, 'Y': 1, 'Z': 2}


def handle_fields(rec, handle):
    """The values ``handle`` drives on ``rec`` (edge / vertex extrusion, bevel: only "TZ" = their arrow field)."""
    if rec is None or handle not in HANDLES:
        return ()
    if rec.spec is not extrude.FACE:
        return (rec.spec.arrow,) if handle == "TZ" and rec.spec.arrow is not None else ()
    return HANDLES[handle][2]


def manip_frame(ob, rec):
    """(world centre, 3x3 world unit axes (columns X, Y, Z), world lengths of one mesh unit along X / Y / Z) of the
    extrude manipulator: Z = the faces' normal, X / Y = polyExtrudeFace's local axes of that normal (world X projected
    into the face plane, extrude.face_axes). None when there is nothing to show."""
    frame = cap_frame(ob, rec)
    if frame is None:
        return None
    centre, nw, kz = frame
    mw3 = ob.matrix_world.to_3x3()
    inv = mw3.inverted_safe()
    n_obj = (inv @ nw)
    n_obj = n_obj.normalized() if n_obj.length > 1e-12 else Vector((0, 0, 1))
    axes = extrude.mesh_axes(ob)
    x_obj, y_obj = extrude.face_axes(n_obj, axes["direction"], axes["fallback"])
    xw, yw = mw3 @ x_obj, mw3 @ y_obj
    kx, ky = xw.length or 1.0, yw.length or 1.0
    xw, yw = xw / kx, yw / ky
    return centre, Matrix((xw, yw, nw)).transposed(), (kx, ky, kz)


def unit_px(context):
    """Screen px of one arrow unit (wm_gizmo: scale_basis x gizmo_size x UI scale at use_draw_scale)."""
    return (manipulator.scale_basis(context) * SIZE * context.preferences.view.gizmo_size
            * (context.preferences.system.ui_scale or 1.0))


def handles_hit(context, region, rv3d, mouse, reach):
    """True when ``mouse`` (region px) is within ``reach`` px of a shown handle of the extrude manipulator: the
    pre-selection gizmo (operators/preselect.py, a 2D test_select that would win over these 3D-picked handles)
    declines there, like it does on the Move manipulator."""
    ob, rec = record(context)
    frame = manip_frame(ob, rec) if rec is not None else None
    if frame is None:
        return False
    centre, axes, _k = frame
    c2 = view3d_utils.location_3d_to_region_2d(region, rv3d, centre)
    if c2 is None:
        return False
    w = view3d_utils.region_2d_to_location_3d(region, rv3d, c2 + Vector((1.0, 0.0)), centre) - centre
    unit = unit_px(context) * w.length          # world length of one arrow unit at the centre
    m = Vector(mouse)

    def at(vec):
        p = view3d_utils.location_3d_to_region_2d(region, rv3d, centre + vec * unit)
        return p if p is not None else c2

    for handle in HANDLES:
        if not handle_fields(rec, handle):
            continue
        role, data, _f = HANDLES[handle]
        if role == 'ARROW':
            a, b = c2, at(axes.col[AXIS_INDEX[data]] * CONE_TIP)
            ab = b - a
            t = 0.0 if ab.length_squared < 1e-9 else max(0.0, min(1.0, (m - a).dot(ab) / ab.length_squared))
            if (a + ab * t - m).length <= reach:
                return True
        elif role == 'CUBE':
            if (at(axes.col[AXIS_INDEX[data]] * CUBE_AT) - m).length <= reach + CUBE_HALF * unit_px(context):
                return True
        elif role == 'PLANE':
            i, j = AXIS_INDEX[data[0]], AXIS_INDEX[data[1]]
            if (at((axes.col[i] + axes.col[j]) * PLANE_AT) - m).length <= reach + PLANE_HALF * unit_px(context):
                return True
        elif (c2 - m).length <= reach + CENTER_HALF * unit_px(context):
            return True
    return False


def handle_shapes(role):
    """(draw shapes [(type, verts, fill)], pick shape (type, verts)) of a handle in arrow units: arrows / cubes point
    along local +Z, plane handles lie in the local XY plane, the centre square faces +Z. Pure (tests run it headless)."""
    m = manipulator
    if role == 'ARROW':
        return ([('LINES', [(0, 0, 0), (0, 0, CONE_BASE)], False), ('TRIS', m._cone(CONE_BASE, CONE_TIP, CONE_R), False)],
                ('TRIS', m._bar(CENTER_HALF, CONE_BASE, 0.04) + m._cone(CONE_BASE, CONE_TIP, CONE_R * 1.6)))
    if role == 'CUBE':
        return ([('LINES', [(0, 0, CONE_TIP), (0, 0, CUBE_AT - CUBE_HALF)], False),
                 ('TRIS', m._box((0, 0, CUBE_AT), CUBE_HALF), False)],
                ('TRIS', m._box((0, 0, CUBE_AT), CUBE_HALF * 1.6)))
    if role == 'PLANE':
        rim = [(x + PLANE_AT, y + PLANE_AT, z) for x, y, z in m._square_outline(PLANE_HALF)]
        return ([('TRIS', m._square(PLANE_AT, PLANE_AT, PLANE_HALF), True), ('LINES', rim, False)],
                ('TRIS', m._square(PLANE_AT, PLANE_AT, PLANE_HALF * 1.3)))
    if role == 'CENTER':
        return ([('LINES', m._square_outline(CENTER_HALF), False)], ('TRIS', m._square(0, 0, CENTER_HALF * 1.3)))
    raise ValueError(role)


class ALLSET_GT_extrude_handle(bpy.types.Gizmo):
    """One handle of the Maya extrude manipulator (custom shapes; plane handles: translucent fill + rim)."""
    bl_idname = "ALLSET_GT_extrude_handle"
    __slots__ = ("draw_shapes", "pick_shape", "handle")

    def build(self, handle):
        self.handle = handle
        draw, pick = handle_shapes(HANDLES[handle][0])
        self.draw_shapes = [(self.new_custom_shape(t, v), fill) for t, v, fill in draw]
        self.pick_shape = self.new_custom_shape(*pick)

    def draw(self, context):
        colour = self.color_highlight if self.is_highlight else self.color
        alpha = self.alpha_highlight if self.is_highlight else self.alpha
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(self.line_width)
        for (batch, shader), fill in getattr(self, "draw_shapes", ()):
            shader.bind()
            shader.uniform_float("color", (*colour, alpha * PLANE_FILL if fill else alpha))
            with gpu.matrix.push_pop():
                gpu.matrix.multiply_matrix(self.matrix_world)
                batch.draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')

    def draw_select(self, context, select_id):
        sh = getattr(self, "pick_shape", None)
        if sh is not None:
            self.draw_custom_shape(sh, select_id=select_id)


def _no_tooltip(gz):
    """Maya manipulators have no tooltips; Blender would show the target operator's description (#98)."""
    if hasattr(gz, "use_tooltip"):
        gz.use_tooltip = False


class ALLSET_GGT_extrude(bpy.types.GizmoGroup):
    bl_idname = "ALLSET_GGT_extrude"
    bl_label = "Maya Extrude Manipulator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.type == 'VIEW_3D' and space.show_gizmo and arrow_visible(context)

    def setup(self, context):
        self.handles = {}
        for handle in HANDLES:
            gz = self.gizmos.new(ALLSET_GT_extrude_handle.bl_idname)
            gz.build(handle)
            gz.target_set_operator(ALLSET_OT_extrude_drag.bl_idname).handle = handle
            gz.color_highlight = YELLOW
            gz.alpha = gz.alpha_highlight = 1.0
            gz.line_width = 1.5
            gz.use_draw_scale = True
            gz.use_draw_modal = True
            _no_tooltip(gz)
            self.handles[handle] = gz
        self.arrow = self.handles["TZ"]

    def draw_prepare(self, context):
        ob, rec = record(context)
        if rec is None:
            return
        frame = manip_frame(ob, rec)
        rv3d = context.region_data
        view = rv3d.view_rotation.to_matrix() if rv3d is not None else Matrix.Identity(3)
        colours = manipulator.axis_colours()
        s = manipulator.scale_basis(context) * SIZE
        for handle, gz in self.handles.items():
            gz.hide = frame is None or not handle_fields(rec, handle)
            if gz.hide:
                continue
            centre, axes, _k = frame
            role, data, _fields = HANDLES[handle]
            gz.scale_basis = s
            if role in ('ARROW', 'CUBE'):
                rot = axes @ manipulator._axis_rot(data)
                gz.color = colours[data]
            elif role == 'PLANE':
                _c, normal, local = manipulator.PLANES[data]
                rot = axes @ local
                gz.color = colours[normal]
            else:
                rot = view
                gz.color = CENTER_COLOUR
            gz.matrix_basis = Matrix.Translation(centre) @ rot.to_4x4()


# --- operators ---------------------------------------------------------------------------------------

def _redraw(context):
    for area in context.screen.areas if context.screen else ():
        if area.type == 'VIEW_3D':
            area.tag_redraw()


class ALLSET_OT_inview_drag(bpy.types.Operator):
    """In-View Editor: drag sideways to change the value (Ctrl: finer, Shift: coarser), click to type it"""
    bl_idname = "allset.inview_drag"
    bl_label = "In-View Editor"
    bl_options = {'INTERNAL'}

    row: IntProperty(default=-1, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        from . import in_view_editor
        return in_view_editor.invoke_drag(self, context, event)

    def modal(self, context, event):
        from . import in_view_editor
        return in_view_editor.modal_drag(self, context, event)

    def cancel(self, context):
        from . import in_view_editor
        in_view_editor.finish_drag(self, context, cancel=True)


class ALLSET_OT_inview_type(bpy.types.Operator):
    """Type a value of the last extrusion (In-View Editor)"""
    bl_idname = "allset.inview_type"
    bl_label = "In-View Editor"
    bl_options = {'INTERNAL'}

    row: IntProperty(options={'SKIP_SAVE'})
    number: FloatProperty(name="Value")
    count: IntProperty(name="Divisions")

    @classmethod
    def poll(cls, context):
        return extrude.active(context)[1] is not None

    def _field(self, context):
        _ob, rec = extrude.active(context)
        if rec is None or self.row >= len(rec.spec.fields):
            return rec, None
        return rec, rec.spec.fields[self.row]

    def invoke(self, context, event):
        rec, field = self._field(context)
        if field is None:
            return {'CANCELLED'}
        if field in INT_FIELDS:
            self.count = int(rec.params[field])
        else:
            self.number = float(rec.params[field])
        return context.window_manager.invoke_props_dialog(self, title=f"{rec.name}: {rec.spec.labels[field]}")

    def draw(self, context):
        rec, field = self._field(context)
        if field is not None:
            self.layout.prop(self, "count" if field in INT_FIELDS else "number", text=rec.spec.labels[field])

    def execute(self, context):
        _rec, field = self._field(context)
        if field is None:
            return {'CANCELLED'}
        from . import node_attributes
        value = self.count if field in INT_FIELDS else self.number
        value = node_attributes.target(context).descriptor(field).limit(value)
        res = extrude.set_params(context, **{field: value})
        _redraw(context)
        return res


class ALLSET_OT_extrude_drag(bpy.types.Operator):
    """Drag a handle of the extrude manipulator (Maya polyExtrudeFace Local Translate / Local Scale; Local
    Translate Z of an edge extrusion, Length of a vertex extrusion)"""
    bl_idname = "allset.extrude_drag"
    bl_label = "Extrude Manipulator"
    bl_options = {'INTERNAL'}

    handle: StringProperty(default="TZ", options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        rec = extrude.active(context)[1]
        return rec is not None and rec.spec.arrow is not None and context.region_data is not None

    def _ray(self, context, event):
        region, rv3d = context.region, context.region_data
        co = (event.mouse_region_x, event.mouse_region_y)
        return (view3d_utils.region_2d_to_origin_3d(region, rv3d, co),
                view3d_utils.region_2d_to_vector_3d(region, rv3d, co))

    def _along(self, context, event, axis):
        o, d = self._ray(context, event)
        hit = geometry.intersect_line_line(self._c, self._c + axis, o, o + d)
        return None if hit is None else (hit[0] - self._c).dot(axis)

    def _on_plane(self, context, event, normal):
        o, d = self._ray(context, event)
        return geometry.intersect_line_plane(o, o + d, self._c, normal)

    def _screen_dir(self, context, axis):
        region, rv3d = context.region, context.region_data
        p0 = view3d_utils.location_3d_to_region_2d(region, rv3d, self._c)
        p1 = view3d_utils.location_3d_to_region_2d(region, rv3d, self._c + axis * 1e-3)
        if p0 is None or p1 is None or (p1 - p0).length < 1e-9:
            return Vector((1.0, 0.0))
        return (p1 - p0).normalized()

    def invoke(self, context, event):
        from . import in_view_editor
        node = in_view_editor.model_target(context, fresh=True)
        ob, rec = (node.ob, node.record) if node is not None else (None, None)
        fields = handle_fields(rec, self.handle)
        frame = manip_frame(ob, rec) if fields else None
        if frame is None:
            return {'CANCELLED'}
        self._ob, self._rec, self._fields = ob, rec, fields
        self._c, axes, self._k = frame
        self._axes = [axes.col[i].copy() for i in range(3)]
        self._role, data, _f = HANDLES[self.handle]
        self._idx = [AXIS_INDEX[a] for a in data] if data else []
        self._start = dict(extrude.DEFAULTS, **rec.params)
        self._unit = units.maya_unit(context.scene)
        self._mouse0 = Vector((event.mouse_region_x, event.mouse_region_y))
        if self._role == 'ARROW':
            self._t0 = self._along(context, event, self._axes[self._idx[0]])
        elif self._role == 'PLANE':
            normal = self._axes[self._idx[0]].cross(self._axes[self._idx[1]])
            self._normal = normal
            self._h0 = self._on_plane(context, event, normal)
        elif self._role == 'CUBE':
            self._sdir = self._screen_dir(context, self._axes[self._idx[0]])
        self._last = {}
        self._button = event.type if event.type in {'LEFTMOUSE', 'MIDDLEMOUSE'} else 'LEFTMOUSE'
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def values(self, context, event):
        """{field: value} for the mouse at ``event`` (the press values while the drag has no reading yet)."""
        start, out = self._start, {}
        if self._role == 'ARROW':
            i = self._idx[0]
            t = self._along(context, event, self._axes[i])
            if t is None or self._t0 is None:
                return dict(self._last)
            out[self._fields[0]] = round(start[self._fields[0]] + (t - self._t0) / self._k[i] / self._unit, 4)
        elif self._role == 'PLANE':
            h = self._on_plane(context, event, self._normal)
            if h is None or self._h0 is None:
                return dict(self._last)
            d = h - self._h0
            for field, i in zip(self._fields, self._idx):
                out[field] = round(start[field] + d.dot(self._axes[i]) / self._k[i] / self._unit, 4)
        else:
            mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            if self._role == 'CUBE':
                dist = (mouse - self._mouse0).dot(self._sdir)
            else:   # centre: Maya's uniform scale follows the horizontal drag
                dist = mouse.x - self._mouse0.x
            factor = 1.0 + dist / (SCALE_PX * (_scale() or 1.0))      # ui_scale reads 0 in background
            for field in self._fields:
                out[field] = round(start[field] * factor, 4)
        self._last = out
        return dict(out)

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            params = dict(self._rec.params, **self.values(context, event))
            extrude.preview(self._ob, self._rec, params, self._unit)
            if self._fields[0] in self._rec.spec.fields:
                _state["hot"] = self._rec.spec.fields.index(self._fields[0])
                from . import in_view_editor, node_attributes
                in_view_editor.select(context, node_attributes.ModelingNode(self._ob, self._rec), self._fields[0])
            _redraw(context)
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            extrude.preview(self._ob, self._rec, {k: self._start[k] for k in self._rec.params}, self._unit)
            self._rec.live = False
            _redraw(context)
            return {'CANCELLED'}
        if event.type == self._button and event.value == 'RELEASE':
            changes = self.values(context, event)
            if changes:
                extrude.set_params(context, **changes)
            else:
                extrude.preview(self._ob, self._rec, {k: self._start[k] for k in self._rec.params}, self._unit)
                self._rec.live = False
            _redraw(context)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


# --- Channel Box INPUTS ------------------------------------------------------------------------------

def cb_record(context, ob):
    """The lead object's last extrusion for Channel Box INPUTS (any selection), or None."""
    if ob is None:
        return None
    if ob is not getattr(context, "edit_object", None):
        return extrude.object_record(ob)        # a node editable in object mode (UV > Automatic)
    return extrude.current(ob)


def _lead(context):
    return getattr(context, "edit_object", None) or getattr(context, "active_object", None)


def clamp(field, value):
    lo, hi = RANGES.get(field, (None, None))
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def _text_get(field):
    def get(_self):
        rec = cb_record(bpy.context, _lead(bpy.context))
        if rec is None or field not in rec.params:
            return ""
        return cb_entry.format_value(rec.params[field], rec.spec.kinds[field], bpy.context.scene)
    return get


def _text_set(field):
    def set_(_self, text):
        context = bpy.context
        rec = cb_record(context, _lead(context))
        if rec is None or field not in rec.params:
            return
        from . import node_attributes
        node = node_attributes.target(context)
        if node is None or not node_attributes.editable(node, field):
            return
        try:
            value = cb_entry.parse_entry(text, rec.params[field], rec.spec.kinds[field], context.scene)
        except (ValueError, TypeError, SyntaxError, NameError):
            return
        if field not in BOOL_FIELDS:
            value = node.descriptor(field).limit(value)
        if value != rec.params[field]:
            extrude.set_params(context, **{field: value})
    return set_


class ALLSET_PG_history(bpy.types.PropertyGroup):
    __annotations__ = {f"{f}_text": StringProperty(name=next(s.labels[f] for s in extrude.SPECS.values()
                                                             if f in s.fields),
                                                   get=_text_get(f), set=_text_set(f), options={'SKIP_SAVE'})
                       for f in ALL_FIELDS}


HISTORY_TIP = "Blender keeps no edit-mode history: only the last operation can be changed here."


def draw_cb_node(layout, context, rec):
    """The polyExtrudeFace node in Channel Box INPUTS; the Blender notice is the node name's
    tooltip (no Blender sentences in Maya windows). Collapsed until its name is clicked, like Maya
   ."""
    from . import channel_box
    lines = channel_box.as_lines(layout)
    ob = channel_box.lead(context)
    _row, opened = channel_box.node_row(lines, ob, channel_box.history_node(rec.name), rec.name, tip=HISTORY_TIP)
    if not opened:
        return
    hist = context.window_manager.allset_history
    for field in rec.spec.fields:
        row = lines.row()
        if row is None:
            continue
        split = row.split(factor=0.5, align=True)
        key = channel_box.model_key(rec, field)
        split.operator('allset.cb_select_channel', text=rec.spec.labels[field], emboss=False,
                       depress=key in channel_box.selected_channels(context)).key = key
        values = split.row()
        values.enabled = not channel_box.is_locked(ob, key)
        values.prop(hist, f"{field}_text", text="")


classes = (ALLSET_PG_history, ALLSET_GT_in_view_row, ALLSET_GGT_in_view, ALLSET_GT_extrude_handle,
           ALLSET_GGT_extrude,
           ALLSET_OT_inview_drag, ALLSET_OT_inview_type, ALLSET_OT_extrude_drag)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.allset_history = PointerProperty(type=ALLSET_PG_history)
    _state["handle"] = bpy.types.SpaceView3D.draw_handler_add(draw_box, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    if _state["handle"] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_state["handle"], 'WINDOW')
        _state["handle"] = None
    del bpy.types.WindowManager.allset_history
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
