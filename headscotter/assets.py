"""Single point of access for all gameplay art.

Every PNG the game draws is declared once in :data:`SPRITE_SPECS`:
logical name -> (relative path under ``assets/``, nominal pixel size).
Nothing else in the codebase should ever read an asset file path
directly -- that table is the contract with whoever supplies real art
(see ``assets/README.md``).

Paths are resolved from this file's location via ``__file__``, never
from the current working directory, since the launcher may spawn the
game from anywhere. A missing or unreadable file never crashes the
game: :func:`get` falls back to a bright magenta placeholder and logs
exactly one warning to stderr per sprite name.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Set, Tuple

import pygame

ASSETS_ROOT = Path(__file__).resolve().parent.parent / "assets"

Size = Tuple[int, int]

# name -> (relative path under assets/, nominal pixel size)
SPRITE_SPECS: Dict[str, Tuple[str, Size]] = {
    # Scotty -- the human/P1 character, CMU's mascot Scottish Terrier.
    "scotty_run_1": ("sprites/scotty_run_1.png", (110, 150)),
    "scotty_run_2": ("sprites/scotty_run_2.png", (110, 150)),
    "scotty_jump": ("sprites/scotty_jump.png", (110, 150)),
    "scotty_kick": ("sprites/scotty_kick.png", (110, 150)),
    # Rival -- the CPU/P2 character, a distinct silhouette and color.
    "rival_run_1": ("sprites/rival_run_1.png", (110, 150)),
    "rival_run_2": ("sprites/rival_run_2.png", (110, 150)),
    "rival_jump": ("sprites/rival_jump.png", (110, 150)),
    "rival_kick": ("sprites/rival_kick.png", (110, 150)),
    # The ball and the pitch itself.
    "ball": ("sprites/ball.png", (36, 36)),
    "goal": ("sprites/goal.png", (90, 200)),
    "pitch_bg": ("sprites/pitch_bg.png", (800, 600)),
    # The automated keepers -- one static pose each, team-colored to
    # match the side they defend (see headscotter/keeper.py).
    "keeper_left": ("sprites/keeper_left.png", (72, 72)),
    "keeper_right": ("sprites/keeper_right.png", (72, 72)),
    # HUD glyph: a small ball icon used as the "-" divider between scores.
    "hud_ball_icon": ("sprites/hud_ball_icon.png", (32, 32)),
}

PLACEHOLDER_COLOR = (255, 0, 255)  # unmissable magenta

_cache: Dict[str, "pygame.Surface"] = {}
_warned: Set[str] = set()


def _placeholder(size: Size) -> "pygame.Surface":
    surface = pygame.Surface(size)
    surface.fill(PLACEHOLDER_COLOR)
    pygame.draw.line(surface, (0, 0, 0), (0, 0), (size[0] - 1, size[1] - 1), 2)
    pygame.draw.line(surface, (0, 0, 0), (0, size[1] - 1), (size[0] - 1, 0), 2)
    return surface


def get(name: str) -> "pygame.Surface":
    """Return the cached, nominal-size surface for a logical sprite name.

    Loads and scales at most once per name; safe to call every frame.
    """
    if name in _cache:
        return _cache[name]

    if name not in SPRITE_SPECS:
        raise KeyError(f"headscotter.assets: no such sprite declared: {name!r}")

    rel_path, size = SPRITE_SPECS[name]
    path = ASSETS_ROOT / rel_path
    try:
        surface = pygame.image.load(str(path))
        if pygame.display.get_surface() is not None:
            surface = surface.convert_alpha()
    except (pygame.error, FileNotFoundError, OSError) as exc:
        if name not in _warned:
            print(
                f"headscotter: missing or unreadable asset '{rel_path}' ({exc}); "
                "using placeholder",
                file=sys.stderr,
            )
            _warned.add(name)
        surface = _placeholder(size)

    if surface.get_size() != tuple(size):
        surface = pygame.transform.smoothscale(surface, size)

    _cache[name] = surface
    return surface


def preload_all() -> None:
    """Force every declared sprite through :func:`get` once, up front."""
    for name in SPRITE_SPECS:
        get(name)


def clear_cache() -> None:
    """Drop cached surfaces and warning state (used by tests)."""
    _cache.clear()
    _warned.clear()
