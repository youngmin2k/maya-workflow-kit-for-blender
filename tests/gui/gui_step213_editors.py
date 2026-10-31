"""#119: in a real UI: Windows > General Editors > Component Editor (a skinned cylinder with vertices
selected in edit mode), Windows > Animation Editors > Shape Editor (pCube1 with a blendShape and an added target) and
Windows > General Editors > Connection Editor (pCube1 / pSphere1 loaded, translate connected) each open a new window
whose Properties area is the kit editor (Maya menu bar, no Blender header); shots
with ``--shots``."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, setup, step, win  # noqa: E402

GUI_TIMEOUT = 220
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


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


def window_of(kind):
    mw = mod(".ui.marked_window")
    w = mw.find_window(bpy.context, kind)
    return w, (next((a for a in w.screen.areas if mw.kind_of(a) == kind), None) if w else None)


def close_others():
    wm = bpy.context.window_manager
    for w in list(wm.windows)[1:]:
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()


def check_window(kind, title, ret):
    w, area = window_of(kind)
    check(f"Windows > ... > {title} opens a window with the kit editor ({ret})", w is not None and area is not None)
    if area is not None:
        check(f"{title}: one area, no Blender header (Maya window)",
              len(w.screen.areas) == 1 and not area.spaces.active.show_region_header)
        ms = mod(".ui.menu_sets")
        n = len(mod(".ui.editor_menu_data").EDITORS[title])
        check(f"{title}: its {n} Maya menus are registered",
              all(hasattr(bpy.types, ms.editor_menu_idname(title, i)) for i in range(n)))
    C["win"] = w
    redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CYLINDER')
    cyl = bpy.context.active_object
    C["cyl"] = cyl.name
    arm_data = bpy.data.armatures.new("skeleton1")
    arm = bpy.data.objects.new("joint1", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='EDIT')
        for i, name in enumerate(("joint1", "joint2")):
            eb = arm_data.edit_bones.new(name)
            eb.head, eb.tail = (0, 0, -0.01 + i * 0.01), (0, 0, i * 0.01)
            if i:
                eb.parent = arm_data.edit_bones["joint1"]
        bpy.ops.object.mode_set(mode='OBJECT')
        for o in bpy.context.scene.objects:
            if o.visible_get():
                o.select_set(o in (arm, cyl))
        bpy.context.view_layer.objects.active = cyl
        C["bind"] = bpy.ops.allset.bind_skin()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
    import bmesh
    bm = bmesh.from_edit_mesh(cyl.data)
    for v in list(bm.verts)[:4]:
        v.select = True
    bmesh.update_edit_mesh(cyl.data)
    check(f"skinned cylinder ({C['bind']})", C["bind"] == {'FINISHED'})
    C["open"] = menu("Windows/General Editors/Component Editor")


@step
def s_component():
    redraw()


@step
def s_component_check():
    check_window("COMPONENT_EDITOR", "Component Editor", C["open"])


@step
def s_component_shot():
    if C.get("win"):
        shot("gui_step213_component_editor.png", C["win"])
    close_others()
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.allset.create(kind='CUBE')
    cube = bpy.context.active_object
    C["cube"] = cube.name
    for o in bpy.context.scene.objects:
        if o.visible_get():
            o.select_set(o == cube)
    C["create"] = bpy.ops.allset.shape_create()
    C["add"] = bpy.ops.allset.shape_add_target()
    key = cube.data.shape_keys
    C["targets"] = [kb.name for kb in key.key_blocks] if key else []
    C["open"] = menu("Windows/Animation Editors/Shape Editor")


@step
def s_shape():
    redraw()


@step
def s_shape_check():
    cube = bpy.data.objects[C["cube"]]
    key = cube.data.shape_keys
    check(f"Create Blend Shape + Add Target: {key and key.name} {C['targets']} ({C['create']}, {C['add']})",
          key is not None and key.name.startswith("blendShape") and len(C["targets"]) == 2)
    check_window("SHAPE_EDITOR", "Shape Editor", C["open"])


@step
def s_shape_shot():
    if C.get("win"):
        shot("gui_step213_shape_editor.png", C["win"])
    close_others()
    for kb_ob in (C["cube"],):
        ob = bpy.data.objects[kb_ob]
        if bpy.context.view_layer.objects.active is not None and bpy.context.mode != 'OBJECT':
            area, region = v3d()
            with bpy.context.temp_override(window=win(), area=area, region=region):
                bpy.ops.object.mode_set(mode='OBJECT')
        ob.select_set(True)
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='SPHERE')
    sphere = bpy.context.active_object
    wm = bpy.context.window_manager
    wm.allset_cn_left, wm.allset_cn_right = C["cube"], sphere.name
    wm.allset_cn_left_attr = "translate"
    bpy.ops.allset.cn_pick(side="RIGHT", attr="translate")
    ce = mod(".ui.connection_editor")
    check("Connection Editor pick: translate -> translate connected (drivers)",
          ce.connected(bpy.data.objects[C["cube"]], "translate", sphere, "translate"))
    wm.allset_cn_open = "LEFT:translate,RIGHT:translate"
    C["open"] = menu("Windows/General Editors/Connection Editor")


@step
def s_connection():
    redraw()


@step
def s_connection_check():
    check_window("CONNECTION_EDITOR", "Connection Editor", C["open"])


@step
def s_connection_shot():
    if C.get("win"):
        shot("gui_step213_connection_editor.png", C["win"])
    shot("gui_step213_main.png")
    close_others()


run()
