"""Lane WIDTH (#60) in a real UI: a new Maya scene fits the Maya tab stack to the running UI scale
(toolbox.dock_width: Channel Box labels left of the vertical tab strip; between 277 and 480 px
times the scale) through
ALLSET_OT_fit_columns, the viewport takes the remaining width, the AE menu bar is one row, the longest Channel Box
label fits its column. Run at the default 1.25, ``--ui-scale 0.8`` (1.0) and ``--ui-scale 1.2`` (1.5)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
os.environ["ALLSET_FIT_WARP"] = "1"   # the cursor fit is off in event-simulated sessions unless asked for
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def shot(name):
    if SHOTS:
        scale = round(bpy.context.preferences.system.ui_scale * 100)
        screenshot(os.path.join(SHOTS, f"{name}_{scale}.png"))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


class _Ctx:
    def __init__(self, region):
        self.region = region
        self.preferences = bpy.context.preferences


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_keymap():
    bpy.ops.allset.keymap_activate()
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)   # over a region: area_move can't poll
    redraw()


for _i in range(10):         # the fit timer (0.5 s) + ALLSET_OT_fit_columns ticks (shelf, dock, column, Outliner)
    step(redraw)


@step
def s_width():
    tb = mod("ui.toolbox")
    prefs = bpy.context.preferences
    scale, pixel = prefs.system.ui_scale, prefs.system.pixel_size
    dock = dock_area()
    want = tb.dock_width(scale, pixel)
    main, _r = view3d()
    C.update(dock=dock.width, want=want, view=main.width)
    check(f"the Maya tab stack fits UI scale {scale:.2f} ({dock.width} px, want {want}; Maya "
          f"{round(tb.DOCK_MAYA_PX * scale)}..{round(tb.DOCK_MAX_PX * scale)})", abs(dock.width - want) <= 3)
    check(f"the viewport takes the rest: its right edge meets the dock ({main.x + main.width} / {dock.x})",
          abs(main.x + main.width - dock.x) <= 8 and main.width >= round(tb.MIN_VIEW_PX * scale))
    outl = max((a for a in win().screen.areas if a.type == 'OUTLINER'), key=lambda a: a.height)
    check(f"the viewport starts at the Outliner ({outl.x + outl.width} / {main.x})", abs(outl.x + outl.width - main.x) <= 8)
    check(f"the Outliner keeps its fitted width ({outl.width}, want {round(260 * scale)})",
          abs(outl.width - round(260 * scale)) <= 2)
    reg = next(r for r in dock.regions if r.type == 'WINDOW')
    u = tb._unit(scale, pixel)
    longest = max(tb.text_px(t, scale) for t in tb.LONG_LABELS)
    content = reg.width - mod("ui.maya_dock").reserved_px(scale)   # left of the vertical tab strip
    check(f"the longest Channel Box label fits its half of the dock ({longest:.0f} px in {(content - 0.8 * u) / 2:.0f})",
          (content - 0.8 * u) / 2 >= longest + 0.8 * u)
    # #78: the tabs are Maya's vertical strip, the AE gets its own width when raised (gui_step142_ui.py)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + 40)
    redraw()


@step
def s_cb_shot():
    shot("s135_channel_box")
    bpy.context.window_manager.allset_dock = 'ATTRIBUTE_EDITOR'
    redraw()


for _i in range(6):         # raising the AE widens the stack (tab change -> cursor fit)
    step(redraw)


@step
def s_ae_shot():
    shot("s135_attribute_editor")
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'
    redraw()


for _i in range(6):         # ... and the Channel Box narrows it again
    step(redraw)


@step
def s_stays():
    dock = dock_area()
    check(f"the fitted dock stays put once fitted ({dock.width} px)", abs(dock.width - C["want"]) <= 3)


run()
