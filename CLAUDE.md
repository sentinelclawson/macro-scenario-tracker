# Macro Scenario Tracker

A one-page website that scores five macro scenarios for rates, oil and stocks through 2028 and is re-scored every Monday. Owner: Allen Elmore (commercial real estate operator in Raleigh, NC, and SPY options trader). Readers: Allen, friends on Telegram, and followers on X.

## Where it lives

- `index.html` in this folder is the whole site. It has no build step and no dependencies to install.
- A shared copy also lives as a claude.ai artifact: https://claude.ai/artifact/XT5pRvBAoV1X8WwxyjNvtT
- This folder is the GitHub repository `macro-scenario-tracker`. Vercel and Netlify both deploy it automatically on every push to `main`.
  - Vercel: framework preset "Other", no build command, output directory is the root.
  - Netlify: settings come from `netlify.toml` (no build, publish the root).

## How it updates

The scheduled task "Macro Scenario Tracker" runs Mondays at 6:54 AM ET. It researches the week, re-scores the odds, writes a new week into the data block, republishes the claude.ai artifact, and commits `index.html` here. The artifact copy has no `<html>`/`<head>` wrapper; this site copy does. Weekly updates change only the data block, so the same JSON goes into both.

## The data block

All content lives in one JSON block in `index.html`:

```
<script type="application/json" id="tracker-data">{"weeks":[ ... ]}</script>
```

`weeks` is in date order; the page shows the latest and offers older weeks in a picker. Each week has: `date`, `label`, `short`, `updatedLabel`, `headline`, `market`, `scenarios`, `paths`, `snapshot`, `signposts`, `changes`, `cre`, `dates`, `sources`.

- Scenarios (fixed ids): `soft` Soft exit, `crack` Deal and labor cracks, `grind` Grind, `stag` Stagflation crack, `esc` Escalation. Groups: deal = soft + crack, nodeal = grind + stag, esc = esc. Each has `prob` (integers summing to 100), `story`, and `end27` levels for `ff`, `ty`, `br`, `sp`.
- Paths: labels `["Now","Mar 27","Jun 27","Dec 27","Dec 28"]`, five numbers per scenario for `ff` (Fed funds midpoint), `ty` (10Y), `br` (Brent), `sp` (S&P 500). `end27` equals the "Dec 27" point.
- Signposts (fixed ids): `hormuz`, `brent`, `unemp`, `core`, `dots`, `bills`, `y30`, `hy`, `ai`. Each has `now`, `status` (`deal`, `none` or `stress`), `good` and `bad` triggers.
- Snapshot rows: `ff`, `effr`, `b3m`, `b6m`, `y2`, `y10`, `y30`, `mort`, `brent`, `cpi`, `core`, `unemp`, `nfp`, `spx`, optional `hy`. Each has `value` (number), `kind` (`rate`, `price`, `index`, `count`, `pp`), `fmt`, `asof`.

## Scoring rules

- Move any scenario at most 8 points a week unless something decisive happens (a signed deal with Hormuz reopening, a major escalation, a Fed pivot to cuts, unemployment up 0.3 points in one report).
- Two or three signposts flipping the same way justify a real move; one alone is a small move.
- Bills vs fed funds (Caleb Franzen's signal): spread = bill yield minus effective fed funds. Neutral band is 15 bps either side, 5 sessions to confirm. Moves priced within 6 months is roughly the 6-month spread divided by 25. Heavy bill issuance can make it read too hawkish; within 10 days of an FOMC meeting it is coincident, not predictive.
- 30Y rule: a 30Y drop below 5.1% counts toward a deal only if Brent confirms. A drop driven by Treasury supply (buybacks, smaller long auctions) is labeled "supply-driven" and does not move the odds.
- Never guess a number. Carry a reading forward with its old date if it can't be confirmed.

## Editing rules

- Never use the em dash or en dash character anywhere: page, data, commit messages, code comments. Use commas, colons, parentheses or periods.
- Weekly updates touch only the JSON block. Design changes are separate commits.
- Validate before committing: the JSON parses, odds sum to 100, every path has 5 numbers, and the JSON contains no `</script`.
- The page must work at phone width, in light and dark mode, and print cleanly on white.
- Libraries: Chart.js 4.4.1 from cdnjs and Google Fonts only. No build tools.
- No secrets, tokens or keys in this repository.
- These are scenario estimates, not investment advice. Keep that line in the footer.

## Related tools on Allen's computer

`macro_signal_tracker.py` (FRED-based regime falsifiers) and `stir_dashboard.py` (Fed pricing) could feed this page later. That's a future project, not part of the weekly update.
