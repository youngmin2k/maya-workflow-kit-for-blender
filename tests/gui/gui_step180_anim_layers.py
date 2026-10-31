"""In the Maya Workflow Kit layout: the Layer Editor Anim tab = Maya animation
layers on NLA tracks (ui/layer_editor.draw_anim_tab, operators/anim_layers.py).

A keyed pCube1 (translateX at frames 1 and 10), two layers made with Create Layer from Selected, AnimLayer1 muted:
the tab lists AnimLayer2 / AnimLayer1 / BaseAnimation (top layer first), a click on the AnimLayer2 row selects it,
its Weight writes the NLA strip influence. Shot ``gui_step180_anim_tab.png`` with ``--shots``."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import (MODULE, check, dock_area, dock_region, ev, find_button, load_maya_layout, run,  # noqa: E402
                 screenshot, setup, step, view3d, win)

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def dock():
    return dock_area(), dock_region()


def layers():
    return bpy.context.scene.allset_anim_layers


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_keys():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.allset.create(kind='CUBE')
    cube = bpy.data.objects["pCube1"]
    u = mod("operators.units").maya_unit(bpy.context.scene)
    for f, x in ((1, 0.0), (10, 10.0 * u)):
        cube.location.x = x
        cube.keyframe_insert("location", index=0, frame=f)
    for o in bpy.context.scene.objects:
        o.select_set(o == cube)
    bpy.context.view_layer.objects.active = cube
    bpy.context.scene.frame_set(1)
    dock_area('CHANNEL_BOX')
    bpy.context.window_manager.allset_le_tab = 'ANIM'
    redraw()


@step
def s_layers():
    with override():
        bpy.ops.allset.anim_layer_create(from_selected=True)
        bpy.ops.allset.anim_layer_create(from_selected=True)
    ls = layers()
    names = [e.name for e in ls]
    check(f"two layers from selected ({names})", names == ["BaseAnimation", "AnimLayer1", "AnimLayer2"])
    ls[1].mute = True
    bpy.context.scene.allset_anim_layer_index = 0       # BaseAnimation, so the click below has something to do
    redraw()


@step
def s_wait():
    redraw()


@step
def s_order():
    le = mod("ui.layer_editor")
    ls = layers()
    order = [ls[i].name for i in le.anim_display_order(bpy.context.scene)]
    check(f"Anim tab lists the top layer first, BaseAnimation last ({order})",
          order == ["AnimLayer2", "AnimLayer1", "BaseAnimation"])
    redraw()


step(find_button(dock, lambda _p, c: "anim_layer_select(index=2)" in c, C, "row2", x_frac=0.6, step_px=4))
step(find_button(dock, lambda p, _c: p.endswith("allset_anim_layers[2].mute"), C, "mute2", y_from="row2",
                 step_px=4))


@step
def s_hover():
    check(f"AnimLayer2 row button found ({C.get('row2')})", C.get("row2") is not None)
    check(f"Lock / Solo / Mute toggles drawn on the rows (AnimLayer2 Mute found: {C.get('mute2')})", C.get("mute2") is not None)
    if C.get("row2"):
        x, y = C["row2"]
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_press():
    if C.get("row2"):
        ev('LEFTMOUSE', 'PRESS')


@step
def s_release():
    if C.get("row2"):
        ev('LEFTMOUSE', 'RELEASE')
    redraw()


@step
def s_clicked():
    i = bpy.context.scene.allset_anim_layer_index
    check(f"a click on the AnimLayer2 row selects it (index {i})", i == 2)
    # park the mouse in the viewport (no hover highlight / tooltip in the shot)
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    redraw()


step(find_button(dock, lambda p, _c: p.endswith("allset_anim_layers[2].weight"), C, "weight", x_frac=0.5,
                 step_px=4))


@step
def s_weight_found():
    check(f"Weight slider of the selected layer drawn ({C.get('weight')})", C.get("weight") is not None)
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    layers()[2].weight = 0.4          # the UI property (its update writes the NLA tracks)
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_shot():
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step180_anim_tab.png"))
    ob = bpy.data.objects["pCube1"]
    tr = ob.animation_data.nla_tracks
    st = tr["AnimLayer2"].strips[0]
    check(f"Weight 0.4 = AnimLayer2 strip influence ({st.influence:.4f}, animated {st.use_animated_influence})",
          abs(st.influence - 0.4) < 1e-6 and st.use_animated_influence)
    check(f"AnimLayer1 muted = its NLA track muted ({tr['AnimLayer1'].mute})", tr["AnimLayer1"].mute)
    check(f"AnimLayer2 Additive = COMBINE strip ({st.blend_type})", st.blend_type == 'COMBINE')


run()
