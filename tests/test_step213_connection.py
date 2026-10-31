"""#119: Maya's Connection Editor = drivers (ui/connection_editor.py;
Maya connectAttr: the right attribute follows the left, a second connect warns, break keeps the value)."""

import math
from importlib import import_module

import bpy

import kit


def m(name):
    return import_module(f"{kit.MODULE}.{name}")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _ob(name):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _cm_scene():
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0


def _eval():
    bpy.context.view_layer.update()


def test_attribute_list_like_maya():
    _clear()
    ce = m("ui.connection_editor")
    a = _ob("pCube1")
    a["weight"] = 0.5
    a["allset_dag_order"] = 3          # kit bookkeeping is not a Maya attribute
    names = [n for n, _d, _c in ce.attributes(a)]
    assert names[:5] == ["visibility", "translate", "translateX", "translateY", "translateZ"], names
    assert "rotateZ" in names and "scaleX" in names and names[-1] == "weight"
    assert "allset_dag_order" not in names
    assert ce.leaves("translate") == ["translateX", "translateY", "translateZ"]
    assert ce._nice("translateX") == "Translate X"


def test_connect_follows_and_break_keeps_the_value():
    _clear()
    _cm_scene()
    ce = m("ui.connection_editor")
    a, b = _ob("pCube1"), _ob("pSphere1")
    a.location.x = 0.03                       # 3 cm (Maya 3)
    assert ce.connect(bpy.context.scene, a, "translateX", b, "translateX") == 1
    _eval()
    assert abs(b.location.x - 0.03) < 1e-9, b.location.x
    assert ce.connected(a, "translateX", b, "translateX")
    assert ce.source_of(b, "translateX") == (a, "translateX")
    a.location.x = 0.05
    _eval()
    assert abs(b.location.x - 0.05) < 1e-9, "the right attribute follows the left (Maya: 5)"
    assert ce.disconnect(b, "translateX") == 1
    a.location.x = 0.0
    _eval()
    assert abs(b.location.x - 0.05) < 1e-9, "after Break the value stays (Maya: 5)"
    assert ce.source_of(b, "translateX") is None


def test_compound_and_unit_conversion():
    _clear()
    _cm_scene()
    ce = m("ui.connection_editor")
    a, b = _ob("pCube1"), _ob("pSphere1")
    a.location = (0.01, 0.02, 0.03)
    assert ce.connect(bpy.context.scene, a, "translate", b, "translate") == 3
    _eval()
    assert all(abs(b.location[i] - a.location[i]) < 1e-9 for i in range(3))
    assert ce.connected(a, "translate", b, "translate")
    # Maya unit conversion: translateX 3 (cm) -> rotateX 3 degrees
    a.location.x = 0.03
    ce.connect(bpy.context.scene, a, "translateX", b, "rotateX")
    _eval()
    assert abs(math.degrees(b.rotation_euler.x) - 3.0) < 1e-6, math.degrees(b.rotation_euler.x)
    try:
        ce.connect(bpy.context.scene, a, "translate", b, "rotateY")
    except ValueError:
        pass
    else:
        raise AssertionError("a compound to a single attribute must be refused")
    a["weight"] = 0.25
    ce.connect(bpy.context.scene, a, "weight", b, "scaleZ")
    _eval()
    fc = ce._fcurve(b, "scale", 2)
    # float32 channel (5.x reads 0.24999998)
    assert abs(b.scale.z - 0.25) < 1e-6, (b.scale.z, fc and fc.driver.is_valid, fc and fc.driver.expression,
                                          fc and [(v.targets[0].id, v.targets[0].data_path) for v in fc.driver.variables])


def test_operators_pick_connects_and_toggles():
    _clear()
    ce = m("ui.connection_editor")
    wm = bpy.context.window_manager
    a, b = _ob("pCube1"), _ob("pSphere1")
    wm.allset_cn_left, wm.allset_cn_right = a.name, b.name
    wm.allset_cn_mode, wm.allset_cn_auto = "FROM_TO", True
    assert bpy.ops.allset.cn_pick(side="LEFT", attr="scaleY") == {'FINISHED'}
    assert bpy.ops.allset.cn_pick(side="RIGHT", attr="scaleY") == {'FINISHED'}
    assert ce.connected(a, "scaleY", b, "scaleY"), "Auto-connect: the right pick connects"
    assert bpy.ops.allset.cn_pick(side="RIGHT", attr="scaleY") == {'FINISHED'}
    assert not ce.connected(a, "scaleY", b, "scaleY"), "a pick on a connected right attribute breaks it"
    wm.allset_cn_auto = False
    bpy.ops.allset.cn_pick(side="RIGHT", attr="scaleY")
    assert not ce.connected(a, "scaleY", b, "scaleY"), "Auto-connect off: Make connects"
    assert bpy.ops.allset.cn_command(action="MAKE") == {'FINISHED'}
    assert ce.connected(a, "scaleY", b, "scaleY")
    assert bpy.ops.allset.cn_command(action="BREAK") == {'FINISHED'}
    assert not ce.connected(a, "scaleY", b, "scaleY")
    bpy.ops.allset.cn_command(action="SWAP")
    assert (wm.allset_cn_left, wm.allset_cn_right) == (b.name, a.name)
    bpy.ops.allset.cn_command(action="CLEAR")
    assert wm.allset_cn_left == wm.allset_cn_right == ""
    wm.allset_cn_auto = True


def test_windows_menu_and_window_marks():
    mm = m("ui.menu_map")
    assert mm.MAP["Windows/General Editors/Connection Editor"] == ("allset.connection_editor", {})
    assert mm.MAP["Windows/General Editors/Component Editor"] == ("allset.component_editor", {})
    assert mm.MAP["Windows/Animation Editors/Shape Editor"] == ("allset.shape_editor", {})
    mw = m("ui.marked_window")
    marks = [frozenset(v) for v in mw.KINDS.values()]
    assert len(set(marks)) == len(marks)
    dock = m("ui.maya_dock")
    hs = m("ui.hypershade")
    ref = m("ui.reference_editor")
    for mark in marks:
        assert len(mark) == 2 and mark != frozenset(hs.MARK) and mark != frozenset(ref.MARK)
        assert not any(mark == {flag} for flag in dock.ROLE_FLAGS.values())
    ed = m("ui.editor_menu_data")
    for name in ("Component Editor", "Shape Editor", "Connection Editor"):
        assert name in ed.EDITORS
    assert [t for t, _i in ed.EDITORS["Connection Editor"]] == ["Options", "Left Display", "Right Display", "Help"]
