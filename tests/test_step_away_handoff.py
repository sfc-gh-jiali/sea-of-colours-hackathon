"""Taking a cell someone is stepping off (§3.17.7, v1.49).

v1.48 ruled that a harvester *lifting* off a cell is departing, not
arriving, so a rival may take the cell it vacates. It explicitly did not
extend that to a harvester **stepping** off, and gave a reason: a step
can be refused part-way through an hour, so "will that cell be free?"
looked unanswerable before the hour ran.

It is answerable. Reading ``try_step_unit`` from the top, the only
refusal that depends on another seat is a collision at the step's own
destination — every other one is static (wrong owner, not on the
surface, already damaged, not adjacent, out of bounds, hold full), and
the two dynamic gates above it, chaff and an EMP-smothered unit, are
settled before the round. Everything *after* the collision check moves
the harvester unconditionally: a snap-hot cell cripples it where it
lands, an EMP cloud denies it the harvest, and neither rewinds the step.

So the one remaining question is a fixpoint over the step graph rather
than a race, and that is what the engine now computes. The tests below
come in two halves, and the second half is the important one: a promise
that a cell will be free is only safe if it is never wrong. If the
fixpoint says a harvester leaves and it does not, a rival lands on top
of it and two healthy harvesters share a cell, which no rule allows.
"""
from __future__ import annotations

from typing import Tuple

import pytest

from sea_of_colours.game import weapons as W
from sea_of_colours.game.session import (
    HARVESTER_HOLD_CAPACITY,
    Entity,
    GameSession,
)

SEATS = ("p1", "p2", "p3", "p4")


def _h(seat: str) -> str:
    return f"harvester_{seat}"


def _new(n: int = 2) -> GameSession:
    return GameSession.new(20, 14, seed=901, players=list(SEATS[:n]))


def _at(sess: GameSession, seat: str, x: int, y: int) -> Entity:
    ent = sess.entities[_h(seat)]
    ent.x, ent.y = x, y
    return ent


def _step(sess: GameSession, seat: str, to: Tuple[int, int]) -> None:
    sess.stash_policy(seat, [{"a": "step", "unit": _h(seat), "to": list(to)}])


def _finish(sess: GameSession) -> None:
    for seat in sess.players:
        if sess.pending_policies.get(seat) is None:
            sess.stash_policy(seat, [{"a": "wait"}])
    assert sess.maybe_resolve_if_ready()


def _healthy_cells(sess: GameSession) -> list:
    return [
        (e.x, e.y) for e in sess.entities.values()
        if e.entity_type == "harvester"
        and e.x is not None
        and not bool(getattr(e, "damaged", False))
    ]


def _assert_no_cell_shared(sess: GameSession) -> None:
    """The invariant a wrong vacancy promise would break (§3.6.1)."""
    cells = _healthy_cells(sess)
    assert len(cells) == len(set(cells)), (
        f"two healthy harvesters ended up on one cell: {sorted(cells)}"
    )


# ── the hand-off works ───────────────────────────────────────────────

def test_a_harvester_may_take_the_cell_a_rival_steps_off() -> None:
    sess = _new()
    a = _at(sess, "p1", 5, 7)
    b = _at(sess, "p2", 6, 7)
    _step(sess, "p1", (6, 7))
    _step(sess, "p2", (7, 7))
    _finish(sess)

    assert (a.x, a.y) == (6, 7) and not a.damaged
    assert (b.x, b.y) == (7, 7) and not b.damaged
    assert not sess.collision_marks


def test_a_landing_may_take_the_cell_a_rival_steps_off() -> None:
    sess = _new()
    b = _at(sess, "p2", 6, 7)
    sess.entities["probe_p1"] = Entity("probe_p1", "probe", "p1", 6, 7)
    a = sess.entities[_h("p1")]
    sess.stash_policy("p1", [{"a": "drop", "unit": _h("p1"), "at": [6, 7]}])
    _step(sess, "p2", (7, 7))
    _finish(sess)

    assert (a.x, a.y) == (6, 7) and not a.damaged
    assert (b.x, b.y) == (7, 7) and not b.damaged


def test_a_convoy_of_three_advances_as_one() -> None:
    """The hand-off chains: whether A may move depends on B, then on C."""
    sess = _new(3)
    line = {"p1": (4, 7), "p2": (5, 7), "p3": (6, 7)}
    ents = {s: _at(sess, s, *xy) for s, xy in line.items()}
    for seat, dest in {"p1": (5, 7), "p2": (6, 7), "p3": (7, 7)}.items():
        _step(sess, seat, dest)
    _finish(sess)

    assert (ents["p1"].x, ents["p1"].y) == (5, 7)
    assert (ents["p2"].x, ents["p2"].y) == (6, 7)
    assert (ents["p3"].x, ents["p3"].y) == (7, 7)
    assert not any(e.damaged for e in ents.values())
    _assert_no_cell_shared(sess)


def test_a_ring_of_four_rotates() -> None:
    """A cycle has no move that is legal first, and is allowed anyway.

    Four, not three: the grid graph is bipartite, so its shortest cycle
    is length four. The two-unit case is a pass-through swap, which
    §3.17.4 collides instead — see the test below.
    """
    sess = _new(4)
    ring = {"p1": (5, 7), "p2": (6, 7), "p3": (6, 8), "p4": (5, 8)}
    goes = {"p1": (6, 7), "p2": (6, 8), "p3": (5, 8), "p4": (5, 7)}
    ents = {s: _at(sess, s, *xy) for s, xy in ring.items()}
    for seat, dest in goes.items():
        _step(sess, seat, dest)
    _finish(sess)

    for seat, dest in goes.items():
        assert (ents[seat].x, ents[seat].y) == dest, f"{seat} did not rotate"
        assert not ents[seat].damaged
    assert not sess.collision_marks
    _assert_no_cell_shared(sess)


def test_a_two_unit_ring_is_still_a_swap_and_still_collides() -> None:
    """§3.17.4 is not repealed by the cycle rule."""
    sess = _new()
    a = _at(sess, "p1", 5, 7)
    b = _at(sess, "p2", 6, 7)
    _step(sess, "p1", (6, 7))
    _step(sess, "p2", (5, 7))
    _finish(sess)

    assert a.damaged and b.damaged
    assert (a.x, a.y) == (5, 7) and (b.x, b.y) == (6, 7)


# ── the promise must never be wrong ──────────────────────────────────

def test_a_blocked_step_does_not_vacate_anything() -> None:
    """B cannot move, so A must not be told B's cell is free."""
    sess = _new(3)
    a = _at(sess, "p1", 5, 7)
    b = _at(sess, "p2", 6, 7)
    _at(sess, "p3", 7, 7)               # stationary wall
    _step(sess, "p1", (6, 7))
    _step(sess, "p2", (7, 7))           # refused: p3 is standing there
    sess.stash_policy("p3", [{"a": "wait"}])
    _finish(sess)

    assert (b.x, b.y) == (6, 7), "B never got out"
    assert (a.x, a.y) == (5, 7), "A must not have taken a cell B still holds"
    _assert_no_cell_shared(sess)


def test_the_refusal_propagates_back_down_a_convoy() -> None:
    """Block the front of the queue and nobody behind it moves either."""
    sess = _new(4)
    ents = {
        "p1": _at(sess, "p1", 4, 7),
        "p2": _at(sess, "p2", 5, 7),
        "p3": _at(sess, "p3", 6, 7),
        "p4": _at(sess, "p4", 7, 7),    # stationary wall
    }
    for seat, dest in {"p1": (5, 7), "p2": (6, 7), "p3": (7, 7)}.items():
        _step(sess, seat, dest)
    sess.stash_policy("p4", [{"a": "wait"}])
    _finish(sess)

    assert (ents["p1"].x, ents["p1"].y) == (4, 7)
    assert (ents["p2"].x, ents["p2"].y) == (5, 7)
    assert (ents["p3"].x, ents["p3"].y) == (6, 7)
    _assert_no_cell_shared(sess)


def test_an_emp_smothered_harvester_does_not_vacate() -> None:
    """A smothered unit takes no action, so its cell is not freed."""
    sess = _new(3)
    a = _at(sess, "p1", 9, 10)
    b = _at(sess, "p2", 10, 10)
    sess.entities[_h("p3")].x, sess.entities[_h("p3")].y = None, None
    sess.weapon_stock["p3"] = {"emp": 1}
    # Centre the blast on B but clear of A: from (12,10), B at (10,10) is
    # 2 away and inside, A at (9,10) is 3 away and clear.
    blast = (12, 10)
    assert abs(blast[0] - b.x) + abs(blast[1] - b.y) <= W.EMP_RADIUS
    assert abs(blast[0] - a.x) + abs(blast[1] - a.y) > W.EMP_RADIUS
    sess.stash_policy("p3", [
        {"a": "emp_launch", "at": [list(blast)]},
        {"a": "wait"},
    ])
    sess.stash_policy("p1", [
        {"a": "wait"},
        {"a": "step", "unit": _h("p1"), "to": [10, 10]},
    ])
    sess.stash_policy("p2", [
        {"a": "wait"},
        {"a": "step", "unit": _h("p2"), "to": [11, 10]},
    ])
    sess.maybe_resolve_if_ready()

    assert (b.x, b.y) == (10, 10), "the smothered harvester should not move"
    _assert_no_cell_shared(sess)


def test_a_full_hold_cannot_step_so_cannot_vacate() -> None:
    """One of the static refusals, and the least obvious of them."""
    sess = _new()
    a = _at(sess, "p1", 5, 7)
    b = _at(sess, "p2", 6, 7)
    b.cargo_squares = [
        {"square_id": f"sq-{i}", "value": 100}
        for i in range(HARVESTER_HOLD_CAPACITY)
    ]
    _step(sess, "p1", (6, 7))
    _step(sess, "p2", (7, 7))
    _finish(sess)

    assert (b.x, b.y) == (6, 7), "a full hold refuses the step (§3)"
    assert (a.x, a.y) == (5, 7), "so A must not have been let in"
    _assert_no_cell_shared(sess)


def test_a_chaffed_hour_vacates_nothing() -> None:
    """Chaff cancels the step, so the cell stays held."""
    sess = _new(3)
    a = _at(sess, "p1", 5, 7)
    b = _at(sess, "p2", 6, 7)
    sess.entities[_h("p3")].x, sess.entities[_h("p3")].y = None, None
    sess.weapon_stock["p3"] = {"chaff": 1}
    sess.stash_policy("p3", [{"a": "chaff_flare"}] + [{"a": "wait"}] * 3)
    _step(sess, "p1", (6, 7))
    _step(sess, "p2", (7, 7))
    _finish(sess)

    assert (b.x, b.y) == (6, 7), "the jammed step did not happen"
    assert (a.x, a.y) == (5, 7), "and the jammed follower did not move in"
    _assert_no_cell_shared(sess)


def test_two_rivals_cannot_both_take_one_vacated_cell() -> None:
    """The hand-off does not repeal §3.17.6 — the arrivals still collide."""
    sess = _new(3)
    a = _at(sess, "p1", 5, 7)
    b = _at(sess, "p2", 7, 7)
    leaver = _at(sess, "p3", 6, 7)
    _step(sess, "p1", (6, 7))
    _step(sess, "p2", (6, 7))
    _step(sess, "p3", (6, 6))
    _finish(sess)

    assert (leaver.x, leaver.y) == (6, 6), "the leaver got away"
    assert not leaver.damaged
    assert a.damaged and b.damaged, "the two arrivals collide over the cell"
    assert (a.x, a.y) == (5, 7) and (b.x, b.y) == (7, 7)
    _assert_no_cell_shared(sess)


def test_a_snap_hot_cell_cripples_the_stepper_but_it_still_vacates() -> None:
    """SNAP does not rewind a step — the origin is freed regardless."""
    sess = _new(3)
    a = _at(sess, "p1", 5, 7)
    b = _at(sess, "p2", 6, 7)
    sess.entities[_h("p3")].x, sess.entities[_h("p3")].y = None, None
    sess.weapon_stock["p3"] = {"snap": 1}
    sess.stash_policy("p3", [{"a": "snap_launch", "at": [7, 7]}, {"a": "wait"}])
    _step(sess, "p1", (6, 7))
    _step(sess, "p2", (7, 7))
    _finish(sess)

    assert (b.x, b.y) == (7, 7), "the step completed into the hot cell"
    assert b.damaged, "and was crippled there (§4.9.4)"
    assert (a.x, a.y) == (6, 7), "the cell it left was genuinely free"
    _assert_no_cell_shared(sess)
