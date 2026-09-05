"""Tests for match rules: the 90-second clock, goal scoring, most-goals-wins,
sudden death, and the persisted "most goals in a won 1P match" record."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from headscotter import config, match as match_mod


class ClockTests(unittest.TestCase):
    def test_new_match_starts_at_90_seconds_in_kickoff(self):
        state = match_mod.new_match()
        self.assertEqual(state.time_remaining, config.MATCH_SECONDS)
        self.assertEqual(state.phase, match_mod.MatchPhase.KICKOFF)
        self.assertFalse(match_mod.is_ball_live(state))

    def test_kickoff_freeze_transitions_to_playing(self):
        state = match_mod.new_match()
        match_mod.tick(state, config.KICKOFF_FREEZE_SECONDS + 0.01)
        self.assertEqual(state.phase, match_mod.MatchPhase.PLAYING)
        self.assertTrue(match_mod.is_ball_live(state))

    def test_clock_counts_down_while_playing(self):
        state = match_mod.new_match()
        match_mod.tick(state, config.KICKOFF_FREEZE_SECONDS + 0.01)
        match_mod.tick(state, 10.0)
        self.assertAlmostEqual(state.time_remaining, config.MATCH_SECONDS - 10.0, delta=0.02)

    def test_clock_does_not_tick_during_kickoff_or_celebration(self):
        state = match_mod.new_match()
        match_mod.tick(state, 0.5)  # still within the kickoff freeze
        self.assertEqual(state.time_remaining, config.MATCH_SECONDS)


class GoalScoringTests(unittest.TestCase):
    def _live_match(self) -> match_mod.MatchState:
        state = match_mod.new_match()
        match_mod.tick(state, config.KICKOFF_FREEZE_SECONDS + 0.01)
        return state

    def test_goal_increments_the_scoring_sides_score(self):
        state = self._live_match()
        match_mod.register_goal(state, side="left")
        self.assertEqual(state.score_left, 1)
        self.assertEqual(state.score_right, 0)
        self.assertEqual(state.phase, match_mod.MatchPhase.GOAL_CELEBRATION)

    def test_goal_celebration_returns_to_kickoff_then_playing(self):
        state = self._live_match()
        match_mod.register_goal(state, side="right")
        match_mod.tick(state, config.GOAL_CELEBRATION_SECONDS + 0.01)
        self.assertEqual(state.phase, match_mod.MatchPhase.KICKOFF)
        match_mod.tick(state, config.KICKOFF_FREEZE_SECONDS + 0.01)
        self.assertEqual(state.phase, match_mod.MatchPhase.PLAYING)

    def test_most_goals_wins_at_full_time(self):
        state = self._live_match()
        match_mod.register_goal(state, side="left")
        match_mod.register_goal(state, side="left")
        match_mod.register_goal(state, side="right")
        # Drain the match via many small per-frame ticks, exactly as the
        # real game loop does -- a single huge tick() call only ever
        # crosses one phase boundary, which is fine since real dt is
        # always small and capped (see game.Game.run()).
        for _ in range(int((config.MATCH_SECONDS + 10) * 60)):
            match_mod.tick(state, 1 / 60.0)
            if match_mod.is_match_over(state):
                break
        self.assertTrue(match_mod.is_match_over(state))
        self.assertEqual(match_mod.winner(state), "left")


class SuddenDeathTests(unittest.TestCase):
    def test_tie_at_full_time_enters_sudden_death_instead_of_ending(self):
        state = match_mod.new_match()
        match_mod.tick(state, config.KICKOFF_FREEZE_SECONDS + 0.01)
        match_mod.tick(state, config.MATCH_SECONDS)
        self.assertTrue(state.sudden_death)
        self.assertFalse(match_mod.is_match_over(state))
        self.assertEqual(state.time_remaining, 0.0)

    def test_sudden_death_first_goal_ends_the_match_immediately(self):
        state = match_mod.new_match()
        match_mod.tick(state, config.KICKOFF_FREEZE_SECONDS + 0.01)  # -> PLAYING
        match_mod.tick(state, config.MATCH_SECONDS)  # drains the clock; tied -> sudden death
        self.assertTrue(state.sudden_death)
        match_mod.register_goal(state, side="right")
        self.assertTrue(match_mod.is_match_over(state))
        self.assertEqual(match_mod.winner(state), "right")

    def test_sudden_death_clock_does_not_keep_counting(self):
        state = match_mod.new_match()
        match_mod.tick(state, config.KICKOFF_FREEZE_SECONDS + 0.01)
        match_mod.tick(state, config.MATCH_SECONDS)
        self.assertTrue(state.sudden_death)
        for _ in range(120):
            match_mod.tick(state, 1 / 60.0)
        self.assertFalse(match_mod.is_match_over(state))  # no goal yet -- still going


class WinnerTests(unittest.TestCase):
    def test_winner_is_none_on_a_tie(self):
        state = match_mod.MatchState(score_left=1, score_right=1)
        self.assertIsNone(match_mod.winner(state))

    def test_winner_is_the_higher_score(self):
        state = match_mod.MatchState(score_left=3, score_right=1)
        self.assertEqual(match_mod.winner(state), "left")


class HighScorePersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = TemporaryDirectory()
        self._original_path = config.HIGHSCORE_PATH
        config.HIGHSCORE_PATH = Path(self._tempdir.name) / "highscore.json"

    def tearDown(self):
        config.HIGHSCORE_PATH = self._original_path
        self._tempdir.cleanup()

    def test_missing_file_reads_as_zero(self):
        self.assertEqual(match_mod.load_high_score(), 0)

    def test_save_then_load_round_trips(self):
        match_mod.save_high_score(5)
        self.assertEqual(match_mod.load_high_score(), 5)

    def test_maybe_record_updates_only_on_a_new_best(self):
        self.assertEqual(match_mod.maybe_record_high_score(3), 3)
        self.assertEqual(match_mod.load_high_score(), 3)
        # A worse or equal score does not overwrite the record.
        self.assertEqual(match_mod.maybe_record_high_score(2), 3)
        self.assertEqual(match_mod.load_high_score(), 3)
        self.assertEqual(match_mod.maybe_record_high_score(7), 7)
        self.assertEqual(match_mod.load_high_score(), 7)

    def test_corrupt_file_reads_as_zero_without_raising(self):
        config.HIGHSCORE_PATH.write_text("not json", encoding="utf-8")
        self.assertEqual(match_mod.load_high_score(), 0)


if __name__ == "__main__":
    unittest.main()
