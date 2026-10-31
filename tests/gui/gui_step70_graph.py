"""In a real UI (Maya animation workflow): a cube with two keys -> Windows >
Animation Editors > Graph Editor -> every key selected -> toolbar Linear -> LINEAR -> Shift+S hold + LMB drag east
(Tangents) and on east (Flat) -> flat tangents -> G = playback range -> Playblast option box (dialog shot) -> Playblast
-> a movie in the temp folder and Blender's player started (killed afterwards) (screenshots)."""

import os
import subprocess
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
D = 110      # px past the marking menu ring (radius 80 x UI scale)


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def run_menu(path, option=False):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return mod(".marking.modal").run_action(bpy.context, mod(".ui.menu_map").MAP[path], option)


def graph():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.ui_type == 'FCURVES':
                return w, a, next(r for r in a.regions if r.type == 'WINDOW')
    return None, None, None


def gev(type, value, x=None, y=None, **kw):
    """sim.ev for the Graph Editor window (keeps sim's simulated key state: tap_hold and the engine read it)."""
    down = sys.modules["sim"]._down
    if value == 'PRESS':
        down.add(type)
    elif value == 'RELEASE':
        down.discard(type)
    w, _a, _r = graph()
    if x is None:
        x, y = C["gpos"]
    C["gpos"] = (x, y)
    w.event_simulate(type=type, value=value, x=x, y=y, **kw)


def keys():
    return list(import_module(MODULE + ".compat").id_fcurve_collection(bpy.data.objects["Cube"])[0].keyframe_points)


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


@step
def s_setup():
    setup()
    bpy.ops.allset.keymap_activate()
    ob = bpy.data.objects["Cube"]
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 120
    for frame, x in ((1, 0.0), (24, 5.0)):
        ob.location.x = x
        ob.keyframe_insert("location", index=0, frame=frame)
    sc.frame_set(1)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    C["open"] = run_menu("Windows/Animation Editors/Graph Editor")


@step
def s_wait_graph():
    # a remembered window place (an earlier file in the same run) opens the window a few ticks later (#203: the
    # menu item returns CANCELLED and runs again once the piece is carved)
    import sim
    if graph()[1] is None and C.setdefault("waits", 0) < 20:
        C["waits"] += 1
        sim._steps.insert(0, s_wait_graph)


@step
def s_graph_open():
    w, a, r = graph()
    check(f"Windows > Animation Editors > Graph Editor: a Graph Editor window (got {C['open']}, {a is not None})",
          a is not None and (C["open"] == {'FINISHED'} or mod(".ui.window_places").deferred() or C.get("waits")))
    with bpy.context.temp_override(window=w, area=a, region=r):
        bpy.ops.graph.select_all(action='SELECT')
        bpy.ops.graph.view_all()
        # the toolbar's Linear button (operator of the header button)
        header = next(rg for rg in a.regions if rg.type == 'HEADER')
    with bpy.context.temp_override(window=w, area=a, region=header):
        C["linear"] = bpy.ops.allset.set_tangent(kind="LINEAR")
    C["gpos"] = (r.x + r.width // 2, r.y + r.height // 2)
    redraw()


@step
def s_linear():
    w, _a, _r = graph()
    interp = [kp.interpolation for kp in keys()]
    check(f"Graph Editor toolbar Linear on the selected keys -> LINEAR (got {C['linear']}, {interp})",
          interp == ['LINEAR', 'LINEAR'])
    shot("gui_step70_graph_toolbar.png", w)
    gev('MOUSEMOVE', 'NOTHING')
    gev('S', 'PRESS', shift=True)


@step
def s_mm_press():
    gev('LEFTMOUSE', 'PRESS')


@step
def s_mm_drag_tangents():
    x, y = C["gpos"]
    gev('MOUSEMOVE', 'NOTHING', x + D // 3, y)
    gev('MOUSEMOVE', 'NOTHING', x + 2 * D // 3, y)
    gev('MOUSEMOVE', 'NOTHING', x + D, y)
    C["gpos"] = (x, y)
    C["x0"] = x


@step
def s_mm_submenu():
    s = mod(".marking.draw").ACTIVE.get("session")
    check("Shift+S hold + LMB drag east: the Tangents submenu opens in place", s is not None and len(s.stack) == 2)
    x, y = C["x0"] + D, C["gpos"][1]
    gev('MOUSEMOVE', 'NOTHING', x + 50, y)
    gev('MOUSEMOVE', 'NOTHING', x + 100, y)
    w, _a, _r = graph()
    shot("gui_step70_tangent_mm.png", w)
    C["release"] = (x + 100, y)


@step
def s_mm_release():
    gev('LEFTMOUSE', 'RELEASE', *C["release"])


@step
def s_flat():
    gev('S', 'RELEASE', shift=True)
    ks = keys()
    flat = all(kp.interpolation == 'BEZIER' and kp.handle_left_type == 'ALIGNED'
               and abs(kp.handle_right.y - kp.co.y) < 1e-4 for kp in ks)
    check(f"Tangents > Flat (east, east) on the selected keys ({[(k.interpolation, k.handle_left_type) for k in ks]})",
          flat)
    x, y = C["x0"], C["gpos"][1]
    gev('MOUSEMOVE', 'NOTHING', x, y)
    gev('G', 'PRESS')
    gev('G', 'RELEASE')


@step
def s_framed():
    _w, _a, r = graph()
    lo, _ = r.view2d.region_to_view(0, 0)
    hi, _ = r.view2d.region_to_view(r.width, 0)
    check(f"G in the Graph Editor = the playback range 1-120 (view {lo:.0f} .. {hi:.0f})",
          -15 < lo < 5 and 115 < hi < 140)
    C["opt"] = run_menu("Windows/Playblast", option=True)


@step
def s_playblast_dialog():
    shot("gui_step70_playblast_options.png")
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


@step
def s_playblast():
    pb = mod(".operators.playblast")
    sc = bpy.context.scene
    sc.frame_end = 12                      # a short playblast
    before = sc.render.filepath
    C["pb"] = run_menu("Windows/Playblast")
    folder = pb.output_dir()
    movies = [f for f in os.listdir(folder)] if os.path.isdir(folder) else []
    check(f"Playblast (option box got {C['opt']}): a movie of frames 1-12 in the temp folder, render settings back "
          f"(got {C['pb']}, {movies}, {sc.render.filepath == before})",
          C["pb"] == {'FINISHED'} and any(f.lower().endswith(".mp4") for f in movies) and sc.render.filepath == before)


@step
def s_player():
    # Blender's player is a separate blender.exe -a <playblast>: found, then closed (only that process)
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'blender.exe' -and "
                          "$_.CommandLine -like '*playblast*' -and $_.CommandLine -like '* -a *' } | "
                          "ForEach-Object { $_.ProcessId }"], capture_output=True, text=True, timeout=60)
    pids = [int(p) for p in out.stdout.split() if p.strip().isdigit()]
    check(f"View on: Blender's player plays the playblast (player processes {pids})", bool(pids))
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)


run()
