"""In a real UI:
- #6: drag down over the Channel Box names Translate X -> Scale Z selects that range (blue name cells); a drag that
  starts on a value field selects too; then one value typed into a selected field goes into every selected channel
  of both selected cubes.
- #7: the Layer Editor with three display layers (Maya-like rows: V / P / type boxes, swatch, name) for a look at the
  dock.
Screenshots with ALLSET_GUI_SHOTS (or --shots)."""

import math
import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, dock_region, ev, find_button, run, screenshot, setup, step, tap, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
GUI_TIMEOUT = 240


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def dock():
    return dock_area(), dock_region()


def cb():
    return import_module(MODULE + ".ui.channel_box")


def cubes():
    return bpy.data.objects["Cube"], bpy.data.objects["Cube2"]


@step
def s_setup():
    setup()
    a = bpy.data.objects["Cube"]
    b = a.copy()
    b.name = "Cube2"
    bpy.context.scene.collection.objects.link(b)
    a.location.x, b.location.x = 1.0, 4.0
    for o in bpy.context.view_layer.objects:
        o.select_set(o in (a, b))
    bpy.context.view_layer.objects.active = a
    cb().set_selected_channels([])
    dock_area('CHANNEL_BOX')
    redraw()


@step
def s_wait():
    redraw()


# fields: a sweep down the right part of the dock; names: along each field's row (the dock width
# follows the UI scale, so the name column is no longer at a fixed fraction of it)
step(find_button(dock, lambda p, _c: p.endswith("allset_cb.tx_text"), C, "tx_field", x_frac=0.7, step_px=4))
step(find_button(dock, lambda p, _c: p.endswith("allset_cb.rz_text"), C, "rz_field", x_frac=0.7, step_px=4))
step(find_button(dock, lambda p, _c: p.endswith("allset_cb.ty_text"), C, "ty_field", x_frac=0.7, step_px=4))
step(find_button(dock, lambda p, _c: p.endswith("allset_cb.sz_text"), C, "sz_field", x_frac=0.7, step_px=4))
step(find_button(dock, lambda p, _c: p.endswith("allset_cb.tx_sel"), C, "tx_name", y_from="tx_field", step_px=8))
step(find_button(dock, lambda p, _c: p.endswith("allset_cb.sz_sel"), C, "sz_name", y_from="sz_field", step_px=8))


@step
def s_found():
    found = {k: C.get(k) for k in ("tx_name", "sz_name", "tx_field", "rz_field", "ty_field")}
    check(f"Channel Box name cells and value fields found ({found})", all(found.values()))
    if not all(found.values()):
        raise RuntimeError("cells not found")
    x, y = C["tx_name"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_hover_name():
    x, y = C["tx_name"]
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


@step
def s_press_name():
    x, y = C["tx_name"]
    ev('LEFTMOUSE', 'PRESS', x=x + 1, y=y)


def _drag_steps(key_from, key_to, tag, n=8):
    for i in range(1, n + 1):
        def move(i=i):
            x0, y0 = C[key_from]
            x1, y1 = C[key_to]
            ev('MOUSEMOVE', 'NOTHING', x=x0 + 1, y=round(y0 + (y1 - y0) * i / n))
        move.__name__ = f"s_drag_{tag}_{i}"
        step(move)


_drag_steps("tx_name", "sz_name", "names")


@step
def s_release_name():
    ev('LEFTMOUSE', 'RELEASE')
    redraw()


@step
def s_names_selected():
    sel = cb().selected_channels()
    check(f"drag over the names Translate X -> Scale Z selects the range ({sel})",
          sel == ["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"])
    shot("gui_step129_cb_names_drag.png")


@step
def s_click_one_name():
    x, y = C["sz_name"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_click_one_name2():
    x, y = C["sz_name"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_one_selected():
    sel = cb().selected_channels()
    check(f"a click on a name selects only that channel ({sel})", sel == ["sz"])
    x, y = C["tx_field"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_hover_field():
    x, y = C["tx_field"]
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


@step
def s_press_field():
    x, y = C["tx_field"]
    ev('LEFTMOUSE', 'PRESS', x=x + 1, y=y)


_drag_steps("tx_field", "rz_field", "fields", n=6)


@step
def s_release_field():
    ev('LEFTMOUSE', 'RELEASE')
    redraw()


@step
def s_fields_selected():
    sel = cb().selected_channels()
    check(f"drag over the value fields Translate X -> Rotate Z selects the range ({sel})",
          sel == ["tx", "ty", "tz", "rx", "ry", "rz"])
    a, b = cubes()
    check(f"the drag changed no value (Cube x {a.location.x:.4f}, Cube2 x {b.location.x:.4f})",
          abs(a.location.x - 1.0) < 1e-6 and abs(b.location.x - 4.0) < 1e-6)
    shot("gui_step129_cb_fields_drag.png")
    x, y = C["ty_field"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_click_selected_field():
    x, y = C["ty_field"]
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


@step
def s_click_selected_field2():
    x, y = C["ty_field"]
    ev('LEFTMOUSE', 'PRESS', x=x + 1, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x + 1, y=y)


@step
def s_type():
    ev('A', 'PRESS', ctrl=True)
    ev('A', 'RELEASE', ctrl=True)
    for ch in "2":
        ev('TEXTINPUT', 'PRESS', unicode=ch)
    redraw()


@step
def s_enter():
    shot("gui_step129_cb_typing.png")
    tap('RET')


@step
def s_applied():
    a, b = cubes()
    sel = cb().selected_channels()
    check(f"the selection stays after typing ({sel})", sel == ["tx", "ty", "tz", "rx", "ry", "rz"])
    for ob in (a, b):
        loc = tuple(round(v, 4) for v in ob.location)
        rot = tuple(round(math.degrees(v), 3) for v in ob.rotation_euler)
        check(f"{ob.name}: one typed value 2 went into Translate X/Y/Z ({loc}) and Rotate X/Y/Z ({rot})",
              loc == (2.0, 2.0, 2.0) and rot == (2.0, 2.0, 2.0))
        check(f"{ob.name}: unselected Scale stays 1 ({tuple(ob.scale)})", tuple(ob.scale) == (1.0, 1.0, 1.0))
    redraw()


@step
def s_layers():
    le = import_module(MODULE + ".ui.layer_editor")
    sc = bpy.context.scene
    a, b = cubes()
    le.new_layer(sc, [a, b])
    l2 = le.new_layer(sc, [])
    l2.allset_layer.display_type = "TEMPLATE"
    l3 = le.new_layer(sc, [])
    l3.allset_layer.visible = False
    l3.allset_layer.playback = False
    l3.allset_layer.display_type = "REFERENCE"
    sc.allset_layer_index = le.layers(sc).index(l3)
    redraw()


@step
def s_layers_wait():
    redraw()


@step
def s_layers_shot():
    shot("gui_step129_layer_editor.png")
    le = import_module(MODULE + ".ui.layer_editor")
    names = [c.name for c in le.display_order(bpy.context.scene)]
    check(f"Layer Editor lists the newest layer on top ({names})", names == ["layer3", "layer2", "layer1"])


run()
