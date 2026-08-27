from __future__ import annotations

from nailer.config import NailerConfig
from nailer.models import WatchlistEntry
from nailer.reports.waivers import build_waiver_report
from tests.conftest import STANDARD_SLOTS, FakeAdapter, make_player


def _config(watchlist=None) -> NailerConfig:
    return NailerConfig(espn=None, yahoo=None, watchlist=watchlist or [])


def test_waivers_only_lists_free_agents_that_beat_worst_bench_player():
    my_roster = [
        make_player("qb1", "Starter QB", "QB", 20.0, is_starter=True, slot="QB"),
        make_player("rb1", "Starter RB", "RB", 15.0, is_starter=True, slot="RB"),
        make_player("worst_rb", "Worst Bench RB", "RB", 4.0, is_starter=False, slot="BE"),
        make_player("worst_wr", "Worst Bench WR", "WR", 6.0, is_starter=False, slot="BE"),
    ]
    free_agents = [
        make_player("fa1", "Better RB", "RB", 7.0),
        make_player("fa2", "Worse RB", "RB", 3.0),  # below threshold, excluded
        make_player("fa3", "Better WR", "WR", 8.0),
    ]
    adapter = FakeAdapter(week=3, slots=STANDARD_SLOTS, my_players=my_roster, free_agents=free_agents)
    report = build_waiver_report(adapter, _config(), week=3)

    by_pos = {pw.position: pw for pw in report.by_position}
    assert [p.name for p in by_pos["RB"].candidates] == ["Better RB"]
    assert [p.name for p in by_pos["WR"].candidates] == ["Better WR"]


def test_watchlist_flags_handcuff_free_agent_like_jordan_mason():
    my_roster = [make_player("aj", "Aaron Jones", "RB", 14.0, is_starter=True, slot="RB")]
    free_agents = [
        make_player("jm", "Jordan Mason", "RB", 5.0),
        make_player("irrelevant", "Random Waiver RB", "RB", 5.0),
    ]
    watchlist = [WatchlistEntry(name="Jordan Mason", league="espn", reason="Handcuff for Aaron Jones")]
    adapter = FakeAdapter(week=3, slots=STANDARD_SLOTS, my_players=my_roster, free_agents=free_agents)
    adapter.league_name = "espn"

    report = build_waiver_report(adapter, _config(watchlist), week=3)

    hit_names = {hit.player.name for hit in report.watchlist_hits}
    assert "Jordan Mason" in hit_names
    assert "Random Waiver RB" not in hit_names


def test_watchlist_entry_scoped_to_other_league_does_not_match():
    my_roster = [make_player("aj", "Aaron Jones", "RB", 14.0, is_starter=True, slot="RB")]
    free_agents = [make_player("jm", "Jordan Mason", "RB", 5.0)]
    watchlist = [WatchlistEntry(name="Jordan Mason", league="yahoo", reason="Wrong league")]
    adapter = FakeAdapter(week=3, slots=STANDARD_SLOTS, my_players=my_roster, free_agents=free_agents)
    adapter.league_name = "espn"

    report = build_waiver_report(adapter, _config(watchlist), week=3)
    assert report.watchlist_hits == []


def test_top_overall_ranks_across_positions():
    my_roster = [
        make_player("worst_rb", "Worst Bench RB", "RB", 4.0, is_starter=False, slot="BE"),
        make_player("worst_wr", "Worst Bench WR", "WR", 4.0, is_starter=False, slot="BE"),
    ]
    free_agents = [
        make_player("fa1", "Top Add", "WR", 15.0),
        make_player("fa2", "Second Add", "RB", 12.0),
        make_player("fa3", "Third Add", "WR", 9.0),
    ]
    adapter = FakeAdapter(week=1, slots=STANDARD_SLOTS, my_players=my_roster, free_agents=free_agents)
    report = build_waiver_report(adapter, _config(), week=1)

    top = report.top_overall(2)
    assert [p.name for p in top] == ["Top Add", "Second Add"]
