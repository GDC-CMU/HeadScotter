"""The 1-player mode's CPU opponent.

Deliberately imperfect and readable, not "AI": it tracks the ball, jumps
when it is overhead, and kicks when it is in range, but only *perceives*
the ball on a fixed tick (config.CPU_REACTION_DELAY_SECONDS) rather than
every frame, extrapolating a stale snapshot in between -- this is what
gives it a small, human-like reaction lag instead of frame-perfect
tracking, which is what makes it beatable. A fresh random aim error is
rolled every perception tick so it is never pixel-accurate even once it
has "seen" the ball.

Pure logic, no :mod:`pygame` import.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import config, physics
from .physics import Ball
from .players import Player


@dataclass
class CPUIntent:
    """One frame's decision: exactly what a human's inputs would resolve to."""

    move: int = 0
    jump: bool = False
    kick: bool = False


@dataclass
class CPUController:
    rng: random.Random = field(default_factory=random.Random)

    _perception_timer: float = field(default=0.0, repr=False)
    _known_ball_x: float = field(default=0.0, repr=False)
    _known_ball_y: float = field(default=0.0, repr=False)
    _known_ball_vx: float = field(default=0.0, repr=False)
    _known_ball_vy: float = field(default=0.0, repr=False)
    _aim_error: float = field(default=0.0, repr=False)
    _has_perceived: bool = field(default=False, repr=False)

    def reset(self) -> None:
        """Forget everything perceived so far (used at kickoff)."""
        self._perception_timer = 0.0
        self._has_perceived = False
        self._aim_error = 0.0

    def update(self, dt: float, ball: Ball, player: Player) -> CPUIntent:
        self._perceive(dt, ball)

        target_x = physics.clamp(
            self._known_ball_x + self._aim_error,
            config.PITCH_LEFT + config.PLAYER_HALF_WIDTH,
            config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH,
        )
        dx = target_x - player.x
        move = 0 if abs(dx) <= config.CPU_MOVE_DEADZONE_PX else (1 if dx > 0 else -1)

        ball_overhead = (
            abs(self._known_ball_x - player.x) <= config.CPU_JUMP_RANGE_X
            and self._known_ball_y < player.y - config.CPU_JUMP_BALL_HEIGHT
        )
        jump = ball_overhead and player.on_ground

        kick_box_cx = player.x + player.facing * (config.CPU_KICK_RANGE_X * 0.5)
        kick_box_cy = player.y - (config.CPU_KICK_RANGE_Y * 0.5)
        in_kick_range = (
            abs(self._known_ball_x - kick_box_cx) <= config.CPU_KICK_RANGE_X
            and abs(self._known_ball_y - kick_box_cy) <= config.CPU_KICK_RANGE_Y
        )
        kick = in_kick_range and player.kick_cooldown <= 0.0

        return CPUIntent(move=move, jump=jump, kick=kick)

    def _perceive(self, dt: float, ball: Ball) -> None:
        self._perception_timer += dt
        if not self._has_perceived or self._perception_timer >= config.CPU_REACTION_DELAY_SECONDS:
            self._perception_timer = 0.0
            self._has_perceived = True
            self._known_ball_x = ball.x
            self._known_ball_y = ball.y
            self._known_ball_vx = ball.vx
            self._known_ball_vy = ball.vy
            self._aim_error = self.rng.uniform(-config.CPU_AIM_ERROR_PX, config.CPU_AIM_ERROR_PX)
        else:
            # Extrapolate the stale snapshot forward with simple ballistic
            # motion so the CPU still looks like it is tracking the ball
            # between perception ticks -- just slightly behind reality.
            self._known_ball_vy += config.GRAVITY * dt
            self._known_ball_x += self._known_ball_vx * dt
            self._known_ball_y += self._known_ball_vy * dt
