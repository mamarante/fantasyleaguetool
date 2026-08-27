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
nailer report                 # everything, as one markdown file

# any command:
nailer <cmd> --league espn    # just one league (default: both)
nailer <cmd> --week 7         # override the week (default: current)
```

`nailer report` writes to `reports/nailer-report-<date>.md` (configurable
via `report.output_dir` in config.yaml) and also prints to stdout so you
can paste it straight into a chat.

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
pip install -r requirements.txt   # includes pytest
pytest                            # unit tests use an in-memory fake
                                   # adapter — no live credentials needed
```
