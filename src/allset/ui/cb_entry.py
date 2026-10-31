# SPDX-License-Identifier: GPL-3.0-or-later
"""Channel Box field text: Maya-style display and entry.

Maya shows plain numbers in the current units (cm, degrees) and accepts relative entry
``+=5``, ``-=2``, ``*=2``, ``/=2`` (Maya's Channel Box entry). Values are
shown in the scene's display length unit without the unit name; entry goes through
``bpy.utils.units.to_value`` so ``5`` means 5 display units and ``5 m`` / ``2*3`` work too.
Kinds: ``LENGTH``, ``ROTATION``, ``NONE`` (plain float), ``INT``, ``BOOL``.
"""

import math
import re

import bpy
from bpy.utils import units

# Display length unit -> (metres per unit, unit name to_value understands).
_LENGTH_UNITS = {
    'METERS': (1.0, "m"), 'CENTIMETERS': (0.01, "cm"), 'MILLIMETERS': (0.001, "mm"),
    'KILOMETERS': (1000.0, "km"), 'MICROMETERS': (1e-6, "um"),
    'FEET': (0.3048, "ft"), 'INCHES': (0.0254, "in"), 'MILES': (1609.344, "mi"),
    'THOU': (2.54e-5, "thou"),
}
_RELATIVE = re.compile(r"^\s*([-+*/])=\s*(.+?)\s*$")
_TRUE = {"on", "true", "yes", "1"}
_FALSE = {"off", "false", "no", "0"}


def _length_unit(scene):
    us = scene.unit_settings
    if us.system == 'NONE':
        return None
    unit = us.length_unit
    if unit == 'ADAPTIVE':
        unit = 'METERS' if us.system == 'METRIC' else 'FEET'
    return _LENGTH_UNITS.get(unit, (1.0, "m"))


def _degrees(scene):
    return scene.unit_settings.system_rotation == 'DEGREES'


def to_display(value, kind, scene):
    """Blender value -> the number the Channel Box shows (display units)."""
    if kind == "LENGTH":
        lu = _length_unit(scene)
        return value if lu is None else value * scene.unit_settings.scale_length / lu[0]
    if kind == "ROTATION" and _degrees(scene):
        return math.degrees(value)
    return value


def from_display(number, kind, scene):
    if kind == "LENGTH":
        lu = _length_unit(scene)
        return number if lu is None else number * lu[0] / scene.unit_settings.scale_length
    if kind == "ROTATION" and _degrees(scene):
        return math.radians(number)
    return number


def fmt_number(x):
    """Maya-like: up to 3 decimals, no trailing zeros, no "-0"."""
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def format_value(value, kind, scene):
    if kind == "BOOL":
        return "on" if value else "off"
    if kind == "INT":
        return str(int(value))
    return fmt_number(to_display(value, kind, scene))


def _number(text, kind, scene):
    """A typed amount in display units (``5``, ``5 m``, ``2*3``, ``45``) -> display-unit number."""
    us = scene.unit_settings
    if kind == "LENGTH" and _length_unit(scene) is not None:
        metres = units.to_value(us.system, 'LENGTH', text, str_ref_unit=_length_unit(scene)[1])
        return round(metres / _length_unit(scene)[0], 6)
    if kind == "ROTATION" and _degrees(scene):
        return round(math.degrees(units.to_value('METRIC', 'ROTATION', text)), 6)
    return units.to_value('NONE', 'NONE', text)


def parse_entry(text, old, kind, scene):
    """New Blender value for ``text`` typed over ``old``; ValueError when it can't be read."""
    text = text.strip()
    if not text:
        raise ValueError("empty")
    if kind == "BOOL":
        low = text.lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        m = _RELATIVE.match(text)
        if m is None:
            return bool(units.to_value('NONE', 'NONE', text))
    m = _RELATIVE.match(text)
    if m is None:
        value = from_display(_number(text, kind, scene), kind, scene)
    else:
        op, amount = m.groups()
        if op in "+-":
            delta = from_display(_number(amount, kind, scene), kind, scene)
            value = old + delta if op == "+" else old - delta
        else:
            factor = units.to_value('NONE', 'NONE', amount)
            if op == "/" and factor == 0:
                raise ValueError("division by zero")
            value = old * factor if op == "*" else old / factor
    if kind == "INT":
        return int(round(value))
    if kind == "BOOL":
        return bool(value)
    return value


def kind_of_rna(prop):
    """Entry kind of a scalar RNA property (None: not drawn as text)."""
    if getattr(prop, "array_length", 0):
        return None
    if prop.type == 'BOOLEAN':
        return "BOOL"
    if prop.type == 'INT':
        return "INT"
    if prop.type == 'FLOAT':
        if prop.unit == 'LENGTH':
            return "LENGTH"
        if prop.unit == 'ROTATION':
            return "ROTATION"
        return "NONE"
    return None


def kind_of_value(value):
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT"
    if isinstance(value, float):
        return "NONE"
    return None


def scene():
    return bpy.context.scene
