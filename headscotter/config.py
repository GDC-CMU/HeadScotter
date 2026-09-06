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
# Side-view head-soccer conventions, measured directly from seven independent
# open-source implementations of the genre (see the project research report).
# One of them runs at exactly this project's 800x600, so its numbers are used
# unscaled wherever possible. There is deliberately no HUD band eating into
# the pitch here -- the scoreboard is a small overlay near the top of the sky
# (see render.py), not a strip that pushes the playfield down.
#
# The ground line is the single most important number in the genre: two
# independent projects (one already at 800x600) land on exactly 0.833 * H.
GROUND_Y = 500

# Invisible ceiling: the ball can never go above this. Not directly sourced
# (no implementation documents a ceiling height as a fraction of screen
# height), chosen to sit just below the stadium's floodlight/roofline art so
# a high header or a crossbar rebound has generous room to arc without ever
# visually punching through the sky.
PITCH_TOP = 40

# Goal line flush with the screen edge -- sourced: five of six implementations
# place the goal at x=0 / x=WIDTH exactly (a sixth insets by an near-flush
# 1.3%). The previous build inset the goal line 70px into the pitch, which is
# exactly the deviation the research report called out as non-standard.
PITCH_LEFT = 0
PITCH_RIGHT = SCREEN_WIDTH
PITCH_CENTER_X = (PITCH_LEFT + PITCH_RIGHT) / 2.0

# Goal mouth: the vertical gap, right at PITCH_LEFT/PITCH_RIGHT, that counts
# as a goal instead of a wall bounce. Below CROSSBAR_Y (numerically closer to
# GROUND_Y) is the open net; at or above it is the solid crossbar/post, which
# just bounces the ball back into play like any other wall.
#
# Sourced: goal height ~0.333 * screen height (GeriiGarcia/HACKUPC26_P2P_Game,
# which runs at this project's exact 800x600 resolution) -- 200px here, which
# lands the crossbar exactly at half screen height, also matching that source.
GOAL_MOUTH_HEIGHT = 200
CROSSBAR_Y = GROUND_Y - GOAL_MOUTH_HEIGHT  # 300

# Goal depth in profile (front post to back of net) -- sourced: ~0.10 *
# screen width in the same reference implementation.
GOAL_WIDTH = 80
# Sourced convention: a solid ~10px crossbar is a real collision surface in
# every serious implementation measured (tompashinsky, sp1099).
CROSSBAR_THICKNESS = 10
# Sourced convention band was 3-5px at each source's own resolution; bumped
# up for readability at this project's pixel-art scale, per the report's own
# note that a chunkier mesh (8-12px pitch) reads better at small scale than
# the 20px pitch measured at higher resolutions.
POST_THICKNESS = 8
NET_MESH = 10
NET_COLOR = (150, 150, 150)  # sourced: mid-grey, so the ball stays readable against it

# --- Stadium backdrop geometry (art layout; consumed by render.py and
# tools/generate_placeholders.py) --------------------------------------------
GROUND_HEIGHT = SCREEN_HEIGHT - GROUND_Y  # 100 -- the grass strip below GROUND_Y
# Sourced depth trick: martinlhw/Head_Soccer:v3/game.py:34,46,460 draws its
# visual grass band starting 40px *above* the actual collision line the
# characters stand on (grass blitted at y=250, collision line at y=290 on
# their 330-tall screen) -- so the feet line falls partway down the grass
# band rather than exactly at its top edge, leaving a sliver of pitch
# visible behind the players. This is purely a rendering offset: it does
# not move GROUND_Y (the real physics collision line) at all, only where
# the ground *sprite* is drawn relative to it.
GROUND_VISUAL_MARGIN = 40
GROUND_SPRITE_HEIGHT = GROUND_HEIGHT + GROUND_VISUAL_MARGIN  # 140
GROUND_SPRITE_Y = GROUND_Y - GROUND_VISUAL_MARGIN  # 460 -- top-left the ground sprite is blitted at
# Scrolling advertising hoarding: sourced position/size convention (sits
# directly above the grass, on the lower stadium band) from martinlhw/
# Head_Soccer, rescaled proportionally from its 330-tall screen to this
# project's 600-tall one (their band was 50/330 = 0.152 of H; 0.152*600 ~= 91,
# but that source's crowd tiers ate far more vertical space than this build's
# stadium art needs -- a slimmer 50px band reads just as well at this scale
# and keeps more of the backdrop as legible crowd/stand art). Sits directly
# above the ground *sprite* (GROUND_SPRITE_Y), not above GROUND_Y itself, so
# it never gets covered by the grass depth margin above.
HOARDING_HEIGHT = 50
HOARDING_Y = GROUND_SPRITE_Y - HOARDING_HEIGHT  # 410
HOARDING_WIDTH = 560  # sourced (martinlhw's banner width, used verbatim)
# Not sourced numerically -- the report documents that the hoarding "scrolls
# continuously" but no implementation measures a speed. Chosen slow enough to
# read as ambient background motion rather than a distraction.
HOARDING_SCROLL_SPEED = 40.0  # px/sec
# A real advertising hoarding runs along the back of the pitch and stops
# at the goals -- it never crosses a goal mouth. render.py only draws the
# *scrolling* hoarding graphic within this horizontal span, between where
# the two goals end; behind each goal, the plain wall-board colour baked
# into bg_stadium.png shows instead (see assets.py's bg_stadium entry).
HOARDING_SPAN_LEFT = PITCH_LEFT + GOAL_WIDTH
HOARDING_SPAN_RIGHT = PITCH_RIGHT - GOAL_WIDTH

# --- Player geometry ------------------------------------------------------------
# Head-soccer characters are drawn with a big head and a small body; against
# the *ball*, only the head is a solid collider (matching the genre -- the
# body doesn't head/kick the ball). Against *each other*, both players'
# whole bodies block one another (see players.separate_players()) so
# closing distance actually means something. All distances below are from
# the player's feet anchor (x, y), which is what players.Player.x/y track.
#
# Sourced: character height ~0.14 * screen height -- two independent sources
# (GeriiGarcia and DucAnh1053) agree to three decimal places (85/600 and
# 102/720 both round to 0.142).
CHAR_HEIGHT = 85
# Sourced: head diameter is 0.65-0.83 * total character height across every
# genuine "big head" implementation measured. 64px (radius 32) is 0.75 of
# CHAR_HEIGHT, comfortably inside that band.
HEAD_RADIUS = 32
# Derived, not independently chosen: feet -> head-center distance, so that
# head-top (HEAD_OFFSET_Y + HEAD_RADIUS above the feet) lands exactly at
# CHAR_HEIGHT above the ground -- this is what keeps the jump-to-crossbar
# invariant (see tests/test_geometry_invariants.py) consistent by
# construction instead of by coincidence.
HEAD_OFFSET_Y = CHAR_HEIGHT - HEAD_RADIUS  # 53
# NOT sourced -- the report has no measured body-width convention (most
# clones draw little to no torso at all). Chosen so the body (40px wide)
# reads clearly narrower than the head (64px diameter), matching every
# reference's "big head, small/near-invisible body" silhouette, while
# staying wide enough that player-vs-player contact still feels fair.
PLAYER_HALF_WIDTH = 20
# NOT sourced -- kickoff stand position. Chosen so both players start clear
# of their own goal mouth (GOAL_WIDTH=80) with room to react, roughly midway
# between their goal line and the center circle.
PLAYER_START_INSET = 190
# Approximate feet-to-head-top body height, used only to gate player-vs-
# player separation on genuine vertical overlap (see players.separate_players()):
# a jumping player whose feet have cleared the other's head height is
# passing over them, which is a legitimate head-soccer move and must not
# be blocked just because their footprints still overlap horizontally.
PLAYER_HEIGHT = HEAD_OFFSET_Y + HEAD_RADIUS  # 85 == CHAR_HEIGHT

# --- Ball geometry & mass ------------------------------------------------------
# Sourced: ball diameter ~0.05 * screen height (30px at 600) and ~0.45-0.55 *
# head diameter -- 30/64 = 0.469, inside that band. The same reference
# implementation that supplied the goal geometry above uses this exact value.
BALL_RADIUS = 15

# --- Movement --------------------------------------------------------------------
# NOT sourced -- ground run speed has no measured cross-implementation
# convention in the report. Kept at its previously-tuned value.
PLAYER_SPEED = 260.0             # px/sec, flat ground run speed
# Sourced: jump velocity ~-13 px/frame at 60fps -> -780 px/sec. Apex =
# v^2/(2g) = 780^2/(2*2160) ~= 141px, clearing the ~115px head-top-to-crossbar
# gap this geometry produces (see tests/test_geometry_invariants.py) with
# the margin the report describes.
JUMP_VELOCITY = -780.0           # px/sec, initial upward velocity on jump (negative = up)

# --- Gravity & drag --------------------------------------------------------------
# Sourced: gravity ~0.6 px/frame^2 at 60fps -> 2160 px/sec^2 -- "snappy, not
# floaty", per the report's own characterization of the genre.
GRAVITY = 2160.0                 # px/sec^2, shared by the ball and both players
BALL_AIR_DRAG_PER_SEC = 0.35     # fraction of horizontal speed shed per second while airborne
BALL_GROUND_FRICTION_PER_SEC = 620.0  # px/sec^2 horizontal deceleration while rolling on the ground

# --- Bounce restitution (0 = dead stop, 1 = perfectly elastic) -------------------
# Sourced: 0.70 is the median and mode of seven independent measurements
# (range 0.6-0.8) for the ground bounce; GeriiGarcia (this project's exact
# resolution) also uses 0.7 for its side walls.
BALL_RESTITUTION_GROUND = 0.70
BALL_RESTITUTION_WALL = 0.70
# NOT sourced as a distinct value -- no implementation in the report
# separates a header bounce from the ordinary ground/wall restitution above.
# With the goalkeeper removed (see the project brief: "the genre has no
# goalkeeper"), defense now depends entirely on the CPU's own positioning
# discipline (see CPU_MAX_ADVANCE_FRACTION below) rather than a last line of
# defense, so this is tuned below the ground/wall value to keep a chain of
# headers from building up enough speed to volley the length of the pitch.
# 0.60 was the value found by simulating full CPU-vs-CPU matches after the
# keeper's removal (see tests/test_balance.py) rather than guessed.
BALL_RESTITUTION_HEAD = 0.60
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
# player in their facing direction. NOT sourced (no implementation measures
# a kick hit-box); scaled down from the previous build's tuned values by the
# same ratio the character shrank by (new PLAYER_HEIGHT 85 / old 112 ~=
# 0.76), so the kick reach stays proportional to the now-smaller character
# rather than reaching disproportionately far.
KICK_RANGE_X = 44.0
KICK_RANGE_Y = 70.0
KICK_IMPULSE_SPEED = 560.0       # px/sec, magnitude of the velocity a kick imparts
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
# The genre has no goalkeeper (confirmed across every reference
# implementation in the research report) -- each player, human or CPU,
# defends their own goal directly. Without a keeper as a last line of
# defense, this is the single most important defensive parameter in the
# game: a field player who fully committed forward on every attack would
# leave their own goal completely undefended between the moment they lose
# the ball and the moment they can run all the way back -- and, visually,
# both players simply chasing the ball everywhere is what caused the
# "glued together in the middle of the pitch" look this replaces. This
# caps how far a CPU will chase the ball away from its own goal, as a
# fraction of the full pitch width, while the ball is a live attacking
# threat (see CPU_RESTING_SPEED_PX for the exception). Chosen empirically,
# not guessed: simulating dozens of full 90s CPU-vs-CPU matches per
# candidate value, after the goalkeeper's removal, found this was a
# knife-edge parameter -- too low and both CPUs can't even reach the
# resting kickoff ball (0-0 forever); too high and enough space opens up
# in front of an undefended goal that scorelines rocket into the double
# digits. 0.20 was the value found by re-simulating 20 seeds at a
# generous tick budget (together with BALL_RESTITUTION_HEAD and
# KICK_IMPULSE_SPEED below) that reliably keeps scorelines single-digit-
# per-side with zero non-terminating matches now that no keeper backstops
# a missed defensive read -- see tests/test_balance.py, which locks this
# in as a regression guard.
CPU_MAX_ADVANCE_FRACTION = 0.20
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

# --- HUD ---------------------------------------------------------------------------
# A compact scoreboard panel replacing the old 110px dark band across the
# top of the screen (which ate a fifth of the playfield and, combined with
# the top-down pitch markings, was one of the things that made the previous
# build read as the wrong genre). Sourced convention: the report's HUD
# section documents a top-centre scoreboard panel roughly W/3 x H/4 as
# "well-supported" across the clones it measured; sized down further here
# since this build's panel only needs to hold two score digits, a divider,
# and a clock, not a full graphic scoreboard shell.
SCOREBOARD_WIDTH = 260
SCOREBOARD_HEIGHT = 70
SCOREBOARD_TOP_Y = 8  # px from the top of the screen

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
