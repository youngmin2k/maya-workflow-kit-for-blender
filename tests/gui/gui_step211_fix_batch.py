"""#117 in a real window: a new Maya scene's Outliner lists Maya's startup cameras
persp / top / front / side first (real hidden Blender rows, not drawn after the objects), then the objects in creation
order, the default sets and kit sets last; a click on the persp row makes it the lead (Channel Box "persp"). The
Attribute Editor (dock fitted, ALLSET_FIT_WARP=1) shows its node tabs as one row and Select / Load Attributes /
Copy Tab as one row (audit 16 G1 / G2)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import (MODULE, check, dock_area, dock_region, dock_tab_point, ev, load_maya_layout, run, scale,  # noqa: E402
                 screenshot, setup, step, view3d, win)

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
os.environ["ALLSET_FIT_WARP"] = "1"   # the cursor fit is off in event-simulated sessions unless asked for
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def shot(name):
    tag = f"{scale():.2f}".replace(".", "")
    screenshot(os.path.join(SHOTS or bpy.app.tempdir, f"gui_step211_{name}_{tag}.png"))


def outl():
    a = max((a for a in win().screen.areas if a.type == 'OUTLINER'), key=lambda a: a.height)
    return a, next(r for r in a.regions if r.type == 'WINDOW')


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
def s_scene():
    stc = mod("operators.startup_cameras")
    sc = bpy.context.scene
    names = [o.name for o in stc.cameras(sc)]
    check(f"a new Maya scene has Maya's startup cameras ({names})", names == ["persp", "top", "front", "side"])
    check("they are hidden and don't render", all(o.hide_viewport and o.hide_render for o in stc.cameras(sc)))
    a, _r = outl()
    check("the Maya Outliner lists in creation order (Sort Alphabetically off)", not a.spaces.active.use_sort_alpha)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.allset.create(kind='SPHERE')
    mod("operators.sets").create(objects=[bpy.data.objects["pCube1"]])
    redraw()


for _i in range(3):            # ui/outliner_order.py relinks from its 0.25 s timer
    step(redraw)


@step
def s_order_check():
    _a, reg = outl()
    rows = mod("ui.outliner_sets").REGIONS.get(reg.as_pointer(), [])
    kinds = [r[2] for r in rows]
    check(f"drawn rows: no camera rows, default sets then the kit set ({[r[3] for r in rows]})",
          'CAMERA' not in kinds and kinds[:3] == ['DEFAULT_SET', 'DEFAULT_SET', 'SET'])
    u = mod("ui.outliner_sets").unit(bpy.context.preferences)
    if rows:
        k = round((reg.height - rows[0][1]) / u)
        check(f"the default sets follow 6 Blender rows (4 cameras + 2 objects; first drawn row = row {k})", k == 6)
    shot("outliner")
    C["u"], C["seen"] = u, []


def _row_point(k):
    _a, reg = outl()
    u = C["u"]
    return reg.x + int(4 * u), reg.y + reg.height - int((k + 0.5) * u)


def _scan(k):
    def hover():
        x, y = _row_point(k)
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)

    def press():
        x, y = _row_point(k)
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)

    def release():
        x, y = _row_point(k)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
        redraw()

    def read():
        active = bpy.context.view_layer.objects.active
        C["seen"].append(active.name if active else None)
    for f in (hover, press, release, read):
        step(f)
        for _i in range(3 if f is read else 0):
            step(redraw)
    for _i in range(12):            # no double click on the next row
        step(redraw)


for _k in range(6):
    _scan(_k)


@step
def s_order_seen():
    check(f"the Outliner rows from the top, clicked one by one: {C['seen']} (Maya: startup cameras, then creation "
          "order)", C["seen"] == ["persp", "top", "front", "side", "pCube1", "pSphere1"])
    shot("persp_lead")
    cube = bpy.data.objects["pCube1"]
    for o in bpy.context.scene.objects:
        if o.visible_get():
            o.select_set(o == cube)
    bpy.context.view_layer.objects.active = cube
    C["ae_tab"] = dock_tab_point('ATTRIBUTE_EDITOR')
    ev('MOUSEMOVE', 'NOTHING', x=C["ae_tab"][0], y=C["ae_tab"][1])
    redraw()


@step
def s_ae_click():
    ev('LEFTMOUSE', 'PRESS', x=C["ae_tab"][0], y=C["ae_tab"][1])
    ev('LEFTMOUSE', 'RELEASE', x=C["ae_tab"][0], y=C["ae_tab"][1])
    redraw()


for _i in range(8):          # draw -> timer -> cursor fit ticks
    step(redraw)


@step
def s_ae():
    wm = bpy.context.window_manager
    check(f"the Attribute Editor is raised ({wm.allset_dock})", wm.allset_dock == 'ATTRIBUTE_EDITOR')
    dock, reg = dock_area(), dock_region()
    tb = mod("ui.toolbox")
    target = tb._dock_target(win(), bpy.context.preferences.system.ui_scale,
                             bpy.context.preferences.system.pixel_size, 'ATTRIBUTE_EDITOR')
    want = target[1] if target else None
    check(f"the dock widens to Maya's AE width ({dock.width} px, want {want})",
          want is not None and abs(dock.width - want) <= 3)
    ae = mod("ui.attribute_editor")
    ob = bpy.data.objects["pCube1"]
    with bpy.context.temp_override(window=win(), area=dock, region=reg):
        ctx = bpy.context
        labels = [label for _k, label, _t in ae.tabs(ob)]
        widths = ae.text_widths(ctx, labels)
        avail = ae.content_width(ctx)
        a, b, over = ae.tab_window(widths, avail, 0, 0)
        bottom = ae.wrap_rows(ctx, [t for _o, t in ae.BOTTOM])
    check(f"the node tabs are one row with every tab shown ({labels}, {sum(widths):.0f} / {avail} px)",
          not over and (a, b) == (0, len(labels)) and len(labels) >= 4)
    check(f"Select / Load Attributes / Copy Tab are one row ({bottom})", len(bottom) == 1)
    shot("ae")


run()
