"""In a real UI (Maya Workflow Kit layout): Alt+A cycles X-ray joints / everything / meshes only, Alt+P toggles
persp / ortho, Alt+Right moves the cube one pixel, ` held = Tweak tool then back to Move, \\ held + LMB drag pans
the camera view."""

import os
import sys

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def key(type, **mods):
    names = {"alt": "LEFT_ALT", "ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT"}
    for m in mods:
        ev(names[m], 'PRESS')
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)
    for m in mods:
        ev(names[m], 'RELEASE')


def hover():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


def space():
    return view3d()[0].spaces.active


def cube():
    return bpy.data.objects["pCube1"]


def screen_x():
    _a, r = view3d()
    return location_3d_to_region_2d(r, r.data, cube().matrix_world.translation)


def tool():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return bpy.context.workspace.tools.from_space_view3d_mode('OBJECT').idname


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    arm = bpy.data.objects.new("joint_rig", bpy.data.armatures.new("joint_rig"))
    bpy.context.scene.collection.objects.link(arm)
    arm.show_in_front = False
    for o in bpy.context.view_layer.objects:
        o.select_set(o.name == "pCube1")
    bpy.context.view_layer.objects.active = cube()
    hover()


@step
def s_alt_a1():
    key('A', alt=True)


@step
def s_alt_a1_check():
    arm = bpy.data.objects["joint_rig"]
    check(f"Alt+A 1: joint X-ray (armature In Front {arm.show_in_front})", arm.show_in_front
          and space().show_object_viewport_armature)
    key('A', alt=True)


@step
def s_alt_a2_check():
    arm = bpy.data.objects["joint_rig"]
    check("Alt+A 2: everything, X-ray off", not arm.show_in_front and space().show_object_viewport_armature
          and space().show_object_viewport_curve)
    key('A', alt=True)


@step
def s_alt_a3_check():
    sp = space()
    check("Alt+A 3: meshes only (joints and curves hidden)", not sp.show_object_viewport_armature
          and not sp.show_object_viewport_curve and sp.show_object_viewport_mesh)
    key('A', alt=True)
    C["persp"] = view3d()[1].data.is_perspective


@step
def s_alt_p():
    check("Alt+A 4: back to joint X-ray, joints shown", space().show_object_viewport_armature
          and bpy.data.objects["joint_rig"].show_in_front)
    key('P', alt=True)


@step
def s_alt_p_check():
    check(f"Alt+P: persp -> ortho ({C['persp']} -> {view3d()[1].data.is_perspective})",
          C["persp"] and not view3d()[1].data.is_perspective)
    key('P', alt=True)


@step
def s_alt_p_back():
    check("Alt+P again: back to persp", view3d()[1].data.is_perspective)
    C["p0"] = screen_x()
    C["loc0"] = cube().location.copy()


@step
def s_nudge():
    key('RIGHT_ARROW', alt=True)


@step
def s_nudge_check():
    p1 = screen_x()
    d = p1 - C["p0"]
    check(f"Alt+Right: the cube moves one pixel right ({d.x:.3f}, {d.y:.3f} px)",
          abs(d.x - 1.0) < 0.05 and abs(d.y) < 0.05 and cube().location != C["loc0"])
    C["tool0"] = tool()
    ev('ACCENT_GRAVE', 'PRESS')


@step
def s_tweak_held():
    check(f"` held: Tweak tool ({C['tool0']} -> {tool()})", C["tool0"] == "builtin.move" and tool() == "builtin.select")
    ev('ACCENT_GRAVE', 'RELEASE')


@step
def s_tweak_released():
    check(f"` released: back to Move ({tool()})", tool() == "builtin.move")
    cam = bpy.data.objects.new("camera1", bpy.data.cameras.new("camera1"))
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (0, -0.3, 0.1)
    cam.rotation_euler = (1.4, 0, 0)
    bpy.context.scene.camera = cam
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.view3d.view_camera()
    hover()


@step
def s_pan_start():
    C["off0"] = tuple(view3d()[1].data.view_camera_offset)
    ev('BACK_SLASH', 'PRESS')
    _a, r = view3d()
    ev('LEFTMOUSE', 'PRESS', x=r.x + r.width // 2, y=r.y + r.height // 2)


@step
def s_pan_move():
    _a, r = view3d()
    for i in range(1, 5):
        ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2 + 20 * i, y=r.y + r.height // 2)


@step
def s_pan_end():
    _a, r = view3d()
    ev('LEFTMOUSE', 'RELEASE', x=r.x + r.width // 2 + 80, y=r.y + r.height // 2)
    ev('BACK_SLASH', 'RELEASE')


@step
def s_pan_check():
    off = tuple(view3d()[1].data.view_camera_offset)
    check(f"\\ + LMB drag right pans the camera view ({C['off0']} -> {off}), the camera stays",
          off[0] < C["off0"][0] - 1e-4 and abs(off[1] - C["off0"][1]) < 1e-6
          and abs(bpy.data.objects["camera1"].location.x) < 1e-9)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step87_pan_zoom.png"))


run()
