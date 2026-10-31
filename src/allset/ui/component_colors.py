# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya-style component colours in mesh edit mode.

A mesh in component mode is drawn with these colours (at UI scale 1.0):
every visible edge 1 px hilite #64dcff; vertex mode: unselected vertices #c800c8 at the theme's Vertex Size
(factory 3 px), selected vertices #fdff88 one pixel larger; edge mode: selected edges #e3ac79; face mode:
selected faces a 1-in-4 pixel stipple #e3ac79, no fill.

Blender draws edit meshes with the user's theme (orange / black). The kit ships no theme,
so this POST_VIEW handler draws the Maya colours on top of Blender's own edit-mesh drawing (which stays under it).

Reading the edit mesh (a mesh of 101 124 vertices): the evaluated object's ``to_mesh()`` is the current
BMesh with ``.select_vert/edge/poly`` in ~4 ms; BMesh Python loops cost ~0.4 s. With a modifier shown in edit mode
the evaluated mesh is not the cage, so the cage is read from the BMesh, only up to ``BMESH_LIMIT`` vertices
(bigger meshes keep Blender's drawing). Arrays and GPU batches are cached per object and re-read when a
depsgraph update names the object or its mesh.

Selected faces: Blender's own selected-face tint (theme ``face_select``, drawn when the view's overlay
``show_faces`` is on) sat under the kit stipple and turned the 1-in-4 stipple into a near-opaque orange (pixels between the stipple
dots #9d856b where the unselected face is #747577; Maya keeps the base grey there). In a
Maya layout 3D View, while the kit draws every edited mesh, the view's ``overlay.show_faces`` is switched off (view
data, not preferences; from a timer, never inside the draw) and switched back when the kit stops drawing there
(preference off, mesh over ``BMESH_LIMIT``) and on unregister. Views the kit didn't switch are left alone.

Edges: Maya draws a thin hilite wire with crisp orange selected edges.
Kit primitives keep Maya's hard edges as ``sharp_edge``, so
Blender drew its theme sharp-edge colour (factory #00ffff) about 3 px wide around the kit's line (at UI 1.25,
cross-section of a silhouette edge: 519a9a 00dfdf 008a8a with the kit's 64dbff only in the middle) and the selected
edge looked like an orange sliver inside a thick cyan band. ``overlay.show_edge_sharp`` is now switched off with
``show_faces`` (Maya has no sharp-edge colour); Blender's plain edit edge left under the kit line is 2 px (474747 333333),
so the hilite line is 1.5 px x UI scale (2 px at 1.25, nothing of Blender's left; 1 px left a dark pixel beside it).
The lines also failed the depth test on one side of a silhouette edge (bias 0.0005): ``DEPTH_BIAS`` 0.002 for the
hilite wire, ``EDGE_SEL_BIAS`` 0.003 for selected edges, drawn last and 2 px so they stay on top.
"""

import bpy
import numpy as np

HILITE = "#64dcff"          # the object being edited, every edge
VERT = "#c800c8"            # unselected vertices
VERT_SEL = "#fdff88"        # selected vertices
EDGE_SEL = "#e3ac79"        # selected edges
FACE_SEL = "#e3ac79"        # selected face stipple
VERT_PX = 3.0               # pixel sizes at UI scale 1.0 when the theme vertex size can't be read
VERT_SEL_PX = 4.0           # selected = theme vertex size + 1 (Blender's factory 3 gives Maya's 3 / 4)
LINE_PX = 1.5               # thin lines; 1.5 x UI scale just covers Blender's own 2 px edit edge
EDGE_SEL_PX = 2.0           # selected edges a little wider, drawn over the hilite wire
BMESH_LIMIT = 50000         # cage read from the BMesh (modifiers shown in edit mode) only up to this many vertices
DEPTH_BIAS = 0.002          # relative pull toward the camera: 0.0005 lost the line's far side on silhouettes
EDGE_SEL_BIAS = 0.003       # selected edges in front of the hilite wire
FACE_BIAS = 0.0005          # selected face stipple
POINT_BIAS = 0.003          # vertices: Blender's own edit vertices write depth well in front of the surface

_handle = []
OVERLAY_OFF = ("show_faces", "show_edge_sharp")   # Blender edit-mesh overlays under the Maya look
_faces_off = set()          # (space pointer, overlay prop) the kit switched off (restored on unregister)
_pending = {}               # (space pointer, overlay prop) -> value the timer writes
_shader = {}
_cache = {}                 # (object pointer, mesh pointer) -> _State
_dirty = set()              # object / mesh names a depsgraph update touched since the last read
_times = []
_selection_snapshot = {}       # edit-mesh selection signatures for changes with no depsgraph notification
_POLL_INTERVAL = 0.15


# --- pure helpers (tests/test_step134_selection.py) -----------------------------------------------

def srgb(hex_str):
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class MeshArrays:
    """Edit cage arrays: co (n, 3) float32 object space, edges (e, 2) int32, per element select / hide bools,
    polygons as loop_start / loop_total into corner_vert."""
    __slots__ = ("co", "edges", "vsel", "vhide", "esel", "ehide", "fsel", "fhide", "loop_start", "loop_total",
                 "corner_vert")

    def __init__(self, co, edges, vsel=None, vhide=None, esel=None, ehide=None, fsel=None, fhide=None,
                 loop_start=None, loop_total=None, corner_vert=None):
        self.co = np.asarray(co, dtype=np.float32).reshape(-1, 3)
        self.edges = np.asarray(edges, dtype=np.int32).reshape(-1, 2)
        n, e = len(self.co), len(self.edges)
        f = 0 if loop_start is None else len(loop_start)

        def flags(a, k):
            return np.zeros(k, bool) if a is None else np.asarray(a, dtype=bool).reshape(-1)
        self.vsel, self.vhide = flags(vsel, n), flags(vhide, n)
        self.esel, self.ehide = flags(esel, e), flags(ehide, e)
        self.fsel, self.fhide = flags(fsel, f), flags(fhide, f)
        self.loop_start = np.zeros(0, np.int32) if loop_start is None else np.asarray(loop_start, np.int32)
        self.loop_total = np.zeros(0, np.int32) if loop_total is None else np.asarray(loop_total, np.int32)
        self.corner_vert = np.zeros(0, np.int32) if corner_vert is None else np.asarray(corner_vert, np.int32)


def point_sizes(theme_size):
    """(unselected, selected) vertex sizes at UI scale 1.0 for the theme's Vertex Size."""
    try:
        size = float(theme_size)
    except (TypeError, ValueError):
        return VERT_PX, VERT_SEL_PX
    if size <= 0:
        return VERT_PX, VERT_SEL_PX
    return size, size + 1.0


def theme_point_sizes(context):
    try:
        return point_sizes(context.preferences.themes[0].view_3d.vertex_size)
    except (AttributeError, IndexError):
        return VERT_PX, VERT_SEL_PX


def fan_triangles(loop_start, loop_total, corner_vert, mask):
    """Vertex index triangles (t, 3) of the polygons in ``mask``, fanned from each polygon's first corner."""
    start = np.asarray(loop_start, np.int64)[mask]
    total = np.asarray(loop_total, np.int64)[mask]
    ntri = np.maximum(total - 2, 0)
    if not len(ntri) or ntri.sum() == 0:
        return np.zeros((0, 3), np.int32)
    first = np.repeat(start, ntri)
    # i = 1 .. total-2 within each polygon
    offs = np.arange(ntri.sum()) - np.repeat(np.cumsum(ntri) - ntri, ntri) + 1
    cv = np.asarray(corner_vert, np.int64)
    return np.stack([cv[first], cv[first + offs], cv[first + offs + 1]], axis=1).astype(np.int32)


def layers(m, select_mode):
    """What to draw for the Maya component look: dict of index arrays into ``m.co``.

    edges: every visible edge (hilite); verts / verts_sel (vertex mode); edges_sel (edge mode); tris (face mode,
    selected visible faces). Hidden elements are never drawn."""
    vert_mode, edge_mode, face_mode = (bool(x) for x in select_mode)
    vis_e = ~m.ehide
    out = {"edges": m.edges[vis_e]}
    if vert_mode:
        vis = ~m.vhide
        out["verts"] = np.flatnonzero(vis & ~m.vsel).astype(np.int32)
        out["verts_sel"] = np.flatnonzero(vis & m.vsel).astype(np.int32)
    if edge_mode:
        out["edges_sel"] = m.edges[vis_e & m.esel]
    if face_mode:
        out["tris"] = fan_triangles(m.loop_start, m.loop_total, m.corner_vert, m.fsel & ~m.fhide)
    return out


def face_overlay_action(want_off, show_faces, ours):
    """What to do with a view's ``overlay.show_faces``: (value to write or None, kit owns the switch afterwards).

    ``want_off``: the kit draws the Maya face look in this view; ``ours``: the kit switched it off earlier. Only a
    switch the kit made is ever undone."""
    if want_off:
        return (False if show_faces else None), (ours or show_faces)
    if ours:
        return True, False
    return None, False


def use_evaluated(modifiers):
    """True when the evaluated edit mesh is the cage: no modifier is shown in edit mode."""
    return not any(md.show_viewport and md.show_in_editmode for md in modifiers)


def readable(n_verts, evaluated):
    """Whether the kit draws this mesh: the evaluated read is always fast, the BMesh read only up to BMESH_LIMIT."""
    return evaluated or n_verts <= BMESH_LIMIT


# --- reading the edit mesh -------------------------------------------------------------------------

def _attr(me, name, count):
    a = me.attributes.get(name)
    out = np.zeros(count, bool)
    if a is not None and count:
        a.data.foreach_get("value", out)
    return out


def read_evaluated(ob, depsgraph, faces=True):
    """MeshArrays of the evaluated edit mesh (no edit-mode modifiers: this is the cage); polygons only with
    ``faces`` (face select mode)."""
    ev = ob.evaluated_get(depsgraph)
    me = ev.to_mesh()
    try:
        n, e = len(me.vertices), len(me.edges)
        f, l = (len(me.polygons), len(me.loops)) if faces else (0, 0)
        co = np.empty(n * 3, np.float32)
        me.vertices.foreach_get("co", co)
        ed = np.empty(e * 2, np.int32)
        me.edges.foreach_get("vertices", ed)
        ls = np.empty(f, np.int32)
        me.polygons.foreach_get("loop_start", ls)
        lt = np.empty(f, np.int32)
        me.polygons.foreach_get("loop_total", lt)
        cv = np.empty(l, np.int32)
        me.loops.foreach_get("vertex_index", cv)
        return MeshArrays(co, ed, _attr(me, ".select_vert", n), _attr(me, ".hide_vert", n),
                          _attr(me, ".select_edge", e), _attr(me, ".hide_edge", e),
                          _attr(me, ".select_poly", f), _attr(me, ".hide_poly", f), ls, lt, cv)
    finally:
        ev.to_mesh_clear()


def read_bmesh(bm):
    """MeshArrays of the BMesh cage (Python loops: small meshes only)."""
    from itertools import chain
    bm.verts.index_update()
    n, e = len(bm.verts), len(bm.edges)
    co = np.fromiter(chain.from_iterable(v.co for v in bm.verts), np.float32, 3 * n)
    ed = np.fromiter(chain.from_iterable((x.verts[0].index, x.verts[1].index) for x in bm.edges), np.int32, 2 * e)
    lt = np.fromiter((len(f.verts) for f in bm.faces), np.int32, len(bm.faces))
    ls = (np.cumsum(lt) - lt).astype(np.int32)
    cv = np.fromiter(chain.from_iterable((v.index for v in f.verts) for f in bm.faces), np.int32, int(lt.sum()))
    return MeshArrays(co, ed,
                      np.fromiter((v.select for v in bm.verts), bool, n), np.fromiter((v.hide for v in bm.verts), bool, n),
                      np.fromiter((x.select for x in bm.edges), bool, e), np.fromiter((x.hide for x in bm.edges), bool, e),
                      np.fromiter((f.select for f in bm.faces), bool, len(bm.faces)),
                      np.fromiter((f.hide for f in bm.faces), bool, len(bm.faces)), ls, lt, cv)


class _State:
    __slots__ = ("arrays", "faces", "batches", "bkey", "name", "me_name")

    def __init__(self, ob):
        self.arrays = None
        self.faces = False          # arrays hold the polygons (read only in face select mode)
        self.batches = None
        self.bkey = None
        self.name = ob.name
        self.me_name = ob.data.name


# --- drawing ---------------------------------------------------------------------------------------

def _enabled():
    from .. import preferences
    try:
        return preferences.get().maya_component_colors
    except (KeyError, AttributeError):
        return False


def _builtin(name):
    if name not in _shader:
        import gpu
        _shader[name] = gpu.shader.from_builtin(name)
    return _shader[name]


def _stipple():
    if "stipple" not in _shader:
        import gpu
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4', 'ModelViewProjectionMatrix')
        info.push_constant('VEC4', 'color')
        info.vertex_in(0, 'VEC3', 'pos')
        info.fragment_out(0, 'VEC4', 'fragColor')
        info.vertex_source("void main() { gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0); }")
        # Maya's face stipple: one pixel in every 2 x 2 block
        info.fragment_source("void main() { ivec2 p = ivec2(gl_FragCoord.xy);"
                             " if (((p.x | p.y) & 1) != 0) { discard; } fragColor = color; }")
        _shader["stipple"] = gpu.shader.create_from_info(info)
    return _shader["stipple"]


def _linear(hex_str):
    from mathutils import Color
    c = Color(srgb(hex_str)).from_srgb_to_scene_linear()
    return (c.r, c.g, c.b, 1.0)


def _batches(st, select_mode):
    key = tuple(bool(x) for x in select_mode)
    if st.batches is not None and st.bkey == key:
        return st.batches
    from gpu_extras.batch import batch_for_shader
    m = st.arrays
    lay = layers(m, select_mode)
    flat = _builtin('UNIFORM_COLOR')
    poly = _builtin('POLYLINE_UNIFORM_COLOR')
    out = []

    def lines(idx, color, width, kind='LINES'):
        if len(idx):
            out.append((kind, poly, batch_for_shader(poly, 'LINES', {"pos": m.co[idx.reshape(-1)]}), color, width))

    def points(idx, color, size):
        if len(idx):
            out.append(('POINTS', flat, batch_for_shader(flat, 'POINTS', {"pos": m.co[idx]}), color, size))
    if "tris" in lay and len(lay["tris"]):
        sh = _stipple()
        out.append(('TRIS', sh, batch_for_shader(sh, 'TRIS', {"pos": m.co}, indices=lay["tris"]),
                    _linear(FACE_SEL), 0.0))
    lines(lay["edges"], srgb(HILITE) + (1.0,), LINE_PX)
    if "edges_sel" in lay:
        lines(lay["edges_sel"], srgb(EDGE_SEL) + (1.0,), EDGE_SEL_PX, 'LINES_SEL')
    if "verts" in lay:
        points(lay["verts"], srgb(VERT) + (1.0,), 0)          # size index into theme_point_sizes
        points(lay["verts_sel"], srgb(VERT_SEL) + (1.0,), 1)
    st.batches, st.bkey = out, key
    return out


def _biased_projection(rv3d, bias):
    import gpu
    from mathutils import Matrix
    p = Matrix(gpu.matrix.get_projection_matrix())
    if rv3d is not None and rv3d.is_perspective:
        p[2][3] -= bias * abs(p[2][3])
    else:
        p[2][3] -= bias * 0.1
    return p


def _xray(space):
    sh = space.shading
    return sh.show_xray_wireframe if sh.type == 'WIREFRAME' else sh.show_xray


def edit_objects(context):
    return [ob for ob in (context.objects_in_mode_unique_data or ()) if ob is not None and ob.type == 'MESH'
            and ob.visible_get()]


def state(ob, depsgraph, faces=True):
    """Up-to-date cached arrays of ``ob`` (None when the kit leaves this mesh to Blender's drawing); ``faces``:
    the polygons are needed too (face select mode)."""
    import bmesh
    key = (ob.as_pointer(), ob.data.as_pointer())
    st = _cache.get(key)
    if st is None or st.name != ob.name or st.me_name != ob.data.name:
        st = _cache[key] = _State(ob)
        st.arrays = None
    if st.arrays is not None and ob.name not in _dirty and ob.data.name not in _dirty and (st.faces or not faces):
        return st
    bm = bmesh.from_edit_mesh(ob.data)
    # Draw may run before the selection poll. Detect changed membership here.
    # This avoids presenting the previously cached GPU batch for one more frame.
    if len(bm.verts) <= BMESH_LIMIT:
        sig = _selection_signature(bm)
        if _selection_snapshot.get(key) != sig:
            _selection_snapshot[key] = sig
            _dirty.update((ob.name, ob.data.name))
    evaluated = use_evaluated(ob.modifiers)
    if not readable(len(bm.verts), evaluated):
        st.arrays = None
        return None
    # Blender 4.5: evaluated mesh selection attributes may lag behind the live
    # edit BMesh (notably when growing/shrinking selections without a geometry
    # dependency-graph update). Always obtain highlight flags from the BMesh.
    # For small meshes also read cage coordinates from the BMesh, avoiding stale
    # evaluated snapshots and preserving consistent element ordering.
    if len(bm.verts) <= BMESH_LIMIT:
        arrays, faces = read_bmesh(bm), True
    else:
        arrays = read_evaluated(ob, depsgraph, faces) if evaluated else None
        if arrays is None or len(arrays.co) != len(bm.verts) or len(arrays.edges) != len(bm.edges):
            return None
        # Keep evaluated coordinates on large meshes but use authoritative live
        # BMesh selection flags (the element order matches when lengths match).
        arrays.vsel = np.fromiter((v.select for v in bm.verts), bool, len(bm.verts))
        arrays.esel = np.fromiter((e.select for e in bm.edges), bool, len(bm.edges))
        if faces and len(arrays.fsel) == len(bm.faces):
            arrays.fsel = np.fromiter((f.select for f in bm.faces), bool, len(bm.faces))
    st.arrays, st.faces, st.batches, st.bkey = arrays, faces, None, None
    return st


def _maya_layout(context):
    from .shelf import strip_area
    return strip_area(context.screen) is not None


def _apply_pending():
    from .. import live_refs
    todo = dict(_pending)
    _pending.clear()
    for (ptr, prop), value in todo.items():
        _w, area, space = live_refs.find_space(ptr)
        if space is not None and getattr(space.overlay, prop) != value:
            setattr(space.overlay, prop, value)
            area.tag_redraw()
    return None


def _face_overlay(context, space, kit_draws):
    """Switch the OVERLAY_OFF overlays of this view off while the kit draws the Maya look in a Maya layout view."""
    want_off = kit_draws and _maya_layout(context)
    for prop in OVERLAY_OFF:
        key = (space.as_pointer(), prop)
        value, ours = face_overlay_action(want_off, getattr(space.overlay, prop), key in _faces_off)
        if ours:
            _faces_off.add(key)
        else:
            _faces_off.discard(key)
        if value is not None and _pending.get(key) != value:
            _pending[key] = value
            if not bpy.app.timers.is_registered(_apply_pending):
                bpy.app.timers.register(_apply_pending, first_interval=0.0)


def _draw():
    context = bpy.context
    if context.mode != 'EDIT_MESH':
        return
    space, rv3d, region = context.space_data, context.region_data, context.region
    if rv3d is None or space is None or region is None or not space.overlay.show_overlays:
        return
    if not _enabled():
        if _faces_off:
            _face_overlay(context, space, False)
        return
    from . import toolbox
    if toolbox.is_toolbox(space):
        return
    obs = edit_objects(context)
    if not obs:
        return
    import time
    import gpu
    t0 = time.perf_counter()
    depsgraph = context.view_layer.depsgraph
    select_mode = tuple(context.tool_settings.mesh_select_mode)
    states = []
    for ob in obs:
        st = state(ob, depsgraph, select_mode[2])
        if st is not None:
            states.append((ob, st))
    _dirty.difference_update({ob.name for ob in obs} | {ob.data.name for ob in obs})
    live = {(ob.as_pointer(), ob.data.as_pointer()) for ob in obs}
    for k in [k for k in _cache if k not in live]:
        del _cache[k]
    _face_overlay(context, space, len(states) == len(obs))
    if not states:
        return
    scale = context.preferences.system.ui_scale or 1.0
    vert_px = theme_point_sizes(context)
    gpu.state.depth_test_set('NONE' if _xray(space) else 'LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    proj = {'LINES': _biased_projection(rv3d, DEPTH_BIAS), 'TRIS': _biased_projection(rv3d, FACE_BIAS),
            'LINES_SEL': _biased_projection(rv3d, EDGE_SEL_BIAS), 'POINTS': _biased_projection(rv3d, POINT_BIAS)}
    gpu.matrix.push_projection()
    try:
        for ob, st in states:
            with gpu.matrix.push_pop():
                gpu.matrix.multiply_matrix(ob.matrix_world)
                for kind, sh, batch, color, size in _batches(st, select_mode):
                    gpu.matrix.load_projection_matrix(proj[kind])
                    sh.bind()
                    sh.uniform_float("color", color)
                    if kind == 'POINTS':
                        gpu.state.point_size_set(max(1.0, round(vert_px[size] * scale)))
                    elif kind in ('LINES', 'LINES_SEL'):
                        sh.uniform_float("viewportSize", (region.width, region.height))
                        sh.uniform_float("lineWidth", size * scale)
                    batch.draw(sh)
        gpu.state.point_size_set(1.0)
    finally:
        gpu.matrix.pop_projection()
        gpu.state.depth_test_set('NONE')
    _times.append(time.perf_counter() - t0)
    if len(_times) > 120:
        del _times[0]


def frame_ms():
    return sum(_times) / len(_times) * 1000.0 if _times else 0.0


def _callback():
    try:
        _draw()
    except Exception:
        # A transient graphics-context error must not permanently disable
        # highlighting until the entire add-on is reloaded.
        import traceback
        traceback.print_exc()


def _remove_handler():
    while _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle.pop(), 'WINDOW')


def _selection_signature(bm):
    """Track selection *membership*, not only counts (replace/add/subtract all matter).

    Blender does not always tag edit-mesh selection as a depsgraph update, especially
    when expanding an existing component selection. The overlay must not cache it forever.
    """
    return (len(bm.verts), len(bm.edges), len(bm.faces),
            tuple(v.index for v in bm.verts if v.select),
            tuple(e.index for e in bm.edges if e.select),
            tuple(f.index for f in bm.faces if f.select))


def _poll_selection():
    """Invalidate and redraw the Maya overlay when component selection changes."""
    if not _handle:
        return None
    try:
        import bmesh
        seen = set()
        changed = False
        wm = bpy.context.window_manager
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type != 'VIEW_3D':
                    continue
                with bpy.context.temp_override(window=window, area=area):
                    ctx = bpy.context
                    if ctx.mode != 'EDIT_MESH':
                        continue
                    for ob in edit_objects(ctx):
                        key = (ob.as_pointer(), ob.data.as_pointer())
                        if key in seen:
                            continue
                        seen.add(key)
                        bm = bmesh.from_edit_mesh(ob.data)
                        # Avoid scanning unusually large edit meshes on a UI timer.
                        if len(bm.verts) > BMESH_LIMIT:
                            continue
                        bm.verts.index_update()
                        bm.edges.index_update()
                        bm.faces.index_update()
                        sig = _selection_signature(bm)
                        if _selection_snapshot.get(key) != sig:
                            _selection_snapshot[key] = sig
                            _dirty.update((ob.name, ob.data.name))
                            changed = True
        for key in tuple(_selection_snapshot):
            if key not in seen:
                del _selection_snapshot[key]
        if changed:
            for window in wm.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
    except (AttributeError, ReferenceError, RuntimeError):
        pass  # transient area/mode changes while switching Blender screens
    return _POLL_INTERVAL


@bpy.app.handlers.persistent
def _on_depsgraph(_scene=None, depsgraph=None):
    if depsgraph is None or not _cache:
        return
    for u in depsgraph.updates:
        if isinstance(u.id, (bpy.types.Mesh, bpy.types.Object)):
            _dirty.add(u.id.original.name if u.id.original is not None else u.id.name)


@bpy.app.handlers.persistent
def _on_reload(*_args):
    _cache.clear()
    _dirty.clear()
    _selection_snapshot.clear()


_HANDLERS = (("depsgraph_update_post", _on_depsgraph), ("undo_post", _on_reload), ("redo_post", _on_reload),
             ("load_post", _on_reload))


def register():
    for name, fn in _HANDLERS:
        getattr(bpy.app.handlers, name).append(fn)
    _handle.append(bpy.types.SpaceView3D.draw_handler_add(_callback, (), 'WINDOW', 'POST_VIEW'))
    if not bpy.app.timers.is_registered(_poll_selection):
        bpy.app.timers.register(_poll_selection, first_interval=_POLL_INTERVAL)


def unregister():
    _remove_handler()
    if bpy.app.timers.is_registered(_poll_selection):
        bpy.app.timers.unregister(_poll_selection)
    for name, fn in _HANDLERS:
        lst = getattr(bpy.app.handlers, name)
        if fn in lst:
            lst.remove(fn)
    if bpy.app.timers.is_registered(_apply_pending):
        bpy.app.timers.unregister(_apply_pending)
    _pending.clear()
    for key in list(_faces_off):
        _pending[key] = True
    _faces_off.clear()
    _apply_pending()
    _cache.clear()
    _dirty.clear()
    _selection_snapshot.clear()
    _shader.clear()
    _times.clear()
