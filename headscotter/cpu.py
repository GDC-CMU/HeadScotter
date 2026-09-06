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

import math
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
    #: The x-coordinate of the goal *this* CPU defends -- config.PITCH_RIGHT
    #: for a CPU on the right (the common case, the 1P-mode opponent), or
    #: config.PITCH_LEFT for a CPU on the left (only used when both sides
    #: are CPU-controlled, i.e. the attract-mode demo). Used only to bound
    #: how far forward it will chase the ball -- see _defensive_target_x().
    defend_x: float = config.PITCH_RIGHT

    _perception_timer: float = field(default=0.0, repr=False)
    _known_ball_x: float = field(default=0.0, repr=False)
    _known_ball_y: float = field(default=0.0, repr=False)
    _known_ball_vx: float = field(default=0.0, repr=False)
    _known_ball_vy: float = field(default=0.0, repr=False)
    _aim_error: float = field(default=0.0, repr=False)
    _has_perceived: bool = field(default=False, repr=False)
    #: Whether the ball was in kick range on the *previous* call -- see
    #: the note at the ``kick`` computation in :meth:`update` on why this
    #: must be edge-triggered, not a level signal.
    _kick_was_in_range: bool = field(default=False, repr=False)
    #: Whether this CPU's kick was on cooldown on the *previous* call --
    #: see the note at the ``kick`` computation on why a cooldown clearing
    #: must give a fresh kick opportunity even if the ball never left range.
    _was_on_cooldown: bool = field(default=False, repr=False)

    def reset(self) -> None:
        """Forget everything perceived so far (used at kickoff)."""
        self._perception_timer = 0.0
        self._has_perceived = False
        self._aim_error = 0.0
        self._kick_was_in_range = False
        self._was_on_cooldown = False

    def update(self, dt: float, ball: Ball, player: Player, force_full_advance: bool = False) -> CPUIntent:
        self._perceive(dt, ball)

        target_x = physics.clamp(
            self._defensive_target_x(force_full_advance) + self._aim_error,
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
        # Edge-triggered, not a level signal: players.update_kick() now
        # charges a power shot for as long as its "kick" input is held,
        # firing only on release (see config.POWER_SHOT_*). A CPU's
        # in-range check is a *condition*, true for as many consecutive
        # frames as the ball happens to sit in its kick box -- treating
        # that directly as "held" made every CPU kick charge to a near-
        # full power shot almost every time, which blew scoring far past
        # any sane band. Firing only on the rising edge (the first frame
        # the ball enters range) reproduces a human's quick tap-and-kick
        # instead, so the CPU kicks at ordinary strength like it always
        # did -- confirmed by re-running the full-match balance
        # simulation (see tests/test_balance.py) before and after.
        #
        # But a *pure* rising edge alone can permanently latch off: a
        # ball that comes to rest and simply never leaves kick range
        # would only ever fire once, on the very first frame it arrived
        # -- confirmed by simulation to genuinely deadlock a match
        # forever (a resting ball a player could always reach, but never
        # kicked again). So a cooldown clearing while the ball is still
        # sitting in range also counts as a fresh opportunity, exactly
        # like a human tapping the button again once they're able to --
        # this still fires as a single one-frame pulse each time (a tap,
        # not a hold), so it never risks charging a power shot either.
        cooldown_just_cleared = self._was_on_cooldown and player.kick_cooldown <= 0.0
        self._was_on_cooldown = player.kick_cooldown > 0.0
        if cooldown_just_cleared:
            self._kick_was_in_range = False

        kick = in_kick_range and not self._kick_was_in_range and player.kick_cooldown <= 0.0
        self._kick_was_in_range = in_kick_range

        return CPUIntent(move=move, jump=jump, kick=kick)

    def _defensive_target_x(self, force_full_advance: bool = False) -> float:
        """Where this CPU wants to stand, x-wise: the ball's perceived
        position, but never advanced further from its own goal than
        ``config.CPU_MAX_ADVANCE_FRACTION`` of the pitch width.

        Without this, both CPUs simply chase the ball wherever it goes --
        which leaves both goals completely unguarded at the same time and
        both players clumped in the middle of the pitch. This is a
        deliberately simple stand-in for a dedicated goalkeeper (the genre
        doesn't have one; see assets/README.md and the club's other
        cabinet games for the same "no separate keeper" convention): each
        field player instead holds a defensive line rather than fully
        committing forward, exactly like the real single-defender AI
        pattern used in 2D head-soccer clones. It does not affect
        jump/kick decisions at all -- those still react to the ball
        wherever it actually is, so a clearance that lands near a
        deep-lying defender is still headed/kicked away normally.

        The cap is lifted entirely while the ball is essentially at rest
        (perceived speed below ``config.CPU_RESTING_SPEED_PX``): a ball
        that has stopped moving is not an attacking threat worth holding
        a defensive line against, and always going to retrieve it is what
        stops a dead ball that happens to settle outside this CPU's
        advance limit -- e.g. facing a human who isn't moving at all --
        from being permanently unreachable and stalling the match forever.

        ``force_full_advance`` is the anti-stalemate override (see
        ``config.CPU_STALEMATE_SECONDS``, set by the caller once neither
        side has scored in a while): it lifts the cap the same way a
        resting ball does, regardless of the ball's actual speed, so a
        prolonged deadlock always eventually breaks.
        """
        pitch_width = config.PITCH_RIGHT - config.PITCH_LEFT
        advance = config.CPU_MAX_ADVANCE_FRACTION * pitch_width
        ball_speed = math.hypot(self._known_ball_vx, self._known_ball_vy)
        if force_full_advance or ball_speed < config.CPU_RESTING_SPEED_PX:
            return self._known_ball_x
        if self.defend_x >= config.PITCH_CENTER_X:  # defends the right goal
            limit_x = self.defend_x - advance
            return max(self._known_ball_x, limit_x)
        else:  # defends the left goal
            limit_x = self.defend_x + advance
            return min(self._known_ball_x, limit_x)

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
            # Mirror the real ball's ground collision: without this, a
            # ball that is genuinely at rest on the ground (real vy == 0,
            # held there every frame by physics.step_ball's ground snap)
            # would still be extrapolated as if gravity kept accelerating
            # it downward, fabricating an ever-growing "falling" velocity
            # for a ball that isn't moving at all -- which was silently
            # defeating the CPU_RESTING_SPEED_PX check in
            # _defensive_target_x() for most of the time between
            # perception ticks.
            ground_y = config.GROUND_Y - config.BALL_RADIUS
            if self._known_ball_y >= ground_y:
                self._known_ball_y = ground_y
                self._known_ball_vy = 0.0

