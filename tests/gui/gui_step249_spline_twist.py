"""Issue #166: in a real UI: a six-joint spine -> Skeleton > Create IK Spline Handle (click the root, then
the end joint) -> the curve is bent -> the handle's Channel Box shows Twist / Roll / Twist Type; Twist 100 turns the
in-between joints 25 deg each (Maya Linear), Twist Type 1 (Ease In) piles it toward the end, Roll 30 turns the root
-> Ctrl+Z -> save + open keeps the twist."""

import math
import os
import sys
import tempfile
from importlib import import_module

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, f"gui_step249_{name}.png"))


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def ov():
    area, region = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def screen_of(world):
    _a, r = main_view()
    p = view3d_utils.location_3d_to_region_2d(r, r.data, world)
    return int(round(r.x + p.x)), int(round(r.y + p.y))


def click_at(x, y):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


def rig():
    return bpy.data.objects[C["rig"]]


def head(name):
    return rig().matrix_world @ rig().pose.bones[name].head


def roll_of(name):
    """The joint's own rotation about its X (bone Y) relative to its parent, in degrees."""
    bpy.context.view_layer.update()
    pb = rig().pose.bones[name]
    local = (pb.parent.matrix.inverted() @ pb.matrix) if pb.parent else pb.matrix
    rest = (pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local) if pb.parent else pb.bone.matrix_local
    return math.degrees((rest.inverted() @ local).to_euler('YXZ').y)


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_skeleton():
    for ob in list(bpy.data.objects):
        if ob.type in {'MESH', 'ARMATURE', 'EMPTY', 'CURVE'}:
            bpy.data.objects.remove(ob)
    joints = mod(".operators.joints")
    k = mod(".operators.units").maya_unit()
    with ov():
        ob = joints.new_skeleton(bpy.context)
        parent, names = None, []
        for i in range(6):
            parent = joints.add_joint(ob, Vector((0.0, 0.0, 2.0 * i * k)), parent, length=k)
            names.append(parent)
        joints.orient_new(ob, names)
        bpy.ops.object.mode_set(mode='POSE')
        ob.data.show_axes = True
    C["rig"], C["names"] = ob.name, names
    with ov():
        bpy.ops.view3d.view_all()


@step
def s_tool():
    with ov():
        bpy.ops.allset.menu_item(item="Skeleton/Create IK Spline Handle")


@step
def s_click_root():
    click_at(*screen_of(head(C["names"][0])))


@step
def s_click_end():
    click_at(*screen_of(head(C["names"][-1])))


@step
def s_made():
    h = next((o for o in bpy.data.objects if o.get("allset_spline_ik")), None)
    check("Create IK Spline Handle made a handle with Twist / Roll / Twist Type", h is not None)
    if h is None:
        return
    C["h"] = h.name
    keys = mod(".ui.channel_box").custom_keys(h)
    check(f"Channel Box rows Roll / Twist / Twist Type ({keys})", {"twist", "roll", "twistType"} <= set(keys))
    curve = next(o for o in bpy.data.objects if o.type == 'CURVE')
    k = mod(".operators.units").maya_unit()
    pts = curve.data.splines[0].points
    pts[-2].co = (2.0 * k, 0.0, pts[-2].co[2], 1.0)          # bend it like the Maya case
    pts[-1].co = (4.0 * k, -1.0 * k, pts[-1].co[2], 1.0)
    curve.data.update_tag()
    bpy.ops.ed.undo_push(message="bend")


@step
def s_twist():
    h = bpy.data.objects[C["h"]]
    mod(".ui.channel_box").set_value(h, "cp:twist", 100.0)
    bpy.context.view_layer.update()
    rolls = [roll_of(n) for n in C["names"][1:5]]
    check(f"Twist 100 Linear: 25 deg on each in-between joint ({[round(r, 2) for r in rolls]})",
          all(abs(r - 25.0) < 0.7 for r in rolls))
    for ar in win().screen.areas:
        ar.tag_redraw()


@step
def s_twist_shot():
    shot("twist100")
    h = bpy.data.objects[C["h"]]
    mod(".ui.channel_box").set_value(h, "cp:twistType", 1)
    rolls = [roll_of(n) for n in C["names"][1:5]]
    check(f"Twist Type 1 (Ease In): 1.6 / 10.9 / 29.7 / 57.8 ({[round(r, 2) for r in rolls]})",
          all(abs(a - b) < 0.7 for a, b in zip(rolls, (1.5625, 10.9375, 29.6875, 57.8125))))
    mod(".ui.channel_box").set_value(h, "cp:roll", 30.0)
    check(f"Roll 30 turns the root joint ({roll_of(C['names'][0]):.2f})", abs(roll_of(C["names"][0]) - 30.0) < 0.7)
    _a, r = main_view()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    h = bpy.data.objects[C["h"]]
    check(f"Ctrl+Z takes the Roll back ({h.get('roll')})", abs(h.get("roll", 1.0)) < 1e-9)
    cb = mod(".ui.channel_box")
    cb.set_value(h, "cp:twist", 100.0)          # Python writes push no undo step: set again for the file
    cb.set_value(h, "cp:twistType", 3)
    path = os.path.join(tempfile.mkdtemp(prefix="allset249_"), "spline.blend")
    C["tt"] = h.get("twistType")
    C["twist"] = h.get("twist")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)


@step
def s_reopened():
    h = bpy.data.objects.get(C["h"])
    check("save + open keeps the handle", h is not None)
    bpy.context.view_layer.update()
    rolls = [roll_of(n) for n in C["names"][1:5]]
    from importlib import import_module as im
    st = im(MODULE + ".operators.spline_twist")
    want = [C["twist"] * s for s in st.shares(5, int(C["tt"] or 0))[1:]]
    check(f"the twist still drives the joints after open ({[round(r, 2) for r in rolls]} vs Ease In Out "
          f"{[round(w, 2) for w in want]})", abs(C["twist"] - 100.0) < 1e-9
          and all(abs(a - b) < 0.7 for a, b in zip(rolls, want)))


run()
