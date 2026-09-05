"""The automated goalkeeper defending each goal mouth.

Every goal has one, in every mode (1P/2P/DEMO) -- it is never controlled
by a human or by the CPU field-player AI. A keeper is a simple vertical
"paddle": it stands at a fixed depth in front of its own goal line (see
config.KEEPER_DEPTH) and only moves up/down to line up with the ball's
height within the goal mouth, the same "track the ball, react late,
imperfect aim" pattern as :mod:`headscotter.cpu`'s field-player AI, so it
is beatable rather than a wall.

Pure logic, no :mod:`pygame` import.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import config, physics
from .physics import Ball


def _ready_y() -> float:
    """Vertically centered in the goal mouth -- where a keeper waits
    with no better information yet."""
    return (config.CROSSBAR_Y + config.GROUND_Y) / 2.0


def _keeper_x(goal_x: float) -> float:
    """A fixed point KEEPER_DEPTH in front of the goal line, toward the
    pitch center -- never further, so a shot placed past this depth
    (not just past the keeper's current height) can beat it."""
    if goal_x <= config.PITCH_CENTER_X:
        return goal_x + config.KEEPER_DEPTH
    return goal_x - config.KEEPER_DEPTH


@dataclass
class Keeper:
    goal_x: float  # which goal line this keeper defends: config.PITCH_LEFT or PITCH_RIGHT
    x: float
    y: float

    _perception_timer: float = field(default=0.0, repr=False)
    _target_y: float = field(default=0.0, repr=False)


def new_keeper(goal_x: float) -> Keeper:
    return Keeper(goal_x=goal_x, x=_keeper_x(goal_x), y=_ready_y(), _target_y=_ready_y())


def reset_keeper(keeper: Keeper) -> None:
    """Return to the ready position (used at every kickoff)."""
    keeper.x = _keeper_x(keeper.goal_x)
    keeper.y = _ready_y()
    keeper._target_y = _ready_y()
    keeper._perception_timer = 0.0


def update_keeper(keeper: Keeper, dt: float, ball: Ball, rng: random.Random) -> None:
    """Advance the keeper's vertical position by one frame: re-read the
    ball's height (with a reaction delay and random aim error, on the
    same fixed-tick pattern as the CPU field players -- see
    config.KEEPER_REACTION_DELAY_SECONDS/KEEPER_AIM_ERROR_PX), then glide
    toward that target at a capped speed. A shot that changes height
    faster than the keeper can react, or is aimed with better precision
    than KEEPER_AIM_ERROR_PX allows for, can still beat it."""
    keeper._perception_timer += dt
    if keeper._perception_timer >= config.KEEPER_REACTION_DELAY_SECONDS:
        keeper._perception_timer = 0.0
        error = rng.uniform(-config.KEEPER_AIM_ERROR_PX, config.KEEPER_AIM_ERROR_PX)
        low = config.CROSSBAR_Y + config.KEEPER_RADIUS
        high = config.GROUND_Y - config.KEEPER_RADIUS
        keeper._target_y = physics.clamp(ball.y + error, low, high)

    dy = keeper._target_y - keeper.y
    max_step = config.KEEPER_SPEED * dt
    if abs(dy) <= max_step:
        keeper.y = keeper._target_y
    else:
        keeper.y += max_step if dy > 0 else -max_step


def apply_keeper_collision(keeper: Keeper, ball: Ball) -> bool:
    """The passive save: the ball bounces off the keeper whenever they
    overlap, regardless of any button -- there is no input to press a
    keeper never receives one."""
    return physics.resolve_circle_collision(
        ball, keeper.x, keeper.y, config.KEEPER_RADIUS, config.KEEPER_RESTITUTION,
    )
