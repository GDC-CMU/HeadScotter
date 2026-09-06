"""Regression guard for the ball passing through a standing player.

Two independent, previously-real bugs combined to make this possible:

1. The player had only one collider on the whole body -- a circle on
   the head (see players.apply_head_collision()). The torso and legs,
   a real ~21px vertical band a ball rolling on the ground sits well
   inside of, had no collider at all. See players.body_rect() /
   players.apply_body_collision(), the fix.

2. Even with a body collider, physics.step_ball()/the ball-vs-player
   checks are discrete overlap tests done once per real frame. At
   config.BALL_MAX_SPEED (900 px/sec) a ball moves 15px in a single
   60fps frame -- wider than either goalpost -- so a fast enough ball
   could in principle skip clean over a thin collider between two
   samples without ever registering an overlap. game.py now substeps
   the ball's per-frame movement (see config.BALL_MAX_STEP_PX) and
   re-checks every player collider at the start of every substep, which
   this module verifies end-to-end through the real per-frame game loop
   (not just the underlying pure collision functions in isolation).
"""
from __future__ import annotations

import random
import unittest

from headscotter import config
from headscotter.game import Game
from headscotter.input import RawInput


class BallNeverTunnelsThroughAStandingPlayerTests(unittest.TestCase):
    def _make_game(self):
        game = Game(rng=random.Random(1))
        game.start_match("2P")
        return game

    def _fire_and_check(self, ball_y_offset: float, speed: float):
        """Fire the ball at ``speed`` along +x at a standing, idle
        player_right from well clear on the left, at ball height
        ``ball_y_offset`` above the ground -- and confirm it is always
        deflected, never ending up on the far side of the player."""
        game = self._make_game()
        game.player_right.x = config.PITCH_CENTER_X + 150
        game.player_right.y = config.GROUND_Y
        game.player_left.x = config.PITCH_LEFT + config.PLAYER_HALF_WIDTH  # out of the way
        game.ball.x = game.player_right.x - 350
        game.ball.y = config.GROUND_Y - ball_y_offset
        game.ball.vx = speed
        game.ball.vy = 0.0
        idle = RawInput()

        far_side_x = game.player_right.x + config.PLAYER_HALF_WIDTH + config.BALL_RADIUS + 2
        max_x_reached = game.ball.x
        for _ in range(240):  # 4 seconds -- plenty even at the slowest speed tested
            game._step_gameplay(1 / 60.0, idle)
            max_x_reached = max(max_x_reached, game.ball.x)
            if game.ball.vx <= 0.0 and game.ball.x < game.player_right.x:
                break  # deflected back into play; nothing more to check
        self.assertLess(
            max_x_reached, far_side_x,
            f"speed={speed}: ball reached x={max_x_reached:.1f}, past the player at "
            f"x={game.player_right.x:.1f} -- it tunnelled through instead of colliding",
        )

    def test_never_tunnels_through_the_body_at_any_speed_up_to_max(self):
        # Ball at ground height -- squarely inside the body collider's
        # band (below the head circle), the exact scenario the original
        # bug report described: "the ball can go through the player".
        ball_y_offset = config.BALL_RADIUS
        for speed in (100.0, 300.0, 500.0, 700.0, config.BALL_MAX_SPEED):
            with self.subTest(speed=speed):
                self._fire_and_check(ball_y_offset, speed)

    def test_never_tunnels_through_the_head_at_any_speed_up_to_max(self):
        # Ball at head height.
        ball_y_offset = config.HEAD_OFFSET_Y
        for speed in (100.0, 300.0, 500.0, 700.0, config.BALL_MAX_SPEED):
            with self.subTest(speed=speed):
                self._fire_and_check(ball_y_offset, speed)

    def test_a_ball_rolling_along_the_ground_into_a_player_is_stopped(self):
        game = self._make_game()
        game.player_right.x = config.PITCH_CENTER_X + 150
        game.player_right.y = config.GROUND_Y
        game.player_left.x = config.PITCH_LEFT + config.PLAYER_HALF_WIDTH
        game.ball.x = game.player_right.x - 200
        game.ball.y = config.GROUND_Y - config.BALL_RADIUS
        game.ball.vx = 250.0
        game.ball.vy = 0.0
        idle = RawInput()

        for _ in range(180):  # 3 seconds
            game._step_gameplay(1 / 60.0, idle)
        self.assertLessEqual(game.ball.x, game.player_right.x)

    def test_a_ball_dropped_on_the_head_still_bounces_up_not_blocked(self):
        """Heading, not blocking, is the genre's actual scoring
        mechanic: a ball landing on the head must still bounce (the
        bouncier head collision), not be silently absorbed like a body
        block."""
        game = self._make_game()
        game.player_right.x = config.PITCH_CENTER_X
        game.player_right.y = config.GROUND_Y
        game.player_left.x = config.PITCH_LEFT + config.PLAYER_HALF_WIDTH
        hx, hy = game.player_right.head_center
        game.ball.x = hx
        game.ball.y = hy - config.HEAD_RADIUS - 5
        game.ball.vx = 0.0
        game.ball.vy = 250.0
        idle = RawInput()

        game._step_gameplay(1 / 60.0, idle)
        self.assertLess(game.ball.vy, 0.0)  # bounced upward, not stopped dead


if __name__ == "__main__":
    unittest.main()
