"""Joint player/ball stepping and constrained, post-integration contacts.

Player heads and torsos form a union of solids. Resolving each in isolation
can push a ball into its neighbour or through the floor. Instead, project to
the nearest locally reachable point OUTSIDE the entire union, including the
pitch. In 2D the candidates are boundary projections and intersections.

If closing kinematic players leave no such point, shorten only the involved
players' proposed motion. Never shuttle an embedded ball between two solids
or pop it over a head to escape a ground squeeze. Velocity uses relative
collider motion, then a simultaneous non-penetrating velocity projection.

No input, RNG, pygame or audio dependency. CPU forecasts use this same solver
on copies, without an impact callback.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Callable, Optional, Sequence

from . import config, physics, players
from .physics import Ball
from .players import Player

MAX_STEP_SECONDS = 1 / 120.0
EPS = 1e-7
CONTACT_EPS = 2e-6


@dataclass(frozen=True)
class Circle:
    x: float
    y: float
    radius: float


@dataclass(frozen=True)
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class Contact:
    name: str
    nx: float
    ny: float
    restitution: float
    actor: Optional[Player] = None
    lift: float = 0.0

    @property
    def velocity(self):
        return (self.actor.vx, self.actor.vy) if self.actor is not None else (0.0, 0.0)


def _body_gap(x, y, actor, radius):
    left, top, right, bottom = players.body_rect(actor)
    dx = x - physics.clamp(x, left, right)
    dy = y - physics.clamp(y, top, bottom)
    return math.hypot(dx, dy) - radius


def _pose_gap(point, pose, radius):
    x, y = point
    px, py = pose
    head = math.hypot(x - px, y - (py - config.HEAD_OFFSET_Y)) - config.HEAD_RADIUS - radius
    top = py - (config.HEAD_OFFSET_Y - config.HEAD_RADIUS)
    dx = x - physics.clamp(x, px - config.PLAYER_HALF_WIDTH, px + config.PLAYER_HALF_WIDTH)
    dy = y - physics.clamp(y, top, py)
    return min(head, math.hypot(dx, dy) - radius)


def is_clear(ball: Ball, actors: Sequence[Player], point=None) -> bool:
    """Rendered-state invariant; also used by local debug/regression tools."""
    x, y = point if point is not None else ball.pos
    r = ball.radius
    if y < config.PITCH_TOP + r - EPS or y > config.GROUND_Y - r + EPS:
        return False
    for side in ("left", "right"):
        if physics.post_contact(x, y, r, side)[0] < -EPS:
            return False
    for actor in actors:
        hx, hy = actor.head_center
        if math.hypot(x - hx, y - hy) < config.HEAD_RADIUS + r - EPS:
            return False
        if _body_gap(x, y, actor, r) < -EPS:
            return False
    return True


def _project_segment(x, y, line):
    dx, dy = line.x2 - line.x1, line.y2 - line.y1
    length = dx * dx + dy * dy
    t = physics.clamp(((x - line.x1) * dx + (y - line.y1) * dy) / length, 0.0, 1.0) if length else 0.0
    return line.x1 + t * dx, line.y1 + t * dy


def _intersections(a, b):
    if isinstance(a, Circle) and isinstance(b, Circle):
        dx, dy = b.x - a.x, b.y - a.y
        distance = math.hypot(dx, dy)
        if distance < EPS or distance > a.radius + b.radius + EPS or distance < abs(a.radius - b.radius) - EPS:
            return []
        along = (a.radius * a.radius - b.radius * b.radius + distance * distance) / (2 * distance)
        height = math.sqrt(max(0.0, a.radius * a.radius - along * along))
        x, y = a.x + along * dx / distance, a.y + along * dy / distance
        return [(x - height * dy / distance, y + height * dx / distance),
                (x + height * dy / distance, y - height * dx / distance)]
    if isinstance(a, Circle):
        a, b = b, a
    if isinstance(b, Circle):
        dx, dy = a.x2 - a.x1, a.y2 - a.y1
        ox, oy = a.x1 - b.x, a.y1 - b.y
        aa = dx * dx + dy * dy
        bb = 2 * (ox * dx + oy * dy)
        cc = ox * ox + oy * oy - b.radius * b.radius
        disc = bb * bb - 4 * aa * cc
        if aa < EPS or disc < -EPS:
            return []
        root = math.sqrt(max(0.0, disc))
        return [(a.x1 + t * dx, a.y1 + t * dy)
                for t in ((-bb - root) / (2 * aa), (-bb + root) / (2 * aa))
                if -EPS <= t <= 1 + EPS]
    ax, ay = a.x2 - a.x1, a.y2 - a.y1
    bx, by = b.x2 - b.x1, b.y2 - b.y1
    det = ax * by - ay * bx
    if abs(det) < EPS:
        return []
    dx, dy = b.x1 - a.x1, b.y1 - a.y1
    t, u = (dx * by - dy * bx) / det, (dx * ay - dy * ax) / det
    return [(a.x1 + t * ax, a.y1 + t * ay)] if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS else []


def _boundaries(actors, radius, origin, limit):
    """Exact circle/AABB Minkowski boundaries, not enlarged square corners."""
    ox, oy = origin
    boundaries = []
    for actor in actors:
        hx, hy = actor.head_center
        boundaries.append(Circle(hx, hy, config.HEAD_RADIUS + radius))
        left, top, right, bottom = players.body_rect(actor)
        boundaries.extend((
            Segment(left - radius, top, left - radius, bottom),
            Segment(right + radius, top, right + radius, bottom),
            Segment(left, top - radius, right, top - radius),
            Segment(left, bottom + radius, right, bottom + radius),
        ))
        boundaries.extend(Circle(x, y, radius) for x in (left, right) for y in (top, bottom))
    span = limit + 1.0
    boundaries.extend((
        Segment(ox - span, config.GROUND_Y - radius, ox + span, config.GROUND_Y - radius),
        Segment(ox - span, config.PITCH_TOP + radius, ox + span, config.PITCH_TOP + radius),
        Segment(config.PITCH_LEFT + radius, config.PITCH_TOP + radius,
                config.PITCH_LEFT + radius, config.CROSSBAR_Y),
        Segment(config.PITCH_RIGHT - radius, config.PITCH_TOP + radius,
                config.PITCH_RIGHT - radius, config.CROSSBAR_Y),
        Circle(config.PITCH_LEFT, config.CROSSBAR_Y, radius),
        Circle(config.PITCH_RIGHT, config.CROSSBAR_Y, radius),
    ))
    if ox - span < config.PITCH_LEFT:
        boundaries.append(Segment(ox - span, config.CROSSBAR_Y + radius,
                                  config.PITCH_LEFT, config.CROSSBAR_Y + radius))
    if ox + span > config.PITCH_RIGHT:
        boundaries.append(Segment(config.PITCH_RIGHT, config.CROSSBAR_Y + radius,
                                  ox + span, config.CROSSBAR_Y + radius))
    nearby = []
    for boundary in boundaries:
        if isinstance(boundary, Circle):
            distance = abs(math.hypot(boundary.x - ox, boundary.y - oy) - boundary.radius)
        else:
            x, y = _project_segment(ox, oy, boundary)
            distance = math.hypot(x - ox, y - oy)
        if distance <= limit + CONTACT_EPS:
            nearby.append(boundary)
    # Intersections with the reachable-motion disk matter in tight squeezes.
    nearby.append(Circle(ox, oy, limit))
    return nearby


def _project_position(ball, actors, target, origin, limit, hints=()):
    def valid(point):
        return math.dist(point, origin) <= limit + EPS and is_clear(ball, actors, point)

    if valid(target):
        return target
    # If a nearest projection out of ONE violated solid already satisfies
    # every other constraint, it is also the global nearest legal point.
    # This is the usual free-floor/single-body case; intersections are only
    # needed for actual coupled contacts.
    x, y = target
    simple = []
    if y < config.PITCH_TOP + ball.radius or y > config.GROUND_Y - ball.radius:
        simple.append((x, physics.clamp(y, config.PITCH_TOP + ball.radius, config.GROUND_Y - ball.radius)))
    for side in ("left", "right"):
        gap, nx, ny = physics.post_contact(x, y, ball.radius, side)
        if gap < 0.0:
            simple.append((x - gap * nx, y - gap * ny))
    for actor in actors:
        hx, hy = actor.head_center
        dx, dy = x - hx, y - hy
        distance = math.hypot(dx, dy)
        radius = config.HEAD_RADIUS + ball.radius
        if EPS < distance < radius:
            simple.append((hx + dx * radius / distance, hy + dy * radius / distance))
        left, top, right, bottom = players.body_rect(actor)
        px, py = physics.clamp(x, left, right), physics.clamp(y, top, bottom)
        dx, dy = x - px, y - py
        distance = math.hypot(dx, dy)
        if EPS < distance < ball.radius:
            simple.append((px + dx * ball.radius / distance, py + dy * ball.radius / distance))
    for point in simple:
        if valid(point):
            return point
    boundaries = _boundaries(actors, ball.radius, origin, limit)
    # Parallel contacts can leave a zero-width sliding manifold (e.g. floor
    # and a supported foot). Keep tangential motion on the previous legal
    # contact level even when their analytic boundaries differ by roundoff.
    # Keeping only `origin` in that case parks a ball with nonzero velocity.
    candidates = [origin, (target[0], origin[1]), (origin[0], target[1]), *hints]
    for boundary in boundaries:
        if isinstance(boundary, Circle):
            dx, dy = x - boundary.x, y - boundary.y
            distance = math.hypot(dx, dy)
            if distance > EPS:
                candidates.append((boundary.x + dx * boundary.radius / distance,
                                   boundary.y + dy * boundary.radius / distance))
            else:
                candidates.extend((boundary.x + nx * boundary.radius, boundary.y + ny * boundary.radius)
                                  for nx, ny in ((0, -1), (1, 0), (-1, 0), (0, 1)))
        else:
            candidates.append(_project_segment(x, y, boundary))
            candidates.extend(((boundary.x1, boundary.y1), (boundary.x2, boundary.y2)))
    for a, b in combinations(boundaries, 2):
        candidates.extend(_intersections(a, b))
    legal = (p for p in candidates if valid(p))
    return min(legal, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2, default=None)


def contacts(ball: Ball, actors: Sequence[Player]):
    """All simultaneous touching surfaces, with their actual world velocities."""
    result = []
    x, y, r = ball.x, ball.y, ball.radius
    if config.GROUND_Y - y - r <= CONTACT_EPS:
        result.append(Contact("ground", 0, -1, config.BALL_RESTITUTION_GROUND))
    if y - r - config.PITCH_TOP <= CONTACT_EPS:
        result.append(Contact("ceiling", 0, 1, config.BALL_RESTITUTION_WALL))
    for side in ("left", "right"):
        gap, nx, ny = physics.post_contact(x, y, r, side)
        if gap <= CONTACT_EPS:
            result.append(Contact(f"{side}_wall", nx, ny, config.BALL_RESTITUTION_WALL))
    for actor in actors:
        hx, hy = actor.head_center
        dx, dy = x - hx, y - hy
        distance = math.hypot(dx, dy)
        if distance - config.HEAD_RADIUS - r <= CONTACT_EPS and distance > EPS:
            result.append(Contact(f"head:{actor.sprite_key}", dx / distance, dy / distance,
                                  config.BALL_RESTITUTION_HEAD, actor, config.HEADER_LIFT))
        left, top, right, bottom = players.body_rect(actor)
        dx, dy = x - physics.clamp(x, left, right), y - physics.clamp(y, top, bottom)
        distance = math.hypot(dx, dy)
        if distance - r <= CONTACT_EPS and distance > EPS:
            result.append(Contact(f"body:{actor.sprite_key}", dx / distance, dy / distance,
                                  config.BALL_RESTITUTION_BODY, actor))
    return result


def _project_velocity(vx, vy, touching):
    """Closest velocity satisfying every support half-plane and speed cap."""
    constraints = [(c.nx, c.ny, c.nx * c.velocity[0] + c.ny * c.velocity[1]) for c in touching]
    cap = config.BALL_MAX_SPEED

    def valid(v):
        return math.hypot(*v) <= cap + EPS and all(nx * v[0] + ny * v[1] >= bound - EPS
                                                  for nx, ny, bound in constraints)
    if valid((vx, vy)):
        return vx, vy
    candidates = [(0.0, 0.0)]
    for nx, ny, bound in constraints:
        offset = bound - nx * vx - ny * vy
        candidates.append((vx + offset * nx, vy + offset * ny))
        tangent = math.sqrt(max(0.0, cap * cap - bound * bound))
        candidates.extend(((nx * bound - ny * tangent, ny * bound + nx * tangent),
                           (nx * bound + ny * tangent, ny * bound - nx * tangent)))
    for (ax, ay, ab), (bx, by, bb) in combinations(constraints, 2):
        det = ax * by - ay * bx
        if abs(det) > EPS:
            candidates.append(((ab * by - ay * bb) / det, (ax * bb - ab * bx) / det))
    return min((v for v in candidates if valid(v)),
               key=lambda v: (v[0] - vx) ** 2 + (v[1] - vy) ** 2, default=None)


def _resolve_velocity(ball, actors, dt, on_impact):
    touching = contacts(ball, actors)
    ball.impact_contacts.intersection_update(c.name for c in touching)
    events = []
    for contact in touching:
        incoming = physics.reflect_velocity(
            ball, contact.nx, contact.ny, contact.restitution, contact.velocity,
            contact.lift, settle=contact.name == "ground" or contact.name.startswith("head:"),
            settle_speed=config.BALL_GROUND_SETTLE_SPEED if contact.name == "ground" else None,
        )
        if physics._impact(ball, contact.name, incoming):
            events.append(contact.name)
    velocity = _project_velocity(ball.vx, ball.vy, touching)
    if velocity is None:
        # Closing supports cannot demand two incompatible ball velocities.
        # They have reached their blocked position and must stop, not keep
        # driving through the ball on the next solve.
        for contact in touching:
            if contact.actor is not None:
                contact.actor.vx = 0.0
                contact.actor.vy = 0.0
        velocity = _project_velocity(ball.vx, ball.vy, touching)
    if velocity is None:
        raise RuntimeError("world contact velocity has no feasible stationary solution")
    ball.vx, ball.vy = velocity
    if any(c.name == "ground" for c in touching):
        friction = config.BALL_GROUND_FRICTION_PER_SEC * dt
        ball.vx = math.copysign(max(0.0, abs(ball.vx) - friction), ball.vx)
        # Friction must not pull a rolling ball back into its moving support.
        velocity = _project_velocity(ball.vx, ball.vy, touching)
        if velocity is not None:
            ball.vx, ball.vy = velocity
    physics._cap_speed(ball)
    if on_impact is not None:
        for name in events:
            on_impact(name)


def _separate_actors(actors, old):
    """Preserve the approach axis of player contacts.

    A landing is a vertical contact, not permission to instantaneously shove
    the grounded player sideways (and through a nearby ball). Grounded
    approaches retain the existing symmetric horizontal separation.
    """
    if len(actors) != 2:
        return
    a, b = actors
    if abs(a.x - b.x) >= 2 * config.PLAYER_HALF_WIDTH or abs(a.y - b.y) >= config.PLAYER_HEIGHT:
        return
    if abs(old[0][1] - old[1][1]) >= config.PLAYER_HEIGHT - EPS:
        upper_index = 0 if old[0][1] < old[1][1] else 1
        lower_index = 1 - upper_index
        old_gap = old[lower_index][1] - old[upper_index][1]
        new_gap = actors[lower_index].y - actors[upper_index].y
        closing = old_gap - new_gap
        fraction = physics.clamp((old_gap - config.PLAYER_HEIGHT) / closing, 0.0, 1.0) if closing > EPS else 0.0
        for i, actor in enumerate(actors):
            actor.y = old[i][1] + (actor.y - old[i][1]) * fraction
        actors[upper_index].y = min(actors[upper_index].y,
                                    actors[lower_index].y - config.PLAYER_HEIGHT - EPS)
    else:
        players.separate_players(a, b)


def _substep(ball, actors, moves, dt, on_impact):
    origin = ball.pos
    old = [(p.x, p.y) for p in actors]
    for player, move in zip(actors, moves):
        players.apply_move(player, move, dt)
        supported = (
            player.on_ground and player.vy == 0.0 and player.y < config.GROUND_Y
            and ball.y + ball.radius >= config.GROUND_Y - CONTACT_EPS
            and abs(player.y - (ball.y - ball.radius)) <= CONTACT_EPS
            and abs(player.x - ball.x) <= config.PLAYER_HALF_WIDTH
        )
        # A supported foot need not attempt to penetrate its support again
        # every substep. Once it walks off (or jumps), gravity resumes.
        if not supported:
            if player.y < config.GROUND_Y:
                player.on_ground = False
            players.step_player_physics(player, dt, tick_timers=False)
    integrated = [(p.x, p.y) for p in actors]
    _separate_actors(actors, old)
    proposed = [(p.x, p.y) for p in actors]
    for i, (p, (ox, _)) in enumerate(zip(actors, old)):
        p.vx = (p.x - ox) / dt
        if p.y != integrated[i][1]:
            p.vy = 0.0
            p.on_ground = p.y >= config.GROUND_Y - CONTACT_EPS
    physics.integrate_ball(ball, dt)
    target = ball.pos
    # Limit depenetration by the motion that actually caused contact, not
    # merely by a hypothetical 900px/s ball. Otherwise a resting floor ball
    # could hop into a disconnected pocket above the torso when squeezed.
    travels = [math.dist(a, b) for a, b in zip(old, proposed)]
    ball_travel = math.dist(origin, target)
    local = [i for i in range(len(actors))
             if min(_pose_gap(origin, old[i], ball.radius), _pose_gap(origin, proposed[i], ball.radius))
             <= ball_travel + 2 * travels[i] + CONTACT_EPS]
    actor_travel = max((travels[i] for i in local), default=0.0)
    limit = min(config.BALL_MAX_SPEED * dt, ball_travel + actor_travel) + CONTACT_EPS

    def project():
        # A contact island translating together must remain translatable even
        # when a three-surface intersection differs by numerical tolerance.
        hints = [(origin[0] + actors[i].x - old[i][0], origin[1] + actors[i].y - old[i][1]) for i in local]
        return _project_position(ball, actors, target, origin, limit, hints)

    point = project()
    if point is None:
        involved = [
            i for i, p in enumerate(actors)
            if old[i] != proposed[i] and (
                math.dist(origin, p.head_center) <= config.HEAD_RADIUS + ball.radius + 2 * limit
                or _body_gap(*origin, p, ball.radius) <= 2 * limit
            )
        ]
        if len(actors) == 2 and involved and (
            abs(old[0][0] - old[1][0]) <= 2 * config.PLAYER_HALF_WIDTH + 2 * actor_travel + CONTACT_EPS
            and abs(old[0][1] - old[1][1]) <= config.PLAYER_HEIGHT + 2 * actor_travel + CONTACT_EPS
        ):
            # A neighbour can push a blocked actor even without touching the
            # ball itself. Constrain the connected island, not just the
            # collider nearest the ball. Distant unrelated players stay free.
            involved = [0, 1]

        motion_masks = {}
        for i in involved:
            old_gap = _pose_gap(origin, old[i], ball.radius)
            motion_masks[i] = (
                _pose_gap(origin, (proposed[i][0], old[i][1]), ball.radius) < old_gap - EPS,
                _pose_gap(origin, (old[i][0], proposed[i][1]), ball.radius) < old_gap - EPS,
            )

        def try_motion(fraction_x, fraction_y):
            # Restore every proposal on each probe: player separation must
            # not accumulate motion on an uninvolved neighbour during search.
            for i, actor in enumerate(actors):
                mx, my = motion_masks.get(i, (False, False))
                sx, sy = fraction_x if mx else 1.0, fraction_y if my else 1.0
                actor.x = old[i][0] + (proposed[i][0] - old[i][0]) * sx
                actor.y = old[i][1] + (proposed[i][1] - old[i][1]) * sy
            _separate_actors(actors, old)
            return project()

        point = try_motion(0.0, 0.0)
        if point is None:
            # A connected neighbour may transmit pressure indirectly. Only
            # then restrict the whole island, including its separating axes.
            motion_masks = {i: (proposed[i][0] != old[i][0], proposed[i][1] != old[i][1]) for i in involved}
            point = try_motion(0.0, 0.0)
        if point is None:
            raise RuntimeError("world lost the previous legal contact configuration")
        # Preserve free tangential player motion too. A blocked downward
        # step off a ball must not cancel a perfectly legal sideways step.
        families = []
        if try_motion(1.0, 0.0) is not None:
            families.append(lambda f: (1.0, f))
        if try_motion(0.0, 1.0) is not None:
            families.append(lambda f: (f, 1.0))
        if not families:
            families.append(lambda f: (f, f))
        solutions = []
        for fractions in families:
            low, high = 0.0, 1.0
            for _ in range(22):
                middle = (low + high) * 0.5
                if try_motion(*fractions(middle)) is None:
                    high = middle
                else:
                    low = middle
            sx, sy = fractions(low)
            error = sum(((proposed[i][0] - old[i][0]) * (1 - sx) * motion_masks[i][0]) ** 2
                        + ((proposed[i][1] - old[i][1]) * (1 - sy) * motion_masks[i][1]) ** 2 for i in involved)
            solutions.append((error, sx, sy))
        _, sx, sy = min(solutions)
        point = try_motion(sx, sy)
        for i, player in enumerate(actors):
            player.vx = (player.x - old[i][0]) / dt
            if i not in involved and player.y != proposed[i][1]:
                player.vy = 0.0
                player.on_ground = player.y >= config.GROUND_Y - CONTACT_EPS
        for i in involved:
            player = actors[i]
            if sx < 1.0 and motion_masks[i][0]:
                player.vx = 0.0
            if sy < 1.0 and motion_masks[i][1]:
                # Only a downward foot support can arm another ground jump.
                # A blocked side/head motion is not a landing.
                player.on_ground = (
                    player.y >= config.GROUND_Y - CONTACT_EPS
                    or (proposed[i][1] > old[i][1]
                        and point[1] >= player.y - CONTACT_EPS
                        and point[1] + ball.radius >= config.GROUND_Y - CONTACT_EPS)
                )
                player.vy = 0.0
    ball.x, ball.y = point
    _resolve_velocity(ball, actors, dt, on_impact)
    # Position is already clear of the solid posts. Horizontal goal scoring
    # remains centre-crossing, not "wait until the entire ball is past".
    if ball.x <= config.PITCH_LEFT:
        return "left_goal"
    if ball.x >= config.PITCH_RIGHT:
        return "right_goal"
    return None


def step_world(ball: Ball, actors: Sequence[Player], dt: float, moves=None,
               on_impact: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """Advance the scene together. No action edges or charges are consumed here.

    A local contact projection has a strict displacement bound. Adaptive
    substeps include ball acceleration and moving/jumping collider speeds,
    and are recomputed after impulses rather than trusting initial speed.
    """
    if dt <= 0.0:
        return None
    moves = tuple(moves) if moves is not None else tuple(p.facing if p.moving else 0 for p in actors)
    if not is_clear(ball, actors):
        # Only for externally inserted/invalid starting positions. Normal live
        # steps always preserve legality, so this cannot be a squeeze escape.
        point = _project_position(ball, actors, ball.pos, ball.pos, config.PLAYER_HEIGHT + 2 * ball.radius)
        if point is None:
            raise ValueError("no local legal ball placement in initial scene")
        ball.x, ball.y = point
        _resolve_velocity(ball, actors, 0.0, on_impact)
    remaining = dt
    while remaining > 1e-10:
        actor_speed = max((math.hypot(move * config.PLAYER_SPEED, p.vy)
                           for p, move in zip(actors, moves)), default=0.0)
        speed = ball.speed() + actor_speed
        acceleration = config.BALL_GRAVITY + config.GRAVITY
        spatial_step = 2 * config.BALL_MAX_STEP_PX / (
            speed + math.sqrt(speed * speed + 2 * acceleration * config.BALL_MAX_STEP_PX)
        )
        h = min(remaining, MAX_STEP_SECONDS, spatial_step)
        event = _substep(ball, actors, moves, h, on_impact)
        if event is not None:
            return event
        remaining -= h
    return None
