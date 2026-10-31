"""Maya Hypershade swatch MMB drag in a real UI. pCube1 in the Maya layout (main viewport split in two so
the Hypershade window, opened over the largest area, leaves one 3D View visible) + a new blinn1 (no user) ->
Hypershade -> MMB press on blinn1's swatch in the Browser (Hypershade window) -> moves out of the Hypershade window
over the cube in the main window's other 3D View -> release = pCube1 gets blinn1 (one slot); a drag of phong1 to
empty space assigns nothing; ESC cancels; LMB click on a swatch still picks it (Graph / Property Editor)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402
from sim import MODULE, check, run, setup, step, win, load_maya_layout, view3d  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def again(fn, cond, limit=60):
    C.setdefault(fn.__name__, 0)
    if not cond() and C[fn.__name__] < limit:
        C[fn.__name__] += 1
        sim._steps.insert(0, fn)
        redraw()
        return True
    return False


def hs_window():
    hs = mod(".ui.hypershade")
    for w in bpy.context.window_manager.windows[1:]:
        panes = {hs.pane(a): a for a in w.screen.areas if hs.pane(a)}
        if 'BROWSER' in panes and hs.graph_area(w.screen) is not None:
            return w, panes['BROWSER']
    return None, None


def browser():
    w, area = hs_window()
    return w, area, next(r for r in area.regions if r.type == 'WINDOW')


def hs_ev(type, value, x, y, **kw):
    """An event in the Hypershade window (window coordinates; may lie outside it)."""
    w = C["w"]
    if value == 'PRESS':
        sim._down.add(type)
    elif value == 'RELEASE':
        sim._down.discard(type)
    w.event_simulate(type=type, value=value, x=int(x), y=int(y), **kw)


def command_under_mouse():
    w, area, region = browser()
    wm = bpy.context.window_manager
    wm.clipboard = ""
    try:
        with bpy.context.temp_override(window=w, screen=w.screen, area=area, region=region):
            bpy.ops.ui.copy_data_path_button(full_path=True)
    except RuntimeError:
        pass
    return wm.clipboard


def win32_client(window_count):
    """Client rects (left, top, right, bottom; screen px, y down) of this process's top-level windows (Win32,
    test-only reading of the Window.x / y convention) + the primary screen height."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    user32 = ctypes.windll.user32
    pid = os.getpid()
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _l):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(r))
            pt = wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            if r.right > 200 and r.bottom > 200:
                out.append((pt.x, pt.y, pt.x + r.right, pt.y + r.bottom))
        return True
    user32.EnumWindows(each, 0)
    return out, user32.GetSystemMetrics(1)


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_split():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.screen.area_split(direction='VERTICAL', factor=0.3)


@step
def s_scene():
    m = mod(".operators.material")
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    cube = bpy.context.active_object
    C["cube"] = cube.name
    C["cube_mat0"] = cube.active_material.name if cube.active_material else None
    for kind in ('BLINN', 'PHONG'):
        mat = m.new_material(kind)
        mat.use_fake_user = True
        C[kind] = mat.name
    bpy.context.window_manager.allset_hs_swatch = 'SMALL'   # the swatch names fit the Browser of a small window
    # the Python calls above push no undo step: push one, so undoing the drop goes back to this scene
    bpy.ops.ed.undo_push(message="test scene")
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.hypershade()


@step
def s_ready():
    if again(s_ready, lambda: hs_window()[0] is not None and len(hs_window()[0].screen.areas) >= 6):
        return
    w, _area = hs_window()
    check("Hypershade window open", w is not None)
    C["w"] = w
    print("windows", [(x.x, x.y, x.width, x.height) for x in bpy.context.window_manager.windows])
    meas = win32_client(len(bpy.context.window_manager.windows))
    if meas:
        rects, screen_h = meas
        print("win32 client rects (y down)", rects, "screen height", screen_h)
        # Window.x / y bottom-left origin: left = x, top (y down) = screen_h - (y + height)
        want = sorted((x.x, screen_h - x.y - x.height) for x in bpy.context.window_manager.windows)
        got = sorted((r[0], r[1]) for r in rects)
        print("Window.x/y as y-down top-left", want, "win32", got)
        C["win32"] = (want, got)
    redraw()


@step
def s_wait():
    redraw()


@step
def s_wait_shot():
    shot("gui_step162_hs_open.png", C["w"])
    w, area, region = browser()
    print("browser region", region.x, region.y, region.width, region.height, "area", area.x, area.y, area.width,
          area.height)


def find_swatch(name, key):
    """Sweep down the first grid column of the Browser for the name button of ``name`` (one probe per tick)."""
    state = {}

    def look():
        w, area, region = browser()
        if not state:
            wm = bpy.context.window_manager
            s = bpy.context.preferences.system.ui_scale
            size = next(z for z in mod(".ui.hypershade").SWATCHES if z[0] == wm.allset_hs_swatch)
            cell = size[3] * 20 * s + 12
            names = sorted(m.name for m in bpy.data.materials)
            cols = min(len(names), max(1, min(24, int(region.width // cell))))   # grid_flow: no empty columns
            index = names.index(name)
            state["x"] = region.x + int(region.width / cols * (index % cols + 0.5))
            state["y"] = region.y + region.height - 4
            state["n"] = 0
            C[key] = None
        else:
            got = command_under_mouse()
            if os.environ.get("ALLSET_GUI_FIND_DEBUG"):
                print("FIND", name, state["x"], state["y"], repr(got))
            if got.endswith(f'materials["{name}"].allset_hs_pick'):
                state.setdefault("first", state["y"])
                state["last"] = state["y"]
            elif "first" in state:
                C[key] = (state["x"], (state["first"] + state["last"]) // 2)
                return
            state["y"] -= 6
            if state["y"] < region.y + 2:
                if "first" in state:
                    C[key] = (state["x"], (state["first"] + state["last"]) // 2)
                return
        w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=state["x"], y=state["y"])
        sim._steps.insert(0, look)
    return look


@step
def s_find():
    sim._steps.insert(0, find_swatch(C["BLINN"], "blinn_btn"))


@step
def s_icon_probe():
    """Measure: is the swatch icon (template_icon, above the name button) a hoverable button?"""
    btn = C.get("blinn_btn")
    check(f"blinn swatch name button found in the Browser ({btn})", btn is not None)
    if btn is None:
        sim._steps.clear()
        return
    s = bpy.context.preferences.system.ui_scale
    C["icon_pt"] = (btn[0], btn[1] + int(30 * s))
    C["w"].event_simulate(type='MOUSEMOVE', value='NOTHING', x=C["icon_pt"][0], y=C["icon_pt"][1])


@step
def s_icon_probe2():
    print("icon probe: command under the swatch icon =", repr(command_under_mouse()))


def target_point(name):
    """(x, y) in Hypershade-window coordinates of ``name``'s centre in a main-window 3D View not covered by the
    Hypershade window (screen rects), plus that view's area."""
    from bpy_extras import view3d_utils
    toolbox = mod(".ui.toolbox")
    main, hw = win(), C["w"]
    ob = bpy.data.objects[name]
    for area in main.screen.areas:
        if area.type != 'VIEW_3D' or toolbox.is_toolbox(area.spaces.active):
            continue
        region = next(r for r in area.regions if r.type == 'WINDOW')
        p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, ob.matrix_world.translation)
        if p is None:
            continue
        sx, sy = main.x + region.x + p.x, main.y + region.y + p.y
        inside_hs = hw.x <= sx < hw.x + hw.width and hw.y <= sy < hw.y + hw.height
        print("view", area.as_pointer(), "cube at screen", (sx, sy), "under hypershade", inside_hs)
        if not inside_hs and 0 <= p.x < region.width and 0 <= p.y < region.height:
            return (sx - hw.x, sy - hw.y), area, region
    return None, None, None


@step
def s_press():
    btn = C["blinn_btn"]
    hs_ev('MOUSEMOVE', 'NOTHING', *btn)
    C["pt"], C["varea"], C["vregion"] = target_point(C["cube"])
    check(f"a main-window 3D View shows {C['cube']} outside the Hypershade window ({C['pt']})", C["pt"] is not None)
    if C["pt"] is None:
        sim._steps.clear()


@step
def s_press2():
    hs_ev('MIDDLEMOUSE', 'PRESS', *C["blinn_btn"])


@step
def s_moving():
    drag = mod(".ui.hs_drag")
    check(f"MMB press on the blinn1 swatch starts the drag ({drag.DRAG})", drag.DRAG["material"] == C["BLINN"])
    a, b = C["blinn_btn"], C["pt"]
    C["path"] = [(a[0] + (b[0] - a[0]) * t / 4, a[1] + (b[1] - a[1]) * t / 4) for t in (1, 2, 3, 4)]


@step
def s_move():
    if C["path"]:
        hs_ev('MOUSEMOVE', 'NOTHING', *C["path"].pop(0))
        sim._steps.insert(0, s_move)
        redraw()


@step
def s_over():
    redraw()


@step
def s_shot_drag():
    drag = mod(".ui.hs_drag")
    print("drag point", drag.DRAG)
    shot("gui_step162_hs_drag_over.png", win())
    shot("gui_step162_hs_drag_hs.png", C["w"])


@step
def s_release():
    hs_ev('MIDDLEMOUSE', 'RELEASE', *C["pt"])


@step
def s_check_drop():
    cube = bpy.data.objects[C["cube"]]
    mats = [s.material.name if s.material else None for s in cube.material_slots]
    check(f"release over {C['cube']} assigns {C['BLINN']} to the whole object ({mats}, was {C['cube_mat0']})",
          mats == [C["BLINN"]])
    check("drag ended", mod(".ui.hs_drag").DRAG["material"] == "")
    redraw()


@step
def s_undo():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.ed.undo()
    cube = bpy.data.objects[C["cube"]]
    C["undone"] = [s.material.name if s.material else None for s in cube.material_slots]
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.ed.redo()
    cube = bpy.data.objects[C["cube"]]
    redone = [s.material.name if s.material else None for s in cube.material_slots]
    check(f"the drop is one undo step (undo {C['undone']}, redo {redone})",
          C["undone"] == [C["cube_mat0"]] and redone == [C["BLINN"]])


@step
def s_shot_after():
    shot("gui_step162_hs_drag_done.png", win())


@step
def s_find_phong():
    sim._steps.insert(0, find_swatch(C["PHONG"], "phong_btn"))


@step
def s_empty_press():
    btn = C.get("phong_btn")
    check(f"phong swatch found ({btn})", btn is not None)
    if btn is None:
        sim._steps.clear()
        return
    hs_ev('MIDDLEMOUSE', 'PRESS', *btn)


@step
def s_empty_move():
    # empty space: the corner of the same view (the grid floor is not an object)
    region, hw, main = C["vregion"], C["w"], win()
    C["empty"] = (main.x + region.x + 30 - hw.x, main.y + region.y + region.height - 30 - hw.y)
    hs_ev('MOUSEMOVE', 'NOTHING', *C["empty"])


@step
def s_empty_release():
    hs_ev('MIDDLEMOUSE', 'RELEASE', *C["empty"])


@step
def s_empty_check():
    phong = bpy.data.materials[C["PHONG"]]
    cube = bpy.data.objects[C["cube"]]
    users = [o.name for o in bpy.data.objects if any(s.material == phong for s in o.material_slots)]
    check(f"a drop on empty space assigns nothing (phong users {users}, cube {cube.active_material.name})",
          not users and cube.active_material.name == C["BLINN"])
    check("drag ended after the empty drop", mod(".ui.hs_drag").DRAG["material"] == "")


@step
def s_esc_press():
    hs_ev('MIDDLEMOUSE', 'PRESS', *C["phong_btn"])


@step
def s_esc_move():
    hs_ev('MOUSEMOVE', 'NOTHING', *C["pt"])


@step
def s_esc():
    hs_ev('ESC', 'PRESS', *C["pt"])
    hs_ev('ESC', 'RELEASE', *C["pt"])


@step
def s_esc_release():
    hs_ev('MIDDLEMOUSE', 'RELEASE', *C["pt"])


@step
def s_esc_check():
    cube = bpy.data.objects[C["cube"]]
    check(f"ESC cancels the drag: the release over the cube assigns nothing ({cube.active_material.name})",
          cube.active_material.name == C["BLINN"])


@step
def s_click():
    hs_ev('MOUSEMOVE', 'NOTHING', *C["phong_btn"])


@step
def s_click2():
    hs_ev('LEFTMOUSE', 'PRESS', *C["phong_btn"])


@step
def s_click3():
    hs_ev('LEFTMOUSE', 'RELEASE', *C["phong_btn"])


@step
def s_click_check():
    wm = bpy.context.window_manager
    check(f"LMB click on a swatch still picks it ({wm.allset_hs_material})", wm.allset_hs_material == C["PHONG"])
    if "win32" in C:
        want, got = C["win32"]
        check(f"Window.x / y = screen position, bottom-left origin (Blender {want}, Win32 {got})",
              all(any(abs(a[0] - b[0]) <= 1 and abs(a[1] - b[1]) <= 1 for b in got) for a in want))


@step
def s_close():
    wm = bpy.context.window_manager
    while len(wm.windows) > 1:
        w = wm.windows[-1]
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()


run()
