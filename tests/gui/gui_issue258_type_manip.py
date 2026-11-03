"""Issue #258 Type Manipulator in a real UI: in the Maya layout a type "AB" with its Type Manipulator on — a click on
"B" picks that character, a drag on the Move manipulator's X arrow moves only "B", and a click on empty space turns
the manipulator off while "B" stays moved."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win, load_maya_layout, scale  # noqa: E402

C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def tm():
    return mod("operators.type_manip")


def override():
    return bpy.context.temp_override(window=win(), area=view3d()[0], region=view3d()[1])


def screen(world):
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, world)
    return Vector((region.x + p.x, region.y + p.y))


def text():
    return bpy.data.objects[C["ob"]]


def box_centre(index):
    with override():
        boxes = dict(tm().screen_boxes(bpy.context, text()))
    _area, region = view3d()
    b = boxes[index]
    return Vector((region.x + (b[0] + b[2]) / 2, region.y + (b[1] + b[3]) / 2))


def char_mid(index):
    with override():
        _pivot, (lo, hi) = tm().characters(text(), bpy.context.evaluated_depsgraph_get())[index]
    return Vector((float(lo[0] + hi[0]) / 2, float(lo[1] + hi[1]) / 2, float(lo[2] + hi[2]) / 2))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_type():
    bpy.ops.allset.keymap_activate()
    with override():
        ob = mod("operators.create").create(bpy.context, 'TEXT')
        ob.data.body = "AB"
        for o in bpy.context.view_layer.objects:
            o.select_set(o == ob)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.view3d.view_selected()
        C["ob"] = ob.name
        check("Modify > Transformation Tools > Type Manipulator turns it on",
              bpy.ops.allset.type_manipulator() == {'FINISHED'})
    h = tm().handle_of(text())
    check(f"the handle stands for the first character and is selected ({h and h.get(tm().CHAR)})",
          h is not None and h.get(tm().CHAR) == 0 and h.select_get())
    _area, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + 40)


@step
def s_w():
    tap('W')


@step
def s_hover_b():
    C["a0"], C["b0"] = char_mid(0), char_mid(1)
    C["p"] = box_centre(1)
    ev('MOUSEMOVE', 'NOTHING', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_press_b():
    ev('LEFTMOUSE', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_release_b():
    ev('LEFTMOUSE', 'RELEASE', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_picked():
    h = tm().handle_of(text())
    check(f"a click on B picks it ({h and h.get(tm().CHAR)}; handle selected {h and h.select_get()})",
          h is not None and h.get(tm().CHAR) == 1 and h.select_get())
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_hover_arrow():
    h = tm().handle_of(text())
    c = h.matrix_world.translation.copy()
    _area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, c)
    w = region_2d_to_location_3d(region, region.data, p + Vector((1, 0)), c)
    C["px_world"] = (w - c).length
    n = mod("ui.manipulator").ARROW_PX * bpy.context.preferences.view.gizmo_size / 75.0 * scale()
    C["p"] = screen(c + Vector((1, 0, 0)) * n * 0.8 * C["px_world"])
    ev('MOUSEMOVE', 'NOTHING', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_press():
    ev('LEFTMOUSE', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_move1():
    ev('MOUSEMOVE', 'NOTHING', x=int(C["p"].x) + 30, y=int(C["p"].y))


@step
def s_move2():
    ev('MOUSEMOVE', 'NOTHING', x=int(C["p"].x) + 60, y=int(C["p"].y))


@step
def s_release():
    ev('LEFTMOUSE', 'RELEASE', x=int(C["p"].x) + 60, y=int(C["p"].y))


@step
def s_moved():
    want = 60 * C["px_world"]
    db, da = char_mid(1) - C["b0"], char_mid(0) - C["a0"]
    values = tm().xforms(text().data).get(1)
    check(f"the X arrow drag moves only B along X (B {db.x / want:.2f} of the drag, y {db.y / want:.3f}; "
          f"A {da.length / want:.3f}; stored {values and [round(v, 3) for v in values[:3]]})",
          db.x > 0.5 * want and abs(db.y) < 0.05 * want and da.length < 0.01 * want and values is not None)
    _area, r = view3d()
    C["p"] = Vector((r.x + 30, r.y + 30))
    ev('MOUSEMOVE', 'NOTHING', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_press_empty():
    ev('LEFTMOUSE', 'PRESS', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_release_empty():
    ev('LEFTMOUSE', 'RELEASE', x=int(C["p"].x), y=int(C["p"].y))


@step
def s_wait():
    pass


@step
def s_off():
    check(f"a click on empty space turns the manipulator off ({tm().handle_of(text())})",
          tm().handle_of(text()) is None)
    db = char_mid(1) - C["b0"]
    check(f"B stays moved ({db.x:.4f}) and the type keeps its modifier",
          db.x > 0.5 * 60 * C["px_world"] and tm().modifier(text()) is not None)


run()
