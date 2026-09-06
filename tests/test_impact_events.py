"""Real contact episodes drive visual feedback, not support or corrections."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from headscotter import config, physics, players
from headscotter.game import Game
from headscotter.input import RawInput
from headscotter.match import MatchPhase


class ImpactEventTests(unittest.TestCase):
    def live_game(self):
        game = Game()
        game.start_match("2P")
        game.match.phase = MatchPhase.PLAYING
        return game

    def test_floor_rest_and_rolling_do_not_emit_impact_feedback(self):
        for speed in (0.0, 150.0, 850.0):
            with self.subTest(speed=speed):
                game = self.live_game()
                game.ball.vx = speed
                with patch.object(game.feedback, "impact", wraps=game.feedback.impact) as impact:
                    for _ in range(240):
                        game.ball.x = config.PITCH_CENTER_X
                        game.update(1 / 60, RawInput())
                    impact.assert_not_called()
                self.assertLess(game.match.time_remaining, config.MATCH_SECONDS)
                self.assertEqual(game.ball.vy, 0.0)

    def test_real_drop_emits_impacts_then_settles(self):
        game = self.live_game()
        game.ball.y -= 160
        with patch.object(game.feedback, "impact", wraps=game.feedback.impact) as impact:
            for _ in range(1200):
                game.update(1 / 60, RawInput())
                if game.ball.vy == 0.0 and game.ball.y == config.GROUND_Y - game.ball.radius:
                    break
            self.assertGreater(sum(c.args[1] == "ground" for c in impact.call_args_list), 1)
            self.assertEqual(game.ball.vy, 0.0)
            impact.reset_mock()
            for _ in range(120):
                game.update(1 / 60, RawInput())
            impact.assert_not_called()
            game.ball.y -= 100
            for _ in range(120):
                game.update(1 / 60, RawInput())
            self.assertTrue(any(c.args[1] == "ground" for c in impact.call_args_list))

    def test_header_correction_and_separation_are_not_incoming_impacts(self):
        for vy, expected in ((0, 0), (-200, 0), (200, 1)):
            game = self.live_game()
            hx, hy = game.player_left.head_center
            game.ball = physics.Ball(hx, hy - config.HEAD_RADIUS - 5, vy=vy)
            with patch.object(game.feedback, "impact", wraps=game.feedback.impact) as impact:
                game.update(1 / 60, RawInput())
            self.assertEqual(
                sum(c.args[1].startswith("head:") for c in impact.call_args_list), expected,
            )

    def test_same_header_contact_is_coalesced_until_real_separation(self):
        player = players.new_player(400, 1)
        hx, hy = player.head_center
        ball = physics.Ball(hx, hy - config.HEAD_RADIUS - 5, vy=200)
        impact = Mock()
        for _ in range(5):
            ball.y = hy - config.HEAD_RADIUS - 5
            ball.vy = 200
            players.apply_head_collision(player, ball, impact)
        self.assertEqual(impact.call_count, 1)
        ball.y -= 100
        players.apply_head_collision(player, ball, impact)
        ball.y = hy - config.HEAD_RADIUS - 5
        ball.vy = 200
        players.apply_head_collision(player, ball, impact)
        self.assertEqual(impact.call_count, 2)

    def test_ball_resting_on_a_head_does_not_manufacture_repeat_impacts(self):
        game = self.live_game()
        hx, hy = game.player_left.head_center
        game.ball = physics.Ball(hx, hy - config.HEAD_RADIUS - config.BALL_RADIUS)
        with patch.object(game.feedback, "impact", wraps=game.feedback.impact) as impact:
            for _ in range(600):
                game.update(1 / 60, RawInput())
            impact.assert_not_called()

    def test_header_event_uses_relative_incoming_motion(self):
        for player_vy, expected in ((-200, 1), (200, 0)):
            player = players.new_player(400, 1)
            player.vy = player_vy
            hx, hy = player.head_center
            ball = physics.Ball(hx, hy - config.HEAD_RADIUS - 5, vy=100)
            impact = Mock()
            players.apply_head_collision(player, ball, impact)
            self.assertEqual(impact.call_count, expected)
