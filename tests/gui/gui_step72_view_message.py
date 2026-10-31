"""In a real UI: Maya in-view messages (ui/view_message.py) on F8, Ctrl+G, Ctrl+H and b,
drawn in the 3D View they were called from, gone after the fade."""

import os
import sys
import time
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
vm = None


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def centre():
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


def message():
    cur = vm.current()
    return cur[0] if cur else ""


@step
def s_setup():
    global vm
    C["x"], C["y"] = setup()
    vm = import_module(MODULE + ".ui.view_message")
    bpy.ops.object.select_all(action='DESELECT')
    cube = bpy.data.objects["Cube"]
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    centre()
    tap('F8')


@step
def s_f8_wait():
    check(f"F8 -> edit mode ({bpy.context.mode})", bpy.context.mode == 'EDIT_MESH')
    check(f"F8 shows the component message ({message()!r})", message().startswith("Component selection"))
    _area, region = view3d()
    check("the message is drawn in the 3D View F8 was pressed in",
          vm._state["region"] == region.as_pointer() and vm._state["pos"] == 'TOP_CENTER')


@step
def s_f8_shot():
    shot("gui_step72_f8_component.png")
    centre()
    tap('F8')


@step
def s_f8_back():
    check(f"F8 again -> object mode, object message ({message()!r})",
          bpy.context.mode == 'OBJECT' and message().startswith("Object selection"))
    centre()
    ev('G', 'PRESS', ctrl=True)
    ev('G', 'RELEASE', ctrl=True)


@step
def s_group():
    check(f"Ctrl+G shows the group message ({message()!r})", "grouped" in message())
    check("the group message sits top left", vm._state["pos"] == 'TOP_LEFT')


@step
def s_group_shot():
    shot("gui_step72_group.png")
    centre()
    ev('H', 'PRESS', ctrl=True)
    ev('H', 'RELEASE', ctrl=True)


@step
def s_hide():
    check(f"Ctrl+H shows the hide message ({message()!r})", "hidden" in message() and "Shift+H" in message())


@step
def s_hide_shot():
    shot("gui_step72_hide.png")
    bpy.ops.object.select_all(action='DESELECT')
    centre()
    ev('H', 'PRESS', ctrl=True)
    ev('H', 'RELEASE', ctrl=True)


@step
def s_hide_nothing():
    check(f"Ctrl+H with nothing selected says so ({message()!r})", message().startswith("Nothing"))
    C["soft0"] = bpy.context.scene.tool_settings.use_proportional_edit_objects
    centre()
    tap('B')


@step
def s_soft_wait():
    pass


@step
def s_soft():
    on = bpy.context.scene.tool_settings.use_proportional_edit_objects
    check(f"b tap turns soft select on ({C['soft0']} -> {on})", on and not C["soft0"])
    check(f"soft select on shows its message ({message()!r})", "Soft Select" in message())


@step
def s_soft_shot():
    shot("gui_step72_soft_select.png")
    C["t"] = time.monotonic()
    centre()
    tap('B')


@step
def s_soft_off():
    check(f"b again turns it off without a new message ({message()!r})",
          not bpy.context.scene.tool_settings.use_proportional_edit_objects and "Soft Select" in message())


for _i in range(10):   # 4 s: past fade in + hold + fade out of the last message
    step(lambda: None)


@step
def s_gone():
    check(f"the message fades out ({time.monotonic() - C['t']:.1f} s)", vm.current() is None)
    shot("gui_step72_gone.png")


run()
