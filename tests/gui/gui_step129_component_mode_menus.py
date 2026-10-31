"""#39, #17, #18: , from the audit 128 repro: Edit / Select / Modify menu items a Maya user clicks in
component mode, run through the real menu button operator (allset.menu_item, as a click does), and Ctrl+D typed in
face mode. Expected (Maya behaviour): Select > All / Inverse
act on the faces, Deselect All clears and goes to object mode, Edit > Delete deletes the face, Group makes an empty
group null1, Freeze / Delete History leave everything alone, Duplicate (menu and Ctrl+D) copies nothing."""

import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, setup, step, view3d, win  # noqa: E402

C = {}


def ov(fn, *a, **kw):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return fn(*a, **kw)


def sel_faces():
    ob = bpy.context.edit_object
    return sum(1 for f in bmesh.from_edit_mesh(ob.data).faces if f.select) if ob else -1


def n_faces():
    ob = bpy.context.edit_object or bpy.context.active_object
    if ob.mode == 'EDIT':
        return len(bmesh.from_edit_mesh(ob.data).faces)
    return len(ob.data.polygons)


def edit_one_face():
    if bpy.context.mode != 'OBJECT':
        ov(bpy.ops.object.mode_set, mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    ov(bpy.ops.allset.create, kind='CUBE')
    ov(bpy.ops.object.mode_set, mode='EDIT')
    ov(bpy.ops.mesh.select_mode, type='FACE')
    ov(bpy.ops.mesh.select_all, action='DESELECT')
    ob = bpy.context.edit_object
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    bm.faces[0].select_set(True)
    bmesh.update_edit_mesh(ob.data)


def item(path):
    try:
        res = ov(bpy.ops.allset.menu_item, item=path)
    except Exception as ex:
        res = repr(ex)
    print("STEP129", path, res)
    return res


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)


@step
def s_select():
    edit_one_face()
    item("Select/All")
    check(f"component mode: Select > All selects every face (1 -> {sel_faces()} of 6)", sel_faces() == 6)
    edit_one_face()
    item("Select/Inverse")
    check(f"component mode: Select > Inverse selects the other 5 faces ({sel_faces()})", sel_faces() == 5)
    edit_one_face()
    item("Select/Deselect All")
    check(f"component mode: Select > Deselect All clears and goes to object mode ({bpy.context.mode})",
          bpy.context.mode == 'OBJECT' and not bpy.context.selected_objects)


@step
def s_delete():
    edit_one_face()
    item("Edit/Delete")
    check(f"component mode: Edit > Delete deletes the selected face (6 -> {n_faces()})", n_faces() == 5)


@step
def s_group():
    edit_one_face()
    before = set(bpy.data.objects.keys())
    item("Edit/Group")
    new = set(bpy.data.objects.keys()) - before
    check(f"component mode: Edit > Group makes Maya's empty group (new {sorted(new)}, mode {bpy.context.mode})",
          len(new) == 1 and next(iter(new)).startswith("null") and bpy.context.mode == 'OBJECT')
    edit_one_face()
    ob = bpy.context.edit_object
    ob.location.x = 0.05
    res = item("Modify/Freeze Transformations")
    check(f"component mode: Freeze Transformations leaves Translate X like Maya ({ob.location.x:.3f}, {res})",
          abs(ob.location.x - 0.05) < 1e-6 and bpy.context.mode == 'EDIT_MESH')
    edit_one_face()
    n = len(bpy.data.objects)
    res = item("Edit/Duplicate")
    check(f"component mode: Edit > Duplicate copies nothing (Maya: No object(s) to duplicate) ({res})",
          len(bpy.data.objects) == n and n_faces() == 6)
    edit_one_face()
    C["n_obj"] = len(bpy.data.objects)
    _area, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    ev('D', 'PRESS', ctrl=True)
    ev('D', 'RELEASE', ctrl=True)


@step
def s_ctrl_d():
    modals = [op.bl_idname for op in win().modal_operators]
    check(f"Ctrl+D in face mode: no face copy, no move, no new object (objects {C['n_obj']} -> "
          f"{len(bpy.data.objects)}, faces {n_faces()}, modals {modals})",
          # PR #125's window watchers (joint Outliner select, pose empty click) are always running: only a transform
          # modal would be a move
          len(bpy.data.objects) == C["n_obj"] and n_faces() == 6 and not [m for m in modals if m.startswith("TRANSFORM_OT")])


run()
