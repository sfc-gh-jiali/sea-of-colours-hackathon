"""Weapon timing is what RULEBOOK §4.9 says it is.

Every test here pins one sentence of the rulebook against a real
resolved night. The weapons are the part of the engine where "when"
carries as much weight as "what" — a chaff window that is an hour short,
or an EMP that denies a harvest it should have allowed, is not a visible
crash, it is a season that quietly scores differently.

These began as a throwaway audit written to answer whether §4.9 was
still true. It was (25 claims, 25 held), and the audit is here rather
than in /tmp because the answer is only worth having continuously: the
hour loop is due to be reordered to finish issue #56, and these are the
behaviours a reordering would disturb without failing anything else.

Read the dials from :mod:`sea_of_colours.game.weapons`, never a literal
— the whole point is that a retune moves these tests with it instead of
leaving them asserting last month's numbers.
"""
from __future__ import annotations

import pytest

from sea_of_colours.game import weapons as W
from sea_of_colours.game.session import Entity, GameSession


def _new(seed: int = 1201) -> GameSession:
    return GameSession.new(24, 18, seed=seed)


def _arm(sess: GameSession, seat: str, **kinds: int) -> None:
    cur = dict(sess.weapon_stock.get(seat) or {})
    cur.update(kinds)
    sess.weapon_stock[seat] = cur


def _probe(sess: GameSession, seat: str, x: int, y: int, tag: str = "") -> str:
    pid = f"probe_{seat}_{tag or f'{x}_{y}'}"
    sess.entities[pid] = Entity(pid, "probe", seat, x, y)
    return pid


def _stock(sess: GameSession, seat: str, kind: str) -> int:
    return int((sess.weapon_stock.get(seat) or {}).get(kind, 0))


def _in_orbit(sess: GameSession, *seats: str) -> None:
    for seat in seats:
        ent = sess.entities[f"harvester_{seat}"]
        ent.x, ent.y = None, None


def _tagged(sess: GameSession, tag: str) -> list:
    """(hour, caption) for every replay frame carrying ``tag``."""
    return [
        (f.get("hour"), str(f.get("caption", "")))
        for f in sess.last_night_replay
        if f.get("tag") == tag
    ]


def _hours_tagged(sess: GameSession, tag: str) -> list:
    return sorted({h for h, _ in _tagged(sess, tag)})


def _peak_clouds(sess: GameSession) -> list:
    """The most clouds standing on any one replay frame.

    EMP clouds are intra-night only — the simulator clears them at dawn
    — so reading ``sess.emp_clouds`` after the night always reports
    zero, for a reason that has nothing to do with the claim under
    test. The replay frames snapshot the field hour by hour, so they
    are where a cloud can still be seen.
    """
    peak: list = []
    for frame in sess.last_night_replay:
        clouds = frame.get("emp_clouds") or []
        if len(clouds) > len(peak):
            peak = clouds
    return peak


# ── chaff ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def chaff_window() -> GameSession:
    """p1 flares at hour 1, then both seats try to act for four hours."""
    sess = _new()
    _arm(sess, "p1", chaff=1)
    sess.entities["harvester_p1"].x, sess.entities["harvester_p1"].y = 5, 5
    sess.entities["harvester_p2"].x, sess.entities["harvester_p2"].y = 9, 9
    sess.stash_policy("p1", [
        {"a": "chaff_flare"},
        {"a": "step", "unit": "harvester_p1", "to": [6, 5]},
        {"a": "step", "unit": "harvester_p1", "to": [7, 5]},
        {"a": "step", "unit": "harvester_p1", "to": [8, 5]},
    ])
    sess.stash_policy("p2", [
        {"a": "step", "unit": "harvester_p2", "to": [10, 9]},
        {"a": "step", "unit": "harvester_p2", "to": [11, 9]},
        {"a": "step", "unit": "harvester_p2", "to": [12, 9]},
        {"a": "step", "unit": "harvester_p2", "to": [13, 9]},
    ])
    sess.maybe_resolve_if_ready()
    return sess


def test_a_flare_jams_the_whole_window(chaff_window: GameSession) -> None:
    """§4.9.5 — a flare at hour N smothers N through N+CHAFF_DURATION-1."""
    dur = W.CHAFF_DURATION_HOURS
    jammed = _hours_tagged(chaff_window, "chaffed")
    assert set(range(1, dur + 1)) <= set(jammed), (
        f"flare at h1 should jam h1..h{dur}; jammed hours were {jammed}"
    )


def test_the_window_closes_on_time(chaff_window: GameSession) -> None:
    """§4.9.5 — the window is exactly CHAFF_DURATION_HOURS long."""
    dur = W.CHAFF_DURATION_HOURS
    jammed = _hours_tagged(chaff_window, "chaffed")
    assert (dur + 1) not in jammed, (
        f"hour {dur + 1} should be clear again; jammed hours were {jammed}"
    )


def test_the_launcher_is_immune_only_on_its_own_launch_hour(
    chaff_window: GameSession,
) -> None:
    """§4.9.5 — you get the hour you fired; after that you jam yourself too."""
    mine = sorted({h for h, cap in _tagged(chaff_window, "chaffed") if "p1" in cap})
    assert 1 not in mine, f"the launcher was jammed on its own launch hour: {mine}"
    assert {2, 3} <= set(mine), f"the launcher should self-jam after h1; got {mine}"


def test_two_flares_in_one_hour_both_spend_their_charge() -> None:
    """§4.9.5 — simultaneous flares both fire; neither is refunded."""
    sess = _new()
    for seat in ("p1", "p2"):
        _arm(sess, seat, chaff=1)
        _in_orbit(sess, seat)
        sess.stash_policy(
            seat, [{"a": "chaff_flare"}] + [{"a": "wait"}] * 5
        )
    sess.maybe_resolve_if_ready()

    assert _stock(sess, "p1", "chaff") == 0
    assert _stock(sess, "p2", "chaff") == 0


def test_two_simultaneous_flares_do_not_extend_the_window() -> None:
    """§4.9.5 — two flares are not twice the jamming."""
    sess = _new()
    for seat in ("p1", "p2"):
        _arm(sess, seat, chaff=1)
        _in_orbit(sess, seat)
        sess.stash_policy(
            seat, [{"a": "chaff_flare"}] + [{"a": "wait"}] * 5
        )
    sess.maybe_resolve_if_ready()

    jammed = _hours_tagged(sess, "chaffed")
    assert not jammed or max(jammed) <= W.CHAFF_DURATION_HOURS, (
        f"window ran to h{max(jammed)}, cap is {W.CHAFF_DURATION_HOURS}"
    )


def test_chaff_outranks_a_same_hour_emp_salvo() -> None:
    """§4.9.3 (v1.14) — a jammed hour launches nothing at all."""
    sess = _new()
    _arm(sess, "p1", chaff=1)
    _arm(sess, "p2", emp=1)
    _in_orbit(sess, "p1", "p2")
    sess.stash_policy("p1", [{"a": "chaff_flare"}] + [{"a": "wait"}] * 4)
    sess.stash_policy(
        "p2", [{"a": "emp_launch", "at": [[9, 9]]}] + [{"a": "wait"}] * 4
    )
    sess.maybe_resolve_if_ready()

    assert not _peak_clouds(sess), "the jammed salvo still put clouds up"
    assert not _tagged(sess, "emp"), "the jammed salvo still emitted an EMP frame"


def test_a_jammed_salvo_keeps_its_charge() -> None:
    """§4.9.5 (v1.14) — being jammed costs you the hour, not the missile."""
    sess = _new()
    _arm(sess, "p1", chaff=1)
    _arm(sess, "p2", emp=1)
    _in_orbit(sess, "p1", "p2")
    sess.stash_policy("p1", [{"a": "chaff_flare"}] + [{"a": "wait"}] * 4)
    sess.stash_policy(
        "p2", [{"a": "emp_launch", "at": [[9, 9]]}] + [{"a": "wait"}] * 4
    )
    sess.maybe_resolve_if_ready()

    assert _stock(sess, "p2", "emp") == 1


def test_a_second_flare_inside_your_own_window_is_cancelled() -> None:
    """§4.9.5 (v1.14) — chaff cannot be chained, and the charge is kept."""
    sess = _new()
    _arm(sess, "p1", chaff=2)
    _in_orbit(sess, "p1", "p2")
    sess.stash_policy("p1", [
        {"a": "chaff_flare"},   # h1 — fires
        {"a": "chaff_flare"},   # h2 — inside its own window, must be cancelled
    ] + [{"a": "wait"}] * 4)
    sess.stash_policy("p2", [{"a": "wait"}] * 6)
    sess.maybe_resolve_if_ready()

    assert _stock(sess, "p1", "chaff") == 1, "the chained flare was spent"
    jammed = _hours_tagged(sess, "chaffed")
    assert not jammed or max(jammed) <= W.CHAFF_DURATION_HOURS, (
        f"chaining extended the window to h{max(jammed)}"
    )


# ── EMP ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def two_salvos() -> GameSession:
    """Overlapping salvos on consecutive hours, over a SHORT night.

    The night is two hours because a cloud only lives EMP_CLOUD_HOURS:
    over a full night both have evaporated long before the end, and the
    stacking check would read zero for entirely the wrong reason.
    """
    sess = _new()
    _arm(sess, "p1", emp=2)
    _in_orbit(sess, "p1", "p2")
    sess.stash_policy("p1", [
        {"a": "emp_launch", "at": [[10, 10]]},
        {"a": "emp_launch", "at": [[11, 10]]},
    ])
    sess.stash_policy("p2", [{"a": "wait"}] * 2)
    sess.maybe_resolve_if_ready()
    return sess


def test_two_salvos_leave_two_coexisting_clouds(two_salvos: GameSession) -> None:
    """§4.9.3 — a newer cloud does not replace an older one."""
    assert len(_peak_clouds(two_salvos)) >= 2


def test_clouds_are_published_at_the_canonical_radius(
    two_salvos: GameSession,
) -> None:
    """§4.9.3 — the replay publishes EMP_RADIUS, not a copy of it."""
    radii = [c.get("r") for c in _peak_clouds(two_salvos)]
    assert radii and all(r == W.EMP_RADIUS for r in radii), (
        f"radii on the frame were {radii}, canonical is {W.EMP_RADIUS}"
    )


def test_coexisting_clouds_keep_independent_lifetimes(
    two_salvos: GameSession,
) -> None:
    """§4.9.3 — the second salvo does not refresh the first."""
    left = [c.get("hours_remaining") for c in _peak_clouds(two_salvos)]
    assert len(set(map(str, left))) > 1, (
        f"clouds launched an hour apart share a lifetime: {left}"
    )


def _smothered_at(x: int, y: int) -> bool:
    """Is a harvester standing at (x, y) caught by a blast on (10, 10)?"""
    sess = _new()
    _arm(sess, "p1", emp=1)
    _in_orbit(sess, "p1")
    victim = sess.entities["harvester_p2"]
    victim.x, victim.y = x, y
    sess.stash_policy(
        "p1", [{"a": "emp_launch", "at": [[10, 10]]}, {"a": "wait"}]
    )
    sess.stash_policy("p2", [
        {"a": "step", "unit": "harvester_p2", "to": [x, y - 1]},
        {"a": "wait"},
    ])
    sess.maybe_resolve_if_ready()
    return bool(_tagged(sess, "empd"))


@pytest.mark.parametrize(
    "cell,caught,why",
    [
        ((12, 10), True, f"Manhattan {W.EMP_RADIUS} — on the edge, inside"),
        ((13, 10), False, f"Manhattan {W.EMP_RADIUS + 1} — outside"),
        ((12, 11), False, "Chebyshev 2 but Manhattan 3 — the corner is clear"),
    ],
    ids=["edge-inside", "one-past-the-edge", "diagonal-corner"],
)
def test_the_blast_is_a_manhattan_diamond(cell, caught: bool, why: str) -> None:
    """§4.9.3 — radius is Manhattan, so the blast is a DIAMOND not a square.

    Asserted behaviourally: a harvester on the cell is smothered or it
    is not, which is the only thing the shape actually means to anyone.
    """
    assert _smothered_at(*cell) is caught, why


def test_a_unit_standing_in_the_blast_is_disabled_from_the_launch_hour() -> None:
    """§4.9.3 — a launch at hour N counts for hour N's disable check."""
    sess = _new()
    _arm(sess, "p1", emp=1)
    _in_orbit(sess, "p1")
    victim = sess.entities["harvester_p2"]
    victim.x, victim.y = 10, 10
    sess.stash_policy(
        "p1", [{"a": "emp_launch", "at": [[10, 10]]}] + [{"a": "wait"}] * 4
    )
    sess.stash_policy("p2", [
        {"a": "step", "unit": "harvester_p2", "to": [11, 10]},
        {"a": "step", "unit": "harvester_p2", "to": [12, 10]},
    ] + [{"a": "wait"}] * 3)
    sess.maybe_resolve_if_ready()

    assert 1 in _hours_tagged(sess, "empd")


def _land_into_cloud(delay_hours: int):
    """Drop onto (10,10) ``delay_hours`` after a missile lands there."""
    sess = _new()
    _arm(sess, "p1", emp=1)
    _in_orbit(sess, "p1")
    # The beacon has to sit OUTSIDE the blast but still cover (10,10),
    # or the EMP simply kills the sensor and the drop is refused for fog
    # — which would prove nothing whatever about harvest denial.
    _probe(sess, "p2", 13, 10, "vis")
    sess.stash_policy(
        "p1", [{"a": "emp_launch", "at": [[10, 10]]}] + [{"a": "wait"}] * 5
    )
    sess.stash_policy(
        "p2",
        [{"a": "wait"}] * delay_hours
        + [{"a": "drop", "unit": "harvester_p2", "at": [10, 10]}]
        + [{"a": "wait"}] * 3,
    )
    # Hold the reference: Aurora removes an unrecovered harvester from
    # sess.entities, so looking it up afterwards reports "never landed".
    harvester = sess.entities["harvester_p2"]
    sess.maybe_resolve_if_ready()
    return (harvester.x, harvester.y) == (10, 10), len(harvester.cargo_squares or [])


def test_landing_the_same_hour_a_missile_hits_still_banks_the_parcel() -> None:
    """§4.9.3 (v1.10) — the cloud denies nothing on the hour it forms."""
    landed, _cargo = _land_into_cloud(0)
    assert landed


def test_landing_into_an_already_active_cloud_is_denied_its_harvest() -> None:
    """§4.9.3 (v1.10) — you may land in a standing cloud; you may not reap."""
    landed, cargo = _land_into_cloud(1)
    assert landed, "the cloud should deny the harvest, not the landing"
    assert cargo == 0, f"auto-harvest should be denied, banked {cargo}"


def test_a_probe_inside_the_blast_dies_at_cloud_formation() -> None:
    """§4.9.3 — the salvo sweeps what is already there."""
    sess = _new()
    _arm(sess, "p1", emp=1)
    _in_orbit(sess, "p1", "p2")
    victim = _probe(sess, "p2", 10, 10, "atformation")
    sess.stash_policy(
        "p1", [{"a": "emp_launch", "at": [[10, 10]]}] + [{"a": "wait"}] * 4
    )
    sess.stash_policy("p2", [{"a": "wait"}] * 5)
    sess.maybe_resolve_if_ready()

    assert victim not in sess.entities


def test_a_probe_launched_into_a_standing_cloud_is_swept_on_the_next_tick() -> None:
    """§4.9.3 — and it goes on sweeping what arrives later."""
    sess = _new()
    _arm(sess, "p1", emp=1)
    _in_orbit(sess, "p1", "p2")
    sess.stash_policy(
        "p1", [{"a": "emp_launch", "at": [[10, 10]]}] + [{"a": "wait"}] * 4
    )
    sess.stash_policy("p2", [
        {"a": "wait"},
        {"a": "probe", "at": [10, 11]},
    ] + [{"a": "wait"}] * 3)
    sess.maybe_resolve_if_ready()

    alive = [
        (e.x, e.y) for e in sess.entities.values()
        if e.entity_type == "probe" and e.owner == "p2" and e.x is not None
    ]
    assert (10, 11) not in alive, f"probe survived inside a standing cloud: {alive}"


def test_one_charge_buys_the_whole_salvo() -> None:
    """§4.9.3 — EMP_MISSILES_PER_LAUNCH cells for a single charge."""
    sess = _new()
    _arm(sess, "p1", emp=1)
    _in_orbit(sess, "p1", "p2")
    sess.stash_policy(
        "p1", [{"a": "emp_launch", "at": [[6, 6], [12, 6], [18, 6]]}]
    )
    sess.stash_policy("p2", [{"a": "wait"}])
    sess.maybe_resolve_if_ready()

    assert len(_peak_clouds(sess)) == W.EMP_MISSILES_PER_LAUNCH
    assert _stock(sess, "p1", "emp") == 0


# ── SNAP ─────────────────────────────────────────────────────────────

def test_snap_resolves_above_the_vision_snapshot() -> None:
    """§4.9.4 — kill the beacon and the drop it lit is refused TONIGHT.

    This is the ordering claim with the sharpest edge: SNAP sits above
    the vision snapshot, so destroying the only probe covering a cell
    retracts the landing it was lighting, in the same hour.
    """
    sess = _new()
    _arm(sess, "p1", snap=1)
    _in_orbit(sess, "p1")
    _probe(sess, "p2", 10, 10, "beacon")
    sess.stash_policy(
        "p1", [{"a": "snap_launch", "at": [10, 10]}] + [{"a": "wait"}] * 4
    )
    sess.stash_policy(
        "p2",
        [{"a": "drop", "unit": "harvester_p2", "at": [10, 10]}]
        + [{"a": "wait"}] * 4,
    )
    harvester = sess.entities["harvester_p2"]
    sess.maybe_resolve_if_ready()

    assert (harvester.x, harvester.y) != (10, 10)


def test_a_walk_in_on_the_snap_hour_is_crippled_where_it_stands() -> None:
    """§4.9.4 — the cell stays hot for the rest of the hour."""
    sess = _new()
    _arm(sess, "p1", snap=1)
    _in_orbit(sess, "p1")
    walker = sess.entities["harvester_p2"]
    walker.x, walker.y = 9, 10
    sess.stash_policy(
        "p1", [{"a": "snap_launch", "at": [10, 10]}] + [{"a": "wait"}] * 4
    )
    sess.stash_policy("p2", [
        {"a": "step", "unit": "harvester_p2", "to": [10, 10]},
    ] + [{"a": "wait"}] * 4)
    sess.maybe_resolve_if_ready()

    assert bool(getattr(walker, "damaged", False))
    assert (walker.x, walker.y) == (10, 10), "the step completes, then bites"


def test_the_cell_cools_at_the_next_hour() -> None:
    """§4.9.4 — hot for its hour only; an hour later it is just a cell."""
    sess = _new()
    _arm(sess, "p1", snap=1)
    _in_orbit(sess, "p1")
    walker = sess.entities["harvester_p2"]
    walker.x, walker.y = 9, 10
    sess.stash_policy(
        "p1", [{"a": "snap_launch", "at": [10, 10]}] + [{"a": "wait"}] * 4
    )
    sess.stash_policy("p2", [
        {"a": "wait"},
        {"a": "step", "unit": "harvester_p2", "to": [10, 10]},
    ] + [{"a": "wait"}] * 3)
    sess.maybe_resolve_if_ready()

    assert not bool(getattr(walker, "damaged", False))


def test_a_landing_onto_a_hot_cell_is_turned_back_in_orbit() -> None:
    """§4.9.4 — refused and damaged IN ORBIT, not wrecked on the cell."""
    sess = _new()
    _arm(sess, "p1", snap=1)
    _in_orbit(sess, "p1")
    harvester = sess.entities["harvester_p2"]
    # Independent vision, so the refusal is demonstrably the SNAP and
    # not the fog left behind by the beacon it just destroyed.
    _probe(sess, "p2", 10, 12, "far")
    _probe(sess, "p2", 10, 10, "near")
    sess.stash_policy(
        "p1", [{"a": "snap_launch", "at": [10, 10]}] + [{"a": "wait"}] * 4
    )
    sess.stash_policy(
        "p2",
        [{"a": "drop", "unit": "harvester_p2", "at": [10, 10]}]
        + [{"a": "wait"}] * 4,
    )
    sess.maybe_resolve_if_ready()

    assert (harvester.x, harvester.y) == (None, None)
    assert bool(getattr(harvester, "damaged", False))
