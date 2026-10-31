"""Global key batch 4 — Ctrl+X cut, Alt+X walk, Alt+\\ playback range = animation range, Alt+1 / 2 / 4 show
toggles, Ctrl+` / Shift+~ / Ctrl+Shift+~ smooth proxy; Edit > Cut."""

from importlib import import_module

import bpy

import kit

gk = import_module(kit.MODULE + ".operators.global_keys4")
display = import_module(kit.MODULE + ".operators.display")
range_bar = import_module(kit.MODULE + ".ui.range_bar")
menu_map = import_module(kit.MODULE + ".ui.menu_map")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _cube(name="pCube1", parent=None):
    me = bpy.data.meshes.new(name + "Shape")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    return ob


def _keymap():
    return kit.maya_kc().keymaps


def _items(km, t, **mods):
    return [k for k in _keymap()[km].keymap_items if k.active and k.type == t and k.value in ('PRESS', 'CLICK')
            and all(getattr(k, m) == mods.get(m, False) for m in ("shift", "ctrl", "alt", "oskey"))]


def test_keymap_items():
    def one(km, t, idname, props=None, **mods):
        found = [k for k in _items(km, t, **mods) if k.idname == idname
                 and all(getattr(k.properties, p) == v for p, v in (props or {}).items())]
        assert len(found) == 1, (km, t, idname, props, mods, [k.idname for k in _items(km, t, **mods)])
    one("Object Mode", 'X', "allset.cut", ctrl=True)
    one("Outliner", 'X', "allset.cut", ctrl=True)
    one("Object Mode", 'V', "allset.paste", ctrl=True)
    one("3D View", 'X', "view3d.walk", alt=True)
    assert not [k for k in _items("3D View", 'X', alt=True) if k.idname == "view3d.toggle_xray"]
    one("Screen", 'BACK_SLASH', "allset.playback_range_anim", alt=True)
    for key, kind in (('ONE', 'CURVES'), ('TWO', 'POLYGONS'), ('FOUR', 'IMAGE_PLANES')):
        one("3D View", key, "allset.toggle_show", {"kind": kind}, alt=True)
    for km in ("Object Mode", "Mesh"):
        one(km, 'ACCENT_GRAVE', "allset.smooth_proxy", {"action": 'TOGGLE'}, ctrl=True)
        one(km, 'ACCENT_GRAVE', "allset.smooth_proxy", {"action": 'BOTH'}, shift=True)
    one("Object Mode", 'ACCENT_GRAVE', "allset.smooth_proxy", {"action": 'CREATE'}, ctrl=True, shift=True)
    one("3D View", 'ACCENT_GRAVE', "allset.tweak_hold")      # plain ` stays the tweak hold


def test_cut_takes_the_hierarchy_and_paste_brings_it_back():
    _clear()
    grp = bpy.data.objects.new("group1", None)
    bpy.context.scene.collection.objects.link(grp)
    child = _cube("pCube1", parent=grp)
    other = _cube("pCube2")
    assert [o.name for o in gk.cut_targets([grp])] == ["group1", "pCube1"]
    for o in bpy.context.scene.objects:
        o.select_set(o is grp)
    bpy.context.view_layer.objects.active = grp
    assert bpy.ops.allset.cut() == {'FINISHED'}
    assert "group1" not in bpy.data.objects and "pCube1" not in bpy.data.objects and other.name == "pCube2"
    del child
    assert bpy.ops.allset.paste() == {'FINISHED'}
    # Maya pasteScene: pasted__ names under a new "group"
    objs = bpy.data.objects
    assert "pasted__group1" in objs and "pasted__pCube1" in objs, sorted(objs.keys())
    assert objs["pasted__pCube1"].parent == objs["pasted__group1"]
    assert objs["pasted__group1"].parent == objs["group"]
    assert bpy.context.view_layer.objects.active == objs["group"]     # Maya selects the paste group
    assert objs["pasted__pCube1"].data.name == "pasted__pCube1Shape", objs["pasted__pCube1"].data.name


def test_cut_needs_object_mode_and_a_selection():
    _clear()
    _cube()
    for o in bpy.context.scene.objects:
        o.select_set(False)
    assert not bpy.ops.allset.cut.poll()


def test_playback_range_becomes_the_animation_range():
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 120
    range_bar.set_playback(sc, 20, 40)
    assert range_bar.playback(sc) == (20, 40)
    assert bpy.ops.allset.playback_range_anim() == {'FINISHED'}
    assert range_bar.playback(sc) == (1, 120)
    range_bar.toggle_whole(sc)                 # the Range Slider double-click brings the old range back
    assert range_bar.playback(sc) == (20, 40)


class _Space:
    show_object_viewport_curve = True
    show_object_viewport_mesh = True


def test_toggle_show():
    _clear()
    sp, sc = _Space(), bpy.context.scene
    assert gk.toggle_show(sp, sc, 'CURVES') is False and not sp.show_object_viewport_curve and sp.show_object_viewport_mesh
    assert gk.toggle_show(sp, sc, 'CURVES') is True and sp.show_object_viewport_curve
    assert gk.toggle_show(sp, sc, 'POLYGONS') is False and not sp.show_object_viewport_mesh
    plane = bpy.data.objects.new("imagePlane1", None)
    plane.empty_display_type = 'IMAGE'
    loc = bpy.data.objects.new("locator1", None)
    sc.collection.objects.link(plane)
    sc.collection.objects.link(loc)
    assert gk.toggle_show(sp, sc, 'IMAGE_PLANES') is False
    assert not plane.show_empty_image_perspective and not plane.show_empty_image_orthographic
    assert gk.toggle_show(sp, sc, 'IMAGE_PLANES') is True and plane.show_empty_image_perspective


def test_smooth_proxy_create_toggle_both():
    _clear()
    ob = _cube()
    display.set_smooth_preview(ob, 3)                        # the kit preview must stay last
    assert gk.proxy_action(ob, 'TOGGLE') is False            # no proxy yet
    assert gk.proxy_action(ob, 'CREATE')
    mod = gk.proxy_modifier(ob)
    assert mod is not None and mod.show_viewport and not display.is_preview(mod)
    assert display.is_preview(ob.modifiers[-1]) and display.is_preview(ob.modifiers[-2])
    gk.proxy_action(ob, 'CREATE')                            # once only
    assert len([m for m in ob.modifiers if m.type == 'SUBSURF' and not display.is_preview(m)]) == 1
    gk.proxy_action(ob, 'TOGGLE')
    assert not mod.show_viewport                             # cage
    gk.proxy_action(ob, 'TOGGLE')
    assert mod.show_viewport                                 # smooth
    gk.proxy_action(ob, 'BOTH')
    assert mod.show_viewport and ob.show_wire
    gk.proxy_action(ob, 'TOGGLE')                            # both -> cage only
    assert not mod.show_viewport and not ob.show_wire


def test_smooth_proxy_operator_reports_without_proxy():
    _clear()
    ob = _cube()
    for o in bpy.context.scene.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    assert bpy.ops.allset.smooth_proxy(action='TOGGLE') == {'CANCELLED'}
    assert bpy.ops.allset.smooth_proxy(action='CREATE') == {'FINISHED'}
    assert gk.proxy_modifier(ob) is not None


def test_edit_cut_menu_item():
    assert menu_map.MAP["Edit/Cut"] == "allset.cut"
    assert menu_map.MAP["Edit/Paste"] == ("v3d", "allset.paste", {})
