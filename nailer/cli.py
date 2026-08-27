"""League Nailer CLI. Read-only decision support: `nailer` never sets a
lineup, claims a waiver, drops a player, or proposes a trade against
either league. See the project README for the full philosophy.
"""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from nailer.adapters import LeagueAdapterError, build_adapters
from nailer.cache import Cache
from nailer.config import ConfigError, NailerConfig, load_config
from nailer.models import Player
from nailer.reports.byes import build_bye_radar
from nailer.reports.matchup import build_matchup_preview
from nailer.reports.report import build_full_report, write_report
from nailer.reports.roster import build_roster_view
from nailer.reports.sleepers import build_sleeper_report
from nailer.reports.startsit import build_startsit_report
from nailer.reports.strength import build_strength_report
from nailer.reports.waivers import build_waiver_report

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

LeagueOpt = typer.Option("both", "--league", help="espn, yahoo, or both")
WeekOpt = typer.Option(None, "--week", help="Override the week (default: current)")
ConfigOpt = typer.Option("config.yaml", "--config", help="Path to config.yaml")
OutOpt = typer.Option(None, "--out", help="Output file (default: reports/nailer-report-<date>.md)")


def _setup(config_path: str, league: str) -> tuple[NailerConfig, dict]:
    try:
        config = load_config(Path(config_path))
    except ConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        raise typer.Exit(code=1) from e

    cache = Cache(config.cache_dir, config.cache_ttl_hours, config.cache_enabled)
    adapters = build_adapters(config, cache)

    if league != "both":
        if league not in adapters:
            console.print(f"[red]League '{league}' isn't enabled in config.yaml (or isn't 'espn'/'yahoo'/'both').[/red]")
            raise typer.Exit(code=1)
        adapters = {league: adapters[league]}

    if not adapters:
        console.print("[red]No leagues enabled in config.yaml.[/red]")
        raise typer.Exit(code=1)

    return config, adapters


def _status_tag(p: Player) -> str:
    return p.injury_status.value if p.injury_status.value != "ACTIVE" else ""


def _player_row(p: Player, slot: str | None = None) -> list[str]:
    return [slot or (p.slot or ""), p.name, p.position, p.pro_team, f"{p.projected_points:.1f}", _status_tag(p)]


def _players_table(title: str, players: list[Player], slot_fn=lambda p: p.slot or "") -> Table:
    table = Table(title=title)
    for col in ("Slot", "Player", "Pos", "Team", "Proj", "Status"):
        table.add_column(col)
    for p in players:
        table.add_row(slot_fn(p), p.name, p.position, p.pro_team, f"{p.projected_points:.1f}", _status_tag(p))
    return table


@app.command()
def roster(league: str = LeagueOpt, week: int | None = WeekOpt, config: str = ConfigOpt):
    """Show my roster and this week's opponent's roster, side by side."""
    cfg, adapters = _setup(config, league)
    for name, adapter in adapters.items():
        try:
            view = build_roster_view(adapter, week)
        except LeagueAdapterError as e:
            console.print(f"[red]{name.upper()}: {e}[/red]")
            continue

        starters = [p for p in view.my_roster.players if p.is_starter]
        bench = [p for p in view.my_roster.players if not p.is_starter]
        console.print(_players_table(f"{view.my_roster.team_name} — Starters (Week {view.week})", starters))
        console.print(_players_table(f"{view.my_roster.team_name} — Bench", bench))
        console.print(_players_table(f"Opponent: {view.opp_roster.team_name}", view.opp_roster.players))


@app.command()
def startsit(league: str = LeagueOpt, week: int | None = WeekOpt, config: str = ConfigOpt):
    """Recommend the optimal lineup and flag close flex calls."""
    cfg, adapters = _setup(config, league)
    for name, adapter in adapters.items():
        try:
            report = build_startsit_report(adapter, cfg, week)
        except LeagueAdapterError as e:
            console.print(f"[red]{name.upper()}: {e}[/red]")
            continue

        table = Table(title=f"{name.upper()} — Recommended Lineup (Week {report.week})")
        for col in ("Slot", "Player", "Pos", "Team", "Proj", "Status"):
            table.add_column(col)
        for a in report.lineup.assignments:
            if a.player:
                table.add_row(*_player_row(a.player, a.slot))
            else:
                table.add_row(a.slot, "-- none eligible --", "", "", "", "")
        console.print(table)
        console.print(f"[bold]Total projected: {report.lineup.total_projected:.1f}[/bold]")

        if report.lineup.close_calls:
            console.print("[yellow]Close flex calls:[/yellow]")
            for cc in report.lineup.close_calls:
                console.print(
                    f"  {cc.slot}: starting [bold]{cc.started.name}[/bold] ({cc.started.projected_points:.1f}) over "
                    f"{cc.bench_alternative.name} ({cc.bench_alternative.projected_points:.1f}) — margin {cc.margin:+.1f}"
                )


@app.command()
def waivers(league: str = LeagueOpt, week: int | None = WeekOpt, config: str = ConfigOpt, top: int = typer.Option(5, help="Adds to show per position")):
    """List free agents that beat your worst bench player at their position."""
    cfg, adapters = _setup(config, league)
    for name, adapter in adapters.items():
        try:
            report = build_waiver_report(adapter, cfg, week, per_position=top)
        except LeagueAdapterError as e:
            console.print(f"[red]{name.upper()}: {e}[/red]")
            continue

        for pw in report.by_position:
            if not pw.candidates:
                continue
            table = Table(title=f"{name.upper()} — {pw.position} waivers (your worst bench: {pw.worst_bench_projected:.1f} proj)")
            for col in ("Player", "Team", "Proj", "Status"):
                table.add_column(col)
            for p in pw.candidates:
                table.add_row(p.name, p.pro_team, f"{p.projected_points:.1f}", _status_tag(p))
            console.print(table)

        if report.watchlist_hits:
            console.print("[yellow]Watchlist alerts:[/yellow]")
            for hit in report.watchlist_hits:
                reason = f" — {hit.entry.reason}" if hit.entry.reason else ""
                console.print(f"  {hit.player.name} ({hit.player.position}, {hit.player.pro_team}) is a free agent{reason}")


@app.command()
def byes(league: str = LeagueOpt, config: str = ConfigOpt):
    """Warn about upcoming weeks where a starter has no bench replacement for their bye."""
    cfg, adapters = _setup(config, league)
    for name, adapter in adapters.items():
        try:
            warnings = build_bye_radar(adapter, cfg)
        except LeagueAdapterError as e:
            console.print(f"[red]{name.upper()}: {e}[/red]")
            continue

        if not warnings:
            console.print(f"[green]{name.upper()}: no uncovered bye weeks in the next {cfg.bye_lookahead_weeks} weeks.[/green]")
            continue

        console.print(f"[yellow]{name.upper()} bye-week warnings:[/yellow]")
        for w in warnings:
            console.print(f"  Week {w.week}: [bold]{w.player.name}[/bold] ({w.player.position}) is on bye — no bench replacement. Queue a stream.")


@app.command()
def matchup(league: str = LeagueOpt, week: int | None = WeekOpt, config: str = ConfigOpt):
    """My projected total vs. this week's opponent, by position."""
    cfg, adapters = _setup(config, league)
    for name, adapter in adapters.items():
        try:
            waiver_report = build_waiver_report(adapter, cfg, week)
            free_agents = [c for pw in waiver_report.by_position for c in pw.candidates]
            preview = build_matchup_preview(adapter, cfg, week, free_agents=free_agents)
        except LeagueAdapterError as e:
            console.print(f"[red]{name.upper()}: {e}[/red]")
            continue

        console.print(
            f"[bold]{name.upper()} Week {preview.week}[/bold]: "
            f"{preview.my_projected:.1f} (me) vs. {preview.opp_projected:.1f} ({preview.matchup.opponent_name})"
        )
        table = Table()
        for col in ("Position", "Me", "Opp", "Diff"):
            table.add_column(col)
        for b in preview.position_breakdown:
            style = "red" if b.diff < 0 else "green"
            table.add_row(b.position, f"{b.mine:.1f}", f"{b.theirs:.1f}", f"[{style}]{b.diff:+.1f}[/{style}]")
        console.print(table)

        for pos, closer in preview.gap_closers.items():
            console.print(f"  Losing at {pos}: waiver add [bold]{closer.name}[/bold] ({closer.projected_points:.1f} proj) could close the gap")


@app.command()
def strength(league: str = LeagueOpt, week: int | None = WeekOpt, config: str = ConfigOpt):
    """My optimal-lineup projected total vs. the league average this week, and my rank."""
    cfg, adapters = _setup(config, league)
    for name, adapter in adapters.items():
        try:
            report = build_strength_report(adapter, cfg, week)
        except LeagueAdapterError as e:
            console.print(f"[red]{name.upper()}: {e}[/red]")
            continue

        diff_style = "green" if report.diff_from_average >= 0 else "red"
        console.print(
            f"[bold]{name.upper()} Week {report.week}[/bold]: {report.my_team.projected_total:.1f} proj "
            f"vs. league average {report.league_average:.1f} "
            f"([{diff_style}]{report.diff_from_average:+.1f}[/{diff_style}]) — rank {report.rank}/{len(report.all_teams)}"
        )
        table = Table(title=f"{name.upper()} — League Strength (Week {report.week})")
        for col in ("Rank", "Team", "Projected"):
            table.add_column(col)
        for i, t in enumerate(report.all_teams, start=1):
            label = f"[bold]{t.team_name} (you)[/bold]" if t.team_id == report.my_team.team_id else t.team_name
            table.add_row(str(i), label, f"{t.projected_total:.1f}")
        console.print(table)


@app.command()
def sleepers(league: str = LeagueOpt, week: int | None = WeekOpt, config: str = ConfigOpt):
    """Bench and free-agent players whose projection this week is notably above their season average."""
    cfg, adapters = _setup(config, league)
    for name, adapter in adapters.items():
        try:
            report = build_sleeper_report(adapter, cfg, week)
        except LeagueAdapterError as e:
            console.print(f"[red]{name.upper()}: {e}[/red]")
            continue

        def _trending_table(title: str, trending: list):
            table = Table(title=title)
            for col in ("Player", "Pos", "Team", "This Week", "Season Avg", "% Above Avg"):
                table.add_column(col)
            for t in trending:
                table.add_row(
                    t.player.name, t.player.position, t.player.pro_team,
                    f"{t.player.projected_points:.1f}", f"{t.season_avg:.1f}", f"+{t.pct_above_avg:.0%}",
                )
            return table

        if report.bench_trending:
            console.print(_trending_table(f"{name.upper()} — Bench players trending up", report.bench_trending))
        if report.waiver_trending:
            console.print(_trending_table(f"{name.upper()} — Free agents trending up", report.waiver_trending))
        if not report.bench_trending and not report.waiver_trending:
            console.print(f"[green]{name.upper()}: nothing trending notably above its season average right now.[/green]")


@app.command()
def report(league: str = LeagueOpt, config: str = ConfigOpt, out: str | None = OutOpt):
    """Run everything and write one paste-friendly markdown report covering both leagues."""
    cfg, adapters = _setup(config, league)
    markdown = build_full_report(cfg, adapters)

    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown)
    else:
        path = write_report(markdown, cfg.report_output_dir)

    console.print(markdown)
    console.print(f"\n[green]Report written to {path}[/green]")


if __name__ == "__main__":
    app()
