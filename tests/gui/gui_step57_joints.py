"""In a real UI, Maya rigging_01 hand order on the Maya Workflow Kit layout: Skeleton > Create Joints -> three clicks in
the persp view (ground plane) -> Enter -> pose mode, joint1 > joint2 > joint3, Channel Box lead joint1 (Maya 2026: the root) -> Down Down
-> joint3 -> Up Up (pick-walk) -> joint1 -> Skeleton > Mirror Joints (default XY) -> six joints."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, px, run, screenshot, setup, step, tap, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def maya_menu(path):
    for cls in import_module(MODULE + ".ui.menu_sets")._menu_classes:
        if (cls.__doc__ or "").strip() == f"Maya menu: {path}":
            return cls.bl_idname
    raise LookupError(path)


def main_view():
    """The big persp 3D View of the layout (not the Tool Box column)."""
    toolbox = import_module(MODULE + ".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def open_menu(path):
    area, region = main_view()
    x, y = region.x + region.width // 2, region.y + region.height // 2
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.call_menu(name=maya_menu(path))


def cb():
    return import_module(MODULE + ".ui.channel_box")


def skeleton():
    return bpy.data.objects.get("skeleton1")


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_menu():
    bpy.ops.allset.keymap_activate()
    for ob in list(bpy.data.objects):
        ob.select_set(False)
    open_menu("Skeleton")


@step
def s_create_joints():
    tap('C')          # Create Joints (underlined)


@step
def s_tool_running():
    names = [op.bl_idname for op in win().modal_operators]
    check(f"Skeleton > Create Joints starts the Joint Tool ({names})", "ALLSET_OT_joint_tool" in names)
    _a, r = main_view()
    # three clicks below the horizon of the persp view (the ground plane), left to right
    C["clicks"] = [(r.x + r.width * f // 10, r.y + r.height * g // 10) for f, g in ((4, 3), (5, 2), (6, 3))]
    C["i"] = 0
    ev('MOUSEMOVE', 'NOTHING', x=C["clicks"][0][0], y=C["clicks"][0][1])


def _click_step():
    x, y = C["clicks"][C["i"]]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    C["i"] += 1


for _n in range(3):
    step(_click_step)


@step
def s_placed():
    sk = skeleton()
    n = len(sk.data.edit_bones) if sk is not None and sk.mode == 'EDIT' else 0
    check(f"three clicks placed three joints in skeleton1 ({n})", n == 3)
    shot("gui_step57_placing.png")
    _a, r = main_view()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    tap('RET')


@step
def s_finished():
    sk = skeleton()
    check(f"Enter: pose mode ({sk.mode})", sk.mode == 'POSE')
    bones = sk.data.bones
    chain = bones.get("joint3") and bones["joint3"].parent and bones["joint3"].parent.parent
    check("joint1 > joint2 > joint3", chain is not None and chain.name == "joint1" and
          bones["joint3"].parent.name == "joint2")
    z = max(abs(b.head_local.z) for b in bones)
    check(f"persp clicks land on the ground (|z| max {z:.2e})", z < 1e-4)
    ld = cb().lead()
    check(f"Channel Box lead = the root joint (Maya 2026) ({getattr(ld, 'name', None)})", ld is not None and ld.name == "joint1")
    check("joints rotate XYZ", all(pb.rotation_mode == 'XYZ' for pb in sk.pose.bones))
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_shot_cb():
    tap('DOWN_ARROW')


@step
def s_down2():
    tap('DOWN_ARROW')


@step
def s_at_end():
    ld = cb().lead()
    check(f"Down Down walks to the end joint ({getattr(ld, 'name', None)})", ld is not None and ld.name == "joint3")
    shot("gui_step57_joint3.png")
    tap('UP_ARROW')


@step
def s_up2():
    tap('UP_ARROW')


@step
def s_walked():
    ld = cb().lead()
    check(f"Up Up walks to the root joint ({getattr(ld, 'name', None)})", ld is not None and ld.name == "joint1")
    open_menu("Skeleton")


@step
def s_mirror_item():
    tap('M')          # Mirror Joints (underlined): its option dialog


@step
def s_dialog():
    shot("gui_step57_mirror_dialog.png")
    tap('RET')        # Mirror (default XY, Behavior)


@step
def s_mirrored():
    sk = skeleton()
    n = len(sk.data.bones)
    check(f"Mirror Joints XY: six joints ({n}, {sorted(sk.data.bones.keys())})", n == 6)
    if n == 6:
        a, b = sk.data.bones["joint1"], sk.data.bones["joint4"]
        # Maya XY plane = Blender XZ: Blender Y flips (joints.PLANES)
        check("joint4 = joint1 mirrored across Maya XY", abs(a.head_local.y + b.head_local.y) < 1e-5
              and abs(a.head_local.x - b.head_local.x) < 1e-5)
    for ar in win().screen.areas:
        ar.tag_redraw()


@step
def s_final_shot():
    shot("gui_step57_mirrored.png")


run()
