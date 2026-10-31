"""In a real UI: the Maya first screen.

New Maya Workflow Kit scene -> the Tool Box column shows its tools at the running UI scale (run at the default 1.25 and with
``--ui-scale 0.8``: the column is resized through ALLSET_OT_fit_columns, the main view keeps no toolbar), the
layout Outliner lists Maya's startup rows (persp / top / front / side, defaultLightSet, defaultObjectSet) from the
top, the dock shows Maya's three tabs (Channel Box / Layer Editor first) and allset_dock follows them both ways.
Then a cube and a light: the default rows follow the DAG rows, defaultLightSet selects the light, persp clears the
selection."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, dock_tab_point, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
os.environ["ALLSET_FIT_WARP"] = "1"   # the cursor fit is off in event-simulated sessions unless asked for
C = {}
CB, AE, MTK = "Channel Box / Layer Editor", "Attribute Editor", "Modeling Toolkit"


def mod(name):
    return import_module(f"{MODULE}.{name}")


def shot(name):
    if SHOTS:
        scale = round(bpy.context.preferences.system.ui_scale * 100)
        screenshot(os.path.join(SHOTS, f"{name}_{scale}.png"))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def outl():
    a = max((a for a in win().screen.areas if a.type == 'OUTLINER'), key=lambda a: a.height)
    return a, next(r for r in a.regions if r.type == 'WINDOW')


def rows():
    _a, r = outl()
    return mod("ui.outliner_sets").REGIONS.get(r.as_pointer(), [])


def column():
    return next(a for a in win().screen.areas if a.type == 'VIEW_3D' and mod("ui.toolbox").is_toolbox(a.spaces.active))


def dock_region():
    """Maya's tab stack (its own area)."""
    return next(r for r in dock_area().regions if r.type == 'WINDOW')


def tab():
    return mod("ui.maya_dock").current_tab()


def click_row(row):
    _a, r = outl()
    u = mod("ui.outliner_sets").unit(bpy.context.preferences)
    x, y = r.x + int(4 * u), r.y + int((row[0] + row[1]) / 2)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


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


for _i in range(8):          # the fit timer (0.5 s) + ALLSET_OT_fit_columns ticks (column, then Outliner)
    step(redraw)


@step
def s_toolbox():
    col = column()
    tools = next(r for r in col.regions if r.type == 'TOOLS')
    want = mod("ui.toolbox").column_width()
    scale = bpy.context.preferences.system.ui_scale
    check(f"Tool Box column shows its tools at UI scale {scale:.2f} (column {col.width} px, want {want}, "
          f"TOOLS {tools.width} px)", tools.width > 1 and abs(col.width - want) <= 1)
    main, _r = view3d()
    check("the main view shows no toolbar of its own", not main.spaces.active.show_region_toolbar)
    outl_area, _r2 = outl()
    wo = round(260 * scale)
    check(f"the Outliner keeps Maya's panel width at this scale ({outl_area.width} px, want {wo})",
          abs(outl_area.width - wo) <= 2)
    r = rows()
    names = [(x[2], x[3]) for x in r]
    # persp / top / front / side are Maya's startup cameras = Blender's first four rows; the kit draws the
    # default sets right under them
    want_rows = [('DEFAULT_SET', "defaultLightSet"), ('DEFAULT_SET', "defaultObjectSet")]
    check(f"Outliner draws Maya's startup sets ({names})", names == want_rows)
    _a, reg = outl()
    u = mod("ui.outliner_sets").unit(bpy.context.preferences)
    cams = [o.name for o in mod("operators.startup_cameras").cameras(bpy.context.scene)]
    check(f"persp / top / front / side are the first four rows, the sets under them (cameras {cams}, y1 "
          f"{r and r[0][1]} of {reg.height})",
          cams == ["persp", "top", "front", "side"] and bool(r) and abs(r[0][1] - (reg.height - 4 * u)) <= u)
    check(f"dock opens on the {CB!r} tab ({tab()})", tab() == 'CHANNEL_BOX')
    shot("s99_first_screen")


@step
def s_ae():
    bpy.context.window_manager.allset_dock = 'ATTRIBUTE_EDITOR'
    redraw()


@step
def s_ae_check():
    check(f"allset_dock = AE switches the tab ({tab()})", tab() == 'ATTRIBUTE_EDITOR')
    redraw()


# the user clicks the Modeling Toolkit tab of the stack (Maya's vertical tab strip on its right edge)
@step
def s_tab_hover():
    C["mtk_tab"] = dock_tab_point('MODELING_TOOLKIT')
    if C.get("mtk_tab"):
        ev('MOUSEMOVE', 'NOTHING', x=C["mtk_tab"][0], y=C["mtk_tab"][1])


@step
def s_tab_click():
    if C.get("mtk_tab"):
        ev('LEFTMOUSE', 'PRESS', x=C["mtk_tab"][0], y=C["mtk_tab"][1])
        ev('LEFTMOUSE', 'RELEASE', x=C["mtk_tab"][0], y=C["mtk_tab"][1])
    redraw()


@step
def s_tab_check():
    dock = bpy.context.window_manager.allset_dock
    check(f"a tab the user picks becomes the dock state ({C.get('mtk_tab')} -> {dock})",
          dock == 'MODELING_TOOLKIT' and tab() == 'MODELING_TOOLKIT')
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='POINT_LIGHT')
        bpy.ops.allset.create(kind='CUBE')
    redraw()


@step
def s_rows_after():
    r = rows()
    kinds = [x[2] for x in r]
    u = mod("ui.outliner_sets").unit(bpy.context.preferences)
    check(f"with objects the default rows follow Blender's DAG rows ({kinds})",
          kinds[:2] == ['DEFAULT_SET'] * 2 and abs(r[0][1] - (outl()[1].height - 6 * u)) <= u)
    shot("s99_cube_selected")
    C["light"] = next(o.name for o in bpy.context.scene.objects if o.type == 'LIGHT')
    click_row(next(x for x in r if x[3] == "defaultLightSet"))


@step
def s_lightset():
    sel = sorted(o.name for o in bpy.context.selected_objects)
    check(f"defaultLightSet selects the lights ({sel})", sel == [C["light"]])
    h = outl()[1].height
    u = mod("ui.outliner_sets").unit(bpy.context.preferences)
    click_row((h - u, h))                     # Blender's first row = the startup persp camera


@step
def s_persp():
    sel = sorted(o.name for o in bpy.context.selected_objects)
    act = bpy.context.view_layer.objects.active
    check(f"the persp row makes the hidden persp camera the lead, no object selected (Maya) ({sel}, "
          f"{act and act.name})", sel == [] and act is not None and act.name == "persp")
    redraw()


@step
def s_persp_shot():
    shot("s99_persp_row")


run()
