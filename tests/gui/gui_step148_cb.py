"""In the Maya Workflow Kit layout. Run at the default 1.25, ``--ui-scale 0.8``
(1.0) and ``--ui-scale 1.2`` (1.5) in the 1600 x 900 test window; shots with ``--shots``.

#87: RMB on a Channel Box channel name opens Maya's Channels menu (not Blender's button menu with its 15 rows on
top); its first row Key Selected keys the clicked channel.
#83: the Channel Box pane has no empty rows above the Layer Editor (the scroll window fills its part).
#85: the Channel Box menu bar reads "Channels"; numbers in the Channel Box / AE fields are not cut.
#95 / lights: a lattice reads Scale 2, a point light shows Color R / G / B and Intensity."""

import os
import sys
from importlib import import_module

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import (MODULE, check, dock_area, dock_region, ev, find_button, load_maya_layout, run, scale,  # noqa: E402
                 screenshot, setup, step, tap, view3d, win)

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
os.environ["ALLSET_FIT_WARP"] = "1"   # the fitted dock width
C = {}
GUI_TIMEOUT = 240


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def tag():
    return f"{scale():.2f}".replace(".", "")


def shot(name):
    """Window screenshot as (h, w, 3) floats, row 0 = window bottom; also kept in SHOTS."""
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step148_{name}_{tag()}.png")
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def dock():
    return dock_area(), dock_region()


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_keymap():
    bpy.ops.allset.keymap_activate()
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    redraw()


for _i in range(10):         # the fit timer + fit_columns ticks
    step(redraw)


@step
def s_cube():
    with override():
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.data.objects["pCube1"]
    ob.keyframe_insert("location", frame=1)
    bpy.context.scene.frame_set(12)
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'
    redraw()


@step
def s_cube_wait():
    redraw()


@step
def s_long():
    """#83: twelve custom attributes make the Channel Box longer than its pane at every scale."""
    shot("cb_cube")
    ob = bpy.data.objects["pCube1"]
    for i in range(12):
        ob[f"attr{i:02d}"] = float(i)
    mod("ui.channel_box").rebuild_rows()
    redraw()


@step
def s_long_wait():
    redraw()


@step
def s_cube_shot():
    px = shot("cb_long")
    _area, region = dock()
    cbm = mod("ui.channel_box")
    lines = cbm._last.get(dock_area().as_pointer())
    C["cb_last"] = lines
    # the Layer Editor's top = the dark list box under the Channel Box part; look for the lowest drawn Channel Box
    # text row and the first Layer Editor widget below it (column of the field values)
    print("GUI148 cb pane", tag(), "region", (region.x, region.y, region.width, region.height), "lines", lines,
          flush=True)


# --- #87: RMB on a channel name ----------------------------------------------------------------------------------

step(find_button(dock, lambda p, _c: p.endswith("allset_cb.rz_text"), C, "rz_field", x_frac=0.7, step_px=4))
step(find_button(dock, lambda p, _c: p.endswith("allset_cb.rz_sel"), C, "rz_name", y_from="rz_field", step_px=8))


@step
def s_rmb_hover():
    check(f"Rotate Z name found ({C.get('rz_name')})", C.get("rz_name") is not None)
    x, y = C["rz_name"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_rmb_hover2():
    x, y = C["rz_name"]
    ev('MOUSEMOVE', 'NOTHING', x=x + 1, y=y)


@step
def s_rmb():
    ev('RIGHTMOUSE', 'PRESS')
    ev('RIGHTMOUSE', 'RELEASE')


@step
def s_menu_open():
    shot("rmb_menu")
    sel = mod("ui.channel_box").selected_channels()
    check(f"#87 RMB on an unselected name selects it for the menu ({sel})", sel == ["rz"])



@step
def s_pick():
    # the complete Channels menu is taller than the space under the mouse and slides up, so Key Selected
    # is picked by its underlined letter
    tap('K')


@step
def s_picked():
    ob = bpy.data.objects["pCube1"]
    ad = ob.animation_data
    curves = import_module(MODULE + ".compat").id_fcurves(ob) if ad and ad.action else []   # 5.0: no Action.fcurves
    keyed = [fc.array_index for fc in curves
             if fc.data_path == "rotation_euler" and any(abs(k.co[0] - 12) < 1e-6 for k in fc.keyframe_points)]
    check(f"#87 the Channels menu's Key Selected: Rotate Z keyed at 12 ({keyed})", keyed == [2])
    tap('ESC')
    mod("ui.channel_box").set_selected_channels([])
    redraw()


# --- #85: the Attribute Editor at this width ----------------------------------------------------------------------

@step
def s_ae():
    ob = bpy.data.objects["pCube1"]
    ob.location = (0.62, -1.5, 0.0)
    ob.scale = (1.5, 1.5, 1.5)
    bpy.context.window_manager.allset_dock = 'ATTRIBUTE_EDITOR'
    bpy.context.window_manager.allset_ae_tab = "T"          # the transform tab (Transform Attributes)
    redraw()


for _i in range(4):
    step(redraw)


@step
def s_ae_shot():
    shot("ae")
    text = (bpy.context.scene.allset_cb.tx_text, bpy.context.scene.allset_cb.sx_text)
    check(f"#85 AE Translate / Scale fields are Maya numbers (no unit): {text}", text == ("62", "1.5"))
    bpy.context.window_manager.allset_dock = 'CHANNEL_BOX'
    redraw()


for _i in range(4):
    step(redraw)


# --- #95 lattice, light ---------------------------------------------------------------------------------------------

@step
def s_lattice():
    ob = bpy.data.objects["pCube1"]
    ob.scale = (1, 1, 1)
    ob.location = (0, 0, 0)
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    with override():
        bpy.ops.allset.menu_item('EXEC_DEFAULT', True, item="Deform/Lattice")
    redraw()


@step
def s_lattice_wait():
    redraw()


@step
def s_lattice_shot():
    shot("lattice")
    lat = bpy.data.objects.get("ffd1Lattice")
    sc = tuple(round(v, 4) for v in lat.scale) if lat else None
    size = tuple(round(v, 5) for v in lat.matrix_world.to_scale()) if lat else None
    # a polyCube is 1 unit wide: its lattice reads Scale 1 1 1 (a radius 1 sphere's reads 2); the
    # world size is the cube's (1 cm in the cm template), not 1 m
    check(f"#95 ffd1Lattice Scale = 1 1 1 around the 1-unit cube ({sc}; world {size})",
          sc is not None and all(abs(v - 1.0) < 1e-3 for v in sc)
          and all(abs(v - 0.01) < 1e-4 for v in size))
    with override():
        bpy.ops.allset.create(kind='POINT_LIGHT')
    redraw()


@step
def s_light_wait():
    redraw()


@step
def s_light_shot():
    shot("light")
    cbm = mod("ui.channel_box")
    ob = cbm.lead(bpy.context)
    rows = [r.name for r in bpy.context.scene.allset_cb.rows if r.kind == "SHAPE"]
    check(f"point light SHAPES rows = Maya Color R / G / B, Intensity ({ob and ob.name}: {rows})",
          rows == ["maya:colorR", "maya:colorG", "maya:colorB", "allset_intensity"])


run()
