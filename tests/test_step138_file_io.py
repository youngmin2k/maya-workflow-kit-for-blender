"""#69: FBX / OBJ / Alembic / USD round trip the Maya way — no axis / unit conversion left on the channels,
Maya names (files in tmp/file_io138/: maya_cube138.*, kit_cube138*.*).

The reference object is pCube1: polyCube 1 x 1 x 1 at Maya translate (1, 2, 3), rotate Y 28.6, tx keyed 1 at
frame 1 and 5 at frame 10. The kit is Z up (Maya Y = Blender Z, Maya Z = Blender -Y), so in the
kit's Channel Box the same object reads Translate (1, -3, 2), Rotate (0, 0, 28.6), Scale 1 (in display units).
"""

import math
from importlib import import_module
from pathlib import Path

import bpy
from mathutils import Vector

import kit

file_io = import_module(kit.MODULE + ".operators.file_io")
units = import_module(kit.MODULE + ".operators.units")

ROOT = Path(__file__).resolve().parent.parent
IO = ROOT / "tmp" / "file_io138"
EXT = {'FBX': ".fbx", 'OBJ': ".obj", 'ABC': ".abc", 'USD': ".usd"}
RY = 28.6
KIT_T = (1.0, -3.0, 2.0)          # Maya (1, 2, 3) in the kit's Z-up axes


def _scene(cm=True):
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    us = sc.unit_settings
    if cm:
        us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    sc.frame_start, sc.frame_end = 1, 10
    sc.frame_set(1)
    return units.maya_unit(sc)


def _kit_cube(cm=True):
    k = _scene(cm)
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    ob.location = Vector(KIT_T) * k
    ob.rotation_euler = (0.0, 0.0, math.radians(RY))
    ob.keyframe_insert("location", index=0, frame=1)
    ob.location.x = 5 * k
    ob.keyframe_insert("location", index=0, frame=10)
    bpy.context.scene.frame_set(1)
    return ob, k


def describe(k):
    """The scene's objects as the kit's Channel Box shows them (display units, degrees) + world bbox at frame 1 and
    location x at frame 10."""
    sc = bpy.context.scene
    out = []
    sc.frame_set(1)
    for ob in sorted(sc.objects, key=lambda o: o.name):
        ent = {"name": ob.name, "type": ob.type, "data": ob.data.name if ob.data else None,
               "parent": ob.parent.name if ob.parent else None,
               "t": [round(v / k, 3) for v in ob.location], "r": [round(math.degrees(v), 3) for v in ob.rotation_euler],
               "s": [round(v, 3) for v in ob.scale], "dt": [round(v / k, 3) for v in ob.delta_location],
               "mat": [s.material.name for s in ob.material_slots if s.material],
               "anim": bool(ob.animation_data and ob.animation_data.action),
               "cons": [c.type for c in ob.constraints], "mods": [m.type for m in ob.modifiers]}
        if ob.type == 'MESH':
            pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
            ent["bbox"] = [[round(min(p[i] for p in pts) / k, 3) for i in range(3)],
                           [round(max(p[i] for p in pts) / k, 3) for i in range(3)]]
        out.append(ent)
    sc.frame_set(10)
    for ent in out:
        ob = sc.objects[ent["name"]]
        ent["tx10"] = round(ob.matrix_world.translation.x / k, 3)
    sc.frame_set(1)
    return out


def export_kit(fmt, suffix=""):
    path = IO / f"kit_cube138{suffix}{EXT[fmt]}"
    if path.exists():
        path.unlink()
    res = bpy.ops.allset.file_dialog('EXEC_DEFAULT', mode='EXPORT_ALL', export_type=fmt, filepath=str(path))
    assert res == {'FINISHED'} and path.exists(), (fmt, res)
    return path


def import_file(path, cm=True):
    k = _scene(cm)
    res = bpy.ops.allset.file_dialog('EXEC_DEFAULT', mode='IMPORT', import_type='AUTO', filepath=str(path))
    assert res == {'FINISHED'}, (path, res)
    return describe(k)


# --- assertions -----------------------------------------------------------------------------------

def _maya_channels(ent, fmt, label):
    """The kit Channel Box numbers of the Maya pCube1 (OBJ has no transforms: geometry only, like Maya's own
    OBJ round trip)."""
    if fmt == 'OBJ':
        want_t, want_r = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    else:
        want_t, want_r = KIT_T, (0.0, 0.0, RY)
    assert ent["type"] == 'MESH' and ent["name"] == "pCube1", (label, ent)
    assert ent["data"] == "pCubeShape1", (label, ent)
    assert all(abs(a - b) < 1e-3 for a, b in zip(ent["t"], want_t)), (label, "t", ent["t"])
    assert all(abs(a - b) < 1e-3 for a, b in zip(ent["r"], want_r)), (label, "r", ent["r"])
    assert all(abs(a - 1.0) < 1e-4 for a in ent["s"]), (label, "s", ent["s"])
    assert ent["bbox"] == [[0.322, -3.678, 1.5], [1.678, -2.322, 2.5]], (label, ent["bbox"])
    assert not ent["cons"], (label, ent["cons"])
    if fmt != 'OBJ':
        assert abs(ent["tx10"] - 5.0) < 1e-3, (label, "animation", ent["tx10"])


def test_kit_round_trip_keeps_maya_channels():
    """Kit -> file -> kit: channels, names, keys identical for every format, in the cm template scene and in a
    factory metre scene (1 Maya unit = 1 display unit there)."""
    IO.mkdir(parents=True, exist_ok=True)
    for cm, suffix in ((True, ""), (False, "_m")):
        for fmt in EXT:
            _kit_cube(cm)
            path = export_kit(fmt, suffix + "_t")
            obs = import_file(path, cm)
            assert len(obs) == 1, (fmt, cm, [o["name"] for o in obs])      # no root / env_light / scope nodes
            _maya_channels(obs[0], fmt, f"{fmt}{suffix}")


def test_obj_has_maya_group_lines():
    IO.mkdir(parents=True, exist_ok=True)
    _kit_cube()
    text = export_kit('OBJ', "_t").read_text()
    lines = [line for line in text.splitlines() if line[:2] in ("o ", "g ")]
    assert lines == ["o pCube1", "g pCube1"], lines          # Maya's OBJ reader names objects after g


def test_usd_stage_is_maya_shaped():
    from pxr import Usd, UsdGeom
    IO.mkdir(parents=True, exist_ok=True)
    _kit_cube()
    stage = Usd.Stage.Open(str(export_kit('USD', "_t")))
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.y
    assert abs(UsdGeom.GetStageMetersPerUnit(stage) - 0.01) < 1e-9
    tops = [p for p in stage.GetPseudoRoot().GetChildren() if p.GetTypeName() != "Scope"]
    assert [(p.GetName(), p.GetTypeName()) for p in tops] == [("pCube1", "Mesh")], tops
    ops = {op.GetOpName(): op for op in UsdGeom.Xformable(tops[0]).GetOrderedXformOps()}
    assert all(abs(a - b) < 1e-4 for a, b in zip(ops["xformOp:translate"].Get(1), (1, 2, 3)))
    assert all(abs(a - b) < 1e-3 for a, b in zip(ops["xformOp:rotateXYZ"].Get(1), (0, RY, 0)))
    assert all(abs(a - 1) < 1e-5 for a in ops["xformOp:scale"].Get(1))
    assert abs(ops["xformOp:translate"].Get(10)[0] - 5) < 1e-4               # keys kept
    pts = UsdGeom.Mesh(tops[0]).GetPointsAttr().Get()
    assert abs(max(max(abs(c) for c in p) for p in pts) - 0.5) < 1e-6        # polyCube 1 x 1 x 1, Maya units


def test_abc_export_leaves_the_scene_as_it_was():
    IO.mkdir(parents=True, exist_ok=True)
    ob, k = _kit_cube()
    child = bpy.data.objects.new("pCube2", bpy.data.meshes.new("pCubeShape2"))
    bpy.context.scene.collection.objects.link(child)
    child.parent = ob
    child.matrix_parent_inverse = ob.matrix_world.inverted()

    def state():
        return [(o.name, tuple(o.delta_scale), [tuple(r) for r in o.matrix_parent_inverse], len(o.modifiers))
                for o in bpy.context.scene.objects]
    before, groups = state(), len(bpy.data.node_groups)
    export_kit('ABC', "_t")
    assert state() == before and len(bpy.data.node_groups) == groups, (before, state())


def test_hierarchy_round_trip():
    """A child under a moved / turned parent keeps its local channels through FBX / ABC / USD (the
    conjugation must hold below the root too)."""
    IO.mkdir(parents=True, exist_ok=True)
    for fmt in ('FBX', 'ABC', 'USD'):
        ob, k = _kit_cube()
        ob.animation_data_clear()
        grp = bpy.data.objects.new("group1", None)
        bpy.context.scene.collection.objects.link(grp)
        grp.location = Vector((0, 0, 4)) * k
        grp.rotation_euler = (0, 0, math.radians(30))
        ob.parent = grp                       # Maya way: parent inverse identity, local channels
        ob.matrix_parent_inverse.identity()
        ob.location = Vector(KIT_T) * k
        obs = {o["name"]: o for o in import_file(export_kit(fmt, "_h"))}
        assert set(obs) == {"group1", "pCube1"}, (fmt, list(obs))
        cube, g = obs["pCube1"], obs["group1"]
        assert cube["parent"] == "group1", (fmt, cube)
        assert all(abs(a - b) < 1e-3 for a, b in zip(cube["t"], KIT_T)), (fmt, cube["t"])
        assert abs(cube["r"][2] - RY) < 1e-3 and all(abs(v - 1) < 1e-4 for v in cube["s"]), (fmt, cube)
        assert all(abs(a - b) < 1e-3 for a, b in zip(g["t"], (0, 0, 4))) and abs(g["r"][2] - 30) < 1e-3, (fmt, g)
        assert all(abs(v - 1) < 1e-4 for v in g["s"]), (fmt, g)


def test_maya_names():
    assert file_io.shape_name("pCube1") == "pCubeShape1" and file_io.shape_name("box") == "boxShape"
    used = {"pCube1", "pCube2", "lambert1"}
    assert file_io.maya_free_name("pCube1.001", used) == "pCube3"
    assert file_io.maya_free_name("lambert1.001", used) == "lambert2"
    assert file_io.maya_free_name("pSphere1.001", used) == "pSphere1"
    assert file_io.maya_free_name("Looks", {"Looks"}) == "Looks1"


def test_presets():
    k = 0.01
    a = file_io.export_args('FBX', k, False)[1]
    assert a["bake_space_transform"] and not a["bake_anim_use_nla_strips"] and not a["bake_anim_use_all_actions"]
    a = file_io.export_args('USD', k, False)[1]
    assert a["root_prim_path"] == "" and a["merge_parent_xform"] and not a["convert_world_material"]
    a = file_io.import_args('FBX', k)[1]
    assert a["bake_space_transform"] and a["anim_offset"] == 0.0
    assert file_io.import_args('OBJ', k)[1]["use_split_groups"]
    assert file_io.import_args('FBX', k, maya=False) == ("import_scene.fbx", {})


