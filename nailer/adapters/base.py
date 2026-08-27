"""Common interface both league adapters implement.

Report logic (lineup optimizer, waiver scanner, bye radar, matchup preview)
is written once against this interface and never touches espn_api or yfpy
directly. This adapter layer is READ-ONLY by design: there is intentionally
no set_lineup / claim_waiver / propose_trade method anywhere in this
codebase. See the project brief: League Nailer never manages your roster
for you.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from nailer.models import Matchup, Player, Roster


class LeagueAdapterError(RuntimeError):
    """Raised when a league adapter can't fulfill a request (auth, API
    shape change, missing data, etc). CLI code catches this and prints a
    friendly message instead of a raw traceback.
    """


class LeagueAdapter(ABC):
    """Read-only view onto one fantasy football league."""

    league_name: str  # "espn" or "yahoo", used as a key in reports/config

    @abstractmethod
    def current_week(self) -> int:
        """The league's current NFL week."""

    @abstractmethod
    def roster_slots(self) -> list[str]:
        """Starting lineup slot names in roster order, e.g.
        ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DST", "K"].
        Does not include bench/IR slots.
        """

    @abstractmethod
    def get_roster(self, week: int | None = None) -> Roster:
        """My roster (starters + bench) for the given week (default: current)."""

    @abstractmethod
    def get_opponent_roster(self, week: int | None = None) -> Roster:
        """This week's (or given week's) opponent roster."""

    @abstractmethod
    def get_matchup(self, week: int | None = None) -> Matchup:
        """My team vs. this week's opponent."""

    @abstractmethod
    def get_free_agents(self, position: str | None = None, limit: int = 50) -> list[Player]:
        """Available free agents / waiver-wire players, sorted by projected points desc."""

    @abstractmethod
    def get_byes(self) -> dict[str, int]:
        """Map of player_id -> bye week, for every player on my roster."""

    @abstractmethod
    def get_all_team_rosters(self, week: int | None = None) -> list[Roster]:
        """Every team's roster in the league for the given week (default:
        current), mine included. Used for league-wide comparisons like the
        rest-of-season strength view.
        """
