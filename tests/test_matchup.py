from __future__ import annotations

from nailer.config import NailerConfig
from nailer.reports.matchup import build_matchup_preview
from tests.conftest import STANDARD_SLOTS, FakeAdapter, make_player


def _config() -> NailerConfig:
    return NailerConfig(espn=None, yahoo=None)


def _full_roster(qb, rb1, rb2, wr1, wr2, te, dst, k):
    return [
        make_player("qb", "QB", "QB", qb),
        make_player("rb1", "RB1", "RB", rb1),
        make_player("rb2", "RB2", "RB", rb2),
        make_player("wr1", "WR1", "WR", wr1),
        make_player("wr2", "WR2", "WR", wr2),
        make_player("te", "TE", "TE", te),
        make_player("dst", "DST", "DST", dst),
        make_player("k", "K", "K", k),
    ]


def test_matchup_breakdown_flags_losing_positions_and_totals():
    my_players = _full_roster(qb=20, rb1=15, rb2=10, wr1=12, wr2=8, te=6, dst=5, k=4)
    opp_players = _full_roster(qb=18, rb1=10, rb2=9, wr1=20, wr2=15, te=6, dst=5, k=4)

    adapter = FakeAdapter(week=5, slots=STANDARD_SLOTS, my_players=my_players, opp_players=opp_players)
    preview = build_matchup_preview(adapter, _config(), week=5)

    assert preview.my_projected == sum(p.projected_points for p in my_players)
    assert preview.opp_projected == sum(p.projected_points for p in opp_players)
    assert "WR" in preview.losing_positions
    assert "QB" not in preview.losing_positions


def test_matchup_suggests_waiver_gap_closer_for_losing_position():
    my_players = _full_roster(qb=20, rb1=15, rb2=10, wr1=8, wr2=6, te=6, dst=5, k=4)
    opp_players = _full_roster(qb=18, rb1=10, rb2=9, wr1=20, wr2=15, te=6, dst=5, k=4)
    free_agents = [
        make_player("fa_wr_great", "Great Waiver WR", "WR", 25.0),
        make_player("fa_wr_meh", "Meh Waiver WR", "WR", 3.0),  # worse than my worst WR starter, shouldn't be suggested
    ]

    adapter = FakeAdapter(week=5, slots=STANDARD_SLOTS, my_players=my_players, opp_players=opp_players)
    preview = build_matchup_preview(adapter, _config(), week=5, free_agents=free_agents)

    assert "WR" in preview.losing_positions
    assert preview.gap_closers["WR"].name == "Great Waiver WR"
