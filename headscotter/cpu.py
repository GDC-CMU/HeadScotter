"""An imperfect, physical 1v1 side-view head-soccer opponent.

Observe ball/opponent on a delayed tick, forecast only that stale observation,
then intercept, recover a threatened goal, or set up an attacking touch. The
controller only returns the same movement/jump/kick/power intents as a human.
It never mutates real actors, sees future input, or changes physical rules.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from typing import Optional

from . import config, physics, players
from .physics import Ball
from .players import Player


@dataclass
class CPUIntent:
    move: int = 0
    jump: bool = False
    normal_kick: bool = False
    power_held: bool = False


def _copy_ball(ball: Ball) -> Ball:
    return Ball(ball.x, ball.y, ball.vx, ball.vy, ball.radius)


def _forecast_step(ball: Ball, dt: float, opponent: Optional[Player] = None) -> Optional[str]:
    """Shared physical rules, using only an extrapolated observed opponent."""
    steps = max(1, math.ceil(ball.speed() * dt / config.BALL_MAX_STEP_PX))
    for _ in range(steps):
        if opponent is not None:
            players.apply_head_collision(opponent, ball)
            players.apply_body_collision(opponent, ball)
        event = physics.step_ball(ball, dt / steps)
        if event:
            return event
    return None


@dataclass
class CPUController:
    rng: random.Random = field(default_factory=random.Random)
    defend_x: float = config.PITCH_RIGHT
    _perception_timer: float = field(default=0.0, repr=False)
    _known_ball_x: float = field(default=0.0, repr=False)
    _known_ball_y: float = field(default=0.0, repr=False)
    _known_ball_vx: float = field(default=0.0, repr=False)
    _known_ball_vy: float = field(default=0.0, repr=False)
    _known_ball_radius: float = field(default=config.BALL_RADIUS, repr=False)
    _opponent: Optional[Player] = field(default=None, repr=False)
    _trajectory: list = field(default_factory=list, repr=False)
    _predicted_goal: Optional[str] = field(default=None, repr=False)
    _aim_error: float = field(default=0.0, repr=False)
    _has_perceived: bool = field(default=False, repr=False)
    _kick_retry_remaining: float = field(default=0.0, repr=False)
    _jump_retry_remaining: float = field(default=0.0, repr=False)
    _cross_direction: int = field(default=0, repr=False)
    _cross_remaining: float = field(default=0.0, repr=False)
    _cross_target_x: float = field(default=0.0, repr=False)
    _header_target_x: Optional[float] = field(default=None, repr=False)
    tactic: str = "intercept"  # diagnostic only; no HUD/control changes

    @property
    def attack_direction(self) -> int:
        return -1 if self.defend_x >= config.PITCH_CENTER_X else 1

    def reset(self) -> None:
        """Kickoff forgets observations, predictions and jump commitments."""
        self._perception_timer = 0.0
        self._has_perceived = False
        self._aim_error = 0.0
        self._opponent = None
        self._trajectory.clear()
        self._predicted_goal = None
        self._kick_retry_remaining = 0.0
        self._jump_retry_remaining = 0.0
        self._cross_direction = 0
        self._cross_remaining = 0.0
        self._cross_target_x = 0.0
        self._header_target_x = None
        self.tactic = "intercept"

    def update(self, dt: float, ball: Ball, player: Player, opponent: Optional[Player] = None) -> CPUIntent:
        self._perceive(dt, ball, opponent)
        self._kick_retry_remaining = max(0.0, self._kick_retry_remaining - dt)
        self._jump_retry_remaining = max(0.0, self._jump_retry_remaining - dt)
        self._cross_remaining = max(0.0, self._cross_remaining - dt)
        attack = self.attack_direction
        known = self._known_ball()
        own_goal = "right_goal" if attack < 0 else "left_goal"
        threat = self._predicted_goal == own_goal or (
            known.vx * attack < -config.CPU_THREAT_SPEED_PX
            and (known.x - player.x) * attack < config.CPU_SHOT_SETUP_PX
            and abs(known.x - self.defend_x) < config.CPU_RECOVERY_ZONE_PX
        )
        self.tactic = "defend" if threat else "intercept" if known.y < config.GROUND_Y - 100 else "attack"

        # Commit an uncommitted charge to its outward-facing stance. Steering
        # back to the setup point mid-charge would otherwise turn the release
        # into a whiff/own-goal, or alternate charging and cancelling forever.
        # Pause cancellation is automatic: Game clears player.kick_charge.
        if player.kick_charge > 0.0:
            controlled = (
                abs(known.x - (player.x + attack * config.KICK_RANGE_X * 0.5)) <= config.KICK_RANGE_X
                and abs(known.y - (player.y - config.KICK_RANGE_Y * 0.5)) <= config.KICK_RANGE_Y
            )
            hold = controlled and not threat and player.kick_charge < config.POWER_SHOT_CHARGE_SECONDS
            return CPUIntent(power_held=hold)

        target = self._intercept_target(player)
        if player.on_ground:
            self._header_target_x = None
        elif self._header_target_x is not None:
            target = self._header_target_x
            self.tactic = "header"
        move = self._steer(target - player.x)

        # Once airborne, finish crossing the obstacle instead of reversing
        # when a fresh ball observation happens to move the tactical target.
        if self._cross_direction:
            if not player.on_ground and self._cross_remaining > 0.0:
                self.tactic = "cross"
                move = self._cross_direction if (
                    (self._cross_target_x - player.x) * self._cross_direction > config.CPU_MOVE_DEADZONE_PX
                ) else 0
                return CPUIntent(move=move)
            self._cross_direction = 0

        jump = False
        opponent = self._opponent  # only the delayed observation below is used
        if player.on_ground and self._jump_retry_remaining <= 0.0 and move:
            obstacle_x = None
            if opponent is not None and (opponent.x - player.x) * move > 0:
                if (target - opponent.x) * move > -config.PLAYER_HALF_WIDTH:
                    obstacle_x = opponent.x
            # Recover to the useful side of a low ball without walking it
            # into our own goal with the body collider.
            if (obstacle_x is None and move == -attack and known.speed() <= config.CPU_CONTROL_SPEED_PX
                    and known.y > player.y - config.HEAD_OFFSET_Y):
                if (known.x - player.x) * move > config.KICK_RANGE_X * 0.5 and (target - known.x) * move > 0:
                    obstacle_x = known.x
            if obstacle_x is not None:
                gap = (obstacle_x - player.x) * move
                opponent_vx = self._opponent_vx() if opponent and obstacle_x == opponent.x else 0.0
                closing = max(config.PLAYER_SPEED, config.PLAYER_SPEED - move * opponent_vx)
                # Center the crossing near the natural jump apex; all geometry
                # comes from the human body/jump constants, not extra CPU speed.
                trigger = closing * (-config.JUMP_VELOCITY / config.GRAVITY)
                if gap <= trigger + config.CPU_CROSS_MARGIN_PX:
                    blocker = opponent if opponent is not None and obstacle_x == opponent.x else None
                    if self._crossing_clear(player, move, blocker):
                        jump = True
                        self._cross_direction = move
                        self._cross_remaining = -2 * config.JUMP_VELOCITY / config.GRAVITY + dt
                        if opponent is not None and obstacle_x == opponent.x:
                            self._cross_target_x = obstacle_x + move * (
                                2 * config.PLAYER_HALF_WIDTH + config.CPU_CROSS_MARGIN_PX
                            )
                        else:
                            self._cross_target_x = target
                        self.tactic = "cross"
                    else:
                        move = 0  # let a simultaneous jumping blocker descend

        if not jump and player.on_ground and self._jump_retry_remaining <= 0.0:
            header_target = self._header_plan(player)
            if header_target is not None:
                jump = True
                self._header_target_x = header_target
                move = self._steer(header_target - player.x)
                self.tactic = "header"
        if jump:
            self._jump_retry_remaining = config.CPU_JUMP_RETRY_SECONDS

        # Use the facing that apply_move will produce THIS frame, and a
        # low foot-height ball. High touches belong to the head, not a kick
        # that would suppress the passive header in Game's collision loop.
        goal_side = (known.x - player.x) * attack >= -config.CPU_MOVE_DEADZONE_PX
        close = abs(known.x - (player.x + attack * config.KICK_RANGE_X * 0.5)) <= config.KICK_RANGE_X
        if not jump and not self._cross_direction and close and (goal_side or threat):
            if move == 0 and player.facing != attack:
                move = attack
        next_x = player.x + move * config.PLAYER_SPEED * dt
        facing = move or player.facing
        in_range = (
            abs(known.x - (next_x + facing * config.KICK_RANGE_X * 0.5)) <= config.KICK_RANGE_X
            and abs(known.y - (player.y - config.KICK_RANGE_Y * 0.5)) <= config.KICK_RANGE_Y
            and known.y >= player.y - config.HEAD_OFFSET_Y + config.HEAD_RADIUS * 0.5
        )
        # Let a steep rebound rise into a header instead of flattening it
        # into another low kick straight at the defender's body.
        can_shoot = (in_range and facing == attack and not jump and not self._cross_direction
                     and not (self._header_target_x is not None and not player.on_ground)
                     and (threat or known.vy >= -config.CPU_RISING_SHOT_SPEED_PX))
        power = False
        if can_shoot and player.on_ground and not threat and player.kick_cooldown <= 0.0:
            goal_x = config.PITCH_LEFT if attack < 0 else config.PITCH_RIGHT
            blocked_shot = opponent is not None and (opponent.x - known.x) * attack > 0
            if player.kick_charge > 0.0 or (
                known.speed() <= config.CPU_CONTROL_SPEED_PX
                and (abs(known.x - goal_x) > config.CPU_POWER_DISTANCE_PX or blocked_shot)
            ):
                power = player.kick_charge < config.POWER_SHOT_CHARGE_SECONDS
                if power:
                    already_in_range = abs(known.x - (player.x + attack * config.KICK_RANGE_X * 0.5)) <= config.KICK_RANGE_X
                    if player.facing == attack and already_in_range:
                        move = 0
                    else:
                        move = attack

        # A real power release is distinct from a normal press. Never send
        # both on the same frame; recovery still cannot gate normal attempts.
        kick = can_shoot and not power and player.kick_charge <= 0.0 and self._kick_retry_remaining <= 0.0
        if kick:
            self._kick_retry_remaining = config.KICK_COOLDOWN_SECONDS
        return CPUIntent(move=move, jump=jump, normal_kick=kick, power_held=power)

    @staticmethod
    def _steer(dx: float) -> int:
        return 0 if abs(dx) <= config.CPU_MOVE_DEADZONE_PX else (1 if dx > 0 else -1)

    def _intercept_target(self, player: Player) -> float:
        attack = self.attack_direction
        chosen = self._known_ball()
        max_jump = config.JUMP_VELOCITY ** 2 / (2 * config.GRAVITY)
        reachable_top = config.GROUND_Y - config.PLAYER_HEIGHT - max_jump - chosen.radius
        # Earliest reachable forecast, not a blanket leash to our own half.
        # If no intercept is reachable yet, run toward the final forecast.
        for at, sample in self._trajectory:
            t = at - self._perception_timer
            if t < 0:
                continue
            chosen = sample
            setup = sample.x - attack * config.CPU_SHOT_SETUP_PX
            if sample.y >= reachable_top and abs(setup - player.x) <= config.PLAYER_SPEED * t + config.CPU_MOVE_DEADZONE_PX:
                break
        target = chosen.x - attack * config.CPU_SHOT_SETUP_PX + attack * self._aim_error
        opponent = self._opponent
        if opponent is not None and (chosen.x - opponent.x) * attack < 0:
            if abs(chosen.x - opponent.x) < config.HEAD_RADIUS + chosen.radius + config.CPU_CROSS_MARGIN_PX:
                # Don't sandwich a low ball between both heads. Leave room
                # for the defender's rebound to rise, then contest its arc.
                space = 2 * (config.HEAD_RADIUS + chosen.radius) + config.CPU_CROSS_MARGIN_PX
                target = opponent.x - attack * max(space, abs(target - opponent.x))
                # Space must still leave the ball reachable with the HUMAN
                # kick box, including our steering deadzone. Don't stop just
                # outside range and stare at a stationary defender forever.
                reach = config.KICK_RANGE_X * 1.5 - config.CPU_MOVE_DEADZONE_PX - config.CPU_CROSS_MARGIN_PX
                if (chosen.x - target) * attack > reach:
                    target = chosen.x - attack * reach
        return physics.clamp(target, config.PITCH_LEFT + config.PLAYER_HALF_WIDTH,
                             config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH)

    def _header_plan(self, player: Player) -> Optional[float]:
        """A reachable jump must make an incoming, forward-directed header.

        Merely intersecting an upward/separating ball is not a shot. Compare
        reachable goal-side contact points against the real head response,
        then commit to the useful point. Move and stop are ordinary inputs;
        a header need not require running flat-out for the entire jump.
        """
        best_target = None
        best_value = 0.0
        for at, sample in self._trajectory:
            t = at - self._perception_timer
            if t < config.CPU_PREDICTION_STEP or t > -2 * config.JUMP_VELOCITY / config.GRAVITY:
                continue
            if sample.y >= config.GROUND_Y - config.HEAD_OFFSET_Y:
                continue
            # Semi-implicit 60Hz human jump, not an enlarged CPU envelope.
            height = -config.JUMP_VELOCITY * t - 0.5 * config.GRAVITY * t * (t + 1 / 60)
            hy = config.GROUND_Y - height - config.HEAD_OFFSET_Y
            for offset in (config.CPU_SHOT_SETUP_PX, config.CPU_SHOT_SETUP_PX * 0.5):
                desired = sample.x - self.attack_direction * offset
                x = physics.clamp(desired,
                                  max(config.PITCH_LEFT + config.PLAYER_HALF_WIDTH, player.x - config.PLAYER_SPEED * t),
                                  min(config.PITCH_RIGHT - config.PLAYER_HALF_WIDTH, player.x + config.PLAYER_SPEED * t))
                dx, dy = sample.x - x, sample.y - hy
                distance = math.hypot(dx, dy)
                if distance < 1e-6 or distance >= config.HEAD_RADIUS + sample.radius - config.CPU_HEADER_MARGIN_PX:
                    continue
                incoming = (sample.vx * dx + sample.vy * dy) / distance
                if incoming >= -config.BALL_MIN_BOUNCE_SPEED:
                    continue
                headed = _copy_ball(sample)
                physics.resolve_circle_collision(headed, x, hy, config.HEAD_RADIUS,
                                                 config.BALL_RESTITUTION_HEAD, config.HEADER_LIFT)
                value = headed.vx * self.attack_direction - max(0.0, headed.vy) * 0.25
                if value > best_value:
                    best_value, best_target = value, x
        return best_target

    def _crossing_clear(self, player: Player, direction: int, opponent: Optional[Player]) -> bool:
        if opponent is None:
            return True
        own, other = replace(player), replace(opponent)
        players.apply_jump(own)
        crossed = False
        step = 1 / 60.0
        for _ in range(math.ceil((-2 * config.JUMP_VELOCITY / config.GRAVITY) / step)):
            players.step_player_physics(own, step)
            players.apply_move(other, other.facing if other.moving else 0, step)
            players.step_player_physics(other, step)
            next_x = own.x + direction * config.PLAYER_SPEED * step
            overlap = abs(next_x - other.x) < 2 * config.PLAYER_HALF_WIDTH
            if overlap and abs(own.y - other.y) < config.PLAYER_HEIGHT:
                # Rise before entering the footprint, or wait for a jumper.
                continue
            own.x = next_x
            if (own.x - other.x) * direction > 2 * config.PLAYER_HALF_WIDTH + config.CPU_CROSS_MARGIN_PX:
                crossed = True
            if own.on_ground:
                break
        return crossed

    def _opponent_vx(self) -> float:
        return self._opponent.facing * config.PLAYER_SPEED if self._opponent and self._opponent.moving else 0.0

    def _known_ball(self) -> Ball:
        return Ball(self._known_ball_x, self._known_ball_y, self._known_ball_vx,
                    self._known_ball_vy, self._known_ball_radius)

    def _store_ball(self, ball: Ball) -> None:
        self._known_ball_x, self._known_ball_y = ball.x, ball.y
        self._known_ball_vx, self._known_ball_vy = ball.vx, ball.vy
        self._known_ball_radius = ball.radius

    def _perceive(self, dt: float, ball: Ball, opponent: Optional[Player] = None) -> None:
        self._perception_timer += dt
        if not self._has_perceived or self._perception_timer >= config.CPU_REACTION_DELAY_SECONDS:
            self._perception_timer = 0.0
            self._has_perceived = True
            self._store_ball(ball)
            self._opponent = replace(opponent) if opponent is not None else None
            self._aim_error = self.rng.uniform(-config.CPU_AIM_ERROR_PX, config.CPU_AIM_ERROR_PX)
            predicted = _copy_ball(ball)
            other = replace(self._opponent) if self._opponent is not None else None
            self._trajectory = [(0.0, _copy_ball(predicted))]
            self._predicted_goal = None
            for tick in range(1, math.ceil(config.CPU_PREDICTION_SECONDS / config.CPU_PREDICTION_STEP) + 1):
                if other is not None:
                    players.apply_move(other, other.facing if other.moving else 0, config.CPU_PREDICTION_STEP)
                    players.step_player_physics(other, config.CPU_PREDICTION_STEP)
                event = _forecast_step(predicted, config.CPU_PREDICTION_STEP, other)
                self._trajectory.append((tick * config.CPU_PREDICTION_STEP, _copy_ball(predicted)))
                if event:
                    self._predicted_goal = event
                    break
        else:
            predicted = self._known_ball()
            if self._opponent is not None:
                players.apply_move(self._opponent, self._opponent.facing if self._opponent.moving else 0, dt)
                players.step_player_physics(self._opponent, dt)
            _forecast_step(predicted, dt, self._opponent)
            self._store_ball(predicted)
