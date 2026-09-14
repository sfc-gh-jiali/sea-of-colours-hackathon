"""Seat order is not a factor (RULEBOOK §3.10, §3.13) — the whole board.

    "Moves resolve in parallel ... the engine's seat-by-seat application
    order is an implementation detail with no rules standing."

This is the differential harness for that claim, and the safety net for
finishing issue #56. Every scenario below is run TWICE — once with role A
on seat ``p1``, once with role A on seat ``p2`` — and the outcome is
recorded **keyed by role**. If the two runs disagree, the engine let the
seat index decide, which the rule above forbids.

Scenarios still known to be order-dependent are marked ``xfail(strict)``
rather than deleted, so they are executable documentation of exactly what
is left. When a later change fixes one, this file fails with an XPASS and
tells whoever did it to drop the marker — which is the point: the gaps
announce themselves instead of being rediscovered.

Adding a scenario is deliberately cheap. Write a setup function that
describes the board in terms of roles A and B only (never ``p1`` /
``p2`` — that would bake in the very thing under test) and add it to
``SCENARIOS``. Do not assert a specific outcome here; that belongs in a
rule-specific test like test_egress_is_not_seat_ordered.py. The only
question this file asks is "does the answer depend on the seat?".
"""
from __future__ import annotations

import pytest

from sea_of_colours.game.session import Entity, GameSession


def _h(seat: str) -> str:
    return f"harvester_{seat}"


def _probe_for(sess: GameSession, seat: str, x: int, y: int, tag: str = "") -> None:
    pid = f"probe_{seat}_{tag or f'{x}_{y}'}"
    sess.entities[pid] = Entity(pid, "probe", seat, x, y)


# ── scenarios ────────────────────────────────────────────────────────
# Each takes (sess, A, B) where A and B are seat names. Describe the
# board only in terms of A and B so the setup is symmetric by
# construction.

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


#: ``(id, setup, known_gap)``. ``known_gap`` names the reason the engine
#: is still order-dependent; None means it must be deterministic today.
SCENARIOS = [
    ("swap", _swap, None),
    ("simultaneous-drop", _simultaneous_drop, None),
    ("drop-onto-static", _drop_onto_static, None),
    ("step-into-static", _step_into_static, None),
    ("probe-same-cell", _probe_same_cell, None),
    ("drop-onto-pickup", _drop_onto_pickup, None),      # fixed v1.48
    ("step-onto-pickup", _step_onto_pickup, None),      # fixed v1.48
    (
        "follow",
        _follow,
        "#56 — a step can be refused mid-hour, so 'will B vacate?' is "
        "not answerable at hour start; needs dependency-ordered dispatch",
    ),
    (
        "drop-onto-stepaway",
        _drop_onto_stepaway,
        "#56 — same as follow",
    ),
    (
        "converge-step",
        _converge_step,
        "#56 — needs the contention pre-pass generalised to group steps "
        "with drops; both wreck either way, but the scars land on "
        "different cells by seat",
    ),
    (
        "drop-crushes-same-hour-probe",
        _drop_crushes_probe,
        "#56 — probe crushing runs inside the mover's slot; wants to be "
        "a post-hour pass",
    ),
]


def _outcome(setup, A: str, B: str) -> dict:
    """Resolve one night and describe it BY ROLE, never by seat."""
    sess = GameSession.new(20, 14, seed=901)
    setup(sess, A, B)
    # Hold the entity objects: Aurora drops destroyed harvesters out of
    # sess.entities, so looking them up afterwards returns None and hides
    # the very difference being audited.
    refs = {"A": sess.entities[_h(A)], "B": sess.entities[_h(B)]}
    seats = {"A": A, "B": B}
    sess.maybe_resolve_if_ready()

    out: dict = {"scars": tuple(sorted(sess.collision_marks))}
    for role, ent in refs.items():
        seat = seats[role]
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
    return out


@pytest.mark.parametrize(
    "setup,known_gap",
    [
        pytest.param(
            setup,
            gap,
            id=sid,
            marks=(
                pytest.mark.xfail(strict=True, reason=gap) if gap else ()
            ),
        )
        for sid, setup, gap in SCENARIOS
    ],
)
def test_the_outcome_does_not_depend_on_which_seat_holds_which_role(
    setup, known_gap
) -> None:
    on_p1 = _outcome(setup, "p1", "p2")
    on_p2 = _outcome(setup, "p2", "p1")
    differing = {
        key: (on_p1[key], on_p2[key])
        for key in on_p1
        if on_p1[key] != on_p2[key]
    }
    assert not differing, (
        "seat order changed the outcome, which §3.10/§3.13 forbid. "
        f"Differences (role-A-on-p1 vs role-A-on-p2): {differing}"
    )
