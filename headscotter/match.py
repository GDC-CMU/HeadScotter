"""Match rules: the 90-second clock, goal scoring, most-goals-wins, and
sudden death.

Pure logic, no :mod:`pygame` import. Also owns the tiny "most goals
scored in a won 1-player match" record file -- the closest analogue to a
high score this game has -- resolved from this file's location so it
survives regardless of the launcher's working directory, and silently a
no-op if the filesystem can't be written to.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from . import config

Side = str  # "left" or "right"


class MatchPhase(Enum):
    KICKOFF = auto()             # brief freeze before the ball goes live
    PLAYING = auto()
    GOAL_CELEBRATION = auto()    # brief freeze right after a goal
    FULL_TIME = auto()


@dataclass
class MatchState:
    score_left: int = 0
    score_right: int = 0
    time_remaining: float = config.MATCH_SECONDS
    phase: MatchPhase = MatchPhase.KICKOFF
    phase_timer: float = config.KICKOFF_FREEZE_SECONDS
    sudden_death: bool = False
    last_scoring_side: Optional[Side] = None


def new_match() -> MatchState:
    return MatchState()


def is_ball_live(state: MatchState) -> bool:
    """Whether players/CPU/ball physics should actually be simulated this
    frame -- false during the brief kickoff and goal-celebration freezes."""
    return state.phase is MatchPhase.PLAYING


def is_match_over(state: MatchState) -> bool:
    return state.phase is MatchPhase.FULL_TIME


def winner(state: MatchState) -> Optional[Side]:
    """``None`` only if the scores are exactly level -- which cannot
    happen once :attr:`MatchState.phase` is FULL_TIME, since a tie at
    time-up always continues into sudden death instead."""
    if state.score_left == state.score_right:
        return None
    return "left" if state.score_left > state.score_right else "right"


def tick(state: MatchState, dt: float) -> None:
    """Advance the match clock/phase timers by one frame. Does not touch
    the ball or players -- see match.is_ball_live()/game.py for that."""
    if state.phase is MatchPhase.FULL_TIME:
        return

    if state.phase is MatchPhase.KICKOFF:
        state.phase_timer = max(0.0, state.phase_timer - dt)
        if state.phase_timer <= 0.0:
            state.phase = MatchPhase.PLAYING
        return

    if state.phase is MatchPhase.GOAL_CELEBRATION:
        state.phase_timer = max(0.0, state.phase_timer - dt)
        if state.phase_timer <= 0.0:
            state.phase = MatchPhase.KICKOFF
            state.phase_timer = config.KICKOFF_FREEZE_SECONDS
        return

    # PLAYING.
    if state.sudden_death:
        return  # sudden death has no clock: the next goal simply ends it
    state.time_remaining = max(0.0, state.time_remaining - dt)
    if state.time_remaining <= 0.0:
        if state.score_left == state.score_right:
            state.sudden_death = True
        else:
            state.phase = MatchPhase.FULL_TIME


def register_goal(state: MatchState, side: Side) -> None:
    """Record a goal for ``side`` ("left" scored, or "right" scored).
    In sudden death this immediately ends the match; otherwise it starts
    the brief goal-celebration freeze before the next kickoff."""
    if side == "left":
        state.score_left += 1
    else:
        state.score_right += 1
    state.last_scoring_side = side

    if state.sudden_death:
        state.phase = MatchPhase.FULL_TIME
        return

    state.phase = MatchPhase.GOAL_CELEBRATION
    state.phase_timer = config.GOAL_CELEBRATION_SECONDS


# --- "Most goals in a won 1P match" record --------------------------------------

def load_high_score() -> int:
    try:
        with open(config.HIGHSCORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        value = int(data.get("best_goals_in_a_win", 0))
        return max(0, value)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def save_high_score(value: int) -> None:
    """Best-effort write; a read-only checkout must never crash the game."""
    try:
        with open(config.HIGHSCORE_PATH, "w", encoding="utf-8") as handle:
            json.dump({"best_goals_in_a_win": int(value)}, handle)
    except OSError:
        pass


def maybe_record_high_score(goals_scored_by_winner: int) -> int:
    """Update and return the persisted record if ``goals_scored_by_winner``
    beats it; otherwise return the unchanged existing record. Callers
    (game.py) only call this for a genuine 1-player win -- never for a 2P
    match and never for the attract-mode demo."""
    current = load_high_score()
    if goals_scored_by_winner > current:
        save_high_score(goals_scored_by_winner)
        return goals_scored_by_winner
    return current
