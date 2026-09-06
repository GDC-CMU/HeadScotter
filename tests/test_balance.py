"""Finite-match and scoring-integrity regressions, not scoreline tuning.

The former 8-per-side / 14-total / 8-average ceilings rewarded the old
defensive leash and contradict the requested attacking CPU. They are
intentionally replaced, not raised until a sweep passes. Fairness is checked
by mirrored physical scenarios and an unsaveable shot in test_cpu.py.
Real matches and sudden death must still finish without crashes, nonfinite
actors, impossible duplicate goals, or changing human physics to get there.
"""
from __future__ import annotations

import math
import random
import unittest

from headscotter import config, match as match_mod
from headscotter.cpu import CPUController
from headscotter.game import Game, GameState
from headscotter.input import RawInput

MAX_SIMULATED_SECONDS = 20 * 60  # unchanged generous sudden-death failure budget
DT = 1.0 / 60.0
SEEDS = range(20)


def _simulate_cpu_vs_cpu_match(seed: int, sudden_death=False):
    game = Game(rng=random.Random(seed))
    game._start_match_common(
        "2P",
        CPUController(rng=game.rng, defend_x=config.PITCH_LEFT),
        CPUController(rng=game.rng, defend_x=config.PITCH_RIGHT),
    )
    game.state = GameState.MATCH
    if sudden_death:
        game.match.score_left = game.match.score_right = 3
        game.match.time_remaining = 0.0
        game.match.sudden_death = True
        game.match.phase = match_mod.MatchPhase.PLAYING
    previous_total = game.match.score_left + game.match.score_right
    for _ in range(int(MAX_SIMULATED_SECONDS / DT)):
        game.update(DT, RawInput())
        total = game.match.score_left + game.match.score_right
        assert total - previous_total in (0, 1), "impossible score increment"
        previous_total = total
        assert all(math.isfinite(value) for value in (
            game.ball.x, game.ball.y, game.ball.vx, game.ball.vy,
            game.player_left.x, game.player_left.y, game.player_right.x, game.player_right.y,
        ))
        assert game.ball.speed() <= config.BALL_MAX_SPEED + 1e-6
        assert 0 <= game.match.time_remaining <= config.MATCH_SECONDS
        if game.state is GameState.RESULT:
            return game
    raise AssertionError(f"seed {seed}: match never resolved in {MAX_SIMULATED_SECONDS}s; "
                         f"score {game.match.score_left}-{game.match.score_right}, "
                         f"sudden_death={game.match.sudden_death}")


class FinitePlayTests(unittest.TestCase):
    def test_full_matches_finish_with_legitimate_decisive_scores(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                game = _simulate_cpu_vs_cpu_match(seed)
                self.assertEqual(game.match.phase, match_mod.MatchPhase.FULL_TIME)
                self.assertNotEqual(game.match.score_left, game.match.score_right)
                self.assertGreaterEqual(game.match.score_left + game.match.score_right, 1)

    def test_sudden_death_always_terminates(self):
        for seed in (100, 101, 102):
            with self.subTest(seed=seed):
                game = _simulate_cpu_vs_cpu_match(seed, sudden_death=True)
                self.assertEqual(game.match.score_left + game.match.score_right, 7)
                self.assertNotEqual(game.match.score_left, game.match.score_right)


if __name__ == "__main__":
    unittest.main()
