"""A probe never survives the hour under a harvester (§3.11.1, v1.49).

§3.11.1 has always said a harvester riding onto a probe crushes it, and
the engine has always done that — inside the mover's own slot, as part
of the drop or the step. That is the right home for the ordinary case,
where the probe was already sitting there.

It is the wrong home when the probe is launched onto the harvester's
cell during the *same* hour, because then the answer came down to which
seat the dispatch loop walked first. Prober first: the probe lands,
possibly superseding whatever was there, and is flattened a moment later
by the harvester. Harvester first: it lands, crushes whatever was there,
and the probe then settles underneath it and lives — the only way the
board could ever show a probe and a harvester sharing a cell. Same two
orders, same two moves, opposite answers, and nothing in the rules to
pick between them. It was the last of the six in issue #56.

The fix is additive: a sweep at the close of every hour, after every
seat has acted. The mover's own crush is untouched, so the ordinary case
keeps its caption, its frame and its kill-feed credit, and the sweep
finds nothing left to do. These tests pin both halves of that — the new
behaviour, and the absence of change in the old.
"""
from __future__ import annotations

import itertools
from typing import List, Optional, Tuple

from sea_of_colours.game.session import Entity, GameSession

SEATS = ("p1", "p2", "p3", "p4")
CELL = (6, 7)


def _h(seat: str) -> str:
    return f"harvester_{seat}"


def _new(n: int = 2) -> GameSession:
    return GameSession.new(20, 14, seed=901, players=list(SEATS[:n]))


def _probe(sess: GameSession, seat: str, x: int, y: int, tag: str) -> str:
    """Plant a probe on the board directly, as an earlier night would."""
    pid = f"probe_{seat}_{tag}"
    sess.entities[pid] = Entity(pid, "probe", seat, x, y)
    return pid


def _finish(sess: GameSession) -> None:
    for seat in sess.players:
        if sess.pending_policies.get(seat) is None:
            sess.stash_policy(seat, [{"a": "wait"}])
    assert sess.maybe_resolve_if_ready()


def _probes(sess: GameSession) -> List[Tuple[str, int, int]]:
    return sorted(
        (str(e.owner), int(e.x), int(e.y))
        for e in sess.entities.values()
        if e.entity_type == "probe" and e.x is not None
    )


def _frames(sess: GameSession, tag: str) -> List[dict]:
    return [f for f in (sess.last_night_replay or []) if f.get("tag") == tag]


def _crushed_ids(sess: GameSession) -> List[str]:
    out: List[str] = []
    for f in (sess.last_night_replay or []):
        for ev in (f.get("crushed_probes") or []):
            if ev.get("reason") == "crushed_by_harvester":
                out.append(str(ev.get("probe_id")))
    return sorted(out)


def _land_and_probe(
    sess: GameSession, lander: str, prober: str, *, sighted_by: Optional[str] = None,
) -> None:
    """``lander`` drops onto CELL; ``prober`` launches onto it the same hour.

    A drop needs vision of the target, which is what ``sighted_by``'s
    probe provides — and it is also the incumbent whose death is the
    other half of the contest.
    """
    x, y = CELL
    _probe(sess, sighted_by or lander, x, y, "vis")
    sess.stash_policy(lander, [{"a": "drop", "unit": _h(lander), "at": [x, y]}])
    sess.stash_policy(prober, [{"a": "probe", "at": [x, y]}])


# ── the fix ──────────────────────────────────────────────────────────

def test_a_probe_launched_onto_a_landing_cell_is_crushed() -> None:
    sess = _new()
    _land_and_probe(sess, "p1", "p2")
    # Hold the reference: the harvester is stranded at dawn and Aurora
    # takes it out of ``entities`` before we get to look.
    harv = sess.entities[_h("p1")]
    _finish(sess)

    assert _probes(sess) == []
    assert harv.x == CELL[0], "the landing itself must still have happened"


def test_it_is_crushed_whichever_seat_holds_which_role() -> None:
    """The whole point. Twelve seatings, one answer."""
    seen = set()
    for lander, prober in itertools.permutations(SEATS, 2):
        sess = _new(4)
        _land_and_probe(sess, lander, prober)
        harv = sess.entities[_h(lander)]
        _finish(sess)
        # Key by ROLE, not by seat, or the comparison is vacuous.
        seen.add((
            tuple(sorted(
                ("lander" if o == lander else "prober" if o == prober else o)
                for o, _x, _y in _probes(sess)
            )),
            harv.x is not None,
        ))
    assert len(seen) == 1, seen
    assert seen == {((), True)}


def test_the_sweep_credits_the_harvester_s_house() -> None:
    sess = _new()
    _land_and_probe(sess, "p1", "p2")
    _finish(sess)

    crushes = [
        ev
        for f in (sess.last_night_replay or [])
        for ev in (f.get("crushed_probes") or [])
        if ev.get("probe_owner") == "p2"
    ]
    assert len(crushes) == 1
    assert crushes[0]["reason"] == "crushed_by_harvester"
    assert crushes[0]["crusher_owner"] == "p1"


def test_the_sweep_rides_its_own_ownerless_frame() -> None:
    """The client renders it off ``crushed_probes``, not off the tag, so
    the frame needs no new branch — but it does need to exist, and to
    carry the payload the splash animation reads."""
    sess = _new()
    _land_and_probe(sess, "p1", "p2")
    _finish(sess)

    swept = _frames(sess, "probe_crushed")
    assert len(swept) == 1
    assert swept[0]["owner"] is None
    assert swept[0]["hour"] == 1
    assert [e["probe_id"] for e in swept[0]["crushed_probes"]] == ["probe_p2_1"]


def test_a_probe_that_outlived_the_bug_is_swept_on_the_next_hour() -> None:
    """A board carrying the old bug's leftovers heals itself: the sweep
    reads the board, not this hour's moves, so a probe already sitting
    under a harvester goes on the first hour of the next night."""
    sess = _new()
    x, y = CELL
    harv = sess.entities[_h("p1")]
    harv.x, harv.y = x, y
    stowaway = _probe(sess, "p2", x, y, "legacy")
    sess.stash_policy("p1", [{"a": "wait"}])
    _finish(sess)

    assert stowaway not in sess.entities


def test_a_stepping_harvester_crushes_a_same_hour_probe_too() -> None:
    """Not a drop-only rule — arrival is arrival."""
    sess = _new()
    x, y = CELL
    _probe(sess, "p1", x, y, "vis")
    sess.entities[_h("p1")].x, sess.entities[_h("p1")].y = x - 1, y
    sess.stash_policy("p1", [{"a": "step", "unit": _h("p1"), "to": [x, y]}])
    sess.stash_policy("p2", [{"a": "probe", "at": [x, y]}])
    _finish(sess)

    assert _probes(sess) == []


def test_a_wreck_pile_credits_nobody() -> None:
    """Two harvesters on one cell is a collision's leftovers. Crediting
    one of them would hand the answer straight back to the seat loop."""
    sess = _new()
    x, y = CELL
    _probe(sess, "p1", x, y, "vis-a")
    _probe(sess, "p2", x, y, "vis-b")
    # §3.17.2 — both drop on one cell, neither lands... so instead put
    # them there the hard way: a step into a stationary occupant (§3.17.3)
    # leaves both wrecks on adjacent cells, not one. Place them directly.
    sess.entities[_h("p1")].x, sess.entities[_h("p1")].y = x, y
    sess.entities[_h("p2")].x, sess.entities[_h("p2")].y = x, y
    sess.stash_policy("p1", [{"a": "wait"}])
    sess.stash_policy("p2", [{"a": "wait"}])
    _finish(sess)

    assert _probes(sess) == []
    swept = _frames(sess, "probe_crushed")
    assert swept, "the sweep should have fired"
    assert all(
        ev["crusher_owner"] is None
        for f in swept for ev in f["crushed_probes"]
    )


# ── the absence of change ────────────────────────────────────────────

def test_the_ordinary_crush_still_happens_in_the_mover_s_own_slot() -> None:
    """The common case — a harvester rides onto a probe that was already
    there — must not move to the sweep. Its caption and its frame are
    read by the replay UI and by the asset ledger."""
    sess = _new()
    x, y = CELL
    _probe(sess, "p2", x, y, "old")
    _probe(sess, "p1", x, y - 1, "vis")
    sess.stash_policy("p1", [{"a": "drop", "unit": _h("p1"), "at": [x, y]}])
    sess.stash_policy("p2", [{"a": "wait"}])
    _finish(sess)

    drops = _frames(sess, "drop")
    assert len(drops) == 1
    assert drops[0]["owner"] == "p1"
    assert "probe crushed" in drops[0]["caption"]
    assert [e["probe_id"] for e in drops[0]["crushed_probes"]] == ["probe_p2_old"]
    assert not _frames(sess, "probe_crushed"), "the sweep should find nothing"


def test_the_sweep_is_silent_when_no_probe_is_buried() -> None:
    sess = _new()
    x, y = CELL
    _probe(sess, "p1", x, y - 1, "vis")
    sess.stash_policy("p1", [{"a": "drop", "unit": _h("p1"), "at": [x, y]}])
    sess.stash_policy("p2", [{"a": "wait"}])
    _finish(sess)

    assert not _frames(sess, "probe_crushed")
    assert _probes(sess) == [("p1", x, y - 1)]


def test_a_probe_on_an_empty_cell_is_left_alone() -> None:
    """The sweep keys off harvesters, not off probes. A probe launched
    anywhere else is none of its business."""
    sess = _new()
    x, y = CELL
    _probe(sess, "p1", x, y, "vis")
    sess.stash_policy("p1", [{"a": "drop", "unit": _h("p1"), "at": [x, y]}])
    sess.stash_policy("p2", [{"a": "probe", "at": [x + 3, y + 2]}])
    _finish(sess)

    assert _probes(sess) == [("p2", x + 3, y + 2)]


def test_a_harvester_lifting_off_does_not_crush_the_probe_behind_it() -> None:
    """Departure is not occupancy. The sweep reads the board after the
    hour, and by then the lifter is in orbit with x=None."""
    sess = _new()
    x, y = CELL
    harv = sess.entities[_h("p1")]
    harv.x, harv.y = x, y
    sess.stash_policy("p1", [{"a": "pickup", "unit": _h("p1")}])
    sess.stash_policy("p2", [{"a": "probe", "at": [x, y]}])
    _finish(sess)

    assert _probes(sess) == [("p2", x, y)]
    assert harv.x is None


def test_a_probe_pair_colliding_on_a_harvester_cell_is_still_a_collision() -> None:
    """§3.16 runs first and takes both probes; the sweep then has
    nothing to find, and must not invent a crush out of the crater."""
    sess = _new(3)
    x, y = CELL
    _probe(sess, "p1", x, y, "vis")
    sess.stash_policy("p1", [{"a": "drop", "unit": _h("p1"), "at": [x, y]}])
    sess.stash_policy("p2", [{"a": "probe", "at": [x, y]}])
    sess.stash_policy("p3", [{"a": "probe", "at": [x, y]}])
    _finish(sess)

    assert _probes(sess) == []
    assert "probe_p2_1" not in _crushed_ids(sess)
    assert "probe_p3_1" not in _crushed_ids(sess)
