"""In a real UI: Maya selection colours without a theme.

Object mode: the lead's wire is green #43ffa3, another selected object's white, an unselected object has none.
Edit mode (ui/component_colors.py): vertex mode = selected vertex #fdff88, unselected #c800c8, edges #64dcff;
edge mode = selected edge #e3ac79; face mode = a 1-in-4 stipple #e3ac79 on the selected face. Then the frame time
of a 100k-vertex edit mesh with and without the kit colours."""

import os
import sys
import time
from importlib import import_module

import bmesh
import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, win, load_maya_layout, view3d, scale  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


LEAD, OTHER = hexrgb("#43ffa3"), hexrgb("#ffffff")
HILITE, VERT, VERT_SEL, EDGE_SEL = hexrgb("#64dcff"), hexrgb("#c800c8"), hexrgb("#fdff88"), hexrgb("#e3ac79")


def prefs():
    return bpy.context.preferences.addons[MODULE].preferences


def shot(name):
    """Window screenshot as (h, w, 3) sRGB floats, row 0 = window bottom; also kept in SHOTS."""
    import gpu
    backend = gpu.platform.backend_type_get()
    tag = f"{scale():.2f}".replace(".", "") + ("" if backend == 'OPENGL' else "_" + backend.lower())
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step134_{name}_{tag}.png")
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def near(px, colour, tol=0.09):
    return np.abs(px - colour).max(axis=-1) < tol


def hits(px, xy, colour, r=1, tol=0.09):
    """Any pixel within r px of window point xy is ``colour``."""
    x, y = int(round(xy[0])), int(round(xy[1]))
    return bool(near(px[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1], colour, tol).any())


def to_window(world):
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area, region = view3d()
    p = location_3d_to_region_2d(region, area.spaces.active.region_3d, world)
    return None if p is None else (p.x + region.x, p.y + region.y)


def depth(world):
    area, _region = view3d()
    return -(area.spaces.active.region_3d.view_matrix @ world).z


def edge_points(ob):
    mw = ob.matrix_world
    return [(mw @ ((ob.data.vertices[a].co + ob.data.vertices[b].co) / 2)) for a, b in
            (e.vertices for e in ob.data.edges)]


def _hull(pts):
    """Convex hull (counter-clockwise) of 2D points (monotone chain)."""
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def covered(xy, ob, margin=4.0):
    """Window point ``xy`` lies on (or within ``margin`` px of) ``ob``'s screen silhouette: an edge of another object
    drawn there may carry ``ob``'s wire colour (the narrower viewport made the cubes overlap)."""
    pts = [to_window(ob.matrix_world @ v.co) for v in ob.data.vertices]
    hull = _hull([(p[0], p[1]) for p in pts if p is not None])
    if len(hull) < 3:
        return False
    for (x0, y0), (x1, y1) in zip(hull, hull[1:] + hull[:1]):
        ex, ey = x1 - x0, y1 - y0
        length = (ex * ex + ey * ey) ** 0.5 or 1.0
        if (ex * (xy[1] - y0) - ey * (xy[0] - x0)) / length < -margin:   # outside this edge (CCW hull)
            return False
    return True


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    unit = import_module(MODULE + ".operators.units").maya_unit()
    obs = []
    with bpy.context.temp_override(window=win(), area=area, region=region):
        for x in (0.0, 2.2, -2.2):
            bpy.ops.allset.create(kind='CUBE')
            ob = bpy.context.view_layer.objects.active
            ob.location = (x * unit, 0.0, 0.5 * unit)
            obs.append(ob)
        lead, other, rest = obs
        for ob in bpy.context.scene.objects:
            ob.select_set(ob in (lead, other))
        bpy.context.view_layer.objects.active = lead
        bpy.ops.view3d.view_selected()
    C["names"] = [o.name for o in obs]
    # rest the pointer in the viewport's empty corner: over the cube the kit's red pre-selection highlight of the
    # hovered component is drawn on top of the selection colours the shots check
    ev('MOUSEMOVE', 'NOTHING', x=region.x + 12, y=region.y + 12)
    redraw()


@step
def s_object_mode():
    lead, other, rest = (bpy.data.objects[n] for n in C["names"])
    px = shot("object")
    on = {}
    for ob, col in ((lead, LEAD), (other, OTHER), (rest, LEAD)):
        pts = [to_window(p) for p in edge_points(ob)]
        if ob is rest:      # only rest's own edges: skip spots the selected cubes' silhouettes cover
            pts = [p for p in pts if p is not None and not covered(p, lead) and not covered(p, other)]
            C["rest_pts"] = len(pts)
        on[ob.name] = sum(1 for p in pts if p is not None and hits(px, p, col))
    check(f"object mode: lead {lead.name} wire Maya green #43ffa3 on {on[lead.name]}/12 edges (>= 7)",
          on[lead.name] >= 7)
    check(f"object mode: other selected {other.name} wire white on {on[other.name]}/12 edges (>= 7)",
          on[other.name] >= 7)
    check(f"object mode: unselected {rest.name} has no green wire ({on[rest.name]}/{C['rest_pts']} uncovered edges)",
          on[rest.name] == 0 and C["rest_pts"] >= 4)
    # Blender's own orange (factory theme active object) must not show around the lead in the Maya layout
    theme = np.array(bpy.context.preferences.themes[0].view_3d.object_active[:3])
    pts = np.array([to_window(p) for p in edge_points(lead)])
    x0, y0 = (pts.min(axis=0) - 6).astype(int)
    x1, y1 = (pts.max(axis=0) + 6).astype(int)
    orange = int(near(px[y0:y1, x0:x1], theme, 0.06).sum())
    green = int(near(px[y0:y1, x0:x1], LEAD).sum())
    check(f"object mode: lead box green {green} px, Blender theme orange {orange} px (no outline in the Maya layout)",
          green > 30 and orange < green // 10)
    # vertex edit mode on the lead alone, the vertex nearest to the camera and its neighbour selected
    for ob in bpy.context.scene.objects:
        ob.select_set(ob == lead)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.tool_settings.mesh_select_mode = (True, False, False)
        bpy.ops.mesh.select_all(action='DESELECT')
    mw = lead.matrix_world
    order = sorted(range(8), key=lambda i: depth(mw @ lead.data.vertices[i].co))
    C["order"] = order
    bm = bmesh.from_edit_mesh(lead.data)
    bm.verts.ensure_lookup_table()
    bm.verts[order[0]].select = True
    bm.select_flush_mode()
    bmesh.update_edit_mesh(lead.data)
    redraw()


def _bm_world(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm, ob.matrix_world


@step
def s_vertex_mode():
    lead = bpy.data.objects[C["names"][0]]
    px = shot("verts")
    bm, mw = _bm_world(lead)
    order = C["order"]
    sel = to_window(mw @ bm.verts[order[0]].co)
    uns = [to_window(mw @ bm.verts[i].co) for i in order[1:4]]
    check("vertex mode: the selected vertex is yellow #fdff88", hits(px, sel, VERT_SEL))
    n = sum(hits(px, p, VERT) for p in uns)
    check(f"vertex mode: unselected visible vertices are purple #c800c8 ({n}/3)", n >= 2)
    # the points have the theme Vertex Size x UI scale (a backend that ignores the point size draws one pixel)
    cc = import_module(MODULE + ".ui.component_colors")
    want = [max(1, round(s * scale())) for s in cc.theme_point_sizes(bpy.context)]
    big = [int(near(px[int(p[1]) - 6:int(p[1]) + 7, int(p[0]) - 6:int(p[0]) + 7], VERT).sum()) for p in uns]
    big_sel = int(near(px[int(sel[1]) - 6:int(sel[1]) + 7, int(sel[0]) - 6:int(sel[0]) + 7], VERT_SEL).sum())
    check(f"vertex mode: points follow the theme Vertex Size ({want[0]} / {want[1]} px wide): selected point "
          f"{big_sel} px, unselected {big}", big_sel >= want[1] ** 2 // 2 and max(big) >= want[0] ** 2 // 2)
    near_edges = [e for e in bm.edges if bm.verts[order[0]] not in e.verts and
                  any(v.index in order[1:4] for v in e.verts)]
    n = sum(hits(px, to_window(mw @ ((e.verts[0].co + e.verts[1].co) / 2)), HILITE) for e in near_edges)
    check(f"vertex mode: edges are Maya hilite blue #64dcff ({n}/{len(near_edges)})", n >= 1)
    # edge mode: the front edge (both ends among the nearest vertices) selected
    with bpy.context.temp_override(window=win(), area=view3d()[0], region=view3d()[1]):
        bpy.context.tool_settings.mesh_select_mode = (False, True, False)
        bpy.ops.mesh.select_all(action='DESELECT')
    bm, mw = _bm_world(lead)
    front = next(e for e in bm.edges if {v.index for v in e.verts} <= set(order[:3]))
    front.select_set(True)
    C["edge"] = front.index
    bmesh.update_edit_mesh(lead.data)
    redraw()


@step
def s_edge_mode():
    lead = bpy.data.objects[C["names"][0]]
    px = shot("edges")
    bm, mw = _bm_world(lead)
    e = bm.edges[C["edge"]]
    mid = to_window(mw @ ((e.verts[0].co + e.verts[1].co) / 2))
    check("edge mode: the selected edge is Maya orange #e3ac79", hits(px, mid, EDGE_SEL))
    others = [x for x in bm.edges if x.index != C["edge"] and {v.index for v in x.verts} <= set(C["order"][:4])]
    n = sum(hits(px, to_window(mw @ ((x.verts[0].co + x.verts[1].co) / 2)), HILITE) for x in others)
    check(f"edge mode: unselected front edges stay hilite blue ({n}/{len(others)})", n >= 1)
    # face mode: the face most facing the camera
    with bpy.context.temp_override(window=win(), area=view3d()[0], region=view3d()[1]):
        bpy.context.tool_settings.mesh_select_mode = (False, False, True)
        bpy.ops.mesh.select_all(action='DESELECT')
    bm, mw = _bm_world(lead)
    area, _r = view3d()
    vdir = area.spaces.active.region_3d.view_rotation @ bpy.types.Vector((0, 0, -1)) if hasattr(bpy.types, "Vector") \
        else None
    from mathutils import Vector
    vdir = area.spaces.active.region_3d.view_rotation @ Vector((0, 0, -1))
    face = min(bm.faces, key=lambda f: (mw.to_3x3() @ f.normal).normalized().dot(vdir))
    face.select_set(True)
    C["face"] = face.index
    bmesh.update_edit_mesh(lead.data)
    redraw()


@step
def s_face_mode():
    lead = bpy.data.objects[C["names"][0]]
    px = shot("faces")
    bm, mw = _bm_world(lead)
    f = bm.faces[C["face"]]
    c = to_window(mw @ f.calc_center_median())
    r = max(4, round(4 * scale()))
    x, y = int(c[0]), int(c[1])
    win_px = px[y - r:y + r, x - r:x + r]
    frac = float(near(win_px, EDGE_SEL, 0.09).mean())
    check(f"face mode: selected face is the stipple #e3ac79 ({frac * 100:.0f} % of pixels, ~25 %)",
          0.15 < frac < 0.4)
    # the pixels between the stipple dots keep the face's own grey (Blender's face tint is off)
    rest = win_px[~near(win_px, EDGE_SEL, 0.09)]
    sat = float((rest.max(axis=-1) - rest.min(axis=-1)).mean()) if len(rest) else 1.0
    space = view3d()[0].spaces.active
    check(f"no Blender face tint under the stipple (show_faces {space.overlay.show_faces}, "
          f"grey spread {sat:.3f} < 0.05)", not space.overlay.show_faces and sat < 0.05)
    # 100k-vertex mesh in edit mode: frame time with and without the kit component colours
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='OBJECT')
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob)
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=317, y_subdivisions=317, size=0.3)
        bpy.ops.view3d.view_selected()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.tool_settings.mesh_select_mode = (True, False, False)
        bpy.ops.mesh.select_all(action='DESELECT')
    g = bpy.context.view_layer.objects.active
    bm = bmesh.from_edit_mesh(g.data)
    for v in list(bm.verts)[:20000]:
        v.select = True
    bm.select_flush_mode()
    bmesh.update_edit_mesh(g.data)
    C["verts"] = len(bm.verts)
    prefs().maya_component_colors = False
    redraw()


def frame_ms(n=30):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.redraw_timer(type='DRAW', iterations=5)
        t = time.perf_counter()
        bpy.ops.wm.redraw_timer(type='DRAW', iterations=n)
    return (time.perf_counter() - t) / n * 1000.0


@step
def s_time_off():
    C["off"] = frame_ms()
    redraw()


@step
def s_faces_back():
    # the kit gives the overlay back from a timer after a draw, so look one step after the timed draws
    check("preference off gives Blender's face highlight back (show_faces on)",
          view3d()[0].spaces.active.overlay.show_faces)
    prefs().maya_component_colors = True
    redraw()


@step
def s_time_on():
    cc = import_module(MODULE + ".ui.component_colors")
    C["on"] = frame_ms()
    g = bpy.context.view_layer.objects.active
    dg = bpy.context.view_layer.depsgraph
    reads, parts = [], []
    for _ in range(3):
        cc._dirty.add(g.name)
        t = time.perf_counter()
        st = cc.state(g, dg, False)
        t1 = time.perf_counter()
        st.batches = None
        cc._batches(st, (True, False, False))
        t2 = time.perf_counter()
        reads.append((t2 - t) * 1000.0)
        parts.append((round((t1 - t) * 1000, 1), round((t2 - t1) * 1000, 1)))
    print("GUI selection read / batch ms", parts)
    # PR #125 (2e8dcde, kept by the maintainer) rebuilds from the live edit BMesh so the highlight never lags the
    # selection: 101k vertices 36 -> 73 ms per rebuild (git bisect); the per-frame draw is unchanged.
    REBUILD_MS = 90.0
    print("GUI selection frame ms", C["verts"], C["off"], C["on"], "rebuild ms", reads)
    check(f"{C['verts']} vertices in edit mode: frame {C['off']:.2f} -> {C['on']:.2f} ms with Maya component "
          f"colours, cache rebuild {min(reads):.1f} ms (< {REBUILD_MS:.0f} ms)", st is not None and min(reads) < REBUILD_MS)
    shot("100k")


run()
