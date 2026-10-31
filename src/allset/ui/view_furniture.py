# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya view furniture in the 3D View: ViewCube (top right), axis triad (bottom left), camera name label
(bottom centre), in place of Blender's navigation gizmo and text info.

The kit's views: ViewCube 65 px, 26 px from the view's right and 27 px from its top, white faces at
opacity 0.5 (FRONT/RIGHT/TOP readable in the default persp), only in the active panel of a four view;
label "persp" / "top -Y" ... 11 px #e3e3e3, baseline 9 px above the bottom, centred 9 px left of the
middle; axis triad origin 26 px from the left and bottom, 13 px lines, lower-case letters.

A view gets these when Blender's navigation gizmo is off in it (``show_gizmo_navigate``; the Maya Workflow Kit
template turns it and ``overlay.show_text`` off): the Maya furniture replaces Blender's. What is shown is
global like Maya's HUD / ViewCube preferences (add-on preferences ``maya_viewcube``,
``maya_camera_names``, ``maya_view_axis``). ``view_navigation`` = 'BLENDER' (#209) shows Blender's navigation gizmo
in those views instead of the ViewCube.

The triad shows Blender's axes (Z up): Maya's Y-up cannot be had and the
letters have to match the Channel Box channels. The camera labels are Maya's camera names with Maya's
Y-up view direction ("top -Y", "front -Z"): they name Maya's cameras, not axes.
"""

import math

import bpy
from mathutils import Vector

# --- Maya sizes and colours -----------------------------------------------------
CUBE_PX = 65.0                 # ViewCube box in a 612 px tall Maya view
CUBE_INSET = (26.0, 27.0)      # from the right, from the top
MAYA_VIEW_H = 612.0
SMALL_EXP = 0.42               # 65 px in the 612 px view, 48 px in a four-view panel
LABEL_BASELINE = 9.0
LABEL_SHIFT = -9.0
LABEL_PX = 11.0
LABEL_RGB = (0.89, 0.89, 0.89)
TRIAD_INSET = 26.0
TRIAD_LEN = 13.0
CUBE_ALPHA = (0.5, 1.0)        # resting, under the mouse
CUBE_EYE = 3.5526315789473686  # 5% gentler perspective; independent of scene focal length
MAYA_PERSP_DIR = Vector((-28.0, 28.0, -21.0)).normalized()   # Maya persp looking direction, Blender axes

# face -> (normal, text u axis, text v axis), Blender axes; names = view3d.view_axis types
FACES = {
    "TOP": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "BOTTOM": ((0, 0, -1), (1, 0, 0), (0, -1, 0)),
    "FRONT": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    "BACK": ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    "RIGHT": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "LEFT": ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
}
FACE_NAMES = tuple(FACES)
CONTROL_NAMES = ('HOME', 'ROLL_LEFT', 'ROLL_RIGHT', 'MENU')
ORBIT_CONTROLS = ('ORBIT_UP', 'ORBIT_DOWN', 'ORBIT_LEFT', 'ORBIT_RIGHT')

# Orthographic side views (key = the direction the view looks, Blender axes): Maya camera name + that direction
# in Maya's Y-up axes, as Maya prints it ("top -Y", "front -Z", "side -X";
# Blender X/Y/Z = Maya X/-Z/Y). Maya's own words, not Blender's axes.
SIDE_LABELS = {(0, 0, -1): "top -Y", (0, 0, 1): "bottom +Y", (0, 1, 0): "front -Z", (0, -1, 0): "back +Z",
               (-1, 0, 0): "side -X", (1, 0, 0): "left +X"}


# --- maths (mathutils only, no bpy) ---------------------------------------------------------

def _to_view(q, p):
    """World direction/point -> view space of a view whose rotation is ``q`` (view_rotation)."""
    return q.inverted() @ Vector(p)


def _project_cube_point(p, centre, k):
    """Project a view-space cube point; return screen coordinates and its perspective weight."""
    weight = CUBE_EYE - p.z
    factor = (CUBE_EYE - .5) / weight
    return (centre[0] + p.x * k * factor, centre[1] + p.y * k * factor), weight


def _extent(q):
    pts = [_project_cube_point(_to_view(q, (x, y, z)), (0, 0), 1)[0]
           for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)]
    return max(max(p[0] for p in pts) - min(p[0] for p in pts),
               max(p[1] for p in pts) - min(p[1] for p in pts))


def _maya_extent():
    return _extent(MAYA_PERSP_DIR.to_track_quat('-Z', 'Y'))


_PX_PER_UNIT = 1.0 / _maya_extent()   # cube scale that makes its box CUBE_PX tall in Maya's persp


def cube_size(width, height, scale=1.0):
    """ViewCube box size (px) for a view region: 65 px, smaller in small panels."""
    m = min(width, height) / (MAYA_VIEW_H * scale)
    return CUBE_PX * scale * min(1.0, m ** SMALL_EXP)


def faces_2d(q, centre, size):
    """Visible cube faces, back to front: [(name, polygon, facing, u2d, v2d)]."""
    k = size * _PX_PER_UNIT
    out = []
    for name, (n, u, v) in FACES.items():
        nv = _to_view(q, n)
        # Eye is at (0, 0, CUBE_EYE); the face centre is .5 along its normal.
        if nv.z * CUBE_EYE <= .5:
            continue
        nvec, uvec, vvec = Vector(n), Vector(u), Vector(v)
        poly = []
        for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            p = _to_view(q, nvec * .5 + uvec * .5 * su + vvec * .5 * sv)
            poly.append(_project_cube_point(p, centre, k)[0])
        u2, v2 = _to_view(q, u), _to_view(q, v)
        out.append((name, poly, nv.z, (u2.x, u2.y), (v2.x, v2.y)))
    out.sort(key=lambda f: f[2])
    return out


def _cube_rotation(rv3d):
    """Use the visible camera orientation in Camera View and the usual viewport rotation elsewhere."""
    if rv3d.view_perspective == 'CAMERA':
        return rv3d.view_matrix.inverted().to_quaternion()
    return rv3d.view_rotation


def _face_aligned(rv3d):
    """A roll is offered only when the visible view looks straight at a cube face."""
    forward = _cube_rotation(rv3d) @ Vector((0.0, 0.0, 1.0))
    return max(abs(forward.x), abs(forward.y), abs(forward.z)) >= 1.0 - 1e-5


def point_in_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def hit_face(faces, x, y):
    """Front-most face under (x, y), or None."""
    for name, poly, *_rest in reversed(faces):
        if point_in_poly(x, y, poly):
            return name
    return None


def label_for(perspective, side_view, view_dir, camera_name=None):
    """Maya camera label of a view: camera name, "top -Y" ... for side views, else "persp"."""
    if perspective == 'CAMERA' and camera_name:
        return camera_name
    if perspective == 'ORTHO' and side_view:
        key = tuple(int(round(c)) for c in view_dir)
        if key in SIDE_LABELS:
            return SIDE_LABELS[key]
    return "persp"


def layout(bounds, scale, size):
    """Region-local positions in a visible rect (x0, y0, x1, y1): cube centre, label (x centre,
    baseline y), triad origin."""
    x0, y0, x1, y1 = bounds
    cube = (x1 - CUBE_INSET[0] * scale - size / 2, y1 - CUBE_INSET[1] * scale - size / 2)
    label = ((x0 + x1) / 2 + LABEL_SHIFT * scale, y0 + LABEL_BASELINE * scale)
    triad = (x0 + TRIAD_INSET * scale, y0 + TRIAD_INSET * scale)
    return cube, label, triad


def triad(q, origin, length):
    """Axis lines on screen, back to front: [(axis index, end (x, y), depth)]."""
    out = []
    for i in range(3):
        d = [0.0, 0.0, 0.0]
        d[i] = 1.0
        p = _to_view(q, d)
        out.append((i, (origin[0] + p.x * length, origin[1] + p.y * length), p.z))
    out.sort(key=lambda a: a[2])
    return out


# --- per-view state -------------------------------------------------------------------------

def _prefs():
    from .. import preferences
    try:
        return preferences.get()
    except KeyError:
        return None


def maya_view(space):
    return space is not None and space.type == 'VIEW_3D' and space.overlay.show_overlays \
        and (not space.show_gizmo_navigate or space.as_pointer() in _SHOWN)


# --- Blender navigation gizmo instead of the ViewCube (#209) --------------------------------------------------------
# Add-on preference ``view_navigation``: 'VIEWCUBE' (Maya, default) or 'BLENDER'. With 'BLENDER' the kit turns
# Blender's navigation gizmo on in the Maya views (the views whose gizmo is off) and draws no ViewCube there; the
# camera name / view axis stay. Display > Heads Up Display > ViewCube (``maya_viewcube``) shows or hides whichever
# navigation widget is chosen. The kit gives every such view its flag back when the preference goes
# back, Maya mode goes off or the add-on is disabled, and around every save, so a file always holds the Maya view.

_SHOWN = set()        # pointers of the 3D View spaces whose navigation gizmo the kit turned on (this session)
_APPLY_LATER = []
_SAVING = []


def cube_wanted(prefs):
    """True when the kit draws its ViewCube (the HUD item is on and the Maya ViewCube is the chosen widget)."""
    return bool(prefs.maya_viewcube) and getattr(prefs, "view_navigation", 'VIEWCUBE') == 'VIEWCUBE'


def blender_gizmo_wanted(prefs):
    return prefs is not None and bool(prefs.maya_viewcube) and prefs.view_navigation == 'BLENDER'


def _spaces():
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    yield area, space


def _hideable(space):
    """A Maya view whose navigation gizmo the kit may turn on (not the Tool Box column)."""
    from . import toolbox
    return not space.show_gizmo_navigate and space.overlay.show_overlays and not toolbox.is_toolbox(space)


def apply_navigation(want=None):
    """Bring every 3D View in line with the preference (``want`` overrides it: False = give every flag back)."""
    if want is None:
        want = blender_gizmo_wanted(_prefs()) and not _SAVING
    live = set()
    for area, space in _spaces():
        ptr = space.as_pointer()
        live.add(ptr)
        if want and ptr not in _SHOWN and _hideable(space):
            space.show_gizmo_navigate = True
            _SHOWN.add(ptr)
            area.tag_redraw()
        elif not want and ptr in _SHOWN:
            if space.show_gizmo_navigate:
                space.show_gizmo_navigate = False
            _SHOWN.discard(ptr)
            area.tag_redraw()
    _SHOWN.intersection_update(live)      # closed areas: their pointers may be reused


def _apply_tick():
    _APPLY_LATER.clear()
    if _handle:
        apply_navigation()
    return None


def _apply_later():
    """A new Maya view (appended workspace, duplicated area) seen while drawing: apply from a timer."""
    if not _APPLY_LATER:
        _APPLY_LATER.append(_apply_tick)
        bpy.app.timers.register(_apply_tick, first_interval=0.0)


@bpy.app.handlers.persistent
def _save_pre(*_args):
    _SAVING.append(True)
    apply_navigation(False)


@bpy.app.handlers.persistent
def _save_post(*_args):
    _SAVING.clear()
    apply_navigation()


@bpy.app.handlers.persistent
def _load_pre(*_args):
    _SHOWN.clear()                        # the old file's spaces go: never compare their pointers again


@bpy.app.handlers.persistent
def _load_post(*_args):
    _SAVING.clear()
    apply_navigation()


_HANDLERS = (("save_pre", _save_pre), ("save_post", _save_post), ("load_pre", _load_pre),
             ("load_post", _load_post))


def _bounds(context):
    """Visible part of the region (sidebar / toolbar excluded), region-local."""
    from ..operators import view
    return view.visible_bounds(context.area, context.region)   # already region-local


def _scale():
    return bpy.context.preferences.system.ui_scale or 1.0


# Four view: the ViewCube shows in one panel only (Maya: the active panel), the last one the mouse was in.
_ACTIVE = {"region": None}


def _cube_here(context):
    space, region = context.space_data, context.region
    if not space.region_quadviews:
        return True
    if _ACTIVE["region"] is None:
        return region.data == space.region_3d
    return region.as_pointer() == _ACTIVE["region"]


# --- drawing --------------------------------------------------------------------------------

_shader = []
def _face_label(name, poly, facing, u2, size, alpha):
    """The face's name in Blender's UI font, centred on the projected face, along its text axis and never
    upside down."""
    cx = sum(p[0] for p in poly) / 4
    cy = sum(p[1] for p in poly) / 4
    ang = math.atan2(u2[1], u2[0])
    if math.cos(ang) < 0:
        ang += math.pi
    _text(name, cx, cy, max(6, round(size * 0.14 * facing ** 0.5)), (.16, .16, .16, min(1.0, alpha * 1.5)), ang)


def _arc_arrow(centre, radius, start, end, length, half_width):
    """Circular shaft with a separate, tangent-aligned triangular arrowhead."""
    direction = 1 if end > start else -1
    theta = math.radians(end)
    tx, ty = -direction * math.sin(theta), direction * math.cos(theta)
    x, y = centre
    tip = (x + radius * math.cos(theta), y + radius * math.sin(theta))
    base = (tip[0] - tx * length, tip[1] - ty * length)
    head = (tip, (base[0] - ty * half_width, base[1] + tx * half_width),
            (base[0] + ty * half_width, base[1] - tx * half_width))
    # Stop inside the triangle's base; no round stroke cap crosses its point.
    shaft_end = end - direction * math.degrees(length * .8 / radius)
    steps = max(12, math.ceil(abs(shaft_end - start) / 4))
    shaft = [(x + radius * math.cos(a), y + radius * math.sin(a))
             for a in (math.radians(start + (shaft_end-start)*i/steps) for i in range(steps+1))]
    return shaft, head


def _roll_arrows(context, centre, size):
    """Two separated arcs of one circle around the projected face's upper-right corner."""
    faces = faces_2d(_cube_rotation(context.region_data), centre, size)
    points = [p for face in faces for p in face[1]]
    if not points:
        return {}
    x0, x1 = min(p[0] for p in points), max(p[0] for p in points)
    y0, y1 = min(p[1] for p in points), max(p[1] for p in points)
    radius = min(x1-x0, y1-y0) * .48
    s = _scale()
    length, width = min(4.5*s, radius*.22), min(2.6*s, radius*.13)
    return {'ROLL_LEFT': _arc_arrow((x1,y1), radius, 55, 100, length, width),
            'ROLL_RIGHT': _arc_arrow((x1,y1), radius, 32, -5, length, width)}


def control_layout(context, centre, size):
    """Corner controls and the four small arrows around an aligned face."""
    s = _scale()
    x, y = centre
    radius = min(9 * s, size * .14)
    controls = {'HOME': (x - size * .57, y + size * .72, radius),
            'ROLL_LEFT': (x + size * .40, y + size * .78, radius),
            'ROLL_RIGHT': (x + size * .54, y + size * .48, radius),
            'MENU': (x + size * .67, y - size * .55, radius),
            'ORBIT_UP': (x, y + size * .52, radius * .72),
            'ORBIT_DOWN': (x, y - size * .52, radius * .72),
            'ORBIT_LEFT': (x - size * .52, y, radius * .72),
            'ORBIT_RIGHT': (x + size * .52, y, radius * .72)}
    for name, (shaft, head) in _roll_arrows(context, centre, size).items():
        vertices = [*shaft, *head]
        left, right = min(p[0] for p in vertices), max(p[0] for p in vertices)
        bottom, top = min(p[1] for p in vertices), max(p[1] for p in vertices)
        controls[name] = ((left+right)/2, (bottom+top)/2, max(radius,(right-left)/2,(top-bottom)/2))
    return controls


def _control_at(centre, controls, location, face_aligned):
    """Hit visible control targets or the narrow path leading from the cube to each target."""
    eligible = [(name, data) for name, data in controls.items()
                if not name.startswith(('ROLL', 'ORBIT')) or face_aligned]
    px, py = location
    # A control's own circular target wins over another control's approach path.
    for name, (x, y, radius) in eligible:
        if (px - x) ** 2 + (py - y) ** 2 <= radius ** 2:
            return name
    for name, (x, y, radius) in eligible:
        dx, dy = x - centre[0], y - centre[1]
        length_sq = dx * dx + dy * dy
        if length_sq <= 1e-12:
            continue
        t = ((px - centre[0]) * dx + (py - centre[1]) * dy) / length_sq
        if 0.0 <= t <= 1.0:
            ex, ey = centre[0] + t * dx, centre[1] + t * dy
            if (px - ex) ** 2 + (py - ey) ** 2 <= (radius * .45) ** 2:
                return name
    return None


def _draw_controls(context, centre, size, hover):
    arrows = _roll_arrows(context, centre, size)
    for name, (x, y, radius) in control_layout(context, centre, size).items():
        if name.startswith(('ROLL', 'ORBIT')) and not _face_aligned(context.region_data):
            continue
        colour = (.55, .78, .98, 1.0) if hover == name else (.82, .85, .88, .88)
        r = radius * .55
        if name == 'HOME':
            points, head = _arc_arrow((x,y), r, 550, 225, r*.65, r*.29)
            _lines(points, colour, 1.4 * _scale(), context.region)
            _fill(head, colour)
            continue
        elif name == 'MENU':
            points = [(x-r, y+r*.35), (x, y-r*.45), (x+r, y+r*.35)]
        elif name.startswith('ORBIT'):
            dx, dy = {'ORBIT_UP': (0, 1), 'ORBIT_DOWN': (0, -1),
                      'ORBIT_LEFT': (-1, 0), 'ORBIT_RIGHT': (1, 0)}[name]
            dx, dy = -dx, -dy  # The small triangles point toward the cube.
            _fill([(x+dx*r, y+dy*r),
                   (x-dx*r*.6-dy*r, y-dy*r*.6+dx*r),
                   (x-dx*r*.6+dy*r, y-dy*r*.6-dx*r)], colour)
            continue
        else:
            points, head = arrows[name]
            _lines(points, colour, 1.8 * _scale(), context.region)
            _fill(head, colour)
            continue
        _lines(points, colour, 1.5 * _scale(), context.region)


def _sh():
    if not _shader:
        import gpu
        _shader.append(gpu.shader.from_builtin('UNIFORM_COLOR'))
        _shader.append(gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR'))
    return _shader


def _fill(poly, colour):
    from gpu_extras.batch import batch_for_shader
    sh = _sh()[0]
    batch = batch_for_shader(sh, 'TRI_FAN', {"pos": poly})
    sh.uniform_float("color", colour)
    batch.draw(sh)


def _fill_cube_face(poly, name, facing, alpha):
    """World-up lighting: bright upper face, darker underside, smooth sides."""
    import gpu
    from gpu_extras.batch import batch_for_shader
    shaders = _sh()
    if len(shaders) == 2:
        shaders.append(gpu.shader.from_builtin('SMOOTH_COLOR'))
    normal, u, v = FACES[name]
    colours = []
    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        height = .5 + .5 * (normal[2] + u[2] * su + v[2] * sv)
        shade = (.77 + .22 * height) * (.92 + .08 * facing)
        colours.append((shade, shade, shade, alpha))
    shader = shaders[2]
    batch = batch_for_shader(shader, 'TRI_FAN', {'pos': poly, 'color': colours})
    shader.bind()
    batch.draw(shader)


def _lines(points, colour, width, region, loop=False):
    from gpu_extras.batch import batch_for_shader
    sh = _sh()[1]
    pts = list(points) + ([points[0]] if loop else [])
    batch = batch_for_shader(sh, 'LINE_STRIP', {"pos": [(x, y, 0.0) for x, y in pts]})
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    sh.uniform_float("lineWidth", width)
    sh.uniform_float("color", colour)
    batch.draw(sh)


def _text(s, x, y, px, colour, angle=0.0, centre=True):
    import blf
    fid = 0
    blf.size(fid, px)
    w, h = blf.dimensions(fid, s)
    if angle:
        blf.enable(fid, blf.ROTATION)
        blf.rotation(fid, angle)
    if centre:
        c, sn = math.cos(angle), math.sin(angle)
        x, y = x - (c * w / 2 - sn * h / 2), y - (sn * w / 2 + c * h / 2)
    blf.color(fid, *colour)
    blf.position(fid, x, y, 0)
    blf.draw(fid, s)
    if angle:
        blf.disable(fid, blf.ROTATION)


def draw_cube(context, hover=None, alpha=0.5):
    region, rv3d = context.region, context.region_data
    s = _scale()
    size = cube_size(region.width, region.height, s)
    centre, _label, _triad = layout(_bounds(context), s, size)
    q = _cube_rotation(rv3d)
    faces = faces_2d(q, centre, size)
    for name, poly, facing, u2, _v2 in faces:
        import gpu
        gpu.state.blend_set('ALPHA')
        if name == hover:
            _fill(poly, (0.55, 0.75, 0.95, alpha))
        else:
            _fill_cube_face(poly, name, facing, alpha)
        _lines(poly, (0.418, 0.418, 0.418, alpha), 1.95, region, loop=True)
        if facing > 0.28:
            _face_label(name, poly, facing, u2, size, alpha)
    if hover is not None:
        _draw_controls(context, centre, size, hover)
    return faces


def _draw_hud():
    context = bpy.context
    space, region, rv3d = context.space_data, context.region, context.region_data
    if rv3d is None or not maya_view(space):
        return
    prefs = _prefs()
    if prefs is None:
        return
    _check_strip(context)
    if not space.show_gizmo_navigate and blender_gizmo_wanted(prefs) and _hideable(space):
        _apply_later()
    import gpu
    s = _scale()
    _cube, label, origin = layout(_bounds(context), s, 0.0)
    gpu.state.blend_set('ALPHA')
    if prefs.maya_camera_names:
        cam = context.scene.camera
        d = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
        text = label_for(rv3d.view_perspective, rv3d.is_orthographic_side_view, tuple(d),
                         cam.name if cam else None)
        import blf
        blf.size(0, round(LABEL_PX * s))
        w = blf.dimensions(0, text)[0]
        _text(text, label[0] - w / 2, label[1], round(LABEL_PX * s), (*LABEL_RGB, 1.0), centre=False)
    if prefs.maya_view_axis:
        ui = context.preferences.themes[0].user_interface
        colours = (ui.axis_x, ui.axis_y, ui.axis_z)
        for i, end, _depth in triad(rv3d.view_rotation, origin, TRIAD_LEN * s):
            rgb = tuple(colours[i])[:3]
            gpu.state.blend_set('ALPHA')
            _lines((origin, end), (*rgb, 1.0), 1.0, region)
            dx, dy = end[0] - origin[0], end[1] - origin[1]
            n = math.hypot(dx, dy) or 1.0
            _text("xyz"[i], end[0] + dx / n * 5 * s, end[1] + dy / n * 5 * s, round(10 * s), (*rgb, 1.0))
    gpu.state.blend_set('NONE')


def _hud_callback():
    try:
        _draw_hud()
    except Exception:  # never let a draw error repeat every frame
        import traceback
        traceback.print_exc()
        _remove_handler()


# --- asset shelf strip ----------------------------------------------------------
# Pose / paint modes give the view an ASSET_SHELF_HEADER region (29 px at the bottom) that never draws
# while the shelf is collapsed: it expects Region Overlap, which Maya mode turns off. Without overlap the
# WINDOW region shrinks above it and the strip keeps the pixels drawn there before the mode change — the camera
# label and triad showed twice ("persp" under "persp"). A draw handler on that region is never called,
# so the strip is hidden instead (screen.region_toggle; Maya has no asset shelf) and shown again when the shelf is
# opened or the kit unregisters. The HUD draw sees the state; the toggle runs from a timer.

def strip_action(area, overlap):
    """'HIDE' / 'SHOW' for the asset shelf header of ``area``, or None."""
    shelf = next((r for r in area.regions if r.type == 'ASSET_SHELF'), None)
    header = next((r for r in area.regions if r.type == 'ASSET_SHELF_HEADER'), None)
    if shelf is None or header is None:
        return None
    if header.height > 1 and shelf.height <= 1 and not overlap:
        return 'HIDE'
    if header.height <= 1 and area.as_pointer() in _HIDDEN and (shelf.height > 1 or overlap):
        return 'SHOW'
    return None


_HIDDEN = set()       # area pointers whose shelf header the kit hid (this session)
_PENDING = {}        # area pointer -> its timer function


def _toggle_strip(window, area):
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return False
    with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region):
        return bpy.ops.screen.region_toggle(region_type='ASSET_SHELF_HEADER') == {'FINISHED'}


def _strip_later(area_ptr):
    def tick():
        _PENDING.pop(area_ptr, None)
        overlap = bpy.context.preferences.system.use_region_overlap
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.as_pointer() != area_ptr:
                    continue
                act = strip_action(area, overlap)
                if act and _toggle_strip(window, area):
                    (_HIDDEN.add if act == 'HIDE' else _HIDDEN.discard)(area_ptr)
                    area.tag_redraw()
        return None
    if area_ptr not in _PENDING:
        _PENDING[area_ptr] = tick
        bpy.app.timers.register(tick, first_interval=0.0)


def _check_strip(context):
    area = context.area
    if area is not None and strip_action(area, context.preferences.system.use_region_overlap):
        _strip_later(area.as_pointer())


def _show_strips():
    """Unregister: give back every shelf header the kit hid."""
    wm = getattr(bpy.context, "window_manager", None)
    for window in (wm.windows if wm else ()):
        for area in window.screen.areas:
            if area.as_pointer() in _HIDDEN:
                header = next((r for r in area.regions if r.type == 'ASSET_SHELF_HEADER'), None)
                if header is not None and header.height <= 1:
                    try:
                        _toggle_strip(window, area)
                    except RuntimeError:
                        pass
    _HIDDEN.clear()
    for tick in _PENDING.values():
        if bpy.app.timers.is_registered(tick):
            bpy.app.timers.unregister(tick)
    _PENDING.clear()


_handle = []


def _remove_handler():
    while _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle.pop(), 'WINDOW')


# --- ViewCube gizmo -------------------------------------------------------------------------

class ALLSET_OT_view_cube_control(bpy.types.Operator):
    """Navigate the current viewport without moving the scene camera"""
    bl_idname = 'allset.view_cube_control'
    bl_label = 'ViewCube Navigation'
    bl_options = {'INTERNAL'}

    action: bpy.props.EnumProperty(items=[(name, name.replace('_', ' ').title(), '')
                                         for name in CONTROL_NAMES])

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and context.region is not None and context.region.type == 'WINDOW'
                and context.region_data is not None)

    def execute(self, context):
        rv = context.region_data
        if self.action == 'MENU':
            bpy.ops.wm.call_menu('INVOKE_DEFAULT', name=ALLSET_MT_view_cube.__name__)
            return {'FINISHED'}
        if self.action == 'HOME':
            previous = rv.view_perspective
            if previous == 'CAMERA':
                rv.view_perspective = 'PERSP'
            try:
                result = bpy.ops.allset.view_home('EXEC_DEFAULT', True) if bpy.ops.allset.view_home.poll() else {'CANCELLED'}
            except RuntimeError:
                result = {'CANCELLED'}
            if result != {'FINISHED'} and previous == 'CAMERA':
                rv.view_perspective = previous
            return result
        if self.action not in {'ROLL_LEFT', 'ROLL_RIGHT'} or not _face_aligned(rv):
            return {'CANCELLED'}
        if not bpy.ops.view3d.view_roll.poll():
            return {'CANCELLED'}
        previous = rv.view_perspective
        if previous == 'CAMERA':
            visible_rotation = _cube_rotation(rv)
            previous_rotation = rv.view_rotation.copy()
            rv.view_perspective = 'PERSP'
            rv.view_rotation = visible_rotation
        try:
            result = bpy.ops.view3d.view_roll('EXEC_DEFAULT', True, type='ANGLE',
                        angle=(1 if self.action == 'ROLL_LEFT' else -1) * math.pi / 2)
        except RuntimeError:
            result = {'CANCELLED'}
        if result != {'FINISHED'} and previous == 'CAMERA':
            rv.view_rotation = previous_rotation
            rv.view_perspective = previous
        context.area.tag_redraw()
        return result

    def invoke(self, context, event):
        # Open the popup after release so the click that opened it cannot choose an item.
        if self.action == 'MENU' and event.value == 'PRESS':
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        return self.execute(context)

    def modal(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return self.execute(context)
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class ALLSET_MT_view_cube(bpy.types.Menu):
    bl_label = 'ViewCube'

    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'INVOKE_REGION_WIN'
        layout.operator('allset.view_cube_control', text='Home View').action = 'HOME'
        layout.operator('view3d.view_persportho', text='Perspective / Orthographic')
        layout.separator()
        for name in FACE_NAMES:
            layout.operator('view3d.view_axis', text=name.title()).type = name


def _ensure_cube_controls(gizmo):
    if getattr(gizmo, '_view_controls_ready', False) == 2:
        return
    for i, name in enumerate(CONTROL_NAMES + ORBIT_CONTROLS, len(FACE_NAMES)):
        if name in ORBIT_CONTROLS:
            op = gizmo.target_set_operator('view3d.view_orbit', index=i)
            op.type = name.replace('_', '')
            op.angle = math.pi / 2
        else:
            op = gizmo.target_set_operator('allset.view_cube_control', index=i)
            op.action = name
    gizmo._view_controls_ready = 2


class ALLSET_GT_view_cube(bpy.types.Gizmo):
    bl_idname = "ALLSET_GT_view_cube"

    def setup(self):
        self.hover = None
        self.use_tooltip = False          # like the kit's other gizmos: no Blender operator tooltip
        # one view3d.view_axis call per face: test_select returns the face's index as the part
        for i, name in enumerate(FACE_NAMES):
            op = self.target_set_operator("view3d.view_axis", index=i)
            op.type = name

    def draw(self, context):
        if not _cube_here(context):
            return
        _ensure_cube_controls(self)
        import gpu
        from mathutils import Matrix
        region = context.region
        w, h = region.width, region.height
        ortho = Matrix(((2 / w, 0, 0, -1), (0, 2 / h, 0, -1), (0, 0, -1, 0), (0, 0, 0, 1)))
        with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity()
            gpu.matrix.load_projection_matrix(ortho)
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('NONE')
            draw_cube(context, self.hover if self.is_highlight else None,
                      CUBE_ALPHA[1] if self.is_highlight else CUBE_ALPHA[0])
            gpu.state.blend_set('NONE')

    def test_select(self, context, location):
        _ensure_cube_controls(self)
        space, region = context.space_data, context.region
        if space.region_quadviews and _ACTIVE["region"] != region.as_pointer():
            _ACTIVE["region"] = region.as_pointer()
            context.area.tag_redraw()
        s = _scale()
        size = cube_size(region.width, region.height, s)
        centre, _l, _t = layout(_bounds(context), s, size)
        faces = faces_2d(_cube_rotation(context.region_data), centre, size)
        controls = control_layout(context, centre, size)
        # Preserve every existing face target even where a control's radius overlaps it.
        name = hit_face(faces, *location)
        if name is None:
            name = _control_at(centre, controls, location, _face_aligned(context.region_data))
        if name != self.hover:
            self.hover = name
            context.area.tag_redraw()
        names = FACE_NAMES + CONTROL_NAMES + ORBIT_CONTROLS
        return names.index(name) if name else -1


class ALLSET_GGT_view_cube(bpy.types.GizmoGroup):
    bl_idname = "ALLSET_GGT_view_cube"
    bl_label = "Maya ViewCube"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        prefs = _prefs()
        space = context.space_data
        return prefs is not None and cube_wanted(prefs) and maya_view(space) and space.show_gizmo \
            and context.region_data is not None

    def setup(self, context):
        self.gizmos.new(ALLSET_GT_view_cube.bl_idname)


classes = (ALLSET_OT_view_cube_control, ALLSET_MT_view_cube, ALLSET_GT_view_cube, ALLSET_GGT_view_cube)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _handle.append(bpy.types.SpaceView3D.draw_handler_add(_hud_callback, (), 'WINDOW', 'POST_PIXEL'))
    for name, fn in _HANDLERS:
        getattr(bpy.app.handlers, name).append(fn)
    try:
        apply_navigation()
    except AttributeError:               # Blender start: restricted bpy.data while add-ons register
        _apply_later()


def unregister():
    for name, fn in _HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if fn in handlers:
            handlers.remove(fn)
    if _APPLY_LATER and bpy.app.timers.is_registered(_apply_tick):
        bpy.app.timers.unregister(_apply_tick)
    _APPLY_LATER.clear()
    _SAVING.clear()
    try:
        apply_navigation(False)
    except AttributeError:               # restricted bpy.data (quit): nothing of this session is saved any more
        pass
    finally:
        _SHOWN.clear()
    _remove_handler()
    _show_strips()
    _ACTIVE["region"] = None
    _shader.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
