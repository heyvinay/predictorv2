> **NOT PURSUED — archived for future reference.**
>
> This was an elaborate design for a side-prize composite leaderboard
> (exact + rarity + bonus + R32 advancement, with two-flag eligibility,
> a Trionda lens / column, and a contrarian-R32 visual grid). After
> Monte Carlo simulation against real production data on **2026-06-19**,
> we found that even the strongest contrarian variant (pool-consensus-
> weighted R32 at +30) contributed only ~8% to side-prize variance
> while introducing meaningful correlation (~0.35) with the main
> leaderboard — the dilution concern was real, and the orthogonality
> payoff was modest.
>
> **Decision:** the Trionda ball goes to the **runner-up** at
> tournament end on total points, with **any entry that won or shared
> the group-stage cash** ineligible; tiebreaker chain is group-stage
> points → drawn by lots. Implemented as ~80 words of rules-page copy
> in section 05 of `frontend/src/routes/rules/+page.svelte`. Zero
> backend / frontend logic changes.
>
> The simulation findings here remain useful: if anyone proposes a
> side-prize composite again, the analysis below short-circuits the
> re-decision. See also `scratch/trionda_simulation.py`,
> `scratch/trionda_real_data_analysis.py`,
> `scratch/trionda_contrarian_r32.py` for the model code.
>
> ---

# Adidas Trionda Side Prize — Design

**Date:** 2026-06-19
**Status:** NOT PURSUED (see header above)
**Original status:** Approved (user confirmed formula, two-flag eligibility,
mobile lens, live-tracking flag behaviour)
**Implementation:** deferred — this spec only; implementation plan
follows via `superpowers:writing-plans` in a later session.

## Purpose

Award an official Adidas Trionda match ball as a side prize at the
end of the tournament, picking a winner whose name is structurally
unlikely to also be a cash-prize winner. The composite metric
rewards a different skill profile than the main leaderboard
(precision + boldness + foresight, vs the main leaderboard's
density-of-correct-outcomes + knockout-bracket accuracy), so the
ball lands with a fresh face.

The main leaderboard already awards two cash prizes from the
prize pool: one to the group-stage points leader at the moment
all 72 group fixtures finish, one to the tournament points leader
at the moment the Final finishes. Both cash winners are
**ineligible for the side prize**; the ball goes to the highest-
scoring eligible entry on the composite metric.

## Side-prize composite formula

For each scoring entry:

```
trionda_composite = (exact_scores × 10)
                  + sum(rarity_points across all group fixtures)
                  + sum(bonus_question_points for Q1 + Q2 + Q3 + Q4)
                  + (5 × correct_R32_picks)
```

Where `correct_R32_picks` is the number of teams in the entry's
`BracketPrediction.round_of_32` (32 picks) that actually advance
to the real R32 (i.e., make it out of the group stage).

Key properties:

- **`exact_scores × 10` is the SURPRISAL portion only** of the
  exact-score payout. The 5-point base outcome is already counted
  in the main leaderboard's outcome term and is deliberately
  excluded — the side prize must not overlap with what the main
  leaderboard rewards on the match-result axis.
- **Rarity** points come from the active `logarithmic` scoring
  mode (set in `config/worldcup2026.yml`). If the mode is changed
  to `fixed` mid-tournament, rarity collapses to zero and the
  side prize degenerates to `exact + bonus + R32`. Worth
  re-pausing awareness only — current mode is `logarithmic` and
  the spec assumes it stays that way through tournament end.
- **Bonus questions settle in two waves:** Q1 + Q2 at end of
  group stage, Q3 + Q4 at end of tournament. The composite is
  live throughout — components are added as they settle.
- **Knockout-stage match outcomes are not user-predicted** in this
  competition (advancement is). So `exact_scores` and `rarity_points`
  from knockout fixtures are not part of the composite (and aren't
  produced by the scoring engine for those fixtures anyway).
- **R32 advancement picks (+5 each) overlap intentionally** with
  the main leaderboard's existing R32 advancement payout (+20
  each). The discount (5 vs 20) keeps the side prize's emphasis
  on exact + rarity + bonus while still rewarding "you read the
  group stage correctly." The term settles at end of group stage
  (when R32 is seeded — same moment Q1 + Q2 settle), producing
  a meaningful jump in side-prize standings on that single
  tournament moment.
- **R16 / QF / SF / Final picks are NOT extended into this term.**
  The +5 R32 component captures "made it to the knockout stage"
  as a binary skill; deeper-round picks (which the main
  leaderboard already pays generously at +30 / +40 / +60 / +100)
  are left to the main leaderboard.

## Eligibility — two ineligible entries

The side prize is awarded to the highest-scoring **eligible** entry
on `trionda_composite`. Two entries are flagged ineligible:

1. **Group-stage cash winner** — whoever leads the main leaderboard
   at the moment all 72 group fixtures finish.
2. **Tournament cash winner** — whoever leads the main leaderboard
   at the moment the Final finishes and all scores are settled.

If by coincidence the same entry is both — i.e., one player leads
the main leaderboard at both phase-end moments — the two flags
collapse visually to one and the side prize goes to the next
eligible entry.

### Live flag behaviour (option `a`)

Throughout the tournament, a ⚠ icon appears next to whoever is
currently leading the main standings (a *provisional* flag):

- **During group stage:** flag follows the live main-leaderboard
  #1 — it may shift between entries as the standings move. Tooltip
  framing: *"Currently leading the group standings. If this holds,
  this entry wins the group-stage cash prize and is not eligible
  for the side prize ball."*
- **At end of group stage:** the entry holding the flag at that
  moment becomes the group-stage cash winner — their flag
  becomes **permanent** (tooltip changes to "Won the group-stage
  cash prize. Not eligible for the side prize ball."). A new live
  flag begins tracking the live tournament-leader entry.
- **At end of tournament:** the second flag locks permanent
  ("Won the tournament cash prize. Not eligible for the side
  prize ball."). The composite leaderboard's top eligible entry
  is the side-prize winner.

## Tiebreakers

When multiple eligible entries tie on `trionda_composite`:

1. **Primary:** highest main-leaderboard total points
2. **Secondary:** drawn by lots (admin-driven, not automated — the
   admin runs a draw and announces the winner)

Tiebreakers apply only to the *prize award*; the live leaderboard
displays composite ties as identical rank (consistent with the
existing standings table's tie behaviour).

## UI surfaces

### Desktop standings (`≥880px`)

A new sortable column **"Trionda"** appears in the standings table
between Knockout and Trend. Header behaviour matches the existing
sortable columns (Entry / Group / Knockout / Total):

- Click toggles ascending / descending
- Natural sort direction = descending (high composite = top)
- Persisted in `localStorage['predictor:lb:sort']` (same key the
  existing sort already uses)

Inline ⚠ icon next to ineligible entries regardless of the active
sort. Hover tooltip per the live-flag behaviour rules above.

### Mobile standings (`<880px`)

A small **lens segmented control** above the standings table:
`[Main] [Trionda]`. The control sits on the same toolbar row as
the search input, stacking below at very narrow widths
(existing `flex-wrap` pattern).

- **Main lens (default):** existing behaviour unchanged — Total
  column shows main points, sort by main total.
- **Trionda lens:** Total column re-renders to show
  `trionda_composite`, table re-sorts by composite descending,
  inline ⚠ flags appear next to ineligible entries.

Lens choice persists in `localStorage['predictor:lb:lens']`
(`'main'` | `'trionda'`). Pool filters (Atlas / JMFA / Guests /
All) and search apply identically in both lenses.

### Eligibility flag

Visual: small ⚠ icon adjacent to the entry name in the standings
row, rendered in both desktop column-sort and mobile lens modes.

| State | Tooltip text |
|---|---|
| Provisional — leading group standings, group stage not yet over | "Currently leading the group standings. If this holds, this entry wins the group-stage cash prize and is not eligible for the side prize ball." |
| Permanent — group-stage cash winner locked | "Won the group-stage cash prize. Not eligible for the side prize ball." |
| Provisional — leading tournament standings, tournament not yet over | "Currently leading the tournament standings. If this holds, this entry wins the tournament cash prize and is not eligible for the side prize ball." |
| Permanent — tournament cash winner locked | "Won the tournament cash prize. Not eligible for the side prize ball." |
| Both: same entry, after both phases lock | "Won both the group-stage and tournament cash prizes. Not eligible for the side prize ball." (single flag, combined tooltip) |

### Header explainer

Above the Trionda column (desktop) or next to the lens toggle
(mobile), a short one-line explainer:

> Trionda side prize · Bonus + rarity + exact-score bonus + R32 ·
> awarded at end of tournament · [Rules ›]

The `Rules ›` link goes to the corresponding rules-page section.

## Rules page additions

A new section on `frontend/src/routes/rules/+page.svelte`:

> **Adidas Trionda side prize** — one official Adidas Trionda match
> ball, awarded at the end of the tournament to the highest-scoring
> eligible entry on the side-prize composite.
>
> **Composite:** Bonus question points (Q1 + Q2 + Q3 + Q4) +
> rarity points + the +10 bonus on each exact-score prediction
> + 5 points for every R32 pick that actually makes it out of
> the group stage. The base outcome points are not part of this
> composite.
>
> **Eligibility:** the group-stage cash winner and the tournament
> cash winner are both ineligible for the side prize ball. The
> ball goes to the highest-scoring eligible entry.
>
> **Tiebreakers:** highest main-leaderboard total points; if still
> tied, drawn by lots.

## Data model

### Backend

- `LeaderboardEntry` schema gains a new field:
  `trionda_composite: int` — computed during the existing 30s
  leaderboard cache rebuild (`backend/app/services/leaderboard.py`).
- Composition: sum of four existing per-entry quantities — the
  exact-score count × 10, the rarity points sum across group
  fixtures, the bonus-question points sum across Q1 + Q2 + Q3 +
  Q4, and 5 × the count of correct R32 advancement picks. The
  R32 overlap is computed against `get_actual_advancement(
  'round_of_32')` (already produced by the scoring engine for
  the main leaderboard's +20 R32 payout). No new scoring logic;
  the field is a derived aggregation over data the engine
  already produces.
- No new endpoint. The composite field rides on the existing
  `GET /api/leaderboard` response.

### Frontend

- `frontend/src/lib/types/leaderboard.ts` gains
  `trionda_composite: number` on `LbEntryV4`.
- `frontend/src/lib/utils/leaderboardV4.ts` gains a sort comparator
  for the composite (vitest-covered).
- `frontend/src/lib/components/leaderboard/v4/StandingsTable.svelte`
  gains the desktop column, mobile lens, and inline flag
  rendering. Sort-state plumbing extends the existing
  `LbSortKey` union with `'trionda'`.
- A small `TriondaFlag.svelte` component encapsulates the ⚠
  rendering + tooltip state machine (provisional / permanent /
  merged). Reused identically in desktop and mobile lenses.
- Lens-mode store: small `lbLens` writable in
  `frontend/src/lib/stores/leaderboard.ts`, persisted via
  `localStorage['predictor:lb:lens']`.

### Eligibility flag — client-derived

The flag state is computed on the client, not stored server-side.
Trigger rules:

- **Provisional group-stage flag:** the entry with `position === 1`
  on the main leaderboard, while the response's `groupStageComplete`
  is `false` (already exposed via `/predictions/bonus/meta`).
- **Permanent group-stage flag:** persisted in `localStorage` once
  `groupStageComplete` flips `true`. The entry that held the live
  flag at that moment is recorded as the group-stage cash winner.
  *Future hardening:* a small server-side field could carry the
  locked winners after each phase end — out of scope for this spec,
  acceptable to ship client-derived first.
- **Provisional tournament flag:** the entry with `position === 1`
  while the tournament is not yet complete (i.e., the Final fixture
  is not yet FINISHED).
- **Permanent tournament flag:** same persistence pattern after the
  Final's score is settled.

## Out of scope

- The implementation plan itself (handled by the
  `superpowers:writing-plans` skill in a separate session).
- A separate `/leaderboard/trionda` view tab. The decision was to
  surface side-prize info within the existing standings (column
  on desktop, lens on mobile). A dedicated tab can be added later
  if the column drives enough curiosity that an editorial framing
  surface is warranted.
- Analytics events for the lens toggle. Low value; can be added
  later if engagement reporting calls for it.
- A broadcast email announcing the side prize. Out of scope for
  this spec — handled separately when the feature ships.
- Backfilling the composite into historical snapshots. The 30s
  cache rebuild populates it forward; historical snapshots stay
  on their current schema.

## Open follow-ups (verify before code)

- Confirm Q1–Q4 max-point values match the YAML scoring config
  (one-line check before locking the formula in code).
- Decide whether the live-tracking flag should debounce its
  position to avoid pulsing during volatile intra-match minutes.
  Default proposal: re-render on every leaderboard cache rebuild
  (30s cadence), no further debouncing — the existing rebuild
  cadence is already the natural smoothing layer.
- Confirm the rules-page wording with the user before publish.
