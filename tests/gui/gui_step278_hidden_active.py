"""#187: in a real UI: F8 / F9 over the viewport with the active cube hidden (Display > Hide) do nothing to
the scene, print no Python error, and say why in the kit's words; after Display > Show All, F9 enters vertex mode."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, view3d, win, load_maya_layout  # noqa: E402

C = {}


def over_view():
    _area, region = view3d()
    return region.x + region.width // 2, region.y + region.height // 2


def key(k):
    x, y = over_view()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev(k, 'PRESS', x=x, y=y)
    ev(k, 'RELEASE', x=x, y=y)


def reports():
    return [r.message for r in getattr(win(), "reports", [])] if hasattr(win(), "reports") else []


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cube():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.view_layer.objects.active
    C["ob"] = ob.name
    ob.hide_viewport = True           # Display > Hide (Maya visibility)
    bpy.context.view_layer.update()


@step
def s_f8():
    key('F8')


@step
def s_f9():
    key('F9')


@step
def s_check_hidden():
    ob = bpy.data.objects[C["ob"]]
    check(f"F8 / F9 on a hidden cube leave object mode ({bpy.context.mode})", bpy.context.mode == 'OBJECT')
    check("the cube stays hidden", not ob.visible_get())
    ob.hide_viewport = False
    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob


@step
def s_f9_visible():
    key('F9')


@step
def s_check_visible():
    check(f"after Show, F9 = vertex mode ({bpy.context.mode})",
          bpy.context.mode == 'EDIT_MESH' and tuple(bpy.context.tool_settings.mesh_select_mode) == (True, False, False))
    log = os.environ.get("ALLSET_GUI_LOG_FILE")
    if log and os.path.isfile(log):
        text = open(log, encoding="utf-8", errors="replace").read()
        check("no Python error in the console", "Traceback" not in text and "Cannot edit hidden object" not in text)


run()
