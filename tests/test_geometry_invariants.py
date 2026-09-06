"""Locks in the single invariant that makes the head-soccer genre work:
a standing character's head-top sits a well-defined gap below the
crossbar, and a jump must comfortably clear that gap.

Per the project's genre research report: "a character stands 85 tall, so
its head-top is at 500 - 85 = 415. The crossbar sits at 500 - 200 = 300.
Therefore a player must jump about 115px to head the crossbar, and the
sourced jump apex is ~140px. That relationship is the heart of the game."
This module is the regression guard for exactly that relationship, since
it is the thing most likely to silently drift if GROUND_Y, CHAR_HEIGHT,
GOAL_MOUTH_HEIGHT, JUMP_VELOCITY, or GRAVITY are ever tuned independently
of one another.
"""
from __future__ import annotations

import unittest

from headscotter import config, players


class JumpToCrossbarInvariantTests(unittest.TestCase):
    def test_standing_head_top_sits_roughly_115px_below_the_crossbar(self):
        standing_head_top = config.GROUND_Y - config.CHAR_HEIGHT
        gap = standing_head_top - config.CROSSBAR_Y
        self.assertAlmostEqual(gap, 115.0, delta=10.0)

    def test_head_offset_and_radius_reconstruct_char_height_exactly(self):
        """HEAD_OFFSET_Y is derived from CHAR_HEIGHT/HEAD_RADIUS so this
        holds by construction -- a regression here means someone edited
        one without the others."""
        self.assertEqual(config.HEAD_OFFSET_Y + config.HEAD_RADIUS, config.CHAR_HEIGHT)

    def test_jump_apex_clears_the_head_top_to_crossbar_gap(self):
        """Apex height = v^2 / (2*g), the standard projectile-motion
        formula for a vertical launch under constant gravity."""
        apex = (config.JUMP_VELOCITY ** 2) / (2.0 * config.GRAVITY)
        standing_head_top = config.GROUND_Y - config.CHAR_HEIGHT
        gap = standing_head_top - config.CROSSBAR_Y
        self.assertGreater(apex, gap, "a full jump must clear the crossbar, not just approach it")
        # Comfortable margin, not a hair's-breadth clearance -- the report
        # describes "clears it with margin", not "barely clears it".
        self.assertGreater(apex - gap, 10.0)

    def test_a_simulated_jump_actually_reaches_the_crossbar_height(self):
        """End-to-end version of the same check, run through the real
        per-frame player physics (players.apply_jump / step_player_physics)
        rather than the closed-form apex formula, so a bug in how gravity
        or the jump impulse is actually integrated would be caught even if
        the closed-form numbers above still looked right."""
        player = players.new_player(config.PITCH_CENTER_X, facing=1)
        players.apply_jump(player)
        min_y = player.y
        dt = 1.0 / config.FPS
        for _ in range(int(2.0 / dt)):  # generous: at most ~0.72s hang time
            players.step_player_physics(player, dt)
            min_y = min(min_y, player.y)
            if player.on_ground:
                break
        self.assertTrue(player.on_ground)

        head_top_at_apex = min_y - config.HEAD_OFFSET_Y - config.HEAD_RADIUS
        self.assertLessEqual(
            head_top_at_apex, config.CROSSBAR_Y,
            "a full jump's head-top never reached crossbar height in the simulated physics",
        )


if __name__ == "__main__":
    unittest.main()
