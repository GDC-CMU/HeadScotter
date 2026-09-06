"""Player movement, jumping, and kicking.

Pure logic, no :mod:`pygame` import: everything here operates on plain
dataclasses and the shared physics helpers in :mod:`headscotter.physics`.
:mod:`headscotter.game` translates real input into the ``move``/
``jump_pressed``/``kick_pressed`` values these functions take.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from . import config, physics
from .physics import Ball


@dataclass
class Player:
    """One head-soccer character. ``x``/``y`` track the *feet* position;
    the collidable "head" circle and "body" rectangle are both derived
    from it (see :attr:`head_center` and :func:`body_rect`).
    ``sprite_key`` is a pure display label (e.g. "scotty" or "rival")
    consumed only by render.py."""

    x: float
    y: float = config.GROUND_Y
    vy: float = 0.0
    facing: int = 1              # +1 faces right, -1 faces left
    on_ground: bool = True
    moving: bool = False
    kick_cooldown: float = 0.0  # power-shot recovery only; never blocks normal kicks
    #: Seconds the kick control has been held continuously this charge --
    #: see :func:`update_power_shot`. Reset to 0 the instant it is released
    #: (whether or not that release fired a shot) or while on cooldown.
    kick_charge: float = 0.0
    #: Counts down after any kick (normal or power) fires, purely so
    #: render.py can hold the kick pose for a fixed, predictable window
    #: (config.KICK_POSE_HOLD_SECONDS) regardless of that kick's own
    #: (now variable, see config.POWER_SHOT_*) cooldown length.
    kick_pose_timer: float = 0.0
    sprite_key: str = "scotty"
    vx: float = 0.0  # actual constrained world velocity, not a facing guess

    @property
    def head_center(self) -> Tuple[float, float]:
        return (self.x, self.y - config.HEAD_OFFSET_Y)

    @property
    def just_kicked(self) -> bool:
        """True for the short window right after a kick fires -- used
        only by render.py to pick a kick pose; carries no gameplay
        meaning of its own."""
        return self.kick_pose_timer > 0.0

    @property
    def charge_fraction(self) -> float:
        """0.0-1.0 progress toward a full-strength power shot -- used
        only by render.py to draw the charge indicator."""
        if config.POWER_SHOT_CHARGE_SECONDS <= 0.0:
            return 0.0
        return physics.clamp(self.kick_charge / config.POWER_SHOT_CHARGE_SECONDS, 0.0, 1.0)


def body_rect(player: Player) -> Tuple[float, float, float, float]:
    """The torso+legs collider: an axis-aligned box ``PLAYER_HALF_WIDTH``
    either side of the player's centreline, spanning from the bottom of
    the head circle down to the feet. This is what makes the body
    actually solid against the ball -- previously the head circle was
    the *only* collider, leaving a real gap (the torso/legs) the ball
    could pass straight through. See :func:`apply_body_collision`.
    """
    top = player.y - (config.HEAD_OFFSET_Y - config.HEAD_RADIUS)
    return (
        player.x - config.PLAYER_HALF_WIDTH,
        top,
        player.x + config.PLAYER_HALF_WIDTH,
        player.y,
    )


def new_player(x: float, facing: int, sprite_key: str = "scotty") -> Player:
    return Player(x=x, y=config.GROUND_Y, facing=facing, sprite_key=sprite_key)


def apply_move(player: Player, move: int, dt: float) -> None:
    """``move`` is -1 (left), 0 (still), or +1 (right)."""
    player.moving = move != 0
    if move != 0:
        player.facing = 1 if move > 0 else -1
    old_x = player.x
    player.x += move * config.PLAYER_SPEED * dt
    player.x = physics.clamp(
        player.x,
        config.PITCH_LEFT + config.PLAYER_HALF_WIDTH,
        config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH,
    )
    player.vx = (player.x - old_x) / dt if dt > 0.0 else 0.0


def prepare_motion(player: Player, move: int, jump_pressed: bool) -> None:
    """Resolve intent once, before shots. World stepping performs the motion."""
    player.moving = move != 0
    player.vx = move * config.PLAYER_SPEED
    if (move < 0 and player.x <= config.PITCH_LEFT + config.PLAYER_HALF_WIDTH) or (
        move > 0 and player.x >= config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH
    ):
        player.vx = 0.0
    if move:
        player.facing = move
    if jump_pressed:
        apply_jump(player)


def apply_jump(player: Player) -> None:
    if player.on_ground:
        player.vy = config.JUMP_VELOCITY
        player.on_ground = False


def step_player_physics(player: Player, dt: float, *, tick_timers: bool = True) -> None:
    old_vy = player.vy
    player.vy = physics.apply_gravity(player.vy, dt)
    player.y += (old_vy + player.vy) * 0.5 * dt
    if player.y >= config.GROUND_Y:
        player.y = config.GROUND_Y
        player.vy = 0.0
        player.on_ground = True
    if tick_timers:
        advance_timers(player, dt)


def advance_timers(player: Player, dt: float) -> None:
    if player.kick_cooldown > 0.0:
        player.kick_cooldown = max(0.0, player.kick_cooldown - dt)
    if player.kick_pose_timer > 0.0:
        player.kick_pose_timer = max(0.0, player.kick_pose_timer - dt)


def update_player(player: Player, dt: float, move: int, jump_pressed: bool) -> None:
    """The full per-frame update for one player's own body, excluding the
    ball interactions (see :func:`normal_kick` / :func:`apply_head_collision`,
    called separately once both players have moved)."""
    apply_move(player, move, dt)
    if jump_pressed:
        apply_jump(player)
    step_player_physics(player, dt)


def separate_players(a: Player, b: Player) -> bool:
    """Push two overlapping player bodies apart horizontally so they can
    never interpenetrate. World stepping uses this for horizontal approaches
    on each bounded substep; landings are resolved on the vertical approach
    axis instead of shoving a grounded neighbour through a nearby ball.

    Gated on overlap in **both** axes -- horizontal (each player's
    ``PLAYER_HALF_WIDTH``-wide footprint) and vertical (each player's
    ``PLAYER_HEIGHT``-tall body, feet to head-top). This is a deliberate
    design choice, not an oversight: a jumping player passing directly
    over the other's head (e.g. to contest a header) is a legitimate,
    genre-standard move, and must not be blocked just because their
    horizontal footprints still overlap. Only bodies that are genuinely
    overlapping at roughly the same height are ever separated.

    Neither player is privileged -- on an open pitch each is pushed out
    by exactly half the overlap, so separation is symmetric. If one of
    them is pinned against a pitch-edge clamp and has less than half the
    overlap worth of room to give, the other absorbs whatever distance
    is left instead (up to its own room against the far wall), so the
    pair always ends up fully separated (exactly touching, never
    overlapping) rather than partially resolved wherever that's
    geometrically possible. Neither player's position can ever move
    outside the pitch bounds as a result of this.

    Returns True if a separation was applied (i.e. the bodies actually
    overlapped); players that don't overlap are left completely untouched.
    """
    dx = b.x - a.x
    footprint = config.PLAYER_HALF_WIDTH * 2.0
    if abs(dx) >= footprint:
        return False  # no horizontal overlap
    if abs(a.y - b.y) >= config.PLAYER_HEIGHT:
        return False  # no vertical overlap -- e.g. one has jumped clean over the other

    overlap = footprint - abs(dx)
    if overlap <= 0.0:
        return False

    # +1 if b is to a's right (or exactly coincident), -1 if to its left --
    # `a` is pushed by -direction and `b` by +direction, i.e. each moves
    # further in the direction it's already on, away from the other.
    direction = 1.0 if dx >= 0.0 else -1.0
    low = config.PITCH_LEFT + config.PLAYER_HALF_WIDTH
    high = config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH

    # How far each player could move in its own separating direction
    # before hitting a pitch edge, independent of the other player.
    room_a = (a.x - low) if direction > 0 else (high - a.x)
    room_b = (high - b.x) if direction > 0 else (b.x - low)

    half = overlap / 2.0
    push_a = min(half, room_a)
    push_b = min(overlap - push_a, room_b)
    # If `b` still couldn't take its full share (also wall-limited), see
    # whether `a` has any spare room left to make up the difference --
    # keeps the pair as fully separated as the pitch geometrically
    # allows, rather than favoring whichever player happened to be
    # resolved first.
    leftover = (overlap - push_a) - push_b
    if leftover > 0.0:
        push_a += min(leftover, room_a - push_a)

    a.x -= direction * push_a
    b.x += direction * push_b

    return True


class KickResult:
    """Result of a normal attempt or power release. Deliberately a
    small explicit object rather than a bare bool -- ``bool(result)`` is
    NOT meaningful; check ``.fired`` -- so a caller can't accidentally
    treat "a kick object exists" as "a kick fired"."""

    __slots__ = ("fired", "is_power_shot")

    def __init__(self, fired: bool, is_power_shot: bool = False):
        self.fired = fired
        self.is_power_shot = is_power_shot

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"KickResult(fired={self.fired}, is_power_shot={self.is_power_shot})"


def normal_kick(player: Player, ball: Ball) -> KickResult:
    """One fresh press = one attempt, including a visible whiff.

    The caller owns press edges. No release or power recovery is involved.
    """
    player.kick_pose_timer = config.KICK_POSE_HOLD_SECONDS
    return _strike(player, ball, 0.0)


def _strike(player: Player, ball: Ball, fraction: float) -> KickResult:
    box_cx = player.x + player.facing * (config.KICK_RANGE_X * 0.5)
    box_cy = player.y - (config.KICK_RANGE_Y * 0.5)
    if abs(ball.x - box_cx) > config.KICK_RANGE_X or abs(ball.y - box_cy) > config.KICK_RANGE_Y:
        return KickResult(fired=False)

    speed = config.KICK_IMPULSE_SPEED + (config.POWER_SHOT_IMPULSE_SPEED - config.KICK_IMPULSE_SPEED) * fraction
    angle_deg = config.KICK_LAUNCH_ANGLE_DEG + (
        config.POWER_SHOT_LAUNCH_ANGLE_DEG - config.KICK_LAUNCH_ANGLE_DEG
    ) * fraction
    angle = math.radians(angle_deg)
    ball.vx = player.vx + player.facing * speed * math.cos(angle)
    ball.vy = player.vy - speed * math.sin(angle)
    physics._cap_speed(ball)
    return KickResult(fired=True, is_power_shot=fraction >= 0.5)


def update_power_shot(player: Player, ball: Ball, power_held: bool, dt: float) -> KickResult:
    """Charge-and-release power shot: holding the separate power control charges a
    power shot (see config.POWER_SHOT_*); releasing it fires, with the
    strength interpolated continuously from an ordinary kick (an
    immediate tap-and-release, near-zero charge) up to a full power shot
    (held for config.POWER_SHOT_CHARGE_SECONDS). The ball must be within
    this player's kick hit-box (in front of them, at foot height) *at
    the moment of release* for anything to fire; charging with no ball
    nearby is harmless and simply resets on release.

    A kick (of either strength) is a deliberate strike -- distinct from
    the passive header/body bounce in :func:`apply_head_collision` /
    :func:`apply_body_collision`, which happen regardless of any button.
    """
    if power_held:
        if player.kick_cooldown <= 0.0:
            player.kick_charge = min(config.POWER_SHOT_CHARGE_SECONDS, player.kick_charge + dt)
        return KickResult(fired=False)

    charge = player.kick_charge
    player.kick_charge = 0.0
    if charge <= 0.0 or player.kick_cooldown > 0.0:
        return KickResult(fired=False)

    fraction = physics.clamp(charge / config.POWER_SHOT_CHARGE_SECONDS, 0.0, 1.0)
    player.kick_pose_timer = config.KICK_POSE_HOLD_SECONDS
    result = _strike(player, ball, fraction)
    if result.fired:
        player.kick_cooldown = config.KICK_COOLDOWN_SECONDS + config.POWER_SHOT_COOLDOWN_BONUS_SECONDS * fraction
    return result


def apply_head_collision(
    player: Player, ball: Ball, on_impact: Optional[Callable[[], None]] = None
) -> bool:
    """The passive header bounce: the ball rebounds off the player's head
    circle whenever they overlap, whether or not a kick was pressed."""
    hx, hy = player.head_center
    return physics.resolve_circle_collision(
        ball,
        hx,
        hy,
        config.HEAD_RADIUS,
        config.BALL_RESTITUTION_HEAD,
        extra_lift=config.HEADER_LIFT,
        on_impact=on_impact,
        contact_id=f"head:{player.sprite_key}",
        collider_velocity=(player.vx, player.vy),
    )


def apply_body_collision(player: Player, ball: Ball) -> bool:
    """The passive body block: the ball is blocked (not bounced) by the
    player's torso+legs AABB (see :func:`body_rect`) whenever they
    overlap. Deliberately low restitution (config.BALL_RESTITUTION_BODY)
    so a body hit reads as being blocked, not headed -- heading (see
    :func:`apply_head_collision`) is the genre's actual scoring
    mechanic, and the body must never out-bounce the head. This is the
    fix for the ball passing straight through a player's torso/legs: the
    head circle used to be the *only* collider on the whole body.
    """
    left, top, right, bottom = body_rect(player)
    return physics.resolve_circle_aabb_collision(
        ball, left, top, right, bottom, config.BALL_RESTITUTION_BODY, (player.vx, player.vy)
    )
