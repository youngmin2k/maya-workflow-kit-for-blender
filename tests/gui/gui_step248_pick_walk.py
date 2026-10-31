"""Issue #165: in a real UI: a spine with three branches made with the Joint Tool (L_arm, R_arm, neck order
like the Maya fixture) -> arrow keys walk in creation order and wrap (Maya pick walk) ->
the Channel Box shows Radius under Visibility; typing 2 changes it -> Display > Transform Display > Local Rotation
Axes shows the joint axes -> Ctrl+Z -> save + open keeps the child order."""

import os
import sys
import tempfile
from importlib import import_module

import bpy
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
        screenshot(os.path.join(SHOTS, f"gui_step248_{name}.png"))


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def ov():
    area, region = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def rig():
    return bpy.data.objects[C["rig"]]


def lead():
    b = rig().data.bones.active
    return b.name if b is not None else None


def key(k, **kw):
    _a, r = main_view()
    x, y = r.x + r.width // 2, r.y + r.height // 2
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev(k, 'PRESS', x=x, y=y, **kw)
    ev(k, 'RELEASE', x=x, y=y, **kw)


def pick(name):
    cb = mod(".ui.channel_box")
    for pb in rig().pose.bones:
        cb.set_bone_selected(pb, pb.name == name)
    rig().data.bones.active = rig().data.bones[name]


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_skeleton():
    for ob in list(bpy.data.objects):
        if ob.type in {'MESH', 'ARMATURE', 'EMPTY'}:
            bpy.data.objects.remove(ob)
    joints = mod(".operators.joints")
    with ov():
        ob = joints.new_skeleton(bpy.context)
        k = mod(".operators.units").maya_unit()
        p = lambda x, y: Vector((x * k, 0.0, y * k))     # noqa: E731  (Maya front view: x, y)
        root = joints.add_joint(ob, p(0, 10), None, length=k)
        spine = joints.add_joint(ob, p(0, 13), root, length=k)
        for name, (x, y) in (("L_arm", (3, 15)), ("R_arm", (-3, 15)), ("neck", (0, 17))):
            n = joints.add_joint(ob, p(x, y), spine, length=k)
            ob.data.edit_bones[n].name = name
        bpy.ops.object.mode_set(mode='POSE')
    C["rig"] = ob.name
    C["spine"] = spine
    pick(spine)


@step
def s_down():
    key('DOWN_ARROW')


@step
def s_down_done():
    check(f"Down from the spine = its first child L_arm ({lead()})", lead() == "L_arm")
    key('LEFT_ARROW')


@step
def s_left_done():
    check(f"Left from L_arm wraps to the last child neck ({lead()})", lead() == "neck")
    key('RIGHT_ARROW')


@step
def s_right_done():
    check(f"Right from neck wraps to L_arm ({lead()})", lead() == "L_arm")
    key('RIGHT_ARROW')


@step
def s_right2():
    check(f"Right from L_arm = R_arm (creation order, not names) ({lead()})", lead() == "R_arm")
    for ar in win().screen.areas:
        ar.tag_redraw()


@step
def s_radius_shot():
    shot("radius_row")
    b = rig().data.bones["R_arm"]
    check(f"R_arm Radius reads the default (1, {b.allset_joint_radius:g})", abs(b.allset_joint_radius - 1.0) < 1e-6)
    b.allset_joint_radius = 2.0
    with ov():
        bpy.ops.allset.menu_item(item="Display/Transform Display/Local Rotation Axes")


@step
def s_axes():
    for ar in win().screen.areas:
        ar.tag_redraw()
    check("Local Rotation Axes shows the joint axes", rig().data.show_axes)


@step
def s_axes_shot():
    shot("axes")
    key('Z', ctrl=True)


@step
def s_undone():
    check("Ctrl+Z hides the axes again", not rig().data.show_axes)
    rig().data.bones["R_arm"].allset_joint_radius = 2.0   # a Python write pushes no undo step: set again after Ctrl+Z
    path = os.path.join(tempfile.mkdtemp(prefix="allset248_"), "walk.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)


@step
def s_reopened():
    joints = mod(".operators.joints")
    ob = bpy.data.objects[C["rig"]]
    kids = [b.name for b in sorted(ob.data.bones[C["spine"]].children, key=joints.child_order_key)]
    check(f"save + open keeps the child order ({kids})", kids == ["L_arm", "R_arm", "neck"])
    check(f"and the Radius ({ob.data.bones['R_arm'].allset_joint_radius:g})",
          abs(ob.data.bones["R_arm"].allset_joint_radius - 2.0) < 1e-6)


run()
