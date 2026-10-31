# SPDX-License-Identifier: GPL-3.0-or-later
"""Hide Blender's 3D View "Tool" panels where a Properties Tool tab hosts a Maya panel.


A Properties editor on its Tool tab draws the 3D View "Tool"-category panels. The kit's Maya dock areas
(``ui/maya_dock.py``: Channel Box / Layer Editor, Attribute Editor, Modeling Toolkit, torn-off menus) and the Tool
Settings dock (``ui/tool_dock.py``) are such editors, so Blender's panels that were registered when the kit was
enabled are hidden there by wrapping their ``poll`` (only in a Properties WINDOW region; earlier also in the
3D View sidebar, which then hosted the dock). Blender stores a panel's poll callback when the class is registered
and only calls Python if the class had a ``poll`` then, so each panel is unregistered, given the
wrapper and registered again (children first out, parents first in; all of them, so their order
stays); ``unregister`` does the same with the original poll.
Child panels (``bl_parent_id``) hide with their parent.
"""

import bpy

_wrapped = []    # (cls, cls.__dict__ poll before or None, child panels re-registered or None)


def _hidden(context):
    region = context.region
    if region is None or region.type != 'WINDOW':
        return False
    # A Maya panel's own dock area (ui/maya_dock.py) shows only that panel.
    from . import maya_dock
    if maya_dock.area_role(context) is not None:
        return True
    from . import hypershade         # a Hypershade pane shows only its own panel
    if hypershade.context_pane(context) is not None:
        return True
    from . import reference_editor   # the Reference Editor window shows only its own panel
    if reference_editor.context_pane(context):
        return True
    from . import marked_window      # Component / Shape / Connection Editor windows, same
    if marked_window.context_kind(context) is not None:
        return True
    # The Tool Settings dock (a Properties Tool tab): Maya sections replace Blender's tool panels
    # for Move / Rotate / Scale.
    from . import tool_settings
    return tool_settings.hides_blender_panels(context)


def _subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _subclasses(sub)


def _idname(cls):
    return getattr(cls, "bl_idname", "") or cls.__name__


def sidebar_panels():
    """Registered top-level 3D View sidebar panels that are not the kit's, in registration order."""
    seen = set()
    out = []
    for cls in _subclasses(bpy.types.Panel):
        if cls in seen or cls.__name__.startswith("ALLSET_"):
            continue
        seen.add(cls)
        if (getattr(cls, "bl_space_type", None) == 'VIEW_3D' and getattr(cls, "bl_region_type", None) == 'UI'
                and not getattr(cls, "bl_parent_id", "") and cls.is_registered):
            out.append(cls)
    return out


def _children(parent, panels):
    """Registered descendants of ``parent`` (depth first, parents before children)."""
    pid = _idname(parent)
    for cls in panels:
        if getattr(cls, "bl_parent_id", "") == pid and cls.is_registered:
            yield cls
            yield from _children(cls, panels)


def _make_poll(original):
    def poll(cls, context):
        if _hidden(context):
            return False
        return original(context) if original is not None else True
    return classmethod(poll)


def register():
    everything = [c for c in _subclasses(bpy.types.Panel) if getattr(c, "bl_space_type", None) == 'VIEW_3D']
    # Every panel is re-registered (not only those without a poll) so the panels keep their order.
    for cls in sidebar_panels():
        raw = cls.__dict__.get("poll")
        kids = list(_children(cls, everything))
        # A panel Blender won't re-register (another add-on's) stays as it was instead of stopping the kit
        if _reregister(cls, kids, _make_poll(getattr(cls, "poll", None)), raw):
            _wrapped.append((cls, raw, kids))


def _reregister(cls, kids, poll, raw=None):
    from .. import safe_reg
    return safe_reg.reregister_panel(cls, kids, poll, raw)


def unregister():
    for cls, raw, kids in _wrapped:   # forward: the original order again
        _reregister(cls, kids, raw, raw)   # never raises: one foreign panel can't stop the rest
    _wrapped.clear()
