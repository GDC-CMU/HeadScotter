"""Live rendered-state solidity, motion transfer and constrained contacts.

The former 200/350px-away rolling fixtures could stop through friction without
ever reaching a player. These start at real contact distance, advance PLAYING,
and inspect every returned frame. Parent-owned test_world_contacts.py is
independent and unchanged.
"""
from __future__ import annotations

import math
import random
import unittest
from unittest.mock import patch

from headscotter import config, physics, players
from headscotter.game import Game, GameState
from headscotter.input import RawInput
from headscotter.match import MatchPhase


def live_game():
    game = Game(rng=random.Random(4))
    game.start_match("2P")
    game.match.phase = MatchPhase.PLAYING
    game.player_left.x, game.player_right.x = 100.0, 400.0
    return game


def assert_clear(test, game):
    ball = game.ball
    for player in (game.player_left, game.player_right):
        test.assertGreaterEqual(math.dist(ball.pos, player.head_center),
                                config.HEAD_RADIUS + ball.radius - 1e-4)
        left, top, right, bottom = players.body_rect(player)
        nearest = (physics.clamp(ball.x, left, right), physics.clamp(ball.y, top, bottom))
        test.assertGreaterEqual(math.dist(ball.pos, nearest), ball.radius - 1e-4)
    test.assertLessEqual(ball.y + ball.radius, config.GROUND_Y + 1e-4)
    test.assertLessEqual(ball.speed(), config.BALL_MAX_SPEED + 1e-4)
    test.assertTrue(all(math.isfinite(v) for v in (ball.x, ball.y, ball.vx, ball.vy)))


class NearbyCollisionTests(unittest.TestCase):
    def test_nearby_contacts_really_rebound_before_render(self):
        for offset, collider in ((config.BALL_RADIUS, config.PLAYER_HALF_WIDTH),
                                 (config.HEAD_OFFSET_Y, config.HEAD_RADIUS)):
            for speed in (100, 300, 500, 900):
                for direction in (-1, 1):
                    with self.subTest(offset=offset, speed=speed, direction=direction):
                        game = live_game()
                        game.ball = physics.Ball(
                            400 - direction * (collider + config.BALL_RADIUS + 1),
                            config.GROUND_Y - offset, direction * speed,
                        )
                        contacted = False
                        for _ in range(8):
                            game.update(1 / 120, RawInput())
                            assert_clear(self, game)
                            if game.ball.vx * direction < 0:
                                contacted = True
                                break
                        self.assertTrue(contacted, "friction/staying far away is not collision evidence")
                        self.assertLess(game.match.time_remaining, config.MATCH_SECONDS)

    def test_real_drop_from_rest_rebounds_during_a_stalled_frame(self):
        game = live_game()
        game.ball = physics.Ball(400, 370)
        with patch.object(game.feedback, "impact", wraps=game.feedback.impact) as impact:
            game.update(0.25, RawInput())
        assert_clear(self, game)
        self.assertLess(game.ball.vy, 0)
        self.assertEqual(sum(c.args[1].startswith("head:") for c in impact.call_args_list), 1)

    def test_a_running_player_pushes_and_does_not_cross_a_resting_ball(self):
        for mirror in (False, True):
            game = live_game()
            game.player_left.x, game.player_right.x = (480, 100) if mirror else (320, 700)
            direction = -1 if mirror else 1
            game.ball = physics.Ball(game.player_left.x + direction * 35, 485)
            for dt in (1 / 120, 0.1, 0.25, 1 / 60):
                game.update(dt, RawInput(pressed_keys=frozenset({"a" if mirror else "d"})))
                assert_clear(self, game)
                self.assertGreaterEqual((game.ball.x - game.player_left.x) * direction, 35 - 1e-4)
                self.assertGreater(game.ball.vx * direction, 100)

    def test_normal_and_power_rebounds_do_not_get_kicker_immunity(self):
        for power in (False, True):
            for dt in (1 / 120, 1 / 60, 0.1, 0.25):
                for gap in (70, 75, 80, 90):
                    game = live_game()
                    game.player_left.x, game.player_right.x = 360, 360 + gap
                    game.ball = physics.Ball(395, 485)
                    assert_clear(self, game)
                    if power:
                        game.player_left.kick_charge = config.POWER_SHOT_CHARGE_SECONDS
                    raw = RawInput() if power else RawInput(key_downs=("x",))
                    game.update(dt, raw)
                    assert_clear(self, game)
                    for _ in range(4):
                        game.update(1 / 60, RawInput())
                        assert_clear(self, game)


class ConstrainedContactTests(unittest.TestCase):
    def test_separating_gravity_motion_is_not_frozen_by_another_support(self):
        game = live_game()
        game.player_left.x, game.player_left.y = 402.3333333333339, 499.92490214133386
        game.player_right.x, game.player_right.y = 480.00000000000153, 448.85766140874745
        game.player_left.on_ground = game.player_right.on_ground = False
        game.ball = physics.Ball(445.0126976393284, 427.24059729027556)
        assert_clear(self, game)
        for _ in range(4):
            game.update(1 / 120, RawInput())
            assert_clear(self, game)
        self.assertAlmostEqual(game.player_left.y, config.GROUND_Y, places=5)
        self.assertTrue(game.player_left.on_ground)

    def test_blocked_motion_propagates_through_connected_player_contacts(self):
        game = live_game()
        for player, x in ((game.player_left, 62), (game.player_right, 102)):
            player.x, player.y, player.vy, player.on_ground = x, 333, 0, False
        game.ball = physics.Ball(15, 280)
        assert_clear(self, game)
        for _ in range(30):
            before = game.ball.pos
            game.update(1 / 60, RawInput(pressed_keys=frozenset({"a", "left"})))
            assert_clear(self, game)
            self.assertLessEqual(math.dist(before, game.ball.pos), config.BALL_MAX_SPEED / 60 + 1e-3)

    def test_goal_post_underside_is_a_real_rounded_contact_not_a_motion_gate(self):
        for mirror in (False, True):
            game = live_game()
            game.ball = physics.Ball(795 if mirror else 5, 316, 0, -200)
            with patch.object(game.feedback, "impact", wraps=game.feedback.impact) as impact:
                for _ in range(6):
                    game.update(1 / 120, RawInput())
                    assert_clear(self, game)
                    # Independent distance to the nominal solid post corner.
                    dx = 800 - game.ball.x if mirror else game.ball.x
                    dy = game.ball.y - config.CROSSBAR_Y
                    self.assertGreaterEqual(math.hypot(max(0, dx), max(0, dy)), game.ball.radius - 1e-4)
            self.assertGreater(game.ball.vy, 0, "an upward contact must bounce, not park with upward velocity")
            self.assertEqual(impact.call_count, 1)

    def test_landing_does_not_shove_a_grounded_player_through_the_ball(self):
        game = live_game()
        game.player_left.x, game.player_left.y = 668.4343303736207, 412.5
        game.player_left.vy, game.player_left.on_ground = 480, False
        game.player_right.x = 681.8990029597103
        game.ball = physics.Ball(717.0875269501762, 483.7262711348161, 282.5283358905544, -34.69915460735489)
        assert_clear(self, game)
        dt = 0.007712149720091125
        start_x = game.player_right.x
        game.update(dt, RawInput(pressed_keys=frozenset({"right"})))
        assert_clear(self, game)
        self.assertAlmostEqual(game.player_right.x, start_x + config.PLAYER_SPEED * dt, places=5)
        self.assertGreaterEqual(game.player_right.y - game.player_left.y, config.PLAYER_HEIGHT)
        for _ in range(30):
            game.update(1 / 120, RawInput(pressed_keys=frozenset({"right"})))
            assert_clear(self, game)

    def test_player_can_walk_off_a_pinned_ground_ball(self):
        game = live_game()
        game.player_left.x, game.player_right.x = 360, 400
        game.player_right.y = 470
        game.ball = physics.Ball(395, 485)
        assert_clear(self, game)
        for _ in range(30):
            game.update(1 / 120, RawInput(pressed_keys=frozenset({"right"})))
            assert_clear(self, game)
        self.assertGreater(game.player_right.x, 460, "blocked fall must not cancel free sideways movement")

    def test_floor_and_supported_foot_allow_real_tangential_ball_motion(self):
        game = live_game()
        game.player_left.x, game.player_right.x = 400, 700
        game.player_left.y = 470
        game.ball = physics.Ball(400, 485, vx=300)
        assert_clear(self, game)
        for _ in range(12):
            game.update(1 / 120, RawInput())
            assert_clear(self, game)
        self.assertGreater(game.ball.x, 420, "nonzero velocity must not be parked under a foot")

    def test_airborne_ball_is_not_a_new_ground_jump_platform(self):
        game = live_game()
        game.player_left.x, game.player_right.x = 400, 700
        game.player_left.y = 300
        game.player_left.vy = 1000  # stress capped ball support under a fast fall
        game.player_left.on_ground = False
        game.ball = physics.Ball(400, 315)
        assert_clear(self, game)
        game.update(1 / 120, RawInput())
        assert_clear(self, game)
        self.assertLess(game.ball.y + game.ball.radius, config.GROUND_Y)
        self.assertFalse(game.player_left.on_ground)

    def test_floor_squeeze_blocks_closing_motion_but_reverse_input_still_works(self):
        game = live_game()
        game.player_left.x, game.player_right.x = 360, 440
        game.ball = physics.Ball(400, 485)
        held = RawInput(pressed_keys=frozenset({"d", "left"}))
        for _ in range(60):
            game.update(1 / 60, held)
            assert_clear(self, game)
            self.assertAlmostEqual(game.ball.x, 400, delta=1e-3)
            self.assertAlmostEqual(game.ball.y, 485, delta=1e-3)
        self.assertGreaterEqual(game.player_right.x - game.player_left.x, 70 - 1e-4)
        blocked_x = game.player_left.x
        game.update(0.1, RawInput(pressed_keys=frozenset({"a"})))
        assert_clear(self, game)
        self.assertLess(game.player_left.x, blocked_x - 20)

    def test_head_squeeze_never_relocates_the_ball_outside_its_motion_budget(self):
        game = live_game()
        game.player_left.x, game.player_right.x = 340, 460
        game.ball = physics.Ball(400, 447)
        assert_clear(self, game)
        for dt in (1 / 120, 0.1, 1 / 60, 0.25) * 8:
            before = game.ball.pos
            game.update(dt, RawInput(pressed_keys=frozenset({"d", "left"})))
            assert_clear(self, game)
            self.assertLessEqual(math.dist(before, game.ball.pos), config.BALL_MAX_SPEED * dt + 1e-3)

    def test_rising_head_next_to_solid_post_resolves_wall_and_head_together(self):
        for mirror in (False, True):
            game = live_game()
            game.player_right.x = 400
            game.player_left.x = 780 if mirror else 20
            game.player_left.y = 380
            game.player_left.vy = -200
            game.player_left.on_ground = False
            game.ball = physics.Ball(785 if mirror else 15, 280)
            assert_clear(self, game)
            for dt in (1 / 120, 0.1, 0.25, 1 / 60):
                game.update(dt, RawInput())
                assert_clear(self, game)
                if game.ball.y + game.ball.radius <= config.CROSSBAR_Y:
                    self.assertGreaterEqual(game.ball.x, 15 - 1e-4)
                    self.assertLessEqual(game.ball.x, 785 + 1e-4)

    def test_both_jumping_heads_keep_a_valid_ball_outside_both_bodies(self):
        game = live_game()
        game.player_left.x, game.player_right.x = 365, 435
        game.ball = physics.Ball(400, 400)
        assert_clear(self, game)
        game.update(0.25, RawInput(pressed_keys=frozenset({"w", "up"})))
        assert_clear(self, game)
        for _ in range(60):
            game.update(1 / 60, RawInput())
            assert_clear(self, game)


class FrameSequenceTests(unittest.TestCase):
    def test_free_fall_and_jump_agree_across_frame_partitions(self):
        results = []
        for sequence in ([0.25], [1 / 60] * 15, [1 / 120] * 30, [0.1, 0.1, 0.05]):
            game = live_game()
            game.player_right.x = 700
            game.ball = physics.Ball(400, 250, 0, -100)
            for i, dt in enumerate(sequence):
                game.update(dt, RawInput(pressed_keys=frozenset({"w", "d"} if i == 0 else {"d"})))
                assert_clear(self, game)
            results.append((game.ball.y, game.ball.vy, game.player_left.x, game.player_left.y, game.player_left.vy))
        for result in results[1:]:
            for a, b in zip(result, results[0]):
                self.assertAlmostEqual(a, b, places=6)

    def test_edges_charge_and_jump_are_not_multiplied_by_substeps(self):
        game = live_game()
        game.player_right.x = 700
        with patch("headscotter.players.normal_kick", wraps=players.normal_kick) as kick:
            game.update(0.25, RawInput(key_downs=("x", "x"), pressed_keys=frozenset({"c"})))
            self.assertEqual(kick.call_count, 2)
        self.assertAlmostEqual(game.player_left.kick_charge, 0.25)
        game.update(1.0, RawInput(pressed_keys=frozenset({"w"})))
        self.assertTrue(game.player_left.on_ground, "held jump repeated inside one input update")

    def test_variable_live_sequences_preserve_solid_rendered_states(self):
        for seed in range(4):
            rng = random.Random(seed)
            game = live_game()
            live_frames = 0
            for _ in range(160):
                if game.state is not GameState.MATCH:
                    game = live_game()
                raw = RawInput(pressed_keys=frozenset(
                    key for key in ("a", "d", "w", "x", "c", "left", "right", "up", "/", "right shift")
                    if rng.random() < 0.2
                ))
                if game.match.phase is MatchPhase.PLAYING:
                    live_frames += 1
                game.update(rng.choice((1 / 120, 1 / 60, 1 / 30, 0.1, 0.25)), raw)
                assert_clear(self, game)
            self.assertGreater(live_frames, 60)


if __name__ == "__main__":
    unittest.main()
