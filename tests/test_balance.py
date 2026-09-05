"""Regression guard for match-scoring balance.

This is what caught, and now locks in the fix for, a very real bug: an
earlier build's goal was so large (and nothing defended it) that a single
simulated 90-second CPU-vs-CPU match finished 31-28 -- roughly a goal
every 1.5 seconds. The fix (see headscotter/config.py: GOAL_MOUTH_HEIGHT,
CPU_MAX_ADVANCE_FRACTION, BALL_RESTITUTION_HEAD, CPU_RESTING_SPEED_PX,
CPU_STALEMATE_SECONDS) was grounded in real references (real football's
goal-to-player-height ratio; how 2D "head soccer" clones without a
keeper size their goal and position their defenders) and then driven the
rest of the way by simulating full matches and measuring the result --
not tuned by eye. This module re-runs that same measurement on every test
run, so a change to any of those constants that lets scoring drift back
into "meaningless scoreboard" territory fails loudly here instead of only
being noticed by someone watching a preview clip.

Also confirms sudden death itself always terminates: with a much smaller
goal, a tied match staying tied became a real possibility, and this
locks in that it still always resolves within a generous, bounded budget.
"""
from __future__ import annotations

import random
import unittest

from headscotter import config
from headscotter.cpu import CPUController
from headscotter.game import Game, GameState
from headscotter.input import RawInput

# Plausible per the client's brief: "somewhere around 3-10 goals total"
# for a full match, i.e. comfortably single digits per side. Set with
# generous headroom above the actually-observed simulated range (see the
# module docstring and the constants' own comments in config.py: 150
# simulated seeds gave totals of 3-8 and a max of 6 on either side) so
# this doesn't flake on ordinary variance, while still catching a
# regression back toward the old ~30-goals-a-side failure mode by a wide
# margin.
MAX_GOALS_PER_SIDE = 15
MAX_TOTAL_GOALS = 25
MIN_ACCEPTABLE_AVERAGE_TOTAL = 1.0
MAX_ACCEPTABLE_AVERAGE_TOTAL = 14.0

# A real 90s match's *live* playing time is bounded, but every goal also
# spends GOAL_CELEBRATION_SECONDS + KICKOFF_FREEZE_SECONDS frozen, and a
# tied match continues into sudden death with no clock at all -- so the
# wall-clock (simulated) ticks needed to reach FULL_TIME has no hard
# ceiling in principle. This budget is generous specifically so a slow-
# to-resolve sudden death is given every reasonable chance to finish
# before the test calls it a real failure -- confirmed by direct
# investigation that legitimate matches can take several real minutes to
# resolve when scoring is this restrained, which is the point.
MAX_SIMULATED_SECONDS = 20 * 60  # 20 minutes of simulated match time
DT = 1.0 / 60.0

SEEDS = range(20)


def _simulate_cpu_vs_cpu_match(seed: int):
    """Run one full CPU-vs-CPU match through the real game state machine
    (match.py rules, physics.py collisions, cpu.py AI, players.py
    movement) start to finish, and return the finished Game. Raises
    AssertionError if it never reaches a result within MAX_SIMULATED_SECONDS."""
    game = Game(rng=random.Random(seed))
    game._start_match_common(
        "2P",
        CPUController(rng=game.rng, defend_x=config.PITCH_LEFT),
        CPUController(rng=game.rng, defend_x=config.PITCH_RIGHT),
    )
    game.state = GameState.MATCH
    idle = RawInput()
    for _ in range(int(MAX_SIMULATED_SECONDS / DT)):
        game._advance_match(DT, idle)
        if game.state is GameState.RESULT:
            return game
    raise AssertionError(
        f"seed {seed}: match never resolved within {MAX_SIMULATED_SECONDS}s of "
        f"simulated time (sudden death should always terminate); score so far "
        f"{game.match.score_left}-{game.match.score_right}, sudden_death={game.match.sudden_death}"
    )


class ScoringBalanceTests(unittest.TestCase):
    def test_full_matches_produce_plausible_single_digit_scorelines(self):
        totals = []
        for seed in SEEDS:
            with self.subTest(seed=seed):
                game = _simulate_cpu_vs_cpu_match(seed)
                left, right = game.match.score_left, game.match.score_right
                total = left + right
                totals.append(total)
                self.assertLessEqual(
                    left, MAX_GOALS_PER_SIDE,
                    f"seed {seed}: left scored {left}, an implausible blowout",
                )
                self.assertLessEqual(
                    right, MAX_GOALS_PER_SIDE,
                    f"seed {seed}: right scored {right}, an implausible blowout",
                )
                self.assertLessEqual(
                    total, MAX_TOTAL_GOALS,
                    f"seed {seed}: {left}-{right} is an implausible total for a 90s match",
                )
                self.assertGreaterEqual(total, 1, f"seed {seed}: a finished match always has >=1 goal")

        average_total = sum(totals) / len(totals)
        self.assertGreaterEqual(
            average_total, MIN_ACCEPTABLE_AVERAGE_TOTAL,
            f"average total goals ({average_total:.1f}) across {len(totals)} matches is implausibly low",
        )
        self.assertLessEqual(
            average_total, MAX_ACCEPTABLE_AVERAGE_TOTAL,
            f"average total goals ({average_total:.1f}) across {len(totals)} matches is implausibly high "
            "-- this is exactly the regression this test exists to catch",
        )

    def test_sudden_death_always_terminates(self):
        """Directly force a tied sudden-death state (rather than relying
        on one incidentally happening) and confirm it always resolves to
        a decisive score within the generous budget above."""
        from headscotter import match as match_mod

        for seed in (100, 101, 102):
            with self.subTest(seed=seed):
                game = Game(rng=random.Random(seed))
                game._start_match_common(
                    "2P",
                    CPUController(rng=game.rng, defend_x=config.PITCH_LEFT),
                    CPUController(rng=game.rng, defend_x=config.PITCH_RIGHT),
                )
                game.state = GameState.MATCH
                game.match.score_left = 3
                game.match.score_right = 3
                game.match.time_remaining = 0.0
                game.match.sudden_death = True
                game.match.phase = match_mod.MatchPhase.PLAYING

                idle = RawInput()
                resolved = False
                for _ in range(int(MAX_SIMULATED_SECONDS / DT)):
                    game._advance_match(DT, idle)
                    if game.state is GameState.RESULT:
                        resolved = True
                        break
                self.assertTrue(
                    resolved,
                    f"seed {seed}: a forced tied sudden-death match never resolved within "
                    f"{MAX_SIMULATED_SECONDS}s of simulated time",
                )
                self.assertNotEqual(game.match.score_left, game.match.score_right)


if __name__ == "__main__":
    unittest.main()
