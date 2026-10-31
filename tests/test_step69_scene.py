"""Maya projects (Set Project / Project Window / Recent Projects), file dialogs in the project's scenes folder,
render output to images, Ctrl+Alt+S = Maya Increment and Save, Create Reference (Ctrl+R) with namespaces, Reference
Editor. GUI: tests/gui/gui_step69_scene.py."""

import os
import tempfile
from importlib import import_module

import bpy

import kit

project = import_module(kit.MODULE + ".operators.project")
menu_extras = import_module(kit.MODULE + ".operators.menu_extras")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
patches = import_module(kit.MODULE + ".keymap.maya_patches")
mapping = import_module(kit.MODULE + ".keymap.mapping")
preferences = import_module(kit.MODULE + ".preferences")


def _prefs():
    return preferences.get()


def _reset_prefs():
    p = _prefs()
    p.project_root = ""
    p.recent_projects = ""


def _cancelled(call):
    """An operator that reports an ERROR raises in Python; True when it refused."""
    try:
        return call() == {'CANCELLED'}
    except RuntimeError:
        return True


def _new_project(name="proj"):
    folder = tempfile.mkdtemp(prefix="mk69_")
    root = os.path.join(folder, name)
    os.makedirs(root)
    return folder, root


# --- project ---------------------------------------------------------------------------------------

def test_project_window_creates_maya_folders():
    _reset_prefs()
    folder, _root = _new_project("unused")
    assert bpy.ops.allset.project_window(name="shotA", location=folder) == {'FINISHED'}
    root = os.path.join(folder, "shotA")
    for sub in ("scenes", "sourceimages", "images", "renderData", "assets", "data", "cache"):
        assert os.path.isdir(os.path.join(root, sub)), sub
    assert project.is_project(root)
    assert os.path.normcase(project.current_root()) == os.path.normcase(root)
    assert project.recent()[0] == root
    # paths for the file dialogs
    scenes = os.path.join(root, "scenes")
    assert project.open_path() == os.path.join(scenes, "")
    assert project.save_as_path() == os.path.join(scenes, "untitled.blend")
    assert project.NOTICE.startswith("Blender has no project system")


def test_set_project_and_recent():
    _reset_prefs()
    _f1, a = _new_project("a")
    _f2, b = _new_project("b")
    assert bpy.ops.allset.set_project(directory=a, create_folders=False) == {'FINISHED'}
    assert not project.is_project(a), "an unmarked folder stays as it is when not asked to create folders"
    assert bpy.ops.allset.set_project(directory=b) == {'FINISHED'}
    assert project.is_project(b) and os.path.isdir(os.path.join(b, "scenes"))
    assert project.recent()[:2] == [b, a]
    assert bpy.ops.allset.project_recent(path=a) == {'FINISHED'}
    assert project.recent()[:2] == [a, b] and os.path.normcase(project.current_root()) == os.path.normcase(a)
    assert _cancelled(lambda: bpy.ops.allset.set_project(directory=os.path.join(b, "missing")))


def test_save_in_project_renders_to_images_and_detects_project():
    _reset_prefs()
    folder, _ = _new_project("unused")
    bpy.ops.allset.project_window(name="p", location=folder)
    root = os.path.join(folder, "p")
    bpy.context.scene.render.filepath = "/tmp\\"
    path = os.path.join(root, "scenes", "shot_v001.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    assert bpy.context.scene.render.filepath == "//../images/", bpy.context.scene.render.filepath
    assert os.path.normcase(os.path.normpath(bpy.path.abspath(bpy.context.scene.render.filepath))) == \
        os.path.normcase(os.path.join(root, "images"))
    # a render path the user set is kept
    bpy.context.scene.render.filepath = "//renders/x_"
    bpy.ops.wm.save_mainfile()
    assert bpy.context.scene.render.filepath == "//renders/x_"
    # Save As keeps a file that is already in the project in its folder
    assert project.save_as_path() == path
    # opening a file under <root>/scenes makes that project current
    _reset_prefs()
    bpy.ops.wm.open_mainfile(filepath=path)
    assert os.path.normcase(project.current_root()) == os.path.normcase(root)


# --- increment ----------------------------------------------------------------------------------------

def test_ctrl_alt_s_is_maya_increment():
    found = [it for it in patches.ADDED if it[0] == "Window" and it[1] == "allset.increment_save"]
    assert found and found[0][2]["type"] == 'S' and found[0][2].get("ctrl") and found[0][2].get("alt"), found
    by_id = {it[1]: it for it in patches.ADDED if it[0] == "Window"}
    for idname in ("allset.open_scene", "allset.save_scene", "allset.save_scene_as", "allset.create_reference"):
        assert idname in by_id, idname
    km = kit.maya_kc().keymaps["Window"]
    incr = [kmi for kmi in km.keymap_items if kmi.type == 'S' and kmi.ctrl and kmi.alt and kmi.active]
    assert [kmi.idname for kmi in incr] == ["allset.increment_save"], [kmi.idname for kmi in incr]
    assert not [kmi for kmi in km.keymap_items if kmi.idname in {"wm.open_mainfile", "wm.save_mainfile",
                                                                  "wm.save_as_mainfile"}]
    for rtc in ("OpenScene", "SaveScene", "SaveSceneAs", "IncrementAndSave", "CreateReference"):
        assert mapping.ENTRIES[rtc]["status"] == "KIT", rtc
    # the Maya rule (menu_extras.increment_path), not Blender's shot_v002
    folder = tempfile.mkdtemp(prefix="mk69_")
    path = os.path.join(folder, "shot_v001.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    assert bpy.ops.allset.increment_save() == {'FINISHED'}
    assert os.path.basename(bpy.data.filepath) == "shot_v001.0001.blend" and os.path.isfile(path)


# --- references -------------------------------------------------------------------------------------------

def _source_file():
    """A saved scene with pCube1 / camera / light in its Collection (factory scene)."""
    folder = tempfile.mkdtemp(prefix="mk69_")
    bpy.ops.wm.read_homefile(use_factory_startup=True, app_template="")
    bpy.data.objects["Cube"].name = "pCube1"
    path = os.path.join(folder, "shot_v001.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.read_homefile(use_factory_startup=True, app_template="")
    bpy.data.objects["Cube"].name = "pCube1"      # a local pCube1 too: the reference still gets prop:pCube1
    for ob in [o for o in bpy.data.objects if o.name != "pCube1"]:
        bpy.data.objects.remove(ob)
    return folder, path


def test_create_reference_namespace_override():
    folder, src = _source_file()
    sc = bpy.context.scene
    assert bpy.ops.allset.create_reference(filepath=src, namespace="prop") == {'FINISHED'}
    cube = bpy.data.objects.get("prop:pCube1")
    assert cube is not None, sorted(o.name for o in sc.objects)
    assert cube.override_library is not None and cube.library is None, "editable reference = library override"
    assert "prop" in sc.collection.children and sc.collection.children["prop"]["allset_reference"] == src
    names = sorted(o.name for o in sc.objects if o.name != "pCube1")
    assert names == ["prop:Camera", "prop:Light", "prop:pCube1"], names
    assert not [o for o in sc.objects if o.library is not None], "the linked originals aren't in the scene"
    cube.location.x = 3.0                                   # a reference edit
    # same file again: Maya numbers the namespace
    assert bpy.ops.allset.create_reference(filepath=src, namespace="prop") == {'FINISHED'}
    assert "prop1:pCube1" in bpy.data.objects and "prop1" in sc.collection.children
    # default namespace = file name; linked only (not editable)
    assert bpy.ops.allset.create_reference(filepath=src, editable=False) == {'FINISHED'}
    group = sc.collection.children["shot_v001"]
    assert group.all_objects and all(o.library is not None for o in group.all_objects)
    # saved and reopened: the edit stays, the source file is unchanged
    main = os.path.join(folder, "main.blend")
    bpy.ops.wm.save_as_mainfile(filepath=main)
    bpy.ops.wm.open_mainfile(filepath=main)
    assert abs(bpy.data.objects["prop:pCube1"].location.x - 3.0) < 1e-6
    assert [lib.filepath for lib in bpy.data.libraries] and \
        os.path.normcase(bpy.path.abspath(bpy.data.libraries[0].filepath)) == os.path.normcase(src)
    # not a .blend / itself
    assert _cancelled(lambda: bpy.ops.allset.create_reference(filepath=os.path.join(folder, "x.fbx")))
    assert _cancelled(lambda: bpy.ops.allset.create_reference(filepath=main))


def test_menus_and_notices():
    m = menu_map.MAP
    assert m["File/Open Scene..."] == "allset.open_scene" and m["File/Save Scene"] == "allset.save_scene"
    assert m["File/Save Scene As..."] == "allset.save_scene_as"
    assert m["File/Create Reference..."] == "allset.create_reference"
    assert m["File/Reference Editor"] == "allset.reference_editor"   # the kit Reference Editor window
    assert m["File/Project Window"] == "allset.project_window" and m["File/Set Project..."] == "allset.set_project"
    assert m["File/Recent Projects"] == ("menu", "ALLSET_MT_recent_projects")
    assert "Maya Workflow Kit project" in notices.NOTICES["File/Set Project..."][0]
    assert "ns:name" in notices.NOTICES["File/Create Reference..."][1]
    # Recent Projects menu lists the prefs entries
    _reset_prefs()
    _f, root = _new_project("r")
    project.set_current(root)

    class Rec:
        def __init__(self):
            self.ops = []

        def operator(self, idname, text="", **kw):
            props = type("P", (), {})()
            self.ops.append((idname, text, props))
            return props

        def label(self, **kw):
            self.ops.append(("label", kw.get("text"), None))

    rec = Rec()
    project.ALLSET_MT_recent_projects.draw(type("M", (), {"layout": rec})(), bpy.context)
    assert rec.ops[0][0] == "allset.project_recent" and rec.ops[0][2].path == root
