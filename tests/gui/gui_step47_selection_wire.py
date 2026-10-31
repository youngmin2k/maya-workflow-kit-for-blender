"""In a real UI: Maya selection wire over shading — drawn for the selected objects in the Maya Workflow Kit
layout, and the frame time with a 100k-poly selected mesh grows < 20 % (wm.redraw_timer)."""

import os
import sys
import time
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, screenshot, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def area3d():
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)


def region3d():
    return next(r for r in area3d().regions if r.type == 'WINDOW')


def prefs():
    return bpy.context.preferences.addons[MODULE].preferences


def frame_ms(n=40):
    with bpy.context.temp_override(window=win(), area=area3d(), region=region3d()):
        bpy.ops.wm.redraw_timer(type='DRAW', iterations=5)
        t = time.perf_counter()
        bpy.ops.wm.redraw_timer(type='DRAW', iterations=n)
    return (time.perf_counter() - t) / n * 1000.0


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cubes():
    bpy.ops.allset.keymap_activate()
    with bpy.context.temp_override(window=win(), area=area3d(), region=region3d()):
        bpy.ops.allset.create(kind='CUBE')
        a = bpy.context.view_layer.objects.active
        bpy.ops.allset.create(kind='CUBE')
        b = bpy.context.view_layer.objects.active
    b.location.x = 2 * import_module(MODULE + ".operators.units").maya_unit()
    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob in (a, b))
    bpy.context.view_layer.objects.active = a
    C["ab"] = (a.name, b.name)
    area3d().tag_redraw()


@step
def s_wire_check():
    a, b = (bpy.data.objects[n] for n in C["ab"])
    sw = import_module(MODULE + ".ui.selection_wire")
    with bpy.context.temp_override(window=win(), area=area3d(), region=region3d()):
        names = sorted(o.name for o in sw.wire_objects(bpy.context))
    check(f"selected {a.name} (lead) and {b.name} get the selection wire, drawn ({sw.frame_ms():.3f} ms), "
          f"no show_wire written", names == sorted((a.name, b.name)) and sw.frame_ms() > 0
          and not a.show_wire and not b.show_wire)
    check("Maya Workflow Kit view: no Blender selection outline (Maya highlights with the wire)",
          not area3d().spaces.active.overlay.show_outline_selected)
    shot("gui_step47_two_selected.png")
    # 100k-poly mesh, selected alone
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    with bpy.context.temp_override(window=win(), area=area3d(), region=region3d()):
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=317, y_subdivisions=317, size=0.3)
        bpy.ops.view3d.view_selected()
    g = bpy.context.view_layer.objects.active
    C["polys"] = len(g.data.polygons)
    prefs().maya_selection_wire = False
    area3d().tag_redraw()


@step
def s_time_off():
    C["off"] = frame_ms()
    prefs().maya_selection_wire = True
    area3d().tag_redraw()


@step
def s_time_on():
    g = bpy.context.view_layer.objects.active
    C["on"] = frame_ms()
    ratio = C["on"] / C["off"]
    print("GUI frame ms", C["polys"], C["off"], C["on"], ratio)
    check(f"{C['polys']} polys: frame {C['off']:.3f} -> {C['on']:.3f} ms with the selection wire "
          f"(+{(ratio - 1) * 100:.1f} %, < 20 %)", g.select_get() and ratio < 1.2)
    shot("gui_step47_100k.png")


run()
