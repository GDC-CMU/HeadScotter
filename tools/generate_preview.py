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
spans one deterministically selected window of gameplay (an opening rally and its
restart, rather than just a huddle around kickoff), but only
``FRAME_COUNT`` frames are actually sampled from it,
evenly spaced through the whole window rather than consecutive ticks
in the selected window. The output ``fps`` in the manifest is a
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

import argparse
import json
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from headscotter import config, render  # noqa: E402
from headscotter.game import Game, GameState  # noqa: E402
from headscotter.input import RawInput  # noqa: E402
from headscotter.match import MatchPhase  # noqa: E402

# --- Tunables -----------------------------------------------------------------
# A build-time tool, not a runtime setting -- deliberately kept here rather
# than in headscotter/config.py.
SEED = 20260115  # fixed: pins every CPUController aim-error roll the demo makes
SIM_HZ = 60
DT = 1.0 / SIM_HZ

# Find one complete rally with this fixed seed rather than pinning stale
# goal/reset ticks every time the game's feel changes.
MAX_WINDOW_TICKS = SIM_HZ * 90

FPS = 12  # independent of how the window was sampled -- see module docstring
# 20 frames, evenly sampled across the whole WINDOW_TICKS span (not
# consecutive ticks): 20/12 ~= 1.67s, comfortably inside the launcher's
# "roughly 1-3s" guidance and well under MAX_PREVIEW_FRAMES=64.
FRAME_COUNT = 20

OUT_WIDTH, OUT_HEIGHT = 200, 150
OUT_DIR = REPO_ROOT / "assets" / "preview"


def preview_window_ticks() -> int:
    game = Game(rng=random.Random(SEED))
    game._enter_demo()
    scored = False
    restarted = False
    for tick in range(1, MAX_WINDOW_TICKS + 1):
        game.update(DT, RawInput())
        phase = game.match.phase
        if phase is MatchPhase.GOAL_CELEBRATION:
            scored = True
        elif scored and phase is MatchPhase.KICKOFF:
            restarted = True
        elif restarted and phase is MatchPhase.PLAYING:
            return tick
    raise RuntimeError("the fixed preview seed did not produce a complete rally")


def _render_clean_frame(screen, game: Game) -> None:
    """Render one frame via the real render path, but as ordinary
    gameplay: no "DEMO" / menu-wake overlay. That overlay is
    useful in-game (it tells a visitor this isn't a stuck real match) but
    would be redundant clutter inside a launcher card that already names
    the game and only ever shows the play area."""
    real_state = game.state
    game.state = GameState.MATCH
    try:
        render.draw_frame(screen, game)
    finally:
        game.state = real_state


def capture_ui(screen, out_dir: Path) -> None:
    """Bounded UI review via real states/inputs; no source art or scores written.

    Laptop frames are offscreen letterboxing checks, not a hardware display test.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    captures = []

    def capture(name, game):
        render.draw_frame(screen, game)
        image = screen.copy()
        captures.append((name, image))
        path = out_dir / f"headscotter-refinement-{name}.png"
        pygame.image.save(image, str(path))
        laptop = pygame.Surface((1920, 1080))
        laptop.fill((0, 0, 0))
        laptop.blit(pygame.transform.scale(image, (1440, 1080)), (240, 0))
        pygame.image.save(laptop, str(out_dir / f"headscotter-refinement-{name}-laptop.png"))
        print(path)

    for cabinet in (False, True):
        suffix = "cabinet" if cabinet else "keyboard"
        game = Game(rng=random.Random(SEED))
        if cabinet:
            game.joysticks[0] = object()  # presentation flag only; never polled
        game.attract_clock = 1.0
        capture(f"main-{suffix}", game)
        game.state = GameState.HOW_TO_PLAY
        capture(f"help-{suffix}", game)
        game.start_match("2P")
        game.match.phase = MatchPhase.PLAYING
        held = RawInput(buttons_by_device=(frozenset({1}), frozenset({1}))) if cabinet else RawInput(
            pressed_keys=frozenset({"c", "right shift"})
        )
        for _ in range(24):
            game.update(DT, held)
        if not cabinet:
            capture("live-charge", game)
        back = RawInput(buttons_by_device=(frozenset({0}), frozenset())) if cabinet else RawInput(
            pressed_keys=frozenset({"escape"})
        )
        game.update(DT, back)
        capture(f"pause-{suffix}", game)
        # 2P result cannot write the persisted 1P record.
        game.match.score_left, game.match.score_right = 3, 2
        game.match.phase = MatchPhase.FULL_TIME
        game._enter_result()
        capture(f"result-{suffix}", game)

    shot = Game(rng=random.Random(SEED))
    shot.start_match("2P")
    shot.match.phase = MatchPhase.PLAYING
    shot.ball.x = shot.player_left.x + 35
    for _ in range(38):
        shot.update(DT, RawInput(pressed_keys=frozenset({"c"})))
    for _ in range(5):
        shot.update(DT, RawInput())
    capture("power-flight", shot)

    goal = Game(rng=random.Random(SEED))
    goal._enter_demo()
    for _ in range(MAX_WINDOW_TICKS):
        goal.update(DT, RawInput())
        if goal.match.phase is MatchPhase.GOAL_CELEBRATION:
            capture("goal-feedback", goal)
            break
    else:
        raise RuntimeError("no goal event was available for UI capture")

    # One full-resolution batch sheet for the bounded visual inspection.
    sheet = pygame.Surface((2400, ((len(captures) + 2) // 3) * 630))
    sheet.fill((14, 20, 34))
    font = pygame.font.Font(None, 22)
    for index, (name, image) in enumerate(captures):
        x, y = (index % 3) * 800, (index // 3) * 630
        sheet.blit(font.render(name, True, (255, 210, 90)), (x + 16, y + 5))
        sheet.blit(image, (x, y + 30))
    path = out_dir / "headscotter-refinement-ui-batch.png"
    pygame.image.save(sheet, str(path))
    print(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui-output", type=Path, help="capture UI states here instead of regenerating the preview")
    args = parser.parse_args()
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))

    if args.ui_output is not None:
        capture_ui(screen, args.ui_output)
        return 0

    window_ticks = preview_window_ticks()
    stride_ticks = window_ticks / (FRAME_COUNT - 1)
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
            next_capture_at += stride_ticks
            if len(frame_names) >= FRAME_COUNT:
                break
        game.update(DT, idle)
        ticks_elapsed += 1.0

    manifest = {"version": 1, "fps": FPS, "frames": frame_names}
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        f"wrote {len(frame_names)} frames ({OUT_WIDTH}x{OUT_HEIGHT} @ {FPS}fps) "
        f"time-lapsed from {window_ticks} simulated ticks ({window_ticks / SIM_HZ:.1f}s), "
        f"{len(frame_names) / FPS:.2f}s loop, to {OUT_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
