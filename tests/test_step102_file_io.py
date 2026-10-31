"""Maya file I/O — one file dialog with Files of type, Maya cm / Y-up presets, default project, round trip
with Maya. GUI:
tests/gui/gui_step102_file_dialog.py.

The round trip writes tmp/file_io/kit_cube.* and reads tmp/file_io/maya_cube.* when those files exist
(skipped otherwise)."""

import os
from importlib import import_module
from pathlib import Path

import bpy
from mathutils import Vector

import kit

file_io = import_module(kit.MODULE + ".operators.file_io")
project = import_module(kit.MODULE + ".operators.project")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_data = import_module(kit.MODULE + ".ui.menu_data")

ROOT = Path(__file__).resolve().parent.parent
# per sandbox: version runs in parallel must not share the exported files
IO = ROOT / "tmp" / os.environ.get("ALLSET_SANDBOX", "test_env") / "file_io"
# pCube1 for the round trip: 10 x 20 x 5 Maya units (cm), the 20 along Maya's up axis.
SIZE = (10.0, 20.0, 5.0)


def _cm_scene():
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0   # the Maya Workflow Kit template's units


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def _bbox(obs):
    pts = [ob.matrix_world @ Vector(c) for ob in obs if ob.type == 'MESH' for c in ob.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return hi - lo


def _cube():
    """pCube1 in a cm scene: X 10, Blender Z (up) 20, Blender Y 5 Maya units."""
    _clear()
    _cm_scene()
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    k = 0.01
    ob.scale = (SIZE[0], SIZE[2], SIZE[1])            # the cube is 1 unit; Maya Y (20) = Blender Z
    bpy.ops.object.transform_apply(scale=True)
    assert abs(_bbox([ob]).x - SIZE[0] * k) < 1e-6
    return ob


# --- presets ------------------------------------------------------------------------------------

def test_presets_cm_y_up():
    k = 0.01          # Maya Workflow Kit template: one Maya unit (cm) = 0.01 BU
    op, a = file_io.export_args('OBJ', k, False)
    assert op == "wm.obj_export" and abs(a["global_scale"] - 100) < 1e-9 and a["up_axis"] == 'Y'
    op, a = file_io.import_args('OBJ', k)
    assert op == "wm.obj_import" and abs(a["global_scale"] - k) < 1e-12 and a["up_axis"] == 'Y'
    op, a = file_io.export_args('ABC', k, True)
    assert a["selected"] and abs(a["global_scale"] - 100) < 1e-9
    assert abs(file_io.import_args('ABC', k)[1]["scale"] - k) < 1e-12
    op, a = file_io.export_args('FBX', k, True)
    assert a["use_selection"] and a["axis_up"] == 'Y' and a["apply_unit_scale"]
    op, a = file_io.export_args('USD', k, False)
    # Y up / Maya units are written by file_io.usd_maya_axes after Blender's writer (no root prim)
    assert a["root_prim_path"] == "" and not a.get("convert_orientation")
    assert abs(file_io.import_args('USD', k)[1]["scale"] - 1.0) < 1e-12
    # Maya Units option (1 BU = 1 cm): OBJ / ABC numbers pass straight
    assert file_io.export_args('OBJ', 1.0, False)[1]["global_scale"] == 1.0
    # presets off: Blender's own defaults, selection still honoured
    assert file_io.export_args('OBJ', k, True, maya=False) == ("wm.obj_export", {"export_selected_objects": True})
    for fmt, *_ in file_io.FORMATS:
        if fmt == 'BLEND':
            continue
        for op, args in (file_io.import_args(fmt, k), file_io.export_args(fmt, k, True)):
            mod, name = op.split(".")
            rna = getattr(getattr(bpy.ops, mod), name).get_rna_type()
            missing = [key for key in args if key not in rna.properties]
            assert not missing, (op, missing)


def test_format_by_extension_and_files_of_type():
    assert file_io.format_of("a/b.FBX") == 'FBX' and file_io.format_of("x.usdz") == 'USD'
    assert file_io.format_of("scene.blend") == 'BLEND' and file_io.format_of("scene.ma") == ""
    labels = [f[1] for f in file_io.FORMATS]
    assert labels[0].startswith("Maya Scenes") and any("Alembic" in l for l in labels)
    assert file_io.IMPORT_TYPES[0][0] == 'AUTO'


def test_file_menu_runs_the_dialog_and_option_boxes_are_live():
    for path, op in (("File/Import...", "file_import"), ("File/Export All...", "file_export_all"),
                     ("File/Export Selection...", "file_export_selection")):
        assert menu_map.spec(path) == ("op", "allset." + op, {}), path
        assert getattr(bpy.ops.allset, op).get_rna_type().name in ("Import", "Export All", "Export Selection")
        assert path in menu_data.OPTION_BOXES
    # an operator with option_box gets the option box itself (marking/modal.run_action): no dead box icon
    for op in ("file_import", "file_export_all", "file_export_selection", "open_scene", "save_scene_as"):
        assert "option_box" in getattr(bpy.ops.allset, op).get_rna_type().properties, op


# --- default project ----------------------------------------------------------------------------

def test_default_project_like_maya():
    prefs = bpy.context.preferences.addons[kit.MODULE].preferences
    prefs.project_root = ""
    root = project.current_root()
    assert os.path.basename(root) == "default", root
    assert os.path.normcase(root).startswith(os.path.normcase(os.environ["ALLSET_PROJECTS_DIR"])), root
    scenes = project.scenes_dir()
    assert os.path.isdir(scenes) and project.is_project(root)      # made on first use, Maya's folders
    assert project.open_path() == os.path.join(scenes, "")
    assert os.path.isdir(os.path.join(root, "sourceimages"))


# --- round trip ---------------------------------------------------------------------------------

def _export(fmt, mode='EXPORT_ALL'):
    path = IO / f"kit_cube{file_io._BY_ID[fmt][2]}"
    res = bpy.ops.allset.file_dialog('EXEC_DEFAULT', mode=mode, export_type=fmt, filepath=str(path))
    assert res == {'FINISHED'} and path.exists(), (fmt, res)
    return path


def _import(path):
    _clear()
    _cm_scene()
    before = set(bpy.data.objects)
    res = bpy.ops.allset.file_dialog('EXEC_DEFAULT', mode='IMPORT', import_type='AUTO', filepath=str(path))
    assert res == {'FINISHED'}, (path, res)
    return [ob for ob in bpy.data.objects if ob not in before]


def test_round_trip_in_blender():
    IO.mkdir(parents=True, exist_ok=True)
    for fmt in ('FBX', 'OBJ', 'ABC', 'USD', 'BLEND'):
        ob = _cube()
        ob.select_set(True)
        path = _export(fmt, 'EXPORT_SELECTION' if fmt != 'BLEND' else 'EXPORT_ALL')
        size = _bbox(_import(path))
        want = Vector((SIZE[0], SIZE[2], SIZE[1])) * 0.01
        assert (size - want).length < 1e-4, (fmt, tuple(size), tuple(want))


def test_obj_numbers_are_maya_cm_y_up():
    """OBJ is text: the file must hold Maya's numbers (cm) with Y up (20 along Y)."""
    ob = _cube()
    ob.select_set(True)
    path = _export('OBJ', 'EXPORT_SELECTION')
    verts = [tuple(map(float, line.split()[1:4])) for line in path.read_text().splitlines() if line.startswith("v ")]
    span = [max(v[i] for v in verts) - min(v[i] for v in verts) for i in range(3)]
    assert all(abs(a - b) < 1e-4 for a, b in zip(span, SIZE)), span


def test_export_selection_writes_only_the_selection():
    ob = _cube()
    other = bpy.data.objects.new("other", bpy.data.meshes.new("otherShape"))
    bpy.context.scene.collection.objects.link(other)
    for o in bpy.context.scene.objects:
        o.select_set(o is ob)
    path = _export('OBJ', 'EXPORT_SELECTION')
    assert "other" not in path.read_text()
    for o in bpy.context.scene.objects:
        o.select_set(False)
    assert bpy.ops.allset.file_dialog('EXEC_DEFAULT', mode='EXPORT_SELECTION', export_type='OBJ',
                                        filepath=str(path)) == {'CANCELLED'}


