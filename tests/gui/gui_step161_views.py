"""G3 / G4 in the Maya Workflow Kit layout: the Space-tap four view shows Maya-style
ortho cameras (about 30 units across), and the lead's green wire stays
drawn in a side view maximised from the four view (step-154 dogfood shots 08 / 09). Shots with ``--shots``."""

import os
import sys
from importlib import import_module

import bpy
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, scale, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def shot(name):
    """Window screenshot as (h, w, 3) floats, row 0 = window bottom; also kept in SHOTS."""
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step161_{name}_{scale():.2f}.png".replace(".", "", 1))
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def windows_regions():
    """(main area, WINDOW regions of every viewport panel) — the four view is four real 3D View areas."""
    area, _r = view3d()
    fv = mod("ui.four_view")
    return area, [r for a in fv.panes(win().screen) for r in a.regions if r.type == 'WINDOW']


def units_across(region, rv3d):
    """Maya units across the region's width (the scene's Maya unit)."""
    u = mod("operators.units").maya_unit(bpy.context.scene)
    a = location_3d_to_region_2d(region, rv3d, Vector((0, 0, 0)))
    side = rv3d.view_rotation @ Vector((u, 0, 0))
    b = location_3d_to_region_2d(region, rv3d, side)
    if a is None or b is None:
        return None
    return region.width / max(1e-9, (b - a).length)


def toggle(region):
    area = next(a for a in win().screen.areas if any(r == region for r in a.regions))
    with bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active,
                                   region_data=region.data):
        bpy.ops.allset.toggle_quad_view()


def outline_points(region, rv3d, ob):
    """Window pixels of the cube's edges (sampled) in this region."""
    me = ob.data
    out = []
    for e in me.edges:
        p0, p1 = (ob.matrix_world @ me.vertices[i].co for i in e.vertices)
        for t in (0.25, 0.5, 0.75):
            p = location_3d_to_region_2d(region, rv3d, p0.lerp(p1, t))
            if p is not None and 2 < p.x < region.width - 2 and 2 < p.y < region.height - 2:
                out.append((region.x + int(p.x), region.y + int(p.y)))
    return out


def green_share(px, points, r=2):
    hits = 0
    for x, y in points:
        patch = px[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
        g = (patch[..., 1] > 0.8) & (patch[..., 0] < 0.5) & (patch[..., 2] > 0.4) & (patch[..., 2] < 0.8)
        hits += bool(g.any())
    return hits / max(1, len(points))


@step
def s_setup():
    setup()
    load_maya_layout()


for _i in range(6):
    step(redraw)


@step
def s_cube():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.data.objects["pCube1"]
    # the dogfood session (tools/dogfood_session.py): Ctrl+D -> pCube2 at x 3, P under pCube1, then F on pCube1
    u = mod("operators.units").maya_unit(bpy.context.scene)
    dup = ob.copy()
    dup.data = ob.data.copy()
    bpy.context.scene.collection.objects.link(dup)
    dup.name = "pCube2"
    dup.parent = ob
    dup.location.x = 3 * u
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    rv3d = area.spaces.active.region_3d
    rv3d.view_location = ob.location
    rv3d.view_distance = 3 * u
    C["quads0"] = len(area.spaces.active.region_quadviews)
    toggle(region)
    redraw()


step(redraw)
step(redraw)


@step
def s_quad():
    area, regions = windows_regions()
    check(f"Space tap: four views ({len(regions)})", len(regions) == 4)
    widths = {}
    for r in regions:
        rv3d = r.data
        if rv3d.view_perspective == 'ORTHO':
            widths[rv3d.view_perspective + str(round(r.x)) + "," + str(round(r.y))] = units_across(r, rv3d)
    C["widths"] = widths
    print("GUI quad ortho widths", widths, [r.data.view_distance for r in regions], flush=True)
    check(f"G3 three ortho panes ({len(widths)})", len(widths) == 3)
    check(f"G3 each ortho pane is a Maya-style ortho camera: about 30 units across, not zoomed in ({widths})",
          all(w is not None and 24 <= w <= 40 for w in widths.values()))
    redraw()


@step
def s_quad_shot():
    area, regions = windows_regions()
    px = shot("quad")
    ob = bpy.data.objects["pCube1"]
    shares = []
    for r in regions:
        if r.data.view_perspective == 'ORTHO':
            pts = outline_points(r, r.data, ob)
            shares.append(green_share(px, pts))
    check(f"G4 the lead's green wire in the ortho panes ({shares})", shares and min(shares) > 0.6)
    # the side pane: the ortho view looking along X
    side = None
    for r in regions:
        d = r.data.view_rotation @ Vector((0, 0, -1))
        if r.data.view_perspective == 'ORTHO' and abs(d.x) > 0.99:
            side = r
    check("the four view has a side pane", side is not None)
    # G3 Maya grids every ortho panel edge to edge in its own plane (16_four_view.png)
    for r in regions:
        if r.data.view_perspective != 'ORTHO':
            continue
        patch = px[r.y + 4:r.y + r.height - 4, r.x + 4:r.x + r.width - 4]
        grey = np.all(np.abs(patch - 64 / 255) < 6 / 255, axis=-1)
        rows = grey.mean(axis=1) > 0.5          # horizontal grid lines run across the whole pane
        cols = grey.mean(axis=0) > 0.5
        check(f"G3 the {mod('operators.view').ortho_key(r.data)} pane is gridded edge to edge "
              f"({int(rows.sum())} row / {int(cols.sum())} column lines)", rows.sum() >= 10 and cols.sum() >= 10)
    C["side"] = side.as_pointer() if side else None
    if side:
        side.data.view_distance *= 2.0          # the side camera zooms out: kept for the next four view
        toggle(side)
    redraw()


step(redraw)
step(redraw)


@step
def s_side_shot():
    area, region = view3d()
    space = area.spaces.active
    rv3d = space.region_3d
    n = len(windows_regions()[1])
    check(f"leaving the four view keeps the side view ({n} panels, {rv3d.view_perspective})",
          n == 1 and rv3d.view_perspective == 'ORTHO')
    px = shot("side")
    pts = outline_points(region, rv3d, bpy.data.objects["pCube1"])
    share = green_share(px, pts)
    print("GUI side", rv3d.view_distance, rv3d.view_location[:], units_across(region, rv3d), len(pts), flush=True)
    check(f"G4 the lead's green wire in the side view maximised from the four view ({share:.2f}, {len(pts)} pts)",
          pts and share > 0.6)
    child = bpy.data.objects["pCube2"]
    cshare = green_share(px, outline_points(region, rv3d, child))
    check(f"G4 Maya hierarchy highlight: the child pCube2 in front is drawn lead green too ({cshare:.2f})",
          cshare > 0.6)
    C["side_dist"] = rv3d.view_distance
    toggle(region)
    redraw()


step(redraw)
step(redraw)


@step
def s_quad_again():
    area, regions = windows_regions()
    got = {mod("operators.view").ortho_key(r.data): units_across(r, r.data) for r in regions
           if r.data.view_perspective == 'ORTHO'}
    print("GUI quad again", got, flush=True)
    others = [w for k, w in got.items() if not k.startswith("SIDE")]
    sides = [w for k, w in got.items() if k.startswith("SIDE")]
    check(f"G3 the ortho cameras keep their own zoom across layouts (side 60, others 30: {got})",
          sides and abs(sides[0] - 60) < 1 and others and all(abs(w - 30) < 1 for w in others))


run()
