"""Issue #163: in a real UI, the skeleton chain a Maya rigger walks:
Joint Tool 3 clicks -> Enter -> Skeleton > Insert Joints: press on joint2, drag halfway to joint3, release, Enter ->
joint4 sits between them, joint3 didn't move -> Remove Joints on joint4 -> Ctrl+Z brings it back -> Disconnect Joint
on joint3 (root + end joint5 left behind) -> Connect Joint joint3 to joint5 (factory connect mode) -> Mirror Joints
(factory XY) -> save + open keeps the skeleton."""

import os
import sys
import tempfile
from importlib import import_module

import bpy
from bpy_extras import view3d_utils

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
        screenshot(os.path.join(SHOTS, f"gui_step246_{name}.png"))


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


def bones():
    ob = rig()
    return ob.data.edit_bones if ob.mode == 'EDIT' else ob.data.bones


def head(name):
    ob = rig()
    b = bones()[name]
    return ob.matrix_world @ (b.head if ob.mode == 'EDIT' else b.head_local)


def parent(name):
    p = bones()[name].parent
    return p.name if p is not None else None


def frame(name):
    ob = rig()
    b = bones()[name]
    m = b.matrix if ob.mode == 'EDIT' else b.matrix_local
    f = m.to_3x3().normalized() @ mod(".operators.joints").JOINT_AXES
    q = b.get("allset_maya_frame")
    if q is not None and len(q) == 4:
        from mathutils import Quaternion
        f = f @ Quaternion(q).to_matrix()
    return f


def pick(*names):
    """Select joints the way the kit does after a click (pose mode: bones; edit mode: the picked shape), last active."""
    sm = mod(".operators.skeleton_menu")
    with ov():
        sm._select_only(rig(), list(names))
        if len(names) > 1 and rig().mode != 'EDIT':
            cb = mod(".ui.channel_box")
            for n in names:
                cb.set_bone_selected(rig().pose.bones[n], True)
        elif len(names) > 1:
            js = mod(".operators.joint_selection")
            for n in names:
                js._pick_shape(rig().data.edit_bones[n], True, False)
            rig().data.edit_bones.active = rig().data.edit_bones[names[-1]]


def menu(path):
    with ov():
        bpy.ops.allset.menu_item(item=path)


def click_at(x, y):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


def press_key(key, **kw):
    x, y = at(0.9, 0.1)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev(key, 'PRESS', x=x, y=y, **kw)
    ev(key, 'RELEASE', x=x, y=y, **kw)


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


for _i, (_f, _g) in enumerate(((0.30, 0.45), (0.45, 0.60), (0.62, 0.45))):
    def _mk(f=_f, g=_g, i=_i):
        @step
        def s_click():
            click_at(*at(f, g))
        s_click.__name__ = f"s_joint{i + 1}"
    _mk()


@step
def s_enter():
    press_key('RET')


@step
def s_insert_tool():
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    check(f"Joint Tool made a skeleton ({len(arms)})", len(arms) == 1)
    C["rig"] = arms[0].name
    C["names"] = [b.name for b in rig().data.bones]
    check(f"three joints {C['names']}", C["names"] == ["joint1", "joint2", "joint3"])
    C["j3"] = head("joint3").copy()
    C["f2"] = frame("joint2").copy()
    menu("Skeleton/Insert Joints")


@step
def s_press_joint2():
    x, y = screen_of(head("joint2"))
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_drag():
    a = screen_of(head("joint2"))
    b = screen_of(C["j3"])
    C["drop"] = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2 + 20)
    for t in (0.3, 0.7, 1.0):
        ev('MOUSEMOVE', 'NOTHING', x=int(a[0] + (C["drop"][0] - a[0]) * t), y=int(a[1] + (C["drop"][1] - a[1]) * t))


@step
def s_release():
    ev('LEFTMOUSE', 'RELEASE', x=C["drop"][0], y=C["drop"][1])


@step
def s_finish_insert():
    press_key('RET')


@step
def s_inserted():
    shot("insert")
    ok = "joint4" in bones()
    check(f"Insert Joints made joint4 ({[b.name for b in bones()]})", ok)
    if not ok:
        return
    check(f"joint4 between joint2 and joint3 ({parent('joint4')}, {parent('joint3')})",
          parent("joint4") == "joint2" and parent("joint3") == "joint4")
    d = (mod(".operators.units").maya_unit())
    p = screen_of(head("joint4"))
    check(f"joint4 where it was dropped ({p} vs {C['drop']})", abs(p[0] - C["drop"][0]) <= 2 and abs(p[1] - C["drop"][1]) <= 2)
    check(f"joint3 stayed ({(head('joint3') - C['j3']).length / d:.1e})", (head("joint3") - C["j3"]).length / d < 1e-4)
    err = max((frame("joint2").col[i] - C["f2"].col[i]).length for i in range(3))
    check(f"joint2 keeps its Maya frame ({err:.1e})", err < 1e-4)
    pick("joint4")
    menu("Skeleton/Remove Joints")


@step
def s_removed():
    shot("remove")
    check(f"Remove Joints: joint4 gone, joint3 back under joint2 ({parent('joint3')})",
          "joint4" not in bones() and parent("joint3") == "joint2")
    d = mod(".operators.units").maya_unit()
    check("joint3 still where it was", (head("joint3") - C["j3"]).length / d < 1e-4)
    _a, r = main_view()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    check(f"Ctrl+Z brings joint4 back ({[b.name for b in bones()]})", "joint4" in bones() and parent("joint3") == "joint4")
    pick("joint3")
    menu("Skeleton/Disconnect Joint")


@step
def s_disconnected():
    shot("disconnect")
    end = next((b.name for b in bones() if b.name not in ("joint1", "joint2", "joint3", "joint4")), None)
    check(f"Disconnect: joint3 a root, end joint {end} under joint4 at joint3's place",
          parent("joint3") is None and end is not None and parent(end) == "joint4"
          and (head(end) - head("joint3")).length < 1e-5)
    C["end"] = end
    if end is None:
        return
    pick("joint3", end)
    menu("Skeleton/Connect Joint")


@step
def s_connected():
    shot("connect")
    end = C.get("end")
    check(f"Connect (factory connect mode): joint3 under joint4 at {end}'s place ({parent('joint3')})",
          parent("joint3") == "joint4" and (head("joint3") - head(end)).length < 1e-5)
    C["before_mirror"] = [b.name for b in bones()]
    pick("joint1")
    menu("Skeleton/Mirror Joints")


@step
def s_mirrored():
    shot("mirror")
    names = [b.name for b in bones()]
    made = [n for n in names if n not in C["before_mirror"]]
    check(f"Mirror Joints copied the 5 joints ({made})", len(made) == 5)
    copy = bones()[made[0]]                        # the copy of joint1 comes first (parents before children)
    src = head("joint1")
    dst = rig().matrix_world @ (copy.head if rig().mode == 'EDIT' else copy.head_local)
    # Maya XY plane = Blender XZ: Blender Y flips
    check(f"Mirror Joints (factory XY) copies across Maya XY ({tuple(round(c, 3) for c in src)} -> "
          f"{tuple(round(c, 3) for c in dst)})",
          abs(dst.x - src.x) < 1e-5 and abs(dst.y + src.y) < 1e-5 and abs(dst.z - src.z) < 1e-5)
    C["count"] = len(names)
    path = os.path.join(tempfile.mkdtemp(prefix="allset246_"), "skel.blend")
    if rig().mode == 'EDIT':
        with ov():
            bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)


@step
def s_reopened():
    ob = bpy.data.objects.get(C["rig"])
    check(f"save + open keeps the skeleton ({len(ob.data.bones) if ob else None} / {C['count']})",
          ob is not None and len(ob.data.bones) == C["count"])


run()
