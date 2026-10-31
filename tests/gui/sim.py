"""Helpers for GUI event-simulation tests (run inside Blender by tests/gui/run.py).

Blender must run with ``--enable-event-simulate``: real input is ignored and
``Window.event_simulate`` feeds events. Gotchas:
- key events carry a position (default 0,0 = status bar), so ``ev`` reuses
  the last mouse position;
- the factory-startup splash popup eats events until ESC;
- simulated keys never reach the OS, so the add-on's ``keystate.is_down``
  (missed-RELEASE fallback) is replaced by the simulated key state.
"""

import json
import os
import sys
from importlib import import_module

import addon_utils
import bpy

MODULE = os.environ.get("ALLSET_MODULE", "bl_ext.user_default.allset")
RESULT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else None

UI_SCALE = float(os.environ.get("ALLSET_GUI_UI_SCALE", "0") or 0)

# Enabling the add-on turns Blender's region overlap off ("Solid Side Panels"), but region rects only
# follow at the next screen refresh: positions a test computes in its setup tick would still be the overlapping
# ones. Start the session without overlap so the layout is final from the first step (a test of the preference
# itself sets ALLSET_GUI_KEEP_OVERLAP=1 before importing this module).
if os.environ.get("ALLSET_GUI_KEEP_OVERLAP") != "1":
    bpy.context.preferences.system.use_region_overlap = False

_pos = [0, 0]
_down = set()
_steps = []
results = []


def win():
    return bpy.context.window_manager.windows[0]


def view3d():
    # the largest: the Maya Workflow Kit layout also has the narrow Tool Box 3D View
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return area, region


def dock_area(kind=None):
    """Maya's tab stack (Channel Box / Layer Editor | Attribute Editor | Modeling Toolkit) of the main window: its
    own area right of the viewport (ui/maya_dock.py), made here when the screen has none (a factory
    screen). Its role is set from a timer: give it one step before drawing. ``kind`` selects the tab."""
    md = import_module(MODULE + ".ui.maya_dock")
    area = md.find_stack(win().screen)
    if area is None:
        with bpy.context.temp_override(window=win()):
            area = md.open_stack(bpy.context, win())
    if kind is not None:
        bpy.context.window_manager.allset_dock = kind
    return area


def dock_region(kind=None):
    """The WINDOW region of ``dock_area`` (where the Channel Box / AE / MTK draw; was the 3D View sidebar)."""
    return next(r for r in dock_area(kind).regions if r.type == 'WINDOW')


def dock_tab_point(kind):
    """Window point (x, y) in the middle of ``kind``'s tab on the stack's vertical tab strip (drawn on the
    right edge, ui/maya_dock.strip_tabs), or None when the strip has no such tab."""
    md = import_module(MODULE + ".ui.maya_dock")
    region = dock_region()
    s = bpy.context.preferences.system.ui_scale
    for k, x0, y0, x1, y1 in md.strip_tabs(md.stack_tabs(), region.width, region.height, s):
        if k == kind:
            return region.x + round((x0 + x1) / 2), region.y + round((y0 + y1) / 2)
    return None


def button_under_mouse(area, region):
    """(data path, Python command) of the button under the mouse in ``region`` ("" when none / not that kind)."""
    wm = bpy.context.window_manager
    out = []
    for op, kw in ((bpy.ops.ui.copy_data_path_button, {"full_path": False}), (bpy.ops.ui.copy_python_command_button, {})):
        wm.clipboard = ""
        try:
            with bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region):
                op(**kw)
        except RuntimeError:
            pass
        out.append(wm.clipboard)
    return tuple(out)


def find_button(where, match, store, key, step_px=10, rows=(None,), x_frac=None, y_from=None, start_frac=0.0):
    """A step that sweeps the mouse (one probe per tick) until ``match(data_path, command)`` holds for the button
    under it; ``store[key]`` = (x, y) or None. ``where()`` returns (area, region). Default: right to left along
    ``rows`` (y offsets below the region's top in px; None = middle). ``x_frac``: top to bottom along that fraction
    of the region's width instead (from ``start_frac`` of its height down). ``y_from``: a key of ``store`` whose y is the row to sweep (found before).
    Pixel offsets of buttons moved when the dock left the 3D View sidebar: tests look buttons up by what
    they are."""
    state = {}

    def start(region):
        if x_frac is not None:
            state["x"] = region.x + int(region.width * x_frac)
            state["y"] = region.y + region.height - 4 - int(region.height * start_frac)
            state["rows"] = [None]
            return
        if y_from is not None:
            found = store.get(y_from)
            state["rows"] = [found[1]] if found else []
        else:
            state["rows"] = [region.y + (region.height // 2 if r is None else region.height - r) for r in rows]
        state["x"] = region.x + region.width - 4
        state["y"] = state["rows"][0] if state["rows"] else None

    def look():
        area, region = where()
        if not state:
            start(region)
            store[key] = None
            if state["y"] is None:
                return
        else:
            found = button_under_mouse(area, region)
            hit = match(*found)
            if os.environ.get("ALLSET_GUI_FIND_DEBUG"):
                print("FIND", key, state["x"], state["y"], found)
            if hit or "first" in state:
                # go on through the button and keep its centre (a click on a field's edge doesn't edit it)
                axis = "y" if x_frac is not None else "x"
                if hit:
                    state.setdefault("first", state[axis])
                    state["last"] = state[axis]
                else:
                    mid = (state["first"] + state["last"]) // 2
                    store[key] = (state["x"], mid) if axis == "y" else (mid, state["y"])
                    return
            if x_frac is not None:
                state["y"] -= step_px
                if state["y"] < region.y + 2:
                    return
            else:
                state["x"] -= step_px
                if state["x"] < region.x + 2 and "first" in state:
                    # the button reaches the region's left edge (Channel Box names): keep its centre
                    store[key] = ((state["first"] + state["last"]) // 2, state["y"])
                    return
                if state["x"] < region.x + 2:
                    state["rows"].pop(0)
                    if not state["rows"]:
                        return
                    state["x"] = region.x + region.width - 4
                    state["y"] = state["rows"][0]
        ev('MOUSEMOVE', 'NOTHING', x=state["x"], y=state["y"])
        _steps.insert(0, look)
    return look


def ev(type, value, **kw):
    if value == 'PRESS':
        _down.add(type)
    elif value == 'RELEASE':
        _down.discard(type)
    if "x" in kw:
        _pos[:] = [kw["x"], kw["y"]]
    else:
        kw.update(x=_pos[0], y=_pos[1])
    win().event_simulate(type=type, value=value, **kw)


def tap(type):
    ev(type, 'PRESS')
    ev(type, 'RELEASE')


def check(name, cond):
    results.append({"name": name, "ok": bool(cond)})
    print("GUI", "PASS" if cond else "FAIL", name, flush=True)


def screenshot(path):
    with bpy.context.temp_override(window=win()):
        bpy.ops.screen.screenshot(filepath=path)


def step(fn):
    _steps.append(fn)
    return fn


@bpy.app.handlers.persistent
def _keep_ui_scale(*_args):
    # Loading a template with --factory-startup reloads factory preferences (ui_scale 1.0).
    if UI_SCALE and bpy.context.preferences.view.ui_scale != UI_SCALE:
        bpy.context.preferences.view.ui_scale = UI_SCALE


if UI_SCALE:
    bpy.app.handlers.load_post.append(_keep_ui_scale)
    _keep_ui_scale()


def scale():
    """Effective UI scale (OS scale x Resolution Scale): pixel sizes taken at 1.25 scale with it."""
    return bpy.context.preferences.system.ui_scale


# Pixel offsets in the tests were read from screenshots at effective scale 1.25 (125 % display,
# Resolution Scale 1.0); px() converts one to the running scale (e.g. --ui-scale 0.8).
MEASURED_SCALE = 1.25


def px(v):
    return round(v * scale() / MEASURED_SCALE)


def setup():
    """Close the splash, enable the add-on, fake key state, park the mouse mid-viewport."""
    tap('ESC')
    _keep_ui_scale()
    addon_utils.enable(MODULE, default_set=True)
    # opt in to Maya mode (enabling alone changes nothing)
    import_module(MODULE + ".switch").set_mode(True, layout=False)
    import_module(MODULE + ".operators.keystate").is_down = lambda t: t in _down
    _area, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    return r.x + r.width // 2, r.y + r.height // 2


def load_maya_layout():
    """A new scene in the Maya layout (the startup.blend bundled in the extension read as an untitled file;
    no app template, the preferences stay)."""
    import_module(MODULE + ".first_start").new_maya_scene()


def _finish():
    if RESULT:
        with open(RESULT, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=1)
    bpy.ops.wm.quit_blender()


def run(interval=0.4, first=2.0):
    """Run registered steps one per timer tick, then write results and quit."""
    def tick():
        if _steps:
            try:
                _steps.pop(0)()
            except Exception as ex:  # report and stop
                import traceback
                traceback.print_exc()
                check(f"step raised {ex!r}", False)
                _steps.clear()
            return interval
        _finish()
        return None
    # persistent: survive wm.read_homefile (loading the app template)
    bpy.app.timers.register(tick, first_interval=first, persistent=True)


def maya_keys():
    """Maya keymap on (add-on keymap items, the active keyconfig stays Blender's)."""
    kc = bpy.context.window_manager.keyconfigs.active
    return import_module(MODULE + ".keymap").is_applied() and kc is not None and kc.name == "Blender"


def maya_kc():
    """The Maya keymap view tests read (tests/kit.py ``maya_kc``)."""
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import kit
    return kit.maya_kc()


def open_inputs(*history):
    """Expand the lead's Channel Box INPUTS nodes (Maya shows them collapsed until the node name is clicked):
    every modifier and constraint node, plus the kit history nodes named in ``history`` (polyCube1, polyExtrudeFace1)."""
    cb = import_module(MODULE + ".ui.channel_box")
    ob = cb.lead(bpy.context)
    if ob is None:
        return
    keys = [cb.mod_node(m) for m in getattr(ob, "modifiers", ())]
    keys += [cb.con_node(ob, c) for c in getattr(ob, "constraints", ())]
    keys += [cb.history_node(name) for name in history]
    for key in keys:
        cb.set_open(ob, key)
    cb.rebuild_rows()


def scroll_channel_box(first=10 ** 6):
    """Scroll the dock's Channel Box part to line ``first`` (default: the end, where the INPUTS nodes are).
    a long Channel Box scrolls inside its part; the wheel itself is tested in gui_step135_dock. The draw clamps it."""
    cb = import_module(MODULE + ".ui.channel_box")
    area = dock_area()
    cb._scroll[area.as_pointer()] = first
    area.tag_redraw()
