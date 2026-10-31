"""Issue #156 (report @cnzim) in a real UI, chain ③ start:
Joint Tool 3 clicks -> W finishes (Edit mode, Move tool) -> click joint2 -> drag = joint2 + joint3 move, joint1 stays ->
Ctrl+Z / Shift+Z -> Bind Skin -> click joint2 = Pose -> Skin > Move Skinned Joints -> drag: the mesh stays ->
Move Skinned Joints again = Pose, posing bends about the new place -> save + open keeps the joints."""

import os
import sys
import tempfile
from importlib import import_module

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, tap, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, f"gui_step241_{name}.png"))


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def ov():
    area, region = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=region)


def screen_of(world):
    _a, r = main_view()
    p = view3d_utils.location_3d_to_region_2d(r, r.data, world)
    return int(r.x + p.x), int(r.y + p.y)


def at(f, g):
    _a, r = main_view()
    return r.x + int(r.width * f), r.y + int(r.height * g)


def rig():
    return bpy.data.objects[C["rig"]]


def heads():
    ob = rig()
    if ob.mode == 'EDIT':
        return {eb.name: ob.matrix_world @ eb.head for eb in ob.data.edit_bones}
    return {b.name: ob.matrix_world @ b.head_local for b in ob.data.bones}


def verts():
    mesh = bpy.data.objects[C["mesh"]]
    ev_ = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return [ev_.matrix_world @ v.co for v in ev_.data.vertices]


def tool_id():
    area, _r = main_view()
    with ov():
        return bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode).idname


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_clean():
    for ob in list(bpy.data.objects):
        if ob.type in {'MESH', 'ARMATURE'}:
            bpy.data.objects.remove(ob)
    with ov():
        bpy.ops.allset.joint_tool('INVOKE_DEFAULT')


def click(name, p):
    @step
    def s_click():
        x, y = p()
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    s_click.__name__ = name


click("s_j1", lambda: at(0.45, 0.30))
click("s_j2", lambda: at(0.45, 0.50))
click("s_j3", lambda: at(0.45, 0.70))


@step
def s_w():
    tap('W')


@step
def s_placed():
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    check(f"Joint Tool made one skeleton ({len(arms)})", len(arms) == 1)
    C["rig"] = arms[0].name
    ob = rig()
    check(f"W after placing: Edit mode (joints move like Maya's) ({bpy.context.mode})", bpy.context.mode == 'EDIT_ARMATURE')
    check(f"W after placing: Move tool ({tool_id()})", tool_id() == "builtin.move")
    C["names"] = [b.name for b in ob.data.bones]
    shot("01_placed")


@step
def s_pick_j2():
    j2 = C["names"][1]
    x, y = screen_of(heads()[j2])
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_picked():
    ob = rig()
    j1, j2, j3 = C["names"][:3]
    sel = {eb.name for eb in ob.data.edit_bones if eb.select and eb.select_head and eb.select_tail}
    check(f"click joint2: joint2 and its child picked, joint1 not ({sorted(sel)})", sel == {j2, j3})
    C["h0"] = heads()
    cur = bpy.context.scene.cursor.location
    check("E / R pivot = joint2 (cursor on it, pivot Cursor)",
          (cur - C["h0"][j2]).length < 1e-4 and bpy.context.scene.tool_settings.transform_pivot_point == 'CURSOR')
    x, y = screen_of(C["h0"][j2])
    C["drag"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


for _i in range(1, 6):
    @step
    def s_move(i=_i):
        x, y = C["drag"]
        ev('MOUSEMOVE', 'NOTHING', x=x + 12 * i, y=y)


@step
def s_release():
    x, y = C["drag"]
    ev('LEFTMOUSE', 'RELEASE', x=x + 60, y=y)


@step
def s_moved():
    j1, j2, j3 = C["names"][:3]
    h = heads()
    d2, d3 = h[j2] - C["h0"][j2], h[j3] - C["h0"][j3]
    check(f"drag moves joint2 ({d2.length:.3f}) and joint3 follows rigidly ({(d2 - d3).length:.1e})",
          d2.length > 1e-3 and (d2 - d3).length < 1e-5)
    check("joint1 stays", (h[j1] - C["h0"][j1]).length < 1e-6)
    C["h1"] = h
    shot("02_moved")
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undone():
    j2 = C["names"][1]
    check(f"Ctrl+Z puts joint2 back ({(heads()[j2] - C['h0'][j2]).length:.1e})",
          (heads()[j2] - C["h0"][j2]).length < 1e-5)
    ev('Z', 'PRESS', shift=True)
    ev('Z', 'RELEASE', shift=True)


@step
def s_redone():
    j2 = C["names"][1]
    check("Shift+Z moves it again", (heads()[j2] - C["h1"][j2]).length < 1e-5)
    # bind: a cylinder along the chain, both selected, Skin > Bind Skin (menu item)
    ob = rig()
    h = heads()
    with ov():
        bpy.ops.object.mode_set(mode='OBJECT')
        mid = (h[C["names"][0]] + h[C["names"][2]]) / 2
        length = (h[C["names"][2]] - h[C["names"][0]]).length + 0.2
        bpy.ops.mesh.primitive_cylinder_add(radius=length * 0.08, depth=length, location=mid)
        mesh = bpy.context.active_object
        axis = (h[C["names"][2]] - h[C["names"][0]]).normalized()
        mesh.rotation_mode = 'QUATERNION'
        mesh.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(axis)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.subdivide(number_cuts=6)
        bpy.ops.object.mode_set(mode='OBJECT')
        C["mesh"] = mesh.name
        ob.select_set(True)
        mesh.select_set(True)
        bpy.ops.allset.menu_item(item="Skin/Bind Skin")


@step
def s_bound():
    js = mod(".operators.joint_selection")
    check(f"bound: the skeleton is skinned (joint mode {js.joint_mode(rig())})", js.joint_mode(rig()) == 'POSE')
    j2 = C["names"][1]
    x, y = screen_of(heads()[j2])
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_posed():
    check(f"click joint2 of a skinned skeleton = Pose ({bpy.context.mode})", bpy.context.mode == 'POSE')
    shot("03_skinned_pose")
    C["v0"] = verts()
    with ov():
        bpy.ops.allset.menu_item(item="Skin/Move Skinned Joints")


@step
def s_msj_on():
    check(f"Skin > Move Skinned Joints = Edit mode ({bpy.context.mode}, pivot "
          f"{bpy.context.scene.tool_settings.transform_pivot_point})", bpy.context.mode == 'EDIT_ARMATURE'
          and bpy.context.scene.tool_settings.transform_pivot_point == 'CURSOR')
    j2 = C["names"][1]
    C["h2"] = heads()
    x, y = screen_of(C["h2"][j2])
    C["drag"] = (x, y)
    # wait away from the manipulator: resting on it opens Blender's gizmo tooltip, which eats the next press
    ev('MOUSEMOVE', 'NOTHING', x=x + 150, y=y + 150)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_msj_move():
    # the move the Move manipulator runs (dragging the manipulator itself after Move Skinned Joints is checked by hand:
    # simulated presses there didn't reach the gizmo)
    _a, r = main_view()
    with ov():
        bpy.ops.transform.translate(value=(-0.05, 0, 0))


@step
def s_msj_moved():
    j2 = C["names"][1]
    moved = (heads()[j2] - C["h2"][j2]).length
    still = max((a - b).length for a, b in zip(C["v0"], verts()))
    check(f"joint2 moved ({moved:.3f}), the mesh stays ({still:.1e})", moved > 1e-3 and still < 1e-5)
    shot("04_move_skinned")
    with ov():
        bpy.ops.allset.menu_item(item="Skin/Move Skinned Joints")


@step
def s_msj_off():
    check(f"Move Skinned Joints again = Pose ({bpy.context.mode})", bpy.context.mode == 'POSE')
    still = max((a - b).length for a, b in zip(C["v0"], verts()))
    check(f"the mesh is where it was after the move ({still:.1e})", still < 1e-5)
    pb = rig().pose.bones[C["names"][0]]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = (0.0, 0.5, 0.0)
    bpy.context.view_layer.update()
    check("posing bends the mesh about the new place", max((a - b).length for a, b in zip(C["v0"], verts())) > 1e-3)
    pb.rotation_euler = (0, 0, 0)
    C["final"] = {k: v.copy() for k, v in heads().items()}
    path = os.path.join(tempfile.gettempdir(), "allset_gui_step241.blend")
    C["path"] = path
    shot("05_posed_back")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)


@step
def s_reopened():
    h = heads()
    check("save + open keeps the moved joints",
          all((h[k] - v).length < 1e-5 for k, v in C["final"].items()))
    try:
        os.remove(C["path"])
    except OSError:
        pass


run()
