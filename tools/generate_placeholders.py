#!/usr/bin/env python
"""Regenerate the committed placeholder sprite PNGs deterministically.

Every shape here is drawn with fixed coordinates (no randomness), so
running this script twice in a row leaves ``git status`` clean. Run it
whenever a new logical sprite is added to
``headscotter.assets.SPRITE_SPECS``, or any time you want to reset
``assets/sprites/`` back to the stock placeholder look.

These placeholders are deliberately more than flat rectangles -- a
shaggy-eared terrier for Scotty, a distinct antenna'd rival with a very
different silhouette, a real soccer-ball pattern, and a proper goal
frame -- so the repo looks intentional from the first clone. Real art
can replace any file here with zero code changes; see ``assets/README.md``.
"""
from __future__ import annotations

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

TRANSPARENT = (0, 0, 0, 0)

# Scotty: warm cream/tan coat (matches the club's other games' lesson that
# a dark dog on a busy background disappears) with CMU-red trim.
SCOTTY_BODY = (224, 196, 140)
SCOTTY_SHADE = (188, 156, 100)
SCOTTY_OUTLINE = (96, 72, 40)
SCOTTY_TRIM = (196, 32, 48)

# Rival: cool blue-grey with a completely different silhouette (antenna,
# no ears, single big visor-eye instead of a snout) so the two are never
# confusable even in pure silhouette.
RIVAL_BODY = (150, 190, 235)
RIVAL_SHADE = (108, 146, 196)
RIVAL_OUTLINE = (40, 58, 92)
RIVAL_TRIM = (255, 176, 40)

GRASS_LIGHT = (36, 128, 60)
GRASS_DARK = (28, 112, 52)
STAND_COLOR = (30, 40, 34)


def _surface(size):
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill(TRANSPARENT)
    return surf


# --- Scotty ------------------------------------------------------------------------
def _scotty_head(surf, cx, head_cy, radius, mouth_open):
    # Shaggy fur bumps around the back/top of the head.
    for angle in (150, 175, 200, 225):
        import math

        bx = cx + radius * 0.85 * math.cos(math.radians(angle))
        by = head_cy + radius * 0.85 * math.sin(math.radians(angle))
        pygame.draw.circle(surf, SCOTTY_SHADE, (round(bx), round(by)), max(2, round(radius * 0.22)))

    pygame.draw.circle(surf, SCOTTY_BODY, (round(cx), round(head_cy)), round(radius))
    pygame.draw.circle(surf, SCOTTY_OUTLINE, (round(cx), round(head_cy)), round(radius), 2)

    # Two floppy, pointed ears on top.
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

    # Snout, pushed toward the facing direction (right, mirrored in code).
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
    feet_y = h - 4
    radius = config.HEAD_RADIUS
    head_cy = h - config.HEAD_OFFSET_Y

    body_top = head_cy + radius * 0.55
    body_h = feet_y - body_top - 14

    if pose == "kick":
        # Kicking leg extended forward (right) and up; planted leg back.
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx - 6, body_top + body_h), (cx - 14, feet_y), 10)
        pygame.draw.line(
            surf, SCOTTY_OUTLINE, (cx + 4, body_top + body_h * 0.6),
            (cx + radius * 1.1, body_top + body_h * 0.15), 10,
        )
    elif pose == "jump":
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx - 10, body_top + body_h * 0.5), (cx - 16, feet_y - 10), 10)
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx + 10, body_top + body_h * 0.5), (cx + 16, feet_y - 10), 10)
    else:  # run
        offset = 14 if leg_phase == 1 else -14
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx - 6, body_top + body_h * 0.4), (cx - 6 + offset, feet_y), 10)
        pygame.draw.line(surf, SCOTTY_OUTLINE, (cx + 6, body_top + body_h * 0.4), (cx + 6 - offset, feet_y), 10)

    body_rect = pygame.Rect(0, 0, radius * 1.5, body_h)
    body_rect.midtop = (cx, body_top)
    pygame.draw.ellipse(surf, SCOTTY_BODY, body_rect)
    pygame.draw.ellipse(surf, SCOTTY_OUTLINE, body_rect, 2)
    # A CMU-red collar/jersey stripe across the chest.
    pygame.draw.rect(surf, SCOTTY_TRIM, (body_rect.left + 4, body_rect.top + body_rect.height * 0.3, body_rect.width - 8, 6))

    # Short tail at the rear (left, opposite the snout).
    pygame.draw.line(
        surf, SCOTTY_OUTLINE, (cx - radius * 0.9, head_cy + radius * 0.6),
        (cx - radius * 1.35, head_cy + radius * 0.2), 6,
    )

    _scotty_head(surf, cx, head_cy, radius, mouth_open=(pose == "kick"))
    return surf


# --- Rival -----------------------------------------------------------------------
def _rival_head(surf, cx, head_cy, radius):
    pygame.draw.circle(surf, RIVAL_BODY, (round(cx), round(head_cy)), round(radius))
    pygame.draw.circle(surf, RIVAL_OUTLINE, (round(cx), round(head_cy)), round(radius), 2)

    # Two antenna instead of ears -- an unmistakably different silhouette.
    for side in (-1, 1):
        bx = cx + side * radius * 0.5
        by = head_cy - radius * 0.85
        pygame.draw.line(surf, RIVAL_OUTLINE, (bx, by), (bx, by - radius * 0.5), 4)
        pygame.draw.circle(surf, RIVAL_TRIM, (round(bx), round(by - radius * 0.5)), max(3, round(radius * 0.16)))

    # One big visor-eye instead of a snout.
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
    feet_y = h - 4
    radius = config.HEAD_RADIUS
    head_cy = h - config.HEAD_OFFSET_Y

    body_top = head_cy + radius * 0.55
    body_h = feet_y - body_top - 14

    if pose == "kick":
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx - 6, body_top + body_h), (cx - 14, feet_y), 10)
        pygame.draw.line(
            surf, RIVAL_OUTLINE, (cx + 4, body_top + body_h * 0.6),
            (cx + radius * 1.1, body_top + body_h * 0.15), 10,
        )
    elif pose == "jump":
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx - 10, body_top + body_h * 0.5), (cx - 16, feet_y - 10), 10)
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx + 10, body_top + body_h * 0.5), (cx + 16, feet_y - 10), 10)
    else:
        offset = 14 if leg_phase == 1 else -14
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx - 6, body_top + body_h * 0.4), (cx - 6 + offset, feet_y), 10)
        pygame.draw.line(surf, RIVAL_OUTLINE, (cx + 6, body_top + body_h * 0.4), (cx + 6 - offset, feet_y), 10)

    # Rectangular jersey body (vs. Scotty's rounded body) -- another
    # silhouette difference beyond color.
    body_rect = pygame.Rect(0, 0, radius * 1.4, body_h)
    body_rect.midtop = (cx, body_top)
    pygame.draw.rect(surf, RIVAL_BODY, body_rect, border_radius=6)
    pygame.draw.rect(surf, RIVAL_OUTLINE, body_rect, 2, border_radius=6)
    pygame.draw.rect(
        surf, RIVAL_TRIM,
        (body_rect.left + 4, body_rect.top + body_rect.height * 0.3, body_rect.width - 8, 6),
    )

    _rival_head(surf, cx, head_cy, radius)
    return surf


# --- Ball --------------------------------------------------------------------------
def make_ball(size):
    w, h = size
    surf = _surface(size)
    cx, cy = w / 2.0, h / 2.0
    r = min(w, h) / 2.0 - 1.5
    pygame.draw.circle(surf, (250, 250, 250), (round(cx), round(cy)), round(r))
    pygame.draw.circle(surf, (30, 30, 30), (round(cx), round(cy)), round(r), 2)
    # A simple pentagon-patch pattern, just enough to read as a soccer ball.
    pygame.draw.polygon(
        surf, (30, 30, 30),
        [
            (cx, cy - r * 0.5), (cx - r * 0.47, cy - r * 0.15),
            (cx - r * 0.29, cy + r * 0.4), (cx + r * 0.29, cy + r * 0.4),
            (cx + r * 0.47, cy - r * 0.15),
        ],
    )
    for angle_deg in (90, 162, 234, 306, 18):
        import math

        ax = cx + r * 0.8 * math.cos(math.radians(angle_deg))
        ay = cy + r * 0.8 * math.sin(math.radians(angle_deg))
        pygame.draw.line(surf, (30, 30, 30), (cx, cy - r * 0.5), (ax, ay), 1)
    return surf


# --- Goal ----------------------------------------------------------------------------
def make_goal(size):
    """A goal frame authored so its RIGHT edge is the goal line (posts
    facing into the pitch) and it extends left into "out of bounds" for
    the net -- see render._draw_goals(), which anchors this image's
    bottom-right corner at the pitch's goal line."""
    w, h = size
    surf = _surface(size)
    post_thickness = 10
    crossbar_y = h - config.GOAL_MOUTH_HEIGHT
    post_color = (245, 245, 245)
    post_outline = (55, 60, 65)
    net_color = (150, 175, 170, 160)

    # Net hatching, drawn first so the frame sits on top of it.
    step = 14
    for x in range(0, w, step):
        pygame.draw.line(surf, net_color, (x, crossbar_y), (x, h), 1)
    for y in range(round(crossbar_y), h, step):
        pygame.draw.line(surf, net_color, (0, y), (w, y), 1)

    def _post(rect):
        pygame.draw.rect(surf, post_color, rect)
        pygame.draw.rect(surf, post_outline, rect, 2)

    # Back post (left edge of the image, deepest into the net).
    _post((0, crossbar_y, post_thickness, h - crossbar_y))
    # Front post (right edge -- sits on the goal line).
    _post((w - post_thickness, crossbar_y, post_thickness, h - crossbar_y))
    # Crossbar joining them along the top of the goal mouth.
    _post((0, crossbar_y, w, post_thickness))
    return surf


# --- Pitch background ----------------------------------------------------------------
def make_pitch_bg(size):
    w, h = size
    surf = pygame.Surface(size)
    surf.fill(STAND_COLOR)
    pygame.draw.rect(surf, STAND_COLOR, (0, 0, w, config.PITCH_TOP))
    stripe_w = 40
    for i, x in enumerate(range(0, w, stripe_w)):
        color = GRASS_LIGHT if i % 2 == 0 else GRASS_DARK
        pygame.draw.rect(surf, color, (x, config.PITCH_TOP, stripe_w, h - config.PITCH_TOP))
    return surf


def make_hud_ball_icon(size):
    return make_ball(size)


GENERATORS = {
    "scotty_run_1": lambda size: make_scotty(size, "run", leg_phase=1),
    "scotty_run_2": lambda size: make_scotty(size, "run", leg_phase=2),
    "scotty_jump": lambda size: make_scotty(size, "jump"),
    "scotty_kick": lambda size: make_scotty(size, "kick"),
    "rival_run_1": lambda size: make_rival(size, "run", leg_phase=1),
    "rival_run_2": lambda size: make_rival(size, "run", leg_phase=2),
    "rival_jump": lambda size: make_rival(size, "jump"),
    "rival_kick": lambda size: make_rival(size, "kick"),
    "ball": make_ball,
    "goal": make_goal,
    "pitch_bg": make_pitch_bg,
    "hud_ball_icon": make_hud_ball_icon,
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
