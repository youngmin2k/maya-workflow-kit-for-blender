# SPDX-License-Identifier: GPL-3.0-or-later
"""Joints drawn like Maya's in the Maya layout's 3D Views, in place of Blender's bone shapes.

Maya draws a joint as a wire sphere of three great circles in the joint's local XY, YZ and XZ planes, never filled,
1 px lines, at pure world size: the drawn radius is half the joint's Radius times the scene's Joint Size, with no
screen-size limit. Between a joint and each child it draws a wire four-sided pyramid: the square base stands across
the bone on the parent's sphere, turned with the parent's axes, its corners on that sphere; the apex touches the
child's sphere. A joint without children draws no bone.

Colours follow the selection: unselected joints dark violet, selected ones white, the lead (last selected) green; a
joint below a selected one takes that joint's colour, and a bone takes its parent joint's colour. Selected joints in a
perspective view also show short local axes (X red, Y green, Z blue). A shaded surface hides the joints behind or
inside it; X-Ray Joints, X-Ray and wireframe views draw them through every surface.

Here a skeleton's joints are its bones' heads (pose positions in Object / Pose Mode, edit bones in Edit Mode); in
Object Mode a selected skeleton object counts as its root joints selected. Bones with a custom shape draw that shape
instead. The kit draws only in 3D Views of the Maya layout's workspaces where Blender's Bones overlay is off — the kit
turns it off once per screen; a view whose Bones overlay is turned back on shows Blender's bones and no kit joints.
"""

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

UNSELECTED = (0x26 / 255, 0.0, 0x43 / 255)
SELECTED = (1.0, 1.0, 1.0)
LEAD = (0x43 / 255, 1.0, 0xa3 / 255)
AXIS_COLORS = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
SEGMENTS = 32
LINE_PX = 1.0
SETTLED = "allset_bones_settled"      # screen ID prop: the kit turned Blender's Bones overlay off in its 3D Views
MAYA_RADIUS = 1.0                     # Maya joint Radius default

_handle = []
_GEN = [0]          # bumped by every update that can change a drawn joint
_CACHE = {}         # space pointer -> (key, points, colours)
_COS = [math.cos(2.0 * math.pi * i / SEGMENTS) for i in range(SEGMENTS)]
_SIN = [math.sin(2.0 * math.pi * i / SEGMENTS) for i in range(SEGMENTS)]


# --- which views ------------------------------------------------------------------------------------------------

def maya_workspace(workspace):
    from .. import switch
    try:
        return switch.is_maya_workspace(workspace)
    except (ReferenceError, AttributeError):
        return False


def is_maya_view(space, workspace):
    """A 3D View where the kit draws the joints (and Blender's bones are off)."""
    from . import toolbox
    return (space is not None and workspace is not None and space.type == 'VIEW_3D' and not toolbox.is_toolbox(space)
            and space.overlay.show_overlays and not space.overlay.show_bones
            and space.show_object_viewport_armature and maya_workspace(workspace))


def settle(window):
    """Turn Blender's Bones overlay off in the 3D Views of ``window``'s screen once (Maya layout workspaces only)."""
    from . import toolbox
    screen = window.screen
    if screen is None or screen.get(SETTLED) or not maya_workspace(window.workspace):
        return False
    changed = False
    with bpy.context.temp_override(window=window, screen=screen):
        for area in screen.areas:
            space = area.spaces.active
            if area.type == 'VIEW_3D' and not toolbox.is_toolbox(space) and space.overlay.show_bones:
                space.overlay.show_bones = False
                area.tag_redraw()
                changed = True
    screen[SETTLED] = True
    return changed


def release_all():
    """Give Blender's bones back in every screen the kit settled (disable / Maya mode off)."""
    from . import toolbox
    for screen in bpy.data.screens:
        if not screen.get(SETTLED):
            continue
        for area in screen.areas:
            space = area.spaces.active
            if area.type == 'VIEW_3D' and not toolbox.is_toolbox(space):
                space.overlay.show_bones = True
                area.tag_redraw()
        del screen[SETTLED]


def _tick():
    try:
        for window in bpy.context.window_manager.windows:
            settle(window)
    except (ReferenceError, AttributeError, RuntimeError):
        pass
    return 0.5


# --- joints ------------------------------------------------------------------------------------------------------

def drawn_radius(bone, scene, arm_scale=1.0):
    """World radius of the drawn joint sphere: 0.5 x Radius x Joint Size (Maya units -> scene)."""
    from ..operators import joints, units
    r = float(bone.get(joints.RADIUS, MAYA_RADIUS))
    size = float(getattr(scene, "allset_joint_size", 1.0) or 1.0)
    return 0.5 * r * size * units.maya_unit(scene) * arm_scale


def _maya_q(bone):
    from ..operators import joints
    q = bone.get(joints.MAYA_FRAME)
    return Quaternion(q).to_matrix() if q is not None else None


class Joint:
    __slots__ = ("name", "parent", "centre", "frame", "radius", "shape", "children")

    def __init__(self, name, parent, centre, frame, radius, shape=None):
        self.name, self.parent, self.centre, self.frame, self.radius = name, parent, centre, frame, radius
        self.shape = shape          # (custom shape object, world matrix) or None
        self.children = []


def skeleton(ob, scene):
    """{name: Joint} of armature object ``ob`` in world space (visible joints only)."""
    from .. import compat
    from ..operators import joints
    from ..operators.joint_edit import local_frame
    mw = ob.matrix_world
    m3 = mw.to_3x3()
    s = max(mw.to_scale())
    out = {}
    if ob.mode == 'EDIT':
        for eb in ob.data.edit_bones:
            if eb.hide or _coll_hidden(eb):
                continue
            frame = (m3 @ local_frame(eb)).normalized()
            out[eb.name] = Joint(eb.name, eb.parent.name if eb.parent else None, mw @ eb.head, frame,
                                 drawn_radius(eb, scene, s))
    else:
        for pb in ob.pose.bones:
            bone = pb.bone
            if compat.bone_hidden(pb) or _coll_hidden(bone):
                continue
            f = m3 @ pb.matrix.to_3x3() @ joints.JOINT_AXES
            q = _maya_q(bone)
            frame = (f @ q if q is not None else f).normalized()
            shape = None
            if pb.custom_shape is not None:
                shape = (pb.custom_shape, mw @ _shape_matrix(pb))
            out[pb.name] = Joint(pb.name, bone.parent.name if bone.parent else None, mw @ pb.head, frame,
                                 drawn_radius(bone, scene, s), shape)
    for j in out.values():
        if j.parent in out:
            out[j.parent].children.append(j.name)
    return out


def _coll_hidden(bone):
    return bool(bone.collections) and not any(c.is_visible_effectively for c in bone.collections)


def _shape_matrix(pb):
    """Armature-space matrix Blender draws ``pb``'s custom shape with."""
    src = pb.custom_shape_transform or pb
    scale = Vector(pb.custom_shape_scale_xyz)
    if pb.use_custom_shape_bone_size:
        scale = scale * pb.bone.length
    return (src.matrix @ Matrix.Translation(pb.custom_shape_translation)
            @ pb.custom_shape_rotation_euler.to_matrix().to_4x4() @ Matrix.Diagonal(scale.to_4d()))


def selection(ob, joints_):
    """(selected joint names, lead name or None) of ``ob`` in Maya's terms."""
    from ..operators import joint_preview
    from ..operators.joint_selection import _edit_selected
    from .channel_box import bone_selected
    if joint_preview.running() and joint_preview.STATE.get("ob") == ob.name:
        cur = joint_preview.STATE.get("current")
        return ({cur} if cur else set()), cur          # the Joint Tool: the newest joint is the selection
    if ob.mode == 'EDIT':
        sel = {eb.name for eb in ob.data.edit_bones if eb.name in joints_ and _edit_selected(eb)}
        act = ob.data.edit_bones.active
    elif ob.mode == 'POSE':
        sel = {pb.name for pb in ob.pose.bones if pb.name in joints_ and bone_selected(pb)}
        act = ob.data.bones.active
    else:
        if not ob.select_get():
            return set(), None
        roots = [n for n, j in joints_.items() if j.parent is None]
        lead = roots[0] if roots and bpy.context.view_layer.objects.active == ob else None
        return set(roots), lead
    lead = act.name if act is not None and act.name in sel else None
    return sel, lead


def colours(joints_, sel, lead):
    """{name: colour}: own selection first, else the nearest selected joint above it, else unselected."""
    out = {}

    def colour(name):
        if name in out:
            return out[name]
        if name == lead:
            c = LEAD
        elif name in sel:
            c = SELECTED
        else:
            p = joints_[name].parent
            c = colour(p) if p in joints_ else UNSELECTED
        out[name] = c
        return c

    for n in joints_:
        colour(n)
    return out


def sphere_lines(c, frame, r):
    """Line segment end points of the three great circles."""
    x, y, z = frame.col[0], frame.col[1], frame.col[2]
    pts = []
    for a, b in ((x, y), (y, z), (x, z)):
        ring = [c + (a * _COS[i] + b * _SIN[i]) * r for i in range(SEGMENTS)]
        for i in range(SEGMENTS):
            pts += (ring[i], ring[(i + 1) % SEGMENTS])
    return pts


def bone_lines(parent, child):
    """The eight edges of the bone pyramid from ``parent`` to ``child`` (Joint), or [] when they overlap."""
    d = child.centre - parent.centre
    length = d.length
    if length <= parent.radius + child.radius or length < 1e-9:
        return []
    u = d / length
    base = parent.centre + u * parent.radius
    apex = child.centre - u * child.radius
    a = parent.frame.col[1] - u * parent.frame.col[1].dot(u)
    if a.length < 1e-6:
        a = parent.frame.col[2] - u * parent.frame.col[2].dot(u)
    a.normalize()
    b = u.cross(a)
    r = parent.radius
    corners = [base + a * r, base + b * r, base - a * r, base - b * r]
    pts = []
    for i in range(4):
        pts += (corners[i], corners[(i + 1) % 4], corners[i], apex)
    return pts


def shape_lines(ob, matrix, depsgraph):
    """World line segments of a custom shape's edges."""
    try:
        ev = ob.evaluated_get(depsgraph)
        me = ev.to_mesh()
    except (RuntimeError, AttributeError):
        return []
    try:
        vs = [matrix @ v.co for v in me.vertices]
        return [vs[i] for e in me.edges for i in e.vertices]
    finally:
        ev.to_mesh_clear()


def joint_segments(js, name, depsgraph=None):
    """World line segments drawn for joint ``name``: its sphere and its bones to the children (a bone belongs to
    its parent joint), or its custom shape. Flat list of end points."""
    j = js[name]
    if j.shape is not None:
        return shape_lines(j.shape[0], j.shape[1], depsgraph) if depsgraph is not None else []
    pts = sphere_lines(j.centre, j.frame, j.radius)
    for cn in j.children:
        if js[cn].shape is None:
            pts += bone_lines(j, js[cn])
    return pts


def depth(js, name):
    n, p = 0, js[name].parent
    while p in js:
        n, p = n + 1, js[p].parent
    return n


def _screen(context, pts):
    """(a, b, ok) screen end points of segments ``pts`` (pairs) in the context region; ok = both in front."""
    from ..operators.preselect import project
    region, rv3d = context.region, context.region_data
    xy, front = project([tuple(p) for p in pts], rv3d.perspective_matrix, region.width, region.height)
    return xy[0::2], xy[1::2], front[0::2] & front[1::2]


def screen_distance(context, ob, mouse):
    """{joint: screen distance from ``mouse`` to its drawn lines} of armature ``ob``."""
    from ..operators.preselect import segment_distance
    js = skeleton(ob, context.scene)
    dg = context.evaluated_depsgraph_get()
    out = {}
    for n in js:
        pts = joint_segments(js, n, dg)
        if not pts:
            continue
        a, b, ok = _screen(context, pts)
        if not ok.any():
            continue
        d, _t = segment_distance(mouse, a[ok], b[ok])
        out[n] = float(d.min())
    return out


def pick(context, ob, mouse, radius):
    """The joint of ``ob`` whose drawn line is nearest to ``mouse`` within ``radius`` px (Maya: a click hits the wire,
    not the inside of the sphere; a bone hit picks its parent joint), or None."""
    d = screen_distance(context, ob, mouse)
    near = [(v, n) for n, v in d.items() if v <= radius]
    return min(near)[1] if near else None


def _seg_cross(p1, p2, q1, q2):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def _in_poly(pt, poly):
    x, y = pt
    inside = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def segments_touch(a, b, poly):
    """Does any segment a[i]-b[i] touch the closed polygon ``poly`` (screen points)?"""
    edges = [(poly[i - 1], poly[i]) for i in range(len(poly))]
    for p, q in zip(a, b):
        if _in_poly(p, poly) or _in_poly(q, poly):
            return True
        if any(_seg_cross(p, q, e0, e1) for e0, e1 in edges):
            return True
    return False


def region_pick(context, ob, poly):
    """Maya marquee / lasso on a skeleton: the joints whose drawn lines touch ``poly``, kept to the one closest to
    the root (a box around a whole chain selects its top joint). Returns a joint name or None."""
    js = skeleton(ob, context.scene)
    dg = context.evaluated_depsgraph_get()
    hit = []
    for n in js:
        pts = joint_segments(js, n, dg)
        if not pts:
            continue
        a, b, ok = _screen(context, pts)
        if ok.any() and segments_touch([tuple(v) for v in a[ok]], [tuple(v) for v in b[ok]], poly):
            hit.append((depth(js, n), list(js).index(n), n))
    return min(hit)[2] if hit else None


def _sphere_array(js):
    """(points, joint order) of every sphere's three great circles as one float32 array of segment end points."""
    import numpy as np
    order = [n for n, j in js.items() if j.shape is None]
    if not order:
        return np.zeros((0, 3), np.float32), order
    c = np.array([tuple(js[n].centre) for n in order], np.float64)                  # (N, 3)
    f = np.array([[tuple(r) for r in js[n].frame] for n in order], np.float64)      # (N, 3, 3) rows
    r = np.array([js[n].radius for n in order], np.float64)[:, None, None]
    t = np.arange(SEGMENTS) * (2.0 * math.pi / SEGMENTS)
    cos, sin = np.cos(t)[:, None], np.sin(t)[:, None]
    rings = []
    for a, b in ((0, 1), (1, 2), (0, 2)):
        ring = c[:, None, :] + (f[:, None, :, a] * cos + f[:, None, :, b] * sin) * r      # (N, S, 3)
        rings.append(np.stack((ring, np.roll(ring, -1, axis=1)), axis=2))              # (N, S, 2, 3)
    pts = np.stack(rings, axis=1)                                                       # (N, 3, S, 2, 3)
    return pts.reshape(-1, 3).astype(np.float32), order


def view_lines(context):
    """(points, colours) float32 arrays of every joint to draw in this view."""
    import numpy as np
    space, rv3d = context.space_data, context.region_data
    scene = context.scene
    depsgraph = context.view_layer.depsgraph
    pts, cols = [], []
    per_sphere = 3 * SEGMENTS * 2

    def add(segs, colour):
        if segs:
            pts.append(np.array([tuple(v) for v in segs], np.float32))
            cols.append(np.tile(np.array((*colour, 1.0), np.float32), (len(segs), 1)))

    for ob in context.visible_objects:
        if ob.type != 'ARMATURE' or not ob.visible_in_viewport_get(space):
            continue
        js = skeleton(ob, scene)
        if not js:
            continue
        sel, lead = selection(ob, js)
        col = colours(js, sel, lead)
        spheres, order = _sphere_array(js)
        if order:
            pts.append(spheres)
            cols.append(np.repeat(np.array([(*col[n], 1.0) for n in order], np.float32), per_sphere, axis=0))
        bones = []
        bone_cols = []
        for j in js.values():
            if j.shape is not None:
                add(shape_lines(j.shape[0], j.shape[1], depsgraph), col[j.name])
                continue
            for cn in j.children:
                child = js[cn]
                if child.shape is None:
                    segs = bone_lines(j, child)
                    bones += segs
                    bone_cols += [col[j.name]] * len(segs)
            if j.name in sel and rv3d.is_perspective:
                for i in range(3):
                    add([j.centre, j.centre + j.frame.col[i] * j.radius], AXIS_COLORS[i])
        if bones:
            pts.append(np.array([tuple(v) for v in bones], np.float32))
            cols.append(np.array([(*c, 1.0) for c in bone_cols], np.float32))
    if not pts:
        return np.zeros((0, 3), np.float32), np.zeros((0, 4), np.float32)
    return np.concatenate(pts), np.concatenate(cols)


@bpy.app.handlers.persistent
def _depsgraph_post(_scene, depsgraph):
    """Drop the cached lines unless the update only touched objects that are no skeleton (a moved mesh)."""
    try:
        for u in depsgraph.updates:
            ob = u.id
            if isinstance(ob, bpy.types.Object) and ob.type not in {'ARMATURE', 'MESH', 'CURVE', 'EMPTY'}:
                continue
            if isinstance(ob, bpy.types.Object) and ob.type != 'ARMATURE' and not u.is_updated_geometry:
                continue
            _GEN[0] += 1
            return
    except (ReferenceError, AttributeError):
        _GEN[0] += 1


@bpy.app.handlers.persistent
def _frame_post(*_args):
    _GEN[0] += 1


def cached_view_lines(context):
    """``view_lines`` kept per view until a joint can have changed (any skeleton in Edit Mode: every redraw)."""
    from ..operators import joint_preview
    space = context.space_data
    if context.mode == 'EDIT_ARMATURE':
        return view_lines(context)
    key = (_GEN[0], context.region_data.is_perspective, context.scene.frame_current, context.scene.as_pointer(),
           context.view_layer.as_pointer(), space.local_view is not None, joint_preview.running(),
           str(joint_preview.STATE.get("current")))
    hit = _CACHE.get(space.as_pointer())
    if hit is not None and hit[0] == key:
        return hit[1], hit[2]
    pts, cols = view_lines(context)
    if len(_CACHE) > 32:
        _CACHE.clear()
    _CACHE[space.as_pointer()] = (key, pts, cols)
    return pts, cols


@bpy.app.handlers.persistent
def _save_pre(*_args):
    try:
        release_all()        # a saved file shows Blender's bones when it opens without the kit
    except (ReferenceError, AttributeError, RuntimeError):
        pass


@bpy.app.handlers.persistent
def _save_post(*_args):
    _tick()


def see_through(space):
    """Joints draw over every surface: X-Ray Joints, a wireframe view (no surface hides a joint, like Maya) or
    X-Ray shading."""
    shading = space.shading
    return bool(space.overlay.show_xray_bone or shading.type == 'WIREFRAME' or shading.show_xray)


def _draw():
    context = bpy.context
    try:
        if not is_maya_view(context.space_data, context.window.workspace):
            return
        pts, cols = cached_view_lines(context)
    except (ReferenceError, AttributeError, KeyError, ValueError, RuntimeError):
        return
    if not len(pts):
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    region = context.region
    sh = gpu.shader.from_builtin('POLYLINE_SMOOTH_COLOR')
    gpu.state.depth_test_set('NONE' if see_through(context.space_data) else 'LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    gpu.state.blend_set('ALPHA')
    try:
        sh.uniform_float("viewportSize", (region.width, region.height))
        sh.uniform_float("lineWidth", LINE_PX * context.preferences.system.pixel_size)
        batch_for_shader(sh, 'LINES', {"pos": pts, "color": cols}).draw(sh)
    finally:
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('NONE')


def HANDLERS():
    h = bpy.app.handlers
    return ((h.save_pre, _save_pre), (h.save_post, _save_post), (h.depsgraph_update_post, _depsgraph_post),
            (h.frame_change_post, _frame_post), (h.load_post, _frame_post), (h.undo_post, _frame_post),
            (h.redo_post, _frame_post))


def register():
    if not _handle:
        _handle.append(bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW'))
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.2, persistent=True)
    for lst, fn in HANDLERS():
        if fn not in lst:
            lst.append(fn)


def unregister():
    for lst, fn in HANDLERS():
        if fn in lst:
            lst.remove(fn)
    _CACHE.clear()
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    while _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle.pop(), 'WINDOW')
    try:
        release_all()
    except (ReferenceError, AttributeError, RuntimeError):
        pass
