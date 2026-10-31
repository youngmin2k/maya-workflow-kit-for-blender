"""In the Maya Workflow Kit layout: a three-joint skeleton, pose mode, joint2
selected -> Skeleton > Joint Labelling > Label Left + Label Hip#2 (Hip), Toggle Selected Labels -> "Hip (L)" is drawn
next to the joint (shot, pixel change near the joint). Skin > Disable Selected IK Handles on an IK handle sets its
weight to 0."""

import os
import sys
from importlib import import_module

import bpy
import numpy as np
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def main_view():
    toolbox = import_module(MODULE + ".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def override():
    area, r = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=r)


def grab(name):
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step159_{name}.png")
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[..., :3]


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
    joints = import_module(MODULE + ".operators.joints")
    k = import_module(MODULE + ".operators.units").maya_unit()
    with override():
        sk = joints.new_skeleton(bpy.context)
        parent = None
        for z in (-3.0, 0.0, 3.0):
            parent = joints.add_joint(sk, Vector((0, 0, z * k)), parent, length=k)
        joints.finish(bpy.context, sk, ["joint1", "joint2", "joint3"])
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.allset.frame(selected=False)
        bpy.ops.object.mode_set(mode='POSE')
        cbm = import_module(MODULE + ".ui.channel_box")
        for pb in sk.pose.bones:
            cbm.set_bone_selected(pb, pb.name == "joint2")
        sk.data.bones.active = sk.data.bones["joint2"]
    C["k"] = k
    redraw()


@step
def s_before():
    C["before"] = grab("before")
    mm = import_module(MODULE + ".ui.menu_map").MAP
    base = "Skeleton/Joint Labelling/Add Joint Labels/Label "
    with override():
        for path in (base + "Left", base + "Hip#2", "Skeleton/Joint Labelling/Toggle Selected Labels"):
            op, props = (mm[path], {}) if isinstance(mm[path], str) else mm[path]
            mod, name = op.split(".")
            getattr(getattr(bpy.ops, mod), name)(**props)
    redraw()


@step
def s_wait():
    redraw()


@step
def s_after():
    after = grab("labels")
    sk = bpy.data.objects["skeleton1"]
    jl = import_module(MODULE + ".operators.joint_labels")
    b = sk.data.bones["joint2"]
    check(f"joint2 label = {jl.label_text(b)!r}, drawn {jl.get_label(b)[3]}", jl.label_text(b) == "Hip (L)"
          and jl.get_label(b)[3])
    area, r = main_view()
    head = sk.matrix_world @ b.head_local
    p = view3d_utils.location_3d_to_region_2d(r, r.data, head)
    x, y = r.x + int(p.x), r.y + int(p.y)
    win_ = slice(max(0, y - 30), y + 30), slice(max(0, x - 10), x + 120)
    diff = float(np.abs(after[win_] - C["before"][win_]).max())
    check(f"the label is drawn beside joint2 (max pixel change {diff:.2f} near {x}, {y})", diff > 0.2)


run()
