"""Sound effects: kick, power shot, ball bounce, header, goal, whistle,
and menu move/select.

Every effect is a small committed ``.wav`` loaded through this module's
single loader, mirroring :mod:`headscotter.assets`'s contract for art --
see ``assets/README.md``. Nothing else in the codebase should ever touch
:mod:`pygame.mixer` directly; that table is the contract with whoever
supplies real sound.

Audio is entirely optional and must never be able to break the game:

- :func:`init` attempts to bring up ``pygame.mixer``; if that fails for
  an expected device/driver error (no audio device, a headless CI box)
  it prints one warning to stderr and leaves audio disabled -- the
  cabinet must never fail to boot a game because of audio.
- :func:`play` is a no-op whenever audio isn't enabled, the name is
  unknown, or the individual sound fails to load/play.
- :func:`init` is only ever called from :meth:`headscotter.game.Game.
  init_display` (the real, pygame-backed startup path used by
  ``main.py``). Headless tests and the build-time preview/placeholder
  generator tools never call it, so audio stays off there by
  construction -- keeping both fully deterministic without any
  test-specific plumbing.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Set

import pygame

ASSETS_ROOT = Path(__file__).resolve().parent.parent / "assets"

# name -> relative path under assets/
SOUND_SPECS: Dict[str, str] = {
    "kick": "sounds/kick.wav",
    "power_shot": "sounds/power_shot.wav",
    "bounce": "sounds/bounce.wav",
    "header": "sounds/header.wav",
    "goal": "sounds/goal.wav",
    "whistle": "sounds/whistle.wav",
    "menu_move": "sounds/menu_move.wav",
    "menu_select": "sounds/menu_select.wav",
}

_enabled = False
_cache: Dict[str, "pygame.mixer.Sound"] = {}
_warned: Set[str] = set()


def init() -> None:
    """Attempt to bring up the mixer. Safe to call more than once (a
    no-op if already enabled). Audio stays disabled on device/driver errors."""
    global _enabled
    if _enabled:
        return
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        _enabled = True
    except (pygame.error, OSError) as exc:
        print(f"headscotter: audio disabled ({exc})", file=sys.stderr)
        _enabled = False


def is_enabled() -> bool:
    return _enabled


def play(name: str) -> None:
    """Play a named sound effect once, fire-and-forget. A no-op if audio
    isn't enabled, ``name`` isn't declared in :data:`SOUND_SPECS`, or
    an expected error occurs loading/playing it -- a missing or
    corrupt sound file must never crash or stall the game, exactly like
    a missing sprite in :mod:`headscotter.assets`."""
    if not _enabled:
        return
    try:
        sound = _cache.get(name)
        if sound is None:
            if name not in SOUND_SPECS:
                return
            path = ASSETS_ROOT / SOUND_SPECS[name]
            sound = pygame.mixer.Sound(str(path))
            _cache[name] = sound
        sound.play()
    except (pygame.error, OSError) as exc:
        if name not in _warned:
            print(f"headscotter: could not play sound '{name}' ({exc})", file=sys.stderr)
            _warned.add(name)


def clear_cache() -> None:
    """Drop cached Sound objects and warning state (used by tests)."""
    _cache.clear()
    _warned.clear()


def set_enabled_for_testing(value: bool) -> None:
    """Test-only escape hatch so tests can exercise :func:`play`'s code
    paths without a real audio device. Never called from game code."""
    global _enabled
    _enabled = value
