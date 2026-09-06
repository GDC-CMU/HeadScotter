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

BALL_SPIN_MAX_DEGREES = 720.0
BALL_TRAIL_SECONDS = 0.16
BALL_TRAIL_LIMIT = 5
POWER_TRAIL_WINDOW = 0.65
IMPACT_FEEDBACK_SECONDS = 0.16
IMPACT_FEEDBACK_LIMIT = 4
POWER_READY_CUE_SECONDS = 0.45
GOAL_FEEDBACK_SECONDS = 0.55


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
# floaty", per the report's own characterization of the genre. This is the
# *player's* gravity only -- the jump-to-header geometry depends on this
# exact value (see tests/test_geometry_invariants.py) and must not change:
#   apex = JUMP_VELOCITY^2 / (2*GRAVITY) = 141px
#   head-top (415) -> crossbar (300) gap = 115px
GRAVITY = 2160.0                 # px/sec^2, the player's own gravity only
# The ball's own gravity, deliberately lower than the player's: a ball that
# falls exactly as fast as a person feels like a dropped stone, not
# something you can loft, hang in the air, and chase. Lower gravity (a
# floatier arc) plus a bouncier ground restitution below is what gives the
# ball the "light" feel the genre needs while the player's own jump physics
# above stay completely untouched. NOT independently sourced -- the report
# measures a single shared gravity per implementation, not a ball/player
# split -- chosen at ~60% of the player's value as a starting point for a
# noticeably floatier arc, then kept at this value after re-verifying the
# full-match balance simulation still holds (see tests/test_balance.py).
BALL_GRAVITY = 1300.0             # px/sec^2, the ball's own gravity only
BALL_AIR_DRAG_PER_SEC = 0.35     # fraction of horizontal speed shed per second while airborne
BALL_GROUND_FRICTION_PER_SEC = 620.0  # px/sec^2 horizontal deceleration while rolling on the ground

# --- Bounce restitution (0 = dead stop, 1 = perfectly elastic) -------------------
# Deliberately lively rebounds: a lob retains enough height for another
# header opportunity, then loses energy and settles rather than bouncing forever.
BALL_RESTITUTION_GROUND = 0.90
BALL_RESTITUTION_WALL = 0.70
# NOT sourced as a distinct value -- no implementation in the report
# separates a header bounce from the ordinary ground/wall restitution above.
# With the goalkeeper removed (see the project brief: "the genre has no
# goalkeeper"), defense now depends entirely on the CPU's own positioning
# discipline (see the CPU tactics below) rather than a last line of
# defense. Counterintuitively, *raising* this value (a punchier defensive
# header) tightens scoring rather than loosening it: a soft header
# (a lower value) doesn't clear the ball away from danger, so it lingers
# in the danger zone and gets poked back in -- confirmed by sweeping
# candidates against full-match simulation (see tests/test_balance.py),
# not assumed. Re-tuned to 0.90 (from an initial 0.76) alongside
# the former CPU leash and KICK_IMPULSE_SPEED below after making the
# ball itself bouncier/floatier (BALL_GRAVITY/BALL_RESTITUTION_GROUND
# above): a much livelier ball needs a correspondingly firmer defensive
# header to clear it, or scoring runs away into the double digits per
# side. This is the value that reliably keeps per-side scorelines in the
# sourced "low single digits" band (the report: "typical scorelines are
# low single digits (0-5)" per side).
BALL_RESTITUTION_HEAD = 0.90
# Below this bounce speed the ball is considered at rest rather than left to
# jitter in an ever-smaller "Zeno" bounce loop against the ground.
BALL_MIN_BOUNCE_SPEED = 40.0
# Stop imperceptible floor chatter without deadening softer head contacts.
BALL_GROUND_SETTLE_SPEED = 65.0
# Hard speed cap so a chain of bounces/kicks can never make the ball an
# unhittable blur; also keeps it from ever crossing a wall within one frame.
BALL_MAX_SPEED = 900.0
# A small extra upward "lift" added whenever the ball bounces off a player's
# head, on top of the elastic reflection -- makes headers arc believably
# instead of dribbling flatly off the skull.
HEADER_LIFT = 60.0
# Restitution for the *body* collider (see PLAYER geometry below and
# players.apply_body_collision()) -- deliberately low/"dead", not sourced
# as a distinct value (no implementation in the report models a torso
# collider at all): a body hit is meant to read as being blocked, not
# bounced -- the ball loses most of its momentum into the block rather
# than rebounding like a header. Heading, not blocking, is the genre's
# actual scoring mechanic, so the body must never out-bounce the head.
BALL_RESTITUTION_BODY = 0.20
# Tunnelling guard: physics.step_ball()'s ground/wall/goal checks and the
# ball-vs-player collision checks in game.py are both discrete overlap
# tests, so a fast-moving ball can in principle skip clean over a thin
# collider between two samples (at BALL_MAX_SPEED, one full 60fps frame
# is a 15px hop -- wider than the goalposts). game.py substeps the ball's
# per-frame movement so no single substep advances it more than this many
# pixels, which guarantees every collider at least this thick (every one
# in this game is: POST_THICKNESS=8, CROSSBAR_THICKNESS=10, and a body's
# PLAYER_HALF_WIDTH*2=40) gets an overlap check somewhere along the way.
BALL_MAX_STEP_PX = 6.0

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
# A normal kick is a lob, not the old 13px-high chip. The angle also has
# to clear the kicker's solid head; it is not implemented with immunity.
KICK_IMPULSE_SPEED = 825.0      # relative launch speed, before inherited motion/cap
KICK_LAUNCH_ANGLE_DEG = 42.0    # above horizontal, in the kicker's facing direction
KICK_COOLDOWN_SECONDS = 0.35     # power recovery base; also CPU's normal-attempt interval
# How long the "just kicked" pose (render.py's kick sprite) is held after
# any kick fires, normal or power -- independent of the (now variable,
# see POWER_SHOT_* below) actual cooldown, so the pose always reads the
# same regardless of which kind of kick just happened.
KICK_POSE_HOLD_SECONDS = 0.15

# --- Power shot ----------------------------------------------------------------
# Holding the separate power control charges a shot; releasing it fires --
# with the strength interpolated continuously between an ordinary kick
# (an immediate tap-and-release) and a full power shot (held for the full
# charge time). NOT sourced -- the research report's corpus predates this
# feature (a club-approved addition, not a genre convention), so every
# value below is an original tuning choice, kept in config.py so it can
# be retuned freely. render.py shows a charge meter above a charging
# player's head (see _draw_charge_indicator()) so the mechanic is
# discoverable without a tutorial.
POWER_SHOT_CHARGE_SECONDS = 0.6     # seconds held to reach a full-strength power shot
# Meaningfully stronger than an ordinary kick (KICK_IMPULSE_SPEED above)
# but still under BALL_MAX_SPEED, so a full power shot doesn't just get
# silently clamped back down to an ordinary-looking shot.
POWER_SHOT_IMPULSE_SPEED = 850.0   # px/sec, magnitude at full charge
# A fully-charged shot is also flatter/more driven than a normal kick's
# lofted arc (KICK_LAUNCH_ANGLE_DEG) -- interpolated the same way as speed.
POWER_SHOT_LAUNCH_ANGLE_DEG = 20.0
# Extra cooldown added on top of KICK_COOLDOWN_SECONDS, scaled by charge
# fraction -- the gate that keeps a power shot from simply replacing
# ordinary kicking: the harder you hit it, the longer before another power
# shot. Fresh normal kicks are always available.
POWER_SHOT_COOLDOWN_BONUS_SECONDS = 0.55

# --- CPU opponent (1P mode) -------------------------------------------------------
# Ball and opponent observations refresh together on a delayed tick.
# Predictions use only that stale observation and the ordinary ball/body
# rules: the CPU cannot see future input or unobserved collisions.
CPU_REACTION_DELAY_SECONDS = 0.18
# Still imperfect, but noise no longer dominates the 36px shot setup.
CPU_AIM_ERROR_PX = 12.0
CPU_MOVE_DEADZONE_PX = 8.0
# Cache observed flight and opponent-rebound forecasts per observation.
CPU_PREDICTION_SECONDS = 1.4
CPU_PREDICTION_STEP = 1.0 / 30.0
# Stay on the own-goal side of the ball for an outward header/foot strike.
CPU_SHOT_SETUP_PX = 36.0
CPU_THREAT_SPEED_PX = 80.0
CPU_RECOVERY_ZONE_PX = 220.0
CPU_RISING_SHOT_SPEED_PX = 120.0
CPU_HEADER_MARGIN_PX = 4.0  # reject grazing forecasts sensitive to discrete timing
# Jump timings derive from the unchanged human jump/body geometry.
CPU_CROSS_MARGIN_PX = 8.0
CPU_JUMP_RETRY_SECONDS = 0.18
# Existing power action is useful for a controlled, distant/blocked attack;
# urgent clearances use immediate normal kicks instead of waiting to charge.
CPU_CONTROL_SPEED_PX = 140.0
CPU_POWER_DISTANCE_PX = 220.0

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
# device index -- see input.RawInput.device_buttons()).
BUTTON_JUMP = BUTTON_Y
BUTTON_KICK = BUTTON_X
BUTTON_POWER = BUTTON_A

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
