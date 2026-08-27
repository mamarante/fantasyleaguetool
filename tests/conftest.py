from __future__ import annotations

import pytest

from nailer.adapters.base import LeagueAdapter
from nailer.models import InjuryStatus, Matchup, Player, Roster

STANDARD_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DST", "K"]


def make_player(
    player_id: str,
    name: str,
    position: str,
    projected_points: float,
    pro_team: str = "XX",
    is_starter: bool = False,
    slot: str | None = None,
    injury_status: InjuryStatus = InjuryStatus.HEALTHY,
    bye_week: int | None = None,
    season_avg_projected: float | None = None,
) -> Player:
    return Player(
        player_id=player_id,
        name=name,
        position=position,
        pro_team=pro_team,
        projected_points=projected_points,
        injury_status=injury_status,
        bye_week=bye_week,
        is_starter=is_starter,
        slot=slot,
        season_avg_projected=season_avg_projected,
    )


class FakeAdapter(LeagueAdapter):
    """Minimal in-memory LeagueAdapter for exercising report logic without
    hitting ESPN or Yahoo."""

    league_name = "fake"

    def __init__(self, week, slots, my_players, opp_players=None, free_agents=None, byes=None, all_team_rosters=None):
        self._week = week
        self._slots = slots
        self._my_players = my_players
        self._opp_players = opp_players or []
        self._free_agents = free_agents or []
        self._byes = byes or {}
        self._all_team_rosters = all_team_rosters

    def current_week(self) -> int:
        return self._week

    def roster_slots(self) -> list[str]:
        return self._slots

    def get_roster(self, week=None) -> Roster:
        return Roster(league=self.league_name, team_id="1", team_name="My Team", week=week or self._week, players=self._my_players)

    def get_opponent_roster(self, week=None) -> Roster:
        return Roster(league=self.league_name, team_id="2", team_name="Opponent", week=week or self._week, players=self._opp_players)

    def get_matchup(self, week=None) -> Matchup:
        return Matchup(
            league=self.league_name,
            week=week or self._week,
            team_id="1",
            team_name="My Team",
            opponent_id="2",
            opponent_name="Opponent",
            my_roster=self.get_roster(week),
            opp_roster=self.get_opponent_roster(week),
        )

    def get_free_agents(self, position=None, limit=50) -> list[Player]:
        pool = self._free_agents
        if position:
            pool = [p for p in pool if p.position == position]
        return sorted(pool, key=lambda p: p.projected_points, reverse=True)[:limit]

    def get_byes(self) -> dict[str, int]:
        return self._byes

    def get_all_team_rosters(self, week=None) -> list[Roster]:
        if self._all_team_rosters is not None:
            return self._all_team_rosters
        return [self.get_roster(week), self.get_opponent_roster(week)]


@pytest.fixture
def standard_slots():
    return list(STANDARD_SLOTS)
