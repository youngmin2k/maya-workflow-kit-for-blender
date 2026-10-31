"""Step 141 lane KEYS: Ctrl+A = Attribute Editor / Channel Box in every mode (#65), UV / Image Editor Alt+RMB dolly
without Blender's Zoom Axis preference (B4), undo-depth hint (B6), joint names restart at joint1 (#73).
GUI: tests/gui/gui_step141_keys.py."""

from importlib import import_module
from pathlib import Path

import bpy
from mathutils import Vector

import kit

maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")
mapping = import_module(kit.MODULE + ".keymap.mapping")
view = import_module(kit.MODULE + ".operators.view")
joints = import_module(kit.MODULE + ".operators.joints")
create = import_module(kit.MODULE + ".operators.create")
preferences = import_module(kit.MODULE + ".preferences")
welcome = import_module(kit.MODULE + ".welcome")

ROOT = Path(kit.__file__).resolve().parent.parent


def _items(km, t, **mods):
    return [k for k in kit.maya_kc().keymaps[km].keymap_items
            if k.active and k.type == t and k.value in ('PRESS', 'CLICK', 'CLICK_DRAG')
            and all(getattr(k, m) == mods.get(m, False) for m in ("shift", "ctrl", "alt", "oskey"))]


# --- #65 Ctrl+A ------------------------------------------------------------------------------------------------------

def test_ctrl_a_is_ae_toggle_in_every_mode():
    kms = ["Object Mode"] + [km for km, _ in maya_patches.CTRL_A_MODES]
    assert {"Mesh", "Pose", "Curve", "Armature", "UV Editor"} <= set(kms)
    for km in kms:
        got = [k.idname for k in _items(km, 'A', ctrl=True)]
        assert got == ["allset.ae_toggle"], (km, got)
        sel = [k for k in _items(km, 'A', ctrl=True, shift=True)]
        assert [k.idname.endswith("select_all") and k.properties.action == 'SELECT' for k in sel] == [True], \
            (km, [(k.idname, getattr(k.properties, "action", None)) for k in sel])


def test_alt_d_select_none_in_component_and_pose_modes():
    pose = [(k.idname, getattr(k.properties, "action", None)) for k in _items("Pose", 'D', alt=True)]
    assert pose == [("allset.select_none", None)], pose
    for km in ("Mesh", "Curve", "Armature", "Lattice", "Metaball"):
        assert [k.idname for k in _items(km, 'D', alt=True)] == ["allset.select_none"], km


def test_ctrl_a_text_editors_keep_select_all():
    # typing contexts keep their own select-all (Maya's Script Editor is a text field there too)
    for km, idname in (("Text", "text.select_all"), ("Console", "console.select_all"), ("Font", "font.select_all")):
        assert idname in [k.idname for k in _items(km, 'A', ctrl=True)], km


def test_ctrl_a_same_in_every_ic_version():
    # patches are strict only on 5.2: the 5.0 / 5.1 IC data must have the same Ctrl+A items, or their keymap drifts
    for name in ("ic_5_0", "ic_5_1", "ic_5_2"):
        data = import_module(f"{kit.MODULE}.keymap.{name}").DATA
        by = {n: d["items"] for n, _p, d in data}
        for km, idname in maya_patches.CTRL_A_MODES:
            ctrl_a = [it for it in by[km] if it[0] == idname and it[1]["type"] == "A" and it[1].get("ctrl")
                      and not it[1].get("shift")]
            assert ctrl_a, (name, km)


def test_mapping_row_notes_every_mode():
    e = mapping.ENTRIES["ShowAttributeEditorOrChannelBox"]
    assert e["status"] == "KIT" and "step 141" in e["note"]
    path = ROOT / "docs" / "keymap_mapping.md"
    if not path.exists():
        raise kit.Skip("generated mapping table not in this clone")
    doc = path.read_text(encoding="utf-8")
    row = next(ln for ln in doc.splitlines() if "ShowAttributeEditorOrChannelBox" in ln)
    assert "mesh.select_all" not in row and "Mesh: `allset.ae_toggle`" in row, row


# --- B4 UV / Image Editor dolly ----------------------------------------------------------------------------------

def test_image_editor_alt_rmb_is_kit_dolly():
    got = [k.idname for k in _items("Image", 'RIGHTMOUSE', alt=True)]
    assert got == ["allset.dolly_2d"], got
    assert getattr(bpy.types, "ALLSET_OT_dolly_2d", None) is not None


def test_dolly_2d_direction_and_maths():
    f = view.dolly_zoom_factor
    assert f(150, 0) > 1.0 and f(-150, 0) < 1.0, "drag right = zoom in, left = out (Maya)"
    assert abs(f(150, 0) - 2.0) < 1e-9 and abs(f(-150, 0) - 0.5) < 1e-9
    assert abs(f(75, 0) * f(75, 0) - f(150, 0)) < 1e-9, "steps multiply: the drag path doesn't matter"
    assert abs(f(300, 0, ui_scale=2.0) - 2.0) < 1e-9, "pixels follow the UI scale"
    # the 3D dolly and the 2D dolly agree: zoom factor = start distance / new distance
    assert abs(f(90, 30) - 1.0 / view.dolly_distance(1.0, 90, 30)) < 1e-9


def test_dolly_2d_zooms_an_image_editor():
    """exec path of a drag step: image.view_zoom(factor) under an Image Editor override (headless: the zoom getter
    reads the view, which only updates on a redraw, so this checks the call runs and is counted)."""
    win = bpy.context.window_manager.windows[0]
    area = max(win.screen.areas, key=lambda a: a.width * a.height)
    old = area.ui_type
    try:
        area.ui_type = 'UV'
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=win, area=area, region=region, space_data=area.spaces.active):
            assert bpy.ops.allset.dolly_2d.poll()
            res = bpy.ops.image.view_zoom('EXEC_DEFAULT', factor=view.dolly_zoom_factor(150, 0))
            assert res == {'FINISHED'}, res
    finally:
        area.ui_type = old


# --- B6 undo depth hint ------------------------------------------------------------------------------------------

def test_undo_hint_readme_and_app():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sec = readme.split("## Recommended setup", 1)[1].split("\n---", 1)[0]
    assert "Undo Steps" in sec and "256" in sec and "32" in sec and "unlimited" in sec, sec
    steps = bpy.context.preferences.edit.undo_steps
    hint = preferences.undo_hint(bpy.context)
    if steps < 256:
        assert hint and "Undo Steps" in hint and str(steps) in hint, hint
    else:
        assert hint is None
    assert any("Undo" in p and "256" in p for p in welcome.PARAGRAPHS)
    assert bpy.context.preferences.edit.undo_steps == steps, "read only"


def test_undo_hint_in_preferences_panel():
    """The add-on preferences draw the hint (factory Undo Steps 32 < 256)."""
    if bpy.context.preferences.edit.undo_steps >= 256:
        return
    labels = []

    class L:
        def __getattr__(self, name):
            def call(*a, **kw):
                if name == "label":
                    labels.append(kw.get("text", ""))
                return L()
            return call

        def __setattr__(self, name, value):
            pass

    prefs = preferences.get()
    prefs.__class__.draw(type("P", (), {"layout": L(), "maya_mode": prefs.maya_mode,
                                        "__getattr__": lambda s, n: getattr(prefs, n)})(), bpy.context)
    assert any("Undo Steps" in t for t in labels), labels


# --- #73 joint names ------------------------------------------------------------------------------------------------

def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)


def _skeleton(n=3):
    ob = joints.new_skeleton(bpy.context)
    parent, names = None, []
    for i in range(n):
        parent = joints.add_joint(ob, Vector((i, 0.0, 1.0)), parent, length=0.5)
        names.append(parent)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob, names


def test_joint_names_restart_after_delete():
    _clear()
    ob, names = _skeleton()
    assert names == ["joint1", "joint2", "joint3"], names
    _ob2, names2 = _skeleton(2)
    assert names2 == ["joint4", "joint5"], "joint names are scene-wide while skeleton1 exists"
    for o in list(bpy.context.selected_objects):
        o.select_set(False)
    for o in list(bpy.data.objects):
        o.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.delete()
    assert any(a.users == 0 for a in bpy.data.armatures), "Blender keeps the deleted skeletons' data until a purge"
    ob3, names3 = _skeleton(2)
    assert names3 == ["joint1", "joint2"], names3
    assert ob3.name == "skeleton1", ob3.name


def test_joint_names_skip_existing_after_partial_delete():
    _clear()
    a, _ = _skeleton(2)
    b, _ = _skeleton(1)                    # joint3
    for o in bpy.context.selected_objects:
        o.select_set(False)
    a.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.delete()
    _c, names = _skeleton(3)
    assert names == ["joint4", "joint5", "joint6"], names   # Maya (step 208): one past the highest, no gap filling
