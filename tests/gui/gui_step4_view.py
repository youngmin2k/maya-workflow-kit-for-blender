"""With simulated events: dolly direction, ortho tumble lock, view undo,
Space tap four views, Shift+A all views, 1/2/3, F9-F11, Ctrl+Space."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, tap, setup, screenshot, view3d, win  # noqa: E402
from importlib import import_module  # noqa: E402

four_view = import_module(MODULE + ".ui.four_view")   # four real panels

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def rv3d():
    return view3d()[0].spaces.active.region_3d


def drag(button, dx, dy=0, alt=False, then=None):
    """Press, move in two steps, release (one call per tick via the caller)."""
    x, y = C["x"], C["y"]
    ev(button, 'PRESS', x=x, y=y, alt=alt)
    ev('MOUSEMOVE', 'NOTHING', x=x + dx // 2, y=y + dy // 2, alt=alt)
    ev('MOUSEMOVE', 'NOTHING', x=x + dx, y=y + dy, alt=alt)
    ev(button, 'RELEASE', x=x + dx, y=y + dy, alt=alt)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_setup():
    C["x"], C["y"] = setup()
    C["dist"] = rv3d().view_distance
    drag('RIGHTMOUSE', 120, alt=True)  # Alt+RMB drag right


@step
def s_dolly():
    d = rv3d().view_distance
    check(f"Alt+RMB drag right dollies in ({C['dist']:.2f} -> {d:.2f})", d < C["dist"])
    C["dist"] = d
    drag('RIGHTMOUSE', -120, alt=True)


@step
def s_dolly_out():
    check("Alt+RMB drag left dollies out", rv3d().view_distance > C["dist"])
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.view3d.view_axis(type='FRONT')
    C["rot"] = None


@step
def s_wait_axis():
    pass  # smooth view


@step
def s_ortho():
    r = rv3d()
    check("front view is ortho side view", r.view_perspective == 'ORTHO' and r.is_orthographic_side_view)
    C["rot"] = tuple(r.view_rotation)
    drag('LEFTMOUSE', 150, 40, alt=True)


@step
def s_ortho_locked():
    check("Alt+LMB in front ortho view: tumble locked", tuple(rv3d().view_rotation) == C["rot"])
    rv3d().view_perspective = 'PERSP'
    drag('LEFTMOUSE', 150, 40, alt=True)


@step
def s_persp_tumbles():
    check("Alt+LMB in perspective: tumbles", tuple(rv3d().view_rotation) != C["rot"])


@step
def s_settle():
    C["A"] = rv3d().view_distance, tuple(rv3d().view_location)


@step
def s_settle2():
    drag('MIDDLEMOUSE', 200, 60, alt=True)  # Alt+MMB track


@step
def s_track_wait():
    pass


@step
def s_track_wait2():
    C["B"] = rv3d().view_distance, tuple(rv3d().view_location)
    check("Alt+MMB track moved the view", C["B"][1] != C["A"][1])
    tap('LEFT_BRACKET')


@step
def s_undo_view():
    now = rv3d().view_distance, tuple(rv3d().view_location)
    check("[ -> previous view", all(abs(a - b) < 1e-3 for a, b in zip(now[1], C["A"][1])))
    tap('RIGHT_BRACKET')


@step
def s_redo_view():
    now = rv3d().view_distance, tuple(rv3d().view_location)
    check("] -> view again", all(abs(a - b) < 1e-3 for a, b in zip(now[1], C["B"][1])))
    tap('SPACE')


@step
def s_quad_wait():
    pass                      # the top row splits one tick later


@step
def s_quad_on():
    screen = win().screen
    check("Space tap -> four views", four_view.is_four(screen))
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step4_quad.png"))
    # Hover the top-left panel (Maya: top) and tap again.
    tl = four_view.roles(screen)["top"]
    rv = tl.spaces.active.region_3d
    C["hover_persp"] = rv.view_perspective
    C["hover_rot"] = tuple(round(v, 4) for v in rv.view_rotation)
    reg = next(r for r in tl.regions if r.type == 'WINDOW')
    ev('MOUSEMOVE', 'NOTHING', x=reg.x + reg.width // 2, y=reg.y + reg.height // 2)
    tap('SPACE')


@step
def s_quad_off():
    space = view3d()[0].spaces.active
    r = space.region_3d
    check("Space tap in a panel -> single view", len(four_view.panes(win().screen)) == 1)
    check("single view keeps the hovered panel's view",
          r.view_perspective == C["hover_persp"]
          and tuple(round(v, 4) for v in r.view_rotation) == C["hover_rot"])
    _a, reg = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])
    r.view_perspective = 'PERSP'
    r.view_distance = 200.0


@step
def s_settle_layout():
    # alone 1 of 3 runs failed (non-deterministic) — after the layout change the window needs a tick of
    # its own with the pointer in the view before a key reaches the new area under event simulation
    ev('MOUSEMOVE', 'NOTHING', x=C["x"], y=C["y"])


@step
def s_shift_a():
    # after a layout change the first key sent in the move's tick is lost under event simulation
    ev('A', 'PRESS', shift=True)
    ev('A', 'RELEASE', shift=True)


@step
def s_wait_frame():
    pass


@step
def s_wait_frame2():
    pass


@step
def s_frame_all():
    check("Shift+A frames all", rv3d().view_distance < 200.0)
    cube = bpy.data.objects["Cube"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o == cube)
    bpy.context.view_layer.objects.active = cube
    tap('THREE')


@step
def s_three():
    mods = [m for m in bpy.data.objects["Cube"].modifiers if m.type == 'SUBSURF']
    check("3 -> smooth preview subsurf on", len(mods) == 1 and mods[0].show_viewport)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step4_smooth.png"))
    tap('ONE')


@step
def s_one():
    mods = [m for m in bpy.data.objects["Cube"].modifiers if m.type == 'SUBSURF']
    check("1 -> smooth preview off", len(mods) == 1 and not mods[0].show_viewport)
    tap('F10')


@step
def s_f10():
    ts = bpy.context.scene.tool_settings
    check("F10 -> edit mode, edge", bpy.context.mode == 'EDIT_MESH'
          and tuple(ts.mesh_select_mode) == (False, True, False))
    tap('F9')


@step
def s_f9():
    ts = bpy.context.scene.tool_settings
    check("F9 -> vertex", tuple(ts.mesh_select_mode) == (True, False, False))
    tap('F8')


@step
def s_f8():
    check("F8 -> object mode", bpy.context.mode == 'OBJECT')
    ev('SPACE', 'PRESS', ctrl=True)
    ev('SPACE', 'RELEASE', ctrl=True)


@step
def s_full():
    check("Ctrl+Space -> full screen (UI hidden)", win().screen.show_fullscreen)
    ev('SPACE', 'PRESS', ctrl=True)
    ev('SPACE', 'RELEASE', ctrl=True)


@step
def s_full_back():
    check("Ctrl+Space again -> back", not win().screen.show_fullscreen)


run()
