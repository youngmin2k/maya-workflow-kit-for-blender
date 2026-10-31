"""In a real UI (Maya Workflow Kit layout): Ctrl+X cuts the cube, Ctrl+V pastes it back, Alt+X starts Walk (ESC ends it),
Alt+2 hides meshes in the view under the mouse, Alt+\\ sets the playback range to the animation range."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def key(type, **mods):
    names = {"alt": "LEFT_ALT", "ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT"}
    for m in mods:
        ev(names[m], 'PRESS')
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)
    for m in mods:
        ev(names[m], 'RELEASE')


def hover():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


def space():
    return view3d()[0].spaces.active


def modals():
    return [op.bl_idname for op in win().modal_operators]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    for o in bpy.context.scene.objects:
        o.select_set(o.name == "pCube1")
    bpy.context.view_layer.objects.active = bpy.data.objects["pCube1"]
    hover()
    key('X', ctrl=True)


@step
def s_cut():
    check(f"Ctrl+X cuts pCube1 ({sorted(bpy.data.objects.keys())})", "pCube1" not in bpy.data.objects)
    hover()
    key('V', ctrl=True)


@step
def s_paste():
    # Maya pasteScene = pasted__pCube1 under a new group, the group selected
    objs = bpy.data.objects
    check(f"Ctrl+V pastes it back as pasted__pCube1 under group ({sorted(objs.keys())})",
          "pasted__pCube1" in objs and objs["pasted__pCube1"].parent == objs.get("group"))
    act = bpy.context.view_layer.objects.active
    check(f"the paste group is the lead (Channel Box shows it; active {act and act.name})", act is not None and act.name == "group")
    pasted = objs.get("pasted__pCube1")
    check(f"its shape is pasted__ too ({pasted and pasted.data.name})", pasted is not None and pasted.data.name == "pasted__pCubeShape1")
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step90_paste.png"))
    hover()
    key('X', alt=True)


@step
def s_walk():
    C["walk"] = modals()
    check(f"Alt+X starts Walk ({C['walk']})", "VIEW3D_OT_walk" in C["walk"])
    check("Alt+X no longer toggles X-ray", not space().shading.show_xray)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step90_walk.png"))
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


@step
def s_walk_end():
    check(f"ESC ends Walk ({modals()})", "VIEW3D_OT_walk" not in modals())
    hover()
    key('TWO', alt=True)


@step
def s_alt2():
    check("Alt+2 hides polygons in this view", not space().show_object_viewport_mesh)
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step90_alt2.png"))
    key('TWO', alt=True)


@step
def s_alt2_back():
    check("Alt+2 again shows them", space().show_object_viewport_mesh)
    sc = bpy.context.scene
    sc.use_preview_range = True
    sc.frame_preview_start, sc.frame_preview_end = 20, 40
    hover()
    key('BACK_SLASH', alt=True)


@step
def s_range():
    sc = bpy.context.scene
    check(f"Alt+\\ = playback range = animation range (preview {sc.use_preview_range})", not sc.use_preview_range)


run()
