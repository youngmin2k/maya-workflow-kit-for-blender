# SPDX-License-Identifier: GPL-3.0-or-later
"""Tools for editing keyconfig *data* before it becomes a KeyConfig.

The data shape is what ``bl_keymap_utils.io.keyconfig_init_from_data``
consumes and what ``industry_compatible_data.generate_keymaps`` returns
(``$S\\modules\\bl_keymap_utils\\io.py:249-296``)::

    [(km_name, {"space_type", "region_type", ...}, {"items": [
        (idname, {"type", "value", "shift", "ctrl", "alt", ...}, {"properties": [(k, v)]} | None),
    ]}), ...]

Pure Python (no bpy) so the mapping-doc tool and tests can reuse it.
"""

MODS = ("shift", "ctrl", "alt", "oskey")

# Strict on the Blender the kit is checked on (5.2, the main target): a patch that finds
# nothing raises, which catches Industry Compatible drift. On other versions (5.0 / 5.1)
# the missing items are recorded in ``DRIFT`` instead, so the keymap still builds; keymap/__init__.py sets STRICT
# from bpy.app.version.
STRICT = True
DRIFT = []


def event_key(ev):
    """Normalized event identity used for matching and conflict checks."""
    if ev.get("any"):
        mods = ("any",)
    else:
        # True/1 = held, -1 = KM_ANY, missing/False/0 = not held.
        mods = tuple(int(ev.get(m) or 0) for m in MODS)
    return (ev["type"], ev.get("value", "PRESS"), mods, ev.get("key_modifier", "NONE"),
            ev.get("direction", "ANY"))


def make_event(type, value="PRESS", shift=False, ctrl=False, alt=False, oskey=False, **extra):
    ev = {"type": type, "value": value}
    for name, on in (("shift", shift), ("ctrl", ctrl), ("alt", alt), ("oskey", oskey)):
        if on:
            ev[name] = True
    ev.update(extra)
    return ev


def props_dict(item_props):
    if not item_props:
        return {}
    return dict(item_props.get("properties", ()))


def make_props(d):
    return {"properties": list(d.items())} if d else None


class KeyconfigData:
    """Mutable wrapper with lookup by keymap name."""

    def __init__(self, data):
        self.data = data
        self._by_name = {km[0]: km for km in data}

    def keymap(self, name):
        return self._by_name[name]

    def items(self, km_name):
        if km_name not in self._by_name and not STRICT:
            DRIFT.append(f"{km_name}: keymap missing")
            return []
        return self._by_name[km_name][2]["items"]

    def ensure(self, name, params, items=()):
        """Add a keymap the source data doesn't have (e.g. IC has no "Time Scrub": Blender then uses its default one)."""
        if name not in self._by_name:
            km = (name, dict(params), {"items": list(items)})
            self.data.append(km)
            self._by_name[name] = km
        return self._by_name[name]

    def keymap_names(self):
        return list(self._by_name)

    # -- queries ---------------------------------------------------------
    def find(self, km_name, idname=None, **ev):
        """Items in ``km_name`` matching idname and the given event fields.

        Event fields compare with defaults filled in (missing modifier = False).
        """
        want = make_event(**ev) if "type" in ev else None
        out = []
        for item in self.items(km_name):
            if idname is not None and item[0] != idname:
                continue
            if want is not None and event_key(item[1]) != event_key(want):
                continue
            out.append(item)
        return out

    # -- edits -----------------------------------------------------------
    def remove(self, km_name, idname=None, optional=False, **ev):
        """Remove matching items. Raises if nothing matched (catches IC drift); ``optional``: an item only some
        Blender versions have (nothing matched = nothing to do)."""
        found = self.find(km_name, idname, **ev)
        if not found and optional:
            return []
        if not found:
            if not STRICT:
                DRIFT.append(f"{km_name}: no item {idname} {ev}")
                return []
            raise LookupError(f"{km_name}: no item {idname} {ev}")
        items = self.items(km_name)
        items[:] = [it for it in items if not any(it is f for f in found)]
        return found

    def add(self, km_name, idname, event, props=None, first=False):
        item = (idname, event, make_props(props or {}))
        items = self.items(km_name)
        if first:
            items.insert(0, item)  # wins over later items with the same event
        else:
            items.append(item)
        return item

    def rewrite_modifier_set(self, idname, value, variants, keep_props=(), type="LEFTMOUSE"):
        """Replace the no-Alt modifier family of an operator in every keymap.

        For each keymap that has ``idname`` on ``type``/``value`` without Alt:
        remove those items and add one item per ``variants`` entry
        ``((shift, ctrl), props)``. Props listed in ``keep_props`` are copied
        from the original unmodified item (e.g. ``tweak``). Returns the list of
        keymap names touched.
        """
        touched = []
        for km_name in self.keymap_names():
            items = self.items(km_name)
            family = [it for it in items
                      if it[0] == idname and it[1]["type"] == type
                      and it[1].get("value") == value and not it[1].get("alt")
                      and not it[1].get("oskey") and not it[1].get("any")]
            if not family:
                continue
            base = next((it for it in family
                         if not it[1].get("shift") and not it[1].get("ctrl")), family[0])
            base_props = props_dict(base[2])
            kept = {k: base_props[k] for k in keep_props if k in base_props}
            # Insert at the position of the first removed item to keep order stable.
            pos = min(i for i, it in enumerate(items) if any(it is f for f in family))
            items[:] = [it for it in items if not any(it is f for f in family)]
            new = []
            for (shift, ctrl), props in variants:
                ev = dict(base[1])
                for m in ("shift", "ctrl"):
                    ev.pop(m, None)
                if shift:
                    ev["shift"] = True
                if ctrl:
                    ev["ctrl"] = True
                new.append((idname, ev, make_props({**kept, **props})))
            items[pos:pos] = new
            touched.append(km_name)
        return touched


def conflicts(km_items):
    """Pairs of items in one keymap with the same event (both active)."""
    seen = {}
    out = []
    for item in km_items:
        if item[2] and item[2].get("active") is False:
            continue
        k = event_key(item[1])
        if k in seen:
            out.append((seen[k], item))
        else:
            seen[k] = item
    return out


def conflict_signature(km_name, pair):
    """Stable, comparable description of a conflict pair."""
    a, b = pair
    return (km_name, event_key(a[1]), a[0], b[0])
