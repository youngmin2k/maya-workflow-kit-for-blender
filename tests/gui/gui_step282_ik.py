"""#181: in a real UI: Joint Tool 4 clicks (a leg / spine of 3 bones) -> Enter -> Skeleton > Create IK
Handle (first joint, then the last) -> the kit solves the chain Maya's way -> move the handle: the end reaches it and
every joint sits where the Maya-style rule puts it -> Twist 45 -> Ctrl+Z -> save + open keeps it."""

import os
import sys
import tempfile
from importlib import import_module

import bpy
import numpy as np
from bpy_extras import view3d_utils
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
PATH = os.path.join(tempfile.mkdtemp(), "ik282.blend")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, f"gui_step282_{name}.png"))


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


def at(f, g):
    _a, r = main_view()
    return r.x + int(r.width * f), r.y + int(r.height * g)


def rig():
    return bpy.data.objects[C["rig"]]


def joint(i):
    ob = rig()
    names = C["names"]
    if i < len(names):
        return ob.matrix_world @ ob.pose.bones[names[i]].head
    return ob.matrix_world @ ob.pose.bones[names[-1]].head


def click_at(x, y):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


def handle():
    return bpy.data.objects.get("ikHandle1")


def expected():
    """Joint positions of Maya's rule for the handle as it is now (the same solve, computed afresh)."""
    ik_rp = mod(".operators.ik_rp")
    multi = mod(".operators.ik_rp_multi")
    h = handle()
    arm, bones, _con = ik_rp.multi_chain(h)
    k = mod(".operators.units").maya_unit()
    chain, _axes, _sig = ik_rp.kit_chain(arm, bones, k)
    solver = multi.Solver(chain)
    goal = (arm.matrix_world.inverted() @ h.matrix_world.translation) / k
    pv = arm.matrix_world.to_3x3().inverted() @ ik_rp.pole_vector(h)
    import math
    _x, _t, pos = solver.solve(np.array(goal), np.array(pv), math.radians(float(h.get(ik_rp.TWIST, 0.0))))
    return [arm.matrix_world @ Vector((p * k).tolist()) for p in pos]


def compare(label):
    bpy.context.view_layer.update()
    k = mod(".operators.units").maya_unit()
    want = expected()
    got = [joint(i) for i in range(len(want))]
    worst = max((g - w).length for g, w in zip(got, want)) / k
    reach = (got[-1] - handle().matrix_world.translation).length / k
    length = sum((got[i + 1] - got[i]).length for i in range(len(got) - 1))
    inside = (handle().matrix_world.translation - got[0]).length < length * 0.98
    check(f"{label}: joints on the Maya-style rule ({worst:.1e}), the end at the handle ({reach:.1e}, in reach {inside})",
          worst < 1e-4 and (reach < 2e-3 or not inside))


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_tool():
    for ob in list(bpy.data.objects):
        if ob.type in {'MESH', 'ARMATURE', 'EMPTY'}:
            bpy.data.objects.remove(ob)
    with ov():
        bpy.ops.allset.joint_tool('INVOKE_DEFAULT')


for _i, (_f, _g) in enumerate(((0.45, 0.80), (0.52, 0.62), (0.46, 0.45), (0.50, 0.25))):
    def _mk(f=_f, g=_g, i=_i):
        @step
        def s_click():
            click_at(*at(f, g))
        s_click.__name__ = f"s_joint{i + 1}"
    _mk()


@step
def s_enter():
    x, y = at(0.9, 0.1)
    ev('RET', 'PRESS', x=x, y=y)
    ev('RET', 'RELEASE', x=x, y=y)


@step
def s_ik_tool():
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    check(f"Joint Tool made the chain ({len(arms)})", len(arms) == 1)
    C["rig"] = arms[0].name
    C["names"] = [b.name for b in rig().data.bones]
    check(f"four joints = three bones + the end joint's bone ({len(C['names'])})", len(C["names"]) == 4)
    with ov():
        bpy.ops.allset.menu_item(item="Skeleton/Create IK Handle")


@step
def s_click_start():
    click_at(*screen_of(joint(0)))


@step
def s_click_end():
    click_at(*screen_of(joint(3)))


@step
def s_handle():
    h = handle()
    check("Create IK Handle made ikHandle1", h is not None)
    if h is None:
        return
    ik_rp = mod(".operators.ik_rp")
    check("the kit solves the 3-bone RP chain", h.get(ik_rp.MULTI) == 1)
    k = mod(".operators.units").maya_unit()
    with ov():
        bpy.ops.transform.translate('EXEC_DEFAULT', True, value=(0.6 * k, -0.4 * k, -0.8 * k))


@step
def s_moved():
    compare("handle moved")
    shot("01_moved")
    bpy.ops.ed.undo_push(message="before twist")
    mod(".ui.channel_box").set_value(handle(), "cp:twist", 45.0)
    bpy.ops.ed.undo_push(message="Twist")


@step
def s_twisted():
    compare("Twist 45")
    C["twisted"] = joint(1).copy()
    shot("02_twist45")
    x, y = at(0.5, 0.5)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('Z', 'PRESS', ctrl=True, x=x, y=y)
    ev('Z', 'RELEASE', ctrl=True, x=x, y=y)


@step
def s_undone():
    ik_rp = mod(".operators.ik_rp")
    tw = float(handle().get(ik_rp.TWIST, 0.0))
    check(f"Ctrl+Z takes Twist back to 0 (got {tw})", abs(tw) < 1e-9)
    compare("after Ctrl+Z")
    bpy.ops.wm.save_as_mainfile(filepath=PATH)


@step
def s_open():
    bpy.ops.wm.open_mainfile(filepath=PATH)


@step
def s_reopened():
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    C["rig"] = arms[0].name
    compare("reopened")
    shot("03_reopened")


run()
