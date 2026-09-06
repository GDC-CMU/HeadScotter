"""Tests for player movement, jumping, and kicking."""
from __future__ import annotations

import math
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
    """Normal press attempts and separate power-shot holds/releases."""

    DT = 1 / 60.0

    def _tap_kick(self, player, ball):
        return players.normal_kick(player, ball)

    def test_kick_launches_the_ball_in_the_facing_direction(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 10, y=player.y - 40, vx=0.0, vy=0.0)
        result = self._tap_kick(player, ball)
        self.assertTrue(result.fired)
        self.assertFalse(result.is_power_shot)
        self.assertGreater(ball.vx, 0.0)  # launched toward facing direction (right)
        self.assertLess(ball.vy, 0.0)     # launched upward

    def test_kick_facing_left_launches_left(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=-1)
        ball = Ball(x=player.x - 10, y=player.y - 40, vx=0.0, vy=0.0)
        self._tap_kick(player, ball)
        self.assertLess(ball.vx, 0.0)

    def test_kick_out_of_range_does_nothing(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 500, y=player.y, vx=0.0, vy=0.0)
        result = self._tap_kick(player, ball)
        self.assertFalse(result.fired)
        self.assertEqual((ball.vx, ball.vy), (0.0, 0.0))
        self.assertTrue(player.just_kicked)

    def test_normal_kicks_repeat_without_waiting_for_power_recovery(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 10, y=player.y - 40, vx=0.0, vy=0.0)
        self._tap_kick(player, ball)
        player.kick_cooldown = 0.9
        ball2 = Ball(x=player.x + 10, y=player.y - 40, vx=0.0, vy=0.0)
        result_again = self._tap_kick(player, ball2)
        self.assertTrue(result_again.fired)
        self.assertEqual(player.kick_cooldown, 0.9)

    def test_no_kick_without_the_button(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 10, y=player.y - 40, vx=0.0, vy=0.0)
        result = players.update_power_shot(player, ball, power_held=False, dt=self.DT)
        self.assertFalse(result.fired)

    def test_holding_the_button_charges_but_does_not_fire(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 10, y=player.y - 40, vx=0.0, vy=0.0)
        for _ in range(10):
            result = players.update_power_shot(player, ball, power_held=True, dt=self.DT)
            self.assertFalse(result.fired)
        self.assertGreater(player.kick_charge, 0.0)
        self.assertEqual((ball.vx, ball.vy), (0.0, 0.0))  # untouched while still held

    def test_a_full_charge_fires_a_meaningfully_stronger_power_shot(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 10, y=player.y - 40, vx=0.0, vy=0.0)
        steps = int(config.POWER_SHOT_CHARGE_SECONDS / self.DT) + 2
        for _ in range(steps):
            players.update_power_shot(player, ball, power_held=True, dt=self.DT)
        result = players.update_power_shot(player, ball, power_held=False, dt=self.DT)
        self.assertTrue(result.fired)
        self.assertTrue(result.is_power_shot)
        speed = math.hypot(ball.vx, ball.vy)
        self.assertGreater(speed, config.KICK_IMPULSE_SPEED)
        self.assertAlmostEqual(speed, config.POWER_SHOT_IMPULSE_SPEED, delta=1.0)
        # A power shot costs more cooldown than an ordinary kick.
        self.assertGreater(player.kick_cooldown, config.KICK_COOLDOWN_SECONDS)

    def test_charge_resets_on_release_even_if_nothing_fires(self):
        """Charging with no ball in range is harmless -- releasing just
        resets the charge instead of firing anything."""
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 500, y=player.y, vx=0.0, vy=0.0)
        for _ in range(10):
            players.update_power_shot(player, ball, power_held=True, dt=self.DT)
        result = players.update_power_shot(player, ball, power_held=False, dt=self.DT)
        self.assertFalse(result.fired)
        self.assertEqual(player.kick_charge, 0.0)

    def test_power_recovery_blocks_power_but_not_normal_or_charge_state(self):
        player = players.new_player(400, facing=1)
        ball = Ball(420, player.y - 40)
        players.update_power_shot(player, ball, True, config.POWER_SHOT_CHARGE_SECONDS)
        self.assertTrue(players.update_power_shot(player, ball, False, self.DT).is_power_shot)
        recovery = player.kick_cooldown
        for _ in range(5):
            self.assertTrue(players.normal_kick(player, ball).fired)
            self.assertFalse(players.update_power_shot(player, ball, True, self.DT).fired)
        self.assertEqual(player.kick_charge, 0.0)
        self.assertEqual(player.kick_cooldown, recovery)
        self.assertLessEqual(ball.speed(), config.BALL_MAX_SPEED)


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


class BodyCollisionTests(unittest.TestCase):
    """players.apply_body_collision() -- the fix for the ball passing
    straight through a standing player's torso/legs, which previously
    had no collider at all (only the head circle did)."""

    def test_body_rect_spans_from_head_bottom_to_the_feet(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        left, top, right, bottom = players.body_rect(player)
        self.assertAlmostEqual(left, player.x - config.PLAYER_HALF_WIDTH)
        self.assertAlmostEqual(right, player.x + config.PLAYER_HALF_WIDTH)
        self.assertAlmostEqual(bottom, player.y)
        expected_top = player.y - (config.HEAD_OFFSET_Y - config.HEAD_RADIUS)
        self.assertAlmostEqual(top, expected_top)

    def test_a_ball_rolling_along_the_ground_into_a_player_is_blocked(self):
        """This is the exact previously-broken scenario: a ball at
        ground height (well below the head circle) rolling horizontally
        into a standing player must not pass through them."""
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x - 200, y=config.GROUND_Y - config.BALL_RADIUS, vx=400.0, vy=0.0)
        for _ in range(180):  # 3 seconds at 60fps -- plenty to reach and pass the player if unblocked
            collided = players.apply_body_collision(player, ball)
            if collided:
                break
            ball.x += ball.vx * (1 / 60.0)
        self.assertLessEqual(ball.x, player.x)  # never made it to/past the player's centre
        self.assertLessEqual(ball.vx, 0.0)  # horizontal momentum was killed, not preserved

    def test_no_collision_when_ball_is_far_from_the_body(self):
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 400, y=config.GROUND_Y - config.BALL_RADIUS, vx=0.0, vy=0.0)
        collided = players.apply_body_collision(player, ball)
        self.assertFalse(collided)

    def test_a_ball_dropped_on_the_head_still_bounces_not_blocked(self):
        """Heading, not blocking, is the genre's actual scoring
        mechanic -- a ball landing on the head must still be resolved
        by the bouncier head collision, not swallowed by the body block."""
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        hx, hy = player.head_center
        ball = Ball(x=hx, y=hy - config.HEAD_RADIUS - 5, vx=0.0, vy=200.0)
        head_hit = players.apply_head_collision(player, ball)
        body_hit = players.apply_body_collision(player, ball)
        self.assertTrue(head_hit)
        self.assertFalse(body_hit)  # the same ball must not also be caught by the body
        self.assertLess(ball.vy, 0.0)  # bounced, not just stopped


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
        result = players.normal_kick(player, ball)
        self.assertTrue(result.fired)
        self.assertNotEqual((ball.vx, ball.vy), (0.0, 0.0))


class PlayerSeparationTests(unittest.TestCase):
    """players.separate_players() -- the two bodies must never
    interpenetrate, but a jumping player passing over the other's head
    (no vertical overlap) is a legitimate move and must be left alone."""

    def test_bodies_approaching_from_each_side_end_up_exactly_touching(self):
        a = players.new_player(config.PITCH_CENTER_X - 10, facing=1)
        b = players.new_player(config.PITCH_CENTER_X + 10, facing=-1)  # overlapping by 40px
        separated = players.separate_players(a, b)
        self.assertTrue(separated)
        self.assertAlmostEqual(b.x - a.x, config.PLAYER_HALF_WIDTH * 2.0, places=6)

    def test_separation_is_symmetric_in_the_open_pitch(self):
        start_a, start_b = config.PITCH_CENTER_X - 10, config.PITCH_CENTER_X + 10
        a = players.new_player(start_a, facing=1)
        b = players.new_player(start_b, facing=-1)
        players.separate_players(a, b)
        # Overlap = footprint(60) - separation(20) = 40; each player
        # takes half (20px) of it, away from the other, symmetrically.
        overlap = config.PLAYER_HALF_WIDTH * 2.0 - (start_b - start_a)
        self.assertAlmostEqual(start_a - a.x, overlap / 2.0, places=6)
        self.assertAlmostEqual(b.x - start_b, overlap / 2.0, places=6)

    def test_overlapping_players_are_pushed_apart_regardless_of_order(self):
        # b to a's left this time -- the push directions must flip accordingly.
        a = players.new_player(config.PITCH_CENTER_X + 10, facing=-1)
        b = players.new_player(config.PITCH_CENTER_X - 10, facing=1)
        players.separate_players(a, b)
        self.assertAlmostEqual(a.x - b.x, config.PLAYER_HALF_WIDTH * 2.0, places=6)

    def test_player_against_the_left_wall_is_not_pushed_out_of_bounds(self):
        wall_x = config.PITCH_LEFT + config.PLAYER_HALF_WIDTH
        a = players.new_player(wall_x, facing=1)  # already pinned at the left edge
        b = players.new_player(wall_x + 20, facing=-1)  # overlapping by 40px
        separated = players.separate_players(a, b)
        self.assertTrue(separated)
        self.assertEqual(a.x, wall_x)  # could not move further left -- stayed put
        # b absorbed the *entire* separation instead of just half.
        self.assertAlmostEqual(b.x - a.x, config.PLAYER_HALF_WIDTH * 2.0, places=6)
        self.assertGreaterEqual(a.x, config.PITCH_LEFT + config.PLAYER_HALF_WIDTH - 1e-6)

    def test_player_against_the_right_wall_is_not_pushed_out_of_bounds(self):
        wall_x = config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH
        b = players.new_player(wall_x, facing=-1)  # already pinned at the right edge
        a = players.new_player(wall_x - 20, facing=1)  # overlapping by 40px
        players.separate_players(a, b)
        self.assertEqual(b.x, wall_x)
        self.assertAlmostEqual(b.x - a.x, config.PLAYER_HALF_WIDTH * 2.0, places=6)
        self.assertLessEqual(b.x, config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH + 1e-6)

    def test_non_overlapping_players_are_left_completely_untouched(self):
        a = players.new_player(config.PITCH_CENTER_X - 200, facing=1)
        b = players.new_player(config.PITCH_CENTER_X + 200, facing=-1)
        ax, bx = a.x, b.x
        separated = players.separate_players(a, b)
        self.assertFalse(separated)
        self.assertEqual(a.x, ax)
        self.assertEqual(b.x, bx)

    def test_players_touching_but_not_overlapping_are_untouched(self):
        # Exactly at the footprint boundary -- not yet overlapping.
        a = players.new_player(config.PITCH_CENTER_X, facing=1)
        b = players.new_player(config.PITCH_CENTER_X + config.PLAYER_HALF_WIDTH * 2.0, facing=-1)
        separated = players.separate_players(a, b)
        self.assertFalse(separated)

    def test_a_jumping_player_passing_over_the_other_is_not_separated(self):
        """Vertical overlap is required too: a player whose feet have
        cleared the other's head height is legitimately jumping over
        them (e.g. contesting a header), not colliding -- this must not
        be blocked just because their horizontal footprints overlap."""
        a = players.new_player(config.PITCH_CENTER_X, facing=1)  # standing on the ground
        b = players.new_player(config.PITCH_CENTER_X, facing=-1)  # same x -- full horizontal overlap
        b.y = config.GROUND_Y - config.PLAYER_HEIGHT - 5.0  # airborne, clear above a's head
        ax, bx = a.x, b.x
        separated = players.separate_players(a, b)
        self.assertFalse(separated)
        self.assertEqual(a.x, ax)
        self.assertEqual(b.x, bx)

    def test_a_low_jump_that_still_overlaps_vertically_is_still_separated(self):
        a = players.new_player(config.PITCH_CENTER_X - 10, facing=1)
        b = players.new_player(config.PITCH_CENTER_X + 10, facing=-1)
        b.y = config.GROUND_Y - 20.0  # a small hop -- well within PLAYER_HEIGHT of a's feet
        separated = players.separate_players(a, b)
        self.assertTrue(separated)


if __name__ == "__main__":
    unittest.main()
