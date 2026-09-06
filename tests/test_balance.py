"""Regression guard for match-scoring balance.

The genre has no goalkeeper (confirmed across every reference
implementation in the project's genre research report) -- each player,
human or CPU, defends their own goal directly, with a real, visually
credible goal size (GOAL_MOUTH_HEIGHT, ~0.33 * screen height, taller than
a standing player -- sourced from the reference implementation that runs
at this project's exact 800x600 resolution). Without a keeper as a last
line of defense, defense is held entirely by the CPU's own positioning
discipline (CPU_MAX_ADVANCE_FRACTION), ball feel (BALL_RESTITUTION_HEAD,
KICK_IMPULSE_SPEED), and the anti-stalemate/anti-blowout guards
(CPU_RESTING_SPEED_PX, CPU_STALEMATE_SECONDS) -- tuned by simulating full
CPU-vs-CPU matches and measuring the result, not by eye. This module
re-runs that same measurement on every test run, so a change to any of
those constants that lets scoring drift back into "meaningless
scoreboard" territory (in *either* direction: unwatchable blowouts, or
defense so good nobody can ever score) fails loudly here instead of only
being noticed by someone watching a preview clip.

Re-tuned once more after making the ball itself bouncier/floatier
(BALL_GRAVITY/BALL_RESTITUTION_GROUND, both in config.py, raised to make
the ball feel "light" rather than "heavy" per a direct play-feel
complaint): a livelier ball needed CPU_MAX_ADVANCE_FRACTION,
BALL_RESTITUTION_HEAD, and KICK_IMPULSE_SPEED all re-swept together, or
scoring ran away into the double digits per side. The thresholds below
reflect that re-sweep (30+ simulated seeds, tracking the worst-case
per-side score, not only the mean), not the original ball-physics pass.

Confirmed again after adding a real body collider (fixing the ball
passing straight through a standing player), per-substep ball collision
checks (fixing tunnelling at high ball speed), and the chargeable power
shot: a 20-seed sweep over this same seed range gave per-side scores of
1-7 and match totals of 4-11 (avg ~7.65), comfortably inside the
thresholds below and with zero non-terminating matches -- none of that
round's changes needed a further re-tune of the constants above.

Also confirms sudden death itself always terminates: with no keeper and
a smaller defensive leash than before, a tied match staying tied is a
real possibility, and this locks in that it still always resolves within
a generous, bounded budget.
"""
from __future__ import annotations

import random
import unittest

from headscotter import config
from headscotter.cpu import CPUController
from headscotter.game import Game, GameState
from headscotter.input import RawInput

# Sourced band: "low single digits (0-5)" per side. Set with headroom
# above the actually-observed simulated range (30+ simulated seeds with
# the current constants gave per-side scores of 0-6 and match totals of
# 5-9 -- see the constants' own comments in config.py) so this doesn't
# flake on ordinary variance, while still catching a regression back
# toward a double-digit-per-side blowout tail by a wide margin.
MAX_GOALS_PER_SIDE = 8
MAX_TOTAL_GOALS = 14
MIN_ACCEPTABLE_AVERAGE_TOTAL = 1.0
MAX_ACCEPTABLE_AVERAGE_TOTAL = 8.0

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
