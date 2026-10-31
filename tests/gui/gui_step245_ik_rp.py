"""Issue #162: in a real UI, chain ③: Joint Tool 3 clicks (a
bent arm) -> Enter -> Skeleton > Create IK Handle (click joint1, then joint3) -> the handle has a default Pole
Vector (2 units toward the elbow) and Twist in the Channel Box, the chain doesn't move -> move the handle: the elbow
stays in the RP plane -> Twist 90 turns the plane about root -> goal -> Ctrl+Z -> save + open keeps it working."""

import math
import os
import sys
import tempfile
from importlib import import_module

import bpy
from bpy_extras import view3d_utils
from mathutils import Quaternion, Vector

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
        screenshot(os.path.join(SHOTS, f"gui_step245_{name}.png"))


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


def head(name):
    ob = rig()
    return ob.matrix_world @ ob.pose.bones[name].head


def click_at(x, y):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


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


for _i, (_f, _g) in enumerate(((0.40, 0.30), (0.52, 0.50), (0.42, 0.70))):
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
    check(f"Joint Tool made the arm ({len(arms)})", len(arms) == 1)
    C["rig"] = arms[0].name
    C["names"] = [b.name for b in rig().data.bones]
    C["elbow0"] = head(C["names"][1]).copy()
    with ov():
        bpy.ops.allset.menu_item(item="Skeleton/Create IK Handle")


@step
def s_click_start():
    click_at(*screen_of(head(C["names"][0])))


@step
def s_click_end():
    click_at(*screen_of(head(C["names"][2])))


@step
def s_handle():
    h = bpy.data.objects.get("ikHandle1")
    check("Create IK Handle made ikHandle1", h is not None)
    if h is None:
        return
    ik_rp = mod(".operators.ik_rp")
    pv = Vector([h[n] for n in ik_rp.PV])
    k = mod(".operators.units").maya_unit()
    j0, j1, j2 = (head(n) / k for n in C["names"])
    d = j2 - j0
    off = (j1 - j0) - d * ((j1 - j0).dot(d) / d.length_squared)
    off_m = ik_rp.to_maya(off).normalized()
    check(f"default pole vector: 2 units toward the elbow ({tuple(round(c, 3) for c in pv)})",
          abs(pv.length - 2.0) < 1e-4 and (pv.normalized() - off_m).length < 1e-4)
    keys = mod(".ui.channel_box").custom_keys(h)
    check(f"Channel Box rows Pole Vector X/Y/Z, Twist ({keys})",
          {"poleVectorX", "poleVectorY", "poleVectorZ", "twist"} <= set(keys))
    bpy.context.view_layer.update()
    moved = (head(C["names"][1]) - C["elbow0"]).length
    check(f"making the handle doesn't move the chain ({moved:.1e})", moved < 1e-4)
    check("the handle is selected (Maya)", bpy.context.active_object == h)
    C["h"] = h.name


@step
def s_shot_handle():
    shot("01_handle")


@step
def s_move_handle():
    h = bpy.data.objects[C["h"]]
    k = mod(".operators.units").maya_unit()
    with ov():
        bpy.ops.transform.translate('EXEC_DEFAULT', True, value=(0.0, -1.0 * k, -1.5 * k))


@step
def s_moved():
    h = bpy.data.objects[C["h"]]
    ik_rp = mod(".operators.ik_rp")
    k = mod(".operators.units").maya_unit()
    bpy.context.view_layer.update()
    root, el = head(C["names"][0]), head(C["names"][1])
    goal = h.matrix_world.translation
    pv = ik_rp.pole_vector(h)
    u = (goal - root).normalized()
    n = u.cross(pv - u * pv.dot(u)).normalized()
    plane = abs((el - root).dot(n)) / k
    side = (el - root).dot(pv - u * pv.dot(u)) > 0
    check(f"the elbow stays in the RP plane (root, goal, pole) ({plane:.1e}) on the pole side", plane < 1e-3 and side)
    C["el_twist0"] = el.copy()
    C["goal"] = goal.copy()
    bpy.ops.ed.undo_push(message="before twist")
    mod(".ui.channel_box").set_value(h, "cp:twist", 90.0)       # Channel Box: Twist 90
    bpy.ops.ed.undo_push(message="Twist")


@step
def s_twisted():
    bpy.context.view_layer.update()
    root, el = head(C["names"][0]), head(C["names"][1])
    u = (C["goal"] - root).normalized()
    want = root + Quaternion(u, math.radians(90.0)) @ (C["el_twist0"] - root)
    k = mod(".operators.units").maya_unit()
    e = (el - want).length / k
    check(f"Twist 90 turns the elbow 90 deg about root -> goal (right-handed) ({e:.1e})", e < 1e-3)


@step
def s_shot_twist():
    shot("02_twist90")
    x, y = at(0.5, 0.5)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('Z', 'PRESS', ctrl=True, x=x, y=y)
    ev('Z', 'RELEASE', ctrl=True, x=x, y=y)


@step
def s_undone():
    h = bpy.data.objects[C["h"]]
    bpy.context.view_layer.update()
    e = (head(C["names"][1]) - C["el_twist0"]).length / mod(".operators.units").maya_unit()
    check(f"Ctrl+Z: Twist 0 and the elbow back ({h.get('twist')}, {e:.1e})", abs(h.get("twist", 1)) < 1e-9 and e < 1e-3)
    mod(".ui.channel_box").set_value(h, "cp:twist", 45.0)
    path = os.path.join(tempfile.mkdtemp(prefix="allset245_"), "ik.blend")
    C["path"] = path
    bpy.context.view_layer.update()
    C["el45"] = head(C["names"][1]).copy()
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)


@step
def s_reopened():
    h = bpy.data.objects.get(C["h"])
    check("save + open keeps the handle and its pole helper", h is not None and h.get("allset_pole_helper") is not None)
    bpy.context.view_layer.update()
    e = (head(C["names"][1]) - C["el45"]).length / mod(".operators.units").maya_unit()
    check(f"after open the elbow is where it was (Twist 45) ({e:.1e})", e < 1e-3)
    mod(".ui.channel_box").set_value(h, "cp:twist", 0.0)
    bpy.context.view_layer.update()
    e0 = (head(C["names"][1]) - C["el_twist0"]).length / mod(".operators.units").maya_unit()
    check(f"the pole update still runs after open (Twist 0 = first elbow) ({e0:.1e})", e0 < 1e-3)


run()
