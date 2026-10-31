"""No Maya command greyed in one menu while it works in another (tools/menu_consistency.py on the live kit),
Select / Delete All by Type for the kit's IK handles and clusters, Dope Sheet curve commands and Auto Frame."""

import importlib.util
import os
from importlib import import_module

import bpy

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
menu_data = import_module(kit.MODULE + ".ui.menu_data")
editor_menu_data = import_module(kit.MODULE + ".ui.editor_menu_data")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
mm = import_module(kit.MODULE + ".marking.menus")
by_type = import_module(kit.MODULE + ".operators.by_type")
graph_key_menu = import_module(kit.MODULE + ".operators.graph_key_menu")
preferences = import_module(kit.MODULE + ".preferences")


def _tool(name):
    spec = importlib.util.spec_from_file_location(f"tool_{name}", os.path.join(ROOT, "tools", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _menu_paths(menu_count):
    out = []
    for _name, (label, _set, _src, items) in menu_data.MENUS.items():
        out += [(p, p in menu_map.MAP) for p, _it in menu_count.leaves(menu_data, menu_map, items, label)]
    for editor, menus in editor_menu_data.EDITORS.items():
        for title, items in menus:
            out += [(p, p in menu_map.MAP) for p, _it in menu_count.leaves(menu_data, menu_map, items,
                                                                           f"{editor}/{title}")]
    return sorted(set(out))


def test_twins_mapped_to_the_same_action():
    for twin, source in menu_map.TWINS.items():
        assert menu_map.MAP.get(twin) == menu_map.MAP.get(source) is not None, twin
    # Maya 2026's Dope Sheet has no Curves menu: its curve commands are gone with it
    for label in ("Euler Filter", "Smooth Filter (Butterworth)", "Smooth Filter (Gaussian)", "Resample Curve",
                  "Isolate Curve"):
        assert f"Dope Sheet/Curves/{label}" not in menu_map.MAP, label
        assert f"Graph Editor/Curves/{label}" in menu_map.MAP, label
    assert menu_map.MAP["Dope Sheet/View/Auto Frame"] == menu_map.MAP["Graph Editor/View/Auto Frame"][:1] +         ("addon_prefs.dope_auto_frame",) + menu_map.MAP["Graph Editor/View/Auto Frame"][2:]
    assert preferences.get().dope_auto_frame is False, "Maya's Dope Sheet Auto Frame is off by default"


def test_menu_counts():
    menu_count = _tool("menu_count")
    from types import SimpleNamespace
    md = SimpleNamespace(MENUS=menu_data.MENUS, MENU_SETS=menu_data.MENU_SETS, EDITORS=editor_menu_data.EDITORS)
    r = menu_count.count(md, menu_map, notices)
    eds = r["editors"]
    print({k: eds[k]["working"] for k in ("Dope Sheet", "UV Editor")})
    # the Maya 2026 Dope Sheet has 94 leaves, 68 working
    assert eds["Dope Sheet"]["working"] >= 68, eds["Dope Sheet"]
    assert eds["UV Editor"]["working"] >= 114, eds["UV Editor"]       # at least 114
    assert not r["greyed"], r["greyed"][:5]


# --- Select / Delete All by Type ---------------------------------------------------------------------------------

def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _rig():
    """Two-bone armature with an IK constraint on the second bone targeting an ``ikHandle1`` empty."""
    arm = _link(bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1")))
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    a = arm.data.edit_bones.new("joint1")
    a.head, a.tail = (0, 0, 0), (0, 0, 1)
    b = arm.data.edit_bones.new("joint2")
    b.head, b.tail, b.parent = (0, 0, 1), (0, 0, 2), a
    bpy.ops.object.mode_set(mode='OBJECT')
    handle = _link(bpy.data.objects.new("ikHandle1", None))
    con = arm.pose.bones["joint2"].constraints.new('IK')
    con.target = handle
    return arm, handle


def _cluster():
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    cube = bpy.context.view_layer.objects.active
    assert bpy.ops.allset.cluster() == {'FINISHED'}
    handle = bpy.context.view_layer.objects.active
    assert handle.name.startswith("cluster") and handle.name.endswith("Handle"), handle.name
    return cube, handle


def test_select_all_by_type_ik_handles_and_clusters():
    _fresh()
    arm, ik = _rig()
    cube, ch = _cluster()
    other = _link(bpy.data.objects.new("locator1", None))
    soft = cube.modifiers.new("softMod1", 'HOOK')
    soft.object = other                       # a soft modification is not a cluster
    assert bpy.ops.allset.menu_item(item="Select/All by Type/IK Handles") == {'FINISHED'}
    assert [o.name for o in bpy.context.selected_objects] == [ik.name]
    assert bpy.context.view_layer.objects.active == ik
    assert bpy.ops.allset.menu_item(item="Select/All by Type/Clusters") == {'FINISHED'}
    assert [o.name for o in bpy.context.selected_objects] == [ch.name], bpy.context.selected_objects
    assert by_type.cluster_handles(bpy.context.scene) == [ch]


def test_delete_all_by_type_ik_handles_and_clusters():
    _fresh()
    arm, ik = _rig()
    cube, ch = _cluster()
    other = _link(bpy.data.objects.new("locator1", None))
    soft = cube.modifiers.new("softMod1", 'HOOK')
    soft.object = other
    name = ch.name
    assert bpy.ops.allset.menu_item(item="Edit/Delete All by Type/IK Handles") == {'FINISHED'}
    assert not arm.pose.bones["joint2"].constraints, "the IK constraint is gone"
    assert "ikHandle1" not in bpy.data.objects, "and its handle"
    assert bpy.ops.allset.menu_item(item="Edit/Delete All by Type/Clusters") == {'FINISHED'}
    assert name not in bpy.data.objects, "the cluster handle goes with the cluster"
    assert [m.name for m in cube.modifiers if m.type == 'HOOK'] == ["softMod1"], "soft modification kept"
    assert not any(g.name.startswith("cluster") for g in cube.vertex_groups), "the cluster's weights go too"
    assert "locator1" in bpy.data.objects


def test_select_particles_rigid_bodies():
    _fresh()
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    a = bpy.context.view_layer.objects.active
    a.modifiers.new("ps", 'PARTICLE_SYSTEM')
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    assert by_type.select_all(bpy.context, 'PARTICLES') == [a]
    assert [o.name for o in bpy.context.selected_objects] == [a.name]
    assert by_type.select_all(bpy.context, 'RIGID_BODIES') == []


def test_dope_curve_selection_rule():
    _fresh()
    ob = _link(bpy.data.objects.new("pCube1", None))
    ob.keyframe_insert("location", index=0, frame=1)
    ob.keyframe_insert("location", index=1, frame=1)
    fcs = list(kit.fcurves(ob))
    for fc in fcs:
        for k in fc.keyframe_points:
            k.select_control_point = False
    fcs[1].keyframe_points[0].select_control_point = True
    assert graph_key_menu.curves_with_selected_keys(fcs) == [fcs[1]]
    assert not bpy.ops.allset.dope_graph_op.poll(), "needs a Dope Sheet / Graph Editor"
