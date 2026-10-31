"""Issue #167: in a real UI: Joint Tool arm -> a cylinder -> Skin > Bind Skin -> the Attribute Editor's
skinCluster1 tab shows Maya's Skinning Method; Dual Quaternion keeps the elbow's volume, Weight Blended mixes per
vertex by blendWeights (painted 1 on half the cylinder) -> Ctrl+Z -> save + open keeps the method."""

import math
import os
import sys
import tempfile
from importlib import import_module

import bpy
from mathutils import Vector

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
        screenshot(os.path.join(SHOTS, f"gui_step250_{name}.png"))


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def ov():
    area, region = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def verts(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev_ = ob.evaluated_get(dg)
    me = ev_.to_mesh()
    out = [ob.matrix_world @ v.co for v in me.vertices]
    ev_.to_mesh_clear()
    return out


def redraw():
    for ar in win().screen.areas:
        ar.tag_redraw()


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_rig():
    for ob in list(bpy.data.objects):
        if ob.type in {'MESH', 'ARMATURE', 'EMPTY'}:
            bpy.data.objects.remove(ob)
    joints = mod(".operators.joints")
    k = mod(".operators.units").maya_unit()
    with ov():
        ob = joints.new_skeleton(bpy.context)
        parent, names = None, []
        for x in (0, 4, 8, 11):
            parent = joints.add_joint(ob, Vector((x * k, 0.0, 0.0)), parent, length=k)
            names.append(parent)
        joints.orient_new(ob, names)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=k, depth=11 * k, location=(5.5 * k, 0, 0),
                                            rotation=(0, math.pi / 2, 0))
        cyl = bpy.context.active_object
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.subdivide(number_cuts=10)
        bpy.ops.object.mode_set(mode='OBJECT')
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        cyl.select_set(True)
        bpy.context.view_layer.objects.active = cyl
        bpy.ops.allset.menu_item(item="Skin/Bind Skin")
    C["rig"], C["mesh"], C["names"] = ob.name, cyl.name, names


@step
def s_pose():
    mesh = bpy.data.objects[C["mesh"]]
    sm = mod(".operators.skin_method")
    check(f"Bind Skin: Classic Linear by default ({sm.method_of(mesh)})", sm.method_of(mesh) == "CLASSIC_LINEAR")
    arm = bpy.data.objects[C["rig"]]
    pb = arm.pose.bones[C["names"][1]]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = (0.0, 0.0, math.radians(110))
    bpy.context.view_layer.update()
    C["lbs"] = verts(mesh)
    bpy.ops.ed.undo_push(message="pose")
    bpy.context.view_layer.objects.active = mesh
    for o in bpy.context.selected_objects:
        o.select_set(False)
    mesh.select_set(True)
    wm = bpy.context.window_manager
    wm.allset_dock = 'ATTRIBUTE_EDITOR'
    md = mod(".operators.skin").armature_modifier(mesh)
    with ov():
        bpy.ops.allset.ae_tab(key=f"M:{md.name}")
    redraw()


@step
def s_ae_shot():
    shot("ae_skin")
    mesh = bpy.data.objects[C["mesh"]]
    mesh.allset_skinning_method = 'DUAL_QUATERNION'      # the AE dropdown
    bpy.context.view_layer.update()
    dq = verts(mesh)
    moved = max((a - b).length for a, b in zip(C["lbs"], dq))
    check(f"Dual Quaternion changes the bent elbow ({moved / mod('.operators.units').maya_unit():.3f} units)",
          moved > 1e-3)
    C["dq"] = dq
    mesh.allset_skinning_method = 'WEIGHT_BLENDED'
    sm = mod(".operators.skin_method")
    half = {v.index: 1.0 for v in mesh.data.vertices if v.co.z > 0}
    sm.set_blend_weights(mesh, half)
    bpy.context.view_layer.update()
    wb = verts(mesh)
    ok = all(((wb[i] - C["dq"][i]).length < 1e-5) if i in half else ((wb[i] - C["lbs"][i]).length < 1e-5)
             for i in range(len(wb)))
    check("Weight Blended: blendWeights 1 = DQ, 0 = linear, per vertex", ok)
    check("one skinCluster in INPUTS (the DQ half is hidden)",
          len([m for m in mod(".ui.channel_box")._inputs(mesh) if m.type == 'ARMATURE']) == 1)
    redraw()


@step
def s_wb_shot():
    shot("weight_blended")
    _a, r = main_view()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    mesh = bpy.data.objects[C["mesh"]]
    sm = mod(".operators.skin_method")
    check(f"Ctrl+Z goes back to Classic Linear ({sm.method_of(mesh)})", sm.method_of(mesh) == "CLASSIC_LINEAR")
    mesh.allset_skinning_method = 'WEIGHT_BLENDED'
    path = os.path.join(tempfile.mkdtemp(prefix="allset250_"), "skin.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)


@step
def s_reopened():
    mesh = bpy.data.objects[C["mesh"]]
    sm = mod(".operators.skin_method")
    check(f"save + open keeps Weight Blended ({sm.method_of(mesh)})", sm.method_of(mesh) == "WEIGHT_BLENDED")


run()
