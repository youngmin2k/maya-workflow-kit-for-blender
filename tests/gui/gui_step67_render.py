"""Step 67 in a real UI (Maya render workflow): sphere -> Windows > Rendering Editors >
Hypershade -> a window in the Maya Hypershade layout (step 131: panes + Graph) -> Create Standard Surface -> Assign Material To
Selection -> AE Base Color map button > File -> Render > Render Current Frame -> Keep Image -> render again -> two
slots used; Windows > Rendering Editors > Light Editor -> an Outliner window of the lights (screenshots)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, run, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(sys.modules["sim"].MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def redraw_all():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def window_with(ui_type):
    for w in bpy.context.window_manager.windows[1:]:
        for a in w.screen.areas:
            if a.ui_type == ui_type:
                return w, a
    return None, None


def run_menu(path):
    area, region = view3d()
    modal = mod(".marking.modal")
    menu_map = mod(".ui.menu_map")
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return modal.run_action(bpy.context, menu_map.MAP[path])


def wait(fn, cond, limit=40):
    """Run ``fn`` again next tick until ``cond()`` or ``limit`` ticks."""
    C.setdefault(fn.__name__, 0)
    if not cond() and C[fn.__name__] < limit:
        C[fn.__name__] += 1
        sys.modules["sim"]._steps.insert(0, fn)
        return True
    return False


@step
def s_setup():
    C["x"], C["y"] = setup()
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'          # fast: the render path, not the look, is checked
    sc.render.resolution_percentage = 50
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='SPHERE')
    C["sphere"] = bpy.context.active_object.name
    C["open"] = run_menu("Windows/Rendering Editors/Hypershade")


def hypershade_ready():
    """(window, graph area, Browser pane) once the Hypershade window has all its panes (step 131), else Nones."""
    hs = mod(".ui.hypershade")
    for w in bpy.context.window_manager.windows[1:]:
        panes = {hs.pane(a): a for a in w.screen.areas if hs.pane(a)}
        if len(panes) == 4 and hs.graph_area(w.screen) is not None:
            return w, hs.graph_area(w.screen), panes['BROWSER']
    return None, None, None


@step
def s_hypershade_open():
    w, a, browser = hypershade_ready()
    if w is None and wait(s_hypershade_open, lambda: hypershade_ready()[0] is not None):
        redraw_all()
        return
    check(f"Windows > Rendering Editors > Hypershade: a window with Browser / Create / Material Viewer / Property "
          f"Editor panes and the Graph (got {C['open']}, {w is not None})", w is not None)
    C["hs"] = (w, a)
    # Create > Standard Surface from the Create pane (a Properties editor), then Assign Material To Selection
    region = next(r for r in browser.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=w, area=browser, region=region, space_data=browser.spaces.active):
        bpy.ops.allset.hs_create(kind='STANDARD_SURFACE')
    mat = bpy.data.materials.get("standardSurface1")
    sphere = bpy.data.objects[C["sphere"]]
    # step 100: the new sphere already has the default lambert1
    check(f"Create > Standard Surface: standardSurface1, not assigned yet, graph pinned to it "
          f"({mat is not None}, {sphere.active_material and sphere.active_material.name}, {a.spaces.active.pin})",
          mat is not None and sphere.active_material is not mat and a.spaces.active.pin
          and a.spaces.active.node_tree == mat.node_tree)
    with bpy.context.temp_override(window=w, area=browser, region=region):
        bpy.ops.allset.assign_material(material="standardSurface1")
    C["browser"] = browser
    redraw_all()


@step
def s_assigned():
    sphere = bpy.data.objects[C["sphere"]]
    check(f"Assign Material To Selection: {sphere.name} slot 0 = standardSurface1",
          sphere.material_slots and sphere.material_slots[0].material.name == "standardSurface1")
    w, a = C["hs"]
    # pick it in the Browser pane: the graph follows the object again (unpinned)
    browser = C["browser"]
    region = next(r for r in browser.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=w, area=browser, region=region, space_data=browser.spaces.active):
        bpy.ops.allset.hs_pick(material="standardSurface1")
    # AE Base Color map button > File
    bpy.ops.allset.ae_map_connect(material="standardSurface1", socket="Base Color", kind='FILE')
    redraw_all()


@step
def s_mapped():
    w, a = C["hs"]
    mat = bpy.data.materials["standardSurface1"]
    inp = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED').inputs["Base Color"]
    check(f"AE Base Color map > File: Image Texture linked to Base Color, graph unpinned "
          f"({inp.is_linked and inp.links[0].from_node.type}, pin {a.spaces.active.pin})",
          inp.is_linked and inp.links[0].from_node.type == 'TEX_IMAGE' and not a.spaces.active.pin)
    redraw_all()


@step
def s_shot_hypershade():
    w, _a = C["hs"]
    shot("gui_step67_hypershade.png", w)
    C["render"] = run_menu("Render/Render Current Frame")


@step
def s_rendered():
    if wait(s_rendered, lambda: not bpy.app.is_job_running('RENDER') and window_with('IMAGE_EDITOR')[0] is not None):
        return
    rv = mod(".ui.render_view")
    image = rv.render_result()
    w, a = window_with('IMAGE_EDITOR')
    check(f"Render > Render Current Frame: Render Result in a Render View window (got {C['render']}, "
          f"{image is not None}, {a is not None})", image is not None and a is not None)
    C["rv"] = (w, a)
    image[rv.KEPT_PROP] = []
    image.render_slots.active_index = 0
    redraw_all()


@step
def s_keep():
    w, a = C["rv"]
    shot("gui_step67_render_view.png", w)
    header = next(r for r in a.regions if r.type == 'HEADER')
    with bpy.context.temp_override(window=w, area=a, region=header, space_data=a.spaces.active):
        bpy.ops.allset.render_keep_image()
    C["slot_after_keep"] = mod(".ui.render_view").render_result().render_slots.active_index
    C["render2"] = run_menu("Render/Render Current Frame")


@step
def s_rendered_again():
    if wait(s_rendered_again, lambda: not bpy.app.is_job_running('RENDER')):
        return
    rv = mod(".ui.render_view")
    image = rv.render_result()
    slots = image.render_slots
    check(f"Keep Image -> render again: slot 1 kept, the new render in slot 2 "
          f"(kept {sorted(rv.kept(image))}, active {slots.active_index}, after keep {C['slot_after_keep']})",
          rv.kept(image) == {0} and slots.active_index == 1 and C["slot_after_keep"] == 1)
    redraw_all()


@step
def s_light():
    w, _a = C["rv"]
    shot("gui_step67_keep_image.png", w)
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='POINT_LIGHT')
        bpy.ops.allset.create(kind='DIRECTIONAL_LIGHT')
    C["le"] = run_menu("Windows/Rendering Editors/Light Editor")
    C["nwin"] = len(bpy.context.window_manager.windows)


@step
def s_light_open():
    w = bpy.context.window_manager.windows[-1]
    a = w.screen.areas[0]
    sp = a.spaces.active
    check(f"Windows > Rendering Editors > Light Editor: an Outliner window that lists only lights "
          f"(got {C['le']}, windows {C['nwin']}, {a.type})",
          a.type == 'OUTLINER' and sp.use_filter_object and sp.use_filter_object_light
          and not sp.use_filter_object_mesh and not sp.use_filter_object_camera)
    C["lew"] = w
    redraw_all()


@step
def s_render_settings():
    C["nwin_rs"] = len(bpy.context.window_manager.windows)
    C["rs"] = run_menu("Render/Render Settings...")


@step
def s_render_settings_open():
    w = bpy.context.window_manager.windows[-1]
    a = w.screen.areas[0]
    check(f"Render > Render Settings...: its own Properties window on the Render tab "
          f"(got {C['rs']}, windows {C['nwin_rs']} -> {len(bpy.context.window_manager.windows)}, {a.type}, "
          f"{getattr(a.spaces.active, 'context', None)})",
          len(bpy.context.window_manager.windows) == C["nwin_rs"] + 1 and a.type == 'PROPERTIES'
          and a.spaces.active.context == 'RENDER')
    shot("gui_step67_render_settings.png", w)


@step
def s_end():
    shot("gui_step67_light_editor.png", C["lew"])


run()
