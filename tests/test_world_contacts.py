"""Real, live-frame regressions for solid bodies and coherent ball motion."""
from __future__ import annotations

import math
import random
import unittest

from headscotter import config, physics, players
from headscotter.game import Game
from headscotter.input import RawInput
from headscotter.match import MatchPhase


class WorldContactTests(unittest.TestCase):
    def game(self):
        game = Game(rng=random.Random(41))
        game.start_match("2P")
        game.match.phase = MatchPhase.PLAYING
        game.player_left.x = 100.0
        game.player_right.x = 400.0
        return game

    def assert_clear(self, game):
        ball = game.ball
        for player in (game.player_left, game.player_right):
            hx, hy = player.head_center
            self.assertGreaterEqual(
                math.hypot(ball.x - hx, ball.y - hy),
                config.HEAD_RADIUS + ball.radius - 1e-4,
                f"rendered ball inside {player.sprite_key}'s head: {ball.pos}",
            )
            left, top, right, bottom = players.body_rect(player)
            distance = math.hypot(
                ball.x - physics.clamp(ball.x, left, right),
                ball.y - physics.clamp(ball.y, top, bottom),
            )
            self.assertGreaterEqual(
                distance, ball.radius - 1e-4,
                f"rendered ball inside {player.sprite_key}'s torso: {ball.pos}",
            )
        self.assertLessEqual(ball.y + ball.radius, config.GROUND_Y + 1e-4)
        self.assertLessEqual(ball.speed(), config.BALL_MAX_SPEED + 1e-4)

    def test_ordinary_ground_contact_is_resolved_before_rendering(self):
        game = self.game()
        game.ball = physics.Ball(364.0, 485.0, vx=300.0)
        game.update(1 / 60, RawInput())
        self.assert_clear(game)

    def test_gravity_from_rest_cannot_skip_a_head_during_a_slow_frame(self):
        game = self.game()
        game.ball = physics.Ball(400.0, 370.0)
        game.update(0.25, RawInput())
        self.assert_clear(game)
        self.assertLessEqual(game.ball.y, 400.0)
        self.assertLess(game.ball.vy, 0.0)

    def test_body_carries_a_contacted_ball_forward_instead_of_walking_through_it(self):
        for dt in (1 / 60, 0.1, 0.25):
            with self.subTest(dt=dt):
                game = self.game()
                game.player_left.x, game.player_right.x = 320.0, 700.0
                game.ball = physics.Ball(355.0, 485.0)
                game.update(dt, RawInput(pressed_keys=frozenset({"d"})))
                self.assert_clear(game)
                self.assertGreaterEqual(
                    game.ball.x,
                    game.player_left.x + config.PLAYER_HALF_WIDTH + game.ball.radius - 1e-4,
                )
                self.assertGreater(game.ball.vx, 100.0, "moving contact must transfer motion")

    def test_jump_into_a_stationary_ball_produces_an_upward_header(self):
        game = self.game()
        game.player_left.x, game.player_right.x = 400.0, 700.0
        game.ball = physics.Ball(400.0, 399.0)
        game.update(1 / 60, RawInput(pressed_keys=frozenset({"w"})))
        self.assert_clear(game)
        self.assertLess(game.ball.vy, -100.0, "a rising head must hit, not just reposition, the ball")

    def test_a_moving_kick_escapes_its_kicker_without_collision_immunity(self):
        game = self.game()
        game.player_left.x, game.player_right.x = 360.0, 700.0
        game.ball = physics.Ball(395.0, 485.0)
        game.update(1 / 60, RawInput(pressed_keys=frozenset({"d", "x"})))
        self.assert_clear(game)
        self.assertGreater(game.ball.vx, config.PLAYER_SPEED)

    def test_a_rebound_cannot_pass_through_the_player_who_just_kicked(self):
        for gap in (70.0, 75.0, 80.0, 90.0):
            with self.subTest(gap=gap):
                game = self.game()
                game.player_left.x, game.player_right.x = 360.0, 360.0 + gap
                game.ball = physics.Ball(395.0, 485.0)
                self.assert_clear(game)
                game.update(0.25, RawInput(key_downs=("x",)))
                self.assert_clear(game)

    def test_nearby_body_and_head_contacts_are_solid_at_multiple_frame_rates(self):
        for dt in (1 / 120, 1 / 60, 1 / 30, 0.1, 0.25):
            for speed in (100.0, 300.0, 850.0, config.BALL_MAX_SPEED):
                for side in (-1, 1):
                    for height in (config.BALL_RADIUS, config.HEAD_OFFSET_Y):
                        with self.subTest(dt=dt, speed=speed, side=side, height=height):
                            game = self.game()
                            radius = config.PLAYER_HALF_WIDTH if height == config.BALL_RADIUS else config.HEAD_RADIUS
                            game.ball = physics.Ball(
                                400.0 - side * (radius + config.BALL_RADIUS + 1.0),
                                config.GROUND_Y - height, vx=side * speed,
                            )
                            for _ in range(4):
                                game.update(dt, RawInput())
                                self.assert_clear(game)
                            self.assertLessEqual(
                                (game.ball.x - game.player_right.x) * side, 0,
                                "a nearby, contacted ball passed through the defender",
                            )

    def test_two_players_cannot_squeeze_the_ball_inside_either_body(self):
        game = self.game()
        game.player_left.x, game.player_right.x = 360.0, 440.0
        game.ball = physics.Ball(400.0, 485.0)
        held = RawInput(pressed_keys=frozenset({"d", "left"}))
        for _ in range(60):
            game.update(1 / 60, held)
            self.assert_clear(game)


if __name__ == "__main__":
    unittest.main()
