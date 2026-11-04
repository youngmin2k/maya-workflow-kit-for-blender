"""#305 in a real UI: in a window taller than the layout was made for, the Status Line row stays one header high
(no empty strip between the Status Line and the Shelf), also after the window is resized; the shelf row keeps its
height and its top touches the Status Line."""

import os
import sys
from importlib import import_module

import bpy

GUI_GEOMETRY = "0 0 1600 1100"   # taller than the layout's 1600 x 900

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["ALLSET_FIT_WARP"] = "1"   # let the layout fit move area edges in an event-simulated session
from sim import MODULE, check, run, scale, screenshot, setup, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
shelf = import_module(MODULE + ".ui.shelf")
toolbox = import_module(MODULE + ".ui.toolbox")


def rows():
    scr = win().screen
    return shelf.strip_area(scr), shelf.shelf_row_area(scr)


def region(area, kind):
    return next((r for r in area.regions if r.type == kind), None)


def measure(tag):
    strip, row = rows()
    hdr = region(strip, 'HEADER')
    body = region(strip, 'WINDOW')
    print(f"GUI305 {tag}: window {win().width}x{win().height} strip y={strip.y} h={strip.height} "
          f"header {hdr.height} window-region {body.height}; row y={row.y} h={row.height}", flush=True)
    return strip, row, hdr, body


def check_rows(tag):
    strip, row, hdr, body = measure(tag)
    check(f"{tag}: Status Line row is one header high (area {strip.height} px, header {hdr.height} px, "
          f"empty region {body.height} px)", strip.height - hdr.height <= 1)
    gap = strip.y - (row.y + row.height)
    # the area border: the same as between the shelf row and the area under it
    below = max((a.y + a.height for a in win().screen.areas if a.y + a.height <= row.y
                 and a.x < row.x + row.width // 2 < a.x + a.width), default=row.y)
    border = row.y - below
    check(f"{tag}: Shelf row top touches the Status Line (gap {gap} px, area border {border} px)",
          0 <= gap <= border + 1)
    want = round(toolbox.SHELF_PX * scale())
    check(f"{tag}: Shelf row keeps its height ({row.height} px, want {want})", abs(row.height - want) <= 2)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_wait1():
    pass


@step
def s_wait2():
    pass


@step
def s_wait3():
    pass


@step
def s_loaded():
    check_rows("loaded")
    shot("gui_issue305_loaded.png")
    C["size"] = (win().width, win().height)
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.window_fullscreen_toggle()


@step
def s_wait4():
    pass


@step
def s_wait5():
    pass


@step
def s_wait6():
    pass


@step
def s_wait7():
    pass


@step
def s_wait8():
    pass


@step
def s_resized():
    size = (win().width, win().height)
    print("GUI305 resized", C["size"], "->", size, flush=True)
    if size != C["size"]:
        check_rows("resized")
        shot("gui_issue305_resized.png")
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.window_fullscreen_toggle()


run(interval=0.6)
