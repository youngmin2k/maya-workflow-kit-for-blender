"""#294 in a real UI: MMB-drag a camera from the Outliner into a viewport = that viewport looks through it (its own
camera); a mesh dropped on a viewport changes nothing; MMB drags inside the Outliner still parent."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, setup, step, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
NAMES = ("M", "cam1", "cam2")
C = {"rows": {}}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def outl():
    a = next(a for a in win().screen.areas if a.type == 'OUTLINER')
    return a, next(r for r in a.regions if r.type == 'WINDOW')


def row_xy(i):
    _a, r = outl()
    h = 20 * bpy.context.preferences.system.ui_scale
    _x, y = r.view2d.view_to_region(0, -(i + 0.5) * h, clip=False)
    return r.x + int(2.5 * h), r.y + int(y)


def view_xy():
    _a, r = view3d()
    return r.x + r.width // 2, r.y + r.height // 2


def space():
    return view3d()[0].spaces.active


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
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    col = bpy.context.scene.collection.children[0]
    for n in NAMES:
        data = bpy.data.cameras.new(n) if n.startswith("cam") else bpy.data.meshes.new(n)
        o = bpy.data.objects.new(n, data)
        col.objects.link(o)
    bpy.data.objects["cam1"].location = (0, -10, 0)
    bpy.data.objects["cam2"].location = (10, 0, 0)
    bpy.ops.ed.undo_push(message="scene")
    redraw()


def finder(i):
    def s_hover():
        x, y = row_xy(i)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)

    def s_hit():
        od = import_module(MODULE + ".operators.outliner_drag")
        a, r = outl()
        with bpy.context.temp_override(window=win(), area=a, region=r):
            o = od._first_object(od.hit_ids(bpy.context))
        if o is not None:
            C["rows"][o.name] = i
    return [s_hover, s_hit]


for _i in range(4):
    for _s in finder(_i):
        step(_s)


@step
def s_rows():
    check(f"Outliner rows found {C['rows']}", all(n in C["rows"] for n in NAMES))
    C["scene_cam"] = bpy.context.scene.camera
    C["before"] = (space().region_3d.view_perspective, space().camera, space().use_local_camera)


def drag(src, dst):
    """Steps: hover, MMB press, small move, move to dst (twice), release, wait."""
    def s1():
        ev('MOUSEMOVE', 'NOTHING', x=src()[0], y=src()[1])

    def s2():
        ev('MIDDLEMOUSE', 'PRESS')

    def s3():
        x, y = src()
        ev('MOUSEMOVE', 'NOTHING', x=x + 4, y=y - 12)

    def s4():
        ev('MOUSEMOVE', 'NOTHING', x=dst()[0], y=dst()[1])

    def s5():
        ev('MIDDLEMOUSE', 'RELEASE')

    def s6():
        redraw()
    for s in (s1, s2, s3, s4, s4, s5, s6):
        step(s)


# 1. a mesh dropped on the viewport: nothing changes (no parenting, same view)
drag(lambda: row_xy(C["rows"]["M"]), view_xy)


@step
def s_mesh_check():
    m = bpy.data.objects["M"]
    sp = space()
    check("mesh dropped on the viewport: not unparented / parented, view unchanged",
          m.parent is None and (sp.region_3d.view_perspective, sp.camera, sp.use_local_camera) == C["before"])


# 2. cam1 dropped on the viewport: it looks through cam1
drag(lambda: row_xy(C["rows"]["cam1"]), view_xy)


@step
def s_cam1_check():
    sp = space()
    shot("gui_issue294_look_through_cam1.png")
    check(f"cam1 dropped on the viewport: looks through cam1 ({sp.camera}, {sp.region_3d.view_perspective})",
          sp.camera == bpy.data.objects["cam1"] and sp.region_3d.view_perspective == 'CAMERA')
    check(f"it is the viewport's own camera (local {sp.use_local_camera}, scene camera "
          f"{bpy.context.scene.camera} was {C['scene_cam']})",
          sp.use_local_camera and bpy.context.scene.camera == C["scene_cam"])
    check("the camera keeps its place in the scene (not reparented)", bpy.data.objects["cam1"].parent is None)


# 3. cam2 dropped on the same viewport: switches to cam2
drag(lambda: row_xy(C["rows"]["cam2"]), view_xy)


@step
def s_cam2_check():
    sp = space()
    check("cam2 dropped next: looks through cam2",
          sp.camera == bpy.data.objects["cam2"] and sp.region_3d.view_perspective == 'CAMERA')


# 4. inside the Outliner the MMB drag still parents: cam2 onto M
drag(lambda: row_xy(C["rows"]["cam2"]), lambda: row_xy(C["rows"]["M"]))


@step
def s_parent_check():
    check("MMB drag inside the Outliner still parents (cam2 under M)",
          bpy.data.objects["cam2"].parent == bpy.data.objects["M"])


run()
