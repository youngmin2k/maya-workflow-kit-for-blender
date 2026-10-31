"""FX items never show a Python error: Quick Smoke (Fluids > 3D Container, Emit from Object, Effects > Fire / Smoke,
the 3D Fluid Container shelf button) leaves out meshes that already are fluids, warns when every selected mesh is one
and keeps Blender's own message when no mesh is selected."""

from importlib import import_module

import bpy

import kit
from test_issue123_fx_render import _cube, _scene, _select

menu_map = import_module(kit.MODULE + ".ui.menu_map")
shelf_map = import_module(kit.MODULE + ".ui.shelf_map")
modal = import_module(kit.MODULE + ".marking.modal")

SMOKE_PATHS = ("Fluids/3D Container", "Fluids/Add/Edit Contents/Emit from Object", "Effects/Fire", "Effects/Smoke")


def _run(path):
    """Run the item the way the Maya menu does (marking/modal.run_action)."""
    return modal.run_action(bpy.context, menu_map.MAP[path], path=path)


def _fluid_types(ob):
    return [m.fluid_type for m in ob.modifiers if m.type == 'FLUID']


def _domains():
    return [o for o in bpy.data.objects if 'DOMAIN' in _fluid_types(o)]


def test_smoke_items_use_the_guarded_operator():
    for path in SMOKE_PATHS:
        _kind, target, _props = menu_map.spec(path)
        assert target == "allset.fluid_quick_smoke", (path, target)
    action, _icon = shelf_map.lookup("FX", "3D Fluid Container with Emitter", "Create3DContainerEmitter")
    assert action == "allset.fluid_quick_smoke", action
    # no FX / render item calls Blender's Python Quick Smoke directly
    assert not any(menu_map.normalize(v)[1] == "object.quick_smoke" for v in menu_map.MAP.values()
                   if menu_map.normalize(v) is not None)


def test_every_mesh_already_a_fluid_warns():
    for path in SMOKE_PATHS:
        _scene()
        a, b = _cube("pCube1"), _cube("pCube2", z=4.0)
        _select(a, b)
        assert _run(path) == {'FINISHED'}, path
        domains = len(_domains())
        _select(a, b)
        assert _run(path) == {'CANCELLED'}, path            # a Warning, no Python error
        assert len(_domains()) == domains, path
        assert _fluid_types(a) == ['FLOW'] and _fluid_types(b) == ['FLOW'], path
        dom = _domains()[0]
        _select(dom)                                         # the domain itself is a fluid too
        assert _run(path) == {'CANCELLED'}, path
        assert _fluid_types(dom) == ['DOMAIN']


def test_meshes_already_fluids_are_left_out():
    for path in SMOKE_PATHS:
        _scene()
        a, b = _cube("pCube1"), _cube("pCube2", z=4.0)
        _select(a)
        _run(path)
        _select(a, b)
        assert _run(path) == {'FINISHED'}, path
        assert _fluid_types(a) == ['FLOW'] and _fluid_types(b) == ['FLOW'], path
        assert len(_domains()) == 2, path


def test_menu_item_reports_no_python_error():
    _scene()
    a = _cube("pCube1")
    _select(a)
    assert bpy.ops.allset.menu_item(item="Effects/Smoke") == {'FINISHED'}
    _select(a)
    bpy.ops.allset.menu_item(item="Effects/Smoke")            # raises nothing
    assert len(_domains()) == 1


def test_no_mesh_keeps_blenders_message():
    _scene()
    bpy.ops.object.camera_add()
    cam = bpy.context.active_object
    for sel in ((), (cam,)):
        _select(*sel)
        try:
            _run("Effects/Smoke")
        except RuntimeError as ex:
            text = str(ex)
            assert "Traceback" not in text and "Select at least one mesh object" in text, text
        else:
            raise AssertionError("expected Blender's error report")
    assert not _domains()
