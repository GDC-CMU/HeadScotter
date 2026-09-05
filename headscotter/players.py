"""Player movement, jumping, and kicking.

Pure logic, no :mod:`pygame` import: everything here operates on plain
dataclasses and the shared physics helpers in :mod:`headscotter.physics`.
:mod:`headscotter.game` translates real input into the ``move``/
``jump_pressed``/``kick_pressed`` values these functions take.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from . import config, physics
from .physics import Ball


@dataclass
class Player:
    """One head-soccer character. ``x``/``y`` track the *feet* position;
    the collidable "head" circle is derived from it (see
    :attr:`head_center`). ``sprite_key`` is a pure display label
    (e.g. "scotty" or "rival") consumed only by render.py."""

    x: float
    y: float = config.GROUND_Y
    vy: float = 0.0
    facing: int = 1              # +1 faces right, -1 faces left
    on_ground: bool = True
    moving: bool = False
    kick_cooldown: float = 0.0
    sprite_key: str = "scotty"

    @property
    def head_center(self) -> Tuple[float, float]:
        return (self.x, self.y - config.HEAD_OFFSET_Y)

    @property
    def just_kicked(self) -> bool:
        """True for the short window right after a kick fires (cooldown
        freshly set to its maximum) -- used only by render.py to pick a
        kick pose; carries no gameplay meaning of its own."""
        return self.kick_cooldown > (config.KICK_COOLDOWN_SECONDS * 0.6)


def new_player(x: float, facing: int, sprite_key: str = "scotty") -> Player:
    return Player(x=x, y=config.GROUND_Y, facing=facing, sprite_key=sprite_key)


def apply_move(player: Player, move: int, dt: float) -> None:
    """``move`` is -1 (left), 0 (still), or +1 (right)."""
    player.moving = move != 0
    if move != 0:
        player.facing = 1 if move > 0 else -1
    player.x += move * config.PLAYER_SPEED * dt
    player.x = physics.clamp(
        player.x,
        config.PITCH_LEFT + config.PLAYER_HALF_WIDTH,
        config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH,
    )


def apply_jump(player: Player) -> None:
    if player.on_ground:
        player.vy = config.JUMP_VELOCITY
        player.on_ground = False


def step_player_physics(player: Player, dt: float) -> None:
    player.vy = physics.apply_gravity(player.vy, dt)
    player.y += player.vy * dt
    if player.y >= config.GROUND_Y:
        player.y = config.GROUND_Y
        player.vy = 0.0
        player.on_ground = True
    if player.kick_cooldown > 0.0:
        player.kick_cooldown = max(0.0, player.kick_cooldown - dt)


def update_player(player: Player, dt: float, move: int, jump_pressed: bool) -> None:
    """The full per-frame update for one player's own body, excluding the
    ball interactions (see :func:`try_kick` / :func:`apply_head_collision`,
    called separately once both players have moved)."""
    apply_move(player, move, dt)
    if jump_pressed:
        apply_jump(player)
    step_player_physics(player, dt)


def separate_players(a: Player, b: Player) -> bool:
    """Push two overlapping player bodies apart horizontally so they can
    never interpenetrate. Call this once per frame after both players
    have moved (:func:`update_player`) and before any ball interaction,
    so a kick/header resolves from an already-legal, separated position.

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


def separate_player_from_keeper(player: Player, keeper_x: float, keeper_y: float) -> bool:
    """Push a player out of an overlapping keeper -- one-sided, unlike
    :func:`separate_players`: the keeper never moves (it is a paddle
    pinned at a fixed depth in front of its own goal line; letting a
    player shove it sideways would let the player drag it clean out of
    the goal and walk the ball in), so the player alone absorbs the
    *entire* overlap.

    Gated on overlap in **both** axes, the same rule as
    :func:`separate_players` and for the same reason: a player who has
    jumped clear over the keeper's head (e.g. attempting a lob) is not
    colliding with it and must be left alone. The keeper's collider is a
    ``KEEPER_RADIUS`` circle centered on ``keeper_y``; the player's body
    is its usual feet-to-head-top ``PLAYER_HEIGHT`` box.

    The player is pushed toward whichever side of the keeper it is
    already on -- in practice this is away from the goal line, back
    toward the pitch, since a keeper standing at ``KEEPER_DEPTH`` in
    front of its own goal line leaves only a sliver of room on the
    goal-line side for a player to occupy in the first place. Clamped to
    the pitch bounds afterward like any other player movement.

    Returns True if a separation was applied; a player that doesn't
    overlap the keeper is left completely untouched.
    """
    dx = player.x - keeper_x
    footprint = config.KEEPER_RADIUS + config.PLAYER_HALF_WIDTH
    if abs(dx) >= footprint:
        return False  # no horizontal overlap

    player_top = player.y - config.PLAYER_HEIGHT
    player_bottom = player.y
    keeper_top = keeper_y - config.KEEPER_RADIUS
    keeper_bottom = keeper_y + config.KEEPER_RADIUS
    if player_bottom <= keeper_top or keeper_bottom <= player_top:
        return False  # no vertical overlap -- e.g. the player jumped clean over it

    overlap = footprint - abs(dx)
    if overlap <= 0.0:
        return False

    # Push away from wherever the overlap actually places the player
    # relative to the keeper. On the rare exact tie (dx == 0), fall back
    # to pushing away from the nearer goal line instead of an arbitrary
    # default.
    if dx > 0.0:
        direction = 1.0
    elif dx < 0.0:
        direction = -1.0
    else:
        direction = 1.0 if keeper_x <= config.PITCH_CENTER_X else -1.0
    low = config.PITCH_LEFT + config.PLAYER_HALF_WIDTH
    high = config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH
    player.x = physics.clamp(player.x + direction * overlap, low, high)

    return True


def try_kick(player: Player, ball: Ball, kick_pressed: bool) -> bool:
    """If ``kick_pressed`` and the ball is within this player's kick
    hit-box (in front of them, at foot height) and their cooldown has
    elapsed, launch the ball and return True. A kick is a deliberate,
    fairly strong strike -- distinct from the passive header bounce in
    :func:`apply_head_collision`, which happens regardless of any button.
    """
    if not kick_pressed or player.kick_cooldown > 0.0:
        return False

    box_cx = player.x + player.facing * (config.KICK_RANGE_X * 0.5)
    box_cy = player.y - (config.KICK_RANGE_Y * 0.5)
    if abs(ball.x - box_cx) > config.KICK_RANGE_X or abs(ball.y - box_cy) > config.KICK_RANGE_Y:
        return False

    angle = math.radians(config.KICK_LAUNCH_ANGLE_DEG)
    ball.vx = player.facing * config.KICK_IMPULSE_SPEED * math.cos(angle)
    ball.vy = -config.KICK_IMPULSE_SPEED * math.sin(angle)
    player.kick_cooldown = config.KICK_COOLDOWN_SECONDS
    return True


def apply_head_collision(player: Player, ball: Ball) -> bool:
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
    )
