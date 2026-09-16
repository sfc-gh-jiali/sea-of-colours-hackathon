"""Two harvesters stepping into one empty cell (§3.17, v1.48).

§3.17 opens by colliding two harvesters *arriving* on the same cell,
then illustrates four patterns. Converging steps are the plainest case
of that opening sentence and are not one of the four, so they fell
through to the ordinary seat loop — where the first seat walked
completed its step and TOOK the cell, and only the second was turned
back. Both wrecked either way; what seat index decided was **where**.

Now settled the way §3.17.3 and §3.17.4 settle the other two step
patterns — nobody moves, everybody wrecks at their original positions —
with the scar on the contested cell, following §3.17.2, the other case
where a destination is fought over and nobody arrives.

The negative cases matter as much as the positive ones. This pass fires
BEFORE the round, so a false positive wrecks two harvesters over a move
that was never going to happen.
"""
from __future__ import annotations

from typing import List, Tuple

import pytest

from sea_of_colours.game import weapons as W
from sea_of_colours.game.session import Entity, GameSession

SEATS = ("p1", "p2", "p3", "p4")
CONTESTED = (6, 7)


def _h(seat: str) -> str:
    return f"harvester_{seat}"


def _new(n_seats: int = 2) -> GameSession:
    return GameSession.new(20, 14, seed=901, players=list(SEATS[:n_seats]))


def _place(sess: GameSession, seat: str, x: int, y: int) -> Entity:
    ent = sess.entities[_h(seat)]
    ent.x, ent.y = x, y
    return ent


def _step(sess: GameSession, seat: str, to: Tuple[int, int]) -> None:
    sess.stash_policy(seat, [{"a": "step", "unit": _h(seat), "to": list(to)}])


def _wait_out(sess: GameSession) -> None:
    for seat in sess.players:
        if sess.pending_policies.get(seat) is None:
            sess.stash_policy(seat, [{"a": "wait"}])


def _converge(order: Tuple[str, str] = ("p1", "p2")) -> Tuple[GameSession, dict]:
    """A and B step in from opposite sides of ``CONTESTED``."""
    a, b = order
    sess = _new()
    refs = {
        "A": _place(sess, a, CONTESTED[0] - 1, CONTESTED[1]),
        "B": _place(sess, b, CONTESTED[0] + 1, CONTESTED[1]),
    }
    _step(sess, a, CONTESTED)
    _step(sess, b, CONTESTED)
    sess.maybe_resolve_if_ready()
    return sess, refs


def test_neither_harvester_takes_the_contested_cell() -> None:
    sess, refs = _converge()
    for role, ent in refs.items():
        assert (ent.x, ent.y) != CONTESTED, f"{role} took the contested cell"


def test_both_wreck_at_their_original_positions() -> None:
    sess, refs = _converge()
    assert (refs["A"].x, refs["A"].y) == (CONTESTED[0] - 1, CONTESTED[1])
    assert (refs["B"].x, refs["B"].y) == (CONTESTED[0] + 1, CONTESTED[1])
    assert refs["A"].damaged and refs["B"].damaged


def test_the_scar_is_stamped_on_the_contested_cell_only() -> None:
    sess, _refs = _converge()
    assert sorted(sess.collision_marks) == [f"{CONTESTED[0]}:{CONTESTED[1]}"]


def test_the_wreck_positions_do_not_depend_on_the_seating() -> None:
    first, refs_first = _converge(("p1", "p2"))
    second, refs_second = _converge(("p2", "p1"))
    for role in ("A", "B"):
        assert (
            (refs_first[role].x, refs_first[role].y)
            == (refs_second[role].x, refs_second[role].y)
        ), f"{role} came to rest somewhere else when the seats were swapped"
    assert sorted(first.collision_marks) == sorted(second.collision_marks)


def test_both_spill_their_cargo() -> None:
    sess = _new()
    a = _place(sess, "p1", CONTESTED[0] - 1, CONTESTED[1])
    b = _place(sess, "p2", CONTESTED[0] + 1, CONTESTED[1])
    a.cargo_squares = [{"square_id": "sq-a", "value": 400}]
    b.cargo_squares = [{"square_id": "sq-b", "value": 600}]
    _step(sess, "p1", CONTESTED)
    _step(sess, "p2", CONTESTED)
    sess.maybe_resolve_if_ready()

    assert not a.cargo_squares and not b.cargo_squares
    assert not (sess.hoard_squares.get("p1") or [])
    assert not (sess.hoard_squares.get("p2") or [])


def test_three_harvesters_converging_all_wreck_where_they_stood() -> None:
    sess = _new(3)
    starts = {
        "p1": (CONTESTED[0] - 1, CONTESTED[1]),
        "p2": (CONTESTED[0] + 1, CONTESTED[1]),
        "p3": (CONTESTED[0], CONTESTED[1] - 1),
    }
    refs = {s: _place(sess, s, *xy) for s, xy in starts.items()}
    for seat in starts:
        _step(sess, seat, CONTESTED)
    sess.maybe_resolve_if_ready()

    for seat, ent in refs.items():
        assert (ent.x, ent.y) == starts[seat], f"{seat} moved"
        assert ent.damaged, f"{seat} escaped undamaged"
    assert sorted(sess.collision_marks) == [f"{CONTESTED[0]}:{CONTESTED[1]}"]


# ── the negative cases: this pass runs BEFORE the round ──────────────

def test_a_lone_stepper_into_an_empty_cell_is_untouched() -> None:
    """One harvester is not a collision, however contested it looks."""
    sess = _new()
    a = _place(sess, "p1", CONTESTED[0] - 1, CONTESTED[1])
    _place(sess, "p2", 2, 2)
    _step(sess, "p1", CONTESTED)
    sess.stash_policy("p2", [{"a": "wait"}])
    sess.maybe_resolve_if_ready()

    assert (a.x, a.y) == CONTESTED
    assert not a.damaged
    assert not sess.collision_marks


def test_a_step_that_was_never_legal_does_not_manufacture_a_collision() -> None:
    """Both 'step' somewhere non-adjacent. Two wastes, not two wrecks."""
    sess = _new()
    far = (15, 3)
    a = _place(sess, "p1", CONTESTED[0] - 1, CONTESTED[1])
    b = _place(sess, "p2", CONTESTED[0] + 1, CONTESTED[1])
    _step(sess, "p1", far)
    _step(sess, "p2", far)
    sess.maybe_resolve_if_ready()

    assert not a.damaged and not b.damaged
    assert not sess.collision_marks


def test_a_harvester_with_a_full_hold_cannot_step_so_cannot_converge() -> None:
    """A full hold refuses the step (§3), so there is nothing to collide."""
    sess = _new()
    a = _place(sess, "p1", CONTESTED[0] - 1, CONTESTED[1])
    b = _place(sess, "p2", CONTESTED[0] + 1, CONTESTED[1])
    a.cargo_squares = [{"square_id": f"sq-{i}", "value": 100} for i in range(6)]
    _step(sess, "p1", CONTESTED)
    _step(sess, "p2", CONTESTED)
    sess.maybe_resolve_if_ready()

    assert not a.damaged, "the full-hold harvester never stepped"
    assert (b.x, b.y) == CONTESTED, "B had the cell to itself"
    assert not b.damaged


def test_an_occupied_cell_is_a_step_into_collision_not_this() -> None:
    """§3.17.3 still owns the case where somebody is standing there."""
    sess = _new(3)
    a = _place(sess, "p1", CONTESTED[0] - 1, CONTESTED[1])
    b = _place(sess, "p2", CONTESTED[0] + 1, CONTESTED[1])
    sitting = _place(sess, "p3", *CONTESTED)
    _step(sess, "p1", CONTESTED)
    _step(sess, "p2", CONTESTED)
    sess.stash_policy("p3", [{"a": "wait"}])
    sess.maybe_resolve_if_ready()

    assert sitting.damaged, "the occupant should have been rammed"
    assert (sitting.x, sitting.y) == CONTESTED, "the occupant stays put"
    assert a.damaged and b.damaged
    assert (a.x, a.y) == (CONTESTED[0] - 1, CONTESTED[1])
    assert (b.x, b.y) == (CONTESTED[0] + 1, CONTESTED[1])


def test_an_emp_smothered_harvester_never_steps_so_never_converges() -> None:
    """The one precondition that is not static, and is excluded up front.

    A unit inside an active cloud has its action smothered, so it is not
    arriving anywhere. Its rival should walk onto the cell unopposed
    rather than be wrecked against a harvester that never moved.
    """
    sess = _new(3)
    a = _place(sess, "p1", CONTESTED[0] - 1, CONTESTED[1])
    b = _place(sess, "p2", CONTESTED[0] + 1, CONTESTED[1])
    sess.entities[_h("p3")].x, sess.entities[_h("p3")].y = None, None
    sess.weapon_stock["p3"] = {"emp": 1}
    # Aim OFF to A's far side, not at A itself: the blast is a Manhattan
    # radius-2 diamond, and any two cells adjacent to the contested one
    # are at most 2 apart, so a shot centred on A would smother B too and
    # the test would pass for the wrong reason. From (4,7), A at (5,7) is
    # 1 away and inside; B at (7,7) is 3 away and clear.
    blast = (a.x - 1, a.y)
    assert abs(blast[0] - b.x) + abs(blast[1] - b.y) > W.EMP_RADIUS
    sess.stash_policy("p3", [
        {"a": "emp_launch", "at": [list(blast)]},
        {"a": "wait"},
    ])
    for seat in ("p1", "p2"):
        sess.stash_policy(seat, [
            {"a": "wait"},
            {"a": "step", "unit": _h(seat), "to": list(CONTESTED)},
        ])
    sess.maybe_resolve_if_ready()

    assert (b.x, b.y) == CONTESTED, "B should have walked in unopposed"
    assert not b.damaged, "B was wrecked against a harvester that never moved"
