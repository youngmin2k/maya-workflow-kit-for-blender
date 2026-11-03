"""In the Maya Workflow Kit layout: one tool across object / component modes.

Maya 2022 keeps currentCtx when the selection mode changes: W then F9 stays
moveSuperContext, F8 back too; E + F10 = rotate, R + F11 = scale, Q + F9 = select, and W picked in component mode
is still Move after F8. Here: the 3D View keys, then the active tool of the mode we are in (and the kit Move / Scale
manipulator widget). The RMB marking menu's Vertex item runs allset.mm_component like a click on it."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
KIT_WIDGET = "ALLSET_GGT_xform"


def key(type):
    ev(type, 'PRESS')
    ev(type, 'RELEASE')


def centre():
    _a, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)


def tool():
    t = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
    return (t.idname, t.widget) if t else (None, None)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


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
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    cube = bpy.data.objects["pCube1"]
    for o in bpy.context.scene.objects:
        o.select_set(o == cube)
    bpy.context.view_layer.objects.active = cube
    centre()


# (key pressed, expected mode afterwards, expected tool, kit widget expected); one key per tick, checked next tick
SEQ = [
    ("W", 'OBJECT', "builtin.move", True),
    ("F9", 'EDIT_MESH', "builtin.move", True),
    ("F8", 'OBJECT', "builtin.move", True),
    ("E", 'OBJECT', "builtin.rotate", True),
    ("F10", 'EDIT_MESH', "builtin.rotate", True),
    ("F8", 'OBJECT', "builtin.rotate", True),
    ("R", 'OBJECT', "builtin.scale", True),
    ("F11", 'EDIT_MESH', "builtin.scale", True),
    ("W", 'EDIT_MESH', "builtin.move", True),       # W picked in component mode ...
    ("F8", 'OBJECT', "builtin.move", True),         # ... is still Move in object mode
    ("Q", 'OBJECT', None, False),                   # Q = a select tool (which one: the kit's Q binding)
    ("F9", 'EDIT_MESH', "=Q", False),
    ("F8", 'OBJECT', "=Q", False),
]
C = {}


def _press(i):
    def fn():
        if i > 0:
            k, mode, want, widget = SEQ[i - 1]
            idname, wid = tool()
            if k == "Q":
                C["Q"] = idname
                check(f"Q: a select tool in object mode ({idname})", bool(idname) and idname.startswith("builtin.select"))
            else:
                w = C.get("Q") if want == "=Q" else want
                check(f"{k}: {mode} with {w} (now {bpy.context.mode} / {idname})",
                      bpy.context.mode == mode and idname == w)
                if widget:
                    check(f"{k}: the kit Move / Rotate / Scale manipulator ({wid})", wid == KIT_WIDGET)
            if k == "F9" and i == 2 and SHOTS:
                screenshot(os.path.join(SHOTS, "gui_step174_w_f9.png"))
        if i < len(SEQ):
            centre()
            key(SEQ[i][0])
    fn.__name__ = f"s_key_{i}"
    return fn


for _i in range(len(SEQ) + 1):
    step(_press(_i))
    step(redraw)


@step
def s_rmb_vertex():
    """E in object mode, then the RMB marking menu's Vertex item (allset.mm_component) -> rotate in vertex mode."""
    key("E")


step(redraw)


@step
def s_rmb_vertex_run():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.mm_component(type='VERT')
    redraw()


step(redraw)
step(redraw)


@step
def s_rmb_vertex_check():
    idname, _w = tool()
    check(f"RMB Vertex after E: EDIT_MESH with builtin.rotate (now {bpy.context.mode} / {idname})",
          bpy.context.mode == 'EDIT_MESH' and idname == "builtin.rotate")
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step174_rmb_vertex.png"))


run()
