# /compare — Head-to-head Entry Comparison (Sub-project B)

**Date:** 2026-07-18 · **Status:** approved design, pending implementation
**Companions:** `2026-07-18-tournament-conclusion-backend-design.md` (A),
`2026-07-18-wrapup-page-design.md` (C)

## Goal

Answer "why didn't I win?" — a dedicated page putting any two entries side by
side: every pick, every point, and the ranked moments where the gap was made.
Also the home of the **shared comparison engine** that the wrap-up page's
"How the title was won" matrix consumes (one delta engine, two surfaces —
build the engine + shared pieces FIRST; C depends on them).

## Gating & release

- `frontend/src/routes/compare/+page.svelte` behind
  `V4_COMPARE_ENABLED = true` (kill switch) **AND** `$user?.is_admin === true`
  (staged rollout, V4 recipe). The admin previews in production during the
  Live phase; releasing = delete the `is_admin` clause + redeploy — timing is
  the admin's call (planned: shortly after the final; Monday nudge email
  points members at the app).
- Signed-in only (needs "your entry" context; the page is not part of the
  public guest surface). Guests hitting /compare get the standard sign-in
  redirect.
- **Zero new backend.** Both entries' picks + per-pick points come from the
  endpoints the leaderboard EntryDrawer already uses (open pool
  post-deadline). Per-fixture points already ride on
  `MatchPredictionRead.points` for finished fixtures.

## The engine — `frontend/src/lib/utils/compareEntries.ts`

Pure, vitest-covered. Input: two entries' full pick sets (match predictions
with points, bracket/TeamPrediction stage sets with advancement credits, bonus
answers with points). Output:

- `summary`: total delta + group/knockout/bonus deltas (A minus B).
- `matchRows[]`: per fixture — both picks, both points, delta, hit-class
  (exact/outcome/miss per side).
- `swings[]`: every element where the two entries scored differently — match
  rows, per-stage bracket credit diffs, bonus questions — ranked by |delta|,
  each with a machine-buildable why-line ("A exact (13.2) · B outcome (5)").
- `bracketRows[]`: per KO stage (R32→Winner, third_place excluded) — each
  side's team set, hits vs actual advancement, stage points.
- `bonusRows[]`: per current question — both answers, hit/miss, points.

Rarity numbers come from the served points (never recomputed client-side —
parity harness rule).

## Shared components (consumed by C)

- `CompareSummaryStrip.svelte` — the 4-tile delta strip (Total/Group/KO/Bonus).
- `SwingList.svelte` — ranked swing rows (label + why-line + ± chip),
  `limit`/`expandable` props.
Location: `frontend/src/lib/components/compare/`.

## Page layout (per approved mock)

1. **Picker bar** — Entry A (defaults to the viewer's best entry) ⇄ Entry B
   (defaults to the champion once concluded; current #1 before). Swap button.
   Each picker opens a dropdown with a **search field** — reuses the
   leaderboard's `searchRows()` (accent-insensitive, person OR entry name);
   rows show rank + points; keyboard navigable. Multi-entry holders can pick
   any of their own entries as A.
2. **Summary strip** (shared component).
3. **"Where the gap was made"** — top-5 swings, expandable to all
   (shared SwingList).
4. **Tabs: Matches / Bracket / Bonus** — full side-by-side tables with
   per-row deltas (green/red/neutral). Matches table columns: match, result,
   A pick, A pts, B pick, B pts, Δ.
5. URL state `?a=<entry_id>&b=<entry_id>` — shareable, and the deep-link
   target for C's "Compare my entry →" card and matrix footer link.

Mobile (≤560px): pickers stack; tables use FIFA 3-letter codes; summary strip
2×2; name cells ellipsize (390px checklist per the C spec applies).

## Analytics

`compare_opened` (with default-pair flag), `compare_pair_changed`,
`compare_tab_changed`, `compare_swings_expanded` — added to the `EventName`
union; `compare_opened` mapped in `FEATURE_GROUPS` as the "Compare" feature
(see A §9).

## Tests

- `compareEntries.test.ts`: summary deltas, swing ranking (mixed
  match/bracket/bonus), equal-points rows excluded from swings, bracket
  per-stage hit counts, bonus rows, third_place exclusion, zero-diff pair.
- Component smoke via existing vitest patterns; `npm run check` at 0 errors.

## Out of scope

- No backend endpoint; no persistence of comparisons; no guest access;
- No "compare vs pool average" mode (future idea, not this release).
