"""In-Blender part of tools/marketing/make_marketing.py: raw 1920 x 1080 GUI shots for the captioned
feature screens and the key visuals.

Runs in a GUI Blender on a clean sandbox with the extension installed, with --enable-event-simulate
(tests/gui/sim.py). The scene is built from the licensed models in the local assets folder
(tools/marketing/assets.json, docs/distribution/marketing/CREDITS.md; recipes in tools/marketing/scene.py): the
DOGWALK splash set (hero, hotbox), Pack Bot (components, Modeling Toolkit), Security Bot with its battery (Channel Box /
Attribute Editor, pivot) and Rain (marking menus, menus, skin weights, animation), lit by the Studio Small 09 HDRI in
Material Preview over a flat #5c5c5c viewport grey (no theme, #41). Each shot is taken one tick after the UI change
(``screen.screenshot`` shows the previous frame). meta.json records UI rects (top-down window pixels) for callouts.
The approach (event-driven steps, menus opened from mid-window, logo painted over) follows an earlier listing shot script, since removed;
the aborted 10-19 attempt (git stash) was read for the scene recipes only.
"""

import json
import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scene import (ROOT, area_rect, check_capture, clear_objects, dog_scene, dog_view, floor, frame,  # noqa: E402
                   lab_scene, look, maya_look, maya_mode_on, mod, pack_scene, prefs, rain_keys, rain_scene, redraw,
                   region_rect, screen_pos, select, shaders_ready_step, shading, show_bones, to_top,
                   v3d_override, viewport_rects)
import sim  # noqa: E402
from sim import MODULE, check, ev, run, setup, step, tap, view3d, win  # noqa: E402

RAW = Path(os.environ.get("ALLSET_SHOTS", str(ROOT / "tmp" / "marketing" / "raw")))
C = {}
META = {}


def wait():
    redraw()


def esc():
    tap('ESC')


def rects(extra=None):
    """Named UI rects in top-down window pixels for compose.py callouts."""
    out = {}
    md = mod(".ui.maya_dock")
    for a in win().screen.areas:
        key = a.ui_type
        if a.type == 'PROPERTIES':
            role = md.role_of(a) if hasattr(md, "role_of") else None
            key = f"dock_{role}" if role else "properties"
        out.setdefault(key, area_rect(a))
    area, region = view3d()
    out["viewport"] = region_rect(region)
    w = win().width
    out["switch"] = [w - 150, 0, 150, 30]          # Maya | Blender at the right of the top bar
    if extra:
        out.update(extra)
    return out


def shot(name, extra=None, plain_blender=False):
    """Save a raw shot + its meta. Maya-mode shots are checked for Maya's flat viewport background
    (tools/marketing/bg_check.py, #41); ``plain_blender`` shots show Blender's own UI and theme (excluded)."""
    RAW.mkdir(parents=True, exist_ok=True)
    path = str(RAW / f"{name}.png")
    sim.screenshot(path)
    hide_logo(path)
    vl = bpy.context.view_layer
    views = viewport_rects()
    size = [win().width, win().height]
    if plain_blender:
        bg = {"checked": False, "why": "plain Blender (Blender mode): Blender's own theme, not a Maya viewport"}
    else:
        ok, res = check_capture(path, f"shot {name}", views, size)
        bg = {"checked": True, "ok": ok, "maya_mode": maya_mode_on(), "results": res}
    META[name] = {"window": size, "rects": rects(extra), "viewports": views, "background": bg,
                  "selected": [o.name for o in bpy.context.scene.objects if o.select_get()],
                  "active": vl.objects.active.name if vl.objects.active else None, "mode": bpy.context.mode}
    with open(RAW / "meta.json", "w", encoding="utf-8") as fh:
        json.dump(META, fh, indent=1)


def hide_logo(path):
    """Paint the top bar's Blender menu icon over with the bar colour (no Blender logo in the images,
    extensions.blender.org terms 2.2), as the earlier listing shots did."""
    import numpy as np
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    size = round(30 * bpy.context.preferences.system.ui_scale)
    px[h - size:, :size] = px[h - 2, size]
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


# ------------------------------------------------------------------------------------------------ 0 before
@step
def s_before():
    tap('ESC')                                     # factory splash
    import addon_utils
    addon_utils.enable(MODULE, default_set=True)
    bpy.context.preferences.view.show_tooltips = False


step(wait)


@step
def s_welcome():
    _area, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + int(r.height * 0.62))
    with bpy.context.temp_override(window=win()):
        C["welcome"] = bpy.ops.allset.welcome('INVOKE_DEFAULT')
    check("welcome dialog opens on plain Blender", C["welcome"] == {'RUNNING_MODAL'})


step(wait)
step(wait)


@step
def s_before_shot():
    shot("switch_before", plain_blender=True)   # the "before" picture: Blender as installed
    esc()


@step
def s_opt_in():
    setup()   # opts in to Maya mode (what the dialog's button does)
    sim.load_maya_layout()   # the Maya layout startup.blend in the extension


# ------------------------------------------------------------------------------------------------ helpers
def settle(n=2):
    for _ in range(n):
        step(wait)


def shaders():
    step(shaders_ready_step())


def mouse_corner():
    _area, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width - 30, y=r.y + 30)


def object_mode():
    with v3d_override():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')


def tool(name):
    with v3d_override():
        bpy.ops.wm.tool_set_by_id(name=name)


# ------------------------------------------------------------------------------------------------ 1 DOGWALK: hero, hotbox
@step
def s_dog():
    kc = bpy.context.window_manager.keyconfigs.active
    check("Maya keymap on in the Maya layout (add-on items)",
          kc is not None and sys.modules[MODULE + ".keymap"].is_applied())
    maya_look()
    clear_objects()
    check("DOGWALK set appended (Pinda, Chocomel, snowman)", dog_scene(C))
    shading('MATERIAL', rotate=40, clip_end=1000.0)
    floor(False)                                   # the snow ground is the floor: no grid through it
    select([C["snow_head"]])
    tool("builtin.move")
    dog_view("hero")
    mouse_corner()
    redraw()


shaders()
settle(2)


@step
def s_hero_shot():
    shot("hero")


@step
def s_hotbox_press():
    select([C["pinda"]])
    tool("builtin.select_box")
    dog_view("hotbox")
    _area, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
    redraw()


settle(2)


@step
def s_hotbox_space():
    ev('SPACE', 'PRESS')


settle(2)


@step
def s_hotbox_shot():
    _area, r = view3d()
    cx, cy = r.x + r.width // 2, r.y + r.height // 2
    shot("hotbox", {"hotbox_centre": [*to_top(cx - 90, cy + 40), 180, 80]})
    ev('SPACE', 'RELEASE')


# ------------------------------------------------------------------------------------------------ 2 Pack Bot: components, MTK
@step
def s_pack():
    clear_objects()
    check("Pack Bot appended", pack_scene(C))
    shading('MATERIAL', rotate=120)
    floor(True)
    prefs().menu_set = 'modelingMenuSet'
    bpy.ops.allset.shelf_select(shelf="Polygons")
    t = C["torso"]
    select([t])
    with v3d_override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bm = bmesh.from_edit_mesh(t.data)
        zs = [v.co.z for v in bm.verts]
        lo, hi = min(zs), max(zs)
        xs = [v.co.x for v in bm.verts]
        for f in bm.faces:
            c = f.calc_center_median()
            f.select_set(c.z > lo + (hi - lo) * 0.55 and c.x > 0.0)
        bmesh.update_edit_mesh(t.data)
        bpy.ops.wm.tool_set_by_id(name="builtin.move")
    # the whole bot (about 1 m tall), not the box of its evaluated parts: in edit mode those boxes put the camera
    # at one leg
    base = C["pack_rig"].matrix_world.translation
    look(base + Vector((0, 0, 0.5)), (72, 0, -50), 2.9)
    mouse_corner()
    redraw()


shaders()


@step
def s_components_hover():
    x, y = screen_pos(C["torso"], (0, 0, 0))
    ev('MOUSEMOVE', 'NOTHING', x=x + 60, y=y + 40)
    redraw()


settle(2)


@step
def s_components_shot():
    shot("navigate_select")


@step
def s_mtk():
    sim.dock_area('MODELING_TOOLKIT')
    redraw()


settle(2)


@step
def s_mtk_shot():
    shot("modeling_toolkit", {"mtk": area_rect(sim.dock_area('MODELING_TOOLKIT'))})
    object_mode()
    tool("builtin.select_box")
    sim.dock_area('CHANNEL_BOX')
    redraw()


# ------------------------------------------------------------------------------------------------ 3 Security Bot + battery: CB / AE, pivot
@step
def s_lab():
    clear_objects()
    check("Security Bot, display case and battery appended", lab_scene(C))
    shading('MATERIAL', rotate=200)
    floor(True)
    b = C["battery"]
    select([b])
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 24
    z0 = b.location.z
    for f, dz, rz in ((1, 0.0, -25), (12, 0.04, 35), (24, 0.0, 95)):
        sc.frame_set(f)
        b.location.z = z0 + dz
        b.rotation_euler.z = math.radians(rz)
        b.keyframe_insert("location")
        b.keyframe_insert("rotation_euler")
    sc.frame_set(8)
    frame([C["case"]] + [o for o in C["sec_objs"] if o.type == 'MESH' and o.visible_get()], 0.72,
          rot=(82, 0, 30), offset=(0.15, 0, 0.05))
    md = mod(".ui.maya_dock")
    stack = sim.dock_area('CHANNEL_BOX')
    before = set(win().screen.areas[:])
    with bpy.context.temp_override(window=win(), screen=win().screen, area=stack):
        bpy.ops.screen.area_split(direction='HORIZONTAL', factor=0.62)   # AE on top, room for every CB row
    new = [a for a in win().screen.areas if a not in before]
    C["ae"] = new[0] if new else None
    if C["ae"]:
        md.set_role(C["ae"], 'ATTRIBUTE_EDITOR', win())
    with v3d_override():
        bpy.ops.allset.ae_tab(key="T")
    mouse_corner()
    redraw()


shaders()


@step
def s_cb_ae_shot():
    extra = {}
    if C.get("ae"):
        extra["ae"] = area_rect(C["ae"])
    extra["cb"] = area_rect(sim.dock_area('CHANNEL_BOX'))
    shot("channel_box_ae", extra)
    mod(".ui.maya_dock").close_area(bpy.context, win(), C.get("ae"))
    redraw()


@step
def s_pivot_press():
    b = C["battery"]
    select([b])
    tool("builtin.move")
    frame([b] + C["battery_parts"], 2.1, rot=(74, 0, 30), offset=(0, 0, 0.02))
    redraw()


settle(1)


@step
def s_pivot_d():
    x, y = screen_pos(C["battery"], (0, 0, 0.07))
    C["piv"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('D', 'PRESS', x=x, y=y)


settle(1)


@step
def s_pivot_rmb():
    ev('RIGHTMOUSE', 'PRESS', x=C["piv"][0], y=C["piv"][1])


settle(2)


@step
def s_pivot_shot():
    x, y = C["piv"]
    shot("pivot_snapping", {"press": [*to_top(x - 12, y + 12), 24, 24]})
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y)
    esc()


@step
def s_pivot_release():
    ev('D', 'RELEASE', x=C["piv"][0], y=C["piv"][1])
    tool("builtin.select_box")
    redraw()


# ------------------------------------------------------------------------------------------------ 4 Rain: marking menus, menus, skin weights, animation
@step
def s_rain():
    clear_objects()
    check("Rain rig appended", rain_scene(C))
    shading('MATERIAL', rotate=150)
    floor(True)
    select([C["top_mesh"]])
    frame(C["rain_meshes"], 0.68, rot=(86, 0, -14), offset=(0, 0, 0.28))
    redraw()


shaders()


@step
def s_rmb_press():
    x, y = screen_pos(None, world=(0.0, 0.0, 1.18))
    C["rmb"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)


settle(2)


@step
def s_rmb_shot():
    x, y = C["rmb"]
    shot("marking_menus", {"press": [*to_top(x - 12, y + 12), 24, 24]})
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y)
    esc()


@step
def s_rigging():
    prefs().menu_set = 'riggingMenuSet'
    bpy.ops.allset.shelf_select(shelf="Rigging")
    select([C["rig"]])
    show_bones(True)
    frame(C["rain_meshes"], 0.8, rot=(86, 0, 22), offset=(0.12, 0, 0.12))
    redraw()


settle(1)


@step
def s_rig_menu():
    _area, region = view3d()
    C["menu_at"] = (region.x + int(region.width * 0.2), region.y + int(region.height * 0.8))
    ev('MOUSEMOVE', 'NOTHING', x=C["menu_at"][0], y=C["menu_at"][1])
    name = mod(".ui.menu_sets").menu_idname("mainRigSkeletonsMenu")
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.call_menu(name=name)


settle(2)


@step
def s_rig_shot():
    shot("menus_shelves")
    esc()


@step
def s_paint():
    mesh = C["body"]
    select([mesh])
    res = None
    with v3d_override():
        try:
            res = bpy.ops.allset.paint_skin_weights()
        except RuntimeError as e:
            print("paint_skin_weights:", e)
        if bpy.context.mode != 'PAINT_WEIGHT':
            bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
    vg = mesh.vertex_groups.get("DEF-Upperarm1.L") or next(
        (g for g in mesh.vertex_groups if "upperarm" in g.name.lower()), None)
    if vg is not None:
        mesh.vertex_groups.active_index = vg.index
    show_bones(True)
    check(f"rigging: Paint Skin Weights on Rain ({res}, group {vg.name if vg else None})",
          bpy.context.mode == 'PAINT_WEIGHT' and vg is not None)
    frame(C["rain_meshes"], 0.74, rot=(86, 0, 30), offset=(0.1, 0, 0.28))
    mouse_corner()
    redraw()


shaders()


@step
def s_paint_shot():
    shot("rigging", {"cb": area_rect(sim.dock_area('CHANNEL_BOX'))})
    object_mode()
    prefs().menu_set = 'animationMenuSet'
    bpy.ops.allset.shelf_select(shelf="Animation")


@step
def s_anim():
    rig = C["rig"]
    rain_keys(rig)
    bpy.context.scene.frame_end = 24
    select([rig])
    with v3d_override():
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.select_all(action='DESELECT')
    hand = rig.pose.bones["IK-Hand_Parent.R"]
    rig.data.bones.active = hand.bone
    mod(".ui.channel_box").set_bone_selected(hand, True)
    bpy.context.scene.frame_set(8)
    area, _r = view3d()
    before = set(win().screen.areas[:])
    with bpy.context.temp_override(window=win(), screen=win().screen, area=area):
        bpy.ops.screen.area_split(direction='HORIZONTAL', factor=0.5)
    new = [a for a in win().screen.areas if a not in before]
    C["graph"] = None
    if new:
        top = new[0]
        if hasattr(top.spaces.active, "show_region_asset_shelf"):
            top.spaces.active.show_region_asset_shelf = False   # its 29 px header row drew stale pixels
        bottom = min((a for a in win().screen.areas if a.type == 'VIEW_3D' and a is not top
                      and a.x == top.x and a.width == top.width), key=lambda a: a.y)
        bottom.ui_type = 'FCURVES'
        bottom.spaces.active.show_region_ui = False
        bottom.spaces.active.dopesheet.show_only_selected = True
        C["graph"] = bottom
    redraw()


@step
def s_anim_graph():
    a = C["graph"]
    check("Graph Editor split under the viewport", a is not None)
    r = next(rg for rg in a.regions if rg.type == 'WINDOW')
    with bpy.context.temp_override(window=win(), area=a, region=r):
        bpy.ops.graph.select_all(action='SELECT')
        bpy.ops.graph.view_all()
    frame(C["rain_meshes"], 1.55, rot=(86, 0, 20), offset=(0, 0, 0.12))
    shading('MATERIAL', rotate=150)
    show_bones(True)
    mouse_corner()
    redraw()


shaders()
settle(2)   # the split area keeps stale pixels of the old view for a tick or two


@step
def s_anim_shot():
    extra = {"graph": area_rect(C["graph"])} if C.get("graph") else {}
    shot("animation", extra)


run(interval=0.7, first=3.0)
