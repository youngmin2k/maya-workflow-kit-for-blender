"""In a real UI, Maya rigging_04 hand order on the Maya Workflow Kit layout: a cylinder + a three-joint skeleton ->
click the skeleton, Shift+click the cylinder (joints first, mesh last) -> Skin > Bind Skin -> Armature modifier + three
joint groups -> Skin > Paint Skin Weights -> pick joint2 in the influence list -> paint on the mesh -> joint2's weights go
up."""

import os
import sys
from importlib import import_module

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, find_button, run, screenshot, setup, step, tap, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 360   # the influence-row sweep in Tool Settings (PR #125 follow-up)
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def maya_menu(path):
    for cls in import_module(MODULE + ".ui.menu_sets")._menu_classes:
        if (cls.__doc__ or "").strip() == f"Maya menu: {path}":
            return cls.bl_idname
    raise LookupError(path)


def main_view():
    toolbox = import_module(MODULE + ".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def screen_of(world):
    area, r = main_view()
    p = view3d_utils.location_3d_to_region_2d(r, r.data, world)
    return r.x + int(p.x), r.y + int(p.y)


def open_menu(path):
    area, region = main_view()
    x, y = region.x + region.width // 2, region.y + region.height // 2
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.wm.call_menu(name=maya_menu(path))


def cyl():
    return bpy.data.objects["pCylinder1"]


def arm():
    return bpy.data.objects["skeleton1"]


def joint2_weight():
    me = cyl()
    vg = me.vertex_groups.get("joint2")
    if vg is None:
        return 0.0
    return sum(g.weight for v in me.data.vertices for g in v.groups if g.group == vg.index)


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    joints = import_module(MODULE + ".operators.joints")
    k = import_module(MODULE + ".operators.units").maya_unit()
    area, r = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=r):
        bpy.ops.allset.create(kind='CYLINDER')            # pCylinder1: radius 1, height 2 (Maya units)
        c = bpy.context.active_object
        import bmesh                                        # Maya users add height divisions for skinning
        bm = bmesh.new()
        bm.from_mesh(c.data)
        vertical = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1e-9]
        bmesh.ops.subdivide_edges(bm, edges=vertical, cuts=9, use_grid_fill=True)
        bm.to_mesh(c.data)
        bm.free()
        bpy.ops.object.select_all(action='DESELECT')
        sk = joints.new_skeleton(bpy.context)                # what the Joint Tool makes
        parent = None
        for z in (-1.0, 0.0, 1.0):
            parent = joints.add_joint(sk, Vector((0, 0, z * k)), parent, length=k)
        joints.finish(bpy.context, sk, ["joint1", "joint2", "joint3"])
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.allset.frame(selected=False)
    C["k"] = k


@step
def s_positions():
    k = C["k"]
    # click joint3's drawn wire where its sphere pokes out of the cylinder top (an end joint draws no bone, like
    # Maya; positions after the view refit)
    mj = import_module(MODULE + ".ui.maya_joints")
    j3 = mj.skeleton(arm(), bpy.context.scene)["joint3"]
    top = max((j3.frame.col[i] * s for i in range(3) for s in (1, -1)), key=lambda v: v.z)
    C["joint_xy"] = screen_of(j3.centre + top * j3.radius)
    C["cyl_xy"] = screen_of(Vector((0, -k, -0.5 * k)))       # the cylinder's front side
    ev('MOUSEMOVE', 'NOTHING', x=C["joint_xy"][0], y=C["joint_xy"][1])


@step
def s_click_skeleton():
    shot("gui_step58_scene.png")
    x, y = C["joint_xy"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_hover_mesh():
    check(f"clicking the joint selects skeleton1 ({[o.name for o in bpy.context.selected_objects]})",
          arm().select_get())
    x, y = C["cyl_xy"]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_shift_click_mesh():
    x, y = C["cyl_xy"]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y, shift=True)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y, shift=True)


@step
def s_selected_both():
    sel = sorted(o.name for o in bpy.context.selected_objects)
    check(f"Shift+click adds the cylinder ({sel}, active {bpy.context.active_object.name})",
          sel == ["pCylinder1", "skeleton1"] and bpy.context.active_object == cyl())
    open_menu("Skin")


@step
def s_bind():
    tap('B')          # Bind Skin


@step
def s_bound():
    c = cyl()
    mod = next((m for m in c.modifiers if m.type == 'ARMATURE'), None)
    groups = sorted(vg.name for vg in c.vertex_groups)
    check(f"Bind Skin: Armature modifier on {mod and mod.object and mod.object.name}, groups {groups}",
          mod is not None and mod.object == arm() and groups == ["joint1", "joint2", "joint3"])
    check("the skin stays out of the joint hierarchy (no parent)", c.parent is None)
    open_menu("Skin")


@step
def s_paint_item():
    shot("gui_step58_skin_menu.png")
    tap('P')          # Paint Skin Weights


@step
def s_painting():
    check(f"Paint Skin Weights: weight paint ({bpy.context.mode}), skeleton posable ({arm().mode})",
          bpy.context.mode == 'PAINT_WEIGHT' and arm().mode == 'POSE')
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_tool_settings():
    # Maya: the plain menu item only starts the tool (the Channel Box stays); its settings, influence list included,
    # are Tool Settings (PR #125 follow-up) -- open them like the option box / tool double-click does
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.weight_workspace()


def tool_settings_region():
    td = import_module(MODULE + ".ui.tool_dock")
    area = td.find(win().screen)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


@step
def s_panel_shot():
    shot("gui_step58_paint_panel.png")
    c = cyl()
    pw = import_module(MODULE + ".ui.paint_weights")
    # display position of joint2 in the list (Maya order: by hierarchy)
    C["pos"] = pw.influence_order(c, 'HIERARCHY')[c.vertex_groups['joint2'].index]
    C["unit"] = round(20 * bpy.context.preferences.system.ui_scale * bpy.context.preferences.view.ui_scale)


# the influence search field (above the list) in the Tool Settings dock, swept top to bottom
step(find_button(tool_settings_region, lambda path, cmd: path.endswith("allset_weight_workspace.search"), C, "search",
                 step_px=4, x_frac=0.5))


@step
def s_found_row():
    found = C.get("search")
    # list rows are one UI unit tall, the first one 1.4 units under the search field's centre (read from
    # gui_step58_paint_panel.png at UI 1.25), in hierarchy order
    C["lock"] = (found[0], found[1] - int(C["unit"] * (1.4 + C["pos"]))) if found else None


@step
def s_click_row():
    found = C.get("lock")
    check(f"the Tool Settings influence list shows joint2 ({found})", found is not None)
    if found is None:
        return
    _a, r = tool_settings_region()
    x, y = r.x + r.width // 3, found[1]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_row_picked():
    c = cyl()
    name = c.vertex_groups.active.name if c.vertex_groups.active else None
    check(f"the influence list picks joint2 ({name})", name == "joint2")
    if name != "joint2":
        c.vertex_groups.active_index = c.vertex_groups["joint2"].index
    C["w0"] = joint2_weight()
    k = C["k"]
    C["stroke"] = [screen_of(Vector((x * k, -k, 0.6 * k))) for x in (-0.6, -0.2, 0.2, 0.6)]
    x, y = C["stroke"][0]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_stroke_press():
    x, y = C["stroke"][0]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


@step
def s_stroke_move():
    for x, y in C["stroke"][1:]:
        ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


@step
def s_stroke_release():
    x, y = C["stroke"][-1]
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


@step
def s_painted():
    w = joint2_weight()
    check(f"painting raised joint2's weights ({C['w0']:.2f} -> {w:.2f})", w > C["w0"] + 0.5)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_final_shot():
    shot("gui_step58_painted.png")


run()
