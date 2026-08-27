from __future__ import annotations

from nailer.lineup import optimize_lineup
from tests.conftest import STANDARD_SLOTS, make_player


def test_optimizer_fills_dedicated_slots_with_best_available():
    players = [
        make_player("qb1", "Good QB", "QB", 22.0),
        make_player("qb2", "Backup QB", "QB", 15.0),
        make_player("rb1", "RB One", "RB", 18.0),
        make_player("rb2", "RB Two", "RB", 14.0),
        make_player("rb3", "RB Three", "RB", 8.0),
        make_player("wr1", "WR One", "WR", 16.0),
        make_player("wr2", "WR Two", "WR", 13.0),
        make_player("wr3", "WR Three", "WR", 9.0),
        make_player("te1", "TE One", "TE", 11.0),
        make_player("dst1", "Defense", "DST", 7.0),
        make_player("k1", "Kicker", "K", 8.0),
    ]

    lineup = optimize_lineup(players, STANDARD_SLOTS)
    starter_names = {a.slot: a.player.name for a in lineup.assignments}

    assert starter_names["QB"] == "Good QB"
    assert starter_names["DST"] == "Defense"
    assert starter_names["K"] == "Kicker"
    # Two RB slots take the top two RBs; the flex takes the next best
    # RB/WR/TE regardless of position (RB Three at 8.0 vs WR Three at 9.0).
    assert starter_names["FLEX"] == "WR Three"


def test_optimizer_maximizes_total_points_over_greedy_by_position():
    # A greedy "fill RB slots with RBs, WR slots with WRs" approach would
    # miss that RB3 (12) belongs in the flex ahead of WR2 (9), since WR1
    # alone already covers one WR slot and RB1/RB2 cover both RB slots.
    players = [
        make_player("qb1", "QB", "QB", 20.0),
        make_player("rb1", "RB1", "RB", 20.0),
        make_player("rb2", "RB2", "RB", 15.0),
        make_player("rb3", "RB3", "RB", 12.0),
        make_player("wr1", "WR1", "WR", 18.0),
        make_player("wr2", "WR2", "WR", 9.0),
        make_player("te1", "TE1", "TE", 10.0),
        make_player("dst1", "DST", "DST", 5.0),
        make_player("k1", "K", "K", 6.0),
    ]
    lineup = optimize_lineup(players, STANDARD_SLOTS)
    assert lineup.total_projected == 20 + 20 + 15 + 18 + 9 + 10 + 5 + 6 + 12  # includes RB3 in flex
    starters = {a.player.name for a in lineup.assignments if a.player}
    assert "RB3" in starters
    assert "WR2" in starters  # only 2 WR-eligible non-flex slots needed; both WRs still fit (WR + flex taken by RB3)


def test_unfillable_slot_is_left_empty():
    players = [make_player("qb1", "Only QB", "QB", 15.0)]
    lineup = optimize_lineup(players, STANDARD_SLOTS)
    slot_map = {a.slot: a.player for a in lineup.assignments}
    assert slot_map["QB"].name == "Only QB"
    assert slot_map["RB"] is None
    assert slot_map["K"] is None


def test_close_flex_call_is_flagged_like_odunze_vs_btj():
    # Mirrors the project brief's example: two flex-eligible WRs whose
    # projections are close enough that the choice deserves a second look.
    players = [
        make_player("qb1", "QB", "QB", 20.0),
        make_player("rb1", "RB1", "RB", 18.0),
        make_player("rb2", "RB2", "RB", 16.0),
        make_player("wr1", "WR1", "WR", 14.0),
        make_player("wr2", "WR2", "WR", 13.0),
        make_player("odunze", "Odunze", "WR", 11.0),
        make_player("btj", "BTJ", "WR", 10.2),
        make_player("te1", "TE1", "TE", 9.0),
        make_player("dst1", "DST", "DST", 5.0),
        make_player("k1", "K", "K", 6.0),
    ]
    lineup = optimize_lineup(players, STANDARD_SLOTS, close_call_margin=2.5)

    flex_slot = next(a for a in lineup.assignments if a.slot == "FLEX")
    assert flex_slot.player.name == "Odunze"

    close_calls = {cc.slot: cc for cc in lineup.close_calls}
    assert "FLEX" in close_calls
    assert close_calls["FLEX"].started.name == "Odunze"
    assert close_calls["FLEX"].bench_alternative.name == "BTJ"
    assert close_calls["FLEX"].margin == 0.8


def test_blowout_flex_is_not_flagged_as_close():
    players = [
        make_player("qb1", "QB", "QB", 20.0),
        make_player("rb1", "RB1", "RB", 18.0),
        make_player("rb2", "RB2", "RB", 16.0),
        make_player("wr1", "WR1", "WR", 14.0),
        make_player("wr2", "WR2", "WR", 13.0),
        make_player("star", "Star WR", "WR", 20.0),
        make_player("scrub", "Scrub WR", "WR", 2.0),
        make_player("te1", "TE1", "TE", 9.0),
        make_player("dst1", "DST", "DST", 5.0),
        make_player("k1", "K", "K", 6.0),
    ]
    lineup = optimize_lineup(players, STANDARD_SLOTS, close_call_margin=2.5)
    assert lineup.close_calls == []
