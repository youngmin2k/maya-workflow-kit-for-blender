"""Blender 5.x compatibility — every version difference goes through src/allset/compat.py.
Runs on every Blender the suite runs on; each check holds on 5.0-5.2 (4.5 dropped)."""

import re
from importlib import import_module
from pathlib import Path

import bmesh
import bpy

import kit

ROOT = Path(__file__).resolve().parent.parent
compat = import_module(kit.MODULE + ".compat")
driven_key = import_module(kit.MODULE + ".operators.driven_key")
maya_dock = import_module(kit.MODULE + ".ui.maya_dock")


def test_version_checks_only_in_compat():
    """No feature module asks for bpy.app.version: the one place is compat.py."""
    bad = []
    for path in (ROOT / "src" / "allset").rglob("*.py"):
        if path.name == "compat.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"bpy\.app\.version\b(?!_string)", code):
                bad.append(f"{path.relative_to(ROOT)}:{n}")
    assert not bad, bad
    assert compat.IS_TARGET == (tuple(bpy.app.version[:2]) == (5, 2))      # main target
    assert compat.IS_STRICT == (tuple(bpy.app.version[:2]) == (5, 2))
    assert compat.STRICT_VERSIONS == ((5, 2),) and compat.VERSION >= (5, 0)


def test_action_fcurves_on_layered_actions():
    ob = bpy.data.objects.new("c118", None)
    bpy.context.scene.collection.objects.link(ob)
    ob.keyframe_insert("location", index=0, frame=1)
    ob.keyframe_insert("location", index=2, frame=5)
    fcs = compat.id_fcurve_collection(ob)
    assert fcs is not None and fcs.find("location", index=2) is not None
    assert sorted(fc.array_index for fc in compat.id_fcurves(ob)) == [0, 2]
    assert len(compat.action_fcurves(ob.animation_data.action)) == 2
    assert all(hasattr(o, "fcurves") for o in compat.fcurve_owners(ob.animation_data.action))
    bpy.data.objects.remove(ob)


def test_new_sdk_driver_curve_is_empty_and_constant():
    """5.x gives a new driver curve two keys (0,0) (1,1) and LINEAR extrapolation; the kit clears them."""
    a = bpy.data.objects.new("a118", None)
    b = bpy.data.objects.new("b118", None)
    for ob in (a, b):
        bpy.context.scene.collection.objects.link(ob)
    fc = driven_key.ensure_driver(b, "ry", a, "tx")
    assert len(fc.keyframe_points) == 0 and not fc.modifiers and fc.extrapolation == 'CONSTANT'
    for ob in (a, b):
        bpy.data.objects.remove(ob)


def test_uv_island_mode_round_trip():
    ts = bpy.context.scene.tool_settings
    compat.set_uv_island_mode(ts, True)
    assert compat.uv_island_mode(ts)
    compat.set_uv_island_mode(ts, False)
    assert not compat.uv_island_mode(ts) and ts.uv_select_mode == 'VERTEX'


def test_video_and_image_formats():
    im = bpy.context.scene.render.image_settings
    compat.set_file_format(im, 'FFMPEG')
    assert im.file_format == 'FFMPEG'
    compat.set_file_format(im, 'PNG')
    assert im.file_format == 'PNG'


def test_pointmerge_facedata_and_strips():
    bm = bmesh.new()
    vs = [bm.verts.new((x, 0, 0)) for x in range(3)]
    bm.faces.new(vs)
    compat.pointmerge_facedata(bm, [vs[0], vs[1]], vs[0])
    bm.free()
    sc = bpy.context.scene
    if sc.sequence_editor is None:
        sc.sequence_editor_create()
    assert len(compat.strips(sc.sequence_editor)) == 0


def test_dock_role_ignores_newer_properties_tabs():
    """The Maya Workflow Kit template is still saved by 4.5: 5.x opens its dock with the newer strip tabs on."""
    assert compat.LATER_PROPERTIES_TABS.isdisjoint(set(maya_dock.ROLE_FLAGS.values()) | {"show_properties_tool"})
    names = {p.identifier for p in bpy.types.SpaceProperties.bl_rna.properties}
    assert compat.LATER_PROPERTIES_TABS <= names


def test_uv_selection_reads_without_sync():
    """5.x keeps the UV selection on the loop (uv_select_vert)."""
    uv_tools = import_module(kit.MODULE + ".operators.uv_tools")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    uv = bm.loops.layers.uv.new()
    for f in bm.faces:
        f.select = True
    faces = uv_tools.selected_faces(bm, uv, False)
    edges = uv_tools.selected_edges(bm, uv, False)
    assert isinstance(faces, list) and isinstance(edges, list)
    assert all(isinstance(compat.uv_vert_selected(l, uv), bool) for f in bm.faces for l in f.loops)
    bm.free()
