"""Shared data model used by every league adapter and report.

Both ESPN and Yahoo adapters translate their native API responses into
these types so the report logic (lineup optimizer, waiver scanner, bye
radar, matchup preview) is written once and works for either league.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class InjuryStatus(str, Enum):
    HEALTHY = "ACTIVE"
    QUESTIONABLE = "Q"
    DOUBTFUL = "D"
    OUT = "O"
    IR = "IR"
    BYE = "BYE"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_raw(cls, raw: str | None) -> InjuryStatus:
        if not raw:
            return cls.HEALTHY
        raw = raw.upper().strip()
        aliases = {
            "ACTIVE": cls.HEALTHY,
            "HEALTHY": cls.HEALTHY,
            "QUESTIONABLE": cls.QUESTIONABLE,
            "Q": cls.QUESTIONABLE,
            "DOUBTFUL": cls.DOUBTFUL,
            "D": cls.DOUBTFUL,
            "OUT": cls.OUT,
            "O": cls.OUT,
            "INJURY_RESERVE": cls.IR,
            "IR": cls.IR,
            "BYE": cls.BYE,
            "BYE_WEEK": cls.BYE,
        }
        return aliases.get(raw, cls.UNKNOWN)


@dataclass
class Player:
    """A single NFL player as seen from one league (rostered or a free agent)."""

    player_id: str
    name: str
    position: str  # QB, RB, WR, TE, DST, K
    pro_team: str = ""
    projected_points: float = 0.0
    actual_points: float | None = None
    injury_status: InjuryStatus = InjuryStatus.HEALTHY
    bye_week: int | None = None
    eligible_slots: list[str] = field(default_factory=list)
    is_starter: bool = False
    slot: str | None = None  # current lineup slot, if rostered by a team
    percent_owned: float | None = None
    season_avg_projected: float | None = None  # season-to-date avg projected points; None if not available

    def eligible_for(self, slot_positions: set[str]) -> bool:
        return self.position in slot_positions


@dataclass
class Roster:
    """One team's full set of rostered players for a given week."""

    league: str
    team_id: str
    team_name: str
    week: int
    players: list[Player] = field(default_factory=list)

    @property
    def starters(self) -> list[Player]:
        return [p for p in self.players if p.is_starter]

    @property
    def bench(self) -> list[Player]:
        return [p for p in self.players if not p.is_starter]

    def worst_bench_by_position(self) -> dict[str, float]:
        """Lowest projected points among bench players, per position."""
        worst: dict[str, float] = {}
        for p in self.bench:
            if p.position not in worst or p.projected_points < worst[p.position]:
                worst[p.position] = p.projected_points
        return worst


@dataclass
class Matchup:
    """My team vs. this week's opponent, in one league."""

    league: str
    week: int
    team_id: str
    team_name: str
    opponent_id: str
    opponent_name: str
    my_roster: Roster
    opp_roster: Roster

    @property
    def my_projected(self) -> float:
        return sum(p.projected_points for p in self.my_roster.starters)

    @property
    def opp_projected(self) -> float:
        return sum(p.projected_points for p in self.opp_roster.starters)


@dataclass
class WatchlistEntry:
    name: str
    league: str | None = None  # None = watch across all leagues
    reason: str = ""

    def matches(self, player: Player, league: str) -> bool:
        if self.league and self.league != league:
            return False
        return self.name.lower() in player.name.lower()
