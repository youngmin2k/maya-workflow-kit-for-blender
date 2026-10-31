"""Issue #173: in a real UI: the panel Show menu's Selection Highlighting and NURBS Curves rows change
what the viewport draws (icon == setting == behaviour), judged by the screen pixels of the 3D View.

Rig like the reporter's: armature `rig`, its control bone drawn as a hidden circle (bone custom shape), the default
Cube parented to the rig. Chain: Cube selected (green kit wire) -> Selection Highlighting off (no green) -> on ->
Pose mode, control picked (no green on the child mesh) -> NURBS Curves off (control circle gone) -> on (back).
"""

import os
import sys
import tempfile
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
TMP = tempfile.mkdtemp(prefix="allset262_")
C = {}
LEAD = (0x43, 0xff, 0xa3)            # kit lead wire (ui/selection_wire.LEAD)


def ov():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def space():
    return view3d()[0].spaces.active


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def grab(name):
    """Screenshot (shows the previous frame: call one step after a change) -> (H, W, 3) 0..255 of the 3D View."""
    import numpy as np
    path = os.path.join(SHOTS or TMP, name)
    screenshot(path)
    img = bpy.data.images.load(path)
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    a = (a.reshape(h, w, 4)[:, :, :3] * 255).round()
    area = view3d()[0]
    return a[area.y:area.y + area.height, area.x:area.x + area.width]


def green(a):
    import numpy as np
    return int((np.abs(a - np.array(LEAD)).max(axis=2) < 40).sum())


def diff(a, b):
    import numpy as np
    return int((np.abs(a - b).max(axis=2) > 40).sum())


@step
def s_setup():
    C["x"], C["y"] = setup()
    with ov():
        bpy.ops.object.armature_add(location=(0, 0, 0))
        arm = bpy.context.active_object
        arm.name = "rig"
        bpy.ops.curve.primitive_bezier_circle_add(radius=2.2, location=(0, 0, 0))
        wgt = bpy.context.active_object
        wgt.name = "WGT_chest"
        bpy.ops.view3d.view_axis(type='FRONT')
    arm.pose.bones["Bone"].custom_shape = wgt
    wgt.hide_viewport = True
    cube = bpy.data.objects["Cube"]
    cube.parent = arm
    for name in ("Camera", "Light"):
        bpy.data.objects[name].hide_set(True)
    for o in bpy.context.view_layer.objects:
        o.select_set(o is cube)
    bpy.context.view_layer.objects.active = cube
    redraw()


@step
def s_frame():
    with ov():
        bpy.ops.view3d.view_all()
    redraw()


@step
def s_wait():
    pass


@step
def s_cube_on():
    n = green(grab("gui_step262_1_cube_selected.png"))
    check(f"Cube selected, Selection Highlighting on: kit lead wire drawn ({n} px)", n > 50)
    pm = import_module(MODULE + ".ui.panel_menus")
    with ov():
        check("Show > Selection Highlighting row starts checked", pm.state(bpy.context, "SELECTION_HILITE") is True)
        pm.apply(bpy.context, "SELECTION_HILITE")
        check("the row is unchecked after the click", pm.state(bpy.context, "SELECTION_HILITE") is False)
    redraw()


@step
def s_off_wait():
    pass


@step
def s_cube_off():
    n = green(grab("gui_step262_2_highlighting_off.png"))
    check(f"Selection Highlighting off: no kit wire ({n} px)", n == 0)
    sw = import_module(MODULE + ".ui.selection_wire")
    with ov():
        check("highlighted() empty with Selection Highlighting off", sw.highlighted(bpy.context) == [])
        check("Blender's outline is off too", not space().overlay.show_outline_selected)
        import_module(MODULE + ".ui.panel_menus").apply(bpy.context, "SELECTION_HILITE")   # back on
    arm = bpy.data.objects["rig"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is arm)
    bpy.context.view_layer.objects.active = arm
    with ov():
        bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["Bone"].select = True
    arm.data.bones.active = arm.data.bones["Bone"]
    redraw()


@step
def s_pose_wait():
    pass


@step
def s_pose():
    a = grab("gui_step262_3_pose_control_picked.png")
    n = green(a)
    check(f"Pose mode, control picked, highlighting on: the child Cube gets no kit wire ({n} px)", n == 0)
    C["curves_on"] = a
    pm = import_module(MODULE + ".ui.panel_menus")
    with ov():
        check("Show > NURBS Curves row starts checked", pm.state(bpy.context, "SHOW_NURBS_CURVES") is True)
        pm.apply(bpy.context, "SHOW_NURBS_CURVES")
    redraw()


@step
def s_curves_wait():
    pass


@step
def s_curves_off():
    a = grab("gui_step262_4_nurbs_curves_off.png")
    d = diff(a, C["curves_on"])
    pm = import_module(MODULE + ".ui.panel_menus")
    compat = import_module(MODULE + ".compat")
    pb = bpy.data.objects["rig"].pose.bones["Bone"]
    with ov():
        check("NURBS Curves row unchecked = view flag off",
              pm.state(bpy.context, "SHOW_NURBS_CURVES") is False and not space().show_object_viewport_curve)
    check("the curve-shaped control bone is hidden", compat.bone_hidden(pb))
    check(f"the control circle is gone from the view ({d} px changed)", d > 100)
    C["curves_off"] = a
    with ov():
        pm.apply(bpy.context, "SHOW_NURBS_CURVES")
    redraw()


@step
def s_back_wait():
    pass


@step
def s_curves_back():
    a = grab("gui_step262_5_nurbs_curves_on.png")
    compat = import_module(MODULE + ".compat")
    pb = bpy.data.objects["rig"].pose.bones["Bone"]
    check("NURBS Curves on again: the control bone is shown", not compat.bone_hidden(pb))
    d = diff(a, C["curves_off"])
    check(f"the control circle is drawn again ({d} px changed)", d > 100)
    with ov():
        bpy.ops.object.mode_set(mode='OBJECT')


run()
