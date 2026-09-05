"""Tests for the automated goalkeeper: it tracks the ball's height,
reacts with a delay, has aim error, stays confined to its box, and
still saves/blocks the ball via passive collision."""
from __future__ import annotations

import random
import unittest

from headscotter import config, keeper
from headscotter.physics import Ball


class KeeperSetupTests(unittest.TestCase):
    def test_new_keeper_starts_centered_in_the_goal_mouth(self):
        k = keeper.new_keeper(config.PITCH_LEFT)
        expected_y = (config.CROSSBAR_Y + config.GROUND_Y) / 2.0
        self.assertAlmostEqual(k.y, expected_y)

    def test_left_keeper_stands_in_front_of_the_left_goal_line(self):
        k = keeper.new_keeper(config.PITCH_LEFT)
        self.assertGreater(k.x, config.PITCH_LEFT)
        self.assertAlmostEqual(k.x, config.PITCH_LEFT + config.KEEPER_DEPTH)

    def test_right_keeper_stands_in_front_of_the_right_goal_line(self):
        k = keeper.new_keeper(config.PITCH_RIGHT)
        self.assertLess(k.x, config.PITCH_RIGHT)
        self.assertAlmostEqual(k.x, config.PITCH_RIGHT - config.KEEPER_DEPTH)

    def test_reset_returns_to_the_ready_position(self):
        k = keeper.new_keeper(config.PITCH_LEFT)
        k.y = config.GROUND_Y  # simulate having moved
        keeper.reset_keeper(k)
        expected_y = (config.CROSSBAR_Y + config.GROUND_Y) / 2.0
        self.assertAlmostEqual(k.y, expected_y)
        self.assertAlmostEqual(k.x, config.PITCH_LEFT + config.KEEPER_DEPTH)


class KeeperTrackingTests(unittest.TestCase):
    def test_keeper_moves_toward_the_balls_height(self):
        k = keeper.new_keeper(config.PITCH_LEFT)
        start_y = k.y
        ball = Ball(x=config.PITCH_LEFT, y=config.GROUND_Y - 10)  # low shot
        rng = random.Random(1)
        for _ in range(30):  # several reaction ticks' worth
            keeper.update_keeper(k, 1 / 60.0, ball, rng)
        self.assertGreater(k.y, start_y)  # moved down, toward the low shot

    def test_keeper_never_leaves_the_goal_mouth_vertically(self):
        k = keeper.new_keeper(config.PITCH_LEFT)
        ball = Ball(x=config.PITCH_LEFT, y=config.PITCH_TOP)  # absurdly high
        rng = random.Random(2)
        for _ in range(120):
            keeper.update_keeper(k, 1 / 60.0, ball, rng)
        self.assertGreaterEqual(k.y, config.CROSSBAR_Y + config.KEEPER_RADIUS - 1e-6)
        self.assertLessEqual(k.y, config.GROUND_Y - config.KEEPER_RADIUS + 1e-6)

    def test_keeper_x_never_moves(self):
        """The keeper is a fixed-depth vertical paddle -- it never
        advances or retreats, only glides up/down."""
        k = keeper.new_keeper(config.PITCH_RIGHT)
        start_x = k.x
        ball = Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - 100)
        rng = random.Random(3)
        for _ in range(60):
            keeper.update_keeper(k, 1 / 60.0, ball, rng)
        self.assertEqual(k.x, start_x)

    def test_a_fast_height_change_can_beat_the_keeper(self):
        """A shot placed at a very different height right after the
        keeper's last perception tick, and resolved before it can glide
        there, demonstrates the keeper is not a perfect wall."""
        k = keeper.new_keeper(config.PITCH_LEFT)
        rng = random.Random(4)
        ball = Ball(x=config.PITCH_LEFT, y=config.GROUND_Y - 5)
        keeper.update_keeper(k, 0.001, ball, rng)  # perceives near the ground
        # Ball instantly teleports to the opposite end of the goal mouth.
        ball.y = config.CROSSBAR_Y + 5
        keeper.update_keeper(k, 0.001, ball, rng)  # far too little time to glide there
        self.assertGreater(abs(k.y - ball.y), config.KEEPER_RADIUS)

    def test_reaction_lag_means_known_target_does_not_snap_instantly(self):
        k = keeper.new_keeper(config.PITCH_LEFT)
        ball = Ball(x=config.PITCH_LEFT, y=config.GROUND_Y - 5)
        rng = random.Random(5)
        keeper.update_keeper(k, 0.001, ball, rng)
        target_after_first_tick = k._target_y
        ball.y = config.CROSSBAR_Y + 5
        keeper.update_keeper(k, 0.001, ball, rng)  # too soon for another perception tick
        self.assertEqual(k._target_y, target_after_first_tick)


class KeeperCollisionTests(unittest.TestCase):
    def test_keeper_blocks_a_ball_that_reaches_it(self):
        k = keeper.new_keeper(config.PITCH_LEFT)
        ball = Ball(x=k.x + config.KEEPER_RADIUS + 5, y=k.y, vx=-300.0, vy=0.0)
        saved = keeper.apply_keeper_collision(k, ball)
        self.assertTrue(saved)
        self.assertGreater(ball.vx, -300.0)  # redirected, no longer heading straight in

    def test_no_collision_when_ball_is_far_from_the_keeper(self):
        k = keeper.new_keeper(config.PITCH_LEFT)
        ball = Ball(x=config.PITCH_CENTER_X, y=k.y, vx=0.0, vy=0.0)
        saved = keeper.apply_keeper_collision(k, ball)
        self.assertFalse(saved)


if __name__ == "__main__":
    unittest.main()
