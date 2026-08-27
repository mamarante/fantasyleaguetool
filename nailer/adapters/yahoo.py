"""Yahoo league adapter, backed by `yfpy` (https://github.com/uberfastman/yfpy),
which wraps Yahoo's official (OAuth2) Fantasy Sports REST API. Read-only:
only GET-style query methods are used here. Nothing in this module can
submit a transaction against Yahoo.

IMPORTANT LIMITATION: Yahoo's public Fantasy API does not expose true
per-player weekly point PROJECTIONS the way ESPN's does — only team-level
projected totals and player-level actual results are available. As a
stand-in, `projected_points` for Yahoo players is each player's season
average points-per-game so far (season total / games played), rounded to
2 decimals. It is a reasonable "expected value" proxy for start/sit and
waiver comparisons, but it is NOT a matchup-specific projection the way
the ESPN numbers are. This is flagged in report output; see README.
"""
from __future__ import annotations

from pathlib import Path

from nailer.adapters.base import LeagueAdapter, LeagueAdapterError
from nailer.cache import Cache
from nailer.config import YahooConfig
from nailer.lineup import SLOT_DISPLAY_ORDER
from nailer.models import InjuryStatus, Matchup, Player, Roster

UPGRADE_HINT = (
    "Yahoo's API wrapper occasionally lags behind API changes. "
    "Try `pip install --upgrade yfpy` and re-run. "
    "If that doesn't fix it, check https://github.com/uberfastman/yfpy for known issues."
)

_YAHOO_SLOT_TO_INTERNAL = {
    "QB": "QB",
    "RB": "RB",
    "WR": "WR",
    "TE": "TE",
    "K": "K",
    "DEF": "DST",
    "W/R/T": "FLEX",
    "W/T": "FLEX_WT",
    "R/W": "FLEX_RW",
    "Q/W/R/T": "SUPERFLEX",
    "OP": "SUPERFLEX",
}
_BENCH_SLOTS = {"BN", "IR", "IR+"}


def _normalize_position(raw_position: str) -> str:
    return "DST" if raw_position == "DEF" else raw_position


class YahooAdapter(LeagueAdapter):
    league_name = "yahoo"

    def __init__(self, config: YahooConfig, cache: Cache | None = None):
        self.config = config
        self.cache = cache
        self._query = None
        self._settings = None
        self._current_week: int | None = None
        self._projection_cache: dict[str, float] = {}

    @property
    def query(self):
        if self._query is None:
            self._query = self._connect()
        return self._query

    def _connect(self):
        try:
            from yfpy.query import YahooFantasySportsQuery
        except ImportError as e:
            raise LeagueAdapterError(
                "yfpy is not installed. Run `pip install yfpy` (or `pip install -r requirements.txt`)."
            ) from e

        try:
            return YahooFantasySportsQuery(
                league_id=self.config.league_id,
                game_code=self.config.game_key or "nfl",
                yahoo_consumer_key=self.config.consumer_key,
                yahoo_consumer_secret=self.config.consumer_secret,
                env_file_location=Path.cwd(),
                save_token_data_to_env_file=True,
            )
        except Exception as e:
            raise LeagueAdapterError(
                f"Failed to connect to Yahoo league {self.config.league_id}: {e}\n"
                "Double-check YAHOO_CONSUMER_KEY / YAHOO_CONSUMER_SECRET in .env and that your Yahoo developer "
                "app has Fantasy Sports read permission. The first run opens a browser to authorize; "
                "after that, tokens are cached and this should be silent.\n" + UPGRADE_HINT
            ) from e

    def current_week(self) -> int:
        if self._current_week is None:
            try:
                self._current_week = int(self.query.get_league_metadata().current_week)
            except Exception as e:
                raise LeagueAdapterError(f"Couldn't read the current week from Yahoo: {e}\n{UPGRADE_HINT}") from e
        return self._current_week

    def _settings_cached(self):
        if self._settings is None:
            try:
                self._settings = self.query.get_league_settings()
            except Exception as e:
                raise LeagueAdapterError(f"Couldn't read league settings from Yahoo: {e}\n{UPGRADE_HINT}") from e
        return self._settings

    def roster_slots(self) -> list[str]:
        settings = self._settings_cached()
        counts: dict[str, int] = {}
        for rp in settings.roster_positions:
            if int(getattr(rp, "is_bench", 0)):
                continue
            if rp.position in ("BN", "IR", "IR+"):
                continue
            internal = _YAHOO_SLOT_TO_INTERNAL.get(rp.position)
            if internal:
                counts[internal] = counts.get(internal, 0) + int(rp.count)

        slots: list[str] = []
        for label in SLOT_DISPLAY_ORDER:
            slots.extend([label] * counts.get(label, 0))
        return slots

    def _yahoo_player_to_player(self, yp, week: int) -> Player:
        eligible = list(getattr(yp, "eligible_positions", []) or [])
        position = _normalize_position(getattr(yp, "primary_position", "") or getattr(yp, "display_position", ""))
        player_key = getattr(yp, "player_key", "") or str(getattr(yp, "player_id", ""))
        selected_slot = getattr(yp, "selected_position_value", "") or None

        return Player(
            player_id=str(getattr(yp, "player_id", player_key)),
            name=getattr(yp, "full_name", "") or player_key,
            position=position,
            pro_team=getattr(yp, "editorial_team_abbr", ""),
            projected_points=self._estimate_projection(player_key, week),
            actual_points=round(float(getattr(yp, "player_points_value", 0) or 0), 2),
            injury_status=InjuryStatus.from_raw(getattr(yp, "status", None)),
            bye_week=getattr(yp, "bye", None),
            eligible_slots=[_normalize_position(e) for e in eligible],
            is_starter=selected_slot not in _BENCH_SLOTS if selected_slot else False,
            slot=selected_slot,
            percent_owned=getattr(yp, "percent_owned_value", None),
        )

    def _estimate_projection(self, player_key: str, week: int) -> float:
        """Season average points/game so far, as a projection proxy (see
        module docstring). Cached per player_key for the life of this
        adapter instance since it's an expensive one-call-per-player fetch.
        """
        if not player_key:
            return 0.0
        if player_key in self._projection_cache:
            return self._projection_cache[player_key]

        def fetch():
            try:
                season_player = self.query.get_player_stats_for_season(player_key)
                total = float(getattr(season_player, "player_points_value", 0) or 0)
            except Exception:
                return 0.0
            games = max(week - 1, 1)
            return round(total / games, 2)

        if self.cache:
            value = self.cache.get_or_fetch(self.league_name, "player_season_avg", {"player_key": player_key, "week": week}, fetch)
        else:
            value = fetch()
        self._projection_cache[player_key] = value
        return value

    def _team_key(self, team_id: int) -> str:
        return f"{self.query.get_league_key()}.t.{team_id}"

    def get_roster(self, week: int | None = None) -> Roster:
        week = week or self.current_week()
        try:
            players_raw = self.query.get_team_roster_player_stats_by_week(self.config.team_id, week)
        except Exception as e:
            raise LeagueAdapterError(f"Couldn't fetch Yahoo roster for week {week}: {e}\n{UPGRADE_HINT}") from e

        players = [self._yahoo_player_to_player(p, week) for p in players_raw]
        return Roster(league=self.league_name, team_id=str(self.config.team_id), team_name=self.config.name, week=week, players=players)

    def _find_opponent_team_id(self, week: int) -> tuple[int, str]:
        try:
            matchups = self.query.get_team_matchups(self.config.team_id)
        except Exception as e:
            raise LeagueAdapterError(f"Couldn't fetch Yahoo matchups: {e}\n{UPGRADE_HINT}") from e

        my_team_key = self._team_key(self.config.team_id)
        for m in matchups:
            if int(m.week) != week:
                continue
            for t in m.teams:
                if t.team_key != my_team_key:
                    name = t.name.decode("utf-8") if isinstance(t.name, bytes) else str(t.name)
                    return int(t.team_id), name
        raise LeagueAdapterError(f"No Yahoo matchup found for week {week} (bye week, or season not started?).")

    def get_opponent_roster(self, week: int | None = None) -> Roster:
        week = week or self.current_week()
        opp_team_id, opp_name = self._find_opponent_team_id(week)
        try:
            players_raw = self.query.get_team_roster_player_stats_by_week(opp_team_id, week)
        except Exception as e:
            raise LeagueAdapterError(f"Couldn't fetch Yahoo opponent roster for week {week}: {e}\n{UPGRADE_HINT}") from e

        players = [self._yahoo_player_to_player(p, week) for p in players_raw]
        return Roster(league=self.league_name, team_id=str(opp_team_id), team_name=opp_name, week=week, players=players)

    def get_matchup(self, week: int | None = None) -> Matchup:
        week = week or self.current_week()
        my_roster = self.get_roster(week)
        opp_roster = self.get_opponent_roster(week)
        return Matchup(
            league=self.league_name,
            week=week,
            team_id=my_roster.team_id,
            team_name=my_roster.team_name,
            opponent_id=opp_roster.team_id,
            opponent_name=opp_roster.team_name,
            my_roster=my_roster,
            opp_roster=opp_roster,
        )

    def get_free_agents(self, position: str | None = None, limit: int = 50) -> list[Player]:
        week = self.current_week()
        try:
            league_key = self.query.get_league_key()
        except Exception as e:
            raise LeagueAdapterError(f"Couldn't resolve Yahoo league key: {e}\n{UPGRADE_HINT}") from e

        fetch_count = max(limit * 2, 50)  # over-fetch since we re-sort by our own projection estimate
        url = f"https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/players;status=FA;count={fetch_count}"
        if position:
            yahoo_pos = "DEF" if position.upper() == "DST" else position.upper()
            url += f";position={yahoo_pos}"

        try:
            raw_players = self.query.query(url, ["league", "players"])
        except Exception as e:
            raise LeagueAdapterError(f"Couldn't fetch Yahoo free agents: {e}\n{UPGRADE_HINT}") from e

        if raw_players is None:
            raw_players = []
        elif not isinstance(raw_players, list):
            raw_players = [raw_players]

        players = [self._yahoo_player_to_player(p, week) for p in raw_players]
        players.sort(key=lambda p: p.projected_points, reverse=True)
        return players[:limit]

    def get_byes(self) -> dict[str, int]:
        roster = self.get_roster()
        return {p.player_id: p.bye_week for p in roster.players if p.bye_week is not None}
