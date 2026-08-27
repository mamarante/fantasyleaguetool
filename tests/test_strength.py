from __future__ import annotations

from nailer.config import NailerConfig
from nailer.reports.strength import build_strength_report
from tests.conftest import STANDARD_SLOTS, FakeAdapter, make_player


def _config() -> NailerConfig:
    return NailerConfig(espn=None, yahoo=None)


def _team(prefix: str, name: str, qb_pts: float) -> list:
    return [
        make_player(f"{prefix}_qb", f"{name} QB", "QB", qb_pts),
        make_player(f"{prefix}_rb", f"{name} RB", "RB", 10.0),
        make_player(f"{prefix}_wr", f"{name} WR", "WR", 8.0),
        make_player(f"{prefix}_te", f"{name} TE", "TE", 6.0),
        make_player(f"{prefix}_dst", f"{name} DST", "DST", 5.0),
        make_player(f"{prefix}_k", f"{name} K", "K", 4.0),
    ]


def test_strength_report_ranks_teams_and_computes_league_average():
    from nailer.models import Roster

    my_players = _team("me", "Me", qb_pts=20.0)  # total 53
    team_b = _team("b", "Team B", qb_pts=30.0)  # total 63 — strongest
    team_c = _team("c", "Team C", qb_pts=10.0)  # total 43 — weakest

    all_rosters = [
        Roster(league="fake", team_id="1", team_name="My Team", week=4, players=my_players),
        Roster(league="fake", team_id="2", team_name="Team B", week=4, players=team_b),
        Roster(league="fake", team_id="3", team_name="Team C", week=4, players=team_c),
    ]

    adapter = FakeAdapter(week=4, slots=STANDARD_SLOTS, my_players=my_players, all_team_rosters=all_rosters)
    report = build_strength_report(adapter, _config(), week=4)

    assert report.my_team.projected_total == 53.0
    assert report.league_average == round((53.0 + 63.0 + 43.0) / 3, 2)
    assert report.diff_from_average == round(53.0 - report.league_average, 2)
    assert report.rank == 2  # Team B (63) > Me (53) > Team C (43)
    assert [t.team_name for t in report.all_teams] == ["Team B", "My Team", "Team C"]
