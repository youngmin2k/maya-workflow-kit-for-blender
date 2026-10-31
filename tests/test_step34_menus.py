"""Maya menu dead ends filled — Windows editor submenus, UV Editor / Planar /
Normal-Based, Edit > Ungroup, Heads Up Display > Poly Count, File > Increment and Save,
File > Export Selection. GUI: tests/gui/gui_step34_menus.py."""

import os
import tempfile
from importlib import import_module

import bmesh
import bpy
from mathutils import Matrix, Vector

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")
extras = import_module(kit.MODULE + ".operators.menu_extras")

NEW_PATHS = {
    "File/Increment and Save": "allset.increment_save",
    "File/Export Selection...": "allset.file_export_selection",  # was a format submenu
    "Edit/Ungroup": "allset.ungroup",
    "Windows/Outliner": "allset.panel_show",   # raise a docked Outliner, else a floating one
    "Windows/Node Editor": "allset.open_editor",
    "Windows/General Editors/Attribute Editor": "allset.dock_show",
    "Windows/General Editors/Script Editor": "allset.script_editor",
    "Windows/Animation Editors/Graph Editor": "allset.open_editor",
    "Windows/Rendering Editors/Hypershade": "allset.hypershade",   # own window
    "UV/UV Editor": "allset.open_editor",
    "UV/Planar": "allset.uv_planar",
    "UV/Normal-Based": "allset.uv_planar",
    "Display/Heads Up Display/Poly Count": "wm.context_toggle",
}


def _exists(target):
    if "." not in target:
        return hasattr(bpy.types, target)
    mod, name = target.split(".")
    return hasattr(getattr(bpy.ops, mod), name)


def test_new_menu_items_are_mapped_paths():
    paths = {p for p, _it in menu_sets.iter_items()}
    for path, target in NEW_PATHS.items():
        assert path in paths, f"{path} is not a Maya menu path"
        spec = menu_map.spec(path)
        assert spec is not None and spec[1] == target, (path, spec)
        assert _exists(target), target
    # Every mapped run-time child exists as a path, and every MAP path is a real menu path.
    stale = [p for p in menu_map.MAP if p not in paths]
    assert not stale, stale


def test_runtime_submenus_are_menus():
    paths = dict(menu_sets.iter_items())
    for parent in menu_map.CHILDREN:
        kids = [p for p in paths if p.startswith(parent + "/")]
        assert kids, parent
    # The Windows menu draws "General Editors" as a submenu (not a greyed leaf).
    cls = getattr(bpy.types, menu_sets.menu_idname("mainWindowMenu"))
    calls = []

    class Fake:
        def menu(self, idname, text="", icon='NONE', icon_value=0, translate=True):     # menu icons
            calls.append(text)

        def operator(self, *a, **k):
            return type("P", (), {})()

        operator_menu_hold = operator

        def separator(self):
            pass

        def label(self, text="", translate=True):
            pass

        def row(self):     # section titles sit on a lower row
            return self

    cls.draw(type("M", (), {"layout": Fake()})(), bpy.context)
    for name in ("General Editors", "Modeling Editors", "Animation Editors", "Rendering Editors",
                 "Relationship Editors"):
        assert name in calls, (name, calls)


def test_increment_path_maya_rules():
    cases = {"MyFile.blend": "MyFile.0001.blend", "MyFile.01.blend": "MyFile.02.blend",
             "MyFile.99.blend": "MyFile.100.blend", "MyFile01.blend": "MyFile01.0001.blend",
             "MyFile.0043.blend": "MyFile.0044.blend", "MyFile.00a22.blend": "MyFile.00a22.0001.blend"}
    for src, want in cases.items():
        got = os.path.basename(extras.increment_path(os.path.join("C:/x", src)))
        assert got == want, (src, got, want)


def test_increment_save_keeps_original_and_skips_taken_numbers():
    folder = tempfile.mkdtemp(prefix="mk34_")
    first = os.path.join(folder, "shot.blend")
    bpy.ops.wm.save_as_mainfile(filepath=first)
    open(os.path.join(folder, "shot.0002.blend"), "wb").close()   # taken by someone else
    assert bpy.ops.allset.increment_save() == {'FINISHED'}
    assert os.path.basename(bpy.data.filepath) == "shot.0001.blend"
    assert os.path.exists(first) and os.path.exists(bpy.data.filepath)
    assert bpy.ops.allset.increment_save() == {'FINISHED'}
    assert os.path.basename(bpy.data.filepath) == "shot.0003.blend", "0002 exists: never overwritten"
    assert os.path.getsize(os.path.join(folder, "shot.0002.blend")) == 0


def _clear():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def test_ungroup_moves_children_up_keeping_world():
    _clear()
    top = bpy.data.objects.new("top", None)
    grp = bpy.data.objects.new("group1", None)
    a = bpy.data.objects.new("pCube1", bpy.data.meshes.new("m"))
    b = bpy.data.objects.new("pCube2", bpy.data.meshes.new("m2"))
    for ob in (top, grp, a, b):
        bpy.context.collection.objects.link(ob)
    top.matrix_world = Matrix.Translation((1, 2, 3)) @ Matrix.Rotation(0.4, 4, 'Z')
    grp.parent = top
    grp.matrix_basis = Matrix.Translation((0, 5, 0)) @ Matrix.Diagonal((2, 2, 2, 1))
    for ob, x in ((a, 1.0), (b, -1.0)):
        ob.parent = grp
        ob.matrix_basis = Matrix.Translation((x, 0, 0)) @ Matrix.Rotation(0.3, 4, 'X')
    bpy.context.view_layer.update()
    world = {ob.name: ob.matrix_world.copy() for ob in (a, b)}
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    grp.select_set(True)
    bpy.context.view_layer.objects.active = grp
    assert bpy.ops.allset.ungroup() == {'FINISHED'}
    bpy.context.view_layer.update()
    assert "group1" not in bpy.data.objects, "the group is deleted"
    for ob in (a, b):
        assert ob.parent == top, (ob.name, ob.parent)
        diff = max(abs(x - y) for r1, r2 in zip(ob.matrix_world, world[ob.name]) for x, y in zip(r1, r2))
        assert diff < 1e-5, (ob.name, diff)
        assert ob.select_get()
    # Ungroup at the top level: children go to the world.
    top.select_set(True)
    for ob in (a, b):
        ob.select_set(False)
    bpy.context.view_layer.objects.active = top
    bpy.ops.allset.ungroup()
    bpy.context.view_layer.update()
    assert a.parent is None and b.parent is None
    diff = max(abs(x - y) for r1, r2 in zip(a.matrix_world, world["pCube1"]) for x, y in zip(r1, r2))
    assert diff < 1e-5, diff


def test_uv_planar_projects_selected_faces():
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    top = max(bm.faces, key=lambda f: f.calc_center_median().z)
    top.select = True
    bmesh.update_edit_mesh(ob.data)
    assert bpy.ops.allset.uv_planar() == {'FINISHED'}
    bm = bmesh.from_edit_mesh(ob.data)
    layer = bm.loops.layers.uv.active
    top = max(bm.faces, key=lambda f: f.calc_center_median().z)
    uvs = sorted((round(lp[layer].uv.x, 4), round(lp[layer].uv.y, 4)) for lp in top.loops)
    assert uvs == [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)], uvs
    bpy.ops.object.mode_set(mode='OBJECT')
    # Aspect ratio kept: a 2x1 rectangle maps to 1 x 0.5.
    pts = [Vector(p) for p in ((0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0))]
    out = extras.planar_uvs(pts, (0, 0, 1))
    spans = (max(u for u, _v in out) - min(u for u, _v in out), max(v for _u, v in out) - min(v for _u, v in out))
    assert sorted(round(x, 4) for x in spans) == [0.5, 1.0], spans


def test_export_selection_menu_sets_selected_only():
    ops = []

    class Fake:
        operator_context = 'EXEC_DEFAULT'

        def operator(self, idname, text=""):
            p = type("P", (), {})()
            ops.append((idname, p))
            return p

    fake = Fake()
    bpy.types.ALLSET_MT_export_selection.draw(type("M", (), {"layout": fake})(), bpy.context)
    assert fake.operator_context == 'INVOKE_DEFAULT'
    names = [i for i, _p in ops]
    assert "export_scene.fbx" in names and "wm.obj_export" in names, names
    for idname, p in ops:
        prop = next(e[1] for e in extras.EXPORTERS if e[0] == idname)
        assert getattr(p, prop) is True, idname
