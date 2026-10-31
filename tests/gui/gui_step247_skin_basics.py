"""Issue #164: in a real UI, the skinning chain a Maya rigger walks:
Joint Tool 3 clicks -> Enter -> a mesh over the chain -> Skin > Bind Skin -> pose joint2 in the Channel Box ->
Skin > Go to Bind Pose puts the mesh back (error 0) -> Skin > Prune Small Weights (0.01, renormalised) ->
Skin > Edit Influences > Set Max Influences... -> Skin > Mirror Skin Weights -> Ctrl+Z -> save + open keeps the bind pose."""

import os
import sys
import tempfile
from importlib import import_module

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, f"gui_step247_{name}.png"))


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def ov():
    area, region = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def at(f, g):
    _a, r = main_view()
    return r.x + int(r.width * f), r.y + int(r.height * g)


def click_at(x, y):
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


def press_key(key, **kw):
    x, y = at(0.9, 0.1)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev(key, 'PRESS', x=x, y=y, **kw)
    ev(key, 'RELEASE', x=x, y=y, **kw)


def menu(path, **kw):
    with ov():
        return bpy.ops.allset.menu_item(item=path, **kw)


def rig():
    return bpy.data.objects[C["rig"]]


def body():
    return bpy.data.objects[C["mesh"]]


def evaluated():
    dg = bpy.context.evaluated_depsgraph_get()
    ob = body().evaluated_get(dg)
    me = ob.to_mesh()
    out = [ob.matrix_world @ v.co for v in me.vertices]
    ob.to_mesh_clear()
    return out


def select(*obs):
    with ov():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.view_layer.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[-1]


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_tool():
    for ob in list(bpy.data.objects):
        if ob.type in {'MESH', 'ARMATURE', 'EMPTY'}:
            bpy.data.objects.remove(ob)
    with ov():
        bpy.ops.allset.joint_tool('INVOKE_DEFAULT')


for _i, (_f, _g) in enumerate(((0.30, 0.50), (0.48, 0.50), (0.66, 0.50))):
    def _mk(f=_f, g=_g, i=_i):
        @step
        def s_click():
            click_at(*at(f, g))
        s_click.__name__ = f"s_joint{i + 1}"
    _mk()


@step
def s_enter():
    press_key('RET')


@step
def s_mesh():
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    check(f"Joint Tool made a skeleton ({len(arms)})", len(arms) == 1)
    C["rig"] = arms[0].name
    ob = rig()
    heads = [ob.matrix_world @ b.head_local for b in ob.data.bones]
    a, b = heads[0], heads[-1]
    mid = (a + b) / 2
    length = (b - a).length
    with ov():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=length * 0.08, depth=length, location=mid,
                                            rotation=(0.0, 0.0, 0.0))
        cyl = bpy.context.active_object
        d = (b - a).normalized()
        cyl.rotation_mode = 'QUATERNION'
        cyl.rotation_quaternion = d.to_track_quat('Z', 'Y')
        bpy.ops.object.transform_apply(rotation=True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.subdivide(number_cuts=6)
        bpy.ops.object.mode_set(mode='OBJECT')
    C["mesh"] = cyl.name
    select(rig(), cyl)
    menu("Skin/Bind Skin")


@step
def s_bound():
    md = mod(".operators.skin").armature_modifier(body())
    check("Bind Skin made the skin", md is not None and md.object == rig())
    check("the bind pose is stored with the skeleton", "allset_bind_pose" in rig())
    C["bind"] = evaluated()
    names = [b.name for b in rig().data.bones]
    C["names"] = names
    cb = mod(".ui.channel_box")
    with ov():
        bpy.ops.object.mode_set(mode='OBJECT')
        select(rig())
        bpy.ops.object.mode_set(mode='POSE')
    pb = rig().pose.bones[names[1]]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = (0.0, 0.0, 0.9)
    rig().pose.bones[names[0]].location = (0.0, 0.0, 0.0)
    rig().pose.bones[names[0]].rotation_mode = 'XYZ'
    rig().pose.bones[names[0]].rotation_euler = (0.3, 0.0, 0.0)
    cb.set_bone_selected(rig().pose.bones[names[1]], True)
    bpy.context.view_layer.update()


@step
def s_posed():
    shot("posed")
    moved = max((a - b).length for a, b in zip(C["bind"], evaluated()))
    check(f"posing moves the skin ({moved:.3f})", moved > 1e-3)
    menu("Skin/Go to Bind Pose")


@step
def s_back():
    shot("bind_pose")
    err = max((a - b).length for a, b in zip(C["bind"], evaluated()))
    check(f"Go to Bind Pose: every joint back, mesh error {err:.1e}", err < 1e-5)
    m = body()
    sb = mod(".operators.skin_basics")
    groups = sb._influence_groups(m)
    C["groups"] = [g.name for g in groups]
    # a small weight on vertex 0 for the prune
    v0 = m.data.vertices[0]
    names = C["groups"]
    for g in groups:
        g.remove([0])
    groups[0].add([0], 0.995, 'REPLACE')
    groups[1].add([0], 0.005, 'REPLACE')
    select(m)
    menu("Skin/Prune Small Weights")
    C["v0"] = v0.index


@step
def s_pruned():
    m = body()
    w = {m.vertex_groups[g.group].name: g.weight for g in m.data.vertices[0].groups}
    check(f"Prune Small Weights: the 0.005 weight leaves, the rest is 1 ({w})",
          C["groups"][1] not in w and abs(w.get(C["groups"][0], 0) - 1.0) < 1e-6)
    with ov():
        bpy.ops.allset.set_max_influences('EXEC_DEFAULT', max_influences=2)
    most = max(sum(1 for g in v.groups if g.weight > 0) for v in m.data.vertices)
    check(f"Set Max Influences 2: no vertex has more than 2 joints ({most})", most <= 2)
    C["before_mirror"] = mod(".operators.skin_basics").weights(m, mod(".operators.skin_basics")._influence_groups(m)).copy()
    menu("Skin/Mirror Skin Weights")


@step
def s_mirrored():
    shot("mirrored")
    sb = mod(".operators.skin_basics")
    m = body()
    after = sb.weights(m, sb._influence_groups(m))
    import numpy as np
    sums = after.sum(axis=1)
    check(f"Mirror Skin Weights ran; weights still sum to 1 ({sums.min():.4f}..{sums.max():.4f})",
          np.all(np.abs(sums - 1.0) < 1e-4))
    C["changed"] = float(np.abs(after - C["before_mirror"]).max())
    _a, r = main_view()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    sb = mod(".operators.skin_basics")
    m = body()
    import numpy as np
    back = sb.weights(m, sb._influence_groups(m))
    err = float(np.abs(back - C["before_mirror"]).max())
    check(f"Ctrl+Z undoes the mirror ({C['changed']:.3f} changed -> {err:.1e})", err < 1e-6)
    path = os.path.join(tempfile.mkdtemp(prefix="allset247_"), "skin.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)


@step
def s_reopened():
    arm = bpy.data.objects.get(C["rig"])
    check("save + open keeps the bind pose", arm is not None and "allset_bind_pose" in arm)
    pb = arm.pose.bones[C["names"][1]]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = (0.0, 0.0, 0.5)
    bpy.context.view_layer.update()
    select(arm)
    menu("Skin/Go to Bind Pose")
    err = max((a - b).length for a, b in zip(C["bind"], evaluated()))
    check(f"after open, Go to Bind Pose still puts the mesh back ({err:.1e})", err < 1e-5)


run()
