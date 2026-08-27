"""JSON (de)serialization for the shared models, used only by the file
cache in nailer/cache.py — adapters fetch data, convert to these
dataclasses, then round-trip through dicts so a second run on the same
day can skip the network call entirely.
"""
from __future__ import annotations

from nailer.models import InjuryStatus, Matchup, Player, Roster


def player_to_dict(p: Player) -> dict:
    return {
        "player_id": p.player_id,
        "name": p.name,
        "position": p.position,
        "pro_team": p.pro_team,
        "projected_points": p.projected_points,
        "actual_points": p.actual_points,
        "injury_status": p.injury_status.value if isinstance(p.injury_status, InjuryStatus) else p.injury_status,
        "bye_week": p.bye_week,
        "eligible_slots": p.eligible_slots,
        "is_starter": p.is_starter,
        "slot": p.slot,
        "percent_owned": p.percent_owned,
    }


def player_from_dict(d: dict) -> Player:
    d = dict(d)
    d["injury_status"] = InjuryStatus(d.get("injury_status") or InjuryStatus.UNKNOWN.value)
    return Player(**d)


def roster_to_dict(r: Roster) -> dict:
    return {
        "league": r.league,
        "team_id": r.team_id,
        "team_name": r.team_name,
        "week": r.week,
        "players": [player_to_dict(p) for p in r.players],
    }


def roster_from_dict(d: dict) -> Roster:
    return Roster(
        league=d["league"],
        team_id=d["team_id"],
        team_name=d["team_name"],
        week=d["week"],
        players=[player_from_dict(p) for p in d["players"]],
    )


def matchup_to_dict(m: Matchup) -> dict:
    return {
        "league": m.league,
        "week": m.week,
        "team_id": m.team_id,
        "team_name": m.team_name,
        "opponent_id": m.opponent_id,
        "opponent_name": m.opponent_name,
        "my_roster": roster_to_dict(m.my_roster),
        "opp_roster": roster_to_dict(m.opp_roster),
    }


def matchup_from_dict(d: dict) -> Matchup:
    return Matchup(
        league=d["league"],
        week=d["week"],
        team_id=d["team_id"],
        team_name=d["team_name"],
        opponent_id=d["opponent_id"],
        opponent_name=d["opponent_name"],
        my_roster=roster_from_dict(d["my_roster"]),
        opp_roster=roster_from_dict(d["opp_roster"]),
    )
