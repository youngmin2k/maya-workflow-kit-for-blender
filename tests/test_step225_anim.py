"""Issue #135: Game Exporter clips and the Motion Trail Editor.

Maya: gameFbxExporter default values, a new clip =
the playback range with an empty name, one file = a take per clip (walk 1-10, run 11-24), a file per clip = file name
prefix + clip name ("hero_walk.fbx"). Maya also writes the plug-in's "Take 001" and repeats earlier clips in later
clip files — the kit writes only the clips' own takes (documented in operators/game_exporter.py).
Motion trail: default settings and their round trip through Blender motion paths."""

import math
import os
from importlib import import_module

import bpy

import kit

ge = import_module(kit.MODULE + ".operators.game_exporter")
mt = import_module(kit.MODULE + ".operators.motion_trail")
fbx_rig = import_module(kit.MODULE + ".operators.fbx_rig")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp", "test_step225")

# gameFbxExporter createNode values (Maya "attrs")
MAYA_NODE = {"exportTypeIndex": 1, "exportSetIndex": 1, "modelFileMode": 1, "fileSplitType": 1, "bakeAnimation": True,
             "skinning": True, "blendshapes": True, "smoothingGroups": True, "tangentsBinormals": True,
             "triangulate": False, "moveToOrigin": False, "embedMedia": False, "includeChildren": False,
             "inputConnections": False, "upAxis": 1, "includeCameras": True, "includeLights": True}
NODE_TO_KIT = {"exportTypeIndex": ("export_type", {1: 'MODEL', 2: 'ANIMATION'}),
               "exportSetIndex": ("export_set", {1: 'ALL', 2: 'SELECTION'}),
               "modelFileMode": ("model_file_mode", {1: 'SINGLE', 2: 'PER_ROOT'}),
               "fileSplitType": ("file_split", {1: 'SINGLE', 2: 'PER_CLIP'}),
               "bakeAnimation": ("bake_animation", None), "skinning": ("skinning", None),
               "blendshapes": ("blendshapes", None), "smoothingGroups": ("smoothing_groups", None),
               "tangentsBinormals": ("tangents", None), "triangulate": ("triangulate", None),
               "moveToOrigin": ("move_to_origin", None), "embedMedia": ("embed_media", None),
               "includeChildren": ("include_children", None), "inputConnections": ("input_connections", None),
               "upAxis": ("up_axis", {1: 'Y', 2: 'Z'}), "includeCameras": ("include_cameras", None),
               "includeLights": ("include_lights", None)}
MAYA_NEW_CLIP = {"animClipName": None, "animClipStart": 1.0, "animClipEnd": 24.0, "exportAnimClip": True}
MAYA_CLIPS = [("walk", 1.0, 10.0), ("run", 11.0, 24.0)]
MAYA_SINGLE = {"file": "anim.fbx", "takes": [["walk", 1.0, 10.0], ["run", 11.0, 24.0]]}      # minus Take 001
MAYA_PER_CLIP = [{"file": "hero_walk.fbx", "take": ["walk", 1.0, 10.0]},
                 {"file": "hero_run.fbx", "take": ["run", 11.0, 24.0]}]
KTIME = 46186158000


def _clear():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.use_preview_range = 1, 24, False
    sc.render.fps, sc.render.fps_base = 24, 1.0
    s = sc.allset_game_exporter
    s.clips.clear()
    return sc


def _rig(sc, mesh_too=False):
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    sc.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    a = arm.data.edit_bones.new("root")
    a.head, a.tail = (0, 0, 0), (0, 0, 0.05)
    b = arm.data.edit_bones.new("spine")
    b.head, b.tail, b.parent = (0, 0, 0.05), (0, 0, 0.1), a
    bpy.ops.object.mode_set(mode='POSE')
    pb = arm.pose.bones["spine"]
    pb.rotation_mode = 'XYZ'
    for f, deg in ((1, 0), (10, 45), (24, -30)):
        pb.rotation_euler = (0, 0, math.radians(deg))
        pb.keyframe_insert("rotation_euler", frame=f)
    bpy.ops.object.mode_set(mode='OBJECT')
    obs = [arm]
    if mesh_too:
        bpy.ops.mesh.primitive_cube_add(size=0.02, location=(0.1, 0, 0))
        cube = bpy.context.active_object
        for f, x in ((1, 0.1), (24, 0.3)):
            cube.location.x = x
            cube.keyframe_insert("location", frame=f)
        obs.append(cube)
    return obs


def _takes(path):
    tree, _v = fbx_rig.load(path)
    out = []
    for st in tree.first(b"Objects").find(b"AnimationStack"):
        props = {p.props[0]: p.props[4] for p in fbx_rig._p70(st).elems if p.props and len(p.props) > 4}
        out.append([fbx_rig.name_of(st), round(props.get(b"LocalStart", 0) / KTIME * 24, 4),
                    round(props.get(b"LocalStop", 0) / KTIME * 24, 4)])
    return out


# --- Game Exporter -----------------------------------------------------------------------------------------------

def test_game_exporter_factory_equals_maya_node():
    # the node's createNode values (FACTORY), then the window's first-open presets ("Model Default" /
    # "Anim Default" presets) — what the kit's fields start with
    sc = _clear()
    s = bpy.data.scenes.new("ge_fresh").allset_game_exporter
    for attr, maya in MAYA_NODE.items():
        name, table = NODE_TO_KIT[attr]
        want = table[maya] if table else maya
        assert want == ge.FACTORY[name], (attr, want)
        model = ge.PRESET_MODEL.get(name, want)
        if name == "file_split":
            model = ge.PRESET_ANIM[name]                          # an Animation Clips tab field
        assert getattr(s, name) == model, (attr, getattr(s, name), model)
        if name in ge.TAB_PROPS:
            assert getattr(s, "anim_" + name) == ge.PRESET_ANIM.get(name, want), (attr, "anim")
    assert ge.PRESET_MODEL == {"embed_media": True, "include_children": True, "input_connections": True}
    assert ge.PRESET_ANIM == {"file_split": 'PER_CLIP', "embed_media": True, "include_cameras": False,
                              "include_children": False, "input_connections": False}
    bpy.data.scenes.remove(bpy.data.scenes["ge_fresh"])


def test_new_clip_is_the_playback_range():
    sc = _clear()
    clip = ge.add_clip(sc)
    assert (clip.name, clip.start, clip.end, clip.export) == ("", MAYA_NEW_CLIP["animClipStart"],
                                                             MAYA_NEW_CLIP["animClipEnd"], True)
    sc.use_preview_range, sc.frame_preview_start, sc.frame_preview_end = True, 5, 12
    clip = ge.add_clip(sc)
    assert (clip.start, clip.end) == (5.0, 12.0)                 # Maya playback range = the preview range


def test_unique_clip_names_like_maya():
    for name, taken, want in (("walk", {"walk"}, "walk1"), ("walk1", {"walk1"}, "walk2"),
                              ("run09", {"run09"}, "run10"), ("run99", {"run99"}, "run100"),
                              ("take0010", {"take0010"}, "take0011"), ("a009", {"a009"}, "a010"),
                              ("walk", {"walk", "walk1"}, "walk2"), ("idle", set(), "idle")):
        assert ge.unique_name(name, taken) == want, (name, ge.unique_name(name, taken), want)


def _clips(sc):
    s = sc.allset_game_exporter
    for name, a, b in MAYA_CLIPS:
        c = ge.add_clip(sc)
        c.name, c.start, c.end = name, a, b
    return s


def test_clip_file_names_like_maya():
    sc = _clear()
    s = _clips(sc)
    s.export_filename, s.file_split = "anim", 'SINGLE'
    files = ge.clip_files(s, "X")
    assert [(os.path.basename(p), [c.name for c in cl]) for p, cl in files] == [("anim.fbx", ["walk", "run"])]
    s.export_filename, s.file_split = "hero_", 'PER_CLIP'
    files = ge.clip_files(s, "X")
    assert [os.path.basename(p) for p, _c in files] == [d["file"] for d in MAYA_PER_CLIP]
    s.clips[0].export = False                                    # unchecked clips are skipped (Maya exportAnimClip)
    assert [os.path.basename(p) for p, _c in ge.clip_files(s, "X")] == ["hero_run.fbx"]


def test_export_single_file_takes():
    sc = _clear()
    _rig(sc)
    s = _clips(sc)
    os.makedirs(OUT, exist_ok=True)
    s.export_type, s.export_path, s.export_filename, s.file_split = 'ANIMATION', OUT, "anim", 'SINGLE'
    done = ge.export(bpy.context, s)
    assert [os.path.basename(p) for p, _t in done] == [MAYA_SINGLE["file"]]
    assert _takes(done[0][0]) == MAYA_SINGLE["takes"], _takes(done[0][0])
    tree, _v = fbx_rig.load(done[0][0])
    first = sorted({int(c.first(b"KeyTime").props[0][0]) for c in tree.first(b"Objects").find(b"AnimationCurve")})
    assert first == [KTIME // 24, KTIME * 11 // 24], first      # keys at the clip frames (1 and 11)
    arm = bpy.data.objects["skeleton1"]
    assert not arm.animation_data.nla_tracks and arm.animation_data.action is not None   # temporary tracks gone


def test_export_clip_files():
    sc = _clear()
    _rig(sc)
    s = _clips(sc)
    s.export_type, s.export_path, s.export_filename, s.file_split = 'ANIMATION', OUT, "hero_", 'PER_CLIP'
    done = ge.export(bpy.context, s)
    assert [os.path.basename(p) for p, _t in done] == [d["file"] for d in MAYA_PER_CLIP]
    for (path, _t), want in zip(done, MAYA_PER_CLIP):
        assert _takes(path) == [want["take"]], (path, _takes(path))


def test_two_animated_objects_share_one_take_per_clip():
    sc = _clear()
    _rig(sc, mesh_too=True)
    s = _clips(sc)
    s.export_type, s.export_path, s.export_filename, s.file_split = 'ANIMATION', OUT, "two", 'SINGLE'
    done = ge.export(bpy.context, s)
    assert _takes(done[0][0]) == MAYA_SINGLE["takes"], _takes(done[0][0])


def test_export_errors_like_maya():
    sc = _clear()
    _rig(sc)
    s = _clips(sc)
    s.export_type, s.export_path, s.export_filename = 'ANIMATION', "", "anim"
    for path, name, msg in (("", "anim", "path is empty"), (os.path.join(OUT, "nope"), "anim", "doesn't exist"),
                            (OUT, "", "Choose a file name to export")):
        s.export_path, s.export_filename = path, name
        try:
            ge.export(bpy.context, s)
            raise AssertionError("no error")
        except ValueError as ex:
            assert msg in str(ex), (msg, str(ex))


# --- Motion Trail Editor -----------------------------------------------------------------------------------------

def test_motion_trail_factory_equals_maya():
    sc = _clear()
    vals = mt.values(sc.allset_motion_trail)
    assert vals == mt.FACTORY, {k: (vals[k], mt.FACTORY[k]) for k in vals if vals[k] != mt.FACTORY[k]}
    assert vals["draw_mode"] == 'PAST_FUTURE' and vals["path_mode"] == 'BEFORE_AFTER' and vals["thickness"] == 2
    assert vals["trail_color"] == (0.49, 0.098, 0.125) and vals["alt_color"] == (0.125, 0.098, 0.49)


def _animated_cube(sc):
    bpy.ops.mesh.primitive_cube_add(size=0.1)
    cube = bpy.context.active_object
    for f, x in ((1, 0.0), (24, 1.0)):
        cube.location.x = x
        cube.keyframe_insert("location", frame=f)
    return cube


def test_create_motion_trail_time_slider_range():
    sc = _clear()
    mt.set_values(sc.allset_motion_trail, mt.FACTORY)
    cube = _animated_cube(sc)
    assert bpy.ops.allset.motion_trail(action='CREATE') == {'FINISHED'}
    mp, viz = cube.motion_path, cube.animation_visualization.motion_path
    assert mp is not None
    assert viz.type == 'RANGE' and (viz.frame_start, viz.frame_end) == (1, 24) and viz.frame_step == 1
    assert mp.frame_start == 1 and mp.frame_end in (24, 25)        # Blender stores the end one past
    assert mp.line_thickness == 2 and mp.use_custom_color
    still = bpy.data.objects.new("still", None)
    sc.collection.objects.link(still)
    for o in sc.objects:
        o.select_set(o == still)
    bpy.context.view_layer.objects.active = still
    assert bpy.ops.allset.motion_trail(action='CREATE') == {'CANCELLED'}        # Maya warns: no animation
    assert still.motion_path is None
    for o in sc.objects:
        o.select_set(o == cube)
    assert bpy.ops.allset.motion_trail(action='DELETE_SELECTED') == {'FINISHED'}
    assert cube.motion_path is None


def test_motion_trail_options_round_trip():
    cases = [{}, {"path_mode": 'BEFORE', "pre_frames": 5.0}, {"path_mode": 'AFTER', "post_frames": 3.0},
             {"path_mode": 'BEFORE_AFTER', "pre_frames": 4.0, "post_frames": 6.0}, {"increment": 2.0},
             {"show_keys": False, "show_key_numbers": False, "show_frame_numbers": True},
             {"draw_mode": 'CONSTANT', "trail_color": (0.2, 0.4, 0.6)},
             {"draw_mode": 'PAST_FUTURE', "trail_color": (0.9, 0.1, 0.1), "alt_color": (0.1, 0.1, 0.9)},
             {"path_mode": 'BEFORE', "pre_frames": 0.0}]
    for case in cases:
        sc = _clear()
        s = sc.allset_motion_trail
        mt.set_values(s, mt.FACTORY)
        mt.set_values(s, case)
        cube = _animated_cube(sc)
        assert bpy.ops.allset.motion_trail(action='CREATE') == {'FINISHED'}, case
        mp = cube.motion_path
        back = mt.from_blender(cube.animation_visualization.motion_path, sc, (mp.color, mp.color_post))
        want = mt.values(s)
        bad = {k: (v, want[k]) for k, v in back.items() if (tuple(round(c, 6) for c in v) if isinstance(v, tuple)
                                                            else v) != want[k]}
        assert not bad, (case, bad)


def test_reset_and_save_default():
    sc = _clear()
    s = sc.allset_motion_trail
    s.thickness, s.increment = 5, 3.0
    assert bpy.ops.allset.motion_trail(action='SAVE_DEFAULT') == {'FINISHED'}
    ow = import_module(kit.MODULE + ".operators.option_windows")
    assert ow.saved(mt.SAVE_KEY)["thickness"] == 5
    assert bpy.ops.allset.motion_trail(action='RESET') == {'FINISHED'}
    assert mt.values(s) == mt.FACTORY
    ow.store(mt.SAVE_KEY, None)


def test_menu_items():
    assert menu_map.MAP["Visualize/Motion Trail Editor"] == "allset.motion_trail_editor"
    assert menu_map.MAP["File/Game Exporter"] == "allset.game_exporter"
