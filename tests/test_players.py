"""Tests for player movement, jumping, and kicking."""
from __future__ import annotations

import unittest

from headscotter import config, players
from headscotter.physics import Ball


class MovementTests(unittest.TestCase):
    def test_move_right_increases_x_and_sets_facing(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=-1)
        players.apply_move(player, move=1, dt=1 / 60.0)
        self.assertGreater(player.x, config.PITCH_CENTER_X)
        self.assertEqual(player.facing, 1)
        self.assertTrue(player.moving)

    def test_move_left_decreases_x_and_sets_facing(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        players.apply_move(player, move=-1, dt=1 / 60.0)
        self.assertLess(player.x, config.PITCH_CENTER_X)
        self.assertEqual(player.facing, -1)

    def test_standing_still_does_not_change_facing_or_moving(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        players.apply_move(player, move=0, dt=1 / 60.0)
        self.assertEqual(player.facing, 1)
        self.assertFalse(player.moving)

    def test_cannot_leave_the_pitch_on_the_left(self):
        player = players.new_player(config.PITCH_LEFT, facing=1)
        for _ in range(120):
            players.apply_move(player, move=-1, dt=1 / 60.0)
        self.assertGreaterEqual(player.x, config.PITCH_LEFT + config.PLAYER_HALF_WIDTH - 1e-6)

    def test_cannot_leave_the_pitch_on_the_right(self):
        player = players.new_player(config.PITCH_RIGHT, facing=-1)
        for _ in range(120):
            players.apply_move(player, move=1, dt=1 / 60.0)
        self.assertLessEqual(player.x, config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH + 1e-6)


class JumpAndGravityTests(unittest.TestCase):
    def test_jump_only_works_while_on_ground(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        players.apply_jump(player)
        self.assertFalse(player.on_ground)
        self.assertLess(player.vy, 0.0)

        vy_before_second_jump = player.vy
        players.apply_jump(player)  # already airborne -- no double jump
        self.assertEqual(player.vy, vy_before_second_jump)

    def test_gravity_returns_the_player_to_the_ground(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        players.apply_jump(player)
        for _ in range(200):
            players.step_player_physics(player, dt=1 / 60.0)
            if player.on_ground:
                break
        self.assertTrue(player.on_ground)
        self.assertEqual(player.y, config.GROUND_Y)
        self.assertEqual(player.vy, 0.0)

    def test_kick_cooldown_counts_down(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        player.kick_cooldown = config.KICK_COOLDOWN_SECONDS
        players.step_player_physics(player, dt=1 / 60.0)
        self.assertLess(player.kick_cooldown, config.KICK_COOLDOWN_SECONDS)
        self.assertGreaterEqual(player.kick_cooldown, 0.0)


class KickTests(unittest.TestCase):
    def test_kick_launches_the_ball_in_the_facing_direction(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 10, y=player.y - 40, vx=0.0, vy=0.0)
        kicked = players.try_kick(player, ball, kick_pressed=True)
        self.assertTrue(kicked)
        self.assertGreater(ball.vx, 0.0)  # launched toward facing direction (right)
        self.assertLess(ball.vy, 0.0)     # launched upward

    def test_kick_facing_left_launches_left(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=-1)
        ball = Ball(x=player.x - 10, y=player.y - 40, vx=0.0, vy=0.0)
        players.try_kick(player, ball, kick_pressed=True)
        self.assertLess(ball.vx, 0.0)

    def test_kick_out_of_range_does_nothing(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 500, y=player.y, vx=0.0, vy=0.0)
        kicked = players.try_kick(player, ball, kick_pressed=True)
        self.assertFalse(kicked)
        self.assertEqual((ball.vx, ball.vy), (0.0, 0.0))

    def test_kick_respects_cooldown(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 10, y=player.y - 40, vx=0.0, vy=0.0)
        players.try_kick(player, ball, kick_pressed=True)
        ball2 = Ball(x=player.x + 10, y=player.y - 40, vx=0.0, vy=0.0)
        kicked_again = players.try_kick(player, ball2, kick_pressed=True)
        self.assertFalse(kicked_again)

    def test_no_kick_without_the_button(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 10, y=player.y - 40, vx=0.0, vy=0.0)
        kicked = players.try_kick(player, ball, kick_pressed=False)
        self.assertFalse(kicked)


class HeadCollisionTests(unittest.TestCase):
    def test_ball_bounces_off_the_head(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        hx, hy = player.head_center
        ball = Ball(x=hx, y=hy - config.HEAD_RADIUS - 5, vx=0.0, vy=200.0)  # falling onto the head from above
        collided = players.apply_head_collision(player, ball)
        self.assertTrue(collided)
        self.assertLess(ball.vy, 0.0)

    def test_no_collision_when_ball_is_far_away(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 400, y=player.y, vx=0.0, vy=0.0)
        collided = players.apply_head_collision(player, ball)
        self.assertFalse(collided)


class NeverPermanentlyStuckTests(unittest.TestCase):
    def test_a_resting_ball_can_always_be_kicked_free(self):
        """A ball resting at (vx=0, vy=0) on the ground is never stuck:
        a deliberate kick can always move it, regardless of its current
        (possibly zero) velocity."""
        from headscotter import physics

        ball = Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - config.BALL_RADIUS, vx=0.0, vy=0.0)
        physics.step_ball(ball, dt=1 / 60.0)
        self.assertEqual((ball.vx, ball.vy), (0.0, 0.0))

        player = players.new_player(ball.x - 20, facing=1)
        kicked = players.try_kick(player, ball, kick_pressed=True)
        self.assertTrue(kicked)
        self.assertNotEqual((ball.vx, ball.vy), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
