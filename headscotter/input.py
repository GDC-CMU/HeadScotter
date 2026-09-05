"""Input intent resolution: two joysticks + keyboard -> game actions.

No :mod:`pygame` import: this module resolves plain floats, key name
strings, and per-device button sets into game-level intent, so it is
fully unit-testable without a display or real hardware. The actual
pygame event/joystick polling lives in :mod:`headscotter.game`, which
builds a :class:`RawInput` each frame and hands it to the functions here.

Two identical joysticks are wired to the cabinet: device index 0 drives
player 1, device index 1 drives player 2 (see ``buttons_by_device``/
``axes``, both ordered by device index). In 1-player mode either stick
may drive the human -- see the ``*_single_player`` resolvers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import FrozenSet, Optional, Tuple

from . import config


class MenuDirection(Enum):
    UP = auto()
    DOWN = auto()


@dataclass(frozen=True)
class RawInput:
    """One frame's worth of raw hardware state, already read out of pygame."""

    axes: Tuple[Tuple[float, float], ...] = field(default_factory=tuple)
    pressed_keys: FrozenSet[str] = frozenset()
    #: Merged across every connected device -- used for menu confirm/back,
    #: which deliberately do not care which stick was used.
    pressed_buttons: FrozenSet[int] = frozenset()
    #: Per-device button sets, ordered by device index -- used for
    #: per-player match controls, where the device matters.
    buttons_by_device: Tuple[FrozenSet[int], ...] = field(default_factory=tuple)

    def device_axis(self, index: int) -> Tuple[float, float]:
        if 0 <= index < len(self.axes):
            return self.axes[index]
        return (0.0, 0.0)

    def device_buttons(self, index: int) -> FrozenSet[int]:
        if 0 <= index < len(self.buttons_by_device):
            return self.buttons_by_device[index]
        return frozenset()


# --- Keyboard fallbacks (for windowed development without two sticks) -----------
# Two disjoint key sets, one per player, so both can be exercised at once on
# a single keyboard; neither overlaps the menu's up/down keys.
P1_MOVE_KEYS = {"a": -1, "d": 1}
P2_MOVE_KEYS = {"left": -1, "right": 1}
P1_JUMP_KEYS = frozenset({"w"})
P1_KICK_KEYS = frozenset({"s"})
P2_JUMP_KEYS = frozenset({"up"})
P2_KICK_KEYS = frozenset({"down"})

MENU_UP_KEYS = frozenset({"up", "w"})
MENU_DOWN_KEYS = frozenset({"down", "s"})
CONFIRM_KEYS = frozenset({"return", "enter", "space"})
# "Go back one level" -- Esc/Backspace on the keyboard, or button P1 (5)/B (0)
# on the cabinet. Equivalent aliases of one action; see game.maybe_go_back().
BACK_KEYS = frozenset({"escape", "backspace"})


def _axis_move(x: float, deadzone: float = None) -> int:
    dz = config.JOYSTICK_DEADZONE if deadzone is None else deadzone
    if x >= dz:
        return 1
    if x <= -dz:
        return -1
    return 0


def _keys_move(pressed_keys: FrozenSet[str], keymap) -> int:
    for key, value in keymap.items():
        if key in pressed_keys:
            return value
    return 0


def resolve_move_p1(raw: RawInput) -> int:
    """2-player mode: player 1 is strictly device 0's stick, or the P1
    keyboard fallback."""
    x, _ = raw.device_axis(config.PLAYER_1_DEVICE_INDEX)
    move = _axis_move(x)
    if move == 0:
        move = _keys_move(raw.pressed_keys, P1_MOVE_KEYS)
    return move


def resolve_move_p2(raw: RawInput) -> int:
    """2-player mode: player 2 is strictly device 1's stick, or the P2
    keyboard fallback."""
    x, _ = raw.device_axis(config.PLAYER_2_DEVICE_INDEX)
    move = _axis_move(x)
    if move == 0:
        move = _keys_move(raw.pressed_keys, P2_MOVE_KEYS)
    return move


def resolve_move_single_player(raw: RawInput) -> int:
    """1-player mode: either connected stick, or either keyboard mapping,
    can drive the one human player."""
    for x, _ in raw.axes:
        move = _axis_move(x)
        if move != 0:
            return move
    move = _keys_move(raw.pressed_keys, P1_MOVE_KEYS)
    if move == 0:
        move = _keys_move(raw.pressed_keys, P2_MOVE_KEYS)
    return move


def wants_jump_p1(raw: RawInput) -> bool:
    return config.BUTTON_JUMP in raw.device_buttons(config.PLAYER_1_DEVICE_INDEX) or bool(
        raw.pressed_keys & P1_JUMP_KEYS
    )


def wants_kick_p1(raw: RawInput) -> bool:
    return config.BUTTON_KICK in raw.device_buttons(config.PLAYER_1_DEVICE_INDEX) or bool(
        raw.pressed_keys & P1_KICK_KEYS
    )


def wants_jump_p2(raw: RawInput) -> bool:
    return config.BUTTON_JUMP in raw.device_buttons(config.PLAYER_2_DEVICE_INDEX) or bool(
        raw.pressed_keys & P2_JUMP_KEYS
    )


def wants_kick_p2(raw: RawInput) -> bool:
    return config.BUTTON_KICK in raw.device_buttons(config.PLAYER_2_DEVICE_INDEX) or bool(
        raw.pressed_keys & P2_KICK_KEYS
    )


def wants_jump_single(raw: RawInput) -> bool:
    if any(config.BUTTON_JUMP in buttons for buttons in raw.buttons_by_device):
        return True
    return bool(raw.pressed_keys & (P1_JUMP_KEYS | P2_JUMP_KEYS))


def wants_kick_single(raw: RawInput) -> bool:
    if any(config.BUTTON_KICK in buttons for buttons in raw.buttons_by_device):
        return True
    return bool(raw.pressed_keys & (P1_KICK_KEYS | P2_KICK_KEYS))


def resolve_menu_direction(raw: RawInput) -> Optional[MenuDirection]:
    """Either connected stick's vertical axis, or the keyboard, may
    navigate the menu list."""
    dz = config.JOYSTICK_DEADZONE
    for _, y in raw.axes:
        if y <= -dz:
            return MenuDirection.UP
        if y >= dz:
            return MenuDirection.DOWN
    if raw.pressed_keys & MENU_UP_KEYS:
        return MenuDirection.UP
    if raw.pressed_keys & MENU_DOWN_KEYS:
        return MenuDirection.DOWN
    return None


def wants_confirm(raw: RawInput) -> bool:
    if raw.pressed_keys & CONFIRM_KEYS:
        return True
    return bool(raw.pressed_buttons & set(config.CONFIRM_BUTTONS))


def wants_go_back(raw: RawInput) -> bool:
    """The single "go back one level" intent: Esc, Backspace, button P1
    (5), or button B (0) -- all exactly equivalent everywhere in the
    game. See Game.maybe_go_back() for what "back" resolves to on each
    screen."""
    if raw.pressed_keys & BACK_KEYS:
        return True
    return bool(raw.pressed_buttons & (set(config.EXIT_BUTTONS) | set(config.BACK_BUTTONS)))


def any_genuine_input(raw: RawInput) -> bool:
    """True if a direction, jump, kick, confirm, or back control is
    physically active this frame -- used both to drive the main menu's
    idle timer (config.DEMO_IDLE_SECONDS) and to end the attract-mode
    demo the instant a visitor touches anything. A drifting/noisy stick
    at rest must not count: the axis resolvers already apply the
    configured deadzone, so only a genuine push registers."""
    if resolve_menu_direction(raw) is not None:
        return True
    if wants_confirm(raw) or wants_go_back(raw):
        return True
    if resolve_move_single_player(raw) != 0:
        return True
    if wants_jump_single(raw) or wants_kick_single(raw):
        return True
    return False
