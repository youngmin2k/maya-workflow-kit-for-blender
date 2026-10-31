"""Graph Editor t (center the current time), Alt+/ (Snap Time To Selection toggle), i hold (Insert Key
tool)."""

from importlib import import_module

import bpy

import kit

gk = import_module(kit.MODULE + ".operators.graph_keys")
prefs_mod = import_module(kit.MODULE + ".preferences")


def _cube_with_keys():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    me = bpy.data.meshes.new("pCubeShape1")
    ob = bpy.data.objects.new("pCube1", me)
    bpy.context.scene.collection.objects.link(ob)
    for f, v in ((1, 0.0), (10, 5.0), (20, 0.0)):
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    fc = kit.fcurves(ob).find("location", index=0)
    for kp in fc.keyframe_points:
        kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False
    return ob, fc


def test_center_delta_pans_to_the_middle():
    assert gk.center_delta(700, 1000) == 200          # frame drawn right of centre: pan right
    assert gk.center_delta(300, 1000) == -200
    assert gk.center_delta(500, 1000) == 0


def test_snap_target_is_the_earliest_selected_key():
    # Maya: 10 + 20 -> 10, 20 then add 10 -> 10, 20 alone -> 20, nothing -> stays
    assert gk.snap_target([10.0, 20.0]) == 10.0
    assert gk.snap_target([20.0, 10.0]) == 10.0
    assert gk.snap_target([20.0]) == 20.0
    assert gk.snap_target([]) is None


def test_snap_step_follows_selection_changes():
    sc = bpy.context.scene
    ob, fc = _cube_with_keys()
    assert gk.snap_step(sc, True) is None                 # first poll: baseline only
    fc.keyframe_points[2].select_control_point = True     # key 20
    assert gk.snap_step(sc, True) == 20.0
    assert gk.snap_step(sc, True) is None                 # no change, no snap
    fc.keyframe_points[1].select_control_point = True     # add key 10
    assert gk.snap_step(sc, True) == 10.0
    for kp in fc.keyframe_points:
        kp.select_control_point = False
    assert gk.snap_step(sc, True) is None                 # empty selection: time stays
    fc.keyframe_points[2].select_control_point = True
    assert gk.snap_step(sc, False) is None                # option off: never
    assert gk.snap_step(sc, True) is None                 # turned on again: new baseline first
    gk.remember_selection(sc)
    fc.keyframe_points[0].select_control_point = True
    gk.remember_selection(sc)                             # a kit edit took this selection as baseline
    assert gk.snap_step(sc, True) is None


def test_insert_frame_is_the_whole_frame():
    assert gk.insert_frame(6.6) == 7 and gk.insert_frame(15.2) == 15 and gk.insert_frame(-0.4) == 0


def test_insert_targets_and_keeps_the_shape():
    ob, fc = _cube_with_keys()
    assert gk.insert_curves([fc]) == [] or fc.select     # nothing selected -> nothing (unless the channel is)
    fc.select = False
    assert gk.insert_curves([fc]) == []
    fc.keyframe_points[1].select_control_point = True
    assert gk.insert_curves([fc]) == [fc]
    before = {f: fc.evaluate(f) for f in (4, 5, 6, 7, 8, 9)}
    assert gk.insert_on([fc], 7) == [fc]
    keys = [(round(kp.co.x), round(kp.co.y, 4), kp.select_control_point) for kp in fc.keyframe_points]
    assert [k[0] for k in keys] == [1, 7, 10, 20], keys
    assert abs(fc.keyframe_points[1].co.y - before[7]) < 1e-5, (fc.keyframe_points[1].co.y, before[7])
    assert [k[2] for k in keys] == [False, True, False, False], keys      # only the new key selected
    for f, v in before.items():
        assert abs(fc.evaluate(f) - v) < 1e-4, (f, fc.evaluate(f), v)     # the curve shape is kept
    fc.lock = True
    assert gk.insert_curves([fc]) == []


def test_snap_toggle_operator_and_menu():
    prefs = prefs_mod.get()
    prefs.snap_time_to_selection = False
    assert bpy.ops.allset.snap_time_toggle() == {'FINISHED'} and prefs.snap_time_to_selection
    assert bpy.ops.allset.snap_time_toggle() == {'FINISHED'} and not prefs.snap_time_to_selection
    assert gk.draw_view_menu in bpy.types.GRAPH_MT_view._dyn_ui_initialize()
    assert bpy.app.timers.is_registered(gk._snap_tick)


def test_keymap_items():
    km = kit.maya_kc().keymaps["Graph Editor"]

    def one(t, idname, **mods):
        items = [k for k in km.keymap_items if k.active and k.type == t and k.idname == idname
                 and all(getattr(k, m) == mods.get(m, False) for m in ("shift", "ctrl", "alt"))]
        assert len(items) == 1, (t, idname, mods)
    one('T', "allset.graph_center_time")
    one('SLASH', "allset.snap_time_toggle", alt=True)
    one('I', "allset.insert_key_tool")
