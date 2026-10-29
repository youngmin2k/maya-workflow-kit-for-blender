"""Overlay ownership across save, failed save, editor changes and explicit legacy repair."""
import bpy
from importlib import import_module
import kit
q=import_module(kit.MODULE+'.operators.quad_draw')


def fixture(original=(False,True,.37)):
    q._restore_overlays()
    if bpy.app.timers.is_registered(q._watch):bpy.app.timers.unregister(q._watch)
    q.STATE.update(ob=None,created=None,timer=False)
    if bpy.context.object is not None and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.object.mode_set(mode='EDIT')
    area=next(a for a in bpy.context.window.screen.areas if a.type=='VIEW_3D')
    region=next(r for r in area.regions if r.type=='WINDOW')
    with bpy.context.temp_override(area=area,region=region):
        bpy.ops.wm.tool_set_by_id(name=q.TOOL,space_type='VIEW_3D')
        q._set_overlay_values(area.spaces.active,original)
        q._retopology_on(bpy.context)
    return area,region,area.spaces.active


def test_save_serializes_original_overlay_and_resumes_the_current_display():
    a,r,space=fixture();original=q.STATE['overlays'][space.as_pointer()];runtime=q._overlay_values(space)
    q._overlay_save_pre('unused.blend')
    assert q._overlay_values(space)==original and q._overlay_saving
    with bpy.context.temp_override(area=a,region=r):q.sync_overlays(bpy.context)
    assert q._overlay_values(space)==original,'draw cannot put temporary values back during serialization'
    q._overlay_save_post('unused.blend')
    assert q._overlay_values(space)==runtime and not q._overlay_saving and not q._overlay_save_runtime
    q._restore_overlays();assert q._overlay_values(space)==original


def test_failed_save_handler_restores_the_live_tool_and_is_registered_once():
    a,r,space=fixture();runtime=q._overlay_values(space)
    q.register_handlers()
    assert hasattr(bpy.app.handlers,'save_post_fail'),'supported Blender must deliver failed-save cleanup'
    for name,fn in (('save_pre',q._overlay_save_pre),('save_post',q._overlay_save_post),('save_post_fail',q._overlay_save_post)):
        assert list(getattr(bpy.app.handlers,name)).count(fn)==1
    q._overlay_save_pre('failed.blend')
    for fn in list(bpy.app.handlers.save_post_fail):
        if fn is q._overlay_save_post:fn('failed.blend')
    assert q._overlay_values(space)==runtime and not q._overlay_saving and not q._overlay_save_runtime


def test_a_manually_enabled_native_overlay_and_custom_offset_are_preserved():
    original=(True,False,.73);a,r,space=fixture(original)
    expected=q.STATE['overlays'][space.as_pointer()]
    q._overlay_save_pre();assert q._overlay_values(space)==expected
    q._overlay_save_post();q._restore_overlays()
    assert q._overlay_values(space)==expected and expected[0] and abs(expected[2]-.73)<1e-6


def test_save_without_tool_ownership_leaves_native_settings_untouched():
    a,r,space=fixture();q._restore_overlays();q._set_overlay_values(space,(True,True,1.25))
    before=q._overlay_values(space);q._overlay_save_pre();q._overlay_save_post()
    assert q._overlay_values(space)==before and not q._overlay_save_runtime


def test_an_inactive_editor_space_gets_its_original_values_back():
    a,r,space=fixture();original=q.STATE['overlays'][space.as_pointer()]
    try:
        a.type='TEXT_EDITOR';q._restore_inactive_overlays()
        assert q._overlay_values(space)==original and space.as_pointer() not in q.STATE['overlays']
    finally:a.type='VIEW_3D'


def test_explicit_repair_affects_only_the_requested_view():
    a,r,space=fixture();other=next(area for area in bpy.context.window.screen.areas if area is not a and area.type not in {'TOPBAR','STATUSBAR'})
    kind=other.type
    try:
        other.type='VIEW_3D';untouched=other.spaces.active;q._set_overlay_values(untouched,(True,True,.8));before=q._overlay_values(untouched)
        with bpy.context.temp_override(area=a,region=r):answer=bpy.ops.allset.restore_modeling_display()
        assert answer=={'FINISHED'} and not space.overlay.show_retopology
        q._watch()
        assert not space.overlay.show_retopology and q._overlay_values(untouched)==before
    finally:other.type=kind


def test_file_reset_discards_suspended_values_from_the_previous_file():
    a,r,space=fixture();original=q.STATE['overlays'][space.as_pointer()];q._overlay_save_pre()
    q._file_reset(None)
    assert q._overlay_values(space)==original
    assert not q._overlay_saving and not q._overlay_save_runtime and not q.STATE['overlays']
    q._overlay_save_post();assert q._overlay_values(space)==original


def test_closed_view_snapshots_are_pruned_and_unregister_restores_owned_values():
    a,r,space=fixture();original=q.STATE['overlays'][space.as_pointer()]
    q.STATE['overlays'][0xDEADBEEF]=(False,True,.01);q._restore_inactive_overlays()
    assert 0xDEADBEEF not in q.STATE['overlays']
    try:
        q.unregister_handlers()
        assert q._overlay_values(space)==original and not q.STATE['overlays']
        assert q._overlay_save_pre not in bpy.app.handlers.save_pre
        assert q._overlay_save_post not in bpy.app.handlers.save_post_fail
    finally:q.register_handlers()


def test_explicit_tool_exit_restores_native_shading_before_the_cleanup_timer():
    a,r,space=fixture();original=q.STATE['overlays'][space.as_pointer()]
    with bpy.context.temp_override(area=a,region=r):answer=bpy.ops.allset.quad_draw_exit()
    assert answer=={'FINISHED'} and q._overlay_values(space)==original and not q.STATE['overlays']
