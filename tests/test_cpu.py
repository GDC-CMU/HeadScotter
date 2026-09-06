"""Delayed, fair CPU decisions and decisive live head-soccer scenarios.

Old "stop on the ball"/"jump merely because overhead" assertions have been
replaced by useful-side setup and actual airborne contacts. Scenario results
come from Game.update in PLAYING, including the real two-body/ball collisions.
"""
from __future__ import annotations

import copy
import math
import random
import unittest
from collections import Counter
from unittest.mock import patch

from headscotter import config, physics, players
from headscotter.cpu import CPUController
from headscotter.game import Game
from headscotter.input import RawInput
from headscotter.match import MatchPhase
from headscotter.physics import Ball
from headscotter.players import new_player


# Canonical right-hand CPU; the same fixtures are mirrored for the left.
# CPU x, opponent x, ball x/y/vx/vy, budget in live frames.
SCENARIOS = {
    "pursuit": (640, 120, 350, 380, -160, 0, 90),
    "blocker": (620, 450, 260, 485, 0, 0, 180),
    "jumping_blocker": (540, 450, 260, 485, 0, 0, 180),
    # A clear incoming header, not the old grazing trajectory whose later
    # overlap was treated as a hit by static-collider response.
    "header": (600, 150, 570, 330, 0, 100, 60),
    "defend": (690, 120, 500, 465, 600, 0, 60),
    "recover_ball": (300, 680, 400, 485, 0, 0, 240),
    # Solidity changes rallies: score within the actual regulation clock,
    # not a 30s golden bound measured with whole-frame kicker immunity.
    "passive": (610, 190, 400, 485, 0, 0, int(config.MATCH_SECONDS * config.FPS)),
}


def run_scenario(name: str, *, mirror=False, seed=8):
    """Reusable measurements for tests/handoff; no high-score or artifact writes."""
    cx, ox, bx, by, vx, vy, budget = SCENARIOS[name]
    game = Game(rng=random.Random(seed))
    game.start_match("2P")  # never writes a 1P record
    game.match.phase = MatchPhase.PLAYING
    bot = game.player_left if mirror else game.player_right
    opponent = game.player_right if mirror else game.player_left
    controller = CPUController(rng=game.rng, defend_x=config.PITCH_LEFT if mirror else config.PITCH_RIGHT)
    if mirror:
        game.cpu_left = controller
    else:
        game.cpu_right = controller
    game._priority_swap = mirror  # mirror the existing tie-resolution order too
    reflect = lambda x: config.PITCH_LEFT + config.PITCH_RIGHT - x if mirror else x
    bot.x, opponent.x = reflect(cx), reflect(ox)
    game.ball = Ball(reflect(bx), by, -vx if mirror else vx, vy)
    if name == "jumping_blocker":
        players.apply_jump(opponent)

    attack = controller.attack_direction
    counts, first = Counter(), {}
    needs_crossing = (bot.x - opponent.x) * attack <= 0
    needs_midfield = (bot.x - config.PITCH_CENTER_X) * attack <= 0
    crossing_clearance = None
    max_height = 0.0
    frame = 0
    original_contact = game._on_contact
    original_kick = players.normal_kick
    original_power = players.update_power_shot

    def contact(surface):
        # World emits only final, real contact episodes. Its copied forecasts
        # have no callback; don't count geometric candidate/solver probes.
        if surface == f"head:{bot.sprite_key}":
            counts["headers"] += 1
            first.setdefault("header", frame)
            if not bot.on_ground:
                counts["air_headers"] += 1
            if game.ball.vx * attack > 0:
                counts["forward_headers"] += 1
        original_contact(surface)

    def kick(player, ball):
        result = original_kick(player, ball)
        if player is bot and result.fired:
            counts["normal_shots"] += 1
            first.setdefault("shot", frame)
            assert ball.vx * attack > 0, "CPU normal shot points at its own goal"
        return result

    def power(player, ball, held, dt):
        result = original_power(player, ball, held, dt)
        if player is bot and result.fired:
            counts["power_shots"] += 1
            first.setdefault("shot", frame)
            assert ball.vx * attack > 0, "CPU power release points at its own goal"
        return result

    with patch.object(game, "_on_contact", new=contact), \
            patch("headscotter.players.normal_kick", new=kick), \
            patch("headscotter.players.update_power_shot", new=power):
        for frame in range(1, budget + 1):
            old_x, old_opp_x, grounded = bot.x, opponent.x, bot.on_ground
            game.update(1 / 60, RawInput())
            if grounded and not bot.on_ground:
                counts["jumps"] += 1
                first.setdefault("jump", frame)
            if not grounded and bot.on_ground:
                first.setdefault("landing", frame)
            if needs_midfield and (bot.x - config.PITCH_CENTER_X) * attack > 0:
                first.setdefault("midfield", frame)
            if needs_crossing and crossing_clearance is None and (bot.x - opponent.x) * attack > 0:
                first["cross"] = frame
                crossing_clearance = abs(bot.y - opponent.y)
            if abs(bot.x - opponent.x) < 2 * config.PLAYER_HALF_WIDTH - 1e-6:
                assert abs(bot.y - opponent.y) >= config.PLAYER_HEIGHT, "interpenetrating bodies"
            if (abs(old_x - old_opp_x) >= 2 * config.PLAYER_HALF_WIDTH
                    and abs(bot.x - opponent.x) > 2 * config.PLAYER_HALF_WIDTH + 1e-6):
                assert abs(bot.x - old_x) <= config.PLAYER_SPEED / 60 + 1e-6, "nonphysical movement"
            assert all(math.isfinite(value) for value in
                       (bot.x, bot.y, bot.vy, opponent.x, opponent.y, game.ball.x,
                        game.ball.y, game.ball.vx, game.ball.vy))
            assert game.ball.speed() <= config.BALL_MAX_SPEED + 1e-6
            max_height = max(max_height, config.GROUND_Y - bot.y)
            if game.match.phase is not MatchPhase.PLAYING:
                break
    assert game.match.time_remaining < config.MATCH_SECONDS, "scenario never advanced live play"
    return {
        "scenario": name, "side": "left" if mirror else "right", "seed": seed,
        "frames": frame, "cpu_goals": game.match.score_left if mirror else game.match.score_right,
        "human_goals": game.match.score_right if mirror else game.match.score_left,
        "first": first, "counts": dict(counts),
        "crossing_clearance": crossing_clearance, "max_jump_height": max_height,
        "final_x_from_right_fixture": reflect(bot.x),
    }


class CPUObservationTests(unittest.TestCase):
    def test_ball_and_opponent_are_observed_only_on_reaction_ticks(self):
        ctrl = CPUController(rng=random.Random(10))
        player, opponent = new_player(600, -1), new_player(200, 1)
        ball = Ball(400, 200)
        ctrl.update(0, ball, player, opponent)
        ball.x, opponent.x = 750, 500
        ctrl.update(0.001, ball, player, opponent)
        self.assertEqual(ctrl._known_ball_x, 400)
        self.assertEqual(ctrl._opponent.x, 200)
        ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player, opponent)
        self.assertEqual(ctrl._known_ball_x, 750)
        self.assertEqual(ctrl._opponent.x, 500)

    def test_extrapolation_uses_actual_ball_gravity_and_drag(self):
        ctrl = CPUController(rng=random.Random(1))
        ball = Ball(400, 200, 50, 30)
        ctrl._perceive(0, ball)
        ctrl._perceive(0.05, ball)
        # Shared joint stepping uses six 120Hz drag integrations, not one
        # coarse Euler step. Gravity/jump constants themselves are unchanged.
        h = 1 / 120
        drag = 1 - config.BALL_AIR_DRAG_PER_SEC * h
        self.assertAlmostEqual(ctrl._known_ball_vy, 30 + config.BALL_GRAVITY * 0.05)
        self.assertAlmostEqual(ctrl._known_ball_x, 400 + sum(50 * drag ** i * h for i in range(1, 7)))
        self.assertAlmostEqual(ctrl._known_ball_y, 200 + 30 * 0.05 + 0.5 * config.BALL_GRAVITY * 0.05 ** 2)
        self.assertAlmostEqual(ctrl._known_ball_vx, 50 * drag ** 6)

    def test_prediction_bounces_without_changing_real_bodies(self):
        ctrl = CPUController(rng=random.Random(1))
        player, opponent = new_player(600, -1), new_player(190, 1)
        ball = Ball(400, 475, 0, 200)
        before = copy.deepcopy((player, opponent, ball))
        ctrl.update(0, ball, player, opponent)
        self.assertEqual((player, opponent, ball), before)
        self.assertTrue(any(sample.vy < 0 for _, sample in ctrl._trajectory))

    def test_observation_keeps_imperfect_aim_and_reset_clears_commitments(self):
        ctrl = CPUController(rng=random.Random(11))
        errors = set()
        for _ in range(12):
            ctrl._perceive(config.CPU_REACTION_DELAY_SECONDS, Ball(400, 200))
            errors.add(ctrl._aim_error)
        self.assertGreater(len(errors), 1)
        self.assertGreater(config.CPU_AIM_ERROR_PX, 0)
        self.assertEqual(config.CPU_REACTION_DELAY_SECONDS, 0.18)
        ctrl._cross_direction, ctrl._cross_remaining, ctrl._header_target_x = -1, 0.5, 300
        ctrl.reset()
        self.assertFalse(ctrl._has_perceived)
        self.assertEqual(ctrl._trajectory, [])
        self.assertEqual(ctrl._cross_direction, 0)
        self.assertEqual(ctrl._cross_remaining, 0)
        self.assertIsNone(ctrl._header_target_x)


class CPUActionTests(unittest.TestCase):
    def test_shot_setup_is_goal_side_not_centered_on_the_ball(self):
        ctrl = CPUController(rng=random.Random(3))
        player = new_player(400, -1)
        intent = ctrl.update(0, Ball(400, 485), player)
        self.assertEqual(intent.move, 1)
        self.assertFalse(intent.normal_kick)  # don't shoot while facing own goal

    def test_immediate_clearance_uses_this_frames_facing_and_ignores_power_recovery(self):
        ctrl = CPUController(rng=random.Random(7))
        player = new_player(690, 1)  # wrong old facing
        player.kick_cooldown = 0.9
        intent = ctrl.update(1 / 60, Ball(650, 485, 400, 0), player)
        self.assertEqual(intent.move, -1)
        self.assertTrue(intent.normal_kick)
        self.assertFalse(intent.power_held)
        self.assertFalse(ctrl.update(1 / 60, Ball(650, 485, 400, 0), player).normal_kick)

    def test_stationary_setup_can_turn_and_charge_at_outer_human_kick_range(self):
        ctrl = CPUController(rng=random.Random(1))
        player, opponent = new_player(289, 1), new_player(190, 1)
        ctrl._perceive(0, Ball(235, 485), opponent)
        intent = ctrl.update(1 / 60, Ball(235, 485), player, opponent)
        self.assertEqual(intent.move, -1)
        self.assertTrue(intent.power_held)

    def test_charge_holds_its_stance_and_releases_outward(self):
        ctrl = CPUController(rng=random.Random(1))
        player = new_player(289, -1)
        player.kick_charge = 0.2
        intent = ctrl.update(1 / 60, Ball(235, 485), player, new_player(190, 1))
        self.assertEqual(intent.move, 0)
        self.assertTrue(intent.power_held)
        self.assertFalse(intent.normal_kick)
        player.kick_charge = config.POWER_SHOT_CHARGE_SECONDS
        release = ctrl.update(1 / 60, Ball(235, 485), player)
        self.assertEqual(release.move, 0)
        self.assertFalse(release.power_held)
        self.assertFalse(release.normal_kick)

    def test_steep_rising_rebound_is_not_flattened_by_a_normal_kick(self):
        ctrl = CPUController(rng=random.Random(1))
        player = new_player(400, -1)
        player.kick_cooldown = 0.9
        intent = ctrl.update(1 / 60, Ball(360, 470, -100, -500), player)
        self.assertFalse(intent.normal_kick)

    def test_shared_human_geometry_and_configured_shot_limits(self):
        self.assertEqual((config.PLAYER_HEIGHT, config.HEAD_RADIUS, config.PLAYER_HALF_WIDTH), (85, 32, 20))
        self.assertEqual((config.PLAYER_SPEED, config.JUMP_VELOCITY, config.GRAVITY), (260, -780, 2160))
        self.assertEqual((config.BALL_GRAVITY, config.BALL_MAX_SPEED), (1300, 900))
        self.assertEqual((config.KICK_IMPULSE_SPEED, config.POWER_SHOT_IMPULSE_SPEED), (825, 850))


class LiveCPUScenarios(unittest.TestCase):
    def test_retrieves_a_moving_ball_beyond_the_old_leash_promptly(self):
        for mirror in (False, True):
            result = run_scenario("pursuit", mirror=mirror)
            self.assertLessEqual(result["first"]["midfield"], 65, result)
            self.assertLess(result["final_x_from_right_fixture"], 400, result)

    def test_legitimate_jump_crosses_stationary_and_airborne_blockers(self):
        for name in ("blocker", "jumping_blocker"):
            for mirror in (False, True):
                result = run_scenario(name, mirror=mirror)
                self.assertLessEqual(result["first"]["cross"], 70, result)
                self.assertGreaterEqual(result["crossing_clearance"], config.PLAYER_HEIGHT, result)
                self.assertGreater(result["first"]["landing"], result["first"]["cross"], result)
                # A real vertical landing may briefly rest on the blocker
                # instead of shoving it sideways. Require actual landing
                # before the attack, not the old frame-80 shove timing.
                self.assertLess(result["first"]["landing"], result["first"]["shot"], result)
                self.assertLessEqual(result["max_jump_height"], config.JUMP_VELOCITY ** 2 / (2 * config.GRAVITY))
                self.assertEqual(result["cpu_goals"], 1, result)
                self.assertEqual(result["human_goals"], 0, result)

    def test_reachable_airborne_ball_receives_a_real_airborne_header(self):
        for mirror in (False, True):
            result = run_scenario("header", mirror=mirror)
            self.assertGreater(result["counts"].get("air_headers", 0), 0, result)
            self.assertGreater(result["counts"].get("forward_headers", 0), 0, result)
            self.assertLessEqual(result["first"]["header"], 40, result)

    def test_actual_incoming_goal_threat_is_intercepted_not_abandoned(self):
        for mirror in (False, True):
            result = run_scenario("defend", mirror=mirror)
            self.assertEqual(result["human_goals"], 0, result)
            self.assertGreater(result["counts"].get("normal_shots", 0) + result["counts"].get("headers", 0), 0, result)
            self.assertLessEqual(result["first"]["shot"], 30, result)

    def test_recovers_to_ball_goal_side_without_waiting_for_a_distant_opponent(self):
        for mirror in (False, True):
            result = run_scenario("recover_ball", mirror=mirror)
            self.assertGreater(result["counts"].get("jumps", 0), 0, result)
            self.assertGreater(result["counts"].get("power_shots", 0), 0, result)
            self.assertEqual(result["cpu_goals"], 1, result)
            self.assertEqual(result["human_goals"], 0, result)

    def test_attacks_and_scores_against_stationary_starting_human(self):
        for seed in (1, 8, 13):
            for mirror in (False, True):
                result = run_scenario("passive", mirror=mirror, seed=seed)
                self.assertEqual(result["cpu_goals"], 1, result)
                self.assertEqual(result["human_goals"], 0, result)
                self.assertGreater(result["counts"].get("normal_shots", 0) + result["counts"].get("power_shots", 0), 0)

    def test_mirror_has_same_physical_crossing_and_scoring_opportunity(self):
        right, left = run_scenario("blocker"), run_scenario("blocker", mirror=True)
        self.assertEqual(right["first"], left["first"])
        self.assertEqual(right["frames"], left["frames"])
        self.assertAlmostEqual(right["crossing_clearance"], left["crossing_clearance"])

    def test_cpu_cannot_save_an_unreachable_shot_by_cheating(self):
        game = Game(rng=random.Random(8))
        game.start_match("1P")
        game.match.phase = MatchPhase.PLAYING
        game.player_right.x = 250
        game.ball = Ball(780, 460, 800, 0)
        for _ in range(6):
            game.update(1 / 60, RawInput())
            if game.match.phase is not MatchPhase.PLAYING:
                break
        self.assertEqual(game.match.score_left, 1)
        self.assertLess(game.player_right.x, 280)


if __name__ == "__main__":
    unittest.main()
