"""In a real UI: Maya selection priority in object mode — a curve in front of or behind the cube
wins a click over the cube, joints (armature) too; Shift / Ctrl / Ctrl+Shift keep Maya's meaning; a click
on the cube alone and the option off are Blender's pick."""

import os
import sys

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def prefs():
    return bpy.context.preferences.addons[MODULE].preferences


def cube():
    return bpy.data.objects["Cube"]


def screen_xy(co):
    area, region = view3d()
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, co)
    return region.x + int(round(p.x)), region.y + int(round(p.y))


def eye():
    area, _region = view3d()
    return area.spaces.active.region_3d.view_matrix.inverted().translation


def view_rot():
    area, _region = view3d()
    return area.spaces.active.region_3d.view_rotation


def cube_spot():
    """A point on the cube far from the circle (and from the circle's origin at the screen centre)."""
    c = screen_xy(Vector())
    far = max((screen_xy(cube().matrix_world @ v.co) for v in cube().data.vertices),
              key=lambda p: (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2)
    return c[0] + int(0.8 * (far[0] - c[0])), c[1] + int(0.8 * (far[1] - c[1]))


def circle_point():
    ob = C["circle"]
    return screen_xy(ob.matrix_world @ ob.data.splines[0].bezier_points[0].co)


def click(xy, **mods):
    x, y = xy
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, **mods)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y, **mods)


def selected():
    return sorted(o.name for o in bpy.context.selected_objects)


def active():
    ob = bpy.context.view_layer.objects.active
    return ob and ob.name


def place_circle(t):
    """The circle on the line eye -> cube centre: t > 0 between (in front), t < 0 behind the cube; it faces
    the view, so its first point (local +x) lies inside the cube's silhouette."""
    ob = C["circle"]
    ob.location = cube().location + (eye() - cube().location) * t
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = view_rot()
    bpy.context.view_layer.update()


@step
def s_setup():
    setup()
    for ob in list(bpy.data.objects):
        if ob.name != "Cube":
            bpy.data.objects.remove(ob)
    cube().location = (0, 0, 0)
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    cu = bpy.data.curves.new("ctrl", 'CURVE')
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(3)
    for p, (x, y) in zip(sp.bezier_points, ((0.4, 0), (0, 0.4), (-0.4, 0), (0, -0.4))):
        p.co = (x, y, 0)
        p.handle_left_type = p.handle_right_type = 'AUTO'
    sp.use_cyclic_u = True
    C["circle"] = bpy.data.objects.new("ctrl", cu)
    bpy.context.scene.collection.objects.link(C["circle"])
    place_circle(0.3)


@step
def s_front():
    C["xy"] = circle_point()
    click(C["xy"])


@step
def s_front_check():
    check(f"curve in front of the cube: click picks the curve ({selected()})", selected() == ["ctrl"])
    check("the curve is the lead (active)", active() == "ctrl")
    shot("gui_step76_front.png")
    click(cube_spot())


@step
def s_cube_check():
    check(f"click on the cube away from the curve: Blender's pick = cube ({selected()})", selected() == ["Cube"])
    click(C["xy"], shift=True)


@step
def s_shift_check():
    check(f"Shift+click the curve toggles it on ({selected()})", selected() == ["Cube", "ctrl"])
    check("Shift+click: the curve becomes the lead", active() == "ctrl")
    click(C["xy"], shift=True)


@step
def s_shift_off_check():
    check(f"Shift+click again toggles it off ({selected()})", selected() == ["Cube"])
    click(C["xy"], shift=True, ctrl=True)


@step
def s_add_check():
    check(f"Ctrl+Shift+click adds the curve ({selected()})", selected() == ["Cube", "ctrl"])
    click(C["xy"], shift=True, ctrl=True)


@step
def s_add_again_check():
    check(f"Ctrl+Shift+click again keeps it (add never removes) ({selected()})", selected() == ["Cube", "ctrl"])
    click(C["xy"], ctrl=True)


@step
def s_ctrl_check():
    check(f"Ctrl+click deselects the curve ({selected()})", selected() == ["Cube"])
    place_circle(-0.35)                      # behind the cube now


@step
def s_behind():
    C["xy"] = circle_point()
    click(C["xy"])


@step
def s_behind_check():
    check(f"curve behind the cube: click still picks the curve ({selected()})", selected() == ["ctrl"])
    shot("gui_step76_behind.png")
    prefs().select_priority = False
    click(C["xy"])


@step
def s_off_check():
    check(f"option off: Blender's depth pick = cube in front of the curve ({selected()})", selected() == ["Cube"])
    prefs().select_priority = True
    # an armature (joint, priority 9) in front of the cube, its bone across the screen centre
    arm_data = bpy.data.armatures.new("rig")
    arm = bpy.data.objects.new("rig", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    C["arm"] = arm
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    bpy.context.view_layer.objects.active = arm
    area, region = view3d()
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0], area=area, region=region,
                                   active_object=arm, object=arm):
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm_data.edit_bones.new("joint1")
        up = view_rot() @ Vector((0, 1, 0))
        base = (eye() - Vector()) * 0.25
        eb.head, eb.tail = base - up * 0.3, base + up * 0.3
        bpy.ops.object.mode_set(mode='OBJECT')
    arm.select_set(False)
    cube().select_set(True)
    bpy.context.view_layer.objects.active = cube()
    C["circle"].hide_set(True)


@step
def s_joint():
    C["xy"] = screen_xy((eye() - Vector()) * 0.25)
    click(C["xy"])


@step
def s_joint_check():
    check(f"joint in front of the cube: click picks the armature ({selected()})", selected() == ["rig"])
    shot("gui_step76_joint.png")


run()
