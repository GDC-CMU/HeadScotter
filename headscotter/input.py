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
    # Genuine down edges collected by the event pump. Tuples retain multiple
    # taps, even down/up/down/up within one render frame. Held state alone
    # cannot represent those. Device ordering matches buttons_by_device.
    key_downs: Tuple[str, ...] = ()
    button_downs_by_device: Tuple[Tuple[int, ...], ...] = ()

    @property
    def active_keys(self) -> FrozenSet[str]:
        return self.pressed_keys | frozenset(self.key_downs)

    @property
    def active_buttons(self) -> FrozenSet[int]:
        return self.pressed_buttons.union(*self.buttons_by_device, *self.button_downs_by_device)

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
# a single keyboard.
P1_MOVE_KEYS = {"a": -1, "d": 1}
P2_MOVE_KEYS = {"left": -1, "right": 1}
P1_JUMP_KEYS = frozenset({"w"})
# "x" is the primary keyboard kick key -- it matches the on-screen legend
# ("X: KICK", the arcade button label) literally, which the *arcade*
# cabinet's stick already did (BUTTON_KICK = BUTTON_X in config.py) but a
# keyboard tester previously had no literal "x" key bound at all, only
# "s". "s" is kept as an alternate so nothing regresses for anyone used
# to it. "s" also doubles as MENU_DOWN_KEYS below; this is deliberately
# safe, not an oversight -- see the note there.
P1_KICK_KEYS = frozenset({"x", "s"})
P2_JUMP_KEYS = frozenset({"up"})
# "down" mirrors P1's "s" (both sit directly under that hand's jump key);
# "/" is P2's literal "x"-equivalent -- an easy-to-reach action key next
# to the arrow cluster P2's movement/jump already use.
P2_KICK_KEYS = frozenset({"down", "/"})
P1_POWER_KEYS = frozenset({"c"})
P2_POWER_KEYS = frozenset({"right shift"})

MENU_UP_KEYS = frozenset({"up", "w"})
# "s" here and in P1_KICK_KEYS above is a deliberate, safe overlap, not a
# bug to remove: menu navigation only ever resolves while GameState is
# ATTRACT (see Game._update_menu()), and kicking only ever resolves
# during MATCH/DEMO (see Game._step_gameplay()) -- those states are
# mutually exclusive, so the same physical key can never trigger both
# interpretations on the same frame.
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


def wants_confirm(raw: RawInput, paused: bool = False) -> bool:
    if raw.active_keys & CONFIRM_KEYS:
        return True
    buttons = {config.BUTTON_START} if paused else set(config.CONFIRM_BUTTONS)
    return bool(raw.active_buttons & buttons)


def wants_go_back(raw: RawInput) -> bool:
    """The single "go back one level" intent: Esc, Backspace, button P1
    (5), or button B (0) -- all exactly equivalent everywhere in the
    game. See Game.maybe_go_back() for what "back" resolves to on each
    screen."""
    if raw.active_keys & BACK_KEYS:
        return True
    return bool(raw.active_buttons & (set(config.EXIT_BUTTONS) | set(config.BACK_BUTTONS)))


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
    return bool(raw.active_keys or raw.active_buttons)


@dataclass(frozen=True)
class PlayerActions:
    normal_kicks: int = 0
    jump: bool = False
    power_held: bool = False
    power_tap: bool = False
    power_released: bool = False


def _held_sources(raw: RawInput) -> set:
    return {(-1, key) for key in raw.pressed_keys} | {
        (index, button) for index, buttons in enumerate(raw.buttons_by_device) for button in buttons
    }


def _down_sources(raw: RawInput) -> list:
    return [(-1, key) for key in raw.key_downs] + [
        (index, button) for index, buttons in enumerate(raw.button_downs_by_device) for button in buttons
    ]


class ActionTracker:
    """Per-source action edges and release-to-arm guards.

    A held X on one device never masks a fresh X on another device (or a
    keyboard alias). Power charges belong to the source that began them;
    another held source cannot conceal its release or inherit its charge.
    """

    def __init__(self):
        self.held = set()
        self.blocked = set()
        self.power_owners = [None, None]

    def suspend(self, raw: RawInput) -> None:
        self.held = _held_sources(raw)
        self.blocked = self.held | set(_down_sources(raw))
        self.power_owners = [None, None]

    def sample(self, raw: RawInput, single_player: bool = False) -> Tuple[PlayerActions, PlayerActions]:
        held = _held_sources(raw)
        downs = _down_sources(raw)
        # Hardware only emits genuine down edges (repeat is filtered). A
        # previously blocked source with a new edge has physically released,
        # even if up/down were both polled in this frame.
        self.blocked.difference_update(downs)
        # Event edges are authoritative, but plain RawInput snapshots remain
        # useful to tests/tools. Don't double-count a down also seen as held.
        presses = downs + sorted(held - self.held - set(downs))
        presses = [source for source in presses if source not in self.blocked]
        available = held - self.blocked
        self.blocked.intersection_update(held)
        self.held = held

        results = []
        for index in range(2):
            if single_player and index == 1:
                results.append(PlayerActions())  # the right side is CPU-owned
                continue
            def sources(button, keys1, keys2):
                keys = (keys1 | keys2) if single_player and index == 0 else (keys1 if index == 0 else keys2)
                devices = range(max(len(raw.buttons_by_device), len(raw.button_downs_by_device))) if (
                    single_player and index == 0
                ) else (index,)
                return {(-1, key) for key in keys} | {(device, button) for device in devices}

            kicks = sources(config.BUTTON_KICK, P1_KICK_KEYS, P2_KICK_KEYS)
            jumps = sources(config.BUTTON_JUMP, P1_JUMP_KEYS, P2_JUMP_KEYS)
            powers = sources(config.BUTTON_POWER, P1_POWER_KEYS, P2_POWER_KEYS)
            owner = self.power_owners[index]
            tap = False
            released = owner is not None and (owner not in available or owner in downs)
            if owner is not None and owner not in available:
                # Release the original charge this frame, even if a different
                # device is now holding A. A new source may charge next frame.
                owner = None
            elif owner is None:
                candidates = sorted(available & powers)
                owner = candidates[0] if candidates else None
                tap = owner is None and any(source in powers for source in presses)
            self.power_owners[index] = owner
            results.append(PlayerActions(
                normal_kicks=sum(source in kicks for source in presses),
                jump=bool((available | set(presses)) & jumps),
                power_held=owner is not None,
                power_tap=tap,
                power_released=released,
            ))
        return tuple(results)
