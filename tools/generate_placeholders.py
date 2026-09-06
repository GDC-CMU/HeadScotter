#!/usr/bin/env python
"""Regenerate the committed placeholder sprite PNGs deterministically.

Every shape here is drawn with fixed coordinates and formulaic (not random)
variation, so running this script twice in a row leaves ``git status``
clean. Run it whenever a new logical sprite is added to
``headscotter.assets.SPRITE_SPECS``, or any time you want to reset
``assets/sprites/`` back to the stock placeholder look.

This is a full side-view head-soccer stage, not a top-down pitch: a
stadium backdrop (sky, tiered stands, a dithered crowd, floodlights), a
scrolling advertising hoarding, and a flat grass strip -- see
``assets/README.md`` and the project's genre research report for why a
side-view game has no pitch markings at all. Real art can replace any
file here with zero code changes.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from headscotter import config  # noqa: E402
from headscotter.assets import ASSETS_ROOT, SPRITE_SPECS  # noqa: E402

pygame.init()
pygame.font.init()

TRANSPARENT = (0, 0, 0, 0)

# --- Scotty: a dark, shaggy Scottish terrier in a CMU-red kit ----------------------
# A real Scottie's defining features -- a dark coat, erect pointed ears, a
# prominent rectangular beard/muzzle, and bushy eyebrows -- are what make
# this read as the breed rather than "a round head". Contrast against the
# stadium backdrop and the rival comes from the kit (a bright red shirt),
# not from the coat itself, matching the club's existing lesson that a
# character drawn in a dark "natural" colour needs a bright element
# somewhere to stay legible at cabinet viewing distance.
SCOTTY_COAT = (52, 44, 38)
SCOTTY_COAT_HI = (86, 74, 62)
SCOTTY_BROW = (168, 148, 118)
# Lighter than the coat itself, not darker -- a near-black outline on an
# already near-black coat nearly vanishes against the stadium's own dark
# crowd tiers. A warm mid-brown rim keeps the silhouette's edge defined
# against both a dark backdrop and the coat it outlines.
SCOTTY_OUTLINE = (94, 78, 62)
SCOTTY_KIT = (196, 32, 48)
SCOTTY_KIT_TRIM = (245, 245, 245)

# --- Rival: an angular, two-eyed creature in a navy kit -- not a palette swap ------
# The previous pass recoloured the exact same "circle head + floppy ear +
# single visor" shape Scotty uses, which is indistinguishable in
# silhouette. This rival's head is a hard-edged hexagonal shape with a
# pointed chin and a single jagged dorsal crest instead of two ears, so
# the two read as different creatures even with colour removed.
RIVAL_HIDE = (150, 190, 235)
RIVAL_HIDE_SHADE = (108, 146, 196)
RIVAL_OUTLINE = (30, 44, 74)
RIVAL_KIT = (44, 78, 156)
RIVAL_KIT_TRIM = (240, 246, 252)

# --- Stadium palette -----------------------------------------------------------------
SKY_TOP = (94, 168, 224)
SKY_HORIZON = (196, 224, 236)
STAND_FAR = (58, 68, 82)
STAND_MID = (46, 55, 68)
STAND_NEAR = (36, 44, 56)
FLOODLIGHT_COLOR = (40, 46, 56)
FLOODLIGHT_GLOW = (255, 244, 200)
CROWD_COLORS = [
    (214, 60, 60), (240, 210, 90), (235, 235, 235), (70, 120, 200), (90, 170, 110),
]
GRASS_LIGHT = (58, 150, 76)
GOAL_POST = (238, 238, 238)
GOAL_OUTLINE = (55, 60, 65)
# Perimeter wall board behind the goals, where the scrolling hoarding
# graphic is never drawn (see make_bg_stadium / the hoarding-span note in
# render.py) -- a plain dark board colour, matching the hoarding's own
# frame colour so the two read as one continuous wall.
WALL_BOARD_COLOR = (18, 18, 20)


def _surface(size):
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill(TRANSPARENT)
    return surf


def _lerp_color(c0, c1, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))


def _boot(surf, x, y, outline_color):
    """A small dark boot with a light sole line -- deliberately simple
    (no rotation to match a leg's exact angle) but enough to read as
    footwear rather than a bare stick leg."""
    rect = pygame.Rect(0, 0, 11, 6)
    rect.center = (round(x), round(y))
    pygame.draw.ellipse(surf, (24, 22, 22), rect)
    pygame.draw.ellipse(surf, outline_color, rect, 1)
    pygame.draw.line(surf, (235, 235, 235), (rect.left + 2, rect.bottom - 1), (rect.right - 2, rect.bottom - 1), 1)


def _draw_kit(
    surf, cx, head_bottom, feet_y, radius, pose, leg_phase,
    kit_color, kit_trim, outline_color, shorts_stripe,
):
    """The torso: a shirt, shorts, legs, and boots, shared between both
    characters (only the colours differ). Occupies the full
    HEAD_OFFSET_Y - HEAD_RADIUS gap below the head -- by construction
    exactly matches the vertical room the config geometry leaves for a
    body, so this is a real torso, not a ring or a sliver.
    """
    shirt_overlap = 5   # tucked up under the chin for a seamless neck join
    shirt_h = 9
    shorts_h = 6
    shirt_top = head_bottom - shirt_overlap
    shirt_bottom = head_bottom + shirt_h
    shorts_bottom = shirt_bottom + shorts_h
    legs_top = shorts_bottom
    boot_y = feet_y - 2

    hip = radius * 0.30
    leg_w = 6

    def _leg(hx, bx, by):
        pygame.draw.line(surf, outline_color, (cx + hx, legs_top), (bx, by), leg_w)
        _boot(surf, bx, by, outline_color)

    if pose == "kick":
        _leg(-hip, cx - hip - 3, boot_y)
        _leg(hip, cx + radius * 1.05, shirt_top + radius * 0.25)
    elif pose == "jump":
        _leg(-hip, cx - hip - 7, boot_y - 3)
        _leg(hip, cx + hip + 7, boot_y - 3)
    elif pose == "idle":
        _leg(-hip, cx - hip, boot_y)
        _leg(hip, cx + hip, boot_y)
    else:  # run
        offset = 6 if leg_phase == 1 else -6
        _leg(-hip, cx - hip + offset, boot_y)
        _leg(hip, cx + hip - offset, boot_y)

    # Shorts -- narrower than the shirt, a distinct band so it reads as
    # a separate garment rather than a continuation of the shirt.
    shorts_rect = pygame.Rect(0, 0, radius * 1.25, shorts_h + 3)
    shorts_rect.midtop = (cx, shirt_bottom - 3)
    pygame.draw.rect(surf, (240, 240, 240), shorts_rect, border_radius=2)
    pygame.draw.rect(surf, outline_color, shorts_rect, 1, border_radius=2)
    pygame.draw.rect(
        surf, shorts_stripe,
        (shorts_rect.centerx - 2, shorts_rect.top + 1, 4, shorts_rect.height - 2),
    )

    # Shirt -- a tapered trapezoid (broader at the shoulders, narrower at
    # the waist), the actual silhouette of a jersey -- drawn last so it
    # overlaps the top of the shorts and the base of the head for a
    # seamless figure. Deliberately *not* a rounded pill/rect: an earlier
    # pass here read as a life-preserver ring rather than a shirt.
    shoulder_w = radius * 1.6
    waist_w = radius * 1.15
    shirt_points = [
        (cx - shoulder_w / 2, shirt_top),
        (cx + shoulder_w / 2, shirt_top),
        (cx + waist_w / 2, shirt_bottom),
        (cx - waist_w / 2, shirt_bottom),
    ]
    pygame.draw.polygon(surf, kit_color, shirt_points)
    pygame.draw.polygon(surf, outline_color, shirt_points, 1)
    # Flat short-sleeve cuffs at the shoulders -- small rectangular tabs,
    # not round stubs, so the silhouette reads as fabric, not a ring.
    for side in (-1, 1):
        sleeve = pygame.Rect(0, 0, 6, 6)
        sleeve.midtop = (cx + side * shoulder_w / 2, shirt_top + 1)
        pygame.draw.rect(surf, kit_color, sleeve)
        pygame.draw.rect(surf, outline_color, sleeve, 1)
    pygame.draw.polygon(
        surf, kit_trim,
        [(cx - 4, shirt_top + 1), (cx + 4, shirt_top + 1), (cx, shirt_top + 6)],
    )


# --- Scotty ------------------------------------------------------------------------
def _scotty_head(surf, cx, head_cy, radius, mouth_open):
    # Shaggy fur bumps around the back/top of the head.
    for angle in (150, 172, 196, 220):
        bx = cx + radius * 0.88 * math.cos(math.radians(angle))
        by = head_cy + radius * 0.88 * math.sin(math.radians(angle))
        pygame.draw.circle(surf, SCOTTY_COAT_HI, (round(bx), round(by)), max(2, round(radius * 0.2)))

    pygame.draw.circle(surf, SCOTTY_COAT, (round(cx), round(head_cy)), round(radius))
    pygame.draw.circle(surf, SCOTTY_OUTLINE, (round(cx), round(head_cy)), round(radius), 2)

    # Two erect, pointed ears on top -- the single most recognisable
    # Scottie silhouette feature -- not a floppy triangle stuck on the side.
    for side in (-1, 1):
        base_x = cx + side * radius * 0.42
        base_y = head_cy - radius * 0.78
        tip_x = cx + side * radius * 0.62
        tip_y = head_cy - radius * 1.45
        pygame.draw.polygon(
            surf, SCOTTY_COAT,
            [(base_x - side * radius * 0.16, base_y), (tip_x, tip_y), (base_x + side * radius * 0.20, base_y + radius * 0.1)],
        )
        pygame.draw.polygon(
            surf, SCOTTY_OUTLINE,
            [(base_x - side * radius * 0.16, base_y), (tip_x, tip_y), (base_x + side * radius * 0.20, base_y + radius * 0.1)],
            1,
        )

    # Rectangular beard/muzzle -- a hard-edged block, not an ellipse --
    # jutting forward, the second defining Scottie feature.
    beard_w, beard_h = radius * 1.05, radius * 0.62
    beard_rect = pygame.Rect(0, 0, beard_w, beard_h)
    beard_rect.midleft = (cx + radius * 0.35, head_cy + radius * 0.32)
    pygame.draw.rect(surf, SCOTTY_COAT, beard_rect, border_radius=2)
    pygame.draw.rect(surf, SCOTTY_OUTLINE, beard_rect, 1, border_radius=2)
    # A lighter chin-tip and a couple of whisker dashes for texture.
    pygame.draw.rect(
        surf, SCOTTY_COAT_HI,
        (beard_rect.right - radius * 0.22, beard_rect.top + 2, radius * 0.2, beard_rect.height - 4),
    )
    for i in range(2):
        wy = beard_rect.top + 4 + i * 6
        pygame.draw.line(surf, SCOTTY_OUTLINE, (beard_rect.left + 3, wy), (beard_rect.left + beard_w * 0.55, wy), 1)

    nose_x = beard_rect.right - radius * 0.08
    nose_y = beard_rect.centery - radius * 0.1
    pygame.draw.circle(surf, (18, 14, 12), (round(nose_x), round(nose_y)), max(2, round(radius * 0.13)))

    if mouth_open:
        pygame.draw.arc(
            surf, SCOTTY_OUTLINE,
            (beard_rect.left + radius * 0.15, beard_rect.centery, beard_rect.width * 0.5, beard_rect.height * 0.5),
            3.4, 6.0, 2,
        )

    # Bushy eyebrow -- a thick tuft above the eye, the third defining
    # Scottie feature, then the eye itself underneath it.
    eye_x = cx + radius * 0.30
    eye_y = head_cy - radius * 0.05
    for dx in (-3, 0, 3):
        pygame.draw.line(
            surf, SCOTTY_BROW,
            (eye_x - radius * 0.32 + dx, eye_y - radius * 0.42),
            (eye_x + radius * 0.10 + dx, eye_y - radius * 0.30), 2,
        )
    pygame.draw.circle(surf, (250, 246, 238), (round(eye_x), round(eye_y)), max(3, round(radius * 0.2)))
    pygame.draw.circle(surf, (22, 18, 14), (round(eye_x), round(eye_y)), max(1, round(radius * 0.09)))


def make_scotty(size, pose, leg_phase=0):
    w, h = size
    surf = _surface(size)
    cx = w / 2.0
    feet_y = h - 2
    radius = config.HEAD_RADIUS
    head_cy = feet_y - config.HEAD_OFFSET_Y
    head_bottom = head_cy + radius

    _draw_kit(
        surf, cx, head_bottom, feet_y, radius, pose, leg_phase,
        kit_color=SCOTTY_KIT, kit_trim=SCOTTY_KIT_TRIM, outline_color=SCOTTY_OUTLINE,
        shorts_stripe=SCOTTY_KIT,
    )

    # Tail, drawn behind the head so it doesn't compete with the beard.
    pygame.draw.line(
        surf, SCOTTY_OUTLINE, (cx - radius * 0.95, head_cy + radius * 0.55),
        (cx - radius * 1.4, head_cy + radius * 0.1), 5,
    )

    _scotty_head(surf, cx, head_cy, radius, mouth_open=(pose == "kick"))
    return surf


# --- Rival -----------------------------------------------------------------------
def _rival_head(surf, cx, head_cy, radius):
    """A hard-edged, angular shape with a pointed chin, a single jagged
    dorsal crest instead of two ears, and two round eyes -- deliberately
    not a recoloured circle, so the two characters are distinguishable
    by silhouette alone (see the module's solid-black self-test note in
    main())."""
    # Hexagonal "shield" head: flat top, angled shoulders, a pointed chin.
    points = [
        (cx - radius * 0.62, head_cy - radius * 0.75),
        (cx + radius * 0.62, head_cy - radius * 0.75),
        (cx + radius * 0.98, head_cy - radius * 0.05),
        (cx + radius * 0.55, head_cy + radius * 0.75),
        (cx, head_cy + radius * 1.05),
        (cx - radius * 0.55, head_cy + radius * 0.75),
        (cx - radius * 0.98, head_cy - radius * 0.05),
    ]
    pygame.draw.polygon(surf, RIVAL_HIDE, points)
    pygame.draw.polygon(surf, RIVAL_OUTLINE, points, 2)
    # A darker angular cheek shade for a touch of depth.
    pygame.draw.polygon(
        surf, RIVAL_HIDE_SHADE,
        [
            (cx + radius * 0.98, head_cy - radius * 0.05), (cx + radius * 0.55, head_cy + radius * 0.75),
            (cx + radius * 0.15, head_cy + radius * 0.55), (cx + radius * 0.55, head_cy - radius * 0.05),
        ],
    )

    # A single jagged dorsal crest on top -- not two ears -- the clearest
    # single silhouette difference from Scotty's paired erect ears.
    crest_base_y = head_cy - radius * 0.75
    crest = [
        (cx - radius * 0.4, crest_base_y), (cx - radius * 0.18, crest_base_y - radius * 0.55),
        (cx + radius * 0.02, crest_base_y - radius * 0.15), (cx + radius * 0.22, crest_base_y - radius * 0.7),
        (cx + radius * 0.4, crest_base_y),
    ]
    pygame.draw.polygon(surf, RIVAL_HIDE, crest)
    pygame.draw.polygon(surf, RIVAL_OUTLINE, crest, 1)
    pygame.draw.line(surf, RIVAL_KIT_TRIM, crest[1], crest[3], 2)

    # Two round eyes, not one huge visor.
    for side, scale in ((-1, 0.85), (1, 1.0)):
        ex = cx + radius * 0.28 + side * radius * 0.30
        ey = head_cy - radius * 0.12
        r = radius * 0.22 * scale
        pygame.draw.circle(surf, (24, 28, 34), (round(ex), round(ey)), round(r))
        pygame.draw.circle(surf, RIVAL_KIT_TRIM, (round(ex), round(ey)), round(r), 1)
        pygame.draw.circle(surf, (150, 220, 255), (round(ex + r * 0.3), round(ey - r * 0.3)), max(1, round(r * 0.35)))


def make_rival(size, pose, leg_phase=0):
    w, h = size
    surf = _surface(size)
    cx = w / 2.0
    feet_y = h - 2
    radius = config.HEAD_RADIUS
    head_cy = feet_y - config.HEAD_OFFSET_Y
    head_bottom = head_cy + radius * 0.95  # the head's own chin point is slightly higher than a circle's

    _draw_kit(
        surf, cx, head_bottom, feet_y, radius, pose, leg_phase,
        kit_color=RIVAL_KIT, kit_trim=RIVAL_KIT_TRIM, outline_color=RIVAL_OUTLINE,
        shorts_stripe=RIVAL_KIT,
    )

    _rival_head(surf, cx, head_cy, radius)
    return surf


# --- Ball --------------------------------------------------------------------------
def make_ball(size):
    w, h = size
    surf = _surface(size)
    cx, cy = w / 2.0, h / 2.0
    r = min(w, h) / 2.0 - 1.0
    pygame.draw.circle(surf, (250, 250, 250), (round(cx), round(cy)), round(r))
    pygame.draw.circle(surf, (30, 30, 30), (round(cx), round(cy)), round(r), 2)
    pygame.draw.polygon(
        surf, (30, 30, 30),
        [
            (cx, cy - r * 0.5), (cx - r * 0.47, cy - r * 0.15),
            (cx - r * 0.29, cy + r * 0.4), (cx + r * 0.29, cy + r * 0.4),
            (cx + r * 0.47, cy - r * 0.15),
        ],
    )
    for angle_deg in (90, 162, 234, 306, 18):
        ax = cx + r * 0.8 * math.cos(math.radians(angle_deg))
        ay = cy + r * 0.8 * math.sin(math.radians(angle_deg))
        pygame.draw.line(surf, (30, 30, 30), (cx, cy - r * 0.5), (ax, ay), 1)
    return surf


# --- Goals -------------------------------------------------------------------------
def _draw_net(surf, x0, y0, x1, y1):
    step = config.NET_MESH
    for x in range(round(x0), round(x1) + 1, step):
        pygame.draw.line(surf, config.NET_COLOR, (x, y0), (x, y1), 1)
    for y in range(round(y0), round(y1) + 1, step):
        pygame.draw.line(surf, config.NET_COLOR, (x0, y), (x1, y), 1)


def make_goal(size, mirrored):
    """A goal frame in profile, authored so the *front* post (the one
    that opens into the pitch) sits on the pitch side of the canvas and
    the *back* of the net sits flush with the screen edge -- see
    render._draw_goals(), which anchors this image's bottom edge at the
    goal line with the canvas's outer edge flush against the screen
    boundary (config.PITCH_LEFT / PITCH_RIGHT).

    ``mirrored=False`` draws a left-hand goal (back of net at the
    canvas's left edge, front post at its right edge, opening rightward
    into the pitch); ``mirrored=True`` flips that for the right-hand goal.
    """
    w, h = size
    surf = _surface(size)
    post_t = config.POST_THICKNESS
    bar_t = config.CROSSBAR_THICKNESS

    # Net hatching first, so the frame sits visibly on top of it.
    _draw_net(surf, post_t, bar_t, w - post_t, h)

    def _post(rect):
        pygame.draw.rect(surf, GOAL_POST, rect)
        pygame.draw.rect(surf, GOAL_OUTLINE, rect, 2)

    _post((0, bar_t, post_t, h - bar_t))          # back post, flush with the screen edge
    _post((w - post_t, bar_t, post_t, h - bar_t))  # front post, opens into the pitch
    _post((0, 0, w, bar_t))                        # crossbar

    if mirrored:
        surf = pygame.transform.flip(surf, True, False)
    return surf


def make_goal_left(size):
    return make_goal(size, mirrored=False)


def make_goal_right(size):
    return make_goal(size, mirrored=True)


# --- Stadium backdrop ----------------------------------------------------------------
def make_bg_stadium(size):
    """Sky, floodlights, tiered stands, and a crowd -- what replaces the
    old top-down green pitch wall. No pitch markings are drawn anywhere
    in this file, on purpose: the genre research report found zero
    side-view head-soccer implementations that draw a centre circle,
    halfway line, or boundary rect.

    The crowd is deliberately restrained rather than maximally dense:
    per the report, the *minimal* fidelity tier some clones use is
    nothing more than a flat sky fill, and a clean sky-plus-stands
    silhouette reads better at this resolution than a maximally busy
    one -- so this leans toward "readable texture", not "as many dots
    as will fit".

    The canvas is taller than the stands themselves: below the stands
    proper (config.HOARDING_Y) is a plain, solid perimeter wall-board
    strip down to where the ground sprite begins (config.GROUND_SPRITE_Y).
    render.py only ever draws the *scrolling* hoarding graphic in the
    span between the two goals (see its hoarding-span note) -- behind
    each goal, this plain wall-board colour shows instead, so the
    scrolling advertising never appears to run *through* a goal mouth.
    """
    w, h = size
    stadium_h = config.HOARDING_Y  # the stands/sky proper; the rest is wall board
    surf = pygame.Surface(size)
    surf.fill(WALL_BOARD_COLOR)

    horizon = round(stadium_h * 0.55)
    for y in range(horizon):
        t = y / max(1, horizon - 1)
        surf.fill(_lerp_color(SKY_TOP, SKY_HORIZON, t), (0, y, w, 1))

    stand_top = round(stadium_h * 0.20)
    tier_h = (stadium_h - stand_top) // 3
    tiers = [
        (stand_top, STAND_FAR),
        (stand_top + tier_h, STAND_MID),
        (stand_top + tier_h * 2, STAND_NEAR),
    ]
    for tier_y, color in tiers:
        pygame.draw.rect(surf, color, (0, tier_y, w, stadium_h - tier_y))
    # A thin lighter seam at the top edge of each tier -- reads as the
    # parapet/step between tiers without drawing an actual 3D ledge.
    for tier_y, color in tiers:
        pygame.draw.rect(surf, _lerp_color(color, (255, 255, 255), 0.25), (0, tier_y, w, 3))

    # Crowd: small figures on a deterministic formulaic scatter (not
    # random.random(), so regenerating this file twice is byte-identical).
    # Wide gaps between figures and a muted palette (each crowd color is
    # blended toward its tier's own background shade, not shown at full
    # saturation) keep this reading as a distant, textured crowd rather
    # than a wall of bright confetti competing with the gameplay below it.
    for tier_index, (tier_y, tier_color) in enumerate(tiers):
        dot_w = 4 + tier_index
        dot_h = 5 + tier_index
        col_pitch = 20 - tier_index * 2  # far tier: sparser horizontally too
        row_pitch = dot_h + 10
        rows = max(1, (tier_h - 12) // row_pitch)
        cols = w // col_pitch
        for row in range(rows):
            y = tier_y + 8 + row * row_pitch
            for col in range(cols):
                # Skip most slots so gaps between spectators dominate --
                # a texture, not a solid band.
                if (col * 7 + row * 3 + tier_index * 5) % 5 != 0:
                    continue
                x = col * col_pitch + ((row + tier_index) % 2) * (col_pitch // 2)
                raw_color = CROWD_COLORS[(col * 3 + row * 5 + tier_index * 7) % len(CROWD_COLORS)]
                color = _lerp_color(raw_color, tier_color, 0.35)
                pygame.draw.rect(surf, color, (x, y, dot_w, dot_h))

    # Floodlights: four poles with a glowing fixture, evenly spread.
    for pole_x in (round(w * 0.08), round(w * 0.34), round(w * 0.66), round(w * 0.92)):
        pygame.draw.rect(surf, FLOODLIGHT_COLOR, (pole_x - 3, 10, 6, stand_top))
        head_rect = pygame.Rect(0, 0, 46, 20)
        head_rect.center = (pole_x, 14)
        pygame.draw.rect(surf, FLOODLIGHT_COLOR, head_rect, border_radius=3)
        for i in range(5):
            lx = head_rect.left + 6 + i * 8
            pygame.draw.circle(surf, FLOODLIGHT_GLOW, (lx, head_rect.centery), 3)

    return surf


def make_bg_hoarding(size):
    """A horizontal advertising band, blitted twice with a wrapping
    offset by render.py for a continuous scroll (see
    config.HOARDING_SCROLL_SPEED)."""
    w, h = size
    surf = pygame.Surface(size)
    panel_w = w // 4
    colors = [(196, 32, 48), (245, 245, 245), (30, 60, 130), (240, 200, 40)]
    labels = ["HEADSCOTTER", "GAME DEV CLUB", "GO SCOTTY", "CMU ARCADE"]
    font = pygame.font.Font(None, 26)
    for i in range(4):
        rect = pygame.Rect(i * panel_w, 0, panel_w, h)
        surf.fill(colors[i], rect)
        text_color = (250, 250, 250) if sum(colors[i]) < 400 else (25, 25, 30)
        label = font.render(labels[i], True, text_color)
        label_rect = label.get_rect(center=rect.center)
        surf.blit(label, label_rect)
    pygame.draw.rect(surf, (15, 15, 15), (0, 0, w, h), 2)
    return surf


def make_ground(size):
    """A single flat-colour grass rectangle -- the sourced genre
    convention (research report, section 1c): "Plain, flat, single
    colour. Every implementation draws it as one filled rectangle. No
    mowed stripes, no gradient, no perspective in any of the seven."
    Mowing stripes are a top-down cue (only visible looking straight
    down at a lawn) and were exactly the previous build's mistake.

    The one genuine depth trick the report documents (martinlhw/
    Head_Soccer) is handled by *layout*, not by anything drawn here:
    this sprite is taller than the ground band below the collision line
    and is blitted starting config.GROUND_VISUAL_MARGIN above it (see
    config.GROUND_SPRITE_Y), so a sliver of grass is visible behind the
    players' feet instead of the sprite starting exactly at the
    collision line.
    """
    w, h = size
    surf = pygame.Surface(size)
    surf.fill(GRASS_LIGHT)
    return surf


# --- HUD scoreboard panel -----------------------------------------------------------
def make_scoreboard(size):
    w, h = size
    surf = _surface(size)
    panel_rect = pygame.Rect(0, 0, w, h)
    panel = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(panel, (12, 20, 32, 210), panel_rect, border_radius=14)
    pygame.draw.rect(panel, (240, 210, 90, 235), panel_rect, 3, border_radius=14)
    surf.blit(panel, (0, 0))

    # A small baked-in ball icon as the score divider decoration.
    cx, cy = w / 2.0, h * 0.42
    r = h * 0.16
    pygame.draw.circle(surf, (250, 250, 250), (round(cx), round(cy)), round(r))
    pygame.draw.circle(surf, (30, 30, 30), (round(cx), round(cy)), round(r), 1)
    return surf


GENERATORS = {
    "scotty_idle": lambda size: make_scotty(size, "idle"),
    "scotty_run_1": lambda size: make_scotty(size, "run", leg_phase=1),
    "scotty_run_2": lambda size: make_scotty(size, "run", leg_phase=2),
    "scotty_jump": lambda size: make_scotty(size, "jump"),
    "scotty_kick": lambda size: make_scotty(size, "kick"),
    "rival_idle": lambda size: make_rival(size, "idle"),
    "rival_run_1": lambda size: make_rival(size, "run", leg_phase=1),
    "rival_run_2": lambda size: make_rival(size, "run", leg_phase=2),
    "rival_jump": lambda size: make_rival(size, "jump"),
    "rival_kick": lambda size: make_rival(size, "kick"),
    "ball": make_ball,
    "goal_left": make_goal_left,
    "goal_right": make_goal_right,
    "bg_stadium": make_bg_stadium,
    "bg_hoarding": make_bg_hoarding,
    "ground": make_ground,
    "scoreboard": make_scoreboard,
}


def main() -> int:
    sprites_dir = ASSETS_ROOT / "sprites"
    sprites_dir.mkdir(parents=True, exist_ok=True)

    missing = sorted(set(SPRITE_SPECS) - set(GENERATORS))
    if missing:
        raise SystemExit(f"no placeholder generator registered for: {missing}")

    for name, (rel_path, size) in sorted(SPRITE_SPECS.items()):
        surface = GENERATORS[name](size)
        out_path = REPO_ROOT / "assets" / rel_path
        pygame.image.save(surface, str(out_path))
        print(f"wrote {out_path.relative_to(REPO_ROOT)}")

    print(f"generated {len(SPRITE_SPECS)} placeholder sprites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
