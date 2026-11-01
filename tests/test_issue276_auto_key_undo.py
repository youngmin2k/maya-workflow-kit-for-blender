"""Auto Key and undo (#276): a change with its own undo step (a transform) and the Auto Key step after it are taken
back by one Undo and brought back by one Redo, keys included; a change without a step of its own keeps the plain
behaviour (Undo takes back the keys only). The same pairing makes the Maya joint pick after Blender's box select one
undo step."""

from importlib import import_module

import bpy

import kit

auto_key = import_module(kit.MODULE + ".operators.auto_key")
undo_pairs = import_module(kit.MODULE + ".operators.undo_pairs")


def _clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)
    bpy.context.scene.frame_set(1)


def _keyed_cube():
    """A cube keyed at frame 1 (x = 0), the time at frame 10."""
    _clear()
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ob.location.x = 0.0
    ob.keyframe_insert("location", index=0, frame=1)
    bpy.context.scene.frame_set(10)
    bpy.ops.ed.undo_push(message="Set Key")
    return ob.name


def _state(name):
    ob = bpy.data.objects[name]
    fc = kit.fcurves(ob).find("location", index=0)
    return round(ob.location.x, 4), len(fc.keyframe_points)


def _flush():
    if bpy.app.timers.is_registered(auto_key._flush):
        bpy.app.timers.unregister(auto_key._flush)
    auto_key._flush()


def _extra():
    """Run the kit's extra undo / redo step now (a timer in the UI)."""
    if bpy.app.timers.is_registered(undo_pairs.run_extra):
        bpy.app.timers.unregister(undo_pairs.run_extra)
    wanted = undo_pairs.wanted()
    undo_pairs.run_extra()
    return wanted


def _undo():
    bpy.ops.ed.undo()
    auto_key._reload_seen()                     # the timer after the reload's update
    return _extra()


def _redo():
    bpy.ops.ed.redo()
    auto_key._reload_seen()
    return _extra()


class _AutoKey:
    def __enter__(self):
        auto_key._pending.clear()
        undo_pairs.reset()
        auto_key._reloaded[0] = False
        bpy.context.scene.allset_auto_key = True

    def __exit__(self, *_exc):
        bpy.context.scene.allset_auto_key = False
        auto_key._pending.clear()
        for fn in (auto_key._flush, undo_pairs.run_extra):
            if bpy.app.timers.is_registered(fn):
                bpy.app.timers.unregister(fn)


def _move(name, x, push=True):
    """A change of the keyed channel; ``push``: with its own undo step, like a transform."""
    ob = bpy.data.objects[name]
    ob.location.x = x
    bpy.context.view_layer.update()
    if push:
        bpy.ops.ed.undo_push(message="Move")
    auto_key._pending[name] = bpy.context.scene.frame_current
    _flush()


def test_one_undo_and_one_redo_per_keyed_move():
    with _AutoKey():
        name = _keyed_cube()
        start = _state(name)
        _move(name, 2.0)
        first = _state(name)
        assert first == (2.0, 2), first
        _move(name, 3.0)
        second = _state(name)
        assert second == (3.0, 2), second           # the key at 10 is replaced

        assert _undo() == 'UNDO'
        assert _state(name) == first, (_state(name), first)
        assert _undo() == 'UNDO'
        assert _state(name) == start, (_state(name), start)

        assert _redo() == 'REDO'
        assert _state(name) == first, (_state(name), first)
        assert _redo() == 'REDO'
        assert _state(name) == second, (_state(name), second)


def test_undo_then_new_move_then_undo():
    with _AutoKey():
        name = _keyed_cube()
        start = _state(name)
        _move(name, 2.0)
        _undo()
        assert _state(name) == start
        _move(name, 4.0)                            # a new branch: the old redo steps are gone
        assert _state(name) == (4.0, 2)
        assert _undo() == 'UNDO'
        assert _state(name) == start, _state(name)
        assert _redo() == 'REDO'
        assert _state(name) == (4.0, 2), _state(name)


def test_change_without_its_own_step_keeps_the_plain_undo():
    with _AutoKey():
        name = _keyed_cube()
        _move(name, 2.0)
        first = _state(name)
        _move(name, 5.0, push=False)                # e.g. a script: only the Auto Key step holds it
        assert _state(name) == (5.0, 2)
        assert _undo() is None                       # no extra step: that would take back the earlier move
        assert _state(name) == first, (_state(name), first)


def test_plain_steps_are_not_skipped():
    with _AutoKey():
        name = _keyed_cube()
        _move(name, 2.0)
        bpy.ops.mesh.primitive_uv_sphere_add()
        bpy.ops.ed.undo_push(message="Sphere")
        assert _undo() is None
        assert "Sphere" not in bpy.data.objects
        assert _state(name) == (2.0, 2), (_state(name), auto_key._seen)


def test_a_pair_without_check_is_one_step():
    """Blender's box select, then the kit's joint pick: one Undo, one Redo."""
    with _AutoKey():
        _keyed_cube()
        bpy.ops.mesh.primitive_uv_sphere_add()
        bpy.ops.ed.undo_push(message="Box Select")
        bpy.data.objects["Sphere"].name = "Picked"
        undo_pairs.push(bpy.context.scene, "Select")
        assert _undo() == 'UNDO'
        assert "Sphere" not in bpy.data.objects and "Picked" not in bpy.data.objects
        assert _redo() == 'REDO'
        assert "Picked" in bpy.data.objects


def test_an_undo_reload_is_no_channel_change():
    """The state an undo / redo loads is not keyed (that would push a step and cut off the redo history)."""
    with _AutoKey():
        name = _keyed_cube()
        bpy.data.objects[name].location.x = 2.0
        bpy.ops.ed.undo_push(message="Move")        # a move whose key was taken back
        auto_key._on_undo_redo()
        bpy.data.objects[name].location.x = 2.5
        bpy.context.view_layer.update()
        assert name not in auto_key._pending
        auto_key._reload_seen()
        bpy.data.objects[name].location.x = 3.0
        bpy.context.view_layer.update()
        assert name in auto_key._pending            # the next real change is keyed again


def test_a_value_changed_with_auto_key_off_is_not_keyed_later():
    """Maya keys only values that change while Auto Key is on: a selection change after turning it on keys
    nothing, the next real change is keyed."""
    name = _keyed_cube()
    ob = bpy.data.objects[name]
    ob.location.x = 2.0                              # changed with Auto Key off: no key
    bpy.context.view_layer.update()
    with _AutoKey():
        ob.select_set(not ob.select_get())           # a plain selection change
        bpy.context.view_layer.update()
        auto_key._pending[name] = bpy.context.scene.frame_current
        _flush()
        assert _state(name) == (2.0, 1), _state(name)
        _move(name, 3.0)
        assert _state(name) == (3.0, 2), _state(name)
