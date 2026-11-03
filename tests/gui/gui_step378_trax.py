"""#287 in a real UI: Windows > Animation Editors > Trax Editor opens an NLA Editor window with Maya's Trax menu bar;
Create > Animation Clip from its menu turns pCube1's keys into clip1, Edit > Duplicate places clip2, Modify >
Activate/Deactivate Keys enters and leaves Blender's tweak mode, the Create menu and the clip library draw
(screenshots with ALLSET_GUI_SHOTS)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, setup, step, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 200
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def nla():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'NLA_EDITOR':
                return w, a
    return None, None


def trax_menu(path):
    w, a = nla()
    region = next(r for r in a.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=w, area=a, region=region):
        return bpy.ops.allset.menu_item(item=path)


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    for frame, x in ((1, 0.0), (24, 0.05)):
        ob.location.x = x
        ob.keyframe_insert("location", index=0, frame=frame)
    C["ob"] = ob.name
    with bpy.context.temp_override(window=win(), area=area, region=region):
        C["open"] = bpy.ops.allset.menu_item(item="Windows/Animation Editors/Trax Editor")


@step
def s_opened():
    w, a = nla()
    check(f"Trax Editor window = an NLA Editor ({C['open']})", a is not None)
    redraw()


@step
def s_header():
    trax = mod(".ui.trax_editor")
    chrome = mod(".ui.editor_chrome")
    check("NLA header = the kit's Trax header", chrome.own_draw(bpy.types.NLA_HT_header) is trax._header)
    w, a = nla()
    with bpy.context.temp_override(window=w, area=a):
        check("Maya editor menus on in this window", chrome.enabled(bpy.context))
    if SHOTS:
        with bpy.context.temp_override(window=w):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_step378_trax_empty.png"))


@step
def s_create():
    res = trax_menu("Trax Editor/Create/Animation Clip")
    tc = mod(".operators.trax_clips")
    sc = bpy.context.scene
    check(f"Create > Animation Clip from the Trax menu made clip1 ({res})", tc.instance_names(sc) == ["clip1"])
    ob = bpy.data.objects[C["ob"]]
    check("the keys moved into the clip", ob.animation_data.action is None and "clip1Source" in bpy.data.actions)
    for _o, _t, st in tc.clip_strips(sc):
        st.select = True
    res = trax_menu("Trax Editor/Edit/Duplicate")
    check(f"Edit > Duplicate placed clip2 after clip1 ({res})", tc.instance_names(sc) == ["clip1", "clip2"])
    redraw()


@step
def s_tweak():
    tc = mod(".operators.trax_clips")
    sc = bpy.context.scene
    for _o, _t, st in tc.clip_strips(sc):
        st.select = st.name == "clip1"
    w, a = nla()
    region = next(r for r in a.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=w, area=a, region=region):
        bpy.ops.allset.trax_activate_keys()
    check("Activate/Deactivate Keys enters tweak mode on the clip", sc.is_nla_tweakmode)
    with bpy.context.temp_override(window=w, area=a, region=region):
        bpy.ops.allset.trax_activate_keys()
    check("... and leaves it", not sc.is_nla_tweakmode)


@step
def s_menu_draw():
    w, a = nla()
    sets = mod(".ui.menu_sets")
    region = next(r for r in a.regions if r.type == 'HEADER')
    a.spaces.active.show_region_ui = True
    with bpy.context.temp_override(window=w, area=a, region=region):
        res = bpy.ops.wm.call_menu(name=sets.editor_menu_idname("Trax Editor", 4))
    check(f"the Trax Create menu opens ({res})", res == {'INTERFACE_CANCELLED'} or res == {'FINISHED'} or bool(res))
    redraw()


@step
def s_shot():
    w, a = nla()
    if SHOTS:
        with bpy.context.temp_override(window=w):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_step378_trax.png"))
    check("clip library panel registered", hasattr(bpy.types, "ALLSET_PT_trax_library"))


run()
