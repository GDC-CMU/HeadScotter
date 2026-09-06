"""Pure ball physics and generic circle collision for HeadScotter.

Gravity, bouncing off the ground/walls/crossbars, and the ball-vs-circle
collision maths used for headers all live here. Every tunable constant is
in :mod:`headscotter.config`; this module only implements the arithmetic,
so it has no :mod:`pygame` import and is fully unit-testable headless.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple

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
    # Audio contact episodes, not an audio timer. Cleared by actual separation,
    # so substep corrections cannot replay an impact, but a new hit can.
    impact_contacts: set[str] = field(default_factory=set, repr=False)

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


def _impact(ball: Ball, contact: str, incoming_speed: float) -> bool:
    """Record contact, reporting only a new, meaningful incoming impact."""
    new_contact = contact not in ball.impact_contacts
    ball.impact_contacts.add(contact)
    return new_contact and incoming_speed > config.BALL_MIN_BOUNCE_SPEED


def _release_contact(ball: Ball, contact: str, gap: float) -> None:
    if gap > 1e-6:
        ball.impact_contacts.discard(contact)


def step_ball(ball: Ball, dt: float, on_bounce: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """Advance the ball one frame (or one substep -- see game.py, which
    calls this several times per real frame at high ball speed to avoid
    tunnelling through thin colliders): gravity, drag, integration, and
    collisions with the ground, side walls/crossbars, and the ceiling.

    Returns ``"left_goal"`` the frame the ball's *centre* crosses the left
    goal line inside the goal mouth (the left goal was breached -- the
    right player scores), ``"right_goal"`` for the mirror case, or
    ``None``. Deliberately centre-crossing, not "the entire circle has
    fully cleared the line": requiring the far edge to clear too left a
    narrow dead zone, beyond where any player can ever stand (past their
    own movement clamp) but before the far-edge threshold, where a slow
    trickle could come to rest forever with no player able to reach it
    and no way to ever finish crossing -- a genuine, confirmed soft-lock
    (see tests/test_arcade_contract.py's full-match simulation, and
    tests/test_balance.py's sudden-death termination guard). Once the
    centre is over the line the ball reads as "in the net" regardless of
    the trailing edge, which also matches how forgiving most reference
    implementations' goal detection is.

    ``on_bounce``, if given, is called with ``"ceiling"``, ``"ground"``,
    or ``"wall"`` on a new incoming impact above the settling threshold --
    purely a notification hook (e.g. for a sound effect); it never
    affects the physics and defaults to doing nothing.

    The ball is always kept within [PITCH_LEFT, PITCH_RIGHT] x
    [PITCH_TOP, GROUND_Y] except while it is mid-crossing of a goal line,
    so it can never wedge into a wall or permanently leave the pitch --
    any kick or header can always move it again from wherever it lands.
    """
    _release_contact(ball, "ground", config.GROUND_Y - ball.y - ball.radius)
    _release_contact(ball, "ceiling", ball.y - ball.radius - config.PITCH_TOP)
    _release_contact(ball, "left_wall", ball.x - ball.radius - config.PITCH_LEFT)
    _release_contact(ball, "right_wall", config.PITCH_RIGHT - ball.x - ball.radius)
    supported = ball.y + ball.radius >= config.GROUND_Y - 1e-6 and ball.vy == 0.0
    ball.vy = apply_gravity(ball.vy, dt, config.BALL_GRAVITY)
    # Gentle air resistance: only horizontal speed decays in flight, so a
    # kicked ball's arc still looks governed by gravity, not a wind machine.
    ball.vx *= max(0.0, 1.0 - config.BALL_AIR_DRAG_PER_SEC * dt)
    ball.x += ball.vx * dt
    ball.y += ball.vy * dt

    event: Optional[str] = None

    # Ceiling.
    if ball.y - ball.radius < config.PITCH_TOP:
        impact = _impact(ball, "ceiling", -ball.vy)
        ball.y = config.PITCH_TOP + ball.radius
        ball.vy = abs(ball.vy) * config.BALL_RESTITUTION_WALL
        if impact and on_bounce is not None:
            on_bounce("ceiling")

    # Ground: bounce, then bleed off horizontal speed via rolling friction.
    if ball.y + ball.radius > config.GROUND_Y:
        impact = _impact(ball, "ground", 0.0 if supported else ball.vy)
        ball.y = config.GROUND_Y - ball.radius
        bounced_vy = -ball.vy * config.BALL_RESTITUTION_GROUND
        if supported:
            ball.vy = 0.0  # gravity against support is not a fresh drop
        elif ball.vy > 0.0:
            ball.vy = bounced_vy if abs(bounced_vy) > config.BALL_MIN_BOUNCE_SPEED else 0.0
        friction = config.BALL_GROUND_FRICTION_PER_SEC * dt
        if abs(ball.vx) <= friction:
            ball.vx = 0.0
        else:
            ball.vx -= friction * (1.0 if ball.vx > 0 else -1.0)
        if impact and on_bounce is not None:
            on_bounce("ground")

    # Left side: solid post above the crossbar, open goal mouth below it.
    if ball.x - ball.radius < config.PITCH_LEFT:
        if ball.y + ball.radius <= config.CROSSBAR_Y:
            impact = _impact(ball, "left_wall", -ball.vx)
            ball.x = config.PITCH_LEFT + ball.radius
            ball.vx = abs(ball.vx) * config.BALL_RESTITUTION_WALL
            if impact and on_bounce is not None:
                on_bounce("wall")
        elif ball.x <= config.PITCH_LEFT:
            event = "left_goal"

    # Right side, mirrored.
    if ball.x + ball.radius > config.PITCH_RIGHT:
        if ball.y + ball.radius <= config.CROSSBAR_Y:
            impact = _impact(ball, "right_wall", ball.vx)
            ball.x = config.PITCH_RIGHT - ball.radius
            ball.vx = -abs(ball.vx) * config.BALL_RESTITUTION_WALL
            if impact and on_bounce is not None:
                on_bounce("wall")
        elif ball.x >= config.PITCH_RIGHT:
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
    on_impact: Optional[Callable[[], None]] = None,
    contact_id: str = "head",
    collider_velocity: Tuple[float, float] = (0.0, 0.0),
) -> bool:
    """Push the ball out of, and elastically bounce it off, a static
    circle (e.g. a player's head) at ``(cx, cy)`` with the given
    ``radius``. Returns True if a collision was present and resolved.

    ``extra_lift`` is added after a meaningful incoming hit, never support.
    ``collider_velocity`` supplies relative normal evidence for sound only;
    collision response keeps its existing static-collider restitution.
    Extra lift biases the outgoing vertical velocity
    (a small negative bias makes headers arc upward instead of dribbling
    flatly off the collider).
    """
    dx = ball.x - cx
    dy = ball.y - cy
    dist = math.hypot(dx, dy)
    min_dist = ball.radius + radius
    _release_contact(ball, contact_id, dist - min_dist)
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
    relative_normal = speed_into_surface - collider_velocity[0] * nx - collider_velocity[1] * ny
    impact = _impact(ball, contact_id, -relative_normal)
    if speed_into_surface < 0:
        ball.vx -= (1.0 + restitution) * speed_into_surface * nx
        ball.vy -= (1.0 + restitution) * speed_into_surface * ny
        # Gravity against head support is not a new header. Giving those
        # tiny corrections extra lift manufactured a repeating bounce cycle.
        if speed_into_surface < -config.BALL_MIN_BOUNCE_SPEED:
            ball.vy -= extra_lift
    _cap_speed(ball)
    if impact and on_impact is not None:
        on_impact()
    return True


def resolve_circle_aabb_collision(
    ball: Ball,
    left: float,
    top: float,
    right: float,
    bottom: float,
    restitution: float,
) -> bool:
    """Push the ball out of, and bounce it off (with ``restitution``), a
    static axis-aligned rectangle -- e.g. a player's body/torso (see
    players.apply_body_collision()). Returns True if a collision was
    present and resolved.

    Uses the standard closest-point-on-rect construction: find the point
    on the rectangle nearest the ball's centre, treat the vector from
    that point to the centre as the collision normal, and resolve exactly
    like :func:`resolve_circle_collision` against a circle at that point.
    If the ball's centre is already inside the rectangle (fully
    embedded -- possible for a very fast ball on a coarse frame), that
    vector is zero-length, so it falls back to pushing out along
    whichever side has the least penetration instead.
    """
    closest_x = clamp(ball.x, left, right)
    closest_y = clamp(ball.y, top, bottom)
    dx = ball.x - closest_x
    dy = ball.y - closest_y
    dist_sq = dx * dx + dy * dy

    if dist_sq >= ball.radius * ball.radius:
        return False

    if dist_sq < 1e-9:
        # Ball centre is inside the rect: push out through whichever side
        # is closest, rather than through an undefined (zero-length) normal.
        pen_left = ball.x - left
        pen_right = right - ball.x
        pen_top = ball.y - top
        pen_bottom = bottom - ball.y
        smallest = min(pen_left, pen_right, pen_top, pen_bottom)
        if smallest == pen_left:
            nx, ny = -1.0, 0.0
        elif smallest == pen_right:
            nx, ny = 1.0, 0.0
        elif smallest == pen_top:
            nx, ny = 0.0, -1.0
        else:
            nx, ny = 0.0, 1.0
        overlap = smallest + ball.radius
    else:
        dist = math.sqrt(dist_sq)
        nx, ny = dx / dist, dy / dist
        overlap = ball.radius - dist

    ball.x += nx * overlap
    ball.y += ny * overlap

    speed_into_surface = ball.vx * nx + ball.vy * ny
    if speed_into_surface < 0:
        ball.vx -= (1.0 + restitution) * speed_into_surface * nx
        ball.vy -= (1.0 + restitution) * speed_into_surface * ny
    _cap_speed(ball)
    return True
