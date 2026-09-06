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
    # Contact episodes, cleared by actual separation rather than a timer,
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
    meaningful = incoming_speed > config.BALL_MIN_BOUNCE_SPEED
    if meaningful:
        ball.impact_contacts.add(contact)
    return new_contact and meaningful


def _release_contact(ball: Ball, contact: str, gap: float) -> None:
    if gap > 1e-6:
        ball.impact_contacts.discard(contact)


def integrate_ball(ball: Ball, dt: float) -> None:
    """Free motion only; the world resolves all contacts after integration."""
    _cap_speed(ball)
    old_vy = ball.vy
    ball.vy = apply_gravity(ball.vy, dt, config.BALL_GRAVITY)
    ball.vx *= max(0.0, 1.0 - config.BALL_AIR_DRAG_PER_SEC * dt)
    _cap_speed(ball)
    ball.x += ball.vx * dt
    ball.y += (old_vy + ball.vy) * 0.5 * dt


def reflect_velocity(ball: Ball, nx: float, ny: float, restitution: float,
                     collider_velocity=(0.0, 0.0), extra_lift: float = 0.0,
                     settle: bool = False, settle_speed: Optional[float] = None) -> float:
    """Reflect relative normal motion, retaining the collider's world motion.

    Returns incoming relative normal speed. Position correction alone never
    reflects an already separating shot. Tiny support corrections don't bounce.
    """
    relative = (ball.vx - collider_velocity[0]) * nx + (ball.vy - collider_velocity[1]) * ny
    if relative < 0.0:
        bounce = restitution
        threshold = config.BALL_MIN_BOUNCE_SPEED if settle_speed is None else settle_speed
        if settle and -relative * restitution <= threshold:
            bounce = 0.0
        ball.vx -= (1.0 + bounce) * relative * nx
        ball.vy -= (1.0 + bounce) * relative * ny
        if -relative > config.BALL_MIN_BOUNCE_SPEED:
            ball.vy -= extra_lift
        _cap_speed(ball)
    return -relative


def post_contact(x: float, y: float, radius: float, side: str):
    """Signed circle/solid-post clearance and outward normal.

    The nominal post is the region outside the pitch ABOVE CROSSBAR_Y.
    Its lower corner is rounded by the ball radius, not switched off when
    only the ball's bottom edge reaches the goal mouth.
    """
    edge = config.PITCH_LEFT if side == "left" else config.PITCH_RIGHT
    px = min(x, edge) if side == "left" else max(x, edge)
    py = min(y, config.CROSSBAR_Y)
    dx, dy = x - px, y - py
    distance = math.hypot(dx, dy)
    if distance > 1e-12:
        return distance - radius, dx / distance, dy / distance
    horizontal = abs(x - edge)
    vertical = config.CROSSBAR_Y - y
    if horizontal <= vertical:
        return -horizontal - radius, 1.0 if side == "left" else -1.0, 0.0
    return -vertical - radius, 0.0, 1.0


def step_ball(ball: Ball, dt: float, on_bounce: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """Compatibility helper for one ball/pitch substep.

    Live matches and copied CPU forecasts use world.step_world(), which
    bounds motion and resolves the pitch together with moving players.

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
    purely a notification hook for visual feedback; it never
    affects the physics and defaults to doing nothing.

    The ball is always kept within [PITCH_LEFT, PITCH_RIGHT] x
    [PITCH_TOP, GROUND_Y] except while it is mid-crossing of a goal line,
    so it can never wedge into a wall or permanently leave the pitch --
    any kick or header can always move it again from wherever it lands.
    """
    _release_contact(ball, "ground", config.GROUND_Y - ball.y - ball.radius)
    _release_contact(ball, "ceiling", ball.y - ball.radius - config.PITCH_TOP)
    for side in ("left", "right"):
        _release_contact(ball, f"{side}_wall", post_contact(ball.x, ball.y, ball.radius, side)[0])
    supported = ball.y + ball.radius >= config.GROUND_Y - 1e-6 and ball.vy == 0.0
    integrate_ball(ball, dt)

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
            ball.vy = bounced_vy if abs(bounced_vy) > config.BALL_GROUND_SETTLE_SPEED else 0.0
        friction = config.BALL_GROUND_FRICTION_PER_SEC * dt
        if abs(ball.vx) <= friction:
            ball.vx = 0.0
        else:
            ball.vx -= friction * (1.0 if ball.vx > 0 else -1.0)
        if impact and on_bounce is not None:
            on_bounce("ground")

    for side in ("left", "right"):
        gap, nx, ny = post_contact(ball.x, ball.y, ball.radius, side)
        if gap < 0.0:
            ball.x -= gap * nx
            ball.y -= gap * ny
            incoming = reflect_velocity(ball, nx, ny, config.BALL_RESTITUTION_WALL)
            if _impact(ball, f"{side}_wall", incoming) and on_bounce is not None:
                on_bounce("wall")
    if ball.x <= config.PITCH_LEFT:
        event = "left_goal"
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
    """Push the ball out of, and elastically bounce it off, a
    circle (e.g. a player's head) at ``(cx, cy)`` with the given
    ``radius``. Returns True if a collision was present and resolved.

    ``extra_lift`` is added after a meaningful incoming hit, never support.
    ``collider_velocity`` supplies relative motion for response and impact events.
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

    incoming = reflect_velocity(ball, nx, ny, restitution, collider_velocity, extra_lift, settle=True)
    impact = _impact(ball, contact_id, incoming)
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
    collider_velocity: Tuple[float, float] = (0.0, 0.0),
) -> bool:
    """Push the ball out of, and bounce it off (with ``restitution``), a
    possibly moving axis-aligned rectangle -- e.g. a player's body/torso (see
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

    reflect_velocity(ball, nx, ny, restitution, collider_velocity)
    return True
