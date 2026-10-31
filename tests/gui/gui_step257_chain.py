"""Issues #149 #150 #151 as a Maya user in the Maya layout: Create > Cylinder -> Ctrl+E on the cap +
Local Translate Z 1 -> Ctrl+B on the cap rim (Maya polyBevel3 numbering, #149) -> object mode UV > Automatic from the
menu (Channel Box INPUTS polyAutoProj1, editable, #150) -> S keys on a locator at 1 / 12 / 24 (Maya 2026 auto
tangents, #151) -> Ctrl+Z -> save / open. Screenshot: gui_step257_inputs.png (Channel Box with polyAutoProj1 open)."""

import os
import sys
import tempfile
from importlib import import_module

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import (MODULE, check, ev, load_maya_layout, open_inputs, run, screenshot, scroll_channel_box,  # noqa: E402
                 setup, step, view3d, win)

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def mod(name):
    return import_module(MODULE + "." + name)


def override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def centre():
    _a, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)


def key(type, **mods):
    centre()
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_cylinder():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.allset.create(kind='CYLINDER')
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        ob = bpy.context.view_layer.objects.active
        C["ob"] = ob
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bm = bmesh.from_edit_mesh(ob.data)
        k = mod("operators.units").maya_unit(bpy.context.scene)
        for f in bm.faces:
            f.select_set(f.calc_center_median().z > 0.99 * k)
        bmesh.update_edit_mesh(ob.data)
    centre()


@step
def s_extrude():
    key('E', ctrl=True)


@step
def s_extrude_value():
    ex = mod("operators.extrude")
    with override():
        check("Ctrl+E made polyExtrudeFace1", ex.active(bpy.context)[1] is not None)
        ex.set_params(bpy.context, local_translate_z=1.0)
        ob = C["ob"]
        bpy.ops.mesh.select_mode(type='EDGE')
        bm = bmesh.from_edit_mesh(ob.data)
        k = mod("operators.units").maya_unit(bpy.context.scene)
        top = {f for f in bm.faces if f.calc_center_median().z > 1.99 * k}
        for e in bm.edges:
            e.select_set(sum(1 for f in e.link_faces if f in top) == 1)
        bmesh.update_edit_mesh(ob.data)
    centre()


@step
def s_bevel():
    key('B', ctrl=True)


@step
def s_bevel_check():
    ob = C["ob"]
    bm = bmesh.from_edit_mesh(ob.data)
    check(f"Ctrl+B on the rim: 82 vertices / 100 faces like Maya ({len(bm.verts)} / {len(bm.faces)})",
          (len(bm.verts), len(bm.faces)) == (82, 100))
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
        res = bpy.ops.allset.menu_item(item="UV/Automatic")
    check(f"object mode UV > Automatic from the Maya menu item ({res})", res == {'FINISHED'})
    rec = mod("ui.in_view").cb_record(bpy.context, ob)
    check(f"Channel Box INPUTS has {rec.name if rec else None} (Maya polyAutoProj1)",
          rec is not None and rec.name == "polyAutoProj1")
    open_inputs("polyAutoProj1")
    scroll_channel_box()


@step
def s_inputs_shot():
    shot("gui_step257_inputs.png")
    hist = bpy.context.window_manager.allset_history
    hist.percentage_space_text = "1"
    rec = mod("ui.in_view").cb_record(bpy.context, C["ob"])
    check("typing Percentage Space 1 in the Channel Box re-projects (node stays)",
          rec is not None and abs(rec.params["percentage_space"] - 1.0) < 1e-6)


@step
def s_keys():
    with override():
        bpy.ops.allset.create(kind='LOCATOR')
    loc = bpy.context.view_layer.objects.active
    C["loc"] = loc
    C["frames"] = [(1, 0.0), (12, 1.5), (24, 0.0)]


def _key_at(i):
    def f():
        frame, v = C["frames"][i]
        bpy.context.scene.frame_set(frame)
        C["loc"].location.z = v
        key('S')
    return f


for _i in range(3):
    step(_key_at(_i))


@step
def s_curve():
    compat = mod("compat")
    fc = next((fc for fc in compat.id_fcurves(C["loc"]) if fc.data_path == "location" and fc.array_index == 2), None)
    vals = {t: fc.evaluate(t) for t in (6.0, 18.0)} if fc else {}
    # Maya 2026: frame 6 = 0.648009, frame 18 = 0.75
    check(f"S keys follow Maya auto tangents {vals}",
          fc is not None and abs(vals[6.0] - 0.648009) < 2e-5 and abs(vals[18.0] - 0.75) < 2e-5)
    C["nkeys"] = len(fc.keyframe_points) if fc else 0
    C["loc_name"], C["name"] = C["loc"].name, C["ob"].name      # undo replaces the RNA objects
    key('Z', ctrl=True)


@step
def s_undo():
    loc = bpy.data.objects.get(C["loc_name"])
    fc = next((fc for fc in mod("compat").id_fcurves(loc) if fc.data_path == "location"
               and fc.array_index == 2), None) if loc is not None else None
    n = len(fc.keyframe_points) if fc else 0
    check(f"Ctrl+Z undoes the last key ({C['nkeys']} -> {n})", n < C["nkeys"])
    path = os.path.join(tempfile.mkdtemp(prefix="allset257_"), "chain.blend")
    C["path"] = path
    with override():
        bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
        bpy.ops.wm.open_mainfile(filepath=path)


@step
def s_reopen():
    ob = bpy.data.objects.get(C["name"])
    check(f"save / open keeps the bevelled mesh ({len(ob.data.vertices) if ob else None} vertices)",
          ob is not None and len(ob.data.vertices) == 82)
    shot("gui_step257_reopened.png")


run()
