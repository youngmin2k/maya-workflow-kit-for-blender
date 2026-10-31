"""#168: in a real UI, in a Maya user's hand order: two locators turned 30 / 150 deg and a cube ->
Constrain > Orient (targets first, the cube last) -> Channel Box INPUTS orientConstraint1 shows Interp Type = Average
and the cube is turned 90 deg -> click the Interp Type drop-down, pick Shortest (S) -> BW1 = 3 -> Ctrl+Z ->
save, open -> Constrain > Aim with World up type Object up. Shots: gui_step252_*.png."""

import math
import os
import sys
from importlib import import_module

import bpy
from mathutils import Euler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, dock_region, ev, find_button, open_inputs, run, screenshot, scroll_channel_box, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def ci():
    return import_module(MODULE + ".operators.constrain_interp")


def cm():
    return import_module(MODULE + ".operators.constrain_multi")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def cube():
    return bpy.data.objects["pCube1"]


def group():
    return next(iter(cm()._groups(cube())), None)


def z_deg(ob):
    return math.degrees(ob.matrix_world.to_euler().z)


def _empty(name, z):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_euler = Euler((0.0, 0.0, math.radians(z)))
    return ob


def _average_z(zs, ws):
    """Maya Average of rotations about one axis: normalised weighted quaternion sum."""
    c = sum(w * math.cos(math.radians(z) / 2) for z, w in zip(zs, ws))
    s_ = sum(w * math.sin(math.radians(z) / 2) for z, w in zip(zs, ws))
    return math.degrees(2 * math.atan2(s_, c))


def main_region():
    return next(r for r in view3d()[0].regions if r.type == 'WINDOW')


@step
def s_setup():
    setup()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    dock_area('CHANNEL_BOX')
    area, _r = view3d()
    a, b = _empty("locatorA", 30.0), _empty("locatorB", 150.0)
    with bpy.context.temp_override(window=win(), area=area, region=main_region()):
        bpy.ops.allset.create(kind='CUBE')
        c = bpy.context.active_object
        c.name = "pCube1"
        for ob in bpy.context.scene.objects:
            ob.select_set(ob in (a, b, c))
        bpy.context.view_layer.objects.active = c
        res = bpy.ops.allset.constrain(type='COPY_ROTATION')       # Constrain > Orient
    check(f"Constrain > Orient with two targets ({res})", res == {'FINISHED'})
    redraw()


@step
def s_inputs():
    bpy.ops.ed.undo_push(message="Orient constraint")    # the setup ran as script calls (no undo steps of its own)
    open_inputs()
    scroll_channel_box()
    redraw()


@step
def s_average():
    bpy.context.view_layer.update()
    g = group()
    check(f"the node is Average by default ({ci().mode_of(cube(), g)})", ci().mode_of(cube(), g) == ci().AVERAGE)
    check(f"the cube turns to the middle of 30 and 150 ({z_deg(cube()):.4f})", abs(z_deg(cube()) - 90.0) < 0.05)
    cb = import_module(MODULE + ".ui.channel_box")
    check("the blend is not a Channel Box node of its own", len(cb.constraints(cube())) == 2)
    shot("gui_step252_interp_average.png")


# the drop-down has no data path: find the two weight rows under it (their fields do) and go one row up
step(find_button(lambda: (dock_area(), dock_region()), lambda path, cmd: "rows[0]" in path, C, "w0",
                 x_frac=0.7, step_px=4))
step(find_button(lambda: (dock_area(), dock_region()), lambda path, cmd: "rows[1]" in path, C, "w1",
                 x_frac=0.7, step_px=4))


@step
def s_menu_point():
    if C.get("w0") and C.get("w1"):
        C["menu"] = (C["w0"][0], 2 * C["w0"][1] - C["w1"][1])


@step
def s_hover():
    check(f"Interp Type drop-down found ({C.get('menu')})", C.get("menu") is not None)
    if C.get("menu"):
        ev('MOUSEMOVE', 'NOTHING', x=C["menu"][0], y=C["menu"][1])


@step
def s_click():
    if C.get("menu"):
        ev('LEFTMOUSE', 'PRESS', x=C["menu"][0], y=C["menu"][1])
        ev('LEFTMOUSE', 'RELEASE', x=C["menu"][0], y=C["menu"][1])


@step
def s_menu_shot():
    shot("gui_step252_interp_menu.png")
    tap('S')                       # Shortest (the menu's underlined letter)


@step
def s_shortest():
    g = group()
    check(f"picked Shortest ({ci().mode_of(cube(), g)})", ci().mode_of(cube(), g) == ci().SHORTEST)
    check("Shortest needs no kit blend (Blender influence only)", ci().blend_constraint(cube(), g) is None)
    w = cm().weights(cube(), g)
    cube()[w[1][0]] = 3.0                                   # BW1 = 3 (typed in the Channel Box)
    cube().update_tag()
    redraw()


@step
def s_weighted():
    bpy.context.view_layer.update()
    check(f"Shortest 1 : 3 = slerp 3/4 of the way: 120 deg ({z_deg(cube()):.3f})", abs(z_deg(cube()) - 120.0) < 0.05)
    shot("gui_step252_interp_shortest.png")
    r = main_region()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    g = group()
    check(f"Ctrl+Z: Interp Type back to Average ({ci().mode_of(cube(), g)})", ci().mode_of(cube(), g) == ci().AVERAGE)
    C["w"] = [float(cube()[p]) for p, _l in cm().weights(cube(), g)]
    path = os.path.join(bpy.app.tempdir, "gui252.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    C["path"] = path
    bpy.ops.wm.open_mainfile(filepath=path)


@step
def s_reopened():
    g = group()
    bpy.context.view_layer.update()
    want = _average_z([30.0, 150.0], C["w"])
    check(f"after open: Average, the blend still drives the cube ({z_deg(cube()):.4f} / {want:.4f})",
          ci().mode_of(cube(), g) == ci().AVERAGE and ci().blend_constraint(cube(), g) is not None
          and abs(z_deg(cube()) - want) < 0.05)
    bpy.data.objects["locatorB"].rotation_euler.z = math.radians(170.0)
    bpy.context.view_layer.update()


@step
def s_follows():
    bpy.context.view_layer.update()
    want = _average_z([30.0, 170.0], C["w"])
    check(f"moving a target after the open: Average of 30 and 170 ({z_deg(cube()):.3f} / {want:.3f})",
          abs(z_deg(cube()) - want) < 0.05)
    # Constrain > Aim, World up type Object up (an up locator), from the option window's values
    ow = import_module(MODULE + ".operators.option_windows")
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    area, _r = view3d()
    t = bpy.data.objects.new("aimTarget", None)
    up = bpy.data.objects.new("upLocator", None)
    for ob in (t, up):
        bpy.context.scene.collection.objects.link(ob)
    t.location, up.location = (4.0, 2.0, 0.0), (0.0, 0.0, 5.0)
    with bpy.context.temp_override(window=win(), area=area, region=main_region()):
        bpy.ops.allset.create(kind='CUBE')
        c = bpy.context.active_object
        for ob in bpy.context.scene.objects:
            ob.select_set(ob in (t, c))
        bpy.context.view_layer.objects.active = c
        win_ = next(w for w in ow.WINDOWS if w.key == "aim_constraint")
        v = win_.defaults()
        v.update(world_up_type="Object up", world_up_object="upLocator")
        res = win_.run(bpy.context, v)
    C["aim_owner"] = c.name
    check(f"Constrain > Aim, Object up ({res})", res == {'FINISHED'})
    redraw()


@step
def s_aim():
    bpy.context.view_layer.update()
    c = bpy.data.objects[C["aim_owner"]]
    m = c.matrix_world.to_3x3().normalized()
    aim = (bpy.data.objects["aimTarget"].location - c.location).normalized()
    up = bpy.data.objects["upLocator"].location - c.location
    up_perp = (up - up.dot(aim) * aim).normalized()
    # Maya: +X at the target, +Y (Blender Z for an object) towards the up locator across the aim
    check(f"aim +X at the target ({m.col[0].dot(aim):.5f})", m.col[0].dot(aim) > 0.9999)
    check(f"up +Y toward the up object ({m.col[2].dot(up_perp):.5f})", m.col[2].dot(up_perp) > 0.9999)
    cb = import_module(MODULE + ".ui.channel_box")
    check("one aimConstraint node in the Channel Box", len(cb.constraints(c)) == 1)
    for ob in bpy.context.scene.objects:
        ob.select_set(ob == c)
    bpy.context.view_layer.objects.active = c
    open_inputs()
    scroll_channel_box()
    redraw()


@step
def s_aim_shot():
    shot("gui_step252_aim_object_up.png")


run()
