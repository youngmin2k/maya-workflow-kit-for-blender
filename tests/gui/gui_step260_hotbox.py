"""Issue #174: the Space hotbox.

1. A click on each hotbox menu name (press and release in separate ticks, mouse not moved) opens that menu and runs no
   menu row. Before: Blender opened the popup on the PRESS with a row under the pointer and the RELEASE ran it (18 of 40
   names ran an item, Edit > Cut deleted the cube).
2. A held Space whose auto-repeat arrives as RELEASE + PRESS pairs (X11 without detectable repeat, remote input) keeps
   the hotbox up and toggles no pane. Before: 5-14 Four View toggles for 20 pairs.
3. A quick tap still toggles the pane once.
Screenshot: gui_step260_menu_open.png (the Edit menu opened by a click on its name, nothing run)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402
from sim import MODULE, check, ev, run, screenshot, setup, step, view3d  # noqa: E402

GUI_TIMEOUT = 300
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"taps": 0}
RAN = []


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def active():
    return dict(C["draw"].ACTIVE)


def wait(n):
    for _ in range(n):
        step(lambda: None)


def label_point(name):
    hb = C["draw"].ACTIVE.get("hotbox")
    _a, r = view3d()
    rect = next(rc for rc, key, label in hb.labels if label == name)
    return r.x + int((rect[0] + rect[2]) / 2), r.y + int((rect[1] + rect[3]) / 2)


@step
def s_setup():
    C["x"], C["y"] = setup()
    C["draw"] = import_module(MODULE + ".marking.draw")
    C["modal"] = import_module(MODULE + ".marking.modal")
    orig = C["modal"].pane_tap

    def counting(context):
        C["taps"] += 1
        return orig(context)
    C["modal"].pane_tap = counting
    ms = import_module(MODULE + ".ui.menu_sets")
    cls = ms.ALLSET_OT_menu_item
    orig_exec = cls.execute

    def execute(self, context):
        RAN.append(self.item)
        return orig_exec(self, context)
    cls.execute = execute
    C["names"] = None
    C["bad"] = []


def click_name(idx):
    @step
    def a():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        if not any(o.type == 'MESH' for o in bpy.context.scene.objects):
            bpy.ops.mesh.primitive_cube_add()
        for o in bpy.context.scene.objects:
            o.select_set(o.type == 'MESH')
        ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
        ev('SPACE', 'PRESS')

    wait(2)

    @step
    def b():
        hb = C["draw"].ACTIVE.get("hotbox")
        C["skip"] = hb is None
        if hb is None:
            C["bad"].append((idx, "no hotbox"))
            return
        names = [label for rc, key, label in hb.labels]
        C["names"] = names
        C["skip"] = idx >= len(names)
        if C["skip"]:
            return
        C["name"] = names[idx]
        C["xy"] = label_point(C["name"])
        ev('MOUSEMOVE', 'NOTHING', x=C["xy"][0], y=C["xy"][1])

    wait(1)

    @step
    def c():
        if not C["skip"]:
            del RAN[:]
            C["nobj"] = len(bpy.data.objects)
            ev('LEFTMOUSE', 'PRESS', x=C["xy"][0], y=C["xy"][1])

    wait(3)

    @step
    def d():
        if not C["skip"]:
            ev('LEFTMOUSE', 'RELEASE', x=C["xy"][0], y=C["xy"][1])

    wait(4)

    @step
    def e():
        if not C["skip"]:
            if C["name"] == "Edit":
                shot("gui_step260_menu_open.png")
            if RAN or len(bpy.data.objects) != C["nobj"]:
                C["bad"].append((C["name"], list(RAN), C["nobj"], len(bpy.data.objects)))
        sim.tap('ESC')
        sim.tap('ESC')
        ev('SPACE', 'RELEASE')

    wait(4)


for _k in range(52):
    click_name(_k)


@step
def s_clicks_done():
    n = len(C["names"] or [])
    check(f"a click on each of the {n} hotbox menu names runs no menu row ({C['bad'][:4]})", n >= 30 and not C["bad"])


# --- auto-repeat as RELEASE + PRESS pairs while Space is held ---
@step
def s2_press():
    C["t0"] = C["taps"]
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('SPACE', 'PRESS')


wait(2)
for _i in range(20):
    @step
    def s2_pair():
        ev('SPACE', 'RELEASE')
        ev('SPACE', 'PRESS')


@step
def s2_mid():
    C["up"] = "hotbox" in active()
    ev('SPACE', 'RELEASE')


wait(8)


@step
def s2_done():
    n = C["taps"] - C["t0"]
    check(f"held Space with 20 release/press repeat pairs: hotbox stays up ({C['up']}), pane toggles {n}",
          C["up"] and n == 0)


# --- #174 on Windows 11: Windows auto-repeat = raw-input key-downs only, no release (GHOST_SystemWin32.cc
# processKeyEvent :1334-1341 flags them is_repeat by the thread key state; event_simulate can't set the flag, the modal
# handles a PRESS the same either way). Space held 2 s (0.5 s delay, then a repeat each 50 ms tick), OS state down ---
@step
def s4_press():
    C["t0"] = C["taps"]
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('SPACE', 'PRESS')


wait(10)        # Windows' default repeat delay
for _i in range(30):
    @step
    def s4_repeat():
        ev('SPACE', 'PRESS')


@step
def s4_mid():
    C["up"] = "hotbox" in active()
    shot("gui_step267_hotbox_held.png")
    ev('SPACE', 'RELEASE')


wait(8)


@step
def s4_done():
    n = C["taps"] - C["t0"]
    check(f"held Space with Windows-style press-only repeats for 2 s: hotbox stays up ({C['up']}), pane toggles {n}",
          C["up"] and n == 0)


# --- a quick tap still toggles the pane ---
@step
def s3_press():
    C["t0"] = C["taps"]
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    ev('SPACE', 'PRESS')


@step
def s3_release():
    ev('SPACE', 'RELEASE')


wait(8)


@step
def s3_done():
    n = C["taps"] - C["t0"]
    check(f"a quick Space tap toggles the pane once ({n})", n == 1)


run(interval=0.05, first=2.0)
