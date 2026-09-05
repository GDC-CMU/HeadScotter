# HeadScotter art assets

All gameplay art is loaded from the PNG files in `assets/sprites/` through
the single loader in `headscotter/assets.py`. Nothing else in the codebase
draws gameplay sprites procedurally, and nothing reads a sprite path
directly -- every file below is declared once in
`headscotter.assets.SPRITE_SPECS` (name -> relative path -> nominal pixel
size).

**To replace any piece of art, overwrite the file at the same path with
the same name, keeping (roughly) the same aspect ratio. No code changes
are required.** Every sprite is loaded once at first use, cached, and
scaled to its nominal size, so files of a different resolution still
work (they're rescaled), but keeping them native-sized avoids any blur
from upscaling.

Everything currently committed in `assets/sprites/` is a **placeholder**,
generated deterministically by `tools/generate_placeholders.py`. Re-run
that script any time you want to reset the stock look (for example after
adding a new logical sprite name to `SPRITE_SPECS`):

```
python tools/generate_placeholders.py
```

Missing or unreadable files never crash the game -- a bright magenta
placeholder with a crossed-out look is substituted, and a single warning
is printed to stderr, so an in-progress art pass never blocks testing.

## Contrast and silhouette (read this before drawing new art)

This is the single most important lesson carried over from the club's
other cabinet games, learned from real play-testing: **a character drawn
in a dark, "natural" color disappears against a busy background from a
few feet away.** Both characters must stay legible under fair lighting,
at cabinet viewing distance, at all times:

- Keep both characters bright/saturated enough (or give them a strong
  outline) that they read clearly against the green pitch and against
  each other.
- Keep the two characters' **silhouettes** distinct, not just their
  colors -- Scotty has floppy ears and a snout; the rival has antenna and
  a visor and no ears at all. If you redraw either one, preserve (or
  exaggerate) that silhouette difference so a colorblind visitor, or
  just a fast glance, can still tell them apart instantly.
- The ball must never blend into the grass or either character -- keep
  it light, with a visible dark pattern.

## Player geometry

Player sprites are anchored **feet-down**: the image's bottom-center
pixel is drawn at the character's feet position. The collidable "head"
is a circle of radius `HEAD_RADIUS` (34px) centered `HEAD_OFFSET_Y`
(78px) above the feet (`headscotter/config.py`) -- keep a replacement
sprite's head roughly in that same place so it still lines up with
where the ball actually bounces off it. All four poses per character
share one canvas size; art only facing **right** is needed, since
`headscotter/render.py` mirrors the sprite in code when a character
faces left.

| Files | Size | Used for |
|---|---|---|
| `scotty_run_1.png`, `scotty_run_2.png` | 110x150 | Scotty (P1 / 1P human), running -- two-frame leg cycle |
| `scotty_jump.png` | 110x150 | Scotty airborne (jumping or falling) |
| `scotty_kick.png` | 110x150 | Scotty, briefly, right after a kick connects |
| `rival_run_1.png`, `rival_run_2.png` | 110x150 | The rival (CPU / P2), running |
| `rival_jump.png` | 110x150 | The rival airborne |
| `rival_kick.png` | 110x150 | The rival, briefly, right after a kick connects |

**Scotty** is CMU's mascot, a Scottish Terrier, drawn big-headed
head-soccer style: floppy pointed ears, a snout, a shaggy fur texture,
and a CMU-red collar stripe, on a warm cream/tan coat for contrast.

**The rival** is a deliberately original, distinct opponent -- not a
copy of any commercial game's character -- with a completely different
silhouette from Scotty: antenna instead of ears, one wide visor instead
of a snout, and a rectangular jersey body instead of a rounded one, in
cool blue-grey with orange trim.

## Ball and pitch

| File | Size | Used for |
|---|---|---|
| `ball.png` | 36x36 | The ball. Matches `BALL_RADIUS` in `headscotter/config.py`. |
| `goal.png` | 90x200 | One goal frame. Drawn once per end; the right-hand goal is this same file mirrored in code, not a separate asset. Authored with the front post at the image's right edge and the net trailing off the left edge, so it opens correctly into the pitch when anchored at the goal line (see `render._draw_goals()`). The crossbar sits `GOAL_MOUTH_HEIGHT` px up from the image's bottom, matching where the ball can actually score. Sized to read as a real, credible net at full screen size -- taller than a standing player -- not shrunk to hold down scoring; see `headscotter/keeper.py` for what actually defends it. |
| `pitch_bg.png` | 800x600 | The full-screen background: grass stripes below `PITCH_TOP`, a stand/sky band above it. The halfway line, center circle, and touchline are drawn directly by `render.py`, not baked into this image. |
| `hud_ball_icon.png` | 32x32 | A small ball glyph used as the "-" divider between the two scores in the HUD. |

## Goalkeepers

Every goal has its own automated keeper (`headscotter/keeper.py`) -- a
simple vertical paddle, never controlled by a human or the CPU field-AI,
that glides up and down within the goal mouth to make saves. It never
runs, jumps, or leaves a fixed depth in front of its goal line, so it
only needs **one static pose each**, not a walk cycle:

| File | Size | Used for |
|---|---|---|
| `keeper_left.png` | 72x72 | Defends the left goal. Team-colored to match Scotty (cream body, CMU-red cap/gloves trim), so it visually reads as "on Scotty's side" even though it's automated. |
| `keeper_right.png` | 72x72 | Defends the right goal. Team-colored to match the rival (blue body, orange trim). |

The collidable circle is `KEEPER_RADIUS` (32px, `headscotter/config.py`),
centered on the sprite -- keep a replacement sprite's body centered in
the canvas so it still lines up with where the ball actually bounces off it.

## Adding a brand-new sprite

1. Add an entry to `SPRITE_SPECS` in `headscotter/assets.py` (name,
   relative path, nominal size).
2. Add a matching generator function in `tools/generate_placeholders.py`
   so the placeholder set stays complete, then run the script.
3. Reference the new sprite by name from `headscotter/render.py` with
   `assets.get("your_new_name")`.
