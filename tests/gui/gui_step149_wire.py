"""#91 in the Maya Workflow Kit layout: the lead's green selection wire follows a
skinned cylinder while the scene plays and after it stops. Shots with ``--shots``.

Maya-unit chain (0,8,0) (0,4,0) (0,0,0) + the factory cylinder scaled (0.5, 4, 0.5), Bind Skin, joint2 Rotate X 0 at
frame 1 / 45 at frame 10; play, stop, then the wire pixels must sit on the deformed bottom ring (not the rest one)."""

import math
import os
import sys
from importlib import import_module

import bpy
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Euler, Vector

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
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step149_{name}_{scale():.2f}.png".replace(".", "", 1))
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def ring_points(evaluated):
    """Window pixel positions of the cylinder's bottom ring (rest or evaluated mesh)."""
    cyl = bpy.data.objects["pCylinder1"]
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    me = cyl.evaluated_get(bpy.context.evaluated_depsgraph_get()).data if evaluated else cyl.data
    rest = cyl.data.vertices
    low = min(x.co.z for x in rest)
    out = []
    for v, r in zip(me.vertices, rest):
        if r.co.z > low + 1e-6 or r.co.xy.length < 1e-6:      # bottom ring only (not the cap centre)
            continue
        p = location_3d_to_region_2d(region, rv3d, cyl.matrix_world @ v.co)
        if p is not None:
            out.append((region.x + int(p.x), region.y + int(p.y)))
    return out


def green_share(px, points, r=2):
    """Share of ``points`` with a lead-green pixel (#43ffa3) within ``r`` px."""
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
def s_rig():
    u = mod("operators.units").maya_unit(bpy.context.scene)
    joints = mod("operators.joints")
    with override():
        arm = joints.new_skeleton(bpy.context)
        parent = None
        for p in ((0, 0, 8 * u), (0, 0, 4 * u), (0, 0, 0)):
            parent = joints.add_joint(arm, Vector(p), parent, length=0.5 * u)
        joints.finish(bpy.context, arm, ["joint1", "joint2", "joint3"])
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.allset.create(kind='CYLINDER')
    cyl = bpy.data.objects["pCylinder1"]
    cyl.location = (0, 0, 4 * u)
    cyl.scale = (0.5, 0.5, 4.0)
    for o in bpy.context.scene.objects:
        o.select_set(o in (arm, cyl))
    bpy.context.view_layer.objects.active = cyl
    with override():
        bpy.ops.allset.bind_skin()
    check(f"#94 the scaled cylinder binds to every joint ({sorted(g.name for g in cyl.vertex_groups)})",
          sorted(g.name for g in cyl.vertex_groups) == ["joint1", "joint2", "joint3"])
    pb = arm.pose.bones["joint2"]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = (0, 0, 0)
    pb.keyframe_insert("rotation_euler", frame=1)
    pb.rotation_euler = (math.radians(45), 0, 0)
    pb.keyframe_insert("rotation_euler", frame=10)
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 10
    scene.frame_set(1)
    for o in scene.objects:
        o.select_set(o == cyl)
    bpy.context.view_layer.objects.active = cyl
    area, _region = view3d()
    area.spaces.active.region_3d.view_rotation = Euler((math.radians(90), 0, math.radians(90))).to_quaternion()   # side (-X)
    with override():
        bpy.ops.view3d.view_selected()
    redraw()


step(redraw)


@step
def s_play():
    shot("rest")
    with override():
        bpy.ops.screen.animation_play()


for _i in range(8):
    step(redraw)


@step
def s_playing():
    C["playing"] = shot("playing")
    C["playing_frame"] = bpy.context.scene.frame_current
    C["playing_ring"] = ring_points(True)


@step
def s_stop():
    with override():
        bpy.ops.screen.animation_cancel(restore_frame=False)
    bpy.context.scene.frame_set(10)
    redraw()


step(redraw)
step(redraw)


@step
def s_stopped():
    px = shot("stopped")
    deformed, rest = ring_points(True), ring_points(False)
    moved = sum(1 for a, b in zip(deformed, rest) if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 6)
    print("GUI149 wire", "playing frame", C.get("playing_frame"), "ring", len(deformed), "moved", moved, flush=True)
    check(f"the bottom ring moved on screen at frame 10 ({moved}/{len(deformed)} points > 6 px)",
          moved >= len(deformed) // 2 and len(deformed) >= 8)
    on_deformed, on_rest = green_share(px, deformed), green_share(px, rest)
    check(f"#91 stopped: lead wire on the deformed ring ({on_deformed:.2f}), not at rest ({on_rest:.2f})",
          on_deformed > 0.6 and on_rest < 0.3)
    if C.get("playing") is not None and C["playing_frame"] != 1:
        share = green_share(C["playing"], C["playing_ring"])
        check(f"#91 playing (frame {C['playing_frame']}): lead wire on the deformed ring ({share:.2f})", share > 0.6)



@step
def s_lattice():
    """A selected lattice gets Maya's lead green wire too (Blender draws it in the theme's orange)."""
    u = mod("operators.units").maya_unit(bpy.context.scene)
    lat = bpy.data.lattices.new("ffd1LatticeShape")
    lat.points_u, lat.points_v, lat.points_w = 2, 5, 2
    ob = bpy.data.objects.new("ffd1Lattice", lat)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (0, 6 * u, 4 * u)
    ob.scale = (2 * u, 2 * u, 8 * u)
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    redraw()


step(redraw)


@step
def s_lattice_shot():
    px = shot("lattice")
    ob = bpy.data.objects["ffd1Lattice"]
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    co, ed = mod("ui.selection_wire").lattice_edges(ob.data)
    pts = []
    for a, b in ed:        # edge midpoints (corners can hide under other drawing)
        p = location_3d_to_region_2d(region, rv3d, ob.matrix_world @ Vector(((co[a] + co[b]) / 2).tolist()))
        if p is not None:
            pts.append((region.x + int(p.x), region.y + int(p.y)))
    share = green_share(px, pts)
    check(f"selected lattice drawn in the lead green ({share:.2f} of {len(pts)} edge midpoints)",
          share > 0.6 and len(pts) >= 20)


run()
