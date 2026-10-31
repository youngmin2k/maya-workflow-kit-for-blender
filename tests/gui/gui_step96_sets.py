"""In a real UI: Maya object sets in the Maya Workflow Kit layout's Outliner.

Three cubes, two selected -> Create > Sets > Set (the Maya menu item) -> a `set1` row under the DAG rows of
Blender's Outliner (kit overlay, ui/outliner_sets.py) -> click = the members are selected, Ctrl+click toggles,
the triangle shows the members, a member row click selects that object, RMB opens the set menu, and the
Outliner's own rows still work (Blender's click selects pCube3)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win, tap, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def outl():
    a = max((a for a in win().screen.areas if a.type == 'OUTLINER'), key=lambda a: a.height)
    return a, next(r for r in a.regions if r.type == 'WINDOW')


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def selected():
    return {o.name for o in bpy.context.selected_objects}


def rows():
    """The kit set rows (Maya's startup camera / set rows are drawn before them)."""
    _a, r = outl()
    return [x for x in mod("ui.outliner_sets").REGIONS.get(r.as_pointer(), []) if x[2] in ('SET', 'MEMBER')]


def point(row, x_units):
    """Window point at ``x_units`` row units from the region's left, in the middle of ``row``."""
    _a, r = outl()
    u = mod("ui.outliner_sets").unit(bpy.context.preferences)
    return r.x + int(x_units * u), r.y + int((row[0] + row[1]) / 2)


def click(p, **mods):
    """LMB press + release (= CLICK) at ``p``; ``mods`` e.g. ctrl=True ride on the mouse events."""
    ev('MOUSEMOVE', 'NOTHING', x=p[0], y=p[1])
    ev('LEFTMOUSE', 'PRESS', x=p[0], y=p[1], **mods)
    ev('LEFTMOUSE', 'RELEASE', x=p[0], y=p[1], **mods)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cubes():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        for _ in range(3):
            bpy.ops.allset.create(kind='CUBE')
    for o in bpy.context.scene.objects:
        o.select_set(o.name in {"pCube1", "pCube2"})
    bpy.context.view_layer.objects.active = bpy.data.objects["pCube2"]
    with bpy.context.temp_override(window=win(), area=area, region=region):
        check("Create > Sets > Set through the Maya menu item",
              bpy.ops.allset.menu_item(item="Create/Sets/Set") == {'FINISHED'})
    s = mod("operators.sets").get("set1")
    check(f"set1 holds pCube1 pCube2, selection kept ({selected()})",
          s is not None and {o.name for o in s.objects} == {"pCube1", "pCube2"} and selected() == {"pCube1", "pCube2"})
    redraw()


@step
def s_row_drawn():
    r = rows()
    _a, region = outl()
    u = mod("ui.outliner_sets").unit(bpy.context.preferences)
    # the default Maya rows (4 cameras, defaultLightSet, defaultObjectSet) come between
    top3 = region.view2d.view_to_region(0, -9 * u, clip=False)[1]
    check(f"Outliner draws one set row right under the three DAG rows and the six default rows ({[(x[0], x[1], x[2], x[3]) for x in r]}, "
          f"row 3 top {top3})", len(r) == 1 and r[0][2] == 'SET' and r[0][3] == "set1" and abs(r[0][1] - top3) <= 1)
    shot("gui_step96_outliner_set.png")
    for o in bpy.context.scene.objects:
        o.select_set(False)
    redraw()


@step
def s_click_set():
    C["row"] = rows()[0]
    click(point(C["row"], 4.0))


@step
def s_click_set_done():
    check(f"click on set1 selects its members ({selected()})", selected() == {"pCube1", "pCube2"})
    for o in bpy.context.scene.objects:
        o.select_set(o.name == "pCube1")
    click(point(C["row"], 4.0), ctrl=True)


@step
def s_ctrl_done():
    check(f"Ctrl+click toggles the members ({selected()})", selected() == {"pCube2"})
    _a, r = outl()
    lead = 1.0 if _a.spaces.active.show_mode_column else 0.0   # the Maya Outliner has no mode column
    click(point(C["row"], lead + 0.6))   # the disclosure triangle


@step
def s_expanded():
    s = mod("operators.sets").get("set1")
    r = rows()
    check(f"triangle shows the members ({[(x[2], x[4]) for x in r]})",
          s.allset_expanded and [x[2] for x in r] == ['SET', 'MEMBER', 'MEMBER'])
    redraw()


@step
def s_member_shot():
    shot("gui_step96_outliner_members.png")
    C["member"] = next(x for x in rows() if x[2] == 'MEMBER' and x[4] == "pCube1")
    click(point(C["member"], 4.5))


@step
def s_member_done():
    check(f"click on a member row selects that object ({selected()})", selected() == {"pCube1"})
    p = point(rows()[0], 4.0)
    ev('MOUSEMOVE', 'NOTHING', x=p[0], y=p[1])
    ev('RIGHTMOUSE', 'PRESS', x=p[0], y=p[1])
    ev('RIGHTMOUSE', 'RELEASE', x=p[0], y=p[1])


@step
def s_menu_open():
    shot("gui_step96_set_menu.png")
    check(f"RMB on the set row targets set1 (menu {bpy.context.window_manager.allset_set_target!r})",
          bpy.context.window_manager.allset_set_target == "set1")
    tap('ESC')


@step
def s_blender_row():
    # Blender's own rows still get their clicks: the third DAG row (pCube3) after Maya's four startup cameras
    # (persp top front side pCube1 pCube2 pCube3)
    _a, region = outl()
    u = mod("ui.outliner_sets").unit(bpy.context.preferences)
    y = int(region.view2d.view_to_region(0, -6.5 * u, clip=False)[1])
    p = (region.x + int(4 * u), region.y + y)
    click(p)


@step
def s_blender_row_done():
    check(f"a click on a Blender row still selects that object ({selected()})", selected() == {"pCube3"})


run()
