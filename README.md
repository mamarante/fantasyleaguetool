# League Nailer

A free, local, read-only fantasy football decision-support CLI for an ESPN
league and a Yahoo league at once. It pulls your rosters, compares
projections, flags close calls, scans waivers, and warns you about bye
weeks — and prints/writes a paste-friendly markdown report. **It never
makes a roster move for you**: no set lineup, no waiver claim, no drop, no
trade. You decide; this tool just does the math.

## Philosophy

- **Tier 1 (this MVP): data + math.** Pull, compare, flag, report. No AI calls.
- **Tier 2 (later, optional):** the markdown from `nailer report` is meant
  to be pasted into a Claude chat for judgment-layer analysis on top of
  the raw numbers.
- **Tier 3 (auto-management): intentionally never.** There is no
  set-lineup / claim-waiver / drop / propose-trade code anywhere in this
  repo, on purpose.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .          # installs the `nailer` command

cp .env.example .env               # fill in secrets, see below
cp config.example.yaml config.yaml # fill in league/team ids, see below
```

### ESPN league secrets (`.env`)

`ESPN_SWID` and `ESPN_S2` — two cookies from your logged-in espn.com
session. Log into espn.com, open browser DevTools → Application →
Cookies → espn.com, and copy the `SWID` and `espn_s2` values. These
expire periodically; if ESPN calls start failing with an access-denied
error, re-copy them.

### Yahoo league secrets (`.env`)

`YAHOO_CONSUMER_KEY` and `YAHOO_CONSUMER_SECRET` — register a free app at
https://developer.yahoo.com/apps/ with **Fantasy Sports → read**
permission (read-only is all this tool ever needs). The first time you
run a `nailer` command against Yahoo, `yfpy` opens a browser window for
one-time OAuth authorization; after that, tokens are cached (in your
local `.env`) and refreshed automatically.

### `config.yaml`

Copy `config.example.yaml` → `config.yaml` and fill in:

- `leagues.espn.league_id` — from your league's ESPN URL (`...leagueId=NNNNNN`)
- `leagues.espn.team_id` — your team's id in that league
- `leagues.yahoo.league_id` — from your Yahoo league URL
- `leagues.yahoo.team_id` — your team's id in that league
- `watchlist` — handcuffs / stash targets you want priority alerts on
  when they hit the waiver wire (e.g. a specific RB behind a starter you
  own)

Neither `config.yaml` nor `.env` is committed (both are gitignored) since
they contain your personal league/team identifiers and secrets.

## Usage

```bash
nailer roster              # my roster + this week's opponent, both leagues
nailer startsit             # recommended lineup + close flex calls
nailer waivers               # free agents that beat your worst bench player
nailer byes                  # upcoming bye weeks with no bench coverage
nailer matchup                # my projected total vs. this week's opponent
nailer strength                # my projected total vs. league average + rank
nailer sleepers                 # bench/waiver players trending above their season avg
nailer report                    # everything, as one markdown file

# any command:
nailer <cmd> --league espn    # just one league (default: both)
nailer <cmd> --week 7         # override the week (default: current)
```

`nailer report` writes to `reports/nailer-report-<date>.md` (configurable
via `report.output_dir` in config.yaml) and also prints to stdout so you
can paste it straight into a chat.

## Running it automatically

Fantasy data (projections, injury tags) changes on a daily cadence, not a
per-second one, and API responses are already cached for `cache.ttl_hours`
(24h by default) — so running `nailer report` every time you open a
terminal is wasted work, not "fresher" data. A daily scheduled run is the
right cadence:

```bash
crontab -e
# add a line like (7am daily; adjust the path to where you cloned this repo):
0 7 * * * /path/to/fantasyleaguetool/scripts/run_report.sh
```

`scripts/run_report.sh` activates the venv, runs `nailer report`, and logs
to `logs/`. Each morning during the season you'll have a fresh
`reports/nailer-report-<date>.md` waiting, without doing anything. On
macOS, cron works the same way, though if it can't read files due to
sandboxing you may need to grant your terminal/cron Full Disk Access in
System Settings, or use `launchd` instead.

## How it works

- `nailer/adapters/` implements one `LeagueAdapter` interface
  (`get_roster`, `get_matchup`, `get_free_agents`, `get_byes`,
  `roster_slots`) against ESPN (`espn-api`) and Yahoo (`yfpy`), so every
  report is written once and works for both leagues.
- `nailer/lineup.py` solves the optimal start/sit assignment exactly (a
  small bitmask DP over slots × players — realistic roster sizes make
  this instant), then flags "close flex calls": a starter whose margin
  over the best benched alternative at that flex slot is inside a
  configurable threshold (`startsit.close_call_margin` in config.yaml).
- API responses are cached to disk per day (`cache.dir`, `.cache/` by
  default) so repeated runs don't hammer either API.
- Every league failure (bad cookies, expired tokens, an API shape
  change) is caught and reported per-league with a hint, rather than
  crashing the whole report.
- `nailer strength` computes every team's optimal-lineup projected total
  for the current week (not whatever their manager happened to set) and
  ranks mine against the league average — a current-week snapshot, since
  true multi-week-ahead projections aren't reliably available from either
  API.
- `nailer sleepers` (ESPN only) flags bench/free-agent players whose
  projection this week is notably above their own season-average
  projection (`sleepers.min_pct_above_avg` / `min_season_avg` in
  config.yaml). This is a pure data/math signal, not a judgment call:
  ESPN's weekly projection is already matchup-aware, so comparing it to
  the player's own baseline is the whole signal — no separate
  opponent-strength modeling happens here.

## Known limitations

- **ESPN's unofficial API changes shape occasionally.** If ESPN calls
  start failing, try `pip install --upgrade espn-api` first — see that
  package's wiki/issues for what changed.
- **Yahoo's public API does not expose true per-player weekly
  projections** the way ESPN's does — only team-level projected totals
  and player-level actual results are available. As a stand-in,
  `projected_points` for Yahoo players is each player's season
  average points-per-game so far, which is a reasonable expected-value
  proxy for start/sit and waiver comparisons but is **not** a
  matchup-specific projection. This is a constraint of Yahoo's API, not
  a bug.
- **Confirm your Yahoo league's actual scoring settings** (full PPR /
  half-PPR / standard) before trusting cross-league comparisons —
  `config.yaml` has a `scoring` field you should double check against
  your league settings.
- The lineup optimizer supports standard single-flex rosters (QB, RB,
  WR, TE, FLEX, DST, K) plus WR/TE flex, RB/WR flex, and superflex/OP
  slots. It does not support IDP (individual defensive player) leagues.

## Development

```bash
pip install -r requirements.txt   # includes pytest, ruff, mypy
pytest                            # unit tests use an in-memory fake
                                   # adapter — no live credentials needed
ruff check nailer tests           # lint
mypy nailer                       # type check — catches adapter/report
                                   # wiring bugs before they hit a live API
```

