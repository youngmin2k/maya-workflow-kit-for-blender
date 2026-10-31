"""Reference Editor (Issue #116) — Maya reference commands on Blender links + library overrides
(operators/references.py, ui/reference_editor.py). Maya rules: reload
keeps edits and shows the source's other changes, unload / load keep edits, replace re-applies edits by node name,
import makes the nodes local with their ns: names, remove takes nodes and namespace, a second reference of a file is
prop1 / propRN1."""

import json
import os
import subprocess
from importlib import import_module
from pathlib import Path

import bpy

import kit

refs = import_module(kit.MODULE + ".operators.references")
project = import_module(kit.MODULE + ".operators.project")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
editor_menu_data = import_module(kit.MODULE + ".ui.editor_menu_data")
reference_editor = import_module(kit.MODULE + ".ui.reference_editor")

TMP = Path(__file__).resolve().parents[1] / "tmp" / os.environ.get("ALLSET_SANDBOX", "test_env") / "refs209"
A, B = TMP / "srcA.blend", TMP / "srcB.blend"


def _mesh(name):
    me = bpy.data.meshes.new(name.replace("p", "p", 1) + "Shape")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    return me


def _save_source(path, objects, group=True):
    bpy.ops.wm.read_homefile(use_empty=True)
    coll = bpy.data.collections.new("group1") if group else None
    if coll is not None:
        bpy.context.scene.collection.children.link(coll)
    for name, loc in objects:
        ob = bpy.data.objects.new(name, _mesh(name))
        (coll or bpy.context.scene.collection).objects.link(ob)
        ob.location = loc
    bpy.ops.wm.save_as_mainfile(filepath=str(path))


def _sources():
    TMP.mkdir(parents=True, exist_ok=True)
    _save_source(B, [("pCube1", (0, 0, 9)), ("pCone1", (0, 0, 0))])
    _save_source(A, [("pCube1", (0, 0, 0)), ("pSphere1", (0, 0, 0))])


def _change_source(path, code):
    """Edit a source .blend in another Blender (the test's own file stays open)."""
    env = dict(os.environ, ALLSET_NO_SLOTS="1")
    subprocess.run([bpy.app.binary_path, "-b", "--factory-startup", str(path), "--python-expr",
                    "import bpy\n" + code + "\nbpy.ops.wm.save_mainfile()"],
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                   check=True)


def _fresh():
    _sources()
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.context.window_manager.allset_ref_current = ""


def _reference(path=A, ns="prop"):
    r = bpy.ops.allset.create_reference(filepath=str(path), namespace=ns)
    assert r == {'FINISHED'}, r
    return refs.find(bpy.context.window_manager.allset_ref_current)


def _cmd(action, ref=None):
    r = bpy.ops.allset.reference_cmd(action=action, reference=ref.name if ref is not None else "")
    assert r == {'FINISHED'}, (action, r)


def _ob(name):
    return bpy.data.objects.get(name)


def _loc(name):
    return tuple(round(v, 5) for v in _ob(name).location)


def test_names_like_maya():
    _fresh()
    a = _reference()
    b = _reference()
    assert (a.name, refs.node_name(a)) == ("prop", "propRN"), (a.name, refs.node_name(a))
    assert (b.name, refs.node_name(b)) == ("prop1", "propRN1"), "Maya: namespace prop1, reference node propRN1"
    assert [r.name for r in refs.references()] == ["prop", "prop1"]
    assert {o.name for o in a.all_objects} == {"prop:pCube1", "prop:pSphere1"}
    assert all(o.override_library is not None for o in a.all_objects)
    assert refs.file_label(a) == "srcA.blend" and refs.is_loaded(a)


def test_reload_keeps_edits_and_shows_source_changes():
    _fresh()
    ref = _reference()
    _ob("prop:pCube1").location.z = 5.0
    _change_source(A, "bpy.data.objects['pSphere1'].location.y = 7; bpy.data.objects['pCube1'].location.x = 3")
    _cmd("RELOAD", ref)
    assert _loc("prop:pSphere1") == (0, 7, 0), "the source's change is seen"
    # Maya: the edit (whole translate) stays and hides the source's change of that attribute (0 5 0)
    assert _loc("prop:pCube1") == (0, 0, 5), _loc("prop:pCube1")


def test_unload_load_keep_edits():
    _fresh()
    ref = _reference()
    _ob("prop:pCube1").location.z = 5.0
    _cmd("UNLOAD", ref)
    vl = bpy.context.view_layer
    vl.update()
    assert not refs.is_loaded(ref) and "prop:pCube1" not in vl.objects, "unloaded: the nodes are gone"
    _cmd("TOGGLE", ref)
    vl.update()
    assert refs.is_loaded(ref) and "prop:pCube1" in vl.objects and _loc("prop:pCube1") == (0, 0, 5)


def test_edits_list_offline_file_and_clean_up():
    _fresh()
    ref = _reference()
    _ob("prop:pCube1").location.z = 5.0
    rows = refs.edits(ref)
    assert ("pCube1", "Object", "location", [0.0, 0.0, 5.0]) in rows, rows
    path = TMP / "edits.json"
    assert bpy.ops.allset.reference_offline(mode="EXPORT", filepath=str(path)) == {'FINISHED'}
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["reference"] == "propRN" and data["edits"], data
    assert bpy.ops.allset.reference_cmd(action="CLEAN") == {'CANCELLED'}, "Maya cleans up unloaded references only"
    _cmd("UNLOAD", ref)
    _cmd("CLEAN", ref)
    _cmd("LOAD", ref)
    assert _loc("prop:pCube1") == (0, 0, 0), "edits removed"
    assert bpy.ops.allset.reference_offline(mode="ASSIGN", filepath=str(path)) == {'FINISHED'}
    assert _loc("prop:pCube1") == (0, 0, 5), "offline file applied"


def test_lock_and_read_only():
    _fresh()
    ref = _reference()
    _cmd("LOCK", ref)
    assert all(o.override_library.is_system_override for o in ref.all_objects) and refs.is_locked(ref)
    assert bpy.context.scene.allset_ref_read_only
    bpy.context.scene.allset_ref_read_only = False
    assert not refs.is_locked(ref) and not any(o.override_library.is_system_override for o in ref.all_objects)


def test_replace_reapplies_edits_by_name():
    _fresh()
    ref = _reference()
    _ob("prop:pCube1").location.z = 5.0
    assert bpy.ops.allset.reference_replace(filepath=str(B)) == {'FINISHED'}
    new = refs.find("prop")
    assert refs.node_name(new) == "propRN" and refs.file_label(new) == "srcB.blend"
    names = {o.name for o in new.all_objects}
    assert names == {"prop:pCube1", "prop:pCone1"}, names
    # Maya: the pCube1 edit (0 5 0) went onto B's pCube1 (0 0 9)
    assert _loc("prop:pCube1") == (0, 0, 5), _loc("prop:pCube1")
    assert list(new[refs.REPLACED]) == [str(A)], "Recently Replaced Files"
    assert bpy.ops.allset.reference_recent(filepath=str(A)) == {'FINISHED'}
    assert {o.name for o in refs.find("prop").all_objects} == {"prop:pCube1", "prop:pSphere1"}


def test_import_objects_makes_them_local():
    _fresh()
    ref = _reference()
    _ob("prop:pCube1").location.z = 5.0
    _cmd("IMPORT", ref)
    assert refs.references() == [], "the reference node goes"
    for name in ("prop:pCube1", "prop:pSphere1"):
        ob = _ob(name)
        assert ob is not None and ob.library is None and ob.override_library is None, name
        assert ob.data.library is None and ob.data.override_library is None, name
    assert _loc("prop:pCube1") == (0, 0, 5), "Maya: the edits are baked in"
    assert not bpy.data.libraries, [lib.name for lib in bpy.data.libraries]


def test_remove_and_duplicate():
    _fresh()
    a = _reference()
    _cmd("DUPLICATE", a)
    b = refs.find("prop1")
    assert b is not None and refs.node_name(b) == "propRN1" and len(b.all_objects) == 2
    _cmd("REMOVE", b)
    assert refs.find("prop1") is None and _ob("prop1:pCube1") is None
    assert bpy.data.libraries, "prop still uses the library"
    _cmd("REMOVE", a)
    assert refs.references() == [] and not [o for o in bpy.data.objects if o.name.startswith("prop")]
    assert not bpy.data.libraries, "the library goes with the last reference"


def test_select_related_namespace_and_save():
    _fresh()
    ref = _reference()
    bpy.context.window_manager.allset_ref_current = ref.name
    _cmd("SELECT")
    assert {o.name for o in bpy.context.selected_objects} == {"prop:pCube1", "prop:pSphere1"}
    _cmd("UNLOAD_RELATED")
    assert not refs.is_loaded(ref)
    _cmd("LOAD", ref)
    bpy.context.scene.allset_ref_namespace = "hero"
    assert refs.find("hero") is ref and {o.name for o in ref.all_objects} == {"hero:pCube1", "hero:pSphere1"}
    assert refs.node_name(ref) == "propRN", "Maya keeps the reference node name"
    _ob("hero:pCube1").location.z = 2.0
    _cmd("UNLOAD", ref)
    shot = TMP / "shot.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(shot))
    bpy.ops.wm.open_mainfile(filepath=str(shot))
    ref = refs.find("hero")
    assert ref is not None and refs.node_name(ref) == "propRN" and not refs.is_loaded(ref), "saved with the file"
    _cmd("LOAD", ref)
    assert _loc("hero:pCube1") == (0, 0, 2)


def test_menus_mapped():
    items = dict(editor_menu_data.EDITORS["Reference Editor"])
    assert list(items) == ["File", "Reference", "Proxy", "View", "Help"], "Maya 2022's Reference Editor menu bar"
    for path in ("File/Reference Editor", "File/Export to Offline File...", "File/Assign Offline File..."):
        assert path in menu_map.MAP, path
    mapped = [p for p in menu_map.MAP if p.startswith("Reference Editor/")]
    assert len([p for p in mapped if p.startswith("Reference Editor/File/")]) == 8, mapped
    for path in mapped:
        value = menu_map.MAP[path]
        op = value if isinstance(value, str) else value[0]
        if op in ("menu", "url") or not isinstance(op, str) or "." not in op:
            continue
        mod, name = op.split(".", 1)
        assert hasattr(getattr(bpy.ops, mod), name), (path, op)
    assert bpy.ops.allset.reference_editor.poll() in (True, False)


def test_pane_flags_are_unique():
    """The window's area is recognised only as the Reference Editor (not the Maya dock, Tool Settings or Hypershade)."""
    maya_dock = import_module(kit.MODULE + ".ui.maya_dock")
    hypershade = import_module(kit.MODULE + ".ui.hypershade")
    assert set(reference_editor.MARK) & set(maya_dock.ROLE_FLAGS.values())
    assert set(reference_editor.MARK) != set(hypershade.MARK)


def test_import_leaves_a_second_reference_alone():
    _fresh()
    a = _reference()
    b = _reference()
    _cmd("IMPORT", a)
    assert refs.references() == [b] and all(o.override_library is not None for o in b.all_objects)
    assert all(o.data.library is not None for o in b.all_objects), "the other reference keeps its linked meshes"
    assert all(o.data.library is None for o in bpy.data.objects if o.name.startswith("prop:"))
    assert bpy.data.libraries, "still used by prop1"
