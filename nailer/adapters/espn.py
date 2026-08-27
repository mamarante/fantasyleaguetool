"""ESPN league adapter, backed by the unofficial `espn_api` package
(https://github.com/cwendt94/espn-api). Read-only: only calls that fetch
data are used here (league.box_scores, league.free_agents, team rosters).
Nothing in this module can submit a transaction against ESPN.
"""
from __future__ import annotations

from nailer.adapters.base import LeagueAdapter, LeagueAdapterError
from nailer.cache import Cache
from nailer.config import EspnConfig
from nailer.lineup import SLOT_DISPLAY_ORDER
from nailer.models import InjuryStatus, Matchup, Player, Roster
from nailer.serde import matchup_from_dict, matchup_to_dict, player_from_dict, player_to_dict

UPGRADE_HINT = (
    "ESPN's API changes shape without notice sometimes. "
    "Try `pip install --upgrade espn-api` and re-run. "
    "If that doesn't fix it, the espn-api GitHub wiki/issues are the best place to check "
    "for what changed: https://github.com/cwendt94/espn-api"
)

# Slot labels espn_api reports (see espn_api.football.constant.POSITION_MAP)
# mapped to the internal slot-eligibility names nailer.lineup understands.
_SLOT_LABEL_TO_INTERNAL = {
    "QB": "QB",
    "RB": "RB",
    "WR": "WR",
    "TE": "TE",
    "D/ST": "DST",
    "K": "K",
    "RB/WR/TE": "FLEX",
    "RB/WR": "FLEX_RW",
    "WR/TE": "FLEX_WT",
    "OP": "SUPERFLEX",
}

_BENCH_SLOTS = {"BE", "IR"}
_SEASON_WEEKS = range(1, 19)


def _normalize_position(eligible_slots: list[str], fallback: str) -> str:
    """Derive a clean single position (QB/RB/WR/TE/DST/K) from a player's
    eligible slots rather than trusting espn_api's own `.position`, which
    can pick up a flex/bench label for some players (e.g. team defenses,
    whose 'D/ST' label itself contains a '/').
    """
    labels = set(eligible_slots)
    if "D/ST" in labels:
        return "DST"
    if "QB" in labels:
        return "QB"
    if "K" in labels:
        return "K"
    if "TE" in labels and "RB" not in labels and "WR" not in labels:
        return "TE"
    if "RB" in labels and "WR" not in labels:
        return "RB"
    if "WR" in labels and "RB" not in labels:
        return "WR"
    return fallback or "UNKNOWN"


def _bye_week_from_schedule(schedule: dict) -> int | None:
    """espn_api populates Player.schedule with one entry per week the
    player's pro team plays. The one week 1-18 missing from that dict is
    the bye. If more than one week is missing (early season, schedule not
    fully loaded yet) we can't tell, so return None rather than guess.
    """
    if not schedule:
        return None
    played_weeks = {int(w) for w in schedule.keys()}
    missing = [w for w in _SEASON_WEEKS if w not in played_weeks]
    if len(missing) == 1:
        return missing[0]
    return None


class EspnAdapter(LeagueAdapter):
    league_name = "espn"

    def __init__(self, config: EspnConfig, cache: Cache | None = None):
        self.config = config
        self.cache = cache
        self._league = None

    @property
    def league(self):
        if self._league is None:
            self._league = self._connect()
        return self._league

    def _connect(self):
        try:
            from espn_api.football import League
        except ImportError as e:
            raise LeagueAdapterError(
                "espn-api is not installed. Run `pip install espn-api` (or `pip install -r requirements.txt`)."
            ) from e

        try:
            return League(
                league_id=self.config.league_id,
                year=self.config.year,
                espn_s2=self.config.espn_s2,
                swid=self.config.swid,
            )
        except Exception as e:
            name = type(e).__name__
            if name in ("ESPNAccessDenied", "ESPNInvalidLeague"):
                raise LeagueAdapterError(
                    f"ESPN rejected the request for league {self.config.league_id}: {e}\n"
                    "Double-check ESPN_SWID / ESPN_S2 in .env (they expire — log into espn.com again and "
                    "re-copy the cookies) and the league_id/year in config.yaml."
                ) from e
            raise LeagueAdapterError(f"Failed to connect to ESPN league {self.config.league_id}: {e}\n{UPGRADE_HINT}") from e

    def current_week(self) -> int:
        try:
            return int(self.league.current_week)
        except Exception as e:
            raise LeagueAdapterError(f"Couldn't read the current week from ESPN: {e}\n{UPGRADE_HINT}") from e

    def roster_slots(self) -> list[str]:
        try:
            counts = self.league.settings.position_slot_counts
        except Exception as e:
            raise LeagueAdapterError(f"Couldn't read roster settings from ESPN: {e}\n{UPGRADE_HINT}") from e

        slots: list[str] = []
        for label in SLOT_DISPLAY_ORDER:
            espn_label = next((k for k, v in _SLOT_LABEL_TO_INTERNAL.items() if v == label), None)
            count = counts.get(espn_label, 0) if espn_label else 0
            slots.extend([label] * int(count))
        return slots

    def _find_team(self, team_id: int):
        for team in self.league.teams:
            if team.team_id == team_id:
                return team
        raise LeagueAdapterError(
            f"team_id {team_id} not found in ESPN league {self.config.league_id}. "
            "Check the team_id in config.yaml against your team's URL."
        )

    def _box_player_to_player(self, bp) -> Player:
        position = _normalize_position(getattr(bp, "eligibleSlots", []), getattr(bp, "position", ""))
        return Player(
            player_id=str(bp.playerId),
            name=bp.name,
            position=position,
            pro_team=getattr(bp, "proTeam", ""),
            projected_points=round(float(getattr(bp, "projected_points", 0) or 0), 2),
            actual_points=round(float(getattr(bp, "points", 0) or 0), 2),
            injury_status=InjuryStatus.from_raw(getattr(bp, "injuryStatus", None)),
            eligible_slots=list(getattr(bp, "eligibleSlots", [])),
            is_starter=getattr(bp, "slot_position", "BE") not in _BENCH_SLOTS,
            slot=getattr(bp, "slot_position", None),
            percent_owned=getattr(bp, "percent_owned", None),
        )

    def _box_score_for(self, week: int, team_id: int):
        try:
            box_scores = self.league.box_scores(week=week)
        except Exception as e:
            raise LeagueAdapterError(f"Couldn't fetch box scores for week {week}: {e}\n{UPGRADE_HINT}") from e

        for bs in box_scores:
            home_id = getattr(bs.home_team, "team_id", None)
            away_id = getattr(bs.away_team, "team_id", None)
            if team_id in (home_id, away_id):
                return bs, (home_id == team_id)
        raise LeagueAdapterError(f"No matchup found for team_id {team_id} in week {week}.")

    def _roster_from_lineup(self, team, lineup, week: int) -> Roster:
        players = [self._box_player_to_player(p) for p in lineup]
        return Roster(
            league=self.league_name,
            team_id=str(team.team_id),
            team_name=team.team_name,
            week=week,
            players=players,
        )

    def _fetch_matchup_uncached(self, week: int) -> Matchup:
        bs, is_home = self._box_score_for(week, self.config.team_id)
        my_team = bs.home_team if is_home else bs.away_team
        my_lineup = bs.home_lineup if is_home else bs.away_lineup
        opp_team = bs.away_team if is_home else bs.home_team
        opp_lineup = bs.away_lineup if is_home else bs.home_lineup

        return Matchup(
            league=self.league_name,
            week=week,
            team_id=str(my_team.team_id),
            team_name=my_team.team_name,
            opponent_id=str(opp_team.team_id) if opp_team else "",
            opponent_name=opp_team.team_name if opp_team else "BYE",
            my_roster=self._roster_from_lineup(my_team, my_lineup, week),
            opp_roster=self._roster_from_lineup(opp_team, opp_lineup, week) if opp_team else Roster(
                league=self.league_name, team_id="", team_name="BYE", week=week, players=[]
            ),
        )

    def get_matchup(self, week: int | None = None) -> Matchup:
        week = week or self.current_week()
        if self.cache:
            params = {"team_id": self.config.team_id, "week": week}
            d = self.cache.get_or_fetch(
                self.league_name, "matchup", params, lambda: matchup_to_dict(self._fetch_matchup_uncached(week))
            )
            return matchup_from_dict(d)
        return self._fetch_matchup_uncached(week)

    def get_roster(self, week: int | None = None) -> Roster:
        week = week or self.current_week()
        return self.get_matchup(week).my_roster

    def get_opponent_roster(self, week: int | None = None) -> Roster:
        week = week or self.current_week()
        return self.get_matchup(week).opp_roster

    def _fetch_free_agents_uncached(self, week: int, espn_position: str | None, limit: int) -> list[Player]:
        try:
            free_agents = self.league.free_agents(week=week, size=limit, position=espn_position)
        except Exception as e:
            raise LeagueAdapterError(f"Couldn't fetch ESPN free agents: {e}\n{UPGRADE_HINT}") from e

        players = [self._box_player_to_player(p) for p in free_agents]
        players.sort(key=lambda p: p.projected_points, reverse=True)
        return players

    def get_free_agents(self, position: str | None = None, limit: int = 50) -> list[Player]:
        week = self.current_week()
        espn_position = None
        if position:
            reverse = {v: k for k, v in _SLOT_LABEL_TO_INTERNAL.items() if k in ("QB", "RB", "WR", "TE", "K")}
            espn_position = reverse.get(position.upper(), position.upper())

        if self.cache:
            params = {"week": week, "position": espn_position, "limit": limit}
            d = self.cache.get_or_fetch(
                self.league_name,
                "free_agents",
                params,
                lambda: [player_to_dict(p) for p in self._fetch_free_agents_uncached(week, espn_position, limit)],
            )
            return [player_from_dict(p) for p in d]
        return self._fetch_free_agents_uncached(week, espn_position, limit)

    def get_byes(self) -> dict[str, int]:
        team = self._find_team(self.config.team_id)
        byes: dict[str, int] = {}
        for p in team.roster:
            bye = _bye_week_from_schedule(getattr(p, "schedule", {}))
            if bye is not None:
                byes[str(p.playerId)] = bye
        return byes
