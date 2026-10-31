"""#137: in a real UI: pCube1 with a blendShape, a target and an in-between at 0.5 (Shape Editor Create >
Add In-Between Target through the Maya menu item) and a combination target; Windows > Animation Editors > Shape Editor
opens the kit Shape Editor, which draws the in-between as a row under its target (weight 0.500) and the combination
target with its method; the helper keys (``_ib500`` / ``_ibfix``) are not listed. Shot: gui_step227_shape_editor.png."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, setup, step, win  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {"rows": [], "targets": []}


def mod(name):
    return import_module(MODULE + name)


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def menu(item):
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return bpy.ops.allset.menu_item(item=item)


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def _record():
    """Wrap the Shape Editor's row drawing: which in-between rows / targets it draws (and in what order)."""
    se = mod(".ui.shape_editor")
    orig_ib = se._draw_inbetween

    def draw_inbetween(col, key, kb, w, label, in_edit):
        C["rows"].append(("ib", kb.name, round(w, 3), label))
        return orig_ib(col, key, kb, w, label, in_edit)

    se._draw_inbetween = draw_inbetween
    C["restore"] = lambda: setattr(se, "_draw_inbetween", orig_ib)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    cube = bpy.context.active_object
    C["cube"] = cube.name
    for o in bpy.context.scene.objects:
        if o.visible_get():
            o.select_set(o == cube)
    C["create"] = bpy.ops.allset.shape_create()
    key = cube.data.shape_keys
    with bpy.context.temp_override(window=win(), area=area, region=region):
        C["add"] = bpy.ops.allset.shape_add_target()
        bpy.ops.allset.shape_add_target()
    smile = key.key_blocks[1]
    for v in smile.data[:4]:
        v.co.z += 0.5 * mod(".operators.units").maya_unit()
    mod(".ui.shape_editor").edit_off(bpy.context)
    wm = bpy.context.window_manager
    wm.allset_se_current = f"{key.name}/1"
    C["ib"] = menu("Shape Editor/Create/Add In-Between Target")
    mod(".ui.shape_editor").edit_off(bpy.context)
    names = [kb.name for kb in key.key_blocks[1:3]]
    C["combo"] = bpy.ops.allset.shape_add_combination(key=key.name, targets="\t".join(names))
    mod(".ui.shape_editor").edit_off(bpy.context)
    C["key"] = key.name
    C["names"] = names
    C["all"] = [kb.name for kb in key.key_blocks]
    _record()
    C["open"] = menu("Windows/Animation Editors/Shape Editor")


@step
def s_draw():
    redraw()


@step
def s_draw2():
    redraw()


@step
def s_check():
    bs = mod(".operators.blend_shapes_227")
    key = bpy.data.shape_keys[C["key"]]
    target = C["names"][0]
    check(f"Create Blend Shape / Add Target x2 / Add In-Between (menu) / Add Combination: {C['create']} {C['add']} "
          f"{C['ib']} {C['combo']}; keys {C['all']}",
          C["ib"] == {'FINISHED'} and C["combo"] == {'FINISHED'} and bs.inbetweens(key).get(target))
    mw = mod(".ui.marked_window")
    w = mw.find_window(bpy.context, "SHAPE_EDITOR")
    check(f"Shape Editor window opens ({C['open']})", w is not None)
    C["win"] = w
    rows = [r for r in C["rows"] if r[0] == "ib"]
    check(f"the in-between row draws under its target: {sorted(set(rows))}",
          any(r[1] == target and r[2] == 0.5 for r in rows))
    shown = [kb.name for kb in bs.target_blocks(key)]
    check(f"helper keys are not listed as targets: {shown}",
          not any(n.endswith("_ibfix") or "_ib5" in n for n in shown) and len(shown) == 3)
    check(f"the combination target is recorded: {bs.combinations(key)}", len(bs.combinations(key)) == 1)


@step
def s_shot():
    if SHOTS and C.get("win"):
        with bpy.context.temp_override(window=C["win"]):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_step227_shape_editor.png"))
    if C.get("restore"):
        C["restore"]()
    wm = bpy.context.window_manager
    for w in list(wm.windows)[1:]:
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()


run()
