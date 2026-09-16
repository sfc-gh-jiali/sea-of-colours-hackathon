"""Everything contended on one hour is settled on THAT hour (§3.10).

v1.48. Both contention pre-passes used to handle one collision and then
hand back to the round loop to find the next one. That loop derives its
clock from ``max(applied) + 1``, and the collision just resolved had
bumped ``applied`` — so a second, entirely unrelated pile-up on the same
hour was recorded an hour later than it happened.

The board came out right, which is why it went unnoticed: everyone
involved wrecked either way. What it got wrong was the account of the
night, and it got it wrong in a partisan direction — the pair sitting on
the lower seat indices always kept the earlier hour. §3.13 gives seat
index no standing in anything, the replay included.

It takes three or four seats to see at all, which is the other reason it
lasted: two seats cannot contend twice in one hour.

The per-seat re-stamp in the round loop cannot clean this up afterwards,
and it is worth knowing why — a joint collision frame belongs to nobody
(``owner=None``, participants listed under ``collisions[].owners``) and
that pass skips ownerless frames by design.
"""
from __future__ import annotations

from typing import List, Tuple

from sea_of_colours.game.session import Entity, GameSession

SEATS = ("p1", "p2", "p3", "p4")


def _h(seat: str) -> str:
    return f"harvester_{seat}"


def _new() -> GameSession:
    return GameSession.new(20, 14, seed=901, players=list(SEATS))


def _wait_out(sess: GameSession) -> None:
    for seat in SEATS:
        if sess.pending_policies.get(seat) is None:
            sess.stash_policy(seat, [{"a": "wait"}])


def _collision_hours(sess: GameSession, tag: str) -> List[Tuple[int, frozenset]]:
    """(hour, participating seats) for each joint collision frame."""
    out = []
    for frame in sess.last_night_replay or []:
        if frame.get("tag") != tag:
            continue
        seats: set = set()
        for col in frame.get("collisions") or []:
            seats |= set(col.get("owners") or [])
        out.append((frame.get("hour"), frozenset(seats)))
    return out


def _face_off(sess: GameSession, a: str, b: str, y: int) -> None:
    """Put ``a`` and ``b`` nose to nose on row ``y`` and have them cross."""
    sess.entities[_h(a)].x, sess.entities[_h(a)].y = 5, y
    sess.entities[_h(b)].x, sess.entities[_h(b)].y = 6, y
    sess.stash_policy(a, [{"a": "step", "unit": _h(a), "to": [6, y]}])
    sess.stash_policy(b, [{"a": "step", "unit": _h(b), "to": [5, y]}])


def test_two_independent_swaps_both_land_on_the_same_hour() -> None:
    sess = _new()
    _face_off(sess, "p1", "p2", 7)
    _face_off(sess, "p3", "p4", 11)
    _wait_out(sess)
    sess.maybe_resolve_if_ready()

    smashes = _collision_hours(sess, "collision_swap")
    assert len(smashes) == 2, f"expected two head-on smashes, got {smashes}"
    assert smashes[0][0] == smashes[1][0] == 1, (
        f"both pairs crossed on hour 1; recorded at {[h for h, _ in smashes]}"
    )


def test_which_pair_is_recorded_first_is_not_a_seat_ordering() -> None:
    """Swap the pairs across the seats; both still resolve on hour 1."""
    for lo, hi in ((("p1", "p2"), ("p3", "p4")), (("p3", "p4"), ("p1", "p2"))):
        sess = _new()
        _face_off(sess, lo[0], lo[1], 7)
        _face_off(sess, hi[0], hi[1], 11)
        _wait_out(sess)
        sess.maybe_resolve_if_ready()

        by_hour = {seats: hour for hour, seats in _collision_hours(sess, "collision_swap")}
        assert by_hour == {frozenset(lo): 1, frozenset(hi): 1}, (
            f"with {lo} on row 7 and {hi} on row 11, hours were {by_hour}"
        )


def test_two_contested_landing_squares_both_land_on_the_same_hour() -> None:
    """The same defect lived in the simultaneous-drop pre-pass."""
    sess = _new()
    for seat, cell in (("p1", (6, 7)), ("p2", (6, 7)), ("p3", (6, 11)), ("p4", (6, 11))):
        pid = f"probe_{seat}"
        sess.entities[pid] = Entity(pid, "probe", seat, cell[0], cell[1])
        sess.stash_policy(
            seat, [{"a": "drop", "unit": _h(seat), "at": list(cell)}]
        )
    sess.maybe_resolve_if_ready()

    piles = _collision_hours(sess, "collision_simultaneous_drops")
    assert len(piles) == 2, f"expected two contested squares, got {piles}"
    assert piles[0][0] == piles[1][0] == 1, (
        f"both squares were contested on hour 1; recorded at "
        f"{[h for h, _ in piles]}"
    )


def test_a_swap_and_a_contested_landing_share_their_hour() -> None:
    """The two pre-passes used to be mutually exclusive within an hour.

    A swap returned straight to the round loop, so a contested landing
    elsewhere on the board — nothing to do with it — was pushed into the
    following hour.
    """
    sess = _new()
    _face_off(sess, "p1", "p2", 7)
    for seat in ("p3", "p4"):
        pid = f"probe_{seat}"
        sess.entities[pid] = Entity(pid, "probe", seat, 6, 11)
        sess.stash_policy(seat, [{"a": "drop", "unit": _h(seat), "at": [6, 11]}])
    sess.maybe_resolve_if_ready()

    swap = _collision_hours(sess, "collision_swap")
    pile = _collision_hours(sess, "collision_simultaneous_drops")
    assert swap and pile, f"expected both kinds of collision; got {swap} {pile}"
    assert swap[0][0] == pile[0][0] == 1, (
        f"swap recorded at h{swap[0][0]}, pile-up at h{pile[0][0]}; "
        "both happened on hour 1"
    )


def test_settling_both_pairs_does_not_grant_anyone_a_second_action() -> None:
    """The rescan must not pair a seat that has already crossed.

    Resolving pairs in a loop means walking the seat list again with
    ``applied`` already bumped; if the seat were not excluded it could
    be matched a second time on the same hour against its NEXT queued
    move, which is a move belonging to a later hour.
    """
    sess = _new()
    _face_off(sess, "p1", "p2", 7)
    _face_off(sess, "p3", "p4", 11)
    # Give everyone somewhere else to be afterwards, so there IS a next
    # move for a buggy rescan to reach for.
    for seat in SEATS:
        sess.pending_policies[seat] = None
        sess.stash_policy(seat, [
            {"a": "step", "unit": _h(seat), "to": list(
                (6, 7) if seat == "p1" else
                (5, 7) if seat == "p2" else
                (6, 11) if seat == "p3" else (5, 11)
            )},
            {"a": "wait"},
            {"a": "wait"},
        ])
    sess.maybe_resolve_if_ready()

    per_seat_hour: set = set()
    for frame in sess.last_night_replay or []:
        owner, hour = frame.get("owner"), frame.get("hour")
        if not owner or not isinstance(hour, int) or hour <= 0:
            continue
        assert (owner, hour) not in per_seat_hour, (
            f"{owner} acted twice on hour {hour}"
        )
        per_seat_hour.add((owner, hour))

    assert len(_collision_hours(sess, "collision_swap")) == 2
