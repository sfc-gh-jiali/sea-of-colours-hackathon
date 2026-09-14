"""Lift-and-land is a rule, not a coin toss on seat index (v1.48).

RULEBOOK §3.17's governing sentence damages two harvesters **arriving**
on one cell. A harvester being lifted is departing, so a rival landing on
the cell it vacates does not collide with it.

The engine used to answer that question by reading live occupancy inside
whichever seat the hour loop reached first: pickup first and both sides
walked away clean, drop first and both wrecked and a full hold was lost.
Same orders, different seat index, opposite outcome — which §3.10 and
§3.13 both forbid ("seat order is not a factor").

Every test here runs the SAME scenario twice with the roles swapped
between seats, and asserts the two runs agree. That is the property; the
specific outcome is asserted alongside it so a future change cannot make
them agree by breaking both equally.
"""
from __future__ import annotations

from sea_of_colours.game.session import Entity, GameSession

HAUL = [{"square_id": "sq-haul", "value": 500}]


def _probe_for(sess: GameSession, seat: str, x: int, y: int) -> None:
    """Give ``seat`` live vision of (x, y) so a drop there validates."""
    pid = f"probe_{seat}_vis"
    sess.entities[pid] = Entity(pid, "probe", seat, x, y)


def _run_lift_and_land(lander: str, lifter: str, *, verb: str) -> dict:
    """``lander`` takes (6,7) by ``verb`` as ``lifter`` lifts off it."""
    sess = GameSession.new(20, 14, seed=811)
    hl = sess.entities[f"harvester_{lifter}"]
    hl.x, hl.y = 6, 7
    hl.cargo_squares = list(HAUL)
    hd = sess.entities[f"harvester_{lander}"]

    if verb == "step":
        hd.x, hd.y = 5, 7
        arrival = {"a": "step", "unit": hd.id, "to": [6, 7]}
    else:
        _probe_for(sess, lander, 6, 7)
        arrival = {"a": "drop", "unit": hd.id, "at": [6, 7]}

    sess.stash_policy(lander, [arrival])
    sess.stash_policy(lifter, [{"a": "pickup", "unit": hl.id}])
    sess.maybe_resolve_if_ready()

    return {
        "lander damaged": bool(getattr(hd, "damaged", False)),
        "lander at": (hd.x, hd.y),
        "lifter damaged": bool(getattr(hl, "damaged", False)),
        "lifter banked": sum(
            int(s.get("value", 0)) for s in (sess.hoard_squares.get(lifter) or [])
        ),
        "scars": tuple(sorted(sess.collision_marks)),
    }


def test_a_drop_onto_a_cell_being_lifted_from_does_not_collide() -> None:
    out = _run_lift_and_land("p1", "p2", verb="drop")
    assert out["lander damaged"] is False
    assert out["lander at"] == (6, 7), "the lander takes the vacated cell"
    assert out["lifter damaged"] is False
    assert out["lifter banked"] == 500, "the lifter gets its haul home"
    assert out["scars"] == (), "nothing collided, so nothing is scarred"


def test_a_step_onto_a_cell_being_lifted_from_does_not_collide() -> None:
    out = _run_lift_and_land("p1", "p2", verb="step")
    assert out["lander damaged"] is False
    assert out["lander at"] == (6, 7)
    assert out["lifter damaged"] is False
    assert out["lifter banked"] == 500
    assert out["scars"] == ()


def test_the_drop_outcome_does_not_depend_on_which_seat_lifts() -> None:
    """The bug itself: swap the roles between seats, get the same night."""
    assert _run_lift_and_land("p1", "p2", verb="drop") == \
        _run_lift_and_land("p2", "p1", verb="drop")


def test_the_step_outcome_does_not_depend_on_which_seat_lifts() -> None:
    assert _run_lift_and_land("p1", "p2", verb="step") == \
        _run_lift_and_land("p2", "p1", verb="step")


def test_a_lifter_that_is_not_leaving_this_hour_still_collides() -> None:
    """The exemption is for THIS hour's egress, not for a queued pickup.

    p2 waits on hour 1 and only lifts on hour 2, so on hour 1 it is an
    ordinary occupant and §3.17.1 applies in full. Without this the fix
    would read "anyone with a pickup anywhere in their queue is
    intangible", which is a much bigger rule than the one intended.
    """
    sess = GameSession.new(20, 14, seed=812)
    h2 = sess.entities["harvester_p2"]
    h2.x, h2.y = 6, 7
    h2.cargo_squares = list(HAUL)
    h1 = sess.entities["harvester_p1"]
    _probe_for(sess, "p1", 6, 7)

    sess.stash_policy("p1", [{"a": "drop", "unit": "harvester_p1", "at": [6, 7]}])
    sess.stash_policy(
        "p2",
        [{"a": "wait"}, {"a": "pickup", "unit": "harvester_p2"}],
    )
    sess.maybe_resolve_if_ready()

    assert h1.damaged and h2.damaged, "an occupant standing still is rammable"
    assert "6:7" in sess.collision_marks
    assert not sess.hoard_squares.get("p2"), "the haul is lost in the crash"


def test_a_stationary_occupant_is_still_rammed() -> None:
    """§3.17.1 is untouched — the exemption is narrow."""
    sess = GameSession.new(20, 14, seed=813)
    h2 = sess.entities["harvester_p2"]
    h2.x, h2.y = 6, 7
    h1 = sess.entities["harvester_p1"]
    _probe_for(sess, "p1", 6, 7)

    sess.stash_policy("p1", [{"a": "drop", "unit": "harvester_p1", "at": [6, 7]}])
    sess.stash_policy("p2", [{"a": "wait"}])
    sess.maybe_resolve_if_ready()

    assert h1.damaged and h2.damaged
    assert "6:7" in sess.collision_marks
