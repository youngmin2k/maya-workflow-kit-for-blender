"""Issue #140: Game Exporter clip files are the same rig FBX as File > Export Selection.

Audit 0.5.0 (③-16 / ⑤-9): a clip file had joints at
1/100 size and the mirrored chain in the wrong place, and kit animation layers (NLA tracks) leaked into the file as
extra takes. Truth = the kit's own joint world positions per frame (Blender -> Maya axes, cm).
"""

import math
import os
from importlib import import_module

import bpy
from mathutils import Vector

import kit

ge = import_module(kit.MODULE + ".operators.game_exporter")
fbx_rig = import_module(kit.MODULE + ".operators.fbx_rig")
units = import_module(kit.MODULE + ".operators.units")

OUT = os.path.join(os.environ.get("ALLSET_TEST_OUT", bpy.app.tempdir), "step231")
KTIME = 46186158000
# an arm and its mirror (Maya Mirror Joints YZ: a second root chain in the same skeleton), cm, Maya axes
LEFT = (("joint1", (5, 10, 0)), ("joint2", (12, 10, -1)), ("joint3", (19, 10, 0)))
RIGHT = (("joint4", (-5, 10, 0)), ("joint5", (-12, 10, -1)), ("joint6", (-19, 10, 0)))


def _bl(p, k):
    return Vector((p[0], -p[2], p[1])) * k            # Maya (x, y, z) -> Blender (x, -z, y)


def _scene():
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    sc = bpy.context.scene
    sc.unit_settings.system, sc.unit_settings.length_unit = 'METRIC', 'CENTIMETERS'   # the kit template
    sc.frame_start, sc.frame_end, sc.use_preview_range = 1, 20, False
    sc.render.fps, sc.render.fps_base = 24, 1.0
    sc.allset_game_exporter.clips.clear()
    return sc


def _rig(sc):
    k = units.maya_unit(sc)
    arm = bpy.data.objects.new("skeleton1", bpy.data.armatures.new("skeleton1"))
    sc.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for chain in (LEFT, RIGHT):
        prev = None
        for i, (name, p) in enumerate(chain):
            eb = arm.data.edit_bones.new(name)
            eb.head = _bl(p, k)
            eb.tail = _bl(chain[i + 1][1], k) if i + 1 < len(chain) else _bl(p, k) + (_bl(p, k) - prev.head) * 0.3
            if prev is not None:
                eb.parent, eb.use_connect = prev, True
            prev = eb
    bpy.ops.object.mode_set(mode='POSE')
    for name, frames in (("joint1", ((1, 0.0), (10, 40.0), (20, -20.0))), ("joint2", ((1, 0.0), (20, 60.0))),
                         ("joint4", ((1, 0.0), (15, -35.0))), ("joint5", ((1, 10.0), (20, -50.0)))):
        pb = arm.pose.bones[name]
        pb.rotation_mode = 'XYZ'
        for f, deg in frames:
            pb.rotation_euler = (math.radians(deg) * 0.2, 0.0, math.radians(deg))
            pb.keyframe_insert("rotation_euler", frame=f)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add(size=4 * k, location=_bl((12, 10, 0), k))
    body = bpy.context.active_object
    body.name = "pCube1"
    for name, *_ in LEFT + RIGHT:
        body.vertex_groups.new(name=name)
    body.vertex_groups["joint2"].add([v.index for v in body.data.vertices], 1.0, 'REPLACE')
    body.modifiers.new("skinCluster1", 'ARMATURE').object = arm
    sc.frame_set(7)                                   # not the rest frame
    return arm, body, k


def _truth(arm, k, frame):
    bpy.context.scene.frame_set(frame)
    out = {}
    for pb in arm.pose.bones:
        p = (arm.matrix_world @ pb.matrix).to_translation() / k
        out[pb.name] = Vector((p.x, p.z, -p.y))
    return out


def _stacks(index):
    return [(fbx_rig.name_of(st), st) for st in index.objects.find(b"AnimationStack")]


def _take_worlds(path, take):
    """{frame: {joint: world position}} of one take of the file (its curves only)."""
    tree, _v = fbx_rig.load(path)
    index = fbx_rig.Index(tree)
    stack = dict(_stacks(index))[take]
    layers = {c.props[1] for c in index.conns.elems if c.props[0] == b"OO" and c.props[2] == stack.props[0]}
    nodes = {c.props[1] for c in index.conns.elems if c.props[0] == b"OO" and c.props[2] in layers}
    # keep only this take's curve nodes
    for key, lst in index.curve_nodes_all.items():
        mine = [n for n in lst if n.props[0] in nodes]
        if mine:
            index.curve_nodes[key] = mine[0]
        else:
            index.curve_nodes.pop(key, None)
    times = None
    for (uid, attr), n in index.curve_nodes.items():
        cs = index.curves.get(n.props[0], {})
        for c in cs.values():
            times = list(c.first(b"KeyTime").props[0])
            break
        if times:
            break
    out = {}
    for i, t in enumerate(times):
        frame = round(t / KTIME * 24)
        out[frame] = {n: w.to_translation() for n, w in fbx_rig.world_matrices(index, sample=i).items()}
    return out


def _check(path, take, arm, k, frames):
    worlds = _take_worlds(path, take)
    worst = 0.0
    for f in frames:
        truth = _truth(arm, k, f)
        got = worlds[f]
        assert sorted(got) == sorted(truth), (sorted(got), sorted(truth))
        for name, p in truth.items():
            worst = max(worst, (got[name] - p).length)
    return worst


def _clip(sc, name, a, b):
    c = ge.add_clip(sc)
    c.name, c.start, c.end = name, a, b
    return c


def _export(sc, split, prefix):
    s = sc.allset_game_exporter
    os.makedirs(OUT, exist_ok=True)
    s.export_type, s.export_path, s.export_filename, s.file_split = 'ANIMATION', OUT, prefix, split
    return ge.export(bpy.context, s)


def test_clip_file_joints_equal_the_rig_every_frame():
    sc = _scene()
    arm, body, k = _rig(sc)
    _clip(sc, "swing", 1, 20)
    done = _export(sc, 'PER_CLIP', "ge_")
    path, takes = done[0]
    assert takes == ["swing"], takes
    worst = _check(path, "swing", arm, k, range(1, 21))
    print(f"step231 clip file max joint error {worst:.2e} cm")
    assert worst < 1e-3, worst


def test_single_file_two_clips_each_take_equals_the_rig():
    sc = _scene()
    arm, body, k = _rig(sc)
    _clip(sc, "idle", 1, 10)
    _clip(sc, "wave", 11, 20)
    (path, takes), = _export(sc, 'SINGLE', "anim231")
    assert takes == ["idle", "wave"], takes
    worst = max(_check(path, "idle", arm, k, range(1, 11)), _check(path, "wave", arm, k, range(11, 21)))
    print(f"step231 two-clip file max joint error {worst:.2e} cm")
    assert worst < 1e-3, worst


def test_rig_layout_like_export_selection():
    """No armature Null, joints in cm with PreRotation — the same layout Export Selection writes."""
    sc = _scene()
    arm, body, k = _rig(sc)
    _clip(sc, "swing", 1, 20)
    (path, _t), = _export(sc, 'PER_CLIP', "lay_")
    index = fbx_rig.Index(fbx_rig.load(path)[0])
    assert b"Null" not in [m.props[2] for m in index.models.values()]
    limbs = {fbx_rig.name_of(m): m for m in index.limbs().values()}
    t = fbx_rig.get_vec(limbs["joint2"], b"Lcl Translation")
    assert abs(t.length - math.sqrt(7 ** 2 + 1)) < 1e-3, t                 # 7.07 cm, not metres


def _ik_baked(sc):
    """The audit's chain ③ scene: IK handle on the left arm, Set IK/FK Keys, then Bake Simulation of that arm."""
    skin = import_module(kit.MODULE + ".operators.skin")
    ik_fk = import_module(kit.MODULE + ".operators.ik_fk")
    bake_maya = import_module(kit.MODULE + ".operators.bake_maya")
    arm, body, k = _rig(sc)
    compat = import_module(kit.MODULE + ".compat")
    coll = compat.id_fcurve_collection(arm)            # the IK drives joint1 / joint2: no FK keys there
    for fc in list(compat.id_fcurves(arm)):
        if '"joint1"' in fc.data_path or '"joint2"' in fc.data_path:
            coll.remove(fc)
    bpy.context.view_layer.objects.active = arm
    handle = skin.create_ik(bpy.context, arm, ("joint1", 'HEAD'), ("joint3", 'HEAD'))
    assert handle is not None
    for o in bpy.context.selected_objects:
        o.select_set(False)
    handle.select_set(True)
    for f, p in ((1, (19, 10, 0)), (10, (15, 14, 3)), (20, (14, 6, -4))):
        sc.frame_set(f)
        handle.location = _bl(p, k)
        bpy.context.view_layer.update()
        ik_fk.set_ik_fk_key(bpy.context, ik_fk.ik_constraints(bpy.context), f)
    handle.select_set(False)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    bones = [arm.pose.bones[n] for n in ("joint1", "joint2", "joint3")]
    cb = import_module(kit.MODULE + ".ui.channel_box")
    for pb in arm.pose.bones:                        # bake = the selected joints (Maya: the left arm)
        cb.set_bone_selected(pb, pb in bones)
    assert bake_maya.bake(bpy.context, bones=bones, start=1, end=20) is not None
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm, k


def test_clip_file_of_an_ik_rig_after_bake():
    sc = _scene()
    arm, k = _ik_baked(sc)
    _clip(sc, "swing", 1, 20)
    (path, takes), = _export(sc, 'PER_CLIP', "ik_")
    worst = _check(path, "swing", arm, k, range(1, 21))
    print(f"step231 ik clip file max joint error {worst:.2e} cm")
    assert worst < 1e-3, worst




def _take_keys(path, take, model_name, attr=b"Lcl Translation"):
    """{frame: value Vector} of one model attribute in one take."""
    tree, _v = fbx_rig.load(path)
    index = fbx_rig.Index(tree)
    stack = dict(_stacks(index))[take]
    layers = {c.props[1] for c in index.conns.elems if c.props[0] == b"OO" and c.props[2] == stack.props[0]}
    nodes = {c.props[1] for c in index.conns.elems if c.props[0] == b"OO" and c.props[2] in layers}
    uid = next(u for u, m in index.models.items() if fbx_rig.name_of(m) == model_name)
    for node in index.curve_nodes_all.get((uid, attr), []):
        if node.props[0] in nodes:
            times, vals, _n, _c = fbx_rig._node_keys(index, node, fbx_rig.get_vec(index.models[uid], attr))
            return {round(t / KTIME * 24): v for t, v in zip(times, vals)}
    return {}


def test_animation_layers_are_not_takes():
    """Audit ⑤-9: kit animation layers (NLA tracks) evaluate into each clip's take instead of being written as
    extra takes (Maya's Game Exporter writes the layered result, one take per clip)."""
    sc = _scene()
    k = units.maya_unit(sc)
    bpy.ops.mesh.primitive_cube_add(size=2 * k)
    cube = bpy.context.active_object
    cube.name = "pCube1"
    for f, x in ((1, 0.0), (20, 10.0)):
        cube.location.x = x * k
        cube.keyframe_insert("location", frame=f)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    assert bpy.ops.allset.anim_layer_create(from_selected=True) == {'FINISHED'}
    al = import_module(kit.MODULE + ".operators.anim_layers")
    sc.frame_set(12)
    assert al.key(cube, "location", 2, frame=12, value=5 * k) is not False      # Translate Z 5 on AnimLayer1
    truth = {}
    for f in range(1, 21):
        sc.frame_set(f)
        p = cube.matrix_world.translation / k
        truth[f] = Vector((p.x, p.z, -p.y))
    assert abs(truth[12].y - 5) < 1e-4, truth[12]                               # the layer shows in the scene
    _clip(sc, "idle", 1, 10)
    _clip(sc, "wave", 11, 20)
    (path, takes), = _export(sc, 'SINGLE', "layers231")
    assert takes == ["idle", "wave"], takes
    index = fbx_rig.Index(fbx_rig.load(path)[0])
    assert [n for n, _st in _stacks(index)] == ["idle", "wave"], _stacks(index)
    worst = 0.0
    for take, frames in (("idle", range(1, 11)), ("wave", range(11, 21))):
        keys = _take_keys(path, take, "pCube1")
        assert sorted(keys) == list(frames), (take, sorted(keys))
        for f in frames:
            worst = max(worst, (keys[f] - truth[f]).length)
    assert worst < 1e-3, worst
    assert cube.animation_data.nla_tracks, "the layer tracks stay"
    assert not [p for p in os.listdir(OUT) if p.endswith(".tmp.fbx")]


def test_scene_is_left_as_it_was():
    sc = _scene()
    arm, body, k = _rig(sc)
    sc.frame_set(7)
    name = sc.name
    _clip(sc, "a", 3, 8)
    _clip(sc, "b", 12, 18)
    _export(sc, 'SINGLE', "keep231")
    assert (sc.name, sc.frame_start, sc.frame_end, sc.frame_current) == (name, 1, 20, 7)
    assert not arm.animation_data.nla_tracks
