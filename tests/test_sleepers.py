from __future__ import annotations

from nailer.config import NailerConfig
from nailer.reports.sleepers import build_sleeper_report, detect_trending
from tests.conftest import STANDARD_SLOTS, FakeAdapter, make_player


def _config(min_pct=0.25, min_avg=3.0) -> NailerConfig:
    return NailerConfig(espn=None, yahoo=None, sleeper_min_pct_above_avg=min_pct, sleeper_min_season_avg=min_avg)


def test_detect_trending_flags_projection_notably_above_season_average():
    players = [
        make_player("hot", "Hot Player", "RB", projected_points=15.0, season_avg_projected=10.0),  # +50%
        make_player("steady", "Steady Player", "RB", projected_points=10.5, season_avg_projected=10.0),  # +5%, below threshold
        make_player("no_avg", "No Avg Data", "RB", projected_points=20.0, season_avg_projected=None),  # excluded
    ]
    trending = detect_trending(players, min_pct_above_avg=0.25, min_season_avg=3.0)

    names = [t.player.name for t in trending]
    assert names == ["Hot Player"]
    assert trending[0].pct_above_avg == 0.5


def test_detect_trending_filters_out_low_volume_noise():
    # A kicker going from a 2.0 season avg to 3.0 projected is a 50% jump
    # but not meaningful — min_season_avg should filter it out.
    players = [make_player("k1", "Noisy Kicker", "K", projected_points=3.0, season_avg_projected=2.0)]
    trending = detect_trending(players, min_pct_above_avg=0.25, min_season_avg=3.0)
    assert trending == []


def test_build_sleeper_report_splits_bench_and_waiver_trending():
    my_roster = [
        make_player("starter", "Starter RB", "RB", projected_points=15.0, is_starter=True, slot="RB", season_avg_projected=14.0),
        make_player("bench_hot", "Bench Riser", "WR", projected_points=12.0, is_starter=False, slot="BE", season_avg_projected=6.0),
    ]
    free_agents = [
        make_player("fa_hot", "Waiver Riser", "RB", projected_points=10.0, season_avg_projected=5.0),
        make_player("fa_cold", "Flat Free Agent", "RB", projected_points=5.2, season_avg_projected=5.0),
    ]
    adapter = FakeAdapter(week=3, slots=STANDARD_SLOTS, my_players=my_roster, free_agents=free_agents)
    report = build_sleeper_report(adapter, _config(), week=3)

    assert [t.player.name for t in report.bench_trending] == ["Bench Riser"]
    assert [t.player.name for t in report.waiver_trending] == ["Waiver Riser"]


def test_build_sleeper_report_empty_when_nothing_trending():
    my_roster = [make_player("bench", "Flat Bench", "WR", projected_points=8.0, season_avg_projected=8.0)]
    adapter = FakeAdapter(week=3, slots=STANDARD_SLOTS, my_players=my_roster)
    report = build_sleeper_report(adapter, _config(), week=3)

    assert report.bench_trending == []
    assert report.waiver_trending == []
