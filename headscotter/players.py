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
