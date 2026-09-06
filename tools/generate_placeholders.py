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

# --- Scotty: warm cream/tan coat with CMU-red trim ---------------------------------
SCOTTY_BODY = (224, 196, 140)
SCOTTY_SHADE = (188, 156, 100)
SCOTTY_OUTLINE = (96, 72, 40)
SCOTTY_TRIM = (196, 32, 48)

# --- Rival: cool blue-grey, a completely different silhouette -----------------------
RIVAL_BODY = (150, 190, 235)
RIVAL_SHADE = (108, 146, 196)
RIVAL_OUTLINE = (40, 58, 92)
RIVAL_TRIM = (255, 176, 40)

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
GRASS_DARK = (46, 132, 64)
GOAL_POST = (238, 238, 238)
GOAL_OUTLINE = (55, 60, 65)


def _surface(size):
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill(TRANSPARENT)
    return surf


def _lerp_color(c0, c1, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))


# --- Scotty ------------------------------------------------------------------------
def _scotty_head(surf, cx, head_cy, radius, mouth_open):
    for angle in (150, 175, 200, 225):
        bx = cx + radius * 0.85 * math.cos(math.radians(angle))
        by = head_cy + radius * 0.85 * math.sin(math.radians(angle))
        pygame.draw.circle(surf, SCOTTY_SHADE, (round(bx), round(by)), max(2, round(radius * 0.22)))

    pygame.draw.circle(surf, SCOTTY_BODY, (round(cx), round(head_cy)), round(radius))
    pygame.draw.circle(surf, SCOTTY_OUTLINE, (round(cx), round(head_cy)), round(radius), 2)

    for side in (-1, 1):
        ex = cx + side * radius * 0.55
        ey = head_cy - radius * 0.65
        pygame.draw.polygon(
            surf, SCOTTY_SHADE,
            [(ex - radius * 0.22, ey), (ex + radius * 0.22 * side, ey - radius * 0.05),
             (ex + radius * 0.05 * side, ey + radius * 0.55)],
        )
        pygame.draw.polygon(
            surf, SCOTTY_OUTLINE,
            [(ex - radius * 0.22, ey), (ex + radius * 0.22 * side, ey - radius * 0.05),
             (ex + radius * 0.05 * side, ey + radius * 0.55)],
            1,
        )

    snout_cx = cx + radius * 0.92
    snout_cy = head_cy + radius * 0.18
    snout_rect = pygame.Rect(0, 0, radius * 0.95, radius * 0.7)
    snout_rect.center = (snout_cx, snout_cy)
    pygame.draw.ellipse(surf, SCOTTY_SHADE, snout_rect)
    pygame.draw.ellipse(surf, SCOTTY_OUTLINE, snout_rect, 1)

    nose_x = snout_cx + radius * 0.42
    pygame.draw.circle(surf, SCOTTY_OUTLINE, (round(nose_x), round(snout_cy)), max(2, round(radius * 0.12)))

    if mouth_open:
        pygame.draw.arc(
            surf, SCOTTY_OUTLINE,
            (snout_cx - radius * 0.3, snout_cy, radius * 0.6, radius * 0.4),
            3.4, 6.0, 2,
        )

    eye_x = cx + radius * 0.18
    eye_y = head_cy - radius * 0.28
    pygame.draw.circle(surf, (255, 250, 240), (round(eye_x), round(eye_y)), max(3, round(radius * 0.22)))
    pygame.draw.circle(surf, (25, 20, 15), (round(eye_x), round(eye_y)), max(1, round(radius * 0.1)))


def make_scotty(size, pose, leg_phase=0):
    w, h = size
    surf = _surface(size)
    cx = w / 2.0
    feet_y = h - 3
    radius = config.HEAD_RADIUS
    head_cy = h - config.HEAD_OFFSET_Y

    # The body only has a sliver of vertical room below the head at this
    # scale (by design -- the genre's "big head, tiny body" silhouette),
    # so it is drawn wide and starts right at the head's own edge (a
    # small deliberate overlap for a seamless neck join) rather than
    # trying to squeeze a separate neck gap in.
    body_top = head_cy + radius * 0.68
    body_h = max(10, feet_y - body_top - 8)

    if pose == "kick":
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx - 6, body_top + body_h * 0.7), (cx - 13, feet_y), 9)
        pygame.draw.line(
            surf, SCOTTY_OUTLINE, (cx + 4, body_top + body_h * 0.55),
            (cx + radius * 1.15, head_cy + radius * 0.35), 9,
        )
    elif pose == "jump":
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx - 9, body_top + body_h * 0.5), (cx - 15, feet_y - 8), 9)
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx + 9, body_top + body_h * 0.5), (cx + 15, feet_y - 8), 9)
    elif pose == "idle":
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx - 6, body_top + body_h * 0.4), (cx - 6, feet_y), 9)
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx + 6, body_top + body_h * 0.4), (cx + 6, feet_y), 9)
    else:  # run
        offset = 12 if leg_phase == 1 else -12
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx - 6, body_top + body_h * 0.4), (cx - 6 + offset, feet_y), 9)
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx + 6, body_top + body_h * 0.4), (cx + 6 - offset, feet_y), 9)

    body_rect = pygame.Rect(0, 0, radius * 1.7, body_h)
    body_rect.midtop = (cx, body_top)
    pygame.draw.ellipse(surf, SCOTTY_BODY, body_rect)
    pygame.draw.ellipse(surf, SCOTTY_OUTLINE, body_rect, 2)
    pygame.draw.rect(
        surf, SCOTTY_TRIM,
        (body_rect.left + 3, body_rect.top + body_rect.height * 0.35, body_rect.width - 6, 6),
    )

    tail_wag = 1.35 if pose == "idle" else 1.2
    pygame.draw.line(
        surf, SCOTTY_OUTLINE, (cx - radius * 0.9, head_cy + radius * 0.6),
        (cx - radius * tail_wag, head_cy + radius * 0.15), 5,
    )

    _scotty_head(surf, cx, head_cy, radius, mouth_open=(pose == "kick"))
    return surf


# --- Rival -----------------------------------------------------------------------
def _rival_head(surf, cx, head_cy, radius):
    pygame.draw.circle(surf, RIVAL_BODY, (round(cx), round(head_cy)), round(radius))
    pygame.draw.circle(surf, RIVAL_OUTLINE, (round(cx), round(head_cy)), round(radius), 2)

    for side in (-1, 1):
        bx = cx + side * radius * 0.5
        by = head_cy - radius * 0.85
        pygame.draw.line(surf, RIVAL_OUTLINE, (bx, by), (bx, by - radius * 0.5), 3)
        pygame.draw.circle(surf, RIVAL_TRIM, (round(bx), round(by - radius * 0.5)), max(3, round(radius * 0.16)))

    visor_rect = pygame.Rect(0, 0, radius * 1.3, radius * 0.55)
    visor_rect.center = (cx + radius * 0.15, head_cy)
    pygame.draw.ellipse(surf, (20, 24, 30), visor_rect)
    pygame.draw.ellipse(surf, RIVAL_TRIM, visor_rect, 2)
    pygame.draw.ellipse(
        surf, (140, 220, 255),
        (visor_rect.right - radius * 0.5, visor_rect.centery - radius * 0.12, radius * 0.35, radius * 0.24),
    )


def make_rival(size, pose, leg_phase=0):
    w, h = size
    surf = _surface(size)
    cx = w / 2.0
    feet_y = h - 3
    radius = config.HEAD_RADIUS
    head_cy = h - config.HEAD_OFFSET_Y

    body_top = head_cy + radius * 0.68
    body_h = max(10, feet_y - body_top - 8)

    if pose == "kick":
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx - 6, body_top + body_h * 0.7), (cx - 13, feet_y), 9)
        pygame.draw.line(
            surf, RIVAL_OUTLINE, (cx + 4, body_top + body_h * 0.55),
            (cx + radius * 1.15, head_cy + radius * 0.35), 9,
        )
    elif pose == "jump":
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx - 9, body_top + body_h * 0.5), (cx - 15, feet_y - 8), 9)
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx + 9, body_top + body_h * 0.5), (cx + 15, feet_y - 8), 9)
    elif pose == "idle":
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx - 6, body_top + body_h * 0.4), (cx - 6, feet_y), 9)
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx + 6, body_top + body_h * 0.4), (cx + 6, feet_y), 9)
    else:
        offset = 12 if leg_phase == 1 else -12
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx - 6, body_top + body_h * 0.4), (cx - 6 + offset, feet_y), 9)
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx + 6, body_top + body_h * 0.4), (cx + 6 - offset, feet_y), 9)

    body_rect = pygame.Rect(0, 0, radius * 1.6, body_h)
    body_rect.midtop = (cx, body_top)
    pygame.draw.rect(surf, RIVAL_BODY, body_rect, border_radius=5)
    pygame.draw.rect(surf, RIVAL_OUTLINE, body_rect, 2, border_radius=5)
    pygame.draw.rect(
        surf, RIVAL_TRIM,
        (body_rect.left + 3, body_rect.top + body_rect.height * 0.35, body_rect.width - 6, 6),
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
    """Sky, floodlights, tiered stands, and a dithered crowd -- what
    replaces the old top-down green pitch wall. No pitch markings are
    drawn anywhere in this file, on purpose: the genre research report
    found zero side-view head-soccer implementations that draw a centre
    circle, halfway line, or boundary rect.
    """
    w, h = size
    surf = pygame.Surface(size)

    horizon = round(h * 0.62)
    for y in range(horizon):
        t = y / max(1, horizon - 1)
        surf.fill(_lerp_color(SKY_TOP, SKY_HORIZON, t), (0, y, w, 1))

    stand_top = round(h * 0.30)
    tier_h = (h - stand_top) // 3
    tiers = [
        (stand_top, STAND_FAR),
        (stand_top + tier_h, STAND_MID),
        (stand_top + tier_h * 2, STAND_NEAR),
    ]
    for tier_y, color in tiers:
        pygame.draw.rect(surf, color, (0, tier_y, w, h - tier_y))
    # A thin lighter seam at the top edge of each tier -- reads as the
    # parapet/step between tiers without drawing an actual 3D ledge.
    for tier_y, color in tiers:
        pygame.draw.rect(surf, _lerp_color(color, (255, 255, 255), 0.25), (0, tier_y, w, 3))

    # Crowd: small figures on a deterministic formulaic scatter (not
    # random.random(), so regenerating this file twice is byte-identical),
    # sparse enough to read as individual spectators rather than a solid
    # band -- roughly a third of each row is left as empty seat/gap, and
    # the far tier's figures are smaller and more sparsely spaced than the
    # near tier's, a cheap depth cue.
    for tier_index, (tier_y, _color) in enumerate(tiers):
        # Nearest tier (index 2) gets the biggest, densest figures.
        dot_w = 4 + tier_index
        dot_h = 5 + tier_index
        col_pitch = 11 - tier_index  # far tier: sparser horizontally too
        row_pitch = dot_h + 5
        rows = max(1, (tier_h - 12) // row_pitch)
        cols = w // col_pitch
        for row in range(rows):
            y = tier_y + 8 + row * row_pitch
            for col in range(cols):
                # Skip roughly a third of the slots so gaps between
                # spectators are visible instead of a solid wall of color.
                if (col * 7 + row * 3 + tier_index * 5) % 3 == 0:
                    continue
                x = col * col_pitch + ((row + tier_index) % 2) * (col_pitch // 2)
                color = CROWD_COLORS[(col * 3 + row * 5 + tier_index * 7) % len(CROWD_COLORS)]
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

    # Perimeter wall band at the very bottom, behind where the scrolling
    # hoarding sprite will be blitted on top (see config.HOARDING_Y).
    pygame.draw.rect(surf, (24, 30, 36), (0, h - config.HOARDING_HEIGHT, w, config.HOARDING_HEIGHT))
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
    w, h = size
    surf = pygame.Surface(size)
    stripe_w = 44
    for i, x in enumerate(range(0, w, stripe_w)):
        color = GRASS_LIGHT if i % 2 == 0 else GRASS_DARK
        pygame.draw.rect(surf, color, (x, 0, stripe_w, h))
    # A subtle lighter band along the very top edge -- the "front lip" of
    # the grass nearest the pitch, giving the strip a touch of depth
    # without any perspective drawing or pitch markings.
    pygame.draw.rect(surf, _lerp_color(GRASS_LIGHT, (255, 255, 255), 0.12), (0, 0, w, 4))
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
