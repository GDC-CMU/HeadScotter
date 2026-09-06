"""Aerial play targets measured through the real solid-body world."""
import unittest

from headscotter import config, physics, players, world
from headscotter.game import Game
from headscotter.input import RawInput
from headscotter.match import MatchPhase


class AerialPlayTests(unittest.TestCase):
    def kick_arc(self, running=False, mirrored=False):
        game = Game()
        game.start_match("2P")
        game.match.phase = MatchPhase.PLAYING
        player = game.player_right if mirrored else game.player_left
        other = game.player_left if mirrored else game.player_right
        direction = -1 if mirrored else 1
        player.x = 700 if mirrored else 100
        other.x = 40 if mirrored else 760
        player.facing = direction
        game.ball = physics.Ball(player.x + direction * 35, config.GROUND_Y - config.BALL_RADIUS)
        initial_y = game.ball.y
        minimum_y = initial_y
        move_key = "left" if mirrored else "d"
        kick_key = "/" if mirrored else "x"
        for frame in range(120):
            raw = RawInput(
                pressed_keys=frozenset({move_key}) if running else frozenset(),
                key_downs=(kick_key,) if frame == 0 else (),
            )
            game.update(1 / 60, raw)
            self.assertTrue(world.is_clear(game.ball, (game.player_left, game.player_right)))
            self.assertLessEqual(game.ball.speed(), config.BALL_MAX_SPEED + 1e-5)
            minimum_y = min(minimum_y, game.ball.y)
            if frame > 0 and game.ball.vy >= 0:
                return initial_y - minimum_y
        self.fail("normal kick never completed an upward arc")

    def test_normal_kicks_loft_above_standing_heads_on_both_sides(self):
        for mirrored in (False, True):
            height = self.kick_arc(mirrored=mirrored)
            self.assertGreaterEqual(height, 110)
            self.assertLessEqual(height, 150)

    def test_running_kicks_still_create_aerial_play_under_the_speed_cap(self):
        for mirrored in (False, True):
            self.assertGreaterEqual(self.kick_arc(running=True, mirrored=mirrored), 75)

    def test_power_shot_is_faster_horizontally_and_flatter_than_the_lob(self):
        player = players.new_player(300, 1)
        normal = physics.Ball(335, config.GROUND_Y - config.BALL_RADIUS)
        power = physics.Ball(335, config.GROUND_Y - config.BALL_RADIUS)
        self.assertTrue(players.normal_kick(player, normal).fired)
        player.kick_charge = config.POWER_SHOT_CHARGE_SECONDS
        self.assertTrue(players.update_power_shot(player, power, False, 0).fired)
        self.assertGreater(power.vx, normal.vx)
        self.assertLess(abs(power.vy), abs(normal.vy))

    def test_high_rebounds_decay_and_eventually_settle(self):
        floor = config.GROUND_Y - config.BALL_RADIUS
        ball = physics.Ball(config.PITCH_CENTER_X, floor - 130)
        peaks = []
        peak = 0.0
        after_impact = False
        for _ in range(2400):
            impacts = []
            world.step_world(ball, (), 1 / 60, on_impact=impacts.append)
            if "ground" in impacts:
                if after_impact:
                    peaks.append(peak)
                after_impact, peak = True, 0.0
            if after_impact:
                peak = max(peak, floor - ball.y)
            if after_impact and ball.vy == 0 and ball.y == floor:
                break
        self.assertGreaterEqual(len(peaks), 2)
        self.assertGreaterEqual(peaks[0], 85)
        self.assertGreaterEqual(peaks[1], 65)
        self.assertTrue(all(a > b for a, b in zip(peaks, peaks[1:])))
        self.assertEqual(ball.vy, 0)
        self.assertEqual(ball.y, floor)
