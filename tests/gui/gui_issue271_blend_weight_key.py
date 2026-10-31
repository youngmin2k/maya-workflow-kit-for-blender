"""Issue #271 in a real UI: a mesh with a blend shape, its blendShape node expanded in the Channel Box INPUTS ->
RMB on a target weight's name selects that channel and opens the Channels menu; Key Selected (K) keys the weight on
the mesh's shape keys, and the row then shows the keyed state. Screenshots with ALLSET_GUI_SHOTS (or --shots)."""

import os
import re
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import (MODULE, check, dock_area, dock_region, ev, find_button, run, screenshot, scroll_channel_box,  # noqa: E402
                 setup, step, tap, view3d, win)

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
GUI_TIMEOUT = 240


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def dock():
    return dock_area(), dock_region()


def cb():
    return import_module(MODULE + ".ui.channel_box")


def mesh():
    return bpy.data.objects[C["mesh"]]


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def node_key():
    return cb().blend_shape_node(mesh().data.shape_keys)


@step
def s_setup():
    setup()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.view_layer.objects.active
    ob.shape_key_add(name="Basis")
    kb = ob.shape_key_add(name="smile")
    kb.data[0].co.z += 1.0
    C["mesh"] = ob.name
    bpy.context.scene.frame_set(5)
    cb().set_selected_channels([])
    dock_area('CHANNEL_BOX')


@step
def s_wait():
    # a new lead starts with every node collapsed (Maya): expand the blendShape node once the lead has settled
    cb().set_open(mesh(), node_key())
    cb().rebuild_rows()
    redraw()


@step
def s_wait2():
    scroll_channel_box()       # the expanded node's rows may sit below the Channel Box part's fixed height
    redraw()


def _is_smile(path, _c=None):
    m = re.search(r"allset_cb\.rows\[(\d+)\]\.sel$", path or "")
    rows = bpy.context.scene.allset_cb.rows
    return (m is not None and int(m.group(1)) < len(rows) and rows[int(m.group(1))].kind == "BLEND"
            and rows[int(m.group(1))].name == "smile")


step(find_button(dock, _is_smile, C, "smile", x_frac=0.25, step_px=4))


@step
def s_hover():
    shot("gui_issue271_found.png")
    check(f"the smile weight's name is a channel button ({C.get('smile')})", C.get("smile") is not None)
    if not C.get("smile"):
        raise RuntimeError("weight row not found")
    x, y = C["smile"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_hover2():
    x, y = C["smile"]
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


@step
def s_rmb():
    ev('RIGHTMOUSE', 'PRESS')
    ev('RIGHTMOUSE', 'RELEASE')


@step
def s_menu():
    shot("gui_issue271_menu.png")
    sel = cb().selected_channels()
    check(f"RMB on the weight selects its channel ({sel})", sel == ["bw:smile"])


@step
def s_pick():
    tap('K')      # Key Selected by its underlined letter (the menu may slide up)


@step
def s_picked():
    redraw()
    key = mesh().data.shape_keys
    curves = list(import_module(MODULE + ".compat").id_fcurves(key)) if key.animation_data else []
    keyed = [(fc.data_path, [round(k.co.x) for k in fc.keyframe_points]) for fc in curves]
    check(f"Channels > Key Selected keys the blendShape weight at the current frame ({keyed})",
          keyed == [('key_blocks["smile"].value', [5])])
    state = cb().channel_state(mesh(), "bw:smile")
    check(f"the weight row reads keyed ({state})", state == 'KEYED')


@step
def s_shot():
    shot("gui_issue271_keyed.png")


run()
