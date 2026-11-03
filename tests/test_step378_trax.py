"""#287: Maya Trax clips on the NLA (operators/trax_clips.py): Create Clip from keys (names, character, keys moved
into the clip, values kept), instances of one source, duplicate / trim / split / enable, blend of overlapping
clips, several objects in one clip, coexistence with animation layers, one undo step per command, the Trax menu bar
and its option window."""

from importlib import import_module

import bpy

import kit

tc = import_module(kit.MODULE + ".operators.trax_clips")
al = import_module(kit.MODULE + ".operators.anim_layers")
compat = import_module(kit.MODULE + ".compat")


def _cube(sc, name, x1=10.0, t1=24):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name + "Shape"))
    sc.collection.objects.link(ob)
    ob.location.x = 0.0
    ob.keyframe_insert("location", index=0, frame=1)
    ob.location.x = x1
    ob.keyframe_insert("location", index=0, frame=t1)
    return ob


def scene(*names):
    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    while len(sc.keying_sets):
        sc.keying_sets.active_index = 0
        bpy.ops.anim.keying_set_remove()
    sc.allset_anim_layers.clear()
    sc.frame_start, sc.frame_end, sc.use_preview_range = 1, 120, False
    obs = [_cube(sc, n, 10.0 * (i + 1)) for i, n in enumerate(names or ("pCube1",))]
    for o in sc.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[0]
    return sc, obs


def x_at(sc, ob, frame):
    sc.frame_set(frame)
    return round(ob.matrix_world.translation.x, 4)


def test_create_clip_like_maya():
    sc, (ob,) = scene()
    before = [x_at(sc, ob, f) for f in (1, 10, 24, 40)]
    assert bpy.ops.allset.trax_create_clip() == {'FINISHED'}
    assert ob.animation_data.action is None, "the keys leave the object (Leave keys in timeline off)"
    act = bpy.data.actions["clip1Source"]
    assert tc.is_source(act) and act.use_fake_user
    assert act[tc.CHARACTER] == "pCube1Ch" and sc.keying_sets.active is None, "a new character, not current"
    assert [ks.bl_label for ks in sc.keying_sets] == ["pCube1Ch"]
    rows = tc.instances(sc, "clip1")
    assert len(rows) == 1 and rows[0][1].name.startswith(tc.TRACK)
    st = rows[0][2]
    assert (st.frame_start, st.frame_end) == (1.0, 24.0), "placed at the source start, animation curve range"
    assert [x_at(sc, ob, f) for f in (1, 10, 24, 40)] == before, "values unchanged (and held after the end)"
    # second clip on new keys -> clip2 / clip2Source, a new track
    ob.location.y = 0
    ob.keyframe_insert("location", index=1, frame=30)
    ob.location.y = 5
    ob.keyframe_insert("location", index=1, frame=40)
    assert bpy.ops.allset.trax_create_clip() == {'FINISHED'}
    assert "clip2Source" in bpy.data.actions and tc.instance_names(sc) == ["clip1", "clip2"]
    assert len(tc.clip_tracks(ob)) == 2
    st2 = tc.instances(sc, "clip2")[0][2]
    assert (st2.frame_start, st2.frame_end) == (30.0, 40.0)
    assert st2.extrapolation == 'HOLD_FORWARD' and st.extrapolation == 'HOLD'


def test_leave_keys_and_ranges():
    sc, (ob,) = scene()
    assert bpy.ops.allset.trax_create_clip(leave_keys=True, time_range="Start/End", start=5, end=15) == {'FINISHED'}
    assert ob.animation_data.action is not None and compat.id_fcurves(ob)
    act = bpy.data.actions["clip1Source"]
    assert tuple(act.frame_range) == (5.0, 15.0)
    st = tc.instances(sc, "clip1")[0][2]
    assert (st.frame_start, st.frame_end) == (5.0, 15.0)
    sc2, (ob2,) = scene()
    assert bpy.ops.allset.trax_create_clip(visor_only=True) == {'FINISHED'}
    assert "clip1Source" in bpy.data.actions and not tc.instance_names(sc2), "Visor only: no instance"


def test_instances_duplicate_trim_split_enable():
    sc, (ob,) = scene()
    bpy.ops.allset.trax_create_clip()
    act = bpy.data.actions["clip1Source"]
    sc.frame_current = 60
    assert bpy.ops.allset.trax_insert_clip(source=act.name) == {'FINISHED'}
    assert tc.instance_names(sc) == ["clip1", "clip2"], "instances count on like Maya's clip nodes"
    st = tc.instances(sc, "clip2")[0][2]
    assert st.action == act and (st.frame_start, st.frame_end) == (60.0, 83.0)
    assert x_at(sc, ob, 70) == x_at(sc, ob, 11), "the instance plays the same source"
    assert x_at(sc, ob, 40) == 10.0, "clip1 holds until clip2 starts"
    # duplicate: right after the clip, same timing
    st.scale = 2.0
    assert bpy.ops.allset.trax_clip_edit(action='DUPLICATE', clip="clip2") == {'FINISHED'}
    d = tc.instances(sc, "clip3")[0][2]
    assert d.frame_start == st.frame_end and d.scale == 2.0
    # trim before / after at the current time
    sc.frame_current = 70
    assert bpy.ops.allset.trax_clip_edit(action='TRIM_BEFORE', clip="clip2") == {'FINISHED'}
    st = tc.instances(sc, "clip2")[0][2]
    assert st.frame_start == 70.0 and abs(st.action_frame_start - 6.0) < 1e-4
    sc.frame_current = 90
    assert bpy.ops.allset.trax_clip_edit(action='TRIM_AFTER', clip="clip2") == {'FINISHED'}
    st = tc.instances(sc, "clip2")[0][2]
    assert abs(st.frame_end - 90.0) < 1e-4
    # split clip1 at 12: the right part is a new instance on the same track
    value = x_at(sc, ob, 18)
    sc.frame_set(12)
    assert bpy.ops.allset.trax_clip_edit(action='SPLIT', clip="clip1") == {'FINISHED'}
    left, right = tc.instances(sc, "clip1")[0], tc.instances(sc, "clip4")[0]
    assert left[1].name == right[1].name and left[2].frame_end == 12.0 and right[2].frame_start == 12.0
    assert x_at(sc, ob, 18) == value, "a split doesn't change the motion"
    # enable / disable
    assert bpy.ops.allset.trax_clip_edit(action='ENABLE', clip="clip3") == {'FINISHED'}
    assert tc.instances(sc, "clip3")[0][2].mute
    # library delete removes the source and every instance
    assert bpy.ops.allset.trax_delete_source(source=act.name) == {'FINISHED'}
    assert not tc.instance_names(sc) and "clip1Source" not in bpy.data.actions


def test_blend_overlap():
    sc, (ob,) = scene()
    bpy.ops.allset.trax_create_clip()
    sc.frame_current = 15
    bpy.ops.allset.trax_insert_clip(source="clip1Source")      # clip2 at 15..38 overlaps clip1 at 15..24
    for _o, _t, st in tc.clip_strips(sc):
        st.select = st.name == "clip1"
    assert bpy.ops.allset.trax_clip_edit(action='BLEND') == {'CANCELLED'}, "needs two selected clips"
    for _o, _t, st in tc.clip_strips(sc):
        st.select = True
    assert bpy.ops.allset.trax_clip_edit(action='BLEND') == {'FINISHED'}
    st2 = tc.instances(sc, "clip2")[0][2]
    assert st2.blend_in == 9.0
    src = compat.action_fcurves(bpy.data.actions["clip1Source"])[0].evaluate
    # blend start = clip1 (source 15), blend end = clip2 (source 10), halfway = the mix
    assert abs(x_at(sc, ob, 15) - round(src(15), 4)) < 1e-3
    assert abs(x_at(sc, ob, 24) - round(src(10), 4)) < 1e-3
    mid = 0.5 * src(19.5) + 0.5 * src(5.5)
    sc.frame_set(19, subframe=0.5)
    assert abs(ob.matrix_world.translation.x - mid) < 1e-3
    # far apart clips: Blender can't blend a gap
    sc.frame_current = 80
    bpy.ops.allset.trax_insert_clip(source="clip1Source")
    for _o, _t, st in tc.clip_strips(sc):
        st.select = st.name in ("clip1", "clip3")
    assert bpy.ops.allset.trax_clip_edit(action='BLEND') == {'CANCELLED'}


def test_several_objects_one_clip():
    sc, (a, b) = scene("pCube1", "pCube2")
    va, vb = x_at(sc, a, 12), x_at(sc, b, 12)
    assert bpy.ops.allset.trax_create_clip() == {'FINISHED'}
    act = bpy.data.actions["clip1Source"]
    assert len(act.slots) == 2 and act[tc.CHARACTER] == "multiCh"
    assert {o.name for o, _s in tc.source_objects(act)} == {"pCube1", "pCube2"}
    assert {o.name for o, _t, _s in tc.instances(sc, "clip1")} == {"pCube1", "pCube2"}
    assert (x_at(sc, a, 12), x_at(sc, b, 12)) == (va, vb)
    # one Insert places the whole group
    sc.frame_current = 50
    bpy.ops.allset.trax_insert_clip(source=act.name)
    assert {o.name for o, _t, _s in tc.instances(sc, "clip2")} == {"pCube1", "pCube2"}


def test_hierarchy_and_character():
    sc, (a, b) = scene("pCube1", "pCube2")
    grp = bpy.data.objects.new("group1", None)
    sc.collection.objects.link(grp)
    a.parent = b.parent = grp
    for o in sc.objects:
        o.select_set(o == grp)
    assert bpy.ops.allset.trax_create_clip() == {'FINISHED'}
    assert {o.name for o, _t, _s in tc.instances(sc, "clip1")} == {"pCube1", "pCube2"}, "keyed nodes below"
    assert bpy.ops.allset.trax_create_clip() == {'CANCELLED'}, "nothing keyed is left"
    # a current character: its channels whatever is selected
    sc, (a, b) = scene("pCube1", "pCube2")
    ks = sc.keying_sets.new(idname="", name="hero")
    ks.bl_label = "hero"
    ks.paths.add(b, "location", index=0, group_method='KEYINGSET')
    sc.keying_sets.active_index = 0
    for o in sc.objects:
        o.select_set(False)
    assert bpy.ops.allset.trax_create_clip() == {'FINISHED'}
    assert bpy.data.actions["clip1Source"][tc.CHARACTER] == "hero"
    assert {o.name for o, _t, _s in tc.instances(sc, "clip1")} == {"pCube2"}
    assert a.animation_data.action is not None, "not a member: its keys stay"


def test_layers_coexist():
    sc, (ob,) = scene()
    bpy.ops.allset.trax_create_clip()
    clip = x_at(sc, ob, 12)
    bpy.ops.allset.anim_layer_create(from_selected=True)
    layer = sc.allset_anim_layers[sc.allset_anim_layer_index].name
    assert al.key(ob, "location", 0, frame=12, value=clip + 3.0, scene=sc)
    names = [tr.name for tr in ob.animation_data.nla_tracks]
    assert names.index(tc.clip_tracks(ob)[0].name) < names.index(al.BASE) < names.index(layer), names
    assert abs(x_at(sc, ob, 12) - (clip + 3.0)) < 1e-4, "the layer adds on top of the clip"
    # a new clip instance still goes below the layer tracks, layer settings kept
    sc.frame_current = 60
    bpy.ops.allset.trax_insert_clip(source="clip1Source")
    names = [tr.name for tr in ob.animation_data.nla_tracks]
    assert max(names.index(t.name) for t in tc.clip_tracks(ob)) < names.index(al.BASE), names
    assert abs(x_at(sc, ob, 12) - (clip + 3.0)) < 1e-4
    # a layered object's keys stay in its layers
    assert bpy.ops.allset.trax_create_clip() == {'CANCELLED'}


def test_one_undo_step():
    sc, (ob,) = scene()
    bpy.ops.ed.undo_push(message="test start")
    assert bpy.ops.allset.trax_create_clip('EXEC_DEFAULT', True) == {'FINISHED'}
    assert "clip1Source" in bpy.data.actions
    bpy.ops.ed.undo()
    ob = bpy.data.objects["pCube1"]
    assert "clip1Source" not in bpy.data.actions and ob.animation_data.action is not None
    assert not ob.animation_data.nla_tracks
    for cls in (bpy.types.ALLSET_OT_trax_create_clip, bpy.types.ALLSET_OT_trax_clip_edit,
                bpy.types.ALLSET_OT_trax_insert_clip, bpy.types.ALLSET_OT_trax_tracks):
        assert cls.bl_options == {'UNDO'}, "no Adjust Last Operation panel (Maya has none)"


def test_menus_and_option_window():
    mm = import_module(kit.MODULE + ".ui.menu_map")
    ow = import_module(kit.MODULE + ".operators.option_windows")
    em = import_module(kit.MODULE + ".ui.editor_menu_data")
    assert [t for t, _i in em.EDITORS["Trax Editor"]] == ["File", "Edit", "View", "Modify", "Create", "Library",
                                                          "List", "Help"]
    for path in ("Trax Editor/Create/Animation Clip", "Trax Editor/Edit/Duplicate", "Trax Editor/Create/Blend",
                 "Trax Editor/Library/Insert Clip", "Windows/Animation Editors/Trax Editor",
                 "Edit/Delete All by Type/Clips", "Playback/Set Range to/Enabled Clips"):
        assert path in mm.MAP, path
    w = ow.find_path("Trax Editor/Create/Animation Clip")
    assert w is not None and w.title == "Create Clip Options"
    assert w.defaults()["name"] == "clip1" and w.defaults()["time_range"] == "Animation curve"
    sc, (ob,) = scene()
    assert bpy.ops.allset.menu_item(item="Trax Editor/Create/Animation Clip") == {'FINISHED'}
    assert tc.instance_names(sc) == ["clip1"]
    sc.frame_current = 50
    bpy.ops.allset.trax_insert_clip(source="clip1Source")
    bpy.ops.allset.menu_item(item="Playback/Set Range to/Enabled Clips")
    assert sc.use_preview_range and (sc.frame_preview_start, sc.frame_preview_end) == (1, 73)
    bpy.ops.allset.menu_item(item="Edit/Delete All by Type/Clips")
    assert not tc.sources() and not tc.instance_names(sc)
