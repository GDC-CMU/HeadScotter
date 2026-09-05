"""Central tunables for HeadScotter.

Every knob that affects physics feel, timing, layout geometry, or input
mapping lives here so the rest of the codebase never hard-codes a magic
number -- the client explicitly asked for this because ball physics is
the thing most likely to need a tuning pass after real play-testing.

Modules other than :mod:`headscotter.render`, :mod:`headscotter.assets`
and :mod:`headscotter.game` avoid importing :mod:`pygame` so that game
logic stays testable without a display.
"""
from __future__ import annotations

import os

# --- Screen / arcade cabinet -------------------------------------------------
# The game always renders at this logical size; pygame.SCALED then letterboxes
# it onto whatever panel is actually fitted, so the cabinet and any laptop both
# get a correct picture without the game knowing the real display size.
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
WINDOW_TITLE = "HeadScotter"

#: Set this to run in a window instead of fullscreen. Fullscreen is the
#: default because that is how the cabinet is played; developing on a laptop
#: against a fullscreen window is painful, hence the escape hatch.
ENV_WINDOWED = "HEADSCOTTER_WINDOWED"


def windowed_requested() -> bool:
    """Whether ``HEADSCOTTER_WINDOWED`` asks for a window rather than fullscreen."""
    raw = os.environ.get(ENV_WINDOWED, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


# --- Pitch geometry -----------------------------------------------------------
# The HUD (score + clock) owns a strip across the top of the screen; the
# pitch itself is the rectangle below it. All of these are pixel coordinates
# in the 800x600 logical screen.
HUD_HEIGHT = 110

PITCH_TOP = 130       # invisible ceiling: the ball can never go above this
GROUND_Y = 520         # the grass line: players' feet and a resting ball sit here
PITCH_LEFT = 70        # left goal line (also the left player's movement limit)
PITCH_RIGHT = 730      # right goal line (also the right player's movement limit)
PITCH_CENTER_X = (PITCH_LEFT + PITCH_RIGHT) / 2.0

# Goal mouth: the vertical gap, right at PITCH_LEFT/PITCH_RIGHT, that counts
# as a goal instead of a wall bounce. Below CROSSBAR_Y (numerically closer to
# GROUND_Y) is the open net; at or above it is the solid crossbar/post, which
# just bounces the ball back into play like any other wall.
GOAL_MOUTH_HEIGHT = 170
CROSSBAR_Y = GROUND_Y - GOAL_MOUTH_HEIGHT

# --- Player geometry ------------------------------------------------------------
# Head-soccer characters are drawn with a big head and a small body; against
# the *ball*, only the head is a solid collider (matching the genre -- the
# body doesn't head/kick the ball). Against *each other*, both players'
# whole bodies block one another (see players.separate_players()) so
# closing distance actually means something. All distances below are from
# the player's feet anchor (x, y), which is what players.Player.x/y track.
HEAD_RADIUS = 34
HEAD_OFFSET_Y = 78              # feet -> head-center vertical distance
PLAYER_HALF_WIDTH = 30           # how close feet may get to a goal line/each other's clamp
PLAYER_START_INSET = 170         # how far in from each goal line a kickoff starts
# Approximate feet-to-head-top body height, used only to gate player-vs-
# player separation on genuine vertical overlap (see players.separate_players()):
# a jumping player whose feet have cleared the other's head height is
# passing over them, which is a legitimate head-soccer move and must not
# be blocked just because their footprints still overlap horizontally.
PLAYER_HEIGHT = HEAD_OFFSET_Y + HEAD_RADIUS

# --- Ball geometry & mass ------------------------------------------------------
BALL_RADIUS = 17

# --- Movement --------------------------------------------------------------------
PLAYER_SPEED = 260.0             # px/sec, flat ground run speed
JUMP_VELOCITY = -560.0           # px/sec, initial upward velocity on jump (negative = up)

# --- Gravity & drag --------------------------------------------------------------
GRAVITY = 1450.0                 # px/sec^2, shared by the ball and both players
BALL_AIR_DRAG_PER_SEC = 0.35     # fraction of horizontal speed shed per second while airborne
BALL_GROUND_FRICTION_PER_SEC = 620.0  # px/sec^2 horizontal deceleration while rolling on the ground

# --- Bounce restitution (0 = dead stop, 1 = perfectly elastic) -------------------
BALL_RESTITUTION_GROUND = 0.72
BALL_RESTITUTION_WALL = 0.80
# Deliberately below the wall/ground values: a header that preserved almost
# all of a hard kick's speed created an unfun "pinball" rally that could
# volley the length of the pitch and back off a single stationary head.
# Found this during a headless full-match simulation against a passive
# opponent, which is exactly the kind of edge case a real tuning pass is
# for -- see the client's request in the project brief.
BALL_RESTITUTION_HEAD = 0.55
# Below this bounce speed the ball is considered at rest rather than left to
# jitter in an ever-smaller "Zeno" bounce loop against the ground.
BALL_MIN_BOUNCE_SPEED = 40.0
# Hard speed cap so a chain of bounces/kicks can never make the ball an
# unhittable blur; also keeps it from ever crossing a wall within one frame.
BALL_MAX_SPEED = 900.0
# A small extra upward "lift" added whenever the ball bounces off a player's
# head, on top of the elastic reflection -- makes headers arc believably
# instead of dribbling flatly off the skull.
HEADER_LIFT = 60.0

# --- Kicking -----------------------------------------------------------------------
# The kick's hit-box is a rectangle in front of the player, at foot height,
# sized (KICK_RANGE_X x KICK_RANGE_Y) and centered a half-width ahead of the
# player in their facing direction.
KICK_RANGE_X = 58.0
KICK_RANGE_Y = 92.0
KICK_IMPULSE_SPEED = 640.0       # px/sec, magnitude of the velocity a kick imparts
KICK_LAUNCH_ANGLE_DEG = 38.0     # above horizontal, in the kicker's facing direction
KICK_COOLDOWN_SECONDS = 0.35     # minimum time between two kicks by the same player

# --- CPU opponent (1P mode) -------------------------------------------------------
# The CPU only "perceives" the ball on a fixed tick instead of every frame,
# and extrapolates between ticks from a stale velocity snapshot -- this is
# what gives it a small, human-like reaction lag rather than frame-perfect
# tracking, and is what makes it beatable.
CPU_REACTION_DELAY_SECONDS = 0.18
# Random aim error re-rolled every perception tick, so the CPU is never
# perfectly accurate even once it has "seen" the ball.
CPU_AIM_ERROR_PX = 26.0
# Below this horizontal distance from its target the CPU stops adjusting,
# instead of jittering back and forth around a pixel-perfect spot.
CPU_MOVE_DEADZONE_PX = 12.0
# The CPU jumps when the ball is within this horizontal distance and is
# above its own head by at least this many pixels.
CPU_JUMP_RANGE_X = 70.0
CPU_JUMP_BALL_HEIGHT = 20.0
# The CPU's own kick hit-box, checked against its *perceived* ball position
# (so its lag applies to kicks too, not just movement).
CPU_KICK_RANGE_X = KICK_RANGE_X
CPU_KICK_RANGE_Y = KICK_RANGE_Y

# --- Match rules -------------------------------------------------------------------
MATCH_SECONDS = 90.0
KICKOFF_FREEZE_SECONDS = 1.2     # brief pause before the ball goes live (kickoff or restart)
GOAL_CELEBRATION_SECONDS = 2.0   # brief pause on a goal before the restart freeze

# --- Persistence -------------------------------------------------------------------
# A small "most goals scored in a won 1-player match" record, the closest
# analogue to a high score this game has. Resolved from this file's location,
# never the current working directory, so it survives regardless of where
# the launcher sets cwd; degrades silently if the filesystem is read-only.
# See match.load_high_score()/save_high_score(). Only a genuine 1P win can
# ever write it -- 2P matches and the self-playing attract demo never touch it.
from pathlib import Path  # noqa: E402

HIGHSCORE_PATH = Path(__file__).resolve().parent.parent / "highscore.json"

# --- Input -------------------------------------------------------------------------
# Arcade cabinet button numbers (verified on the physical cabinet).
BUTTON_B = 0
BUTTON_A = 1
BUTTON_X = 2
BUTTON_Y = 3
BUTTON_COIN = 4
BUTTON_P1 = 5   # "go back one level", per the club's cross-game arcade contract
BUTTON_SELECT = 8
BUTTON_START = 9

CONFIRM_BUTTONS = (BUTTON_A, BUTTON_START)
# The single "go back one level" action is aliased across two buttons on the
# cabinet: P1 (5, the club's cross-game back/exit button) and B (0, the
# natural back partner to A/1 in this cabinet's layout). Never reuse B for a
# gameplay action -- doing so would make every such press also trigger "back".
EXIT_BUTTONS = (BUTTON_P1,)
BACK_BUTTONS = (BUTTON_B,)

# Per-player gameplay buttons (each read from that player's own joystick
# device index -- see input.RawInput.device_buttons()). Two action buttons
# at most, exactly as the client asked for: A to jump, X to kick.
BUTTON_JUMP = BUTTON_A
BUTTON_KICK = BUTTON_X

JOYSTICK_AXIS_X = 0
JOYSTICK_AXIS_Y = 1
JOYSTICK_DEADZONE = 0.5

# Two identical DragonRise sticks are wired to the cabinet: device index 0
# drives player 1, device index 1 drives player 2; in 1-player mode either
# stick may drive the human. See input.py.
PLAYER_1_DEVICE_INDEX = 0
PLAYER_2_DEVICE_INDEX = 1

# --- Attract mode ------------------------------------------------------------------
# How long the main menu can sit with no genuine input (buttons, keys, or a
# stick moved past the deadzone) before the game drops into a self-playing
# demo -- matched to the cabinet's other games for a consistent idle-to-demo
# feel across the machine.
DEMO_IDLE_SECONDS = 15.0

# The gallery hands us off with a button that may still be physically held
# (the visitor pressed it to launch us). Ignore menu confirm/select for this
# short settle window after startup, on top of hardware-state seeding, as a
# belt-and-braces second guard. Never applies to the P1 back/exit contract,
# which must always remain immediate.
INPUT_SETTLE_SECONDS = 0.3
