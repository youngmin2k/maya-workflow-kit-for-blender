"""Lane B (#137) in a real UI: an arm (shoulder -> elbow) skinning a line mesh, Deform > Pose Space Deformation >
Create Pose Interpolator on the elbow, pose elbowBent at -90, Add Shape, elbow at -45; Windows > Animation Editors >
Pose Editor opens a new window whose Properties area is the kit Pose Editor (no Blender header); shot of it."""

import math
import os
import sys
from importlib import import_module

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
P = Matrix(((0, 0, 1), (1, 0, 0), (0, 1, 0)))


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def menu(item):
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return bpy.ops.allset.menu_item(item=item)


def rotate(arm, rz):
    pb = arm.pose.bones["elbow"]
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = (P @ Matrix.Rotation(math.radians(rz), 3, 'Z') @ P.transposed()).to_quaternion()
    bpy.context.view_layer.update()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = v3d()
    data = bpy.data.armatures.new("skeleton1")
    arm = bpy.data.objects.new("skeleton1", data)
    bpy.context.scene.collection.objects.link(arm)
    me = bpy.data.meshes.new("armMeshShape")
    pts = [(x, 0.0, 0.0) for x in range(9)]
    me.from_pydata(pts, [(i, i + 1) for i in range(8)], [])
    mesh = bpy.data.objects.new("armMesh", me)
    bpy.context.scene.collection.objects.link(mesh)
    for o in bpy.context.scene.objects:
        o.select_set(o == arm)
    bpy.context.view_layer.objects.active = arm
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='EDIT')
        s = data.edit_bones.new("shoulder")
        s.head, s.tail = (0, 0, 0), (4, 1, 0)
        e = data.edit_bones.new("elbow")
        e.head, e.tail = (4, 1, 0), (8, 0, 0)
        e.parent, e.use_connect = s, True
        for b in (s, e):
            b.align_roll(Vector((0, 0, 1)))
        bpy.ops.object.mode_set(mode='POSE')
        data.bones.active = data.bones["elbow"]
        C["create"] = menu("Deform/Pose Space Deformation/Create Pose Interpolator")
    gs, ge = mesh.vertex_groups.new(name="shoulder"), mesh.vertex_groups.new(name="elbow")
    for i, (x, _y, _z) in enumerate(pts):
        (gs if x < 4 else ge).add([i], 1.0, 'REPLACE')
    mesh.modifiers.new("skinCluster1", 'ARMATURE').object = arm
    interp = bpy.data.objects.get("elbow_poseInterpolator")
    check(f"Create Pose Interpolator from the Maya menu ({C['create']})", interp is not None)
    if interp is None:
        return
    rotate(arm, -90)
    C["add"] = bpy.ops.allset.pose_add(interpolator=interp.name, name="elbowBent")
    rotate(arm, 0)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = mesh
    C["shape"] = bpy.ops.allset.pose_add_shape(interpolator=interp.name, pose="elbowBent", edit=False)
    rotate(arm, -45)
    check(f"Add Pose / Add Shape ({C['add']}, {C['shape']})", C["add"] == C["shape"] == {'FINISHED'})
    C["open"] = menu("Windows/Animation Editors/Pose Editor")


@step
def s_open():
    redraw()


@step
def s_check():
    mw = mod(".ui.marked_window")
    w = mw.find_window(bpy.context, "POSE_EDITOR")
    area = next((a for a in w.screen.areas if mw.kind_of(a) == "POSE_EDITOR"), None) if w else None
    check(f"Windows > Animation Editors > Pose Editor opens the kit window ({C.get('open')})",
          w is not None and area is not None)
    if area is not None:
        check("Pose Editor: one area, no Blender header", len(w.screen.areas) == 1
              and not area.spaces.active.show_region_header)
    ps = mod(".operators.pose_space_227")
    interp = bpy.data.objects.get("elbow_poseInterpolator")
    wt = ps.weight(interp, "elbowBent") if interp else -1
    kb = bpy.data.objects["armMesh"].data.shape_keys.key_blocks["elbowBent"]
    check(f"elbow at -45: pose weight {wt:.4f} = 0.5 (Maya), corrective key {kb.value:.4f}",
          abs(wt - 0.5) < 1e-4 and abs(kb.value - wt) < 1e-6)
    C["win"] = w
    redraw()


@step
def s_shot():
    if C.get("win"):
        shot("gui_step227_pose_editor.png", C["win"])
    shot("gui_step227_main.png")


run()
