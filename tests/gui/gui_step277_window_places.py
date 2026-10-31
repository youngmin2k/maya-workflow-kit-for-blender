"""Step 277 (#203) in a real UI: Render Settings reopens at the size and place it had; a place off the screen comes
back inside the Blender window; the main layout is the same afterwards. Screenshot: gui_step277_main.png (main
window after the reopen, layout unchanged)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
TOL = 4


def mod(name):
    return import_module(f"{MODULE}.{name}")


def layout():
    return sorted((a.type, a.x, a.y, a.width, a.height) for a in win().screen.areas)


def rs_windows():
    return [w for w in bpy.context.window_manager.windows if w != win()]


def close_others():
    for w in list(bpy.context.window_manager.windows):
        if w != win():
            with bpy.context.temp_override(window=w):
                bpy.ops.wm.window_close()


@step
def s_setup():
    setup()
    load_maya_layout()


for _i in range(8):       # the layout settles (the kit fits its columns once after loading)
    step(lambda: None)


@step
def s_open_at_place():
    main = win()
    C["layout"] = layout()
    wp = mod("ui.window_places")
    wp.remember("render_settings", (main.x + 300, main.y + 200, 640, 480))
    # the window can only open over the largest area of the main window: the place is fitted into it
    area = max(main.screen.areas, key=lambda a: a.width * a.height)
    x, y, w, h = wp.target_in_window("render_settings", main, area)
    C["want"] = (main.x + x, main.y + y, w, h)
    C["before"] = set(bpy.context.window_manager.windows[:])
    open_rs()


def open_rs():
    main = win()
    area = max(main.screen.areas, key=lambda a: a.width * a.height)
    with bpy.context.temp_override(window=main, area=area):
        bpy.ops.allset.render_settings()


def new_window():
    return next((w for w in bpy.context.window_manager.windows if w not in C["before"]), None)


for _i in range(6):       # the place is carved one split per tick, then the window opens
    step(lambda: None)


@step
def s_check_place():
    w = new_window()
    check("Render Settings opened", w is not None)
    got = (w.x, w.y, w.width, w.height)
    want = C["want"]
    print("STEP277 want", want, "got", got, "main", (win().x, win().y, win().width, win().height), flush=True)
    check(f"reopened at the remembered size {got[2:]} (want {want[2:]})",
          abs(got[2] - want[2]) <= TOL and abs(got[3] - want[3]) <= TOL)
    check(f"reopened at the remembered place {got[:2]} (want {want[:2]})",
          abs(got[0] - want[0]) <= TOL and abs(got[1] - want[1]) <= TOL)
    print("STEP277 layout before", C["layout"], flush=True)
    print("STEP277 layout after ", layout(), flush=True)
    check(f"main layout as before ({len(layout())} areas)", layout() == C["layout"])
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step277_main.png"))


@step
def s_close():
    close_others()


@step
def s_saved():
    wp = mod("ui.window_places")
    wp._tick()
    p = wp.path()
    import json
    data = json.load(open(p, encoding="utf-8")) if p and os.path.isfile(p) else {}
    got = data.get("render_settings")
    check(f"closed window's place is saved ({got})", got is not None and abs(got[2] - 640) <= TOL)
    # a place on a monitor that isn't there any more
    wp.remember("render_settings", (win().x - 5000, win().y + 100, 500, 400))
    C["before"] = set(bpy.context.window_manager.windows[:])
    open_rs()


for _i in range(6):
    step(lambda: None)


@step
def s_check_offscreen():
    w, m = new_window(), win()
    inside = m.x <= w.x and w.x + w.width <= m.x + m.width and m.y <= w.y and w.y + w.height <= m.y + m.height
    check(f"an off-screen place comes back inside the Blender window ({w.x}, {w.y}, {w.width}, {w.height})",
          inside and abs(w.width - 500) <= TOL)
    check("main layout as before", layout() == C["layout"])
    close_others()


run()
