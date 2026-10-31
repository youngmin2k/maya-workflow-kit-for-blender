# SPDX-License-Identifier: GPL-3.0-or-later
"""Ask the OS whether a key is physically held.

Fallback for hold modals whose RELEASE event was eaten by another modal
(e.g. the transform modal while dragging).

Windows only: a read-only ``user32.GetAsyncKeyState`` query through ctypes (no hook,
no other OS call). Elsewhere, or if the call fails, ``is_down`` returns None
("unknown"); every caller acts only on an explicit False, so the hold then ends on
Blender's RELEASE event alone.
"""

import sys

# Blender event type -> Windows virtual-key code.
_VK = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
_VK.update({
    "INSERT": 0x2D, "DEL": 0x2E, "HOME": 0x24, "END": 0x23,
    "PAGE_UP": 0x21, "PAGE_DOWN": 0x22,
    "LEFT_ARROW": 0x25, "UP_ARROW": 0x26, "RIGHT_ARROW": 0x27, "DOWN_ARROW": 0x28,
    "SPACE": 0x20, "TAB": 0x09, "ACCENT_GRAVE": 0xC0, "BACK_SLASH": 0xDC,
    "LEFTMOUSE": 0x01, "RIGHTMOUSE": 0x02, "MIDDLEMOUSE": 0x04,
    "LEFT_SHIFT": 0xA0, "RIGHT_SHIFT": 0xA1, "LEFT_CTRL": 0xA2, "RIGHT_CTRL": 0xA3,
    "LEFT_ALT": 0xA4, "RIGHT_ALT": 0xA5,
})

_user32 = None
if sys.platform == "win32":
    try:
        import ctypes
        _user32 = ctypes.windll.user32
    except (ImportError, AttributeError, OSError):
        _user32 = None


def vk_code(event_type):
    return _VK.get(event_type)


def is_down(event_type):
    """True/False if the OS can tell, None if unknown (other OS or key)."""
    vk = _VK.get(event_type)
    if _user32 is None or vk is None:
        return None
    try:
        return bool(_user32.GetAsyncKeyState(vk) & 0x8000)
    except (OSError, AttributeError, ValueError):
        return None
