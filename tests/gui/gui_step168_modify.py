"""In a real UI: Modify > Evaluate Nodes draws Maya's check items (one unticked after Constraints is
switched off), the Align Tool popup shows its X / Y / Z x Min / Mid / Max buttons, and Smooth Mesh Preview to
Polygons from the menu turns a 3-key preview into polygons; screenshots (ALLSET_GUI_SHOTS)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def esc():
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


def submenu(label, parent="mainModifyMenu"):
    prefix = f"ALLSET_MT_{parent}_"
    for name in dir(bpy.types):
        cls = getattr(bpy.types, name, None)
        if name.startswith(prefix) and getattr(cls, "bl_label", "") == label:
            return name
    return None


def v3d_override():
    a = view3d()[0]
    region = next(r for r in a.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=win(), area=a, region=region)


@step
def s_setup():
    setup()
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.create(kind='CUBE')
    C["cube"] = bpy.context.view_layer.objects.active.name
    check("object mode with a cube", bpy.context.mode == 'OBJECT' and C["cube"])


@step
def s_preview():
    ob = bpy.data.objects[C["cube"]]
    with v3d_override():
        bpy.ops.allset.smooth_preview(level=3)
    C["faces"] = len(ob.data.polygons)


@step
def s_convert():
    ob = bpy.data.objects[C["cube"]]
    with v3d_override():
        res = bpy.ops.allset.menu_item(item="Modify/Convert/Smooth Mesh Preview to Polygons")
    check(f"menu item Smooth Mesh Preview to Polygons runs ({res})", res == {'FINISHED'})
    check(f"faces x 16 ({C['faces']} -> {len(ob.data.polygons)})", len(ob.data.polygons) == C["faces"] * 16)
    check("no preview modifier left", not any(m.name.startswith("Maya Smooth Preview") for m in ob.modifiers))


@step
def s_eval_menu():
    bpy.context.scene.allset_eval.constraint = False
    name = submenu("Evaluate Nodes")
    check(f"Evaluate Nodes submenu registered ({name})", name is not None)
    if name:
        with bpy.context.temp_override(window=win()):
            bpy.ops.wm.call_menu(name=name)


@step
def s_wait1():
    pass


@step
def s_eval_shot():
    shot("gui_step168_evaluate_nodes.png")
    esc()
    bpy.context.scene.allset_eval.constraint = True


@step
def s_align():
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.create(kind='CUBE')
    second = bpy.context.view_layer.objects.active
    second.location.x = 3
    bpy.data.objects[C["cube"]].select_set(True)
    second.select_set(True)
    bpy.context.view_layer.objects.active = second
    ev('MOUSEMOVE', 'NOTHING', x=win().width // 2, y=win().height // 2)
    with v3d_override():
        res = bpy.ops.allset.align_tool('INVOKE_DEFAULT')
    check(f"Align Tool opens its popup ({res})", res != {'CANCELLED'})


@step
def s_wait2():
    pass


@step
def s_align_shot():
    shot("gui_step168_align_tool.png")
    esc()


run()
