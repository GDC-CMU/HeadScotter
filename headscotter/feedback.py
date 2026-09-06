"""Bounded presentation state; never drives physics, input, or gameplay RNG."""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import config


@dataclass
class Mark:
    x: float
    y: float
    age: float = 0.0
    kind: str = "contact"


class MatchFeedback:
    def __init__(self, ball_x: float):
        self.impacts: list[Mark] = []
        self.trail: list[Mark] = []
        self.power_remaining = 0.0
        self.ready_remaining = [0.0, 0.0]
        self.previous_cooldowns = [0.0, 0.0]
        self.spin = 0.0
        self.previous_x = ball_x
        self.goal_side = None
        self.goal_age = 0.0

    def advance(self, dt: float) -> None:
        for mark in self.impacts + self.trail:
            mark.age += dt
        self.impacts = [m for m in self.impacts if m.age < config.IMPACT_FEEDBACK_SECONDS]
        self.trail = [m for m in self.trail if m.age < config.BALL_TRAIL_SECONDS]
        self.power_remaining = max(0.0, self.power_remaining - dt)
        self.ready_remaining = [max(0.0, value - dt) for value in self.ready_remaining]
        if self.goal_side is not None:
            self.goal_age += dt

    def observe(self, ball, players, dt: float) -> None:
        turn = math.degrees((ball.x - self.previous_x) / ball.radius)
        limit = config.BALL_SPIN_MAX_DEGREES * dt
        self.spin = (self.spin + max(-limit, min(limit, turn))) % 360.0
        moved = abs(ball.x - self.previous_x) > 1.0
        self.previous_x = ball.x
        if self.power_remaining > 0.0 and moved:
            self.trail.append(Mark(ball.x, ball.y, kind="power"))
            self.trail = self.trail[-config.BALL_TRAIL_LIMIT:]
        for index, player in enumerate(players):
            if self.previous_cooldowns[index] > 0.0 and player.kick_cooldown <= 0.0:
                self.ready_remaining[index] = config.POWER_READY_CUE_SECONDS
            self.previous_cooldowns[index] = player.kick_cooldown

    def impact(self, ball, kind: str) -> None:
        # One readable mark for a coupled contact, not one ring per solver surface.
        if not any(m.age < 1 / 30 and math.hypot(m.x - ball.x, m.y - ball.y) < ball.radius
                   for m in self.impacts):
            self.impacts.append(Mark(ball.x, ball.y, kind=kind))
            self.impacts = self.impacts[-config.IMPACT_FEEDBACK_LIMIT:]
        self.power_remaining = 0.0

    def shot(self, ball, powered: bool) -> None:
        self.impact(ball, "power" if powered else "kick")
        if powered:
            self.power_remaining = config.POWER_TRAIL_WINDOW

    def goal(self, side: str) -> None:
        self.goal_side = side
        self.goal_age = 0.0
        self.power_remaining = 0.0
