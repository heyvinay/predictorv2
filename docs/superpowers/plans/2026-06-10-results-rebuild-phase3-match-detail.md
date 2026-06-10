# V4 Results Rebuild — Phase 3: Match Detail Page

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `/results/[fixture_id]` as the V4 Match Detail page: nav strip with prev/next (click + ←/→ keys + swipe), played layout (hero with upset badge, pool list with ranks, your-pick card, points breakdown, rarity explainer, scoreline spread) and upcoming/locked layout (VS hero, who-picked-what with filters, payout teaser, pool split, predicted scorelines). Completes the v2.163.0 scope; version bump + changelog land at the end of this phase.

**Architecture:** Same composition pattern as Phase 2: one rewritten route shell + presentational components under `components/results/v4-match/`, with ALL derivation logic in two new pure utils (`matchDetailV4.ts`, `rarityNote.ts`) pinned by vitest. Data: fixture from the fixtures store, own pick from the predictions store (entry selection persists via `activeEntryId`), pool from `getCommunityPredictions` (403 pre-lock → placeholder), points math through the EXISTING parity-pinned `computeMatchPoints` / `logarithmicRarityBonus` from `matchBreakdown.ts` — no new scoring math.

**Visual contract:** `reference/v4-match.jsx` + bundle. Token map per HANDOVER §5.
**Spec:** §Page-by-page UI spec `/results/[fixture_id]`, §Microcopy lock (D.4), §Behavior notes (C.3).
**Branch:** `claude/results-page-revamp`.

## Deviations from the spec, decided here

1. **Rarity-note templates render CLIENT-side** (`rarityNote.ts`), not server-side. D.4 assumed the optional `RarityDetailOut` endpoint, which was never built (the spec's backend section only shipped points/rank/completeness). The four locked templates live in ONE pure util — still a single source of truth.
2. **Upset badge drops the cross-fixture tie-break.** The C.3 tie-break ("lowest share among qualifying fixtures wins") would require fetching `/community` for every fixture in the round (up to 24 requests per page view). The badge fires per-fixture on `winner share < 30% AND pool ≥ 10`; multiple fixtures in a round may show it. Tie-break deferred to the aggregate endpoint if it's ever built.
3. **No storyline copy on the hero.** The mockup's editorial storyline has no data source; the hero carries badge + score + meta only.
4. **Scoreline grids clamp to a 0–3+ axis** (mockup shows 0–3): real scores ≥ 3 bucket into the "3" row/col, labelled "3+".
5. **`CommunityPrediction.rank` types via `types/results.ts`** (`CommunityPredictionWithRank`), not the `types/index.ts` barrel — same WIP-lockout convention as Phase 2.

## File structure

**Create:**
```
frontend/src/lib/utils/matchDetailV4.ts        # split/spread/pool-rows/payouts/upset/prev-next derivations
frontend/src/lib/utils/matchDetailV4.test.ts
frontend/src/lib/utils/rarityNote.ts           # the four D.4 templates
frontend/src/lib/utils/rarityNote.test.ts
frontend/src/lib/components/results/v4-match/MatchNav.svelte
frontend/src/lib/components/results/v4-match/MatchHero.svelte          # played + upcoming variants via `mode`
frontend/src/lib/components/results/v4-match/YourPickCard.svelte       # played + upcoming variants via `mode`
frontend/src/lib/components/results/v4-match/PointsBreakdown.svelte
frontend/src/lib/components/results/v4-match/RarityExplainer.svelte
frontend/src/lib/components/results/v4-match/ScorelineSpread.svelte    # played + upcoming via `mode`
frontend/src/lib/components/results/v4-match/PoolList.svelte           # played: banked/missed
frontend/src/lib/components/results/v4-match/PoolPickedWhat.svelte     # upcoming: filter chips
frontend/src/lib/components/results/v4-match/PoolSplit.svelte          # upcoming: bar + outcome cards
```
Component count is lower than the handover's inventory: hero/your-pick/spread pairs merge into single components with a `mode: 'played' | 'upcoming'` prop (the layouts share most structure; two files each would duplicate markup).

**Modify:**
- `frontend/src/lib/types/results.ts` — add `CommunityPredictionWithRank`, `PoolRow`, `OutcomePayout`, `SpreadGrid` types
- `frontend/src/routes/results/[fixture_id]/+page.svelte` — full rewrite (V3 drill-down dies; its `matchDetail.ts` util stays on disk unused)

**Reuse, don't modify:** `matchBreakdown.ts` (`computeMatchPoints`, `logarithmicRarityBonus`, `rarityTier`), `resultsRounds.ts`, `flags.ts`, `teamName.ts`.

---

## Task 1: `rarityNote.ts` — the four D.4 templates (TDD)

Pure function: `rarityNote({n, total, pts, finished}) → string | null`.
- `n` = entries that called the same 1/X/2 outcome (incl. you); `total` = pool size; `pts` = rarity bonus for that outcome.
- Variants: solo (`n === 1`), consensus (`pts === 0`), banked (`finished`), default. Null when `total === 0` or `n === 0`.
- Templates exactly as locked in the spec §Microcopy lock. `pct` = one-decimal percentage.

Test cases: default ("Only 3 of 31 entries called this outcome (9.7%) — you'd earn +6 rarity if it holds."), solo, banked (— banked +6 rarity.), consensus ("Your outcome was the popular call (18 of 31, 58.1%) — no rarity bonus on consensus picks."), null guards.

Steps: write failing test → implement → pass → commit `feat(results-v4): rarity-note templates (D.4, client-side)`.

## Task 2: `matchDetailV4.ts` — derivations (TDD)

Exports (all pure):
```typescript
outcomeOf(h: number, a: number): '1' | 'X' | '2'
sideOf(h, a): 'home' | 'draw' | 'away'
poolSplit(preds): { counts: {home,draw,away}, pcts: {home,draw,away} }   // pcts rounded, sum ≤ 100
spreadGrid(preds, cap = 3): number[][]                                   // [home 0..cap][away 0..cap], clamped
poolRows(preds, actual, rules): { banked: PoolRow[], missed: PoolRow[] } // status exact/result/miss, pts via
    // computeMatchPoints with totalPredictors = preds.length and
    // correctPredictors = #(same outcome as actual); banked sorted pts desc then rank asc; you-flag by entry_reference
outcomePayouts(preds, rules): Record<'home'|'draw'|'away', OutcomePayout> // base = correct_outcome, rarity =
    // logarithmicRarityBonus(total, sideCount, cap), total = base+rarity, band via rarityTier
isUpset(preds, actualOutcome): boolean                                    // share < 0.30 && total >= 10 (C.3, no tie-break)
prevNextInRound(rounds, fid): { roundId, label, index, count, prevId, nextId } | null
```
`preds` are `CommunityPredictionWithRank[]`; "you" detection takes the entry's reference as an argument (the page knows `activeEntry`).

Test the branches: split percentages, grid clamping (5-1 lands in the 3+ bucket), pool rows points (exact = outcome+exact+rarity vs result-only vs miss=0), banked ordering, payout bands (consensus side → +0 rarity), upset boundaries (29%/10 yes, 31% no, 9 entries no), prev/next at edges (null prevId at index 0).

Commit `feat(results-v4): match-detail derivation util`.

## Task 3: types + components (svelte-check gate)

Add to `types/results.ts`: `CommunityPredictionWithRank = CommunityPrediction & { rank?: number | null }`, `PoolRow {name, entryName, reference, rank, pick, status, pts, you}`, `OutcomePayout {base, rarity, total, band, count, pct}`, `SpreadGrid = number[][]`.

Components per the mockup, established token conventions (no glow, `text-warning-text`, semantic tokens, mobile single-column → `lg:grid-cols-2`):

- **MatchNav** — back link to `/results?round={roundId}`, prev/next `<a>` buttons with team-name labels (hidden < 480px), position counter, disabled state at edges.
- **MatchHero** — `mode='played'`: optional `★ UPSET OF THE ROUND` badge, FULL TIME / LIVE pill, big score, group·date meta, winner emphasis. `mode='upcoming'`: 🔒 LOCKED · KO HH:MM badge, big VS, "Kicks off in {countdown}", meta.
- **YourPickCard** — played: verdict chip (NAILED IT / RIGHT WINNER / MISSED / NO PICK), pick + predicted-winner label, points pill. Upcoming: LOCKED IN status, pick, payout teaser `+{total}? IF {OUTCOME}` (dashed gold) from `outcomePayouts`.
- **PointsBreakdown** — "How those {total} points were assigned": base tile (EXACT SCORE +{exactTotal} / RIGHT WINNER +{outcome}) + rarity tile + total tile. Values from scoring-rules + the entry's PickPoints (B.1) — never recomputed locally.
- **RarityExplainer** — renders `rarityNote(...)` + the four-band scale with marker at the pick-share position. Hidden when no pick or pool unavailable.
- **ScorelineSpread** — 4×4(+axis) bubble grid; played: exact/actual/your rings; upcoming: side-tinted cells; legend per mode; foot "{HOME} ↓ · {AWAY} →".
- **PoolList** (played) — banked section (rank, name + YOU pill, pick, EXACT/RESULT pill with pts) + didn't-score section; sorted via `poolRows`.
- **PoolPickedWhat** (upcoming) — filter chips All/{Home}/Draw/{Away}, rows with rank ordinal ("{n}th overall" from B.3 rank), pick, side+band chip; foot "Points are provisional — they lock in the instant the final whistle blows."
- **PoolSplit** (upcoming) — 3-segment percentage bar + three outcome cards ({label} · n picks, band chip, "would pay +{total} (+{rarity} rarity)"), your side ringed.

Commit `feat(results-v4): match-detail components`.

## Task 4: rewrite `/results/[fixture_id]/+page.svelte`

- Load like the Results page (fixtures + rules + reactive entries/predictions on `$user` hydration); plus `getCommunityPredictions($page.params.fixture_id)` with 403 → `poolUnavailable = true` (placeholder card "Pool detail loads once the matchday window opens.").
- Mode: `finished|live → played` (live = "if FT now" provisional), else upcoming.
- Prev/next: `prevNextInRound(buildRounds($fixtures), fid)`; navigate with `goto(..., { noScroll: false })`; re-fetch community on param change (reactive on `$page.params.fixture_id`).
- Keyboard ←/→ (skip when target is input/textarea) + touch swipe (60px, 1.5× horizontal dominance, < 600ms) on the page container.
- Entry's own points: from the predictions store row for this fixture (`points` field, B.1) — drives PointsBreakdown + YourPick verdict.
- No slide animation (spec §8.7).

Gates: overlay → `npx vitest run` (all new tests) → `npm run check` (0 new errors) → commit `feat(results-v4): rewrite match-detail page`.

## Task 5: Chrome smoke

Temp gate-open tweak not needed (this route has no deadline gate — but row-clicks come from /results, so re-apply the tweak there if navigating via UI; direct URL works regardless). Verify against the dev DB's finished fixtures (Mexico–South Africa is exact-pick for Bold):
- Played layout renders: hero score, verdict NAILED IT, points breakdown +15, pool list with all 4 eligible entries + YOU pill + ranks, scoreline spread with rings, rarity explainer hidden (consensus → 0 rarity → only shows when pts>0... spec: hidden when rarity = 0 on a finished hit? D.4 consensus variant exists for live/pending; for finished with 0 rarity show consensus variant or hide? Mockup shows explainer only when rarity > 0 — follow mockup).
- Upcoming layout: any scheduled fixture → VS hero, LOCKED badge (deadline passed ⇒ pre-lock 403 → pool placeholder visible; payout teaser hidden when pool unavailable).
- Prev/next click + ArrowRight + edge-disable. Console: no new errors.
- Restore overlay fully; verify `git status` clean.

## Task 6: Close-out — version bump + changelog (end of v2.163.0 scope)

1. Bump `frontend/package.json` + `package-lock.json` (both spots) + `backend/pyproject.toml` → **2.163.0**.
2. Append changelog entry: `{version: "2.163.0", date: "2026-06-10", type: "feature", summary: "Brand-new Results experience: round-by-round scoreboard with live indicators, a match detail page for every fixture, and an admin completeness check.", commit: "pending"}`.
3. Commit `chore(version): bump to 2.163.0`. NO push (user-gated).
4. Full regression (backend pytest + frontend vitest) with overlay; restore; report.
```
