"""Channel Box middle drag (#273) in the Maya Workflow Kit layout: a click on Translate X makes a middle drag in the
viewport change it; after E (Rotate Tool) the channel stays highlighted but the middle drag is the tool's own and
Translate X stays put; a new click on the channel gives the middle drag back; Ctrl+click on the channel, a click on
the empty space under the channels and deselecting everything in the viewport deselect it, like Maya."""

import math
import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import (MODULE, check, dock_area, dock_region, ev, find_button, load_maya_layout, run, screenshot,  # noqa: E402
                 setup, step, tap, view3d, win)

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
GUI_TIMEOUT = 300


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def cb():
    return import_module(MODULE + ".ui.channel_box")


def cube():
    return bpy.data.objects[C["cube"]]


def dock():
    return dock_area(), dock_region()


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def view_point(fx=0.3, fy=0.3):
    _area, region = view3d()
    return region.x + int(region.width * fx), region.y + int(region.height * fy)


def wait(tag, n=3):
    for i in range(n):
        def w():
            redraw()
        w.__name__ = f"s_{tag}_wait{i}"
        step(w)


def key_in_view(tag, key):
    def hover():
        x, y = view_point(0.5, 0.5)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    hover.__name__ = f"s_{tag}_hover"
    step(hover)

    def press():
        tap(key)
    press.__name__ = f"s_{tag}_key"
    step(press)
    wait(tag, 2)


def click(tag, where, **mods):
    def hover():
        x, y = where()
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    hover.__name__ = f"s_{tag}_hover"
    step(hover)

    def press():
        x, y = where()
        ev('LEFTMOUSE', 'PRESS', x=x, y=y, **mods)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y, **mods)
    press.__name__ = f"s_{tag}_click"
    step(press)
    wait(tag, 12)      # a second press soon after on the same spot would be a double click


def mmb_drag(tag, dx=100, moves=6, dy=0):
    def hover():
        C["tx_before"] = cube().location.x
        x, y = view_point()
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    hover.__name__ = f"s_{tag}_hover"
    step(hover)

    def press():
        x, y = view_point()
        ev('MIDDLEMOUSE', 'PRESS', x=x, y=y)
    press.__name__ = f"s_{tag}_press"
    step(press)
    for i in range(1, moves + 1):
        def move(i=i):
            x, y = view_point()
            ev('MOUSEMOVE', 'NOTHING', x=x + round(dx * i / moves), y=y + round(dy * i / moves))
        move.__name__ = f"s_{tag}_move{i}"
        step(move)

    def release():
        ev('MIDDLEMOUSE', 'RELEASE')
    release.__name__ = f"s_{tag}_release"
    step(release)
    wait(tag, 2)


def tx_moved():
    return abs(cube().location.x - C["tx_before"]) > 1e-4


def name_point():
    return C["tx_name"]


def empty_point():
    """Under the last channel row, above the Layer Editor: the Channel Box part's empty space."""
    area, region = dock()
    u = cb()._unit(bpy.context)
    used = cb()._filled[area.as_pointer()]
    share = cb().cb_share(region, u) * region.height
    top = region.y + region.height
    y = top - round((used * u + share) / 2)
    return region.x + region.width // 3, y


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
    ob = bpy.context.view_layer.objects.active
    C["cube"] = ob.name
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    cb().set_selected_channels([])
    dock_area('CHANNEL_BOX')
    redraw()


wait("scene", 3)
key_in_view("w", 'W')
step(find_button(dock, lambda p, _c: p.endswith("allset_cb.tx_text"), C, "tx_field", x_frac=0.7, step_px=4))
step(find_button(dock, lambda p, _c: p.endswith("allset_cb.tx_sel"), C, "tx_name", y_from="tx_field", step_px=8))


@step
def s_found():
    tool = bpy.context.workspace.tools.from_space_view3d_mode('OBJECT', create=False)
    check(f"W picked the Move Tool ({tool.idname if tool else None})", tool is not None and tool.idname == "builtin.move")
    check(f"Translate X name cell found ({C.get('tx_name')})", C.get("tx_name"))
    if not C.get("tx_name"):
        raise RuntimeError("name cell not found")


click("pick", name_point)


@step
def s_picked():
    check(f"a click on Translate X selects it ({cb().selected_channels()})", cb().selected_channels() == ["tx"])


mmb_drag("slider")


@step
def s_slider():
    check(f"a middle drag in the viewport changes Translate X ({C['tx_before']:.4f} -> {cube().location.x:.4f})",
          tx_moved())
    C["loc"] = tuple(cube().location)
    # the drag follows Translate X as drawn in this view: a straight-up move changes it by the move projected on
    # the X axis on screen (like dragging the Move manipulator's X arrow)
    _area, region = view3d()
    origin, direction = cb().node_axes(cube(), "tx")
    axis = cb().screen_axis(region, region.data, origin, direction)
    C["want_up"] = cb().projected_delta((axis.x, axis.y), 0, 60)
    C["tx_axis"] = (round(axis.x, 1), round(axis.y, 1))


mmb_drag("vertical", dx=0, dy=60)


@step
def s_vertical():
    got = cube().location.x - C["tx_before"]
    check(f"a straight-up middle drag moves Translate X along its axis on screen ({got:.4f}, want "
          f"{C['want_up']:.4f}, axis {C['tx_axis']} px per unit)",
          abs(C["want_up"]) > 1e-3 and abs(got - C["want_up"]) < 0.02 * abs(C["want_up"]) + 1e-4)
    cube().location = C["loc"]
    C["rx_before"] = cube().rotation_euler.x
    cb().set_selected_channels(["rx"])


mmb_drag("rotate", dx=50)


@step
def s_rotate():
    got = math.degrees(cube().rotation_euler.x - C["rx_before"])
    check(f"a selected Rotate X turns 0.36 degrees per px to the right ({got:.2f} for 50 px)", abs(got - 18.0) < 0.5)
    cube().rotation_euler.x = C["rx_before"]
    cb().set_selected_channels(["tx"])


key_in_view("e", 'E')


@step
def s_rotate_tool():
    tool = bpy.context.workspace.tools.from_space_view3d_mode('OBJECT', create=False)
    check(f"E picked the Rotate Tool ({tool.idname if tool else None})", tool is not None and tool.idname == "builtin.rotate")
    check(f"the channel stays highlighted after E ({cb().selected_channels()})", cb().selected_channels() == ["tx"])
    C["rot"] = tuple(cube().rotation_euler)


mmb_drag("after_e")


@step
def s_after_e():
    check(f"after E a middle drag leaves Translate X alone ({C['tx_before']:.4f} -> {cube().location.x:.4f})",
          not tx_moved())
    shot("gui_issue273_after_e.png")


click("repick", name_point)
mmb_drag("repicked")


@step
def s_repicked():
    check(f"picking the channel again gives the middle drag back ({C['tx_before']:.4f} -> {cube().location.x:.4f})",
          tx_moved())


click("ctrl", name_point, ctrl=True)


@step
def s_ctrl():
    check(f"Ctrl+click on the selected channel deselects it ({cb().selected_channels()})",
          cb().selected_channels() == [])


click("pick2", name_point)


@step
def s_pick2():
    check(f"picked again ({cb().selected_channels()})", cb().selected_channels() == ["tx"])
    C["empty"] = empty_point()


click("empty", lambda: C["empty"])


@step
def s_empty():
    check(f"a click on the empty space under the channels deselects them ({cb().selected_channels()}, at {C['empty']})",
          cb().selected_channels() == [])


click("pick3", name_point)
key_in_view("q", 'Q')
click("view_empty", lambda: view_point(0.08, 0.08))


@step
def s_view_empty():
    check(f"a click on empty viewport space deselects the object ({[o.name for o in bpy.context.selected_objects]})",
          not bpy.context.selected_objects)
    check(f"... and the channels ({cb().selected_channels()})", cb().selected_channels() == [])


run()
