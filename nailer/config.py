"""Loads config.yaml (league/team ids, watchlist, thresholds) and .env
(secrets: ESPN cookies, Yahoo OAuth client id/secret). Secrets never live
in config.yaml, and config.yaml itself is gitignored since it holds your
personal league/team ids.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from nailer.models import WatchlistEntry

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_ENV_PATH = Path(".env")


class ConfigError(RuntimeError):
    """Raised when required config or secrets are missing/invalid."""


@dataclass
class EspnConfig:
    enabled: bool
    name: str
    league_id: int
    year: int
    team_id: int
    scoring: str
    swid: str
    espn_s2: str


@dataclass
class YahooConfig:
    enabled: bool
    name: str
    league_id: str
    game_key: str
    team_id: int
    scoring: str
    consumer_key: str
    consumer_secret: str


@dataclass
class NailerConfig:
    espn: EspnConfig | None
    yahoo: YahooConfig | None
    watchlist: list[WatchlistEntry] = field(default_factory=list)
    bye_lookahead_weeks: int = 2
    close_call_margin: float = 2.5
    cache_enabled: bool = True
    cache_dir: Path = Path(".cache")
    cache_ttl_hours: int = 24
    report_output_dir: Path = Path("reports")

    def enabled_leagues(self) -> list[str]:
        leagues = []
        if self.espn and self.espn.enabled:
            leagues.append("espn")
        if self.yahoo and self.yahoo.enabled:
            leagues.append("yahoo")
        return leagues


def load_config(config_path: Path | str = DEFAULT_CONFIG_PATH, env_path: Path | str = DEFAULT_ENV_PATH) -> NailerConfig:
    config_path = Path(config_path)
    env_path = Path(env_path)

    if env_path.exists():
        load_dotenv(env_path)

    if not config_path.exists():
        raise ConfigError(
            f"Config file not found at {config_path}. "
            f"Copy config.example.yaml to {config_path} and fill in your league details."
        )

    with config_path.open() as f:
        raw = yaml.safe_load(f) or {}

    leagues_raw = raw.get("leagues", {})

    espn_cfg = None
    espn_raw = leagues_raw.get("espn")
    if espn_raw and espn_raw.get("enabled", False):
        swid = os.environ.get("ESPN_SWID", "")
        espn_s2 = os.environ.get("ESPN_S2", "")
        if not swid or not espn_s2:
            raise ConfigError(
                "ESPN league is enabled but ESPN_SWID / ESPN_S2 are not set. "
                "Add them to your .env (see .env.example)."
            )
        espn_cfg = EspnConfig(
            enabled=True,
            name=espn_raw.get("name", "ESPN League"),
            league_id=int(espn_raw["league_id"]),
            year=int(espn_raw.get("year", 2026)),
            team_id=int(espn_raw["team_id"]),
            scoring=espn_raw.get("scoring", "ppr"),
            swid=swid,
            espn_s2=espn_s2,
        )

    yahoo_cfg = None
    yahoo_raw = leagues_raw.get("yahoo")
    if yahoo_raw and yahoo_raw.get("enabled", False):
        consumer_key = os.environ.get("YAHOO_CONSUMER_KEY", "")
        consumer_secret = os.environ.get("YAHOO_CONSUMER_SECRET", "")
        if not consumer_key or not consumer_secret:
            raise ConfigError(
                "Yahoo league is enabled but YAHOO_CONSUMER_KEY / YAHOO_CONSUMER_SECRET are not set. "
                "Add them to your .env (see .env.example)."
            )
        yahoo_cfg = YahooConfig(
            enabled=True,
            name=yahoo_raw.get("name", "Yahoo League"),
            league_id=str(yahoo_raw["league_id"]),
            game_key=yahoo_raw.get("game_key", "nfl"),
            team_id=int(yahoo_raw["team_id"]),
            scoring=yahoo_raw.get("scoring", "ppr"),
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
        )

    if espn_cfg is None and yahoo_cfg is None:
        raise ConfigError(
            "No leagues are enabled in config.yaml. Enable at least one of leagues.espn / leagues.yahoo."
        )

    watchlist = [
        WatchlistEntry(name=w["name"], league=w.get("league"), reason=w.get("reason", ""))
        for w in raw.get("watchlist", []) or []
    ]

    bye_radar = raw.get("bye_radar", {}) or {}
    startsit = raw.get("startsit", {}) or {}
    cache = raw.get("cache", {}) or {}
    report = raw.get("report", {}) or {}

    return NailerConfig(
        espn=espn_cfg,
        yahoo=yahoo_cfg,
        watchlist=watchlist,
        bye_lookahead_weeks=int(bye_radar.get("lookahead_weeks", 2)),
        close_call_margin=float(startsit.get("close_call_margin", 2.5)),
        cache_enabled=bool(cache.get("enabled", True)),
        cache_dir=Path(cache.get("dir", ".cache")),
        cache_ttl_hours=int(cache.get("ttl_hours", 24)),
        report_output_dir=Path(report.get("output_dir", "reports")),
    )
