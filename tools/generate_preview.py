#!/usr/bin/env python
"""Generate the ArcadeLauncher's attract-mode preview animation from the
real game.

The launcher's own gallery attract mode plays a short looping animation
inside each game's card. It cannot run another process's game loop to
produce that (separate processes; the launcher owns SDL), so each game
ships a small pre-rendered loop instead -- see the cross-repo contract
this must match, ``preview-contract.md``.

This script drives HeadScotter's actual attract-mode demo (the same one
shown in-game after 15 seconds idle -- see
``headscotter.game.Game._enter_demo``, a real CPU-vs-CPU match) headlessly,
captures a handful of frames through the real render path
(``headscotter.render.draw_frame``), downsamples them to card size, and
writes them plus ``manifest.json`` to ``assets/preview/``.

The captured window is a **time-lapse**, not a straight recording: it
spans ``WINDOW_TICKS`` of simulated gameplay (roughly three rallies --
enough for the ball to travel to both goals, not just huddle around
kickoff), but only ``FRAME_COUNT`` frames are actually sampled from it,
evenly spaced through the whole window rather than consecutive ticks
(see ``STRIDE_TICKS`` below). The output ``fps`` in the manifest is a
separate, independent choice -- how fast the *card* plays the sampled
highlights back -- not the rate anything was captured at.

Deterministic by construction, so running this twice leaves ``git
status`` clean:

* The demo's CPU controllers are seeded from a fixed constant (SEED
  below), via ``Game(rng=random.Random(SEED))`` -- this is the only
  source of randomness anywhere in the demo (CPU aim error).
* Every simulated frame advances by the same fixed ``DT`` (1/60s),
  never real elapsed wall-clock time -- the whole demo is driven by a
  manual loop calling ``game.update(DT, RawInput())``, not ``run()``.
* Unlike the club's other two games, HeadScotter's render path never
  calls ``pygame.time.get_ticks()`` -- walk-cycle animation timing is
  driven entirely by ``Game.anim_clock``, a plain float accumulated by
  the same fixed ``DT`` above -- so no synthetic-clock monkeypatch is
  needed here to keep animation state reproducible.
* HeadScotter's only persisted state is the "most goals in a won 1P
  match" record (``highscore.json``). It is never read here (frames come
  from a demo entered directly, and Game.__init__() reading that file at
  construction time has no bearing on anything drawn) and never shown
  outside the RESULT screen anyway -- the captured HUD is score + clock
  only, both of which are entirely a function of the fixed seed and
  fixed timestep above, never of anything persisted to disk. This is
  the exact trap that broke PacDawg's first version of this tool (a
  persisted high score baked into the HUD), so it's called out
  explicitly here even though it can't actually occur in this game.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from headscotter import config, render  # noqa: E402
from headscotter.game import Game, GameState  # noqa: E402
from headscotter.input import RawInput  # noqa: E402

# --- Tunables -----------------------------------------------------------------
# A build-time tool, not a runtime setting -- deliberately kept here rather
# than in headscotter/config.py.
SEED = 20260115  # fixed: pins every CPUController aim-error roll the demo makes
SIM_HZ = 60
DT = 1.0 / SIM_HZ

# Chosen by tracing this exact seed's demo (see the tests/dev session, not
# reproduced here): the third rally's goal is scored at the LEFT end after
# the first two are scored at the RIGHT end, so this window is the shortest
# prefix of the demo that visits *both* halves of the pitch and *both*
# goals, ending right as the ball resets to center for the next kickoff --
# a visual near-match for the window's own opening frame, so the loop-back
# reads as another kickoff rather than a jump to a random moment.
#
#   tick    0 : KICKOFF, ball at center (the window's opening frame)
#   tick   72 : PLAYING begins (rally 1)
#   tick  168 : GOAL -- ball crosses into the right goal (score 1-0)
#   tick  361 : PLAYING begins (rally 2)
#   tick  457 : GOAL -- right goal again (score 2-0)
#   tick  650 : PLAYING begins (rally 3)
#   tick  732 : GOAL -- LEFT goal this time (score 2-1) -- both goals now covered
#   tick  853 : KICKOFF again, ball reset to center -- the window's closing frame
WINDOW_TICKS = 853

FPS = 12  # independent of how the window was sampled -- see module docstring
# 46 frames, evenly sampled across the whole WINDOW_TICKS span (not
# consecutive ticks), played back at FPS above: 46/12 = ~3.83s, comfortably
# inside the launcher's "roughly 1-3s" guidance's generous upper end and
# well under MAX_PREVIEW_FRAMES=64.
FRAME_COUNT = 46
STRIDE_TICKS = WINDOW_TICKS / (FRAME_COUNT - 1)

OUT_WIDTH, OUT_HEIGHT = 200, 150
OUT_DIR = REPO_ROOT / "assets" / "preview"


def _render_clean_frame(screen, game: Game) -> None:
    """Render one frame via the real render path, but as ordinary
    gameplay: no "DEMO" / "PRESS START TO PLAY" overlay. That overlay is
    useful in-game (it tells a visitor this isn't a stuck real match) but
    would be redundant clutter inside a launcher card that already names
    the game and only ever shows the play area."""
    real_state = game.state
    game.state = GameState.MATCH
    try:
        render.draw_frame(screen, game)
    finally:
        game.state = real_state


def main() -> int:
    pygame.init()
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))

    game = Game(rng=random.Random(SEED))
    game._enter_demo()
    idle = RawInput()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Remove any stale frames from a previous run with a different
    # FRAME_COUNT, so the directory never accumulates orphans.
    for existing in OUT_DIR.glob("frame_*.png"):
        existing.unlink()

    frame_names = []
    ticks_elapsed = 0.0
    next_capture_at = 0.0
    while len(frame_names) < FRAME_COUNT:
        if ticks_elapsed >= next_capture_at - 1e-9:
            _render_clean_frame(screen, game)
            small = pygame.transform.scale(screen, (OUT_WIDTH, OUT_HEIGHT))
            name = f"frame_{len(frame_names):03d}.png"
            pygame.image.save(small, str(OUT_DIR / name))
            frame_names.append(name)
            next_capture_at += STRIDE_TICKS
            if len(frame_names) >= FRAME_COUNT:
                break
        game.update(DT, idle)
        ticks_elapsed += 1.0

    manifest = {"version": 1, "fps": FPS, "frames": frame_names}
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        f"wrote {len(frame_names)} frames ({OUT_WIDTH}x{OUT_HEIGHT} @ {FPS}fps) "
        f"time-lapsed from {WINDOW_TICKS} simulated ticks ({WINDOW_TICKS / SIM_HZ:.1f}s), "
        f"{len(frame_names) / FPS:.2f}s loop, to {OUT_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
