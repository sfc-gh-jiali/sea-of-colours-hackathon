"""Seat order is not a factor (RULEBOOK §3.10, §3.13) — the whole board.

    "Moves resolve in parallel ... the engine's seat-by-seat application
    order is an implementation detail with no rules standing."

This is the differential harness for that claim, and the safety net for
finishing issue #56. Every scenario is described purely in terms of
ROLES (A, B, C, D), then run once for each way of handing those roles to
seats — and the outcome is recorded **keyed by role**. If two runs
disagree, the engine let the seat index decide, which the rule forbids.

v1.48 — the harness was two-seat only, which left the multi-seat paths
unexamined: the swap pre-pass walks every seat *pair* precisely because
four seats can produce two independent collisions in one hour, and the
grid is bipartite so a movement cycle needs FOUR units and cannot be
built at all with two. Scenarios now declare how many seats sit at the
table and how many roles they use, and the sweep runs every assignment
of roles to seats (``P(seats, roles)``).

Scenarios still known to be order-dependent are marked ``xfail(strict)``
rather than deleted, so they are executable documentation of exactly what
is left. When a later change fixes one, this file fails with an XPASS and
tells whoever did it to drop the marker — which is the point: the gaps
announce themselves instead of being rediscovered.

Adding a scenario is deliberately cheap. Write a setup function taking
``(sess, A, B, ...)`` — never ``p1`` / ``p2``, that would bake in the
very thing under test — and add it to ``SCENARIOS``. Do not assert a
specific outcome here; that belongs in a rule-specific test like
test_egress_is_not_seat_ordered.py. The only question this file asks is
"does the answer depend on the seat?".
"""
from __future__ import annotations

import itertools
from typing import Callable, NamedTuple, Optional, Tuple

import pytest

from sea_of_colours.game.session import Entity, GameSession

#: Roles are positional: the Nth argument of a setup function is ROLES[N].
ROLES = ("A", "B", "C", "D")

ALL_SEATS = ("p1", "p2", "p3", "p4")


def _h(seat: str) -> str:
    return f"harvester_{seat}"


def _probe_for(sess: GameSession, seat: str, x: int, y: int, tag: str = "") -> None:
    pid = f"probe_{seat}_{tag or f'{x}_{y}'}"
    sess.entities[pid] = Entity(pid, "probe", seat, x, y)


# ── scenarios ────────────────────────────────────────────────────────
# Each takes (sess, A, B, ...) where the arguments are seat names. Keep
# the board symmetric in those arguments, so the setup itself cannot be
# what makes one seating differ from another.

def _swap(sess, A, B):
    """§3.17.4 — they cross on one edge. Both wreck at origin."""
    sess.entities[_h(A)].x, sess.entities[_h(A)].y = 5, 7
    sess.entities[_h(B)].x, sess.entities[_h(B)].y = 6, 7
    sess.stash_policy(A, [{"a": "step", "unit": _h(A), "to": [6, 7]}])
    sess.stash_policy(B, [{"a": "step", "unit": _h(B), "to": [5, 7]}])


def _follow(sess, A, B):
    """A convoy: A takes B's cell while B moves further on."""
    sess.entities[_h(A)].x, sess.entities[_h(A)].y = 5, 7
    sess.entities[_h(B)].x, sess.entities[_h(B)].y = 6, 7
    sess.stash_policy(A, [{"a": "step", "unit": _h(A), "to": [6, 7]}])
    sess.stash_policy(B, [{"a": "step", "unit": _h(B), "to": [7, 7]}])


def _drop_onto_pickup(sess, A, B):
    """Lift-and-land. Fixed in v1.48 — §3.17.5."""
    hb = sess.entities[_h(B)]
    hb.x, hb.y = 6, 7
    hb.cargo_squares = [{"square_id": "sq-b", "value": 500}]
    _probe_for(sess, A, 6, 7)
    sess.stash_policy(A, [{"a": "drop", "unit": _h(A), "at": [6, 7]}])
    sess.stash_policy(B, [{"a": "pickup", "unit": _h(B)}])


def _step_onto_pickup(sess, A, B):
    """Lift-and-land by step. Fixed in v1.48 — §3.17.5."""
    sess.entities[_h(A)].x, sess.entities[_h(A)].y = 5, 7
    hb = sess.entities[_h(B)]
    hb.x, hb.y = 6, 7
    hb.cargo_squares = [{"square_id": "sq-b", "value": 500}]
    sess.stash_policy(A, [{"a": "step", "unit": _h(A), "to": [6, 7]}])
    sess.stash_policy(B, [{"a": "pickup", "unit": _h(B)}])


def _drop_onto_stepaway(sess, A, B):
    sess.entities[_h(B)].x, sess.entities[_h(B)].y = 6, 7
    _probe_for(sess, A, 6, 7)
    sess.stash_policy(A, [{"a": "drop", "unit": _h(A), "at": [6, 7]}])
    sess.stash_policy(B, [{"a": "step", "unit": _h(B), "to": [7, 7]}])


def _simultaneous_drop(sess, A, B):
    """§3.17.2 — contested destination, none land."""
    _probe_for(sess, A, 6, 7, "a")
    _probe_for(sess, B, 6, 7, "b")
    sess.stash_policy(A, [{"a": "drop", "unit": _h(A), "at": [6, 7]}])
    sess.stash_policy(B, [{"a": "drop", "unit": _h(B), "at": [6, 7]}])


def _converge_step(sess, A, B):
    """Two step into one EMPTY cell — §3.17's headline, no numbered pattern."""
    sess.entities[_h(A)].x, sess.entities[_h(A)].y = 5, 7
    sess.entities[_h(B)].x, sess.entities[_h(B)].y = 7, 7
    sess.stash_policy(A, [{"a": "step", "unit": _h(A), "to": [6, 7]}])
    sess.stash_policy(B, [{"a": "step", "unit": _h(B), "to": [6, 7]}])


def _drop_onto_static(sess, A, B):
    """§3.17.1."""
    sess.entities[_h(B)].x, sess.entities[_h(B)].y = 6, 7
    _probe_for(sess, A, 6, 7)
    sess.stash_policy(A, [{"a": "drop", "unit": _h(A), "at": [6, 7]}])
    sess.stash_policy(B, [{"a": "wait"}])


def _step_into_static(sess, A, B):
    """§3.17.3."""
    sess.entities[_h(A)].x, sess.entities[_h(A)].y = 5, 7
    sess.entities[_h(B)].x, sess.entities[_h(B)].y = 6, 7
    sess.stash_policy(A, [{"a": "step", "unit": _h(A), "to": [6, 7]}])
    sess.stash_policy(B, [{"a": "wait"}])


def _probe_same_cell(sess, A, B):
    """§3.16 — the precedent. Issue #18, fixed for probes in v1.19."""
    sess.stash_policy(A, [{"a": "probe", "at": [9, 9]}])
    sess.stash_policy(B, [{"a": "probe", "at": [9, 9]}])


def _drop_crushes_probe(sess, A, B):
    """A lands where B launches a probe the same hour (§3.11.1)."""
    _probe_for(sess, A, 6, 7, "vis")
    sess.stash_policy(A, [{"a": "drop", "unit": _h(A), "at": [6, 7]}])
    sess.stash_policy(B, [{"a": "probe", "at": [6, 7]}])


# ── scenarios that need more than two seats ──────────────────────────

def _nobody_moves(sess, A, B, C, D):
    """Control. Four seats, nothing happens.

    If THIS is order-dependent then the seats are not symmetric at
    setup and every other multi-seat verdict below is noise, so it is
    worth the two seconds it costs.
    """
    for seat in (A, B, C, D):
        sess.stash_policy(seat, [{"a": "wait"}])


def _rotation(sess, A, B, C, D):
    """Four harvesters rotate around a 2x2 ring.

    Nobody's destination is free at hour start, yet every destination is
    being vacated by someone who is themselves leaving. The ruling is
    that this is allowed. It needs four roles, not three: the grid graph
    is bipartite, so the shortest movement cycle is length four.
    """
    ring = {A: (5, 7), B: (6, 7), C: (6, 8), D: (5, 8)}
    goes_to = {A: (6, 7), B: (6, 8), C: (5, 8), D: (5, 7)}
    for seat, (x, y) in ring.items():
        sess.entities[_h(seat)].x, sess.entities[_h(seat)].y = x, y
    for seat, dest in goes_to.items():
        sess.stash_policy(
            seat, [{"a": "step", "unit": _h(seat), "to": list(dest)}]
        )


def _two_independent_swaps(sess, A, B, C, D):
    """Two unrelated collisions in one hour, at opposite ends of the map.

    The pre-pass resolves contention a pair at a time and re-enters the
    hour; this is the scenario that asks whether the second pair is
    still handled once the first has been.
    """
    pairs = (((A, (5, 7)), (B, (6, 7))), ((C, (5, 11)), (D, (6, 11))))
    for (s1, c1), (s2, c2) in pairs:
        sess.entities[_h(s1)].x, sess.entities[_h(s1)].y = c1
        sess.entities[_h(s2)].x, sess.entities[_h(s2)].y = c2
        sess.stash_policy(s1, [{"a": "step", "unit": _h(s1), "to": list(c2)}])
        sess.stash_policy(s2, [{"a": "step", "unit": _h(s2), "to": list(c1)}])


def _three_way_converge(sess, A, B, C):
    """Three step into one empty cell. Contention beyond a pair."""
    starts = {A: (5, 7), B: (7, 7), C: (6, 6)}
    for seat, (x, y) in starts.items():
        sess.entities[_h(seat)].x, sess.entities[_h(seat)].y = x, y
        sess.stash_policy(seat, [{"a": "step", "unit": _h(seat), "to": [6, 7]}])


def _two_converge_onto_an_occupant(sess, A, B, C):
    """Two step onto a cell a healthy third is standing still on.

    The occupant is rammed by whoever arrives — but a wreck does not
    block (§3.17.1), so once the first stepper had wrecked it the second
    used to walk on unharmed. Seat index picked which.
    """
    sess.entities[_h(A)].x, sess.entities[_h(A)].y = 5, 7
    sess.entities[_h(B)].x, sess.entities[_h(B)].y = 7, 7
    sess.entities[_h(C)].x, sess.entities[_h(C)].y = 6, 7
    sess.stash_policy(A, [{"a": "step", "unit": _h(A), "to": [6, 7]}])
    sess.stash_policy(B, [{"a": "step", "unit": _h(B), "to": [6, 7]}])
    sess.stash_policy(C, [{"a": "wait"}])


def _convoy_of_three(sess, A, B, C):
    """A chain: A follows B follows C, who steps into open space.

    The step-away gap compounds along a chain — whether A may advance
    depends on B, which depends on C.
    """
    line = {A: (4, 7), B: (5, 7), C: (6, 7)}
    for seat, (x, y) in line.items():
        sess.entities[_h(seat)].x, sess.entities[_h(seat)].y = x, y
    for seat, dest in {A: (5, 7), B: (6, 7), C: (7, 7)}.items():
        sess.stash_policy(
            seat, [{"a": "step", "unit": _h(seat), "to": list(dest)}]
        )


class Scenario(NamedTuple):
    id: str
    setup: Callable[..., None]
    roles: int
    #: How many seats sit at the table. More seats than roles means the
    #: spare seats idle — which is not filler: it varies WHICH seat
    #: index each role holds, and that is the variable under test.
    seats: int
    #: Why the engine is still order-dependent here; None means it must
    #: be deterministic today.
    gap: Optional[str]



SCENARIOS: Tuple[Scenario, ...] = (
    Scenario("control-nobody-moves", _nobody_moves, 4, 4, None),
    Scenario("swap", _swap, 2, 4, None),
    Scenario("simultaneous-drop", _simultaneous_drop, 2, 4, None),
    Scenario("drop-onto-static", _drop_onto_static, 2, 4, None),
    Scenario("step-into-static", _step_into_static, 2, 4, None),
    Scenario("probe-same-cell", _probe_same_cell, 2, 4, None),
    Scenario("drop-onto-pickup", _drop_onto_pickup, 2, 4, None),   # fixed v1.48
    Scenario("step-onto-pickup", _step_onto_pickup, 2, 4, None),   # fixed v1.48
    # Found by this file when it grew past two seats; fixed in v1.48.
    Scenario("two-independent-swaps", _two_independent_swaps, 4, 4, None),
    # Step-aways and the convoy behind them — fixed v1.49 (§3.17.7).
    Scenario("follow", _follow, 2, 4, None),
    Scenario("drop-onto-stepaway", _drop_onto_stepaway, 2, 4, None),
    Scenario("convoy-of-three", _convoy_of_three, 3, 4, None),
    Scenario("converge-step", _converge_step, 2, 4, None),        # fixed v1.48
    Scenario("three-way-converge", _three_way_converge, 3, 4, None),  # v1.48
    Scenario(
        "two-converge-onto-an-occupant", _two_converge_onto_an_occupant,
        3, 4, None,
    ),  # fixed v1.48
    Scenario("rotation", _rotation, 4, 4, None),  # fixed v1.49
    # The last of the six — fixed v1.49 by the post-hour sweep (§3.11.1).
    Scenario("drop-crushes-same-hour-probe", _drop_crushes_probe, 2, 4, None),
)


def _resolve(scn: Scenario, assignment: Tuple[str, ...]) -> GameSession:
    """Build the scenario with roles on ``assignment`` and run the night."""
    seats = ALL_SEATS[: scn.seats]
    sess = GameSession.new(20, 14, seed=901, players=list(seats))
    scn.setup(sess, *assignment)
    # Seats the scenario did not speak for still have to file something,
    # or the night never becomes ready to resolve. Readiness is "the
    # value is not None" — the dict is pre-seeded with every seat, so
    # testing for the KEY silently leaves idle seats unlocked and the
    # night unresolved, which reads as a serenely order-independent
    # board on which nothing whatsoever happened.
    for seat in seats:
        if sess.pending_policies.get(seat) is None:
            sess.stash_policy(seat, [{"a": "wait"}])
    assert sess.both_ready(), "scenario left a seat unlocked"

    # Hold the entity objects: Aurora drops destroyed harvesters out of
    # sess.entities, so looking them up afterwards returns None and hides
    # the very difference being audited.
    sess._audit_refs = {  # type: ignore[attr-defined]
        ROLES[i]: sess.entities[_h(s)] for i, s in enumerate(assignment)
    }
    sess._audit_seats = {  # type: ignore[attr-defined]
        ROLES[i]: s for i, s in enumerate(assignment)
    }
    assert sess.maybe_resolve_if_ready(), "the night did not resolve"
    return sess


def _outcome(scn: Scenario, assignment: Tuple[str, ...]) -> dict:
    """Resolve one night and describe it BY ROLE, never by seat."""
    sess = _resolve(scn, assignment)
    refs = sess._audit_refs  # type: ignore[attr-defined]
    by_role = sess._audit_seats  # type: ignore[attr-defined]

    out: dict = {"scars": tuple(sorted(sess.collision_marks))}
    for role, ent in refs.items():
        seat = by_role[role]
        out[f"{role}.pos"] = (ent.x, ent.y)
        out[f"{role}.damaged"] = bool(getattr(ent, "damaged", False))
        out[f"{role}.cargo"] = len(ent.cargo_squares or [])
        out[f"{role}.hoard"] = sum(
            int(s.get("value", 0))
            for s in (sess.hoard_squares.get(seat) or [])
        )
        out[f"{role}.probes"] = tuple(sorted(
            (e.x, e.y) for e in sess.entities.values()
            if e.entity_type == "probe" and e.owner == seat and e.x is not None
        ))
        # WHEN a seat acted is as much an outcome as what it did: the
        # night is 22 hours and a seat shunted an hour later has that
        # much less of it. This is the axis that hid the second-pair
        # bug — both pairs smashed either way, so the board looked
        # identical until you asked what o'clock it was.
        out[f"{role}.hours"] = tuple(sorted({
            f.get("hour") for f in _slot_frames(sess) if seat in _frame_seats(f)
        }))
    return out


@pytest.mark.parametrize(
    "scn",
    [
        pytest.param(
            s,
            id=s.id,
            marks=(pytest.mark.xfail(strict=True, reason=s.gap) if s.gap else ()),
        )
        for s in SCENARIOS
    ],
)
def test_the_outcome_does_not_depend_on_which_seat_holds_which_role(
    scn: Scenario,
) -> None:
    seatings = list(itertools.permutations(ALL_SEATS[: scn.seats], scn.roles))
    reference = _outcome(scn, seatings[0])

    for assignment in seatings[1:]:
        other = _outcome(scn, assignment)
        differing = {
            key: (reference[key], other[key])
            for key in reference
            if reference[key] != other[key]
        }
        assert not differing, (
            "seat order changed the outcome, which §3.10/§3.13 forbid.\n"
            f"  roles {ROLES[: scn.roles]} on {seatings[0]} (reference)\n"
            f"  vs    {ROLES[: scn.roles]} on {assignment}\n"
            f"  differences (reference vs other): {differing}"
        )


#: Frames that are the night's furniture rather than a seat's action.
_NON_SLOT_TAGS = {"open", "dawn"}


def _frame_seats(frame: dict) -> set:
    """Which seats this frame speaks for.

    Usually the ``owner``. A collision resolved by a pre-pass is a
    JOINT frame, though — ``owner`` is None and the participants are
    named in ``collisions[].owners`` — so reading ``owner`` alone
    scores a head-on smash as nobody having done anything.
    """
    if frame.get("tag") in _NON_SLOT_TAGS:
        return set()
    seats = {frame["owner"]} if frame.get("owner") else set()
    for col in frame.get("collisions") or []:
        seats |= set(col.get("owners") or [])
    return seats


def _slot_frames(sess: GameSession) -> list:
    return [f for f in (sess.last_night_replay or []) if _frame_seats(f)]


@pytest.mark.parametrize("scn", [pytest.param(s, id=s.id) for s in SCENARIOS])
def test_every_scenario_actually_exercises_its_roles(scn: Scenario) -> None:
    """A scenario that quietly goes inert would pass the audit above.

    It cost an afternoon once: idle seats were never locked, so the
    night never ran, and a board where nothing happened looked
    beautifully order-independent from every seat. Every role must be
    seen to act.
    """
    sess = _resolve(scn, tuple(ALL_SEATS[: scn.roles]))
    acted: set = set()
    for frame in _slot_frames(sess):
        acted |= _frame_seats(frame)
    expected = set(ALL_SEATS[: scn.roles])
    assert expected <= acted, (
        f"{scn.id} never exercised {sorted(expected - acted)} — the "
        "scenario is inert and its order-independence is vacuous"
    )


@pytest.mark.parametrize("scn", [pytest.param(s, id=s.id) for s in SCENARIOS])
def test_each_seat_consumes_exactly_one_slot_per_hour(scn: Scenario) -> None:
    """The invariant a reordered hour loop is most likely to break.

    ``_advance_until_valid`` promises that every queue item burns
    exactly one slot and pushes exactly one frame — success, waste,
    illegal or EMP-disabled alike. Nothing downstream re-checks it, and
    the night clock (``max(applied) + 1``) is derived from it, so a
    seat that slips an extra action does not fail loudly: it just gets
    a longer night than everyone else.
    """
    sess = _resolve(scn, tuple(ALL_SEATS[: scn.roles]))
    seen: dict = {}
    for frame in sess.last_night_replay or []:
        # Count only frames a seat OWNS. A collision rides along on the
        # acting seat's frame as an annotation (and a pre-pass smash is
        # one joint frame owned by nobody), so counting participants
        # instead would score one slot as two.
        if frame.get("tag") in _NON_SLOT_TAGS or not frame.get("owner"):
            continue
        key = (frame["owner"], frame.get("hour"))
        seen[key] = seen.get(key, 0) + 1
    doubled = {k: n for k, n in seen.items() if n > 1}
    assert not doubled, (
        f"{scn.id}: a seat acted more than once in one hour "
        f"(owner, hour) -> frames: {doubled}"
    )
