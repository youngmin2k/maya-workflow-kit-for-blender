"""Issues #174, #177: a held Space keeps the hotbox up whatever the input path sends while the key is down
(release + press repeat pairs, a moment of "up" from the OS key state); a quick tap still toggles the pane; a click on a
hotbox menu name opens the menu without running a row; the Emulate 3 Button Mouse hint (Alt+LMB tumble can't work)."""

from importlib import import_module

import bpy

import kit

engine = import_module(kit.MODULE + ".marking.engine")
prefs_mod = import_module(kit.MODULE + ".preferences")
welcome = import_module(kit.MODULE + ".welcome")


def _run(events, until=3.0, step=0.05):
    """Feed (time, 'P' / 'R') key events and ticks with the key state (down unless released) -> (end, tap)."""
    hold = engine.HoldKey(0.0)
    down = True
    evs = sorted(events)
    t = 0.0
    while t <= until:
        while evs and evs[0][0] <= t:
            _te, kind = evs.pop(0)
            if kind == 'P':
                hold.press(_te)
                down = True
            else:
                hold.release(_te)
                down = False
        if hold.tick(t, down):
            return hold.end, engine.is_tap(0.0, hold.end, False)
        t = round(t + step, 6)
    return None, False


def test_tap_toggles_and_hold_does_not():
    end, tap = _run([(0.2, 'R')])
    assert abs(end - 0.2) < 1e-9 and tap, (end, tap)           # quick tap = pane toggle (Maya noClickDelay 0.4)
    end, tap = _run([(1.0, 'R')])
    assert abs(end - 1.0) < 1e-9 and not tap                   # a hold, released: no toggle


def test_repeat_pairs_keep_the_hold():
    """X11 / remote input: auto-repeat as RELEASE + PRESS every 33 ms for 2 s, then the real release."""
    events = []
    t = 0.5
    while t < 2.5:
        events += [(t, 'R'), (t + 0.001, 'P')]
        t += 0.033
    events.append((2.6, 'R'))
    end, tap = _run(events, until=4.0)
    assert end is not None and abs(end - 2.6) < 1e-6 and not tap, (end, tap)


def test_two_real_taps_are_two_taps():
    """A release followed by a press later than the grace is a new press (a second tap starts a new hotbox)."""
    hold = engine.HoldKey(0.0)
    hold.release(0.1)
    hold.press(0.1 + engine.RELEASE_GRACE + 0.05)
    assert hold.tick(0.1 + engine.RELEASE_GRACE + 0.06, True) is True and abs(hold.end - 0.1) < 1e-9


def test_key_state_fallback_needs_a_lasting_up():
    hold = engine.HoldKey(0.0)
    assert not hold.tick(1.0, False)                 # one "up" reading is not a release
    assert not hold.tick(1.0 + engine.UP_TIME / 2, False)
    assert not hold.tick(1.1, True)                  # down again: still held
    assert not hold.tick(2.0, False)
    assert hold.tick(2.0 + engine.UP_TIME + 0.01, False) and abs(hold.end - 2.0) < 1e-9
    hold = engine.HoldKey(0.0)
    assert not hold.tick(5.0, None)                  # unknown key state (not Windows): no fallback


def test_restart_guard_and_menu_drag():
    assert engine.restart_too_soon(1.0, 1.0 + engine.RELEASE_GRACE / 2)
    assert not engine.restart_too_soon(1.0, 1.0 + engine.RELEASE_GRACE * 2)
    assert not engine.restart_too_soon(None, 5.0)
    assert not engine.menu_drag((10, 10), (12, 11))
    assert engine.menu_drag((10, 10), (10, 15)) and not engine.menu_drag((10, 10), (10, 15), scale=2.0)


def test_emulate_three_button_hint():
    inputs = bpy.context.preferences.inputs
    old = inputs.use_mouse_emulate_3_button
    try:
        inputs.use_mouse_emulate_3_button = False
        assert prefs_mod.emulate_hint() is None
        inputs.use_mouse_emulate_3_button = True
        assert "Alt+LMB tumble" in prefs_mod.emulate_hint()
    finally:
        inputs.use_mouse_emulate_3_button = old


def test_welcome_comes_back_once_if_not_confirmed():
    assert welcome.WELCOME_SHOWS == 2
    p = prefs_mod.get()
    assert hasattr(p, "welcome_shown")
