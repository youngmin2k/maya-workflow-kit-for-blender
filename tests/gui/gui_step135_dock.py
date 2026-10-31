"""Lane CB (#55) in a real UI: new scene in the Maya layout, a kit cube selected -> the dock's Layer Editor
(Display / Anim tabs) is on screen at Maya's split, Channel Box INPUTS shows polyCube1 collapsed; a click on the name
expands it (Width ... rows) and the Layer Editor stays where it was; a second click collapses it. A long history
(six expanded bevel nodes) scrolls inside the Channel Box part (wheel) and the Layer Editor still stays.
Run at the default scale and with --ui-scale 0.8 / 1.2; shots with ALLSET_GUI_SHOTS (or --shots)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, ev, find_button, run, screenshot, setup, step, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
os.environ["ALLSET_FIT_WARP"] = "1"   # the dock / column fit as on a user's screen
C = {}
GUI_TIMEOUT = 480


def mod(name):
    return import_module(f"{MODULE}.{name}")


def cb():
    return mod("ui.channel_box")


def shot(name):
    if SHOTS:
        scale = round(bpy.context.preferences.system.ui_scale * 100)
        screenshot(os.path.join(SHOTS, f"{name}_{scale}.png"))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def dock():
    area = dock_area()
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def cube():
    return bpy.data.objects.get("pCube1")


def node_key():
    ob = cube()
    return cb().history_node(mod("operators.prim_history").node_of(ob)[1]["name"])


def le_tab(p, _c):
    return p.endswith("allset_le_tab")


def toggle_btn(_p, c):
    return "cb_node_toggle" in c and "polyCube" in c


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_keymap():
    bpy.ops.allset.keymap_activate()
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    redraw()


for _i in range(8):          # the column / dock fit ticks
    step(redraw)


@step
def s_cube():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    ob = bpy.context.view_layer.objects.active
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'
    redraw()


@step
def s_wait():
    redraw()


step(find_button(dock, le_tab, C, "le_tab", x_frac=0.15, step_px=5))


@step
def s_scroll_to_inputs():
    """A short dock (1600x900 at 1.25 / 1.5) scrolls the Channel Box part to show INPUTS — wheel it down like a user;
    the wheel passes through when nothing overflows."""
    area, region = dock()
    x = region.x + region.width // 2
    y = region.y + region.height - int(region.height * 0.25)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    C["inputs_wheel"] = (x, y)
    redraw()


def _wheel_once():
    x, y = C["inputs_wheel"]
    ev('WHEELDOWNMOUSE', 'PRESS', x=x, y=y)    # one per tick: wheel events queued in one tick count once
    redraw()


for _i in range(5):
    step(_wheel_once)


@step
def s_wait_scroll():
    redraw()


step(find_button(dock, toggle_btn, C, "node", x_frac=0.15, step_px=5))


@step
def s_collapsed():
    area, region = dock()
    ob = cube()
    check(f"a kit cube pCube1 is the lead ({ob and ob.name})", ob is not None and cb().lead() == ob)
    le = C.get("le_tab")
    top = region.y + region.height
    check(f"Layer Editor Display / Anim tabs on screen with a cube selected ({le}, dock y {region.y}..{top})",
          le is not None and region.y < le[1] < top)
    if le is not None:
        share = (top - le[1]) / region.height
        check(f"Layer Editor tabs at Maya's split (from the dock top: {share:.2f} of {region.height} px; Maya 0.48)",
              0.40 <= share <= 0.65)
    check(f"INPUTS polyCube1 node row present ({C.get('node')})", C.get("node") is not None)
    check("polyCube1 starts collapsed (Maya cb135/d01_cube.png)", not cb().is_open(ob, node_key()))
    check("no polyCube1 attribute rows while collapsed", "Width" not in labels_now())
    shot("s135_cube_collapsed")
    if C.get("node"):
        ev('MOUSEMOVE', 'NOTHING', x=C["node"][0], y=C["node"][1])


def labels_now():
    """Labels (and attribute name toggles) the Channel Box would draw now (a recorder pass of the same body)."""
    class Rec:
        def __init__(self, log):
            self.log = log

        def __getattr__(self, name):
            if name in ("row", "column", "split", "box"):
                return lambda *a, **k: Rec(self.log)
            if name == "label":
                return lambda *a, **k: self.log.append(k.get("text", ""))
            if name == "prop":      # selectable attribute names are toggles labelled with the Maya name
                return lambda *a, **k: (self.log.append(k["text"]) if k.get("toggle") and "text" in k else None,
                                        type("P", (), {})())[1]
            return lambda *a, **k: type("P", (), {})()

        def __setattr__(self, name, value):
            if name == "log":
                object.__setattr__(self, name, value)
    log = []
    cb().ALLSET_PT_channel_box.body(Rec(log), bpy.context)
    return log


@step
def s_click_expand():
    if C.get("node"):
        x, y = C["node"]
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_click_expand_release():
    if C.get("node"):
        x, y = C["node"]
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    redraw()


@step
def s_wait2():
    redraw()


step(find_button(dock, le_tab, C, "le_tab2", x_frac=0.15, step_px=5))


@step
def s_expanded():
    ob = cube()
    check("a click on polyCube1 expands it", cb().is_open(ob, node_key()))
    check(f"its attributes show (labels {labels_now()[-6:]})", "Width" in labels_now())
    a, b = C.get("le_tab"), C.get("le_tab2")
    check(f"the Layer Editor stays where it was ({a} -> {b})", a is not None and b is not None and abs(a[1] - b[1]) <= 3)
    shot("s135_cube_expanded")
    if C.get("node"):
        ev('MOUSEMOVE', 'NOTHING', x=C["node"][0] + 1, y=C["node"][1])


for _i in range(12):         # past the double-click time: a second PRESS this soon is a DOUBLE_CLICK
    step(redraw)


@step
def s_click_collapse():
    if C.get("node"):
        x, y = C["node"]
        ev('LEFTMOUSE', 'PRESS', x=x + 1, y=y)


@step
def s_click_collapse_release():
    if C.get("node"):
        x, y = C["node"]
        ev('LEFTMOUSE', 'RELEASE', x=x + 1, y=y)
    redraw()


@step
def s_collapsed_again():
    check("a second click collapses polyCube1", not cb().is_open(cube(), node_key()))
    # a long history: six bevel nodes, all expanded -> more lines than the Channel Box part holds
    ob = cube()
    for i in range(6):
        m = ob.modifiers.new(f"polyBevel{i + 1}", 'BEVEL')
        cb().set_open(ob, cb().mod_node(m))
    cb().rebuild_rows()
    redraw()


@step
def s_wait3():
    redraw()


step(find_button(dock, le_tab, C, "le_tab3", x_frac=0.15, step_px=5))


@step
def s_long():
    area, region = dock()
    last = cb()._last.get(area.as_pointer())
    check(f"a long Channel Box overflows its part and scrolls ({last})", last is not None and last[2] is not None)
    a, b = C.get("le_tab"), C.get("le_tab3")
    check(f"the Layer Editor still stays ({a} -> {b})", a is not None and b is not None and abs(a[1] - b[1]) <= 3)
    shot("s135_long_history")
    x = region.x + region.width // 2
    y = region.y + region.height - int(region.height * 0.25)    # over the Channel Box part
    C["wheel"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_wheel():
    x, y = C["wheel"]
    for _i in range(3):
        ev('WHEELDOWNMOUSE', 'PRESS', x=x, y=y)
    redraw()


@step
def s_wheel_check():
    area, _region = dock()
    first = cb()._scroll.get(area.as_pointer(), 0)
    check(f"the mouse wheel over the Channel Box part scrolls it ({first} lines)", first > 0)
    shot("s135_long_scrolled")


run()
