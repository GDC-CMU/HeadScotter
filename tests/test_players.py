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


class PlayerKeeperSeparationTests(unittest.TestCase):
    """players.separate_player_from_keeper() -- one-sided: the keeper
    (a paddle pinned to its goal line) never moves, only the field
    player does."""

    def _keeper_ready_y(self) -> float:
        return (config.CROSSBAR_Y + config.GROUND_Y) / 2.0

    def test_player_approaching_from_the_pitch_side_ends_up_exactly_touching(self):
        keeper_x = config.PITCH_LEFT + config.KEEPER_DEPTH
        keeper_y = self._keeper_ready_y()
        player = players.new_player(keeper_x + 20, facing=-1)  # overlapping, from the pitch side
        player.y = keeper_y  # same height as the keeper -- full vertical overlap
        separated = players.separate_player_from_keeper(player, keeper_x, keeper_y)
        self.assertTrue(separated)
        expected_gap = config.KEEPER_RADIUS + config.PLAYER_HALF_WIDTH
        self.assertAlmostEqual(player.x - keeper_x, expected_gap, places=6)

    def test_keepers_x_is_never_changed_by_the_collision(self):
        keeper_x = config.PITCH_RIGHT - config.KEEPER_DEPTH
        keeper_y = self._keeper_ready_y()
        player = players.new_player(keeper_x - 20, facing=1)
        player.y = keeper_y
        players.separate_player_from_keeper(player, keeper_x, keeper_y)
        self.assertEqual(keeper_x, config.PITCH_RIGHT - config.KEEPER_DEPTH)

    def test_player_jumping_clear_over_the_keeper_is_untouched(self):
        keeper_x = config.PITCH_LEFT + config.KEEPER_DEPTH
        keeper_y = self._keeper_ready_y()
        player = players.new_player(keeper_x, facing=1)  # same x -- full horizontal overlap
        # Feet well above the keeper's topmost reach -- a clean lob attempt.
        player.y = keeper_y - config.KEEPER_RADIUS - config.PLAYER_HEIGHT - 5.0
        px = player.x
        separated = players.separate_player_from_keeper(player, keeper_x, keeper_y)
        self.assertFalse(separated)
        self.assertEqual(player.x, px)

    def test_non_overlapping_bodies_are_untouched(self):
        keeper_x = config.PITCH_LEFT + config.KEEPER_DEPTH
        keeper_y = self._keeper_ready_y()
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        player.y = keeper_y
        px = player.x
        separated = players.separate_player_from_keeper(player, keeper_x, keeper_y)
        self.assertFalse(separated)
        self.assertEqual(player.x, px)

    def test_player_stranded_on_the_goal_line_side_is_pushed_through_to_midfield(self):
        # Approaching from the goal-line side this time (behind the
        # keeper, between it and the goal line) -- a pocket narrower
        # than the required footprint (KEEPER_DEPTH - PLAYER_HALF_WIDTH
        # < KEEPER_RADIUS + PLAYER_HALF_WIDTH), so no resting position
        # there can ever be fully separated. Pushing further toward the
        # wall (the old, buggy behaviour) would leave the player
        # permanently short of clear; the correct resolution is to push
        # the player through to the *other* side of the keeper, toward
        # midfield, which always has room.
        keeper_x = config.PITCH_RIGHT - config.KEEPER_DEPTH
        keeper_y = self._keeper_ready_y()
        player = players.new_player(keeper_x + 10, facing=-1)
        player.y = keeper_y
        separated = players.separate_player_from_keeper(player, keeper_x, keeper_y)
        self.assertTrue(separated)
        expected_gap = config.KEEPER_RADIUS + config.PLAYER_HALF_WIDTH
        # Fully separated now, on the midfield (negative-x) side.
        self.assertAlmostEqual(keeper_x - player.x, expected_gap, places=6)
        self.assertGreaterEqual(player.x, config.PITCH_LEFT + config.PLAYER_HALF_WIDTH - 1e-6)
        self.assertLessEqual(player.x, config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH + 1e-6)

    def test_player_stays_within_pitch_bounds_when_pushed_from_near_a_wall(self):
        # Even from right against the far wall, the fix must never place
        # the player outside the legal pitch range -- whichever side it
        # ends up pushed toward.
        keeper_x = config.PITCH_LEFT + config.KEEPER_DEPTH
        keeper_y = self._keeper_ready_y()
        player = players.new_player(config.PITCH_LEFT + config.PLAYER_HALF_WIDTH, facing=1)
        player.y = keeper_y
        players.separate_player_from_keeper(player, keeper_x, keeper_y)
        self.assertGreaterEqual(player.x, config.PITCH_LEFT + config.PLAYER_HALF_WIDTH - 1e-6)
        self.assertLessEqual(player.x, config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH + 1e-6)

    def test_player_stranded_beside_the_left_keeper_is_also_pushed_through_to_midfield(self):
        # Mirror of the right-keeper pocket case: a player wedged between
        # the left keeper and the left wall must be pushed through to
        # the positive-x (midfield) side, not further into the wall.
        keeper_x = config.PITCH_LEFT + config.KEEPER_DEPTH
        keeper_y = self._keeper_ready_y()
        player = players.new_player(keeper_x - 10, facing=1)
        player.y = keeper_y
        separated = players.separate_player_from_keeper(player, keeper_x, keeper_y)
        self.assertTrue(separated)
        expected_gap = config.KEEPER_RADIUS + config.PLAYER_HALF_WIDTH
        self.assertAlmostEqual(player.x - keeper_x, expected_gap, places=6)
        self.assertGreaterEqual(player.x, config.PITCH_LEFT + config.PLAYER_HALF_WIDTH - 1e-6)
        self.assertLessEqual(player.x, config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH + 1e-6)


class PlayerKeeperSeparationLongRunRegressionTests(unittest.TestCase):
    """Regression check for the actual bug report: player-vs-keeper
    overlap measured over a long real-game simulation, using the same
    box-vs-circle geometry as separate_player_from_keeper itself (not
    the cruder same-height-box proxy used for player-vs-player, which
    previously produced a false "fixed" reading here). Runs the real
    Game update loop -- including movement, the field-field separation,
    keeper tracking, and this fix all together -- rather than calling
    the pure function in isolation, so it also catches ordering bugs in
    game.py, not just bugs in the function itself.

    Before this fix: 17.0% of checked frames overlapped, minimum gap
    0.2px, concentrated entirely in the goal-line-side pocket that is
    structurally narrower than the required footprint. After: 0
    overlapping frames, minimum gap the full required 62.0px.
    """

    def test_240_second_demo_simulation_never_overlaps_a_keeper(self):
        import os
        import random

        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame

        from headscotter import config
        from headscotter.game import Game
        from headscotter.input import RawInput

        pygame.init()
        pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))

        game = Game(rng=random.Random(20260115))
        game._enter_demo()
        idle = RawInput()

        required_gap = config.KEEPER_RADIUS + config.PLAYER_HALF_WIDTH
        min_gap = float("inf")
        overlap_frames = 0
        checked_pairs = 0
        for _ in range(240 * 60):  # 240 simulated seconds at 60Hz
            game.update(1 / 60.0, idle)
            for keeper in (game.keeper_left, game.keeper_right):
                for player in (game.player_left, game.player_right):
                    dx = abs(player.x - keeper.x)
                    player_top = player.y - config.PLAYER_HEIGHT
                    player_bottom = player.y
                    keeper_top = keeper.y - config.KEEPER_RADIUS
                    keeper_bottom = keeper.y + config.KEEPER_RADIUS
                    vertically_overlapping = not (
                        player_bottom <= keeper_top or keeper_bottom <= player_top
                    )
                    if not vertically_overlapping:
                        continue
                    checked_pairs += 1
                    min_gap = min(min_gap, dx)
                    if dx < required_gap - 1e-6:
                        overlap_frames += 1

        self.assertGreater(checked_pairs, 0, "the demo never brought a player near a keeper at all")
        self.assertEqual(
            overlap_frames, 0,
            f"{overlap_frames}/{checked_pairs} vertically-overlapping player/keeper pairs "
            f"were closer than the required {required_gap}px -- keeper separation regressed",
        )
        self.assertAlmostEqual(min_gap, required_gap, places=2)


if __name__ == "__main__":
    unittest.main()
