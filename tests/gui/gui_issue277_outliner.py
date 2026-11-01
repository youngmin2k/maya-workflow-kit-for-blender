"""#277: the Tool Box Outliner button is Maya's Outliner toggle. In the Maya Workflow Kit layout (Outliner docked
right of the Tool Box column) a click hides that Outliner, the next click docks it back there; no second Outliner and
no new window."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, find_button, run, screenshot, setup, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    path = os.path.join(SHOTS or os.path.join(os.environ.get("TEMP", "."), "gui277"), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    screenshot(path)
    return path


def tb():
    return import_module(MODULE + ".ui.toolbox")


def column():
    area = next(a for a in win().screen.areas if a.type == 'VIEW_3D' and tb().is_toolbox(a.spaces.active))
    return area, next(r for r in area.regions if r.type == 'TOOLS')


def state():
    wm = bpy.context.window_manager
    outl = [a for w in wm.windows for a in w.screen.areas if a.type == 'OUTLINER']
    from_main = [a for a in win().screen.areas if a.type == 'OUTLINER']
    col, _r = column()
    view = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return {"windows": len(wm.windows), "outliners": len(outl), "docked": len(from_main),
            "column_w": col.width, "view_w": view.width,
            "next_to_column": [a.x - (col.x + col.width) for a in from_main]}


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_before():
    C["s0"] = state()
    print("GUI INFO before", C["s0"], flush=True)
    check(f"the Maya layout has one docked Outliner ({C['s0']})", C["s0"]["docked"] == 1 and C["s0"]["windows"] == 1)
    redraw()


step(find_button(column, lambda path, cmd: "toggle_outliner" in (cmd or ""), C, "btn", step_px=6, x_frac=0.5,
                 start_frac=0.3))


def click_steps(tag):
    @step
    def hover():
        pos = C.get("btn")
        if tag == "hide":
            check(f"the Tool Box has the Outliner toggle button ({pos})", pos is not None)
        if pos:
            ev('MOUSEMOVE', 'NOTHING', x=pos[0], y=pos[1])

    @step
    def press():
        if C.get("btn"):
            ev('LEFTMOUSE', 'PRESS')
            ev('LEFTMOUSE', 'RELEASE')

    @step
    def settle():
        redraw()

    @step
    def settle2():
        redraw()


click_steps("hide")


@step
def s_hidden():
    s = state()
    C["s1"] = s
    print("GUI INFO hidden", s, flush=True)
    shot("gui_issue277_outliner_hidden.png")
    check(f"#277-5: the Outliner button hides the docked Outliner, no new window ({s})",
          s["outliners"] == 0 and s["windows"] == 1)
    check(f"#277-5: the Tool Box column keeps its width ({C['s0']['column_w']} -> {s['column_w']})",
          abs(s["column_w"] - C["s0"]["column_w"]) <= 2)
    check(f"#277-5: the viewport takes the Outliner's room ({C['s0']['view_w']} -> {s['view_w']})",
          s["view_w"] > C["s0"]["view_w"])
    ev('MOUSEMOVE', 'NOTHING', x=C["btn"][0], y=C["btn"][1] + 3)


click_steps("show")


@step
def s_shown():
    s = state()
    print("GUI INFO shown", s, flush=True)
    shot("gui_issue277_outliner_shown.png")
    check(f"#277-5: the next click docks one Outliner back, no new window ({s})",
          s["outliners"] == 1 and s["docked"] == 1 and s["windows"] == 1)
    check(f"#277-5: it sits right of the Tool Box column ({s['next_to_column']})",
          s["next_to_column"] and abs(s["next_to_column"][0]) <= tb().GAP_PX)
    scale = bpy.context.preferences.system.ui_scale
    w = next(a.width for a in win().screen.areas if a.type == 'OUTLINER')
    check(f"#277-5: at the layout's Outliner width ({w} px, {tb().OUTLINER_PX} x {scale})",
          abs(w - tb().OUTLINER_PX * scale) <= 12)
    check(f"#277-5: the Tool Box column keeps its width ({C['s0']['column_w']} -> {s['column_w']})",
          abs(s["column_w"] - C["s0"]["column_w"]) <= 2)


run()
