"""Issue #134: in a real UI: Visualization > Numeric > Show Numbers on a ~20k-vertex skinned mesh draws at
most 2,000 weight labels (whole mesh in view: only around the brush, Help Line note; zoomed in: every vertex in view),
with the draw time timed; a second Bind Skin on the skinned mesh opens Maya's question. Shots in the shots folder."""

import os
import sys
from importlib import import_module

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, win, load_maya_layout, screenshot  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                           "tmp", "gui_step224")
C = {}


def mod(name):
    return import_module(MODULE + name)


def main_view():
    toolbox = mod(".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def centre():
    _a, r = main_view()
    return r.x + r.width // 2, r.y + r.height // 2


def override():
    area, r = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=r)


def steady_ms(stats):
    """Median draw time of frames that reused the cache (projection + labels)."""
    ms = sorted(m for m, refreshed in stats["history"] if not refreshed)
    return ms[len(ms) // 2] if ms else float("nan")


def first_ms(stats):
    ms = [m for m, refreshed in stats["history"] if refreshed]
    return max(ms) if ms else 0.0


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    joints = mod(".operators.joints")
    k = mod(".operators.units").maya_unit()
    with override():
        bpy.ops.mesh.primitive_uv_sphere_add(segments=160, ring_count=125, radius=10 * k)
        body = bpy.context.active_object
        body.name = "body"
        body.scale.z = 2.0
        bpy.ops.object.transform_apply(scale=True)
        bpy.ops.object.select_all(action='DESELECT')
        sk = joints.new_skeleton(bpy.context)
        parent, names = None, []
        for z in (-15.0, 0.0, 15.0):
            parent = joints.add_joint(sk, Vector((0, 0, z * k)), parent, length=k)
            names.append(parent)
        joints.finish(bpy.context, sk, names)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        sk.select_set(True)
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        bpy.ops.allset.bind_skin()
        bpy.ops.object.select_all(action='DESELECT')
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        bpy.ops.allset.frame(selected=False)
        bpy.ops.allset.weight_workspace()
    body = bpy.data.objects["body"]
    body.vertex_groups.active_index = body.vertex_groups[names[1]].index
    C.update(body=body.name, skeleton=sk.name, n=len(body.data.vertices))
    s = mod(".operators.weight_paint").state(bpy.context)
    with override():
        s.show_numbers = True
    check(f"{C['n']} vertices skinned and painting ({bpy.context.mode})",
          C["n"] > 19000 and bpy.context.mode == 'PAINT_WEIGHT')
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    redraw()


@step
def s_move():
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x + 3, y=y + 2)
    redraw()


@step
def s_wait():
    redraw()


@step
def s_wait_b():
    redraw()


@step
def s_wait_c():
    redraw()


@step
def s_whole():
    stats = mod(".ui.weight_numbers").STATS
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, "numbers_whole_mesh.png")
    screenshot(path)
    C["whole"] = dict(stats, steady=steady_ms(stats), first=first_ms(stats))
    check(f"whole mesh in view: {stats['in_view']} vertices in view, {stats['drawn']} labels around the brush, "
          f"steady {C['whole']['steady']:.2f} ms (cache refill {C['whole']['first']:.2f} ms), pointer "
          f"{stats['mouse']}", stats["capped"] and 0 < stats["drawn"] <= 2000)
    note = mod(".ui.weight_numbers").help_note()
    check(f"Help Line note: {note!r}", "zoom in" in note)


@step
def s_zoom():
    area, r = main_view()
    rv3d = area.spaces.active.region_3d
    k = mod(".operators.units").maya_unit()
    body = bpy.data.objects[C["body"]]
    towards_viewer = rv3d.view_rotation @ Vector((0, 0, 1))
    rv3d.view_location = body.matrix_world.translation + towards_viewer * 10 * k
    rv3d.view_perspective = 'ORTHO'          # front and back patches both count (labels show through)
    rv3d.view_distance = 2.5 * k
    mod(".ui.weight_numbers").STATS["history"] = []
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_wait2b():
    redraw()


@step
def s_wait2c():
    redraw()


@step
def s_zoomed():
    stats = mod(".ui.weight_numbers").STATS
    path = os.path.join(SHOTS, "numbers_zoomed.png")
    screenshot(path)
    zoomed = steady_ms(stats)
    check(f"zoomed in: {stats['in_view']} in view, {stats['drawn']} labels (all), steady {zoomed:.2f} ms: {path}",
          not stats["capped"] and stats["drawn"] == stats["in_view"] > 0)
    check(f"steady draw time under 16.7 ms (whole {C['whole']['steady']:.2f} ms, zoomed {zoomed:.2f} ms)",
          C["whole"]["steady"] < 16.7 and zoomed < 16.7)


@step
def s_second_bind():
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        bpy.data.objects[C["skeleton"]].select_set(True)
        body = bpy.data.objects[C["body"]]
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
    x, y = centre()
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    with override():
        bpy.ops.allset.menu_item(item="Skin/Bind Skin")
    skin = mod(".operators.skin")
    check(f"second Bind Skin asked about {skin.QUESTION['mesh']}, skins {len(skin.armature_modifiers(body))}",
          skin.QUESTION["mesh"] == C["body"] and len(skin.armature_modifiers(body)) == 1)


@step
def s_wait3():
    pass


@step
def s_question_shot():
    path = os.path.join(SHOTS, "second_bind_question.png")
    screenshot(path)
    check(f"screenshot of the question: {path}", os.path.exists(path))
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')


run()
