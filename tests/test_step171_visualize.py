"""Visualize > Create Animation Snapshot / Update Snapshot and ghosting (Ghost Selected / Unghost Selected /
Unghost All / Ghosting Editor). Maya rules.

Maya points are Y-up: Maya (x, y, z) = Blender (x, -z, y); Maya rotateY = Blender rotation Z (same sign)."""

import importlib.util
import math
import os
from importlib import import_module

import bpy

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
snap = import_module(kit.MODULE + ".operators.anim_snapshot")
ghosting = import_module(kit.MODULE + ".ui.ghosting")
option_windows = import_module(kit.MODULE + ".operators.option_windows")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")


def maya(p):
    """Maya Y-up point -> Blender Z-up."""
    return (p[0], -p[2], p[1])


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for d in list(bpy.data.meshes):
        bpy.data.meshes.remove(d)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 24
    scene.use_preview_range = False
    scene.frame_set(1)


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[-1] if obs else None


def _cube(name="pCube1"):
    import bmesh
    me = bpy.data.meshes.new(name + "Shape")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _key_linear(ob):
    for fc in kit.fcurves(ob):
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'


def _anim_cube(rotate=True, tx_end=9.0):
    """Maya anim_cube: translateX 0 -> 9 and rotateY 0 -> 90 over frames 1 -> 10, linear."""
    ob = _cube()
    for f, x, r in ((1, 0.0, 0.0), (10, tx_end, 90.0)):
        ob.location.x = x
        ob.keyframe_insert("location", index=0, frame=f)
        if rotate:
            ob.rotation_euler.z = math.radians(r)
            ob.keyframe_insert("rotation_euler", index=2, frame=f)
    _key_linear(ob)
    bpy.context.scene.frame_set(1)
    return ob


def _vid(ob, p=(-0.5, -0.5, -0.5)):
    """Index of the source vertex at Blender point ``p`` (the vtx[0] corner (-0.5, -0.5, 0.5))."""
    return min(range(len(ob.data.vertices)), key=lambda i: (ob.data.vertices[i].co - __import__("mathutils").Vector(p)).length)


def _close(a, b, tol=1e-4):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# --- Create Animation Snapshot -------------------------------------------------------------------------------------

def test_snapshot_names_count_and_maya_vertices():
    _clear()
    cube = _anim_cube()
    i0 = _vid(cube)
    bpy.context.scene.frame_set(5)
    _select(cube)
    assert bpy.ops.allset.animation_snapshot() == {'FINISHED'}
    grp = bpy.data.objects["snapshot1Group"]
    copies = snap.copies_of(grp)
    assert [c.name for c in copies] == [f"transform1_{k}" for k in range(1, 11)]
    assert [c.data.name for c in copies] == [f"transform1_Shape{k}" for k in range(1, 11)]
    assert all(c.parent == grp and c.matrix_world == __import__("mathutils").Matrix.Identity(4) for c in copies)
    # Maya: source vertex 0 by frame (frames 1, 2, 5, 10), Maya Y-up
    for frame, p in ((1, (-0.5, -0.5, 0.5)), (2, (0.59442, -0.5, 0.57923)), (5, (3.93837, -0.5, 0.70442)),
                     (10, (9.5, -0.5, 0.5))):
        co = copies[frame - 1].data.vertices[i0].co
        assert _close(co, maya(p)), (frame, tuple(co), maya(p))
    assert bpy.context.scene.frame_current == 5                    # Maya: current time unchanged
    assert list(bpy.context.selected_objects) == [cube]            # Maya: selection stays the source
    rec = grp[snap.RECORD]
    assert (rec["start"], rec["end"], rec["increment"], rec["update"]) == (1.0, 10.0, 1.0, "animCurve")
    # a second snapshot counts up (Maya snapshot2Group / transform2_k)
    _select(cube)
    assert bpy.ops.allset.animation_snapshot() == {'FINISHED'}
    assert snap.copies_of(bpy.data.objects["snapshot2Group"])[0].name == "transform2_1"


def test_snapshot_increment_and_frames():
    assert snap.sample_frames(1, 10, 1) == [float(f) for f in range(1, 11)]
    assert snap.sample_frames(1, 10, 3) == [1.0, 4.0, 7.0, 10.0]
    assert snap.sample_frames(1, 4, 1.5) == [1.0, 2.5, 4.0]
    _clear()
    cube = _anim_cube()
    i0 = _vid(cube)
    _select(cube)
    assert bpy.ops.allset.animation_snapshot(increment=3.0) == {'FINISHED'}
    copies = snap.copies_of(bpy.data.objects["snapshot1Group"])
    assert len(copies) == 4
    maya_tx = [(-0.5, -0.5, 0.5), (2.81699, -0.5, 0.68301), (6.18301, -0.5, 0.68301), (9.5, -0.5, 0.5)]
    for c, p in zip(copies, maya_tx):
        assert _close(c.data.vertices[i0].co, maya(p)), (c.name, tuple(c.data.vertices[i0].co))


def test_snapshot_time_slider_range_and_two_objects():
    _clear()
    a = _anim_cube()
    b = _cube("pSphere1")
    b.keyframe_insert("location", index=2, frame=1)
    b.location.z = 3
    b.keyframe_insert("location", index=2, frame=10)
    scene = bpy.context.scene
    scene.use_preview_range = True
    scene.frame_preview_start, scene.frame_preview_end = 1, 4         # Maya playback range = preview range
    _select(a, b)
    assert bpy.ops.allset.animation_snapshot(time_slider=True) == {'FINISHED'}
    g1, g2 = bpy.data.objects["snapshot1Group"], bpy.data.objects["snapshot2Group"]
    assert len(g1.children) == len(g2.children) == 4                   # Maya: two objects, time slider range
    assert {g1[snap.SOURCE], g2[snap.SOURCE]} == {a, b}


def test_snapshot_world_space_of_a_child_in_an_animated_group():
    _clear()
    cube = _cube()
    grp = bpy.data.objects.new("group1", None)
    bpy.context.scene.collection.objects.link(grp)
    cube.parent = grp
    grp.location.z = 0
    grp.keyframe_insert("location", index=2, frame=1)
    grp.location.z = 9
    grp.keyframe_insert("location", index=2, frame=10)
    _key_linear(grp)
    i0 = _vid(cube)
    _select(cube)
    assert bpy.ops.allset.animation_snapshot() == {'FINISHED'}
    last = snap.copies_of(bpy.data.objects["snapshot1Group"])[-1]
    assert last.parent.parent is None                                   # the group is top level (Maya: world)
    assert _close(last.data.vertices[i0].co, maya((-0.5, 8.5, 0.5)))    # Maya: child in a group, last vertex
    # selecting the group itself snapshots the geometry under it
    _select(grp)
    assert bpy.ops.allset.animation_snapshot() == {'FINISHED'}
    assert "snapshot2Group" in bpy.data.objects


def test_no_geometry_error():
    _clear()
    loc = bpy.data.objects.new("locator1", None)
    bpy.context.scene.collection.objects.link(loc)
    _select(loc)
    try:
        bpy.ops.allset.animation_snapshot()
    except RuntimeError as ex:
        assert snap.NO_GEOMETRY in str(ex), ex
    else:
        raise AssertionError("expected Maya's 'No geometry found to create snapshot.'")
    _select()
    try:
        bpy.ops.allset.animation_snapshot()
    except RuntimeError as ex:
        assert snap.NO_GEOMETRY in str(ex)
    assert not snap.all_groups()


def test_smooth_preview_is_left_out():
    _clear()
    cube = _anim_cube(rotate=False)
    display = import_module(kit.MODULE + ".operators.display")
    display.set_smooth_preview(cube, 2)
    _select(cube)
    assert bpy.ops.allset.animation_snapshot(end=2.0) == {'FINISHED'}
    copy = snap.copies_of(bpy.data.objects["snapshot1Group"])[0]
    assert len(copy.data.vertices) == 8, len(copy.data.vertices)        # Maya worldMesh = the base cage
    assert display.preview_modifier(cube, create=False).show_viewport   # the preview is back on


# --- Update Snapshot -----------------------------------------------------------------------------------------------

def _last_vtx(grp, i0):
    return tuple(snap.copies_of(grp)[-1].data.vertices[i0].co)


def test_update_snapshot_menu_and_selection_rules():
    _clear()
    cube = _anim_cube(rotate=False)
    i0 = _vid(cube)
    _select(cube)
    bpy.ops.allset.animation_snapshot()
    grp = bpy.data.objects["snapshot1Group"]
    assert _close(_last_vtx(grp, i0), maya((8.5, -0.5, 0.5)))
    cube.scale.z = 3.0                                                  # a non-animated edit (Maya: scaleY 3)
    for target in (grp, snap.copies_of(grp)[0], cube):                  # group, a copy or the source
        _select(target)
        assert bpy.ops.allset.update_snapshot() == {'FINISHED'}
        assert _close(_last_vtx(grp, i0), maya((8.5, -1.5, 0.5))), _last_vtx(grp, i0)
    assert [c.name for c in snap.copies_of(grp)] == [f"transform1_{k}" for k in range(1, 11)]
    assert snap.copies_of(grp)[0].data.name == "transform1_Shape1"
    assert not [m for m in bpy.data.meshes if m.users == 0]            # old copies' meshes are gone
    _select()
    try:
        bpy.ops.allset.update_snapshot()
    except RuntimeError:
        pass
    # deleting the source keeps the copies (Maya after_delete_source = 10)
    bpy.data.objects.remove(cube)
    assert len(grp.children) == 10
    _select(grp)
    assert bpy.ops.allset.update_snapshot() == {'FINISHED'}


def test_fast_update_follows_key_edits_only():
    _clear()
    cube = _anim_cube(rotate=False)
    i0 = _vid(cube)
    _select(cube)
    bpy.ops.allset.animation_snapshot()
    grp = bpy.data.objects["snapshot1Group"]
    snap._pending.clear()
    # a key edit: translateZ 0 -> 5 (Maya after the key = (8.5, -0.5, 5.5))
    cube.keyframe_insert("location", index=1, frame=1)
    cube.location.y = -5.0
    cube.keyframe_insert("location", index=1, frame=10)
    _key_linear(cube)
    cube.animation_data.action.update_tag()
    bpy.context.view_layer.update()
    assert grp.session_uid in snap._pending
    snap._rebuild_pending()
    assert _close(_last_vtx(grp, i0), maya((8.5, -0.5, 5.5))), _last_vtx(grp, i0)
    # Evaluate Nodes > Snapshots off: no automatic update
    bpy.context.scene.allset_eval.snapshot = False
    snap._pending.clear()
    cube.animation_data.action.update_tag()
    bpy.context.view_layer.update()
    assert not snap._pending
    bpy.context.scene.allset_eval.snapshot = True
    # On demand snapshots never update by themselves
    _select(cube)
    bpy.ops.allset.animation_snapshot(update="demand")
    snap._pending.clear()
    cube.animation_data.action.update_tag()
    bpy.context.view_layer.update()
    assert bpy.data.objects["snapshot2Group"].session_uid not in snap._pending


# --- ghosting ------------------------------------------------------------------------------------------------------

def test_ghost_frames_match_maya():
    gf = ghosting.ghost_frames
    f = lambda rows: [r[0] for r in rows]      # noqa: E731
    keys = (1, 4, 8, 12, 20, 30)               # Maya case keys
    assert f(gf(10, "Pre And Post Frames")) == [9, 8, 7, 11, 12, 13]
    assert sorted(f(gf(1, "Pre And Post Frames"))) == [-2, -1, 0, 2, 3, 4]       # not clipped to the range
    assert sorted(f(gf(5, "Pre Frames"))) == [2, 3, 4] and sorted(f(gf(5, "Post Frames"))) == [6, 7, 8]
    for step, want in ((2, [6, 8, 10, 14, 16, 18]), (4, [0, 4, 8, 16, 20, 24]), (5, [-3, 2, 7, 17, 22, 27]),
                       (10, [-18, -8, 2, 22, 32, 42])):
        assert sorted(f(gf(12, "Pre And Post Frames", step=step))) == want, step
    assert sorted(f(gf(10, "Pre And Post Keyframes", keys=keys))) == [1, 4, 8, 12, 20, 30]
    assert sorted(f(gf(25, "Pre And Post Keyframes", keys=keys))) == [8, 12, 20, 30]
    assert sorted(f(gf(10, "All Keyframes", keys=keys, play_range=(1, 24)))) == [1, 4, 8, 12, 20]
    assert sorted(f(gf(10, "Custom Frames", custom=(3, 7, 15)))) == [3, 7, 15]
    assert ghosting.parse_frames("3, 7,15") == [3.0, 7.0, 15.0]
    assert ghosting.preset_steps({"preset": "4s"}) == (3, 3, 4)
    assert ghosting.preset_steps({"preset": "Custom", "custom_pre": 2, "custom_post": 5, "custom_step": 3}) == (2, 5, 3)
    # opacity: wireframe alpha 127 / 83 / 38 of 255 for the 1st / 2nd / 3rd ghost (Maya)
    for k, alpha in ((1, 127), (2, 83), (3, 38)):
        assert abs(ghosting.opacity(k, 3) * 255 - alpha) < 1.0, (k, ghosting.opacity(k, 3) * 255)
    # shaded: front + back face = 1 - (1 - a)^2 -> 191 / 139 / 71
    for k, alpha in ((1, 191), (2, 139), (3, 71)):
        a = ghosting.opacity(k, 3)
        assert abs((1 - (1 - a) ** 2) * 255 - alpha) < 1.0


def test_ghost_selected_hierarchy_and_unghost():
    _clear()
    cube = _anim_cube()
    sphere = _cube("pSphere1")
    sphere.parent = cube
    other = _cube("pCube2")
    _select(cube)
    assert bpy.ops.allset.ghost(action="GHOST") == {'FINISHED'}
    assert cube.allset_ghost.enabled and sphere.allset_ghost.enabled and not other.allset_ghost.enabled
    g = cube.allset_ghost
    assert (g.mode, g.pre_frames, g.post_frames, g.step) == ("PRE_POST", 3, 3, 1)
    assert _close(g.color_pre, (0.447, 1.0, 1.0), 1e-6) and _close(g.color_post, (0.878, 0.678, 0.663), 1e-6)
    assert (round(g.near_opacity, 6), round(g.far_opacity, 6)) == (0.5, 0.15)
    bpy.context.scene.frame_set(5)
    assert sorted(f for f, *_r in ghosting.frames_for(cube, bpy.context.scene)) == [2, 3, 4, 6, 7, 8]
    _select(cube)
    assert bpy.ops.allset.ghost(action="UNGHOST") == {'FINISHED'}
    assert not cube.allset_ghost.enabled and not sphere.allset_ghost.enabled
    _select(cube, other)
    bpy.ops.allset.ghost(action="GHOST")
    _select()
    assert bpy.ops.allset.ghost(action="UNGHOST_ALL") == {'FINISHED'}
    assert not any(o.allset_ghost.enabled for o in bpy.data.objects)


def test_ghost_geometry_cache_at_offset_frames():
    _clear()
    cube = _anim_cube()
    _select(cube)
    bpy.ops.allset.ghost(action="GHOST")
    scene = bpy.context.scene
    scene.frame_set(5)
    ghosting.drop()
    assert ghosting.fill(bpy.context) == 6
    assert scene.frame_current == 5
    tris, nrms, edges = ghosting._geom[(cube.session_uid, 2.0)]
    assert len(tris) == 12 * 3 and len(edges) == 12 * 2 and len(nrms) == len(tris)
    want = maya((0.59442, -0.5, 0.57923))                                 # Maya vtx[0] at frame 2
    assert min(sum((a - b) ** 2 for a, b in zip(p, want)) for p in tris) < 1e-8
    assert ghosting.fill(bpy.context) == 0                               # cached
    scene.frame_set(6)
    assert ghosting.fill(bpy.context) == 2                               # only frames 5 and 9 are new
    # moving the source drops its ghosts
    cube.location.y = 1.0
    bpy.context.view_layer.update()
    assert not any(k[0] == cube.session_uid for k in ghosting._geom)


def test_ghost_colours():
    lin = ghosting.to_linear((0.447, 1.0, 1.0), 1.0)
    assert lin[0] < 0.1 and lin[1] > 1.0 and lin[2] > 1.0               # ACEScg cyan -> Rec.709: red ~0
    lin = ghosting.to_linear((0.878, 0.678, 0.663), 1.0)
    assert abs(lin[0] - 1.02) < 0.01 and abs(lin[1] - 0.652) < 0.01


# --- windows / menus -----------------------------------------------------------------------------------------------

def test_option_windows_have_maya_defaults():
    w = option_windows.find_path("Visualize/Create Animation Snapshot")
    assert w is not None and w.title == "Animation Snapshot Options" and w.action == "Snapshot"
    d = w.defaults()
    assert (d["time_range"], d["start"], d["end"], d["increment"]) == ("Start/End", 1.0, 10.0, 1.0)
    assert d["update"] == "Fast (update only when keyframes change)"
    ed = option_windows._BY_KEY["ghosting_editor"]
    assert ed.title == "Ghosting Editor" and ed.action == "Create Ghost from Selection"
    e = ed.defaults()
    assert (e["mode"], e["preset"], e["near_opacity"], e["far_opacity"]) == ("Pre And Post Frames", "1s", 0.5, 0.15)
    assert hasattr(bpy.ops.allset, "opt_ghosting_editor")
    # the window's command with its values
    _clear()
    cube = _anim_cube()
    _select(cube)
    assert option_windows.run(w, bpy.context, {"increment": 3.0}) == {'FINISHED'}
    assert len(bpy.data.objects["snapshot1Group"].children) == 4
    assert option_windows.run(ed, bpy.context, {"preset": "2s", "mode": "Pre Frames"}) == {'FINISHED'}
    assert (cube.allset_ghost.step, cube.allset_ghost.mode) == (2, "PRE")
    ed.apply_run(bpy.context, {**ed.defaults(), "near_opacity": 0.8})
    assert abs(cube.allset_ghost.near_opacity - 0.8) < 1e-6 and cube.allset_ghost.step == 1


def test_visualize_menu_at_least_sixty_percent():
    spec = importlib.util.spec_from_file_location("tool_menu_count", os.path.join(ROOT, "tools", "menu_count.py"))
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    md = import_module(kit.MODULE + ".ui.menu_data")
    _label, _set, _src, items = md.MENUS["mainVisualizeMenu"]
    paths = [p for p, _it in mc.leaves(md, menu_map, items, "Visualize")]
    working = sum(1 for p in paths if p in menu_map.MAP)
    print(f"Visualize: {working} / {len(paths)} working ({100 * working / len(paths):.0f} %)")
    assert working / len(paths) >= 0.60, (working, len(paths))
    for path in ("Visualize/Create Turntable...", "Visualize/Create Animated Sweep"):
        assert path not in menu_map.MAP and notices.greyed_notice(path), path
    kind, target, _p = menu_map.normalize(menu_map.MAP["Modify/Evaluate Nodes/Snapshots"])
    assert (kind, target) == ("prop", "scene.allset_eval.snapshot")
