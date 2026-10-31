"""In a real UI: a source scene referenced twice (prop / prop1, the second unloaded), then File > Reference
Editor -> a new window whose Properties area is the kit Reference Editor (Maya menu bar File / Reference / Proxy /
View / Help, icon row, File Particulars, list "propRN srcA.blend" with load check boxes); Reload from the list's
selection; shot beside Maya's Reference Editor."""

import os
import sys
from importlib import import_module
from pathlib import Path

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
TMP = Path(__file__).resolve().parents[2] / "tmp" / os.environ.get("ALLSET_SANDBOX", "test_env") / "gui209"
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_source():
    bpy.ops.allset.keymap_activate()
    TMP.mkdir(parents=True, exist_ok=True)
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.allset.create(kind='SPHERE')
    bpy.data.objects["pSphere1"].location.x = 0.03
    C["src"] = str(TMP / "srcA.blend")
    bpy.ops.wm.save_as_mainfile(filepath=C["src"], copy=True)
    load_maya_layout()


@step
def s_reference():
    bpy.ops.allset.keymap_activate()
    for _ in range(2):
        bpy.ops.allset.create_reference(filepath=C["src"], namespace="prop")
    refs = mod(".operators.references")
    names = [(r.name, refs.node_name(r)) for r in refs.references()]
    check(f"two references like Maya: {names}", names == [("prop", "propRN"), ("prop1", "propRN1")])
    bpy.ops.allset.reference_cmd(action="UNLOAD", reference="prop1")
    bpy.context.window_manager.allset_ref_current = "prop"
    bpy.data.objects["prop:pCube1"].location.z = 0.05
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        C["open"] = bpy.ops.allset.menu_item(item="File/Reference Editor")


@step
def s_wait():
    redraw()


@step
def s_check():
    re_ = mod(".ui.reference_editor")
    w = re_.find_window(bpy.context)
    check(f"File > Reference Editor opens a window with the kit pane ({C['open']})", w is not None)
    if w is None:
        return
    C["win"] = w
    area = next(a for a in w.screen.areas if re_.is_pane(a))
    check("one area, header hidden (Maya window)", len(w.screen.areas) == 1 and not area.spaces.active.show_region_header)
    ms = mod(".ui.menu_sets")
    ids = [ms.editor_menu_idname("Reference Editor", i) for i in range(5)]
    check("its five menus are registered", all(hasattr(bpy.types, i) for i in ids))
    bpy.ops.allset.reference_cmd(action="RELOAD")
    ob = bpy.data.objects.get("prop:pCube1")
    check(f"Reload from the selected row keeps the edit ({tuple(ob.location) if ob else None})",
          ob is not None and abs(ob.location.z - 0.05) < 1e-6)
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_shot():
    w = C.get("win")
    if w is not None:
        shot("gui_step209_reference_editor.png", w)
    shot("gui_step209_main.png")


run()
