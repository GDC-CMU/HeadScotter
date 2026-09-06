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

from . import config

ASSETS_ROOT = Path(__file__).resolve().parent.parent / "assets"

Size = Tuple[int, int]

# name -> (relative path under assets/, nominal pixel size)
SPRITE_SPECS: Dict[str, Tuple[str, Size]] = {
    # Scotty -- the human/P1 character, CMU's mascot Scottish Terrier.
    "scotty_idle": ("sprites/scotty_idle.png", (72, 90)),
    "scotty_run_1": ("sprites/scotty_run_1.png", (72, 90)),
    "scotty_run_2": ("sprites/scotty_run_2.png", (72, 90)),
    "scotty_jump": ("sprites/scotty_jump.png", (72, 90)),
    "scotty_kick": ("sprites/scotty_kick.png", (72, 90)),
    # Rival -- the CPU/P2 character, a distinct silhouette and color.
    "rival_idle": ("sprites/rival_idle.png", (72, 90)),
    "rival_run_1": ("sprites/rival_run_1.png", (72, 90)),
    "rival_run_2": ("sprites/rival_run_2.png", (72, 90)),
    "rival_jump": ("sprites/rival_jump.png", (72, 90)),
    "rival_kick": ("sprites/rival_kick.png", (72, 90)),
    # The ball.
    "ball": ("sprites/ball.png", (30, 30)),
    # Goals in profile, flush with each screen edge -- two distinct files
    # (not one code-mirrored image) so a real art pass can draw each end
    # with its own perspective/lighting if it wants to.
    "goal_left": ("sprites/goal_left.png", (config.GOAL_WIDTH, config.GOAL_MOUTH_HEIGHT)),
    "goal_right": ("sprites/goal_right.png", (config.GOAL_WIDTH, config.GOAL_MOUTH_HEIGHT)),
    # The side-view stage: stadium backdrop (sky/stands/crowd/floodlights),
    # a scrolling advertising hoarding, and the grass strip -- replaces the
    # old top-down pitch_bg.png entirely. See assets/README.md.
    "bg_stadium": ("sprites/bg_stadium.png", (config.SCREEN_WIDTH, config.GROUND_Y)),
    "bg_hoarding": ("sprites/bg_hoarding.png", (config.HOARDING_WIDTH, config.HOARDING_HEIGHT)),
    "ground": ("sprites/ground.png", (config.SCREEN_WIDTH, config.GROUND_HEIGHT)),
    # The compact HUD scoreboard panel.
    "scoreboard": ("sprites/scoreboard.png", (config.SCOREBOARD_WIDTH, config.SCOREBOARD_HEIGHT)),
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
