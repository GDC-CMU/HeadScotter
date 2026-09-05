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
#
# A first balance pass shrank this to 60px (15% of the playfield) to fix a
# simulated 90s CPU-vs-CPU match finishing 31-28 with no goalkeeper on
# either end. That fixed the score, but broke the *look* of the goal: at
# full size, with the goal barely half PLAYER_HEIGHT tall (Scotty could
# not stand up in his own net) and an opening only ~1.8 ball-diameters
# across, the goals read as small crates in the bottom corners rather
# than goals, and scoring felt like squeezing through a slot rather than
# beating a keeper. Restored to a size that reads as a real goal --
# taller than a standing player, matching the two references below --
# and the score is now held down by an actual keeper instead
# (see KEEPER_* below and CPU_MAX_ADVANCE_FRACTION), which is what real
# football and every 2D head-soccer clone with a credible-looking net
# actually do:
#  1. Real association football: a regulation goal is 2.44m tall; an average
#     adult is roughly 1.75-1.83m, so a real goal is ~1.3-1.4x a player's
#     standing height. 170px is ~1.5x this game's PLAYER_HEIGHT (112px).
#  2. 2D "head soccer"-style clones commonly size the goal mouth at
#     roughly 20-30% of the playfield's vertical extent; 170px is ~44%,
#     which is taller than that band, but deliberately so -- see the
#     clone research note on KEEPER_RADIUS below on why "as tall as a
#     real net" and "hard to score in" are handled by two different
#     constants now, not one.
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
#
# Lowered further from an initial 0.55 during the goal/scoring-rate
# balance pass (see GOAL_MOUTH_HEIGHT and CPU_MAX_ADVANCE_FRACTION):
# headers, not kicks, turned out to be the main source of unrealistic
# scoring once the goal was already shrunk and the CPU was already
# playing more defensively -- a chain of two or three headers between
# players could still build up enough speed to cross the whole pitch
# regardless of how hard the ball was kicked (confirmed by simulating
# with KICK_IMPULSE_SPEED cut by a third, which barely changed the
# scoreline). 0.3 was the value, found by simulating full matches at
# each candidate (see tests/test_balance.py), that -- together with the
# other two changes -- reliably keeps scorelines single-digit-per-side.
BALL_RESTITUTION_HEAD = 0.3
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
# Even with a real goalkeeper now defending the mouth (see KEEPER_* below),
# a field player who fully committed forward on every attack would still
# leave their own goal undefended between the moment they lose the ball
# and the moment they can run all the way back -- and, visually, both
# players simply chasing the ball everywhere is what caused the "glued
# together in the middle of the pitch" look. This caps how far a CPU will
# chase the ball away from its own goal, as a fraction of the full pitch
# width, while the ball is a live attacking threat (see
# CPU_RESTING_SPEED_PX for the exception). Chosen empirically, not
# guessed: simulating dozens of full 90s CPU-vs-CPU matches per candidate
# value found this was a knife-edge parameter -- too low (below ~0.30)
# and both CPUs can't even reach the resting kickoff ball (0-0 forever);
# too high (0.36+) and enough space opens up that scorelines rocket into
# the double digits. A first pass landed on 0.39, but a later fix to a
# bug in the CPU's own ballistic extrapolation (see
# CPUController._perceive()) made its ball-tracking meaningfully more
# accurate, which shifted this whole knife-edge lower -- 0.39 alone was
# no longer enough once combined with that fix and the lowered
# BALL_RESTITUTION_HEAD below. 0.32 was the value found by re-simulating
# 150 seeds at a generous tick budget that reliably keeps scorelines
# single-digit-per-side with zero non-terminating matches -- see
# tests/test_balance.py, which locks this in as a regression guard. Kept
# unchanged when the goalkeeper was added: re-simulating with the keeper
# in place at this same value still held the target band, so there was
# no reason to loosen the field players' own defensive discipline too.
CPU_MAX_ADVANCE_FRACTION = 0.32
# Below this perceived speed (px/sec) the ball is treated as having
# stopped, not as a live attacking threat -- the defensive cap above is
# lifted entirely so any CPU will always go and retrieve a dead ball
# regardless of distance from its own goal. Without this, a ball that
# happens to settle outside a CPU's advance limit (e.g. facing a human
# who never moves at all) could never be reached by anyone and the match
# would stall forever -- the exact failure mode this constant exists to
# rule out.
CPU_RESTING_SPEED_PX = 50.0
# Anti-stalemate timeout, the same pattern this club already uses for
# PacDawg's ghost-release anti-starvation timer: if *no one* has scored
# for this many seconds of actual live play, every CPU temporarily
# ignores CPU_MAX_ADVANCE_FRACTION entirely and chases the ball wherever
# it is, exactly as if the ball had come to rest (see
# CPU_RESTING_SPEED_PX above). Found necessary by simulation: an
# otherwise-idle human can act as a stationary wall that, combined with
# both CPUs' own defensive caution, occasionally kept a rally shuttling
# back and forth near midfield without either side ever committing far
# enough forward to actually score -- confirmed to persist for a full
# simulated hour before this fix. This guarantees a match (and sudden
# death specifically) always eventually resolves, without weakening the
# defensive positioning during ordinary, actively-contested play.
CPU_STALEMATE_SECONDS = 20.0

# --- Goalkeeper ----------------------------------------------------------------
# Every goal has its own automated keeper, in every mode (1P/2P/DEMO) --
# not human- or CPU-field-player-controlled, exactly like the fixed,
# always-present single keeper in 2D head-soccer clones that keep a
# visually credible, real-sized net (see GOAL_MOUTH_HEIGHT above) rather
# than shrinking the goal until scoring is merely rare. A keeper is a
# simple vertical "paddle": it does not run, jump, or leave its line's
# small forward depth, it only tracks the ball's height within the goal
# mouth -- see keeper.py. It must be beatable (a reaction delay, a speed
# cap, and aim error all below), not a wall: re-simulating the same full
# CPU-vs-CPU matches used to tune CPU_MAX_ADVANCE_FRACTION, with the
# keeper added and GOAL_MOUTH_HEIGHT restored to 170, was how every value
# below was actually chosen -- see tests/test_balance.py for the
# resulting scorelines this locks in.
KEEPER_RADIUS = 32.0
# Fixed horizontal distance from its own goal line the keeper stands at
# -- a "six-yard box" depth, not a movable range; the keeper never
# advances further than this to challenge a ball, which is what keeps it
# beatable by a shot placed past it rather than through it.
KEEPER_DEPTH = 55.0
# px/sec vertical speed cap while moving to cover a shot -- a fast,
# well-placed shot can still beat a keeper that isn't already covering
# that height, which is deliberate.
KEEPER_SPEED = 300.0
# Same perception-lag pattern as the CPU field players (see
# CPU_REACTION_DELAY_SECONDS): the keeper only re-reads the ball's height
# on a fixed tick rather than every frame.
KEEPER_REACTION_DELAY_SECONDS = 0.15
# Random vertical aim error re-rolled every perception tick, so the
# keeper is never pixel-accurate even once it has "seen" the ball.
KEEPER_AIM_ERROR_PX = 18.0
# Bounce restitution for a ball the keeper touches (0 = dead stop/catch,
# 1 = perfectly elastic parry) -- softer than a header, since a keeper
# smothering a shot should look like a save, not another bounce that
# keeps the rally dangerous.
KEEPER_RESTITUTION = 0.4

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
