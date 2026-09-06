"""Tests for pure ball physics: gravity, bouncing, pitch containment."""
from __future__ import annotations

import unittest

from headscotter import config, physics
from headscotter.physics import Ball


class GravityTests(unittest.TestCase):
    def test_gravity_increases_downward_velocity(self):
        vy = physics.apply_gravity(0.0, dt=0.1, gravity=100.0)
        self.assertAlmostEqual(vy, 10.0)

    def test_gravity_is_cumulative(self):
        vy = 0.0
        for _ in range(10):
            vy = physics.apply_gravity(vy, dt=0.1, gravity=100.0)
        self.assertAlmostEqual(vy, 100.0)


class GroundBounceTests(unittest.TestCase):
    def test_rest_is_supported_even_after_a_long_frame(self):
        ball = physics.new_kickoff_ball()
        events = []
        for _ in range(10):
            physics.step_ball(ball, 0.25, events.append)
        self.assertEqual(events, [])
        self.assertEqual(ball.vy, 0.0)

    def test_separating_floor_penetration_is_not_an_impact(self):
        ball = Ball(400, config.GROUND_Y - 5, vy=-200)
        events = []
        physics.step_ball(ball, 0.001, events.append)
        self.assertEqual(events, [])
        self.assertLess(ball.vy, 0)
    def test_ball_bounces_off_ground_with_restitution(self):
        ball = Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - 5, vx=0.0, vy=200.0)
        physics.step_ball(ball, dt=1 / 60.0)
        self.assertLessEqual(ball.y + ball.radius, config.GROUND_Y + 1e-6)
        self.assertLess(ball.vy, 0.0)  # bounced back upward

    def test_slow_bounce_settles_to_rest_not_infinite_jitter(self):
        ball = Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - config.BALL_RADIUS, vx=0.0, vy=10.0)
        for _ in range(5):
            physics.step_ball(ball, dt=1 / 60.0)
        self.assertEqual(ball.vy, 0.0)

    def test_ground_friction_bleeds_off_horizontal_speed(self):
        ball = Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - config.BALL_RADIUS, vx=300.0, vy=0.0)
        for _ in range(240):  # a few seconds
            physics.step_ball(ball, dt=1 / 60.0)
        self.assertAlmostEqual(ball.vx, 0.0, delta=1.0)


class CeilingAndWallTests(unittest.TestCase):
    def test_wall_and_ceiling_contacts_require_incoming_normal_speed(self):
        cases = [
            (config.PITCH_LEFT + 5, config.PITCH_TOP + 80, 200, 0),
            (config.PITCH_RIGHT - 5, config.PITCH_TOP + 80, -200, 0),
            (400, config.PITCH_TOP + 5, 0, 200),
            (config.PITCH_LEFT + 5, config.PITCH_TOP + 80, 0, 0),
        ]
        for x, y, vx, vy in cases:
            events = []
            physics.step_ball(Ball(x, y, vx, vy), 0.001, events.append)
            self.assertEqual(events, [])

    def test_real_wall_contact_rearms_only_after_separation(self):
        ball = Ball(config.PITCH_LEFT + 5, config.PITCH_TOP + 80, -200, 0)
        events = []
        for _ in range(5):
            ball.x, ball.vx = config.PITCH_LEFT + 5, -200
            physics.step_ball(ball, 0.001, events.append)
        self.assertEqual(events, ["wall"])
        ball.x = 400
        physics.step_ball(ball, 0.001, events.append)
        ball.x, ball.vx = config.PITCH_LEFT + 5, -200
        physics.step_ball(ball, 0.001, events.append)
        self.assertEqual(events, ["wall", "wall"])
    def test_ball_bounces_off_ceiling(self):
        ball = Ball(x=config.PITCH_CENTER_X, y=config.PITCH_TOP + 5, vx=0.0, vy=-200.0)
        physics.step_ball(ball, dt=1 / 60.0)
        self.assertGreaterEqual(ball.y - ball.radius, config.PITCH_TOP - 1e-6)
        self.assertGreater(ball.vy, 0.0)

    def test_ball_bounces_off_post_above_crossbar(self):
        # Above the crossbar height -- a solid post, not a goal.
        ball = Ball(x=config.PITCH_LEFT + 5, y=config.PITCH_TOP + 10, vx=-200.0, vy=0.0)
        event = physics.step_ball(ball, dt=1 / 60.0)
        self.assertIsNone(event)
        self.assertGreater(ball.vx, 0.0)
        self.assertGreaterEqual(ball.x - ball.radius, config.PITCH_LEFT - 1e-6)

    def test_ball_bounces_off_right_post_above_crossbar(self):
        ball = Ball(x=config.PITCH_RIGHT - 5, y=config.PITCH_TOP + 10, vx=200.0, vy=0.0)
        event = physics.step_ball(ball, dt=1 / 60.0)
        self.assertIsNone(event)
        self.assertLess(ball.vx, 0.0)


class GoalScoringTests(unittest.TestCase):
    def test_ball_fully_crossing_left_goal_line_below_crossbar_scores(self):
        ball = Ball(x=config.PITCH_LEFT + 2, y=config.GROUND_Y - 10, vx=-400.0, vy=0.0)
        event = None
        for _ in range(10):
            event = physics.step_ball(ball, dt=1 / 60.0)
            if event:
                break
        self.assertEqual(event, "left_goal")

    def test_ball_fully_crossing_right_goal_line_below_crossbar_scores(self):
        ball = Ball(x=config.PITCH_RIGHT - 2, y=config.GROUND_Y - 10, vx=400.0, vy=0.0)
        event = None
        for _ in range(10):
            event = physics.step_ball(ball, dt=1 / 60.0)
            if event:
                break
        self.assertEqual(event, "right_goal")

    def test_ball_center_still_on_the_pitch_side_is_not_yet_a_goal(self):
        # The leading edge has entered the goal mouth, but the centre
        # has not yet crossed the line -- not a goal yet.
        ball = Ball(x=config.PITCH_LEFT + 1, y=config.GROUND_Y - 10, vx=0.0, vy=0.0)
        event = physics.step_ball(ball, dt=1 / 600.0)
        self.assertIsNone(event)

    def test_ball_center_crossing_the_line_scores_even_if_the_far_edge_has_not_cleared(self):
        # This is the fix for a genuine soft-lock found via simulation: a
        # ball resting just past the line (centre past it, far/trailing
        # edge not yet) must still count as a goal -- otherwise it could
        # end up motionless in a dead zone beyond where any player can
        # ever reach it (past their own movement clamp), with no way to
        # ever finish crossing on its own. See the module docstring on
        # physics.step_ball().
        ball = Ball(x=config.PITCH_LEFT - 1, y=config.GROUND_Y - 10, vx=0.0, vy=0.0)
        event = physics.step_ball(ball, dt=1 / 600.0)
        self.assertEqual(event, "left_goal")


class BallContainmentTests(unittest.TestCase):
    def test_ball_never_leaves_pitch_bounds_across_many_frames(self):
        """Property test: from a variety of starting velocities well clear
        of the goal mouths, the ball always stays within the pitch
        rectangle (or a goal event fires and play would be reset)."""
        starts = [
            (config.PITCH_CENTER_X, config.GROUND_Y - 100, 350.0, -600.0),
            (config.PITCH_CENTER_X, config.PITCH_TOP + 50, -500.0, 400.0),
            (config.PITCH_CENTER_X + 100, config.GROUND_Y - 200, 700.0, -300.0),
            (config.PITCH_CENTER_X - 150, config.GROUND_Y - 50, -650.0, -500.0),
        ]
        for x, y, vx, vy in starts:
            with self.subTest(start=(x, y, vx, vy)):
                ball = Ball(x=x, y=y, vx=vx, vy=vy)
                for _ in range(600):  # 10 seconds
                    event = physics.step_ball(ball, dt=1 / 60.0)
                    if event is not None:
                        break
                    self.assertGreaterEqual(ball.x, config.PITCH_LEFT - ball.radius - 1.0)
                    self.assertLessEqual(ball.x, config.PITCH_RIGHT + ball.radius + 1.0)
                    self.assertGreaterEqual(ball.y, config.PITCH_TOP - 1.0)
                    self.assertLessEqual(ball.y, config.GROUND_Y + 1.0)

    def test_ball_speed_is_capped(self):
        ball = Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - 200, vx=5000.0, vy=5000.0)
        physics.step_ball(ball, dt=1 / 60.0)
        self.assertLessEqual(ball.speed(), config.BALL_MAX_SPEED + 1e-6)


class CircleCollisionTests(unittest.TestCase):
    def test_overlapping_ball_is_pushed_out_and_reflected(self):
        ball = Ball(x=100.0, y=100.0, vx=0.0, vy=100.0)  # moving down, into the collider below
        collided = physics.resolve_circle_collision(ball, cx=100.0, cy=120.0, radius=20.0, restitution=0.5)
        self.assertTrue(collided)
        self.assertLess(ball.vy, 0.0)  # reflected back upward

    def test_no_collision_when_far_apart(self):
        ball = Ball(x=0.0, y=0.0, vx=10.0, vy=10.0)
        collided = physics.resolve_circle_collision(ball, cx=1000.0, cy=1000.0, radius=20.0, restitution=0.5)
        self.assertFalse(collided)
        self.assertEqual((ball.vx, ball.vy), (10.0, 10.0))

    def test_resting_touch_does_not_get_spurious_lift(self):
        # Moving *away* from the collider already -- extra_lift must not apply.
        ball = Ball(x=100.0, y=95.0, vx=0.0, vy=-50.0)
        physics.resolve_circle_collision(ball, cx=100.0, cy=120.0, radius=20.0, restitution=0.5, extra_lift=999.0)
        self.assertGreater(ball.vy, -999.0)


if __name__ == "__main__":
    unittest.main()
