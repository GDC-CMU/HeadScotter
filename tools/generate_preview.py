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
  match" record (``highscore.json``), and it is never displayed outside
  the RESULT screen -- the captured scene here is a live MATCH/DEMO
  frame (HUD score + clock only), which never reads that file. This
  script still never touches match.load_high_score()/Game() defaults
  that would, purely as a precaution: the frames captured below come
  from a demo entered directly, and Game.__init__() reading the real
  high score at construction time has no bearing on anything actually
  drawn in these frames.
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

# Chosen by sampling the demo's first several rallies: KICKOFF ends and
# PLAYING begins at simulated tick 72; the ball itself doesn't actually
# start moving until tick 89 (both players spend ~17 ticks closing in
# before the first kick), and the first goal ends live play at tick 154.
# WARMUP_TICKS lands just after the ball is kicked -- not at dead-center
# rest -- so the very first captured frame already shows real motion.
WARMUP_TICKS = 90
FPS = 8
FRAME_PERIOD_SECONDS = 1.0 / FPS
# 8 unique frames * 0.125s = 1.0s (60 ticks) of unique captured motion,
# ending around tick 150 -- comfortably inside the live window (goal at
# 154) with margin. The ping-pong sequence below doubles this to a
# 14-frame, 1.75s loop -- within the "roughly 1-3 seconds" target --
# without ever jump-cutting, since a goal/celebration freeze is never
# captured.
FRAME_COUNT = 8
OUT_WIDTH, OUT_HEIGHT = 200, 150
OUT_DIR = REPO_ROOT / "assets" / "preview"


def _ping_pong_sequence(names: list) -> list:
    """Forward then reverse, excluding the two endpoints from the reverse
    leg so they aren't held for a doubled frame: [0, 1, ..., N, N-1, ...,
    1] then wraps back to 0. Every adjacent pair in this sequence --
    including the wrap from the last entry back to the first -- is a
    real, adjacent pair from the original continuous capture, so the
    loop has no jump-cut anywhere."""
    if len(names) < 2:
        return list(names)
    return list(names) + list(reversed(names[1:-1]))


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
    for _ in range(WARMUP_TICKS):
        game.update(DT, idle)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Remove any stale frames from a previous run with a different
    # FRAME_COUNT, so the directory never accumulates orphans.
    for existing in OUT_DIR.glob("frame_*.png"):
        existing.unlink()

    frame_names = []
    elapsed_since_capture = 0.0
    while len(frame_names) < FRAME_COUNT:
        # Capture the very first frame of the window immediately (before
        # advancing), so the loop's first sample is exactly WARMUP_TICKS
        # in, then advance by simulated ticks between subsequent captures.
        if frame_names:
            game.update(DT, idle)
            elapsed_since_capture += DT
            if elapsed_since_capture < FRAME_PERIOD_SECONDS - 1e-9:
                continue
            elapsed_since_capture -= FRAME_PERIOD_SECONDS

        _render_clean_frame(screen, game)
        small = pygame.transform.scale(screen, (OUT_WIDTH, OUT_HEIGHT))
        name = f"frame_{len(frame_names):03d}.png"
        pygame.image.save(small, str(OUT_DIR / name))
        frame_names.append(name)

    manifest_frames = _ping_pong_sequence(frame_names)
    manifest = {"version": 1, "fps": FPS, "frames": manifest_frames}
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        f"wrote {len(frame_names)} unique frames ({OUT_WIDTH}x{OUT_HEIGHT} @ {FPS}fps), "
        f"{len(manifest_frames)}-entry ping-pong sequence, to {OUT_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
