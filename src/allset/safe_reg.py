# SPDX-License-Identifier: GPL-3.0-or-later
"""Register / unregister a list of sub-modules all or nothing (#198 #199).

A module whose ``register()`` raised used to leave every module before it registered (the Maya menu bar, the
Status Line, the menus) while the modules after it (the tear-off operator, the keymap ...) were missing, and the
switch back to Blender then unregistered nothing. ``register_all`` rolls back what it registered and re-raises;
``unregister_all`` takes back exactly what was recorded, carrying on past a module that raises.
"""

import traceback

PREFIX = "Maya Workflow Kit:"


def _name(mod):
    return getattr(mod, "__name__", repr(mod)).rsplit(".", 1)[-1]


def register_all(modules, done):
    """Register ``modules`` in order, appending each one to ``done`` once it registered. On an exception the failing
    module is unregistered as far as it goes, then ``done`` in reverse, and the exception is raised again."""
    for mod in modules:
        try:
            mod.register()
        except Exception as ex:
            print(PREFIX, f"registering '{_name(mod)}' failed; taking back what was registered")
            if not getattr(ex, "_allset_printed", False):    # a nested list printed it already
                traceback.print_exc()
                try:
                    ex._allset_printed = True
                except AttributeError:
                    pass
            try:
                mod.unregister()          # whatever part of it did register
            except Exception:
                pass
            unregister_all(done, quiet=True)
            raise
        done.append(mod)


def unregister_all(done, quiet=False):
    """Unregister the modules in ``done`` in reverse and empty it. A module that raises is reported (unless
    ``quiet``) and the rest still go. Returns the names of the modules that raised."""
    failed = []
    while done:
        mod = done.pop()
        try:
            mod.unregister()
        except Exception:
            failed.append(_name(mod))
            if not quiet:
                print(PREFIX, f"unregistering '{_name(mod)}' failed; the others still go")
                traceback.print_exc()
    return failed


def reregister_panel(cls, kids, poll, raw):
    """Unregister panel ``cls`` (another add-on's or Blender's) with its child panels ``kids``, give it ``poll``
    (None = no own poll) and register them again. If Blender refuses at any point the panel gets its original poll
    ``raw`` back, whatever was unregistered is registered again where Blender lets it, and False is returned: one
    foreign panel must not stop the kit."""
    try:
        for kid in reversed(kids):
            if kid.is_registered:
                _unregister_class(kid)
        if cls.is_registered:
            _unregister_class(cls)
        _set_poll(cls, poll)
        _register_class(cls)
        for kid in kids:
            _register_class(kid)
        return True
    except Exception as ex:
        print(PREFIX, f"left panel '{getattr(cls, '__name__', cls)}' as it was ({ex})")
        _set_poll(cls, raw)
        for c in (cls, *kids):
            if not c.is_registered:
                try:
                    _register_class(c)
                except Exception:
                    pass
        return False


def _set_poll(cls, poll):
    if poll is not None:
        cls.poll = poll
    elif "poll" in cls.__dict__:
        del cls.poll


def _register_class(cls):
    import bpy
    bpy.utils.register_class(cls)


def _unregister_class(cls):
    import bpy
    bpy.utils.unregister_class(cls)
