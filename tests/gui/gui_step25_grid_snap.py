"""In a real UI: X hold + Move gizmo drag snaps to whole Maya units (1 cm) in the
Maya Workflow Kit layout and with Maya Units on, to whole metres in the factory scene; the grid
shows in the Maya Workflow Kit persp view (screenshot)."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def area3d():
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)


def region3d():
    return next(r for r in area3d().regions if r.type == 'WINDOW')


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def units():
    return import_module(MODULE + ".operators.units")


def make_cube():
    area, region = area3d(), region3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    ob = bpy.context.view_layer.objects.active
    C["ob"] = ob.name
    C["k"] = units().maya_unit()


def hover_arrow():
    ob = bpy.data.objects[C["ob"]]
    region = region3d()
    o = location_3d_to_region_2d(region, region.data, ob.location)
    a = location_3d_to_region_2d(region, region.data, ob.location + Vector((C["k"], 0, 0)))
    d = (a - o).normalized()
    size = bpy.context.preferences.view.gizmo_size * bpy.context.preferences.system.ui_scale
    p = o + d * size * 0.75
    C["g"] = (int(region.x + p.x), int(region.y + p.y), d)
    x, y, _ = C["g"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


def snap_drag(px=110):
    x, y, d = C["g"]
    ev('X', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    for i in range(1, 11):
        ev('MOUSEMOVE', 'NOTHING', x=int(x + d.x * px * i / 10), y=int(y + d.y * px * i / 10))
    ev('LEFTMOUSE', 'RELEASE', x=int(x + d.x * px), y=int(y + d.y * px))
    ev('X', 'RELEASE', x=int(x + d.x * px), y=int(y + d.y * px))


def check_snap(label, unit_name):
    ob = bpy.data.objects[C["ob"]]
    n = ob.location.x / C["k"]          # in Maya units (= display units)
    check(f"{label}: X snap lands on a whole {unit_name}, not 0 (x = {n:.4f} {unit_name})",
          abs(n - round(n)) < 1e-3 and round(n) >= 1 and abs(ob.location.y) < 1e-6)


# --- Maya Workflow Kit layout (m + cm display) ----------------------------------------------------

@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_template():
    bpy.ops.allset.keymap_activate()
    ov = area3d().spaces.active.overlay
    check(f"Maya Workflow Kit persp grid scale = 0.01 (1 cm step) ({ov.grid_scale})", abs(ov.grid_scale - 0.01) < 1e-6)
    make_cube()
    redraw()


@step
def s_template_shot():
    shot("gui_step25_grid_cm.png")
    hover_arrow()


@step
def s_template_drag():
    snap_drag()


@step
def s_template_done():
    check_snap("Maya Workflow Kit layout", "cm")
    # the view draws the Maya grid (Blender floor off), its lines are every Maya unit, so the
    # snapped copy sits on a grid line inside the 12-unit grid; the grid was drawn (draw time > 0).
    grid = import_module(MODULE + ".ui.maya_grid")
    space = area3d().spaces.active
    n = bpy.data.objects[C["ob"]].location.x / C["k"]
    lines = {round(line[0][0]) for kind in grid.segments().values() for line in kind if line[0][1] == -grid.SIZE}
    check(f"Maya grid on in the Maya Workflow Kit view, snapped x = {n:.3f} is one of its lines",
          grid.is_on(space) and not space.overlay.show_floor and round(n) in lines)
    check(f"Maya grid drawn ({grid.frame_ms():.3f} ms per draw)", 0.0 < grid.frame_ms() < 5.0)
    print("GUI grid draw ms", grid.frame_ms())
    shot("gui_step25_snapped_cm.png")
    # Maya Units on: a new file gets cm with scale_length 0.01
    prefs = import_module(MODULE + ".preferences").get()
    prefs.maya_units = True
    load_maya_layout()


@step
def s_maya_units():
    bpy.ops.allset.keymap_activate()
    prefs = import_module(MODULE + ".preferences").get()
    if not prefs.maya_units:            # read_homefile reloads factory prefs (--factory-startup)
        prefs.maya_units = True
    us = bpy.context.scene.unit_settings
    ov = area3d().spaces.active.overlay
    check(f"Maya Units: scale_length 0.01, grid scale 0.01 ({us.scale_length:.4f}, {ov.grid_scale})",
          abs(us.scale_length - 0.01) < 1e-6 and abs(ov.grid_scale - 0.01) < 1e-6)
    make_cube()
    check(f"Maya Units: 1 Maya unit = 1 BU ({C['k']:.4f})", abs(C["k"] - 1.0) < 1e-4)
    redraw()


@step
def s_maya_units_hover():
    hover_arrow()


@step
def s_maya_units_drag():
    snap_drag()


@step
def s_maya_units_done():
    check_snap("Maya Units", "cm")
    import_module(MODULE + ".preferences").get().maya_units = False
    bpy.ops.wm.read_homefile(app_template="")


# --- factory scene (m display) ----------------------------------------------------------

@step
def s_factory():
    bpy.ops.allset.keymap_activate()
    for name in ("Cube", "Camera", "Light"):
        ob = bpy.data.objects.get(name)
        if ob is not None:
            bpy.data.objects.remove(ob)
    ov = area3d().spaces.active.overlay
    check(f"factory grid scale untouched ({ov.grid_scale})", abs(ov.grid_scale - 1.0) < 1e-6)
    make_cube()
    redraw()


@step
def s_factory_hover():
    hover_arrow()


@step
def s_factory_drag():
    snap_drag(px=160)


@step
def s_factory_done():
    check_snap("factory scene", "m")


run()
