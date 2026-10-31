"""Issue #178: in a real UI: Maya D hold with another add-on that also binds D, then D + drag on the Move
manipulator moves only the pivot.

An add-on registered after the kit adds its own D item to the add-on keyconfig's "Object Mode" keymap (the reporter's
"Draw" add-on); D must still start the kit's pivot edit (Maya mode = Maya keys first), and the other add-on's item
must come back first when Maya mode is off."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, view3d, win  # noqa: E402

C = {}
FOREIGN = "wm.context_toggle"        # stands in for the other add-on's operator


def ts():
    return bpy.context.scene.tool_settings


def ov():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def foreign_add():
    kc = bpy.context.window_manager.keyconfigs.addon
    km = kc.keymaps.new("Object Mode", space_type='EMPTY', region_type='WINDOW')
    kmi = km.keymap_items.new(FOREIGN, 'D', 'PRESS')
    kmi.properties.data_path = "space_data.show_gizmo"   # a visible, harmless effect
    C["foreign"] = (km, kmi)


def handle_point(ob, axis, frac):
    area, region = view3d()
    o = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation)
    a = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation + Vector(axis) * 0.1)
    d = (a - o).normalized()
    size = bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale
    p = o + d * size * frac
    return Vector((region.x + p.x, region.y + p.y))


@step
def s_setup():
    C["x"], C["y"] = setup()
    foreign_add()                                   # the other add-on registers after the kit
    cube = bpy.data.objects["Cube"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is cube)
    bpy.context.view_layer.objects.active = cube
    for name in ("Camera", "Light"):
        bpy.data.objects[name].hide_set(True)
    with ov():
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    C["gizmo"] = view3d()[0].spaces.active.show_gizmo


@step
def s_wait_watch():
    pass        # the keymap watch (1 s) puts the Maya items first again


@step
def s_wait_watch2():
    pass


@step
def s_wait_watch3():
    ob = bpy.data.objects["Cube"]
    C["p"] = handle_point(ob, (1, 0, 0), 0.6)
    C["to"] = handle_point(ob, (1, 0, 0), 1.1)
    C["loc"] = ob.location.copy()
    ev('MOUSEMOVE', 'NOTHING', x=int(C["p"].x), y=int(C["p"].y))
    ev('MOUSEMOVE', 'NOTHING', x=int(C["p"].x) + 1, y=int(C["p"].y))


@step
def s_d_press():
    ev('D', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_held():
    check("D with another add-on's D item: the kit's pivot edit starts", ts().use_transform_data_origin)
    check("the other add-on's operator didn't run", view3d()[0].spaces.active.show_gizmo == C["gizmo"])
    ev('LEFTMOUSE', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_drag():
    for i in range(1, 9):
        f = i / 8
        q = C["p"] + (C["to"] - C["p"]) * f
        ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y))


@step
def s_release():
    ev('LEFTMOUSE', 'RELEASE', x=int(C["to"].x), y=int(C["to"].y))


@step
def s_d_up():
    ev('D', 'RELEASE', x=int(C["to"].x), y=int(C["to"].y))


@step
def s_done():
    ob = bpy.data.objects["Cube"]
    check(f"D + drag moved only the pivot (translate {tuple(round(v, 3) for v in ob.location)}, "
          f"pivot offset x {ob.delta_location.x:.3f})",
          (ob.location - C["loc"]).length < 1e-6 and abs(ob.delta_location.x) > 1e-3)
    check("pivot edit off after D", not ts().use_transform_data_origin)
    # Maya mode off: the kit's items go, the other add-on's D is the user's again
    import_module(MODULE + ".switch").set_mode(False, layout=False)


@step
def s_off_wait():
    pass


@step
def s_off():
    C["gizmo"] = view3d()[0].spaces.active.show_gizmo
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('D', 'PRESS', x=C["x"], y=C["y"])
    ev('D', 'RELEASE', x=C["x"], y=C["y"])


@step
def s_off_check():
    check("Maya mode off: the other add-on's D runs again",
          view3d()[0].spaces.active.show_gizmo != C["gizmo"])
    km, kmi = C["foreign"]
    km.keymap_items.remove(kmi)


run()
