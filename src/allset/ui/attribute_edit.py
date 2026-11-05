# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared numeric drag rules. UI clients own picking and backends own their undo transaction."""

import math
from dataclasses import dataclass


def nearest_integer(value):
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def delta(distance, step, speed=1.0, ctrl=False, shift=False, hyperbolic=False):
    distance = float(distance)
    if hyperbolic:
        distance *= abs(distance) / 50.0
    return distance * step * speed * (0.1 if ctrl else 1.0) * (10.0 if shift else 1.0)


@dataclass(frozen=True)
class Field:
    kind: str = 'NONE'
    step: float = 0.01
    minimum: float | None = None
    maximum: float | None = None
    default: float = 0.0

    def limit(self, value):
        if not math.isfinite(value):
            raise ValueError('Attribute value must be finite')
        if self.minimum is not None:
            value = max(self.minimum, value)
        if self.maximum is not None:
            value = min(self.maximum, value)
        if self.kind == 'INT':
            return nearest_integer(value)
        return float(value)


class Drag:
    """Accumulate small moves and rebase sensitivity changes without jumping at a clamp."""

    def __init__(self, value, field):
        self.field = field
        self.value = self.continuous = self.origin = float(value)
        self.distance = 0.0
        self.mode = None

    def move(self, distance, speed=1.0, ctrl=False, shift=False, hyperbolic=False):
        mode = speed, ctrl, shift, hyperbolic
        if mode != self.mode:
            self.origin = self.value
            self.distance = 0.0
            self.mode = mode
        self.distance += distance
        self.continuous = self.origin + delta(self.distance, self.field.step, *mode)
        limited = self.field.limit(self.continuous)
        # A bound must not accumulate travel which the user has to undo before reversing.
        bounded = ((self.field.minimum is not None and self.continuous < self.field.minimum)
                   or (self.field.maximum is not None and self.continuous > self.field.maximum))
        if bounded:
            self.origin = limited
            self.distance = 0.0
        self.value = limited
        return limited


_owners = {}


def claim(context, owner):
    """One attribute edit per window; a second editor cannot overwrite a live preview."""
    key = context.window.as_pointer()
    if key in _owners:
        return False
    _owners[key] = owner
    return True


def release(window_pointer, owner):
    if _owners.get(window_pointer) is owner:
        _owners.pop(window_pointer, None)


def busy(context):
    return context.window is not None and context.window.as_pointer() in _owners


def clear():
    _owners.clear()
