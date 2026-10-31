"""#92 #86: in the Maya Workflow Kit layout: Ctrl+E, Ctrl+B, the Joint Tool started from the Rigging shelf
and the IK Handle Tool leave no Adjust Last Operation panel anywhere, and the shelf click after Create Joints reaches
the shelf (#86: the Joint Tool panel covered the shelf and ate it)."""

import os
import sys
from importlib import import_module

import bmesh
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, scale, screenshot, setup, step, tap, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
shelf = import_module(MODULE + ".ui.shelf")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def huds():
    """Shown Adjust Last Operation regions in every area: Blender hides a cleared HUD by zeroing its window rect
    (hud_region_hide), a shown one never sits at the window origin (gui_step134_display.hud)."""
    out = []
    for area in win().screen.areas:
        for r in area.regions:
            if r.type == 'HUD' and r.width > 1 and r.height > 1 and (r.x, r.y) != (0, 0):
                out.append((area.type, r.x, r.y, r.width, r.height))
    return out


def main_view():
    toolbox = import_module(MODULE + ".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def centre():
    _a, r = main_view()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


def key(type, **mods):
    names = {"ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT", "alt": "LEFT_ALT"}
    for m in mods:
        ev(names[m], 'PRESS')
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)
    for m in mods:
        ev(names[m], 'RELEASE')


def override():
    area, region = main_view()
    return bpy.context.temp_override(window=win(), area=area, region=region, space_data=area.spaces.active)


def icon_centre(label):
    _cur, buttons = shelf.icon_buttons(bpy.context)
    slot = next(k for k, b in enumerate(buttons) if b[1] == label)
    area = shelf.shelf_row_area(win().screen)
    r = next(r for r in area.regions if r.type == 'WINDOW')
    x, y, size = shelf.icon_rect(r, slot, scale())
    return round(r.x + x + size / 2), round(r.y + y + size / 2)


def cube():
    return bpy.data.objects["pCube1"]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    with override():
        bpy.ops.allset.create(kind='CUBE')
    for o in bpy.context.scene.objects:
        o.select_set(o.name == "pCube1")
    bpy.context.view_layer.objects.active = cube()
    centre()
    # the Maya layout views keep Blender's HUD region off (Maya has no redo panel); turn it on here so the
    # check below still proves that kit commands don't ask for Adjust Last Operation
    area, _r = main_view()
    with override():
        area.spaces.active.show_region_hud = True
    # positive control: Alt+W = Blender's object.location_clear (REGISTER + UNDO, a visible property) keeps its panel
    key('W', alt=True)


@step
def s_control():
    h = huds()
    check(f"control: Alt+W (Blender's Clear Location) shows Adjust Last Operation (detector sees {h})", bool(h))
    with override():
        bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(cube().data)
    for f in bm.faces:
        f.select_set(f.normal.z > 0.9)
    bmesh.update_edit_mesh(cube().data)
    C["verts"] = len(bm.verts)
    centre()
    key('E', ctrl=True)


@step
def s_extruded():
    n = len(bmesh.from_edit_mesh(cube().data).verts)
    h = huds()
    shot("gui_step147_ctrl_e.png")
    check(f"Ctrl+E extruded the top face ({C['verts']} -> {n} verts)", n == C["verts"] + 4)
    check(f"#92 no Adjust Last Operation after Ctrl+E ({h})", not h)
    bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
    bm = bmesh.from_edit_mesh(cube().data)
    for e in bm.edges:
        e.select_set(False)
    bm.edges[0].select_set(True)
    bmesh.update_edit_mesh(cube().data)
    C["verts"] = len(bm.verts)
    centre()
    key('B', ctrl=True)


@step
def s_beveled():
    n = len(bmesh.from_edit_mesh(cube().data).verts)
    h = huds()
    shot("gui_step147_ctrl_b.png")
    check(f"Ctrl+B bevelled the edge ({C['verts']} -> {n} verts)", n > C["verts"])
    check(f"#92 no Adjust Last Operation after Ctrl+B ({h})", not h)
    with override():
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.allset.shelf_select(shelf="Rigging")
    redraw()


@step
def s_joints_hover():
    C["joints_icon"] = icon_centre("Create Joints")
    ev('MOUSEMOVE', 'NOTHING', x=C["joints_icon"][0], y=C["joints_icon"][1])
    redraw()


@step
def s_joints_click():
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_joint_tool():
    names = [op.bl_idname for op in win().modal_operators]
    check(f"Rigging shelf > Create Joints starts the Joint Tool ({names})", "ALLSET_OT_joint_tool" in names)
    _a, r = main_view()
    C["clicks"] = [(r.x + r.width * f // 10, r.y + r.height * g // 10) for f, g in ((3, 3), (4, 2), (5, 3), (6, 2))]
    C["i"] = 0


def _place():
    x, y = C["clicks"][C["i"]]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    C["i"] += 1


for _n in range(4):
    step(_place)


@step
def s_enter():
    centre()
    tap('RET')


@step
def s_joints_done():
    sk = bpy.data.objects.get("skeleton1")
    n = len(sk.data.bones) if sk else 0
    h = huds()
    shot("gui_step147_joints.png")
    check(f"four clicks + Enter = four joints ({n})", n == 4)
    check(f"#86 no Adjust Last Operation after the Joint Tool, over the shelf or anywhere ({h})", not h)
    C["ik_icon"] = icon_centre("Create IK Handle")
    ev('MOUSEMOVE', 'NOTHING', x=C["ik_icon"][0], y=C["ik_icon"][1])
    redraw()


@step
def s_ik_click():
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_ik_tool():
    names = [op.bl_idname for op in win().modal_operators]
    check(f"#86 the next shelf click (Create IK Handle) reaches the shelf: IK Handle Tool runs ({names})",
          "ALLSET_OT_ik_handle" in names)
    sk = bpy.data.objects["skeleton1"]
    area, r = main_view()
    rv3d = area.spaces.active.region_3d
    pts = []
    for name in ("joint1", "joint4"):
        bone = sk.data.bones[name]
        p = location_3d_to_region_2d(r, rv3d, sk.matrix_world @ (bone.head_local if name == "joint1" else
                                                                   bone.tail_local))
        pts.append((r.x + round(p.x), r.y + round(p.y)))
    C["ik_pts"] = pts
    C["k"] = 0


def _ik_click():
    x, y = C["ik_pts"][C["k"]]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    C["k"] += 1


step(_ik_click)
step(_ik_click)


@step
def s_ik_done():
    pass


@step
def s_ik_checked():
    h = huds()
    shot("gui_step147_ik.png")
    made = bpy.data.objects.get("ikHandle1")
    names = [op.bl_idname for op in win().modal_operators]
    check(f"IK Handle Tool made ikHandle1 ({made and made.name}, modal {names})", made is not None)
    check(f"#92 no Adjust Last Operation after the IK Handle Tool ({h})", not h)
    tap('ESC')


run()
