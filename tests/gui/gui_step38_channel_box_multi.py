"""In a real UI: two cubes selected, type "+=5" in the Channel Box Translate X field ->
both move by 5 display units (each from its own value); AE tab of a Maya lambert material;
screenshots."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, dock_region, ev, find_button, px, run, screenshot, setup, step, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"tries": 0}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def dock():
    return dock_area(), dock_region()


def cubes():
    return bpy.data.objects["Cube"], bpy.data.objects["Cube2"]


@step
def s_setup():
    C["x"], C["y"] = setup()
    a = bpy.data.objects["Cube"]
    b = a.copy()
    b.name = "Cube2"
    bpy.context.scene.collection.objects.link(b)
    a.location.x, b.location.x = 1.0, 4.0
    for o in bpy.context.view_layer.objects:
        o.select_set(o in (a, b))
    bpy.context.view_layer.objects.active = a
    dock_area('CHANNEL_BOX')     # Maya's tab stack right of the viewport (was the 3D View sidebar)
    redraw()


@step
def s_wait():
    redraw()


@step
def s_cb_shot():
    shot("gui_step38_cb_before.png")
    from importlib import import_module as im
    md = im(MODULE + ".ui.maya_dock")
    check("Channel Box drawn in its own dock area with two objects selected (screenshot)",
          md.role(dock_area()) == 'STACK' and md.current_tab() == 'CHANNEL_BOX')


# Translate X value field: looked up by its data path (Scene.allset_cb.tx_text) along the row ~114 px under the top
step(find_button(dock, lambda path, _cmd: path.endswith("tx_text"), C, "field", rows=(px(114), px(90), px(140))))


@step
def s_hover_field():
    check(f"Translate X field found in the Channel Box ({C['field']})", C["field"] is not None)
    if C["field"]:
        ev('MOUSEMOVE', 'NOTHING', x=C["field"][0], y=C["field"][1])


@step
def s_click_field():
    x, y = C["field"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_type():
    ev('A', 'PRESS', ctrl=True)     # select the whole text, then type over it
    ev('A', 'RELEASE', ctrl=True)
    for ch in "+=5":
        ev('TEXTINPUT', 'PRESS', unicode=ch)
    redraw()


@step
def s_typed_shot():
    shot("gui_step38_cb_typing.png")
    tap('RET')


@step
def s_applied():
    a, b = cubes()
    check(f"'+=5' moved the lead Cube 1 -> {a.location.x:.3f}", abs(a.location.x - 6.0) < 1e-4)
    check(f"... and Cube2 from its own value 4 -> {b.location.x:.3f}", abs(b.location.x - 9.0) < 1e-4)
    redraw()


@step
def s_after_shot():
    shot("gui_step38_cb_after.png")
    material = import_module(MODULE + ".operators.material")
    a, _b = cubes()
    mat = material.new_material('LAMBERT')
    a.data.materials.clear()
    a.data.materials.append(mat)
    C["mat"] = mat.name
    bpy.context.window_manager.allset_dock = 'ATTRIBUTE_EDITOR'
    bpy.ops.allset.ae_tab(key="MAT:0")
    redraw()


@step
def s_ae_wait():
    redraw()


@step
def s_ae_shot():
    shot("gui_step38_ae_lambert.png")
    ae = import_module(MODULE + ".ui.attribute_editor")
    a, _b = cubes()
    label = next(t for t in ae.tabs(a) if t[0] == "MAT:0")
    check(f"AE material tab is a lambert ({label})", label[2] == "lambert" and label[1] == C["mat"])


run()
