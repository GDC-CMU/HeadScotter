import copy
import os
import pickle
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from headscotter import config, feedback, physics, render
from headscotter.game import Game, GameState, RESULT_ITEMS
from headscotter.input import PlayerActions, RawInput
from headscotter.match import MatchPhase


class FeedbackStateTests(unittest.TestCase):
    def test_transient_lists_are_bounded_and_expire(self):
        state = feedback.MatchFeedback(0)
        ball = physics.Ball(0, 300)
        for index in range(100):
            ball.x = index * 40
            state.shot(ball, True)
            state.observe(ball, (), 1 / 60)
            self.assertLessEqual(len(state.trail), config.BALL_TRAIL_LIMIT)
            self.assertLessEqual(len(state.impacts), config.IMPACT_FEEDBACK_LIMIT)
        state.advance(2)
        self.assertEqual(state.trail, [])
        self.assertEqual(state.impacts, [])
        self.assertEqual(state.power_remaining, 0)

    def test_coupled_contacts_make_one_readable_mark(self):
        state = feedback.MatchFeedback(400)
        ball = physics.Ball(400, 485)
        state.impact(ball, "ground")
        state.impact(ball, "body:scotty")
        state.impact(ball, "body:rival")
        self.assertEqual(len(state.impacts), 1)

    def live(self):
        game = Game()
        game.start_match("2P")
        game.match.phase = MatchPhase.PLAYING
        return game

    def test_miss_has_no_fake_contact_but_real_strikes_do(self):
        game = self.live()
        game._apply_actions(game.player_left, PlayerActions(normal_kicks=1), 1 / 60)
        self.assertEqual(game.feedback.impacts, [])
        game.ball = physics.Ball(game.player_left.x + 35, config.GROUND_Y - config.BALL_RADIUS)
        game._apply_actions(game.player_left, PlayerActions(normal_kicks=1), 1 / 60)
        self.assertEqual(game.feedback.impacts[-1].kind, "kick")

    def test_power_readiness_cue_is_a_transition_not_a_permanent_bar(self):
        game = self.live()
        game.player_left.kick_cooldown = 0.01
        game.feedback.observe(game.ball, (game.player_left, game.player_right), 0)
        game.update(1 / 60, RawInput())
        self.assertGreater(game.feedback.ready_remaining[0], 0)
        for _ in range(40):
            game.update(1 / 60, RawInput())
        self.assertEqual(game.feedback.ready_remaining[0], 0)

    def test_feedback_freezes_during_pause(self):
        game = self.live()
        game.feedback.shot(game.ball, True)
        game.feedback.observe(game.ball, (game.player_left, game.player_right), 1 / 60)
        game.update(1 / 60, RawInput(pressed_keys=frozenset({"escape"})))
        frozen = copy.deepcopy(vars(game.feedback))
        rng = game.rng.getstate()
        for _ in range(40):
            game.update(0.25, RawInput())
        self.assertEqual(vars(game.feedback), frozen)
        self.assertEqual(game.rng.getstate(), rng)

    def test_rendering_feedback_does_not_mutate_the_game_or_rng(self):
        pygame.init()
        render.clear_caches()
        self.addCleanup(render.clear_caches)
        game = self.live()
        game.feedback.shot(game.ball, True)
        game.feedback.observe(game.ball, (game.player_left, game.player_right), 1 / 60)
        before = pickle.dumps(game)
        screen = pygame.Surface((800, 600))
        for _ in range(5):
            render.draw_frame(screen, game)
        self.assertEqual(pickle.dumps(game), before)


class RematchFlowTests(unittest.TestCase):
    def result(self, mode):
        game = Game()
        game.start_match(mode)
        game.match.score_left = 2
        game.match.score_right = 3
        game.match.phase = MatchPhase.FULL_TIME
        with patch("headscotter.match.load_high_score", return_value=7):
            game.update(1 / 60, RawInput())
        self.assertIs(game.state, GameState.RESULT)
        game.update(1 / 60, RawInput())
        return game

    def test_rematch_keeps_mode_but_resets_match_actors_and_feedback(self):
        for mode in ("1P", "2P"):
            with self.subTest(mode=mode):
                game = self.result(mode)
                old_match, old_player = game.match, game.player_left
                game.player_left.kick_cooldown = 1
                game.feedback.shot(game.ball, True)
                game.update(1 / 60, RawInput(pressed_buttons=frozenset({9})))
                self.assertIs(game.state, GameState.MATCH)
                self.assertEqual(game.mode, mode)
                self.assertIsNot(game.match, old_match)
                self.assertIsNot(game.player_left, old_player)
                self.assertEqual((game.match.score_left, game.match.score_right), (0, 0))
                self.assertEqual(game.match.time_remaining, config.MATCH_SECONDS)
                self.assertEqual(game.player_left.kick_cooldown, 0)
                self.assertEqual(game.feedback.impacts, [])
                self.assertIsNone(game.result_winner)
                self.assertEqual(game.cpu_right is not None, mode == "1P")
                for _ in range(20):
                    game.update(1 / 60, RawInput(pressed_buttons=frozenset({9})))
                self.assertIs(game.state, GameState.MATCH)

    def test_main_menu_is_an_explicit_result_choice(self):
        game = self.result("2P")
        game.result_index = RESULT_ITEMS.index("MAIN MENU")
        game.update(1 / 60, RawInput(pressed_keys=frozenset({"return"})))
        self.assertIs(game.state, GameState.ATTRACT)
        game.update(1 / 60, RawInput(pressed_keys=frozenset({"return"})))
        self.assertIs(game.state, GameState.ATTRACT)
