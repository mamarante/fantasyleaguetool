from __future__ import annotations

from nailer.config import NailerConfig
from nailer.reports.byes import build_bye_radar
from tests.conftest import STANDARD_SLOTS, FakeAdapter, make_player


def _config(lookahead=2) -> NailerConfig:
    return NailerConfig(espn=None, yahoo=None, bye_lookahead_weeks=lookahead)


def test_bye_radar_flags_uncovered_te_and_k_crunch_week():
    # Mirrors the project brief's known crunch: TE and K both on bye the
    # same week with no bench replacement at either position.
    my_roster = [
        make_player("te1", "Starting TE", "TE", 9.0, is_starter=True, slot="TE"),
        make_player("k1", "Starting K", "K", 7.0, is_starter=True, slot="K"),
        make_player("rb1", "Starting RB", "RB", 15.0, is_starter=True, slot="RB"),
        make_player("bench_rb", "Bench RB", "RB", 6.0, is_starter=False, slot="BE"),
    ]
    byes = {"te1": 11, "k1": 11}
    adapter = FakeAdapter(week=9, slots=STANDARD_SLOTS, my_players=my_roster, byes=byes)

    warnings = build_bye_radar(adapter, _config(lookahead=2), lookahead_weeks=2)

    flagged = {(w.week, w.player.name) for w in warnings}
    assert (11, "Starting TE") in flagged
    assert (11, "Starting K") in flagged
    # RB has a bench replacement and isn't on bye, so it should never be flagged.
    assert not any(w.player.name == "Starting RB" for w in warnings)


def test_bye_radar_does_not_flag_when_bench_replacement_exists():
    my_roster = [
        make_player("te1", "Starting TE", "TE", 9.0, is_starter=True, slot="TE"),
        make_player("te2", "Bench TE", "TE", 5.0, is_starter=False, slot="BE"),
    ]
    byes = {"te1": 11}
    adapter = FakeAdapter(week=9, slots=STANDARD_SLOTS, my_players=my_roster, byes=byes)

    warnings = build_bye_radar(adapter, _config(lookahead=2), lookahead_weeks=2)
    assert warnings == []


def test_bye_radar_ignores_replacement_also_on_bye_same_week():
    my_roster = [
        make_player("te1", "Starting TE", "TE", 9.0, is_starter=True, slot="TE"),
        make_player("te2", "Bench TE", "TE", 5.0, is_starter=False, slot="BE"),
    ]
    byes = {"te1": 11, "te2": 11}  # both on bye the same week — no real coverage
    adapter = FakeAdapter(week=9, slots=STANDARD_SLOTS, my_players=my_roster, byes=byes)

    warnings = build_bye_radar(adapter, _config(lookahead=2), lookahead_weeks=2)
    assert len(warnings) == 1
    assert warnings[0].player.name == "Starting TE"


def test_bye_radar_respects_lookahead_window():
    my_roster = [make_player("te1", "Starting TE", "TE", 9.0, is_starter=True, slot="TE")]
    byes = {"te1": 15}  # far beyond the lookahead window
    adapter = FakeAdapter(week=9, slots=STANDARD_SLOTS, my_players=my_roster, byes=byes)

    warnings = build_bye_radar(adapter, _config(lookahead=2), lookahead_weeks=2)
    assert warnings == []
