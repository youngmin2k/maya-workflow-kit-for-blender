"""#105: in a real UI: a Graph Editor shown in the big view has no Blender sidebar (Maya has none), and
View > Show Buffer Curves draws the buffer snapshot grey behind the edited curve (screenshot)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def region():
    return next(r for r in C["area"].regions if r.type == 'WINDOW')


def curve():
    return import_module(MODULE + ".compat").id_fcurve_collection(bpy.data.objects["pCube1"]).find("location", index=0)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    area, reg = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=reg):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.data.objects["pCube1"]
    for f, v in ((1, 0.0), (10, 0.05), (20, 0.0)):
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    import_module(MODULE + ".preferences").get().snap_time_to_selection = False
    C["area"] = area
    area.ui_type = 'FCURVES'
    area.spaces.active.show_region_ui = True       # Blender's sidebar open, like a Graph Editor from a user layout


@step
def s_wait():
    pass


@step
def s_sidebar():
    sp = C["area"].spaces.active
    check(f"the kit closed the Graph Editor sidebar ({sp.show_region_ui})", sp.show_region_ui is False)
    sp.use_normalization = False
    with bpy.context.temp_override(window=win(), area=C["area"], region=region()):
        bpy.ops.graph.view_all()
        for kp in curve().keyframe_points:
            kp.select_control_point = True
        bpy.ops.allset.buffer_snapshot()
    kp = curve().keyframe_points[1]
    kp.co.y += 0.03
    kp.handle_left.y += 0.03
    kp.handle_right.y += 0.03
    curve().update()
    import_module(MODULE + ".preferences").get().graph_show_buffers = True
    C["area"].tag_redraw()


@step
def s_shot_wait():
    C["area"].tag_redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "step198_buffer.png"))
    gb = import_module(MODULE + ".operators.graph_buffers")
    check("the curve has a buffer", gb.has_buffer(curve()))
    with bpy.context.temp_override(window=win(), area=C["area"], region=region()):
        lines = gb.buffer_lines(bpy.context)
    check(f"one buffer polyline is drawn ({len(lines)})", len(lines) >= 1)


@step
def s_swap():
    with bpy.context.temp_override(window=win(), area=C["area"], region=region()):
        bpy.ops.allset.buffer_swap()
    y = curve().keyframe_points[1].co.y
    check(f"Swap Buffer Curve brings the snapshot back ({y:.4f})", abs(y - 0.05) < 1e-6)
    import_module(MODULE + ".preferences").get().graph_show_buffers = False
    C["area"].ui_type = 'VIEW_3D'


run()
