"""Tests for the 1P mode's CPU opponent: it tracks the ball, jumps when
overhead, kicks in range, has a genuine reaction lag, and is beatable."""
from __future__ import annotations

import random
import unittest

from headscotter import config
from headscotter.cpu import CPUController
from headscotter.physics import Ball
from headscotter.players import new_player


class CPUTrackingTests(unittest.TestCase):
    def test_cpu_moves_toward_the_ball(self):
        cpu_ctrl = CPUController(rng=random.Random(1))
        player = new_player(config.PITCH_CENTER_X, facing=-1)
        ball = Ball(x=config.PITCH_RIGHT - 100, y=config.GROUND_Y - 50)
        # First tick establishes perception; subsequent ticks should steer right.
        cpu_ctrl.update(0.0, ball, player)
        intent = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
        self.assertGreaterEqual(intent.move, 0)

    def test_cpu_does_not_stand_still_while_ball_moves_away(self):
        cpu_ctrl = CPUController(rng=random.Random(2))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - 50, vx=0.0, vy=0.0)
        moves_seen = set()
        for i in range(10):
            ball.x = config.PITCH_CENTER_X + i * 40  # ball marches away to the right
            intent = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
            moves_seen.add(intent.move)
        self.assertIn(1, moves_seen)  # it does chase at some point, not frozen at 0 forever

    def test_cpu_stops_within_the_deadzone(self):
        cpu_ctrl = CPUController(rng=random.Random(3))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - 50)
        cpu_ctrl.update(0.0, ball, player)
        intent = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
        self.assertEqual(intent.move, 0)


class CPUJumpTests(unittest.TestCase):
    def test_cpu_jumps_when_ball_is_overhead(self):
        cpu_ctrl = CPUController(rng=random.Random(4))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=config.PITCH_CENTER_X, y=player.y - config.HEAD_OFFSET_Y - 10)
        cpu_ctrl.update(0.0, ball, player)
        intent = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
        self.assertTrue(intent.jump)

    def test_cpu_does_not_jump_when_ball_is_far_overhead_horizontally(self):
        cpu_ctrl = CPUController(rng=random.Random(5))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=config.PITCH_CENTER_X + 400, y=player.y - config.HEAD_OFFSET_Y)
        cpu_ctrl.update(0.0, ball, player)
        intent = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
        self.assertFalse(intent.jump)

    def test_cpu_does_not_jump_when_already_airborne(self):
        cpu_ctrl = CPUController(rng=random.Random(6))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        player.on_ground = False
        ball = Ball(x=config.PITCH_CENTER_X, y=player.y - config.HEAD_OFFSET_Y - 10)
        cpu_ctrl.update(0.0, ball, player)
        intent = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
        self.assertFalse(intent.jump)


class CPUKickTests(unittest.TestCase):
    def test_cpu_kicks_when_ball_is_in_range(self):
        """Edge-triggered: kick fires the frame the ball *newly* enters
        range, mimicking a human's quick tap-and-kick -- see cpu.py's
        note on why this must not be a level signal (players.update_kick()
        now charges a power shot for as long as its input is held)."""
        cpu_ctrl = CPUController(rng=random.Random(7))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        far_ball = Ball(x=player.x + 500, y=player.y)
        cpu_ctrl.update(0.0, far_ball, player)  # perceives the ball out of range first
        ball = Ball(x=player.x + 20, y=player.y - 40)
        intent = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
        self.assertTrue(intent.kick)

    def test_cpu_does_not_keep_kicking_while_ball_stays_in_range(self):
        """The whole point of the edge trigger: once the ball has been
        in range for one frame, subsequent frames must not also report
        kick=True just because it is still there -- otherwise a CPU
        "holds" the kick control for as long as the ball lingers, which
        is exactly the bug that made every CPU kick charge into an
        unintended power shot."""
        cpu_ctrl = CPUController(rng=random.Random(7))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 20, y=player.y - 40)
        first = cpu_ctrl.update(0.0, ball, player)
        second = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
        third = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
        self.assertTrue(first.kick)
        self.assertFalse(second.kick)
        self.assertFalse(third.kick)

    def test_cpu_does_not_kick_when_ball_is_far_away(self):
        cpu_ctrl = CPUController(rng=random.Random(8))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=player.x + 500, y=player.y)
        cpu_ctrl.update(0.0, ball, player)
        intent = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
        self.assertFalse(intent.kick)

    def test_cpu_respects_the_kickers_own_cooldown(self):
        cpu_ctrl = CPUController(rng=random.Random(9))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        player.kick_cooldown = config.KICK_COOLDOWN_SECONDS
        far_ball = Ball(x=player.x + 500, y=player.y)
        cpu_ctrl.update(0.0, far_ball, player)
        ball = Ball(x=player.x + 20, y=player.y - 40)
        intent = cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
        self.assertFalse(intent.kick)


class CPUReactionLagTests(unittest.TestCase):
    def test_cpu_perception_lags_behind_a_sudden_ball_teleport(self):
        """This is what makes the CPU beatable: it does not instantly
        know the ball moved -- see cpu.CPUController._perceive()."""
        cpu_ctrl = CPUController(rng=random.Random(10))
        player = new_player(config.PITCH_LEFT + 200, facing=1)
        ball = Ball(x=config.PITCH_LEFT + 200, y=config.GROUND_Y - 50)
        cpu_ctrl.update(0.0, ball, player)  # first perception tick, at the ball's original spot

        ball.x = config.PITCH_RIGHT - 200  # the ball is suddenly far away
        # A single, tiny frame right after the teleport: far too little
        # time has passed for another perception tick to have occurred.
        cpu_ctrl.update(0.001, ball, player)
        self.assertLess(cpu_ctrl._known_ball_x, config.PITCH_CENTER_X)  # still thinks it's on the left

    def test_cpu_aim_error_is_not_always_zero(self):
        """Re-rolled every perception tick -- confirms the CPU is not
        pixel-perfect even once it has "seen" the ball."""
        cpu_ctrl = CPUController(rng=random.Random(11))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - 50)
        errors = set()
        for _ in range(20):
            cpu_ctrl.update(config.CPU_REACTION_DELAY_SECONDS, ball, player)
            errors.add(round(cpu_ctrl._aim_error, 3))
        self.assertGreater(len(errors), 1)

    def test_reset_forgets_prior_perception(self):
        cpu_ctrl = CPUController(rng=random.Random(12))
        player = new_player(config.PITCH_CENTER_X, facing=1)
        ball = Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - 50)
        cpu_ctrl.update(0.0, ball, player)
        cpu_ctrl.reset()
        self.assertFalse(cpu_ctrl._has_perceived)


if __name__ == "__main__":
    unittest.main()
