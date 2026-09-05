"""Pure ball physics and generic circle collision for HeadScotter.

Gravity, bouncing off the ground/walls/crossbars, and the ball-vs-circle
collision maths used for headers all live here. Every tunable constant is
in :mod:`headscotter.config`; this module only implements the arithmetic,
so it has no :mod:`pygame` import and is fully unit-testable headless.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from . import config


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def apply_gravity(vy: float, dt: float, gravity: float = config.GRAVITY) -> float:
    """One frame of gravity applied to a vertical velocity (px/sec)."""
    return vy + gravity * dt


@dataclass
class Ball:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    radius: float = config.BALL_RADIUS

    @property
    def pos(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)


def new_kickoff_ball() -> Ball:
    """A ball resting on the ground at the center spot, ready for kickoff."""
    return Ball(x=config.PITCH_CENTER_X, y=config.GROUND_Y - config.BALL_RADIUS)


def _cap_speed(ball: Ball) -> None:
    speed = ball.speed()
    if speed > config.BALL_MAX_SPEED:
        scale = config.BALL_MAX_SPEED / speed
        ball.vx *= scale
        ball.vy *= scale


def step_ball(ball: Ball, dt: float) -> Optional[str]:
    """Advance the ball one frame: gravity, drag, integration, and
    collisions with the ground, side walls/crossbars, and the ceiling.

    Returns ``"left_goal"`` the frame the ball fully crosses the left goal
    line inside the goal mouth (the left goal was breached -- the right
    player scores), ``"right_goal"`` for the mirror case, or ``None``.

    The ball is always kept within [PITCH_LEFT, PITCH_RIGHT] x
    [PITCH_TOP, GROUND_Y] except while it is mid-crossing of a goal line,
    so it can never wedge into a wall or permanently leave the pitch --
    any kick or header can always move it again from wherever it lands.
    """
    ball.vy = apply_gravity(ball.vy, dt)
    # Gentle air resistance: only horizontal speed decays in flight, so a
    # kicked ball's arc still looks governed by gravity, not a wind machine.
    ball.vx *= max(0.0, 1.0 - config.BALL_AIR_DRAG_PER_SEC * dt)
    ball.x += ball.vx * dt
    ball.y += ball.vy * dt

    event: Optional[str] = None

    # Ceiling.
    if ball.y - ball.radius < config.PITCH_TOP:
        ball.y = config.PITCH_TOP + ball.radius
        ball.vy = abs(ball.vy) * config.BALL_RESTITUTION_WALL

    # Ground: bounce, then bleed off horizontal speed via rolling friction.
    if ball.y + ball.radius > config.GROUND_Y:
        ball.y = config.GROUND_Y - ball.radius
        bounced_vy = -ball.vy * config.BALL_RESTITUTION_GROUND
        ball.vy = bounced_vy if abs(bounced_vy) > config.BALL_MIN_BOUNCE_SPEED else 0.0
        friction = config.BALL_GROUND_FRICTION_PER_SEC * dt
        if abs(ball.vx) <= friction:
            ball.vx = 0.0
        else:
            ball.vx -= friction * (1.0 if ball.vx > 0 else -1.0)

    # Left side: solid post above the crossbar, open goal mouth below it.
    if ball.x - ball.radius < config.PITCH_LEFT:
        if ball.y + ball.radius <= config.CROSSBAR_Y:
            ball.x = config.PITCH_LEFT + ball.radius
            ball.vx = abs(ball.vx) * config.BALL_RESTITUTION_WALL
        elif ball.x + ball.radius < config.PITCH_LEFT:
            event = "left_goal"

    # Right side, mirrored.
    if ball.x + ball.radius > config.PITCH_RIGHT:
        if ball.y + ball.radius <= config.CROSSBAR_Y:
            ball.x = config.PITCH_RIGHT - ball.radius
            ball.vx = -abs(ball.vx) * config.BALL_RESTITUTION_WALL
        elif ball.x - ball.radius > config.PITCH_RIGHT:
            event = "right_goal"

    _cap_speed(ball)
    return event


def resolve_circle_collision(
    ball: Ball,
    cx: float,
    cy: float,
    radius: float,
    restitution: float,
    extra_lift: float = 0.0,
) -> bool:
    """Push the ball out of, and elastically bounce it off, a static
    circle (e.g. a player's head) at ``(cx, cy)`` with the given
    ``radius``. Returns True if a collision was present and resolved.

    ``extra_lift`` is added to the outgoing vertical velocity afterward
    (a small negative bias makes headers arc upward instead of dribbling
    flatly off the collider).
    """
    dx = ball.x - cx
    dy = ball.y - cy
    dist = math.hypot(dx, dy)
    min_dist = ball.radius + radius
    if dist >= min_dist:
        return False

    if dist < 1e-6:
        # Perfectly concentric (should not really happen) -- push straight up.
        nx, ny = 0.0, -1.0
        dist = 0.0
    else:
        nx, ny = dx / dist, dy / dist

    overlap = min_dist - dist
    ball.x += nx * overlap
    ball.y += ny * overlap

    speed_into_surface = ball.vx * nx + ball.vy * ny
    if speed_into_surface < 0:
        ball.vx -= (1.0 + restitution) * speed_into_surface * nx
        ball.vy -= (1.0 + restitution) * speed_into_surface * ny
        # Only a genuine impact (moving into the collider) gets the extra
        # lift -- otherwise a ball merely resting against a head would be
        # nudged upward every single frame with nothing to explain it.
        ball.vy -= extra_lift
    _cap_speed(ball)
    return True
