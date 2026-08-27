"""Optimal start/sit lineup solver + "close flex call" detection.

Both league adapters translate their native roster-slot vocabulary into
this module's internal slot names, so the optimizer (and the rest of the
report layer) is written once and works for either league.
"""
from __future__ import annotations

from dataclasses import dataclass

from nailer.models import Player

# Internal slot name -> set of player positions eligible to fill it.
SLOT_ELIGIBILITY: dict[str, set[str]] = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "DST": {"DST"},
    "K": {"K"},
    "FLEX": {"RB", "WR", "TE"},  # RB/WR/TE
    "FLEX_RW": {"RB", "WR"},  # RB/WR
    "FLEX_WT": {"WR", "TE"},  # WR/TE
    "SUPERFLEX": {"QB", "RB", "WR", "TE"},  # QB/RB/WR/TE ("OP")
}

# Canonical order to render starting slots for humans. Slot types not
# listed here (bench, IR, individual defensive positions in IDP leagues)
# are not part of the starting lineup this optimizer manages.
SLOT_DISPLAY_ORDER = ["QB", "RB", "WR", "TE", "FLEX_WT", "FLEX_RW", "FLEX", "SUPERFLEX", "DST", "K"]


@dataclass
class LineupAssignment:
    slot: str
    player: Player | None  # None if the slot went unfilled (not enough eligible players)


@dataclass
class FlexCloseCall:
    slot: str
    started: Player
    bench_alternative: Player
    margin: float  # started.projected_points - bench_alternative.projected_points


@dataclass
class OptimalLineup:
    assignments: list[LineupAssignment]
    bench: list[Player]
    total_projected: float
    close_calls: list[FlexCloseCall]

    @property
    def starters(self) -> list[Player]:
        return [a.player for a in self.assignments if a.player is not None]


def _slot_mask(slot: str, players: list[Player]) -> int:
    allowed = SLOT_ELIGIBILITY.get(slot, set())
    mask = 0
    for i, p in enumerate(players):
        if p.position in allowed:
            mask |= 1 << i
    return mask


def _solve(players: list[Player], slots: list[str]) -> tuple[float, dict[int, int]]:
    """Exact max-projected-points assignment of players to slots via
    bitmask DP. Cheap for realistic roster sizes (<= ~20 skill players,
    <= ~10 starting slots): at most len(slots) * 2**len(players) states,
    pruned hard by eligibility since most players are eligible for very
    few slot types.

    Returns (total, {slot_index: player_index}); a slot with no eligible
    unused player is simply left out of the mapping.
    """
    slot_masks = [_slot_mask(s, players) for s in slots]
    memo: dict[tuple[int, int], tuple[float, dict[int, int]]] = {}

    def rec(slot_i: int, used_mask: int) -> tuple[float, dict[int, int]]:
        if slot_i == len(slots):
            return 0.0, {}
        key = (slot_i, used_mask)
        if key in memo:
            return memo[key]

        # Try every eligible player for this slot first (ties broken by
        # whichever is found first, i.e. lowest player index — arbitrary
        # but stable), then only fall back to leaving the slot empty if
        # that's *strictly* better. Otherwise, when leaving a dedicated
        # slot empty ties with filling it (because some later flex slot
        # could absorb the same player for the same total), the tie would
        # go to "empty" just because it's evaluated first — confusing to
        # display even though the grand total is unaffected.
        best_val: float = float("-inf")
        best_assign: dict[int, int] = {}
        avail = slot_masks[slot_i] & ~used_mask
        m = avail
        while m:
            low = m & (-m)
            i = low.bit_length() - 1
            m ^= low
            val, assign = rec(slot_i + 1, used_mask | low)
            total = players[i].projected_points + val
            if total > best_val:
                best_val = total
                best_assign = {slot_i: i, **assign}

        skip_val, skip_assign = rec(slot_i + 1, used_mask)
        if skip_val > best_val:
            best_val = skip_val
            best_assign = skip_assign

        memo[key] = (best_val, best_assign)
        return memo[key]

    return rec(0, 0)


def optimize_lineup(players: list[Player], slots: list[str], close_call_margin: float = 2.5) -> OptimalLineup:
    """Assign `players` to `slots` to maximize total projected points.

    `players` should be every rostered player (starters and bench both —
    the optimizer decides who starts) with `.projected_points` set.
    """
    total, slot_to_player = _solve(players, slots)

    assignments: list[LineupAssignment] = []
    used_indices: set[int] = set()
    for slot_i, slot in enumerate(slots):
        player_i = slot_to_player.get(slot_i)
        if player_i is not None:
            assignments.append(LineupAssignment(slot=slot, player=players[player_i]))
            used_indices.add(player_i)
        else:
            assignments.append(LineupAssignment(slot=slot, player=None))

    bench = [p for i, p in enumerate(players) if i not in used_indices]
    close_calls = _find_close_calls(assignments, bench, margin=close_call_margin)

    return OptimalLineup(assignments=assignments, bench=bench, total_projected=round(total, 2), close_calls=close_calls)


def _find_close_calls(assignments: list[LineupAssignment], bench: list[Player], margin: float = 2.5) -> list[FlexCloseCall]:
    """For every flex-type slot (more than one eligible position), find
    the best benched alternative eligible for that slot. If the gap is
    within `margin` points, it's a close call worth a second look.
    """
    close_calls: list[FlexCloseCall] = []
    for a in assignments:
        if a.player is None:
            continue
        eligible = SLOT_ELIGIBILITY.get(a.slot, set())
        if len(eligible) <= 1:
            continue  # dedicated slot, not a flex decision
        alternatives = [b for b in bench if b.position in eligible]
        if not alternatives:
            continue
        best_alt = max(alternatives, key=lambda p: p.projected_points)
        gap = a.player.projected_points - best_alt.projected_points
        if gap <= margin:
            close_calls.append(FlexCloseCall(slot=a.slot, started=a.player, bench_alternative=best_alt, margin=round(gap, 2)))
    return close_calls
