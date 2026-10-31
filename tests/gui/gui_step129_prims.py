"""#11, #12: in a real UI: Create > Polygon Primitives > Cylinder shows polyCylinder1 in Channel Box INPUTS;
typing 2 into its Subdivisions Caps field rebuilds the caps (42 -> 82 vertices), Ctrl+Z brings the fan caps back;
a NURBS circle's Sections field (makeNurbCircle1) takes "+=4". Screenshots."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, dock_region, ev, find_button, open_inputs, run, scroll_channel_box, screenshot, setup, step, tap  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def dock():
    return dock_area(), dock_region()


def _type(text):
    ev('A', 'PRESS', ctrl=True)     # select the whole text, then type over it
    ev('A', 'RELEASE', ctrl=True)
    for ch in text:
        ev('TEXTINPUT', 'PRESS', unicode=ch)


@step
def s_setup():
    setup()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.allset.create(kind='CYLINDER')
    C["ob"] = bpy.context.view_layer.objects.active.name
    bpy.ops.ed.undo_push(message="Create Cylinder")   # script calls push no undo step: mark the start
    dock_area('CHANNEL_BOX')
    redraw()


@step
def s_wait():
    redraw()


@step
def s_inputs_shot():
    shot("gui_step129_cylinder_inputs.png")
    ob = bpy.data.objects[C["ob"]]
    check(f"Create > Cylinder: {C['ob']} with 42 vertices (caps = centre fans)", len(ob.data.vertices) == 42)


@step
def s_open_cylinder_node():
    open_inputs("polyCylinder1")   # INPUTS nodes start collapsed (Maya)
    scroll_channel_box()           # ... and a long Channel Box scrolls inside its part
    for a in bpy.context.window.screen.areas:
        a.tag_redraw()


@step
def s_wait_open_cylinder():
    pass


step(find_button(dock, lambda path, _cmd: path.endswith("subdivisionsCaps_text"), C, "caps", x_frac=0.8,
                 step_px=8))


@step
def s_hover_caps():
    check(f"Subdivisions Caps field of polyCylinder1 found in INPUTS ({C['caps']})", C["caps"] is not None)
    if C["caps"]:
        ev('MOUSEMOVE', 'NOTHING', x=C["caps"][0], y=C["caps"][1])


@step
def s_click_caps():
    x, y = C["caps"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_type_caps():
    _type("2")
    redraw()


@step
def s_enter():
    tap('RET')


@step
def s_caps_applied():
    ob = bpy.data.objects[C["ob"]]
    n = len(ob.data.vertices)
    check(f"typing 2 into Subdivisions Caps rebuilt the cylinder: {n} vertices (Maya 82)", n == 82)
    check("the node now reads 2", bpy.context.scene.allset_creation.subdivisionsCaps_text == "2")
    redraw()


@step
def s_caps_shot():
    shot("gui_step129_cylinder_caps2.png")
    x, y = C["caps"]
    ev('MOUSEMOVE', 'NOTHING', x=x - 300 if x > 400 else x + 300, y=y)   # off the field: Ctrl+Z goes to the view


@step
def s_undo():
    from sim import view3d
    _area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    ob = bpy.data.objects[C["ob"]]
    n = len(ob.data.vertices)
    check(f"Ctrl+Z brings the one-ring fan caps back: {n} vertices", n == 42)
    check("... and the node value 1", bpy.context.scene.allset_creation.subdivisionsCaps_text == "1")
    prim_history = import_module(MODULE + ".operators.prim_history")
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.allset.create(kind='NURBS_CIRCLE')
    C["circle"] = bpy.context.view_layer.objects.active.name
    check("Create > NURBS Circle has makeNurbCircle1 (#11)",
          prim_history.node_of(bpy.data.objects[C["circle"]])[1]["name"] == "makeNurbCircle1")
    C.pop("sections", None)
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_open_circle_node():
    open_inputs("makeNurbCircle1")
    scroll_channel_box()
    for a in bpy.context.window.screen.areas:
        a.tag_redraw()


@step
def s_wait_open_circle():
    pass


step(find_button(dock, lambda path, _cmd: path.endswith("sections_text"), C, "sections", x_frac=0.8, step_px=8))


@step
def s_hover_sections():
    check(f"Sections field of makeNurbCircle1 found in INPUTS ({C['sections']})", C["sections"] is not None)
    if C["sections"]:
        ev('MOUSEMOVE', 'NOTHING', x=C["sections"][0], y=C["sections"][1])


@step
def s_click_sections():
    x, y = C["sections"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_type_sections():
    _type("+=4")
    redraw()


@step
def s_enter2():
    tap('RET')


@step
def s_sections_applied():
    ob = bpy.data.objects[C["circle"]]
    n = len(ob.data.splines[0].points)
    check(f"'+=4' on Sections: the circle has {n} CVs (8 + 4)", n == 12)
    redraw()


@step
def s_circle_shot():
    shot("gui_step129_circle_sections.png")


run()
