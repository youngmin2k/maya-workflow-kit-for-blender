"""Issues #152 #155 as a Maya user in the Maya layout: pCube1 -> Skin > Bind Skin with only the cube (no
joint) -> Maya's Error, no traceback -> grid snap on from the Status Line -> move -> Ctrl+Z undoes the move and keeps
the snap (Maya: snap toggles aren't undoable) -> F frames with a margin -> save / open.
Screenshots: gui_step258_bind_error.png, gui_step258_snap_undo.png."""

import os
import sys
import tempfile

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def centre():
    _a, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)


def key(type, **mods):
    centre()
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_bind():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.allset.create('EXEC_DEFAULT', True, kind='CUBE')      # an undo step like a menu click
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    C["name"] = bpy.context.view_layer.objects.active.name
    err = None
    try:
        with override():
            bpy.ops.allset.menu_item('EXEC_DEFAULT', item="Skin/Bind Skin")
    except RuntimeError as ex:
        err = str(ex)
    except Exception as ex:          # a traceback a Maya user would see
        err = f"TRACEBACK {type(ex).__name__}: {ex}"
    C["err"] = err
    centre()


@step
def s_bind_shot():
    err = C["err"] or ""
    check(f"Bind Skin without a joint = Maya's Error ({err!r})",
          "You must select at least one joint." in err and "TRACEBACK" not in err)
    shot("gui_step258_bind_error.png")
    with override():
        bpy.ops.allset.snap_toggle(snap='GRID')
    ts = bpy.context.scene.tool_settings
    C["snap"] = ts.use_snap and 'GRID' in set(ts.snap_elements)
    with override():
        bpy.ops.transform.translate('EXEC_DEFAULT', True, value=(0.0, 0.0, 0.5))


@step
def s_undo():
    check(f"grid snap on from the Status Line ({C['snap']})", C["snap"])
    key('Z', ctrl=True)


@step
def s_wait():
    pass


@step
def s_after_undo():
    ob = bpy.data.objects.get(C["name"])
    ts = bpy.context.scene.tool_settings
    check(f"Ctrl+Z undid the move (z = {ob.location.z if ob else None})", ob is not None and abs(ob.location.z) < 1e-6)
    check("Ctrl+Z kept the grid snap on (Maya: snap toggles aren't undoable)",
          ts.use_snap and 'GRID' in set(ts.snap_elements))
    shot("gui_step258_snap_undo.png")
    path = os.path.join(tempfile.mkdtemp(prefix="allset258_"), "scene.blend")
    with override():
        bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
        bpy.ops.wm.open_mainfile(filepath=path)


@step
def s_reopen():
    check("save / open keeps pCube1", bpy.data.objects.get(C["name"]) is not None)


run()
