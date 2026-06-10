# V4 Results Rebuild — Phase 2: `/results` Page Core

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flag-gated stub at `/results` with the V4 round-tabbed Results page: entry switcher, points summary, round tabs with LIVE dots + auto-select, group/KO fixtures tables, Missed Picks + Progressing cards, Summary tab, Winner tab. Match Detail (`/results/[fixture_id]`) is Phase 3 — row clicks navigate there but the route keeps its current placeholder until then.

**Architecture:** One rewritten route shell (`/results/+page.svelte`) composing ~16 new components under `frontend/src/lib/components/results/v4/`. All data comes from existing endpoints (fixtures, entry predictions with the Phase 1 `points` field, bracket, leaderboard) plus one new tiny API client helper for `GET /api/leaderboard/scoring-rules`. Three new pure utils own the logic: round mapping, live-round derivation + default-round selection, and KO points/progressing/missed computation. **No hardcoded point values anywhere** — every number in copy templates from scoring-rules (spec C.1).

**Tech Stack:** SvelteKit 1.x + TypeScript, Tailwind + DaisyUI semantic tokens (premium-night / hybrid themes), vitest for utils + cell components.

**Spec:** [docs/superpowers/specs/2026-06-10-results-leaderboard-rebuild-design.md](../specs/2026-06-10-results-leaderboard-rebuild-design.md) — §Decisions, §Page-by-page UI spec `/results`, §Behavior notes, §Domain invariants.
**Visual contract:** `mockups/Results-redesign/V4-Results-MatchDetail-bundle.html` + `reference/v4-results.jsx` (layout, microcopy, spacing) + `reference/styles.css` (V4 sections). **Match it — don't redesign.** Token map: HANDOVER.md §5.

**Branch:** `claude/results-page-revamp` (Phase 1 commits `eb98a23`..`6431e4d` already on it).

---

## ⚠ Constraints discovered in Phase 1 — read before starting

1. **The user's main worktree carries uncommitted WIP in:** `frontend/src/lib/types/index.ts`, `frontend/src/lib/stores/phase.ts`, `frontend/src/routes/+layout.svelte`, `frontend/src/routes/+page.svelte`, `frontend/src/lib/server/news/aggregate.ts`, `.gitignore`. **This plan must NOT modify any of those files** — overlay-restore would clobber the user's edits. Consequences baked into this plan:
   - New types go in a NEW module `frontend/src/lib/types/results.ts`, NOT the `types/index.ts` barrel. The `points` field arrives via a local intersection type, not by editing the `MatchPrediction` interface.
   - `phase1Deadline` is imported read-only from `$stores/phase` (no edits to that file).
   - The latent `+layout.svelte` pathname TypeError stays unfixed in this phase (the file is the user's WIP; touching it risks their work). Noted for the release checklist.
2. **Vite file-watching on this Windows bind-mount is unreliable** — after overlaying files into the main worktree, `docker-compose restart frontend-dev` is often required for changes to serve. The dev server keeps a stale last-good build silently when a compile error exists (CLAUDE.md gotcha) — check `docker logs predictorv2-frontend-dev-1` FIRST when a change "doesn't show up."
3. **A stub exists at `frontend/src/lib/components/dev/DevPhaseSwitcher.svelte`** (untracked, main worktree only) keeping the user's WIP layout compiling. Leave it alone.
4. **Stage values are SINGULAR** in `Fixture.stage` (`quarter_final`, `semi_final`) but PLURAL in the `BracketPrediction` API response fields (`quarter_finals`, `semi_finals`) — a deliberate display convention. The round-mapping util must bridge this.
5. **KO stage point values are stage-specific** (R32:20, R16:30, QF:40, SF:50, F:75, W:100 per `config/worldcup2026.yml`) — NOT the flat +5 the mockup hardcodes. Every KO cell/explainer/card templates from scoring-rules. The mockup's "+5×2: 10" pattern becomes "+20×2: 40" on R32.

## How to run tests in this worktree

Same worktree-overlay pattern as Phase 1 (CLAUDE.md): edit here → `cp` to main worktree → run `docker-compose exec -T frontend-dev …` from main → restore (`git checkout --` for modified, `rm` for new) → commit here. **Restore ONLY files this plan owns; never run a broad checkout** (user WIP in the same tree).

Gates per commit:
```bash
docker-compose exec -T frontend-dev npx vitest run <your test files>
docker-compose exec -T frontend-dev npm run check   # 0 NEW errors (4 pre-existing errors live in the user's WIP files)
```

---

## File structure (Phase 2)

**Create:**
```
frontend/src/lib/types/results.ts                    # PickPoints, MatchPredictionWithPoints, RoundId, RoundDef, EntryRankInfo
frontend/src/lib/utils/resultsRounds.ts              # fixtures → rounds mapping, labels, date ranges, next-round chain
frontend/src/lib/utils/resultsRounds.test.ts
frontend/src/lib/utils/roundsLive.ts                 # roundsWithLive derivation + default-round selection (D.1)
frontend/src/lib/utils/roundsLive.test.ts
frontend/src/lib/utils/koPoints.ts                   # KO per-fixture hits/points, progressing, missed picks
frontend/src/lib/utils/koPoints.test.ts
frontend/src/lib/components/results/v4/RoundExplainer.svelte
frontend/src/lib/components/results/v4/EntryPillBar.svelte
frontend/src/lib/components/results/v4/PointsSummary.svelte
frontend/src/lib/components/results/v4/RoundTabs.svelte
frontend/src/lib/components/results/v4/PointsCellGroup.svelte
frontend/src/lib/components/results/v4/PointsCellGroup.test.ts
frontend/src/lib/components/results/v4/FixtureRowGroup.svelte
frontend/src/lib/components/results/v4/GroupRoundTable.svelte
frontend/src/lib/components/results/v4/BracketChip.svelte
frontend/src/lib/components/results/v4/PointsCellKo.svelte
frontend/src/lib/components/results/v4/FixtureRowKo.svelte
frontend/src/lib/components/results/v4/KnockoutRoundTable.svelte
frontend/src/lib/components/results/v4/MissedPicksCard.svelte
frontend/src/lib/components/results/v4/ProgressingCard.svelte
frontend/src/lib/components/results/v4/SummaryView.svelte
frontend/src/lib/components/results/v4/WinnerView.svelte
```

**Modify:**
```
frontend/src/lib/api/leaderboard.ts                  # + getScoringRules()
frontend/src/routes/results/+page.svelte             # full rewrite (the stub dies)
```

**Do NOT touch:** `types/index.ts`, `stores/phase.ts`, `+layout.svelte`, `+page.svelte`, `BreakdownCard.svelte` (V3 component stays during transition), anything Phase 2-flagged.

Component count note: `EntryPill` is folded into `EntryPillBar` (single consumer, trivial markup) and `SumBlock`/`SummaryRow` are folded into `SummaryView` — fewer files than the handover's original inventory, same UI.

---

# Group A — Types + API client

## Task 1: `types/results.ts` + `getScoringRules()` client

**Files:**
- Create: `frontend/src/lib/types/results.ts`
- Modify: `frontend/src/lib/api/leaderboard.ts`

- [ ] **Step 1: Create the types module**

Create `frontend/src/lib/types/results.ts`:

```typescript
/**
 * V4 Results page types (v2.163.0).
 *
 * Lives outside the `$lib/types` barrel deliberately — the barrel
 * (types/index.ts) carries uncommitted user WIP and must not be touched
 * during this phase. Import directly: `from '$lib/types/results'`.
 */

import type { MatchPrediction } from '$types';

/** Per-fixture points decomposition served by the backend for FINISHED
 *  fixtures (Phase 1, B.1). Mirrors backend PickPointsOut. */
export interface PickPoints {
	base: number;
	base_kind: 'miss' | 'result' | 'exact';
	rarity: number;
	total: number;
}

/** MatchPrediction as served since v2.163.0 — the `points` field exists on
 *  the wire but isn't declared on the barrel's MatchPrediction interface
 *  (user WIP lockout). V4 code paths cast through this. */
export type MatchPredictionWithPoints = MatchPrediction & {
	points?: PickPoints | null;
};

/** Round tab identifiers, in display order. */
export type RoundId =
	| 'summary'
	| 'r1'
	| 'r2'
	| 'r3'
	| 'r32'
	| 'r16'
	| 'qf'
	| 'sf'
	| 'f'
	| 'winner';

/** One resolved round: its fixtures plus display metadata. */
export interface RoundDef {
	id: RoundId;
	label: string;
	/** "11 – 18 Jun" — derived from fixture kickoffs; '' when no fixtures. */
	dates: string;
	isKnockout: boolean;
	/** Fixture IDs in kickoff order. Empty for summary/winner. */
	fixtureIds: string[];
}

/** Rank + points for an entry, pulled from the leaderboard for pills. */
export interface EntryRankInfo {
	position: number;
	total_points: number;
}

/** Scoring rules served by GET /api/leaderboard/scoring-rules. The page
 *  loads this once and threads it everywhere a point value appears in
 *  copy (spec C.1 — no hardcoded numbers). */
export interface ScoringRules {
	mode: string;
	match: {
		correct_outcome: number;
		exact_score: number;
		rarity_cap: number;
		[key: string]: number;
	};
	advancement: {
		round_of_32: number;
		round_of_16: number;
		quarter_final: number;
		semi_final: number;
		final: number;
		winner: number;
		[key: string]: number;
	};
}
```

- [ ] **Step 2: Add the API client helper**

In `frontend/src/lib/api/leaderboard.ts`, add at the end (and add the type import at the top of the file):

```typescript
import type { ScoringRules } from '$lib/types/results';

/** GET /api/leaderboard/scoring-rules — full scoring config including the
 *  per-stage advancement values. The V4 Results page templates every
 *  point value in user-facing copy from this (no hardcoded numbers). */
export async function getScoringRules(): Promise<ScoringRules> {
	return api.get<ScoringRules>('/leaderboard/scoring-rules');
}
```

Check the existing file's import style — if it imports `api` from `'./client'`, the new function uses the same instance. Place the type import with the other type imports at the top, not mid-file.

- [ ] **Step 3: Overlay + type-check**

```bash
# from the main worktree
cp <worktree>/frontend/src/lib/types/results.ts frontend/src/lib/types/results.ts
cp <worktree>/frontend/src/lib/api/leaderboard.ts frontend/src/lib/api/leaderboard.ts
docker-compose exec -T frontend-dev npm run check
```

Expected: no NEW errors (4 pre-existing from user WIP).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types/results.ts frontend/src/lib/api/leaderboard.ts
git commit -m "feat(results-v4): types module + scoring-rules client"
```

---

# Group B — Pure utils (the logic layer)

## Task 2: `resultsRounds.ts` — fixtures → rounds mapping

**Files:**
- Create: `frontend/src/lib/utils/resultsRounds.ts`
- Test: `frontend/src/lib/utils/resultsRounds.test.ts`

Mapping rules (spec + dev-DB verified):
- `r1` / `r2` / `r3` — group-stage fixtures bucketed by `match_number`: 1–24 / 25–48 / 49–72.
- `r32` / `r16` / `qf` / `sf` — stages `round_of_32` / `round_of_16` / `quarter_final` / `semi_final` (SINGULAR).
- `f` ("Finals") — stages `final` AND `third_place` (both fixtures appear on the Finals tab; only the `final` fixture gets bracket chips/points — `third_place` has no advancement value in the YAML).
- `summary` / `winner` — pseudo-rounds, no fixtures.
- Tab date sublabels derive from fixture kickoffs (min–max), e.g. "11 – 18 Jun". Not hardcoded.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/utils/resultsRounds.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import type { Fixture } from '$types';
import {
	buildRounds,
	NEXT_ROUND,
	ROUND_LABELS,
	roundIdForFixture,
	formatDateRange
} from './resultsRounds';

function fx(partial: Partial<Fixture>): Fixture {
	return {
		id: partial.id ?? crypto.randomUUID(),
		home_team: 'Home',
		away_team: 'Away',
		kickoff: '2026-06-11T18:00:00+00:00',
		stage: 'group',
		group: 'A',
		match_number: 1,
		status: 'scheduled',
		minute: null,
		is_locked: false,
		time_until_lock: null,
		score: null,
		...partial
	} as Fixture;
}

describe('roundIdForFixture', () => {
	it('buckets group fixtures into matchdays by match_number', () => {
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 1 }))).toBe('r1');
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 24 }))).toBe('r1');
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 25 }))).toBe('r2');
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 48 }))).toBe('r2');
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 49 }))).toBe('r3');
		expect(roundIdForFixture(fx({ stage: 'group', match_number: 72 }))).toBe('r3');
	});

	it('maps singular knockout stages', () => {
		expect(roundIdForFixture(fx({ stage: 'round_of_32' }))).toBe('r32');
		expect(roundIdForFixture(fx({ stage: 'round_of_16' }))).toBe('r16');
		expect(roundIdForFixture(fx({ stage: 'quarter_final' }))).toBe('qf');
		expect(roundIdForFixture(fx({ stage: 'semi_final' }))).toBe('sf');
		expect(roundIdForFixture(fx({ stage: 'final' }))).toBe('f');
		expect(roundIdForFixture(fx({ stage: 'third_place' }))).toBe('f');
	});

	it('returns null for unknown stages', () => {
		expect(roundIdForFixture(fx({ stage: 'mystery' }))).toBeNull();
	});
});

describe('buildRounds', () => {
	it('produces all ten rounds in display order with fixtures attached', () => {
		const fixtures = [
			fx({ id: 'a', stage: 'group', match_number: 3, kickoff: '2026-06-12T18:00:00+00:00' }),
			fx({ id: 'b', stage: 'group', match_number: 30, kickoff: '2026-06-19T18:00:00+00:00' }),
			fx({ id: 'c', stage: 'round_of_32', match_number: 73, kickoff: '2026-06-28T18:00:00+00:00' }),
			fx({ id: 'd', stage: 'final', match_number: 104, kickoff: '2026-07-19T18:00:00+00:00' })
		];
		const rounds = buildRounds(fixtures);
		expect(rounds.map((r) => r.id)).toEqual([
			'summary', 'r1', 'r2', 'r3', 'r32', 'r16', 'qf', 'sf', 'f', 'winner'
		]);
		expect(rounds.find((r) => r.id === 'r1')?.fixtureIds).toEqual(['a']);
		expect(rounds.find((r) => r.id === 'r2')?.fixtureIds).toEqual(['b']);
		expect(rounds.find((r) => r.id === 'r32')?.fixtureIds).toEqual(['c']);
		expect(rounds.find((r) => r.id === 'f')?.fixtureIds).toEqual(['d']);
		expect(rounds.find((r) => r.id === 'winner')?.fixtureIds).toEqual([]);
	});

	it('orders fixtures within a round by kickoff', () => {
		const fixtures = [
			fx({ id: 'late', stage: 'group', match_number: 9, kickoff: '2026-06-14T18:00:00+00:00' }),
			fx({ id: 'early', stage: 'group', match_number: 2, kickoff: '2026-06-11T20:00:00+00:00' })
		];
		const r1 = buildRounds(fixtures).find((r) => r.id === 'r1');
		expect(r1?.fixtureIds).toEqual(['early', 'late']);
	});

	it('marks knockout rounds', () => {
		const rounds = buildRounds([]);
		expect(rounds.find((r) => r.id === 'r1')?.isKnockout).toBe(false);
		expect(rounds.find((r) => r.id === 'r32')?.isKnockout).toBe(true);
		expect(rounds.find((r) => r.id === 'f')?.isKnockout).toBe(true);
	});
});

describe('formatDateRange', () => {
	it('renders same-day as a single date', () => {
		expect(
			formatDateRange('2026-07-19T16:00:00+00:00', '2026-07-19T20:00:00+00:00')
		).toBe('19 Jul');
	});
	it('renders a cross-day range', () => {
		expect(
			formatDateRange('2026-06-11T18:00:00+00:00', '2026-06-18T20:00:00+00:00')
		).toBe('11 – 18 Jun');
	});
	it('renders a cross-month range with both months', () => {
		expect(
			formatDateRange('2026-06-28T18:00:00+00:00', '2026-07-04T20:00:00+00:00')
		).toBe('28 Jun – 4 Jul');
	});
});

describe('NEXT_ROUND', () => {
	it('chains KO rounds and ends at the final', () => {
		expect(NEXT_ROUND.r32).toBe('r16');
		expect(NEXT_ROUND.r16).toBe('qf');
		expect(NEXT_ROUND.qf).toBe('sf');
		expect(NEXT_ROUND.sf).toBe('f');
		expect(NEXT_ROUND.f).toBeNull();
	});
});

describe('ROUND_LABELS', () => {
	it('has a label for every round', () => {
		for (const id of ['summary', 'r1', 'r2', 'r3', 'r32', 'r16', 'qf', 'sf', 'f', 'winner']) {
			expect(ROUND_LABELS[id as keyof typeof ROUND_LABELS]).toBeTruthy();
		}
	});
});
```

- [ ] **Step 2: Run to verify failure**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/utils/resultsRounds.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/src/lib/utils/resultsRounds.ts`:

```typescript
/**
 * Round mapping for the V4 Results page.
 *
 * WC2026 group fixtures bucket into three "rounds" (matchdays) by
 * match_number: MD1 = 1–24, MD2 = 25–48, MD3 = 49–72. Knockout rounds
 * map from Fixture.stage (SINGULAR values — the v2.161.0 invariant).
 * The "Finals" tab (id 'f') carries BOTH the third-place playoff and the
 * final; only the final fixture earns bracket chips/points.
 */

import type { Fixture } from '$types';
import type { RoundDef, RoundId } from '$lib/types/results';

export const ROUND_ORDER: RoundId[] = [
	'summary', 'r1', 'r2', 'r3', 'r32', 'r16', 'qf', 'sf', 'f', 'winner'
];

export const ROUND_LABELS: Record<RoundId, string> = {
	summary: 'Summary',
	r1: 'Round 1',
	r2: 'Round 2',
	r3: 'Round 3',
	r32: 'Round of 32',
	r16: 'Round of 16',
	qf: 'Quarter-Finals',
	sf: 'Semi-Finals',
	f: 'Finals',
	winner: 'Winner'
};

/** KO progression chain — which round a fixture's winners advance to. */
export const NEXT_ROUND: Record<string, RoundId | null> = {
	r32: 'r16',
	r16: 'qf',
	qf: 'sf',
	sf: 'f',
	f: null
};

/** Stage value (singular, as stored) per KO round — used to read the
 *  matching advancement points from scoring-rules and the matching
 *  bracket picks. */
export const ROUND_STAGE: Record<string, string> = {
	r32: 'round_of_32',
	r16: 'round_of_16',
	qf: 'quarter_final',
	sf: 'semi_final',
	f: 'final'
};

const KO_ROUNDS = new Set<RoundId>(['r32', 'r16', 'qf', 'sf', 'f']);

export function isKnockoutRound(id: RoundId): boolean {
	return KO_ROUNDS.has(id);
}

/** Which round a fixture belongs to; null for unknown stages. */
export function roundIdForFixture(f: Fixture): RoundId | null {
	if (f.stage === 'group') {
		const n = f.match_number ?? 0;
		if (n >= 1 && n <= 24) return 'r1';
		if (n >= 25 && n <= 48) return 'r2';
		if (n >= 49 && n <= 72) return 'r3';
		return null;
	}
	switch (f.stage) {
		case 'round_of_32':
			return 'r32';
		case 'round_of_16':
			return 'r16';
		case 'quarter_final':
			return 'qf';
		case 'semi_final':
			return 'sf';
		case 'final':
		case 'third_place':
			return 'f';
		default:
			return null;
	}
}

/** "11 – 18 Jun" / "28 Jun – 4 Jul" / "19 Jul" from two ISO kickoffs. */
export function formatDateRange(startIso: string, endIso: string): string {
	const start = new Date(startIso);
	const end = new Date(endIso);
	const day = (d: Date) => d.getUTCDate();
	const mon = (d: Date) => d.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' });
	if (day(start) === day(end) && mon(start) === mon(end)) {
		return `${day(end)} ${mon(end)}`;
	}
	if (mon(start) === mon(end)) {
		return `${day(start)} – ${day(end)} ${mon(end)}`;
	}
	return `${day(start)} ${mon(start)} – ${day(end)} ${mon(end)}`;
}

/** Resolve the full ten-round structure from the fixtures list. */
export function buildRounds(fixtures: Fixture[]): RoundDef[] {
	const byRound = new Map<RoundId, Fixture[]>();
	for (const f of fixtures) {
		const rid = roundIdForFixture(f);
		if (!rid) continue;
		const list = byRound.get(rid) ?? [];
		list.push(f);
		byRound.set(rid, list);
	}

	return ROUND_ORDER.map((id) => {
		const list = (byRound.get(id) ?? []).sort(
			(a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime()
		);
		const dates =
			list.length > 0
				? formatDateRange(list[0].kickoff, list[list.length - 1].kickoff)
				: id === 'summary'
				? 'All rounds'
				: '';
		return {
			id,
			label: ROUND_LABELS[id],
			dates,
			isKnockout: isKnockoutRound(id),
			fixtureIds: list.map((f) => f.id)
		};
	});
}
```

- [ ] **Step 4: Run to verify pass**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/utils/resultsRounds.test.ts
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils/resultsRounds.ts frontend/src/lib/utils/resultsRounds.test.ts
git commit -m "feat(results-v4): round mapping util (matchday buckets + KO stages)"
```

---

## Task 3: `roundsLive.ts` — LIVE-set + default-round selection (D.1)

**Files:**
- Create: `frontend/src/lib/utils/roundsLive.ts`
- Test: `frontend/src/lib/utils/roundsLive.test.ts`

Rules (spec D.1 + handover §8.1):
1. Any round containing a fixture with `status ∈ {live, halftime}` is "live".
2. Default selected round on mount: earliest live round in tab order → else round whose fixture-kickoff window contains today → else last completed round (latest round whose last kickoff is in the past) → else `r1`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/utils/roundsLive.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import type { Fixture } from '$types';
import type { RoundDef } from '$lib/types/results';
import { defaultRound, roundsWithLive } from './roundsLive';

function fx(id: string, status: string, kickoff: string): Fixture {
	return {
		id,
		home_team: 'H',
		away_team: 'A',
		kickoff,
		stage: 'group',
		group: 'A',
		match_number: 1,
		status,
		minute: null,
		is_locked: false,
		time_until_lock: null,
		score: null
	} as unknown as Fixture;
}

function round(id: string, fixtureIds: string[]): RoundDef {
	return {
		id: id as RoundDef['id'],
		label: id,
		dates: '',
		isKnockout: ['r32', 'r16', 'qf', 'sf', 'f'].includes(id),
		fixtureIds
	};
}

const ROUNDS: RoundDef[] = [
	round('summary', []),
	round('r1', ['a', 'b']),
	round('r2', ['c']),
	round('r3', []),
	round('r32', ['d']),
	round('r16', []),
	round('qf', []),
	round('sf', []),
	round('f', []),
	round('winner', [])
];

describe('roundsWithLive', () => {
	it('is empty when nothing is live', () => {
		const map = new Map([
			['a', fx('a', 'finished', '2026-06-11T18:00:00+00:00')],
			['c', fx('c', 'scheduled', '2026-06-18T18:00:00+00:00')]
		]);
		expect(roundsWithLive(ROUNDS, map).size).toBe(0);
	});

	it('contains the round of a live fixture (halftime counts)', () => {
		const map = new Map([
			['a', fx('a', 'live', '2026-06-11T18:00:00+00:00')],
			['c', fx('c', 'halftime', '2026-06-18T18:00:00+00:00')]
		]);
		const live = roundsWithLive(ROUNDS, map);
		expect(live.has('r1')).toBe(true);
		expect(live.has('r2')).toBe(true);
		expect(live.has('r3')).toBe(false);
	});
});

describe('defaultRound', () => {
	const fixturesByDate = new Map([
		['a', fx('a', 'finished', '2026-06-11T18:00:00+00:00')],
		['b', fx('b', 'finished', '2026-06-14T18:00:00+00:00')],
		['c', fx('c', 'scheduled', '2026-06-19T18:00:00+00:00')],
		['d', fx('d', 'scheduled', '2026-06-28T18:00:00+00:00')]
	]);

	it('LIVE round wins — earliest in tab order on a transition day', () => {
		const map = new Map(fixturesByDate);
		map.set('c', fx('c', 'live', '2026-06-18T18:00:00+00:00'));
		map.set('b', fx('b', 'live', '2026-06-18T15:00:00+00:00'));
		// both r1 (b) and r2 (c) live → earliest tab order = r1
		expect(defaultRound(ROUNDS, map, new Date('2026-06-18T19:00:00+00:00'))).toBe('r1');
	});

	it('falls back to the round whose window contains today', () => {
		expect(defaultRound(ROUNDS, fixturesByDate, new Date('2026-06-12T12:00:00+00:00'))).toBe('r1');
	});

	it('falls back to the last completed round between rounds', () => {
		// 2026-06-16: r1 windows ended (last kickoff 14 Jun), r2 hasn't started
		expect(defaultRound(ROUNDS, fixturesByDate, new Date('2026-06-16T12:00:00+00:00'))).toBe('r1');
	});

	it('falls back to r1 before the tournament', () => {
		expect(defaultRound(ROUNDS, fixturesByDate, new Date('2026-06-01T12:00:00+00:00'))).toBe('r1');
	});
});
```

- [ ] **Step 2: Run to verify failure**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/utils/roundsLive.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/src/lib/utils/roundsLive.ts`:

```typescript
/**
 * LIVE-round derivation + default-round selection (spec D.1).
 *
 * One derivation feeds BOTH the round tabs' pulsing dots and the Summary
 * rows' mirrored dots (spec D.1b) — single source so they can't drift.
 */

import type { Fixture } from '$types';
import type { RoundDef, RoundId } from '$lib/types/results';

const LIVE_STATUSES = new Set(['live', 'halftime']);

/** Set of round ids containing at least one LIVE fixture. */
export function roundsWithLive(
	rounds: RoundDef[],
	fixtureById: Map<string, Fixture>
): Set<RoundId> {
	const out = new Set<RoundId>();
	for (const r of rounds) {
		for (const fid of r.fixtureIds) {
			const f = fixtureById.get(fid);
			if (f && LIVE_STATUSES.has(f.status)) {
				out.add(r.id);
				break;
			}
		}
	}
	return out;
}

/** Default selected round on mount.
 *  1. earliest LIVE-containing round in tab order
 *  2. round whose first..last kickoff window contains `now` (day-granular)
 *  3. last completed round
 *  4. r1
 */
export function defaultRound(
	rounds: RoundDef[],
	fixtureById: Map<string, Fixture>,
	now: Date
): RoundId {
	const live = roundsWithLive(rounds, fixtureById);
	for (const r of rounds) {
		if (r.id !== 'summary' && r.id !== 'winner' && live.has(r.id)) return r.id;
	}

	const playable = rounds.filter(
		(r) => r.id !== 'summary' && r.id !== 'winner' && r.fixtureIds.length > 0
	);
	const windows = playable.map((r) => {
		const kicks = r.fixtureIds
			.map((fid) => fixtureById.get(fid)?.kickoff)
			.filter(Boolean)
			.map((k) => new Date(k as string).getTime());
		return { id: r.id, start: Math.min(...kicks), end: Math.max(...kicks) };
	});

	const DAY = 24 * 60 * 60 * 1000;
	const t = now.getTime();
	// inside a round window (end extended to end-of-day so the gap between
	// the last kickoff and midnight still counts as "inside")
	const inWindow = windows.find((w) => t >= w.start - DAY && t <= w.end + DAY);
	if (inWindow) return inWindow.id;

	const past = windows.filter((w) => w.end < t).sort((a, b) => b.end - a.end);
	if (past.length > 0) return past[0].id;

	return 'r1';
}
```

- [ ] **Step 4: Run to verify pass**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/utils/roundsLive.test.ts
```

Expected: all PASS. If the "window contains today" test fails on the ±DAY padding, adjust the test dates, not the padding — the padding exists so evening gaps inside a matchday don't fall through to "last completed".

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils/roundsLive.ts frontend/src/lib/utils/roundsLive.test.ts
git commit -m "feat(results-v4): live-round set + default-round selection (D.1)"
```

---

## Task 4: `koPoints.ts` — KO hits, progressing, missed picks

**Files:**
- Create: `frontend/src/lib/utils/koPoints.ts`
- Test: `frontend/src/lib/utils/koPoints.test.ts`

Rules:
- Bracket picks for a KO round come from `BracketPrediction` (plural field names: `round_of_32` is `round_of_32`, QF is `quarter_finals` — bridge to round ids).
- Per-fixture hits = |{home, away} ∩ stage picks| (matched by canonical team NAME — the bracket stores full team names, fixtures store full team names; no code conversion needed unlike the mockup).
- Per-fixture points = hits × `advancement[stage]` from scoring-rules. Banked regardless of fixture status (lineup-based timing, v2.161.0).
- `third_place` fixtures: no chips, no points (render `—`).
- Progressing: winners of FINISHED fixtures in this round (`Score.outcome` '1' → home, '2' → away; 'X' impossible for finished KO) split by membership in the NEXT round's picks.
- Missed picks (r32 only): entry's R32 picks minus teams appearing in any actual R32 fixture — only when ALL r32 fixtures have real team names (lineup set). No reason chip (spec F.1).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/utils/koPoints.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import type { BracketPrediction, Fixture } from '$types';
import {
	bracketPicksForRound,
	fixtureKoHits,
	missedR32Picks,
	progressingSplit,
	stagePointsForRound
} from './koPoints';

const BRACKET: BracketPrediction = {
	group_winners: {},
	round_of_32: ['Mexico', 'Senegal', 'Brazil', 'Italy'],
	round_of_16: ['Mexico', 'Brazil'],
	quarter_finals: ['Brazil'],
	semi_finals: ['Brazil'],
	final: ['Brazil'],
	winner: 'Brazil'
};

const RULES_ADVANCEMENT = {
	round_of_32: 20,
	round_of_16: 30,
	quarter_final: 40,
	semi_final: 50,
	final: 75,
	winner: 100
};

function fx(partial: Partial<Fixture>): Fixture {
	return {
		id: partial.id ?? crypto.randomUUID(),
		home_team: 'Mexico',
		away_team: 'Senegal',
		kickoff: '2026-06-28T18:00:00+00:00',
		stage: 'round_of_32',
		group: null,
		match_number: 73,
		status: 'scheduled',
		minute: null,
		is_locked: true,
		time_until_lock: null,
		score: null,
		...partial
	} as Fixture;
}

describe('bracketPicksForRound', () => {
	it('bridges plural API fields to round ids', () => {
		expect(bracketPicksForRound(BRACKET, 'r32')).toEqual(
			new Set(['Mexico', 'Senegal', 'Brazil', 'Italy'])
		);
		expect(bracketPicksForRound(BRACKET, 'qf')).toEqual(new Set(['Brazil']));
		expect(bracketPicksForRound(null, 'r32')).toEqual(new Set());
	});
});

describe('stagePointsForRound', () => {
	it('reads stage-specific values from scoring rules', () => {
		expect(stagePointsForRound(RULES_ADVANCEMENT, 'r32')).toBe(20);
		expect(stagePointsForRound(RULES_ADVANCEMENT, 'sf')).toBe(50);
		expect(stagePointsForRound(RULES_ADVANCEMENT, 'f')).toBe(75);
	});
});

describe('fixtureKoHits', () => {
	const picks = bracketPicksForRound(BRACKET, 'r32');

	it('counts 2 when both teams picked', () => {
		expect(fixtureKoHits(fx({}), picks)).toEqual({ home: true, away: true, hits: 2 });
	});

	it('counts 1 when one team picked', () => {
		expect(fixtureKoHits(fx({ away_team: 'France' }), picks)).toEqual({
			home: true,
			away: false,
			hits: 1
		});
	});

	it('counts 0 for a third_place fixture regardless of picks', () => {
		expect(fixtureKoHits(fx({ stage: 'third_place' }), picks)).toEqual({
			home: false,
			away: false,
			hits: 0
		});
	});
});

describe('progressingSplit', () => {
	it('splits finished-fixture winners by next-round membership', () => {
		const fixtures = [
			fx({
				id: 'w1',
				status: 'finished',
				score: { home_score: 2, away_score: 1, outcome: '1' } as Fixture['score']
			}), // Mexico wins — in r16 picks
			fx({
				id: 'w2',
				home_team: 'Spain',
				away_team: 'Brazil',
				status: 'finished',
				score: { home_score: 0, away_score: 2, outcome: '2' } as Fixture['score']
			}), // Brazil wins — in r16 picks
			fx({
				id: 'w3',
				home_team: 'France',
				away_team: 'Norway',
				status: 'finished',
				score: { home_score: 1, away_score: 0, outcome: '1' } as Fixture['score']
			}), // France wins — NOT in r16 picks
			fx({ id: 'w4', status: 'live' }) // live — excluded
		];
		const next = bracketPicksForRound(BRACKET, 'r16');
		const split = progressingSplit(fixtures, next);
		expect(split.inNext).toEqual(['Mexico', 'Brazil']);
		expect(split.notInNext).toEqual(['France']);
	});
});

describe('missedR32Picks', () => {
	it('lists picks absent from the seeded R32 lineup', () => {
		const fixtures = [
			fx({ home_team: 'Mexico', away_team: 'Senegal' }),
			fx({ id: 'x', home_team: 'Brazil', away_team: 'USA' })
		];
		const picks = bracketPicksForRound(BRACKET, 'r32');
		expect(missedR32Picks(fixtures, picks)).toEqual(['Italy']);
	});

	it('returns empty before the lineup is seeded (placeholder team names)', () => {
		const fixtures = [fx({ home_team: '1A', away_team: '2B' })];
		const picks = bracketPicksForRound(BRACKET, 'r32');
		expect(missedR32Picks(fixtures, picks)).toEqual([]);
	});
});
```

- [ ] **Step 2: Run to verify failure**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/utils/koPoints.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/src/lib/utils/koPoints.ts`:

```typescript
/**
 * Knockout points + progressing + missed-picks derivations (V4 Results).
 *
 * KO points are LINEUP-BANKED (v2.161.0): a pick pays the moment the team
 * is seeded into a stage fixture, not when the match finishes. So hits
 * render for scheduled and live KO fixtures too. Stage values are
 * stage-specific from scoring-rules (R32:20 … F:75) — never hardcoded.
 *
 * third_place fixtures live on the Finals tab but carry no advancement
 * value — no chips, no points.
 */

import type { BracketPrediction, Fixture } from '$types';
import type { RoundId } from '$lib/types/results';
import { ROUND_STAGE } from './resultsRounds';

/** Bracket API fields are PLURAL for QF/SF (display convention). */
const ROUND_TO_BRACKET_FIELD: Record<string, keyof BracketPrediction> = {
	r32: 'round_of_32',
	r16: 'round_of_16',
	qf: 'quarter_finals',
	sf: 'semi_finals',
	f: 'final'
};

/** Team names the entry picked to reach the given KO round. */
export function bracketPicksForRound(
	bracket: BracketPrediction | null,
	roundId: RoundId
): Set<string> {
	if (!bracket) return new Set();
	const field = ROUND_TO_BRACKET_FIELD[roundId];
	if (!field) return new Set();
	const value = bracket[field];
	return Array.isArray(value) ? new Set(value) : new Set();
}

/** Stage-specific advancement points for a KO round id. */
export function stagePointsForRound(
	advancement: Record<string, number>,
	roundId: RoundId
): number {
	const stage = ROUND_STAGE[roundId];
	return stage ? advancement[stage] ?? 0 : 0;
}

/** Per-fixture bracket hits. third_place earns nothing by design. */
export function fixtureKoHits(
	fixture: Fixture,
	roundPicks: Set<string>
): { home: boolean; away: boolean; hits: number } {
	if (fixture.stage === 'third_place') {
		return { home: false, away: false, hits: 0 };
	}
	const home = roundPicks.has(fixture.home_team);
	const away = roundPicks.has(fixture.away_team);
	return { home, away, hits: (home ? 1 : 0) + (away ? 1 : 0) };
}

/** Winners of FINISHED fixtures, split by next-round bracket membership. */
export function progressingSplit(
	fixtures: Fixture[],
	nextRoundPicks: Set<string>
): { inNext: string[]; notInNext: string[] } {
	const winners: string[] = [];
	for (const f of fixtures) {
		if (f.status !== 'finished' || !f.score) continue;
		if (f.stage === 'third_place') continue;
		if (f.score.outcome === '1') winners.push(f.home_team);
		else if (f.score.outcome === '2') winners.push(f.away_team);
		// 'X' on a finished knockout shouldn't happen (ET/pens resolve it);
		// skip defensively rather than guessing.
	}
	return {
		inNext: winners.filter((w) => nextRoundPicks.has(w)),
		notInNext: winners.filter((w) => !nextRoundPicks.has(w))
	};
}

/** Placeholder seed labels look like "1A" / "3ABCDF" / "W49" — short and
 *  containing digits. Real team names don't. */
function lineupSeeded(fixtures: Fixture[]): boolean {
	return (
		fixtures.length > 0 &&
		fixtures.every((f) => !/\d/.test(f.home_team) && !/\d/.test(f.away_team))
	);
}

/** R32 picks that never made it out of the groups — only meaningful once
 *  the R32 lineup is fully seeded with real team names. No reason chip
 *  (spec F.1). */
export function missedR32Picks(
	r32Fixtures: Fixture[],
	r32Picks: Set<string>
): string[] {
	if (!lineupSeeded(r32Fixtures)) return [];
	const seeded = new Set<string>();
	for (const f of r32Fixtures) {
		seeded.add(f.home_team);
		seeded.add(f.away_team);
	}
	return [...r32Picks].filter((team) => !seeded.has(team)).sort();
}
```

- [ ] **Step 4: Run to verify pass**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/utils/koPoints.test.ts
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils/koPoints.ts frontend/src/lib/utils/koPoints.test.ts
git commit -m "feat(results-v4): KO hits/progressing/missed-picks util (lineup-banked)"
```

---

# Group C — Leaf components

Layout reference for ALL components: `reference/v4-results.jsx` + `reference/styles.css` V4 sections. Token map (HANDOVER §5): `--primary` → `primary`, `--success-soft` → `bg-success/20`, `--warning-soft` + amber text → `bg-warning/20` + `text-warning-text` (NEVER bare `text-warning`), `--content-55` → `text-base-content/55`, `--content-30` → `text-base-content/30`. Active pills/tabs: faint gold outline `border-primary/55` + tinted fill `bg-primary/10` — **no glow** (the ONLY glow on the page is the Tournament-total card in SummaryView).

## Task 5: `RoundExplainer.svelte` (C.1 + C.2 templates)

**Files:**
- Create: `frontend/src/lib/components/results/v4/RoundExplainer.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
	/** Slim gold-tinted info strip explaining the active round's scoring.
	 *  EVERY number templates from scoring-rules (spec C.1) — a yml change
	 *  updates this copy with no code edit. KO copy re-anchors the banking
	 *  causation per spec C.2. Vocabulary: Result / Exact — never "Outcome". */
	import type { RoundId, ScoringRules } from '$lib/types/results';
	import { ROUND_LABELS, NEXT_ROUND, isKnockoutRound } from '$lib/utils/resultsRounds';
	import { stagePointsForRound } from '$lib/utils/koPoints';

	export let roundId: RoundId;
	export let rules: ScoringRules;
	/** "19 Jul" — the final's date, for the Winner copy. '' hides the clause. */
	export let finalDate = '';

	$: exactTotal = rules.match.correct_outcome + rules.match.exact_score;
	$: resultPts = rules.match.correct_outcome;
	$: winnerPts = rules.advancement.winner;
	$: roundLabel = ROUND_LABELS[roundId];
	$: stagePts = isKnockoutRound(roundId)
		? stagePointsForRound(rules.advancement, roundId)
		: 0;
	$: nextId = NEXT_ROUND[roundId] ?? null;
	$: nextLabel = nextId ? ROUND_LABELS[nextId] : null;
	$: prevLabel =
		roundId === 'r32'
			? 'the group stage'
			: roundId === 'r16'
			? 'the Round of 32'
			: roundId === 'qf'
			? 'the Round of 16'
			: roundId === 'sf'
			? 'the Quarter-Finals'
			: roundId === 'f'
			? 'the Semi-Finals'
			: '';
</script>

<div
	class="mt-4 flex items-start gap-2.5 rounded-btn border border-primary/25 bg-primary/10 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-base-content/80"
>
	<span class="text-primary" aria-hidden="true">ⓘ</span>
	{#if roundId === 'summary'}
		<span>
			<b>Summary</b> — points across every round of the tournament for the selected entry.
			<b>Group stage</b> rounds award <b>+{exactTotal} exact / +{resultPts} result</b> plus a
			<b>rarity bonus</b>; <b>knockout</b> rounds award stage-specific points per bracket pick
			that reaches the round. Tap any row to jump to that round.
		</span>
	{:else if roundId === 'winner'}
		<span>
			<b>How Winner scoring works:</b> you earn
			<b>+{winnerPts} if your champion pick lifts the trophy</b>. Points are awarded when the
			final whistle blows{finalDate ? ` on ${finalDate}` : ''}. No rarity bonus.
		</span>
	{:else if isKnockoutRound(roundId)}
		<span>
			<b>How {roundLabel} scoring works:</b> you earn
			<b>+{stagePts} for each team in your bracket that reaches this round</b>.
			<b>
				These points are banked from your bracket pick — you earned them when each team
				finished {prevLabel}. The match score below decides who walks to
				{nextLabel ?? 'the trophy'}, not these points.
			</b>
			No rarity bonus in the knockouts.
		</span>
	{:else}
		<span>
			<b>How {roundLabel} scoring works:</b> <b>+{exactTotal}</b> for the exact score,
			<b>+{resultPts}</b> for the correct result — plus a <b>rarity bonus</b> on top when your
			correct pick was one few others made.
		</span>
	{/if}
</div>
```

- [ ] **Step 2: Overlay + type-check** (`npm run check` — 0 new errors)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/results/v4/RoundExplainer.svelte
git commit -m "feat(results-v4): RoundExplainer with scoring-rules-templated copy (C.1/C.2)"
```

---

## Task 6: `EntryPillBar.svelte` + `PointsSummary.svelte`

**Files:**
- Create: `frontend/src/lib/components/results/v4/EntryPillBar.svelte`
- Create: `frontend/src/lib/components/results/v4/PointsSummary.svelte`

- [ ] **Step 1: Create EntryPillBar**

Rendered ONLY when 2+ entries (parent decides). Pills: name (+ DRAFT chip) · ordinal rank · pts. Active = faint gold outline. Horizontal scroll on mobile, active pill scrolled into view with `block: 'nearest'`.

```svelte
<script lang="ts">
	/** Entry switcher pill bar — V4 Results. Parent renders this only for
	 *  multi-entry users (spec: single-entry users never see a switcher). */
	import type { Entry } from '$lib/types/entry';
	import type { EntryRankInfo } from '$lib/types/results';

	export let entries: Entry[];
	export let selectedId: string;
	export let rankByEntry: Map<string, EntryRankInfo>;
	export let onSelect: (entryId: string) => void;

	function ordinal(n: number): string {
		const s = ['th', 'st', 'nd', 'rd'];
		const v = n % 100;
		return n + (s[(v - 20) % 10] || s[v] || s[0]);
	}

	function isDraft(e: Entry): boolean {
		// Entries store exposes phase statuses; treat anything not submitted
		// as draft for the chip. computeDisplayStatus lives in types/entry.
		return e.phase_1_status !== 'submitted';
	}

	function scrollIntoViewAction(node: HTMLElement, active: boolean) {
		function maybeScroll(isActive: boolean) {
			if (isActive)
				node.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
		}
		maybeScroll(active);
		return { update: maybeScroll };
	}
</script>

<div class="flex items-stretch gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Entries">
	{#each entries as e (e.id)}
		{@const active = e.id === selectedId}
		{@const rank = rankByEntry.get(e.id)}
		<button
			role="tab"
			aria-selected={active}
			use:scrollIntoViewAction={active}
			class="flex min-w-fit flex-col items-start gap-0.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-left transition-colors border-[1.5px] {active
				? 'border-primary/55 bg-primary/10'
				: 'border-transparent bg-base-300/40 hover:bg-base-300/60'}"
			on:click={() => onSelect(e.id)}
		>
			<span class="flex items-center gap-2">
				<span
					class="font-display text-[13px] leading-tight {active
						? 'text-base-content'
						: 'text-base-content/70'}">{e.display_name}</span
				>
				{#if isDraft(e)}
					<span
						class="rounded-badge bg-primary/20 px-1.5 py-px text-[9.5px] font-bold tracking-[0.08em] text-primary"
						>DRAFT</span
					>
				{/if}
			</span>
			<span class="text-[11px] font-bold">
				{#if rank}
					<span class={active ? 'text-primary' : 'text-base-content/55'}
						>{ordinal(rank.position)}</span
					>
					<span class="text-base-content/55"> · {rank.total_points} pts</span>
				{:else}
					<span class="text-base-content/30">—</span>
				{/if}
			</span>
		</button>
	{/each}
</div>
```

Note: verify the `Entry` type's phase-status field name in `$lib/types/entry` (`computeDisplayStatus(e, 'phase_1')` is the canonical helper used by `/admin/entries` — prefer reusing it over the raw field if the raw field doesn't exist; check before finalizing `isDraft`).

- [ ] **Step 2: Create PointsSummary**

Four cells one line: Result · Exact · Rarity · Total. Derived ENTIRELY from the per-fixture `points` list so it can't disagree with the tables (one source of truth):

```svelte
<script lang="ts">
	/** Top points-summary card — Result/Exact/Rarity/Total on ONE line.
	 *  Derived from the per-fixture points the backend computed (B.1), so
	 *  this card and the fixtures tables can never disagree. Match points
	 *  only by design (KO + winner points live on the Summary tab). */
	import type { MatchPredictionWithPoints } from '$lib/types/results';

	export let predictions: MatchPredictionWithPoints[];
	/** Stretches full-width for single-entry users (parent toggles). */
	export let fullWidth = false;

	$: scored = predictions.filter((p) => p.points != null);
	$: resultHits = scored.filter((p) => p.points!.base_kind === 'result').length;
	$: exactHits = scored.filter((p) => p.points!.base_kind === 'exact').length;
	$: rarityHits = scored.filter((p) => (p.points!.rarity ?? 0) > 0).length;
	$: resultPts = scored
		.filter((p) => p.points!.base_kind === 'result')
		.reduce((s, p) => s + p.points!.base, 0);
	$: exactPts = scored
		.filter((p) => p.points!.base_kind === 'exact')
		.reduce((s, p) => s + p.points!.base, 0);
	$: rarityPts = scored.reduce((s, p) => s + (p.points!.rarity ?? 0), 0);
	$: total = scored.reduce((s, p) => s + p.points!.total, 0);

	const CELLS = [
		{ key: 'result', letter: 'R', label: 'Results', chip: 'bg-warning/20 text-warning-text' },
		{ key: 'exact', letter: 'E', label: 'Exact', chip: 'bg-success/20 text-success' },
		{ key: 'rarity', letter: '★', label: 'Rarity', chip: 'bg-primary/20 text-primary' }
	];
</script>

<div
	class="flex items-stretch gap-3 rounded-box border border-base-300/60 bg-base-200 px-4 py-3 {fullWidth
		? 'w-full justify-between'
		: ''}"
>
	<div class="flex items-stretch gap-4">
		{#each CELLS as c (c.key)}
			{@const hits = c.key === 'result' ? resultHits : c.key === 'exact' ? exactHits : rarityHits}
			{@const pts = c.key === 'result' ? resultPts : c.key === 'exact' ? exactPts : rarityPts}
			<div class="flex flex-col gap-1">
				<span class="text-[10px] font-semibold uppercase tracking-[0.08em] text-base-content/55">
					{c.label}<span class="text-base-content/70"> · {hits}</span>
				</span>
				<span class="flex items-center gap-2">
					<span
						class="grid h-[18px] w-[18px] place-items-center rounded-[5px] font-display text-[10px] font-extrabold {c.chip}"
						>{c.letter}</span
					>
					<span class="font-display text-[15px] text-base-content">{pts}</span>
				</span>
			</div>
		{/each}
	</div>
	<div class="ml-auto flex flex-col items-end gap-1 border-l border-base-300/40 pl-4">
		<span class="text-[10px] font-semibold uppercase tracking-[0.08em] text-base-content/55"
			>Total</span
		>
		<span class="font-display text-[22px] leading-none text-primary">{total}</span>
	</div>
</div>
```

- [ ] **Step 3: Overlay + type-check** (`npm run check` — 0 new errors). Fix the `isDraft` field reference against the real Entry type if it differs.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/results/v4/EntryPillBar.svelte frontend/src/lib/components/results/v4/PointsSummary.svelte
git commit -m "feat(results-v4): entry switcher pills + points summary card"
```

---

## Task 7: `RoundTabs.svelte` — scrollable tabs, LIVE dots, auto-scroll

**Files:**
- Create: `frontend/src/lib/components/results/v4/RoundTabs.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
	/** Horizontal-scroll round tabs. Active = faint gold outline (NO glow).
	 *  A pulsing red dot marks rounds with a LIVE fixture; the same
	 *  roundsWithLive set drives the Summary rows (spec D.1b). On mount the
	 *  page pre-selects the live/default round and this component scrolls
	 *  it into view. */
	import type { RoundDef, RoundId } from '$lib/types/results';

	export let rounds: RoundDef[];
	export let selected: RoundId;
	export let liveRounds: Set<RoundId>;
	export let onSelect: (id: RoundId) => void;

	function scrollActive(node: HTMLElement, active: boolean) {
		function maybe(isActive: boolean) {
			if (isActive)
				node.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
		}
		maybe(active);
		return { update: maybe };
	}
</script>

<div
	role="tablist"
	aria-label="Rounds"
	class="sticky top-0 z-10 mt-4 flex items-stretch gap-1 overflow-x-auto rounded-full border border-base-300/55 bg-base-100/95 p-1 backdrop-blur [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
>
	{#each rounds as r (r.id)}
		{@const active = r.id === selected}
		<button
			role="tab"
			aria-selected={active}
			use:scrollActive={active}
			class="relative flex min-w-fit flex-none flex-col items-center gap-0.5 whitespace-nowrap rounded-full px-[13px] py-1.5 transition-colors border-[1.5px] {active
				? 'border-primary/55 bg-primary/10'
				: 'border-transparent hover:bg-base-300/30'}"
			on:click={() => onSelect(r.id)}
		>
			<span
				class="flex items-center gap-1.5 font-display text-[13px] leading-tight {active
					? 'text-base-content'
					: 'text-base-content/70'}"
			>
				{#if liveRounds.has(r.id)}
					<span
						class="h-[7px] w-[7px] rounded-full bg-error animate-pulse-soft"
						title="Match in progress"
					></span>
				{/if}
				{r.label}
			</span>
			<span
				class="text-[10px] font-bold tracking-[0.04em] {active
					? 'text-primary'
					: 'text-base-content/55'}">{r.dates}</span
			>
		</button>
	{/each}
</div>
```

Check `animate-pulse-soft` exists in `tailwind.config.js` (it's used by the countdown urgency tiers); if the utility is named differently, use the repo's name.

- [ ] **Step 2: Overlay + type-check.**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/results/v4/RoundTabs.svelte
git commit -m "feat(results-v4): round tabs with live dots + active auto-scroll"
```

---

## Task 8: Group-round table (PointsCellGroup + FixtureRowGroup + GroupRoundTable)

**Files:**
- Create: `frontend/src/lib/components/results/v4/PointsCellGroup.svelte`
- Create: `frontend/src/lib/components/results/v4/PointsCellGroup.test.ts`
- Create: `frontend/src/lib/components/results/v4/FixtureRowGroup.svelte`
- Create: `frontend/src/lib/components/results/v4/GroupRoundTable.svelte`

- [ ] **Step 1: Write the failing PointsCellGroup test**

Create `frontend/src/lib/components/results/v4/PointsCellGroup.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import PointsCellGroup from './PointsCellGroup.svelte';

describe('PointsCellGroup', () => {
	it('renders a muted dash when the fixture has not been played', () => {
		const { getByText } = render(PointsCellGroup, { points: null, played: false });
		expect(getByText('—')).toBeTruthy();
	});

	it('renders EXACT pill with rarity star when exact + rarity', () => {
		const { getByText, queryByLabelText } = render(PointsCellGroup, {
			points: { base: 15, base_kind: 'exact', rarity: 3, total: 18 },
			played: true
		});
		expect(getByText('EXACT')).toBeTruthy();
		expect(getByText('+18')).toBeTruthy();
		expect(queryByLabelText('rarity bonus applied')).toBeTruthy();
	});

	it('renders RESULT pill without star when no rarity', () => {
		const { getByText, queryByLabelText } = render(PointsCellGroup, {
			points: { base: 5, base_kind: 'result', rarity: 0, total: 5 },
			played: true
		});
		expect(getByText('RESULT')).toBeTruthy();
		expect(getByText('+5')).toBeTruthy();
		expect(queryByLabelText('rarity bonus applied')).toBeNull();
	});

	it('renders MISS 0 for a played miss', () => {
		const { getByText } = render(PointsCellGroup, {
			points: { base: 0, base_kind: 'miss', rarity: 0, total: 0 },
			played: true
		});
		expect(getByText('MISS')).toBeTruthy();
		expect(getByText('0')).toBeTruthy();
	});

	it('renders a dash for played-without-points (defensive)', () => {
		const { getByText } = render(PointsCellGroup, { points: null, played: true });
		expect(getByText('—')).toBeTruthy();
	});
});
```

If `@testing-library/svelte` is not installed, check `frontend/package.json`; if absent, render-test via `vitest` + `svelte/server`'s `render` (SSR string assertion) instead — keep the same five behavioural cases. Do NOT add a new dependency without checking what component tests already exist (`frontend/src/lib/**/*.test.ts`) and following that pattern.

- [ ] **Step 2: Run to verify failure**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/components/results/v4/PointsCellGroup.test.ts
```

- [ ] **Step 3: Create PointsCellGroup**

```svelte
<script lang="ts">
	/** Group-round per-fixture points pill: EXACT / RESULT / MISS + total.
	 *  `—` when the fixture hasn't produced points yet (not played) — spec
	 *  D.2 cell matrix. Tones: success / amber(text-warning-text) / muted. */
	import type { PickPoints } from '$lib/types/results';

	export let points: PickPoints | null;
	export let played: boolean;

	$: tone =
		points?.base_kind === 'exact'
			? 'bg-success/15 text-success'
			: points?.base_kind === 'result'
			? 'bg-warning/15 text-warning-text'
			: 'bg-base-300/30 text-base-content/55';
	$: label =
		points?.base_kind === 'exact' ? 'EXACT' : points?.base_kind === 'result' ? 'RESULT' : 'MISS';
	$: display = points ? (points.total > 0 ? `+${points.total}` : `${points.total}`) : '—';
</script>

{#if !points}
	<span class="text-xs text-base-content/30">—</span>
{:else}
	<span
		class="inline-flex items-center gap-1 rounded-badge px-2 py-0.5 text-[11px] font-bold {tone}"
		title={points.rarity > 0 ? `Includes +${points.rarity} rarity bonus` : undefined}
	>
		{#if points.rarity > 0}
			<span class="text-primary" aria-label="rarity bonus applied">★</span>
		{/if}
		<span class="tracking-[0.06em]">{label}</span>
		<span class="font-display text-[12.5px]">{display}</span>
	</span>
{/if}
```

(`played` is accepted for parity with the cell matrix but the render only branches on `points` — backend nulls points for unplayed fixtures, so the two agree; keep the prop for explicitness at call sites.)

- [ ] **Step 4: Run the cell test to verify pass.**

- [ ] **Step 5: Create FixtureRowGroup**

Desktop: 5-col grid `[minmax(130px,1fr)_86px_minmax(130px,1fr)_64px_118px]`. Mobile (<640px): stacked card per HANDOVER §7.5. LIVE: red left rail. Loser side 60% opacity. Row click navigates to Match Detail.

```svelte
<script lang="ts">
	import type { Fixture } from '$types';
	import type { MatchPredictionWithPoints } from '$lib/types/results';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import PointsCellGroup from './PointsCellGroup.svelte';

	export let fixture: Fixture;
	export let prediction: MatchPredictionWithPoints | undefined;
	export let striped = false;

	$: isLive = fixture.status === 'live' || fixture.status === 'halftime';
	$: played = fixture.status === 'finished';
	$: score = fixture.score;
	$: homeLoses = !!score && score.home_score < score.away_score;
	$: awayLoses = !!score && score.away_score < score.home_score;
	$: pickLabel = prediction ? `${prediction.home_score}-${prediction.away_score}` : null;
	$: dateLabel = new Date(fixture.kickoff).toLocaleDateString('en-GB', {
		day: 'numeric',
		month: 'short'
	});
</script>

<a
	href={`/results/${fixture.id}`}
	class="block border-t border-base-300/45 transition-colors first:border-t-0 hover:bg-primary/5
		{striped && !isLive ? 'bg-base-300/15' : ''}
		{isLive ? 'border-l-4 border-l-error bg-error/5' : ''}"
	aria-label={`Open match detail for ${displayTeamName(fixture.home_team)} vs ${displayTeamName(fixture.away_team)}`}
>
	<!-- Desktop grid -->
	<div
		class="hidden items-center gap-2.5 px-3.5 py-2.5 sm:grid sm:grid-cols-[minmax(130px,1fr)_86px_minmax(130px,1fr)_64px_118px]"
	>
		<div class="flex items-center justify-end gap-2 {homeLoses ? 'opacity-60' : ''}">
			<span class="truncate text-[13px] font-semibold">{displayTeamName(fixture.home_team)}</span>
			{#if hasFlag(fixture.home_team)}
				<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="h-auto w-[22px] rounded-sm" />
			{/if}
		</div>
		<div class="text-center">
			{#if score}
				<span class="font-display text-[15px] {isLive ? 'text-error' : ''}">
					<b class={homeLoses ? 'opacity-60' : ''}>{score.home_score}</b>
					<span class="px-0.5 text-base-content/40">–</span>
					<b class={awayLoses ? 'opacity-60' : ''}>{score.away_score}</b>
				</span>
			{:else}
				<span class="text-base-content/30">———</span>
			{/if}
			<div class="text-[10px] text-base-content/55">
				{#if isLive}
					<span class="font-bold text-error">LIVE {fixture.minute ? `${fixture.minute}'` : ''}</span>
				{:else}
					{dateLabel}{fixture.group ? ` · GRP ${fixture.group}` : ''}
				{/if}
			</div>
		</div>
		<div class="flex items-center gap-2 {awayLoses ? 'opacity-60' : ''}">
			{#if hasFlag(fixture.away_team)}
				<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="h-auto w-[22px] rounded-sm" />
			{/if}
			<span class="truncate text-[13px] font-semibold">{displayTeamName(fixture.away_team)}</span>
		</div>
		<div class="text-center">
			{#if pickLabel}
				<span class="font-display text-[13px]">{pickLabel}</span>
			{:else}
				<span class="text-[11px] text-base-content/30">No pick</span>
			{/if}
		</div>
		<div class="text-right">
			<PointsCellGroup points={prediction?.points ?? null} {played} />
		</div>
	</div>

	<!-- Mobile stacked card (HANDOVER §7.5) -->
	<div class="flex flex-col gap-1.5 px-3 py-2.5 sm:hidden">
		<div class="flex items-center justify-between gap-2">
			<span class="flex items-center gap-2 {homeLoses ? 'opacity-60' : ''}">
				{#if hasFlag(fixture.home_team)}
					<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="h-auto w-5 rounded-sm" />
				{/if}
				<span class="text-[13px] font-semibold">{displayTeamName(fixture.home_team)}</span>
			</span>
			<span class="font-display text-[15px] {isLive ? 'text-error' : ''}">
				{#if score}{score.home_score}{:else}<span class="text-base-content/30">—</span>{/if}
			</span>
		</div>
		<div class="flex items-center justify-between gap-2">
			<span class="flex items-center gap-2 {awayLoses ? 'opacity-60' : ''}">
				{#if hasFlag(fixture.away_team)}
					<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="h-auto w-5 rounded-sm" />
				{/if}
				<span class="text-[13px] font-semibold">{displayTeamName(fixture.away_team)}</span>
			</span>
			<span class="font-display text-[15px] {isLive ? 'text-error' : ''}">
				{#if score}{score.away_score}{:else}<span class="text-base-content/30">—</span>{/if}
			</span>
		</div>
		<div
			class="mt-0.5 flex items-center justify-between gap-2 border-t border-dashed border-base-300/40 pt-1.5 text-[12px]"
		>
			<span class="text-base-content/55">
				{#if isLive}
					<span class="font-bold text-error">LIVE {fixture.minute ? `${fixture.minute}'` : ''}</span>
				{:else}
					{dateLabel}
				{/if}
				· Your pick: <span class="font-display">{pickLabel ?? '—'}</span>
			</span>
			<PointsCellGroup points={prediction?.points ?? null} {played} />
		</div>
	</div>
</a>
```

- [ ] **Step 6: Create GroupRoundTable**

```svelte
<script lang="ts">
	/** Fixtures card for R1/R2/R3 — header, rows, gold round-subtotal footer. */
	import type { Fixture } from '$types';
	import type { MatchPredictionWithPoints, RoundDef } from '$lib/types/results';
	import FixtureRowGroup from './FixtureRowGroup.svelte';

	export let round: RoundDef;
	export let fixtures: Fixture[];
	export let predictionsByFixture: Map<string, MatchPredictionWithPoints>;

	$: subtotal = fixtures.reduce(
		(s, f) => s + (predictionsByFixture.get(f.id)?.points?.total ?? 0),
		0
	);
</script>

<div class="mt-4 overflow-hidden rounded-box border border-base-300/60 bg-base-200">
	<div
		class="hidden items-center gap-2.5 border-b border-base-300/50 bg-base-300/20 px-3.5 py-2 sm:grid sm:grid-cols-[minmax(130px,1fr)_86px_minmax(130px,1fr)_64px_118px]"
	>
		<div class="text-[11px] font-extrabold uppercase tracking-[0.1em] text-base-content/70">
			{round.label}
		</div>
		<div></div>
		<div></div>
		<div class="text-center text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
			Pick
		</div>
		<div class="text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
			Points
		</div>
	</div>
	<div
		class="border-b border-base-300/50 bg-base-300/20 px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.1em] text-base-content/70 sm:hidden"
	>
		{round.label}
	</div>

	{#if fixtures.length === 0}
		<div class="px-8 py-8 text-center text-[13px] text-base-content/55">
			No fixtures for this round yet.
		</div>
	{:else}
		{#each fixtures as f, i (f.id)}
			<FixtureRowGroup fixture={f} prediction={predictionsByFixture.get(f.id)} striped={i % 2 === 1} />
		{/each}
	{/if}

	<div class="flex items-center justify-end gap-3 border-t border-base-300/50 px-3.5 py-2.5">
		<span class="text-[12.5px] font-bold tracking-[0.06em] text-primary">Round Total</span>
		<span class="font-display text-[18px] {subtotal > 0 ? 'text-primary' : 'text-base-content/70'}"
			>{subtotal}</span
		>
	</div>
</div>
```

- [ ] **Step 7: Overlay all four files + run gates**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/components/results/v4/PointsCellGroup.test.ts
docker-compose exec -T frontend-dev npm run check
```

Expected: tests PASS, 0 new check errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/components/results/v4/PointsCellGroup.svelte frontend/src/lib/components/results/v4/PointsCellGroup.test.ts frontend/src/lib/components/results/v4/FixtureRowGroup.svelte frontend/src/lib/components/results/v4/GroupRoundTable.svelte
git commit -m "feat(results-v4): group-round fixtures table (desktop grid + mobile cards)"
```

---

## Task 9: Knockout table (BracketChip + PointsCellKo + FixtureRowKo + KnockoutRoundTable)

**Files:**
- Create: `frontend/src/lib/components/results/v4/BracketChip.svelte`
- Create: `frontend/src/lib/components/results/v4/PointsCellKo.svelte`
- Create: `frontend/src/lib/components/results/v4/FixtureRowKo.svelte`
- Create: `frontend/src/lib/components/results/v4/KnockoutRoundTable.svelte`

- [ ] **Step 1: Create BracketChip**

```svelte
<script lang="ts">
	/** ✓ MEX (green) when the team is in the entry's bracket for this
	 *  round; muted otherwise. Label = first 3 letters of the short name. */
	import { displayTeamName } from '$lib/utils/teamName';

	export let team: string;
	export let picked: boolean;

	$: label = displayTeamName(team).toUpperCase().slice(0, 3);
</script>

<span
	class="inline-flex items-center gap-0.5 rounded-badge px-1.5 py-0.5 text-[10px] font-extrabold tracking-[0.02em] {picked
		? 'bg-success/20 text-success'
		: 'bg-base-300/30 text-base-content/40'}"
>
	{picked ? '✓ ' : ''}{label}
</span>
```

- [ ] **Step 2: Create PointsCellKo**

```svelte
<script lang="ts">
	/** `+{stagePts}×{hits}: {total}` — stage points are stage-specific from
	 *  scoring-rules (R32:20 … F:75), never hardcoded (C.1). Banked at
	 *  lineup-set, so this renders for LIVE and upcoming fixtures too. */
	export let stagePoints: number;
	export let hits: number;
	/** False for third_place rows and unseeded fixtures → renders a dash. */
	export let applicable = true;

	$: total = stagePoints * hits;
	$: tone =
		hits === 2 ? 'text-success' : hits === 1 ? 'text-warning-text' : 'text-base-content/40';
</script>

{#if !applicable}
	<span class="text-xs text-base-content/30">—</span>
{:else}
	<span class="inline-flex items-baseline gap-1 {tone}">
		<span class="text-[11px] font-bold">+{stagePoints}×{hits}:</span>
		<b class="font-display text-[14px]">{total}</b>
	</span>
{/if}
```

- [ ] **Step 3: Create FixtureRowKo**

Same 5-col grid as the group row; 4th column = bracket chips; LIVE indicator stays under the score (never in the points cell). Placeholder seeds (e.g. "1A") render as a dashed TBD slot.

```svelte
<script lang="ts">
	import type { Fixture } from '$types';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import BracketChip from './BracketChip.svelte';
	import PointsCellKo from './PointsCellKo.svelte';

	export let fixture: Fixture;
	export let roundPicks: Set<string>;
	export let stagePoints: number;
	export let striped = false;

	$: isLive = fixture.status === 'live' || fixture.status === 'halftime';
	$: score = fixture.score;
	$: homeLoses = !!score && score.home_score < score.away_score;
	$: awayLoses = !!score && score.away_score < score.home_score;
	$: isThirdPlace = fixture.stage === 'third_place';
	$: seeded = !/\d/.test(fixture.home_team) && !/\d/.test(fixture.away_team);
	$: homePicked = seeded && !isThirdPlace && roundPicks.has(fixture.home_team);
	$: awayPicked = seeded && !isThirdPlace && roundPicks.has(fixture.away_team);
	$: hits = (homePicked ? 1 : 0) + (awayPicked ? 1 : 0);
	$: dateLabel = new Date(fixture.kickoff).toLocaleDateString('en-GB', {
		day: 'numeric',
		month: 'short'
	});
</script>

<a
	href={`/results/${fixture.id}`}
	class="block border-t border-base-300/45 transition-colors first:border-t-0 hover:bg-primary/5
		{striped && !isLive ? 'bg-base-300/15' : ''}
		{isLive ? 'border-l-4 border-l-error bg-error/5' : ''}"
	aria-label={`Open match detail for ${displayTeamName(fixture.home_team)} vs ${displayTeamName(fixture.away_team)}`}
>
	<!-- Desktop grid -->
	<div
		class="hidden items-center gap-2.5 px-3.5 py-2.5 sm:grid sm:grid-cols-[minmax(130px,1fr)_86px_minmax(130px,1fr)_64px_118px]"
	>
		<div class="flex items-center justify-end gap-2 {homeLoses ? 'opacity-60' : ''}">
			<span class="truncate text-[13px] font-semibold">
				{seeded ? displayTeamName(fixture.home_team) : 'TBD'}
			</span>
			{#if seeded && hasFlag(fixture.home_team)}
				<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="h-auto w-[22px] rounded-sm" />
			{:else if !seeded}
				<span
					class="grid h-4 w-[22px] place-items-center rounded-sm border border-dashed border-base-300/80 bg-base-300/40 text-[8px] font-extrabold text-base-content/55"
					>{fixture.home_team}</span
				>
			{/if}
		</div>
		<div class="text-center">
			{#if score}
				<span class="font-display text-[15px] {isLive ? 'text-error' : ''}">
					<b class={homeLoses ? 'opacity-60' : ''}>{score.home_score}</b>
					<span class="px-0.5 text-base-content/40">–</span>
					<b class={awayLoses ? 'opacity-60' : ''}>{score.away_score}</b>
				</span>
			{:else}
				<span class="text-base-content/30">———</span>
			{/if}
			<div class="text-[10px] text-base-content/55">
				{#if isLive}
					<span class="font-bold text-error">LIVE {fixture.minute ? `${fixture.minute}'` : ''}</span>
				{:else}
					{dateLabel}
				{/if}
			</div>
		</div>
		<div class="flex items-center gap-2 {awayLoses ? 'opacity-60' : ''}">
			{#if seeded && hasFlag(fixture.away_team)}
				<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="h-auto w-[22px] rounded-sm" />
			{:else if !seeded}
				<span
					class="grid h-4 w-[22px] place-items-center rounded-sm border border-dashed border-base-300/80 bg-base-300/40 text-[8px] font-extrabold text-base-content/55"
					>{fixture.away_team}</span
				>
			{/if}
			<span class="truncate text-[13px] font-semibold">
				{seeded ? displayTeamName(fixture.away_team) : 'TBD'}
			</span>
		</div>
		<div class="flex items-center justify-center gap-1">
			{#if !seeded || isThirdPlace}
				<span class="text-xs text-base-content/30">—</span>
			{:else}
				<BracketChip team={fixture.home_team} picked={homePicked} />
				<BracketChip team={fixture.away_team} picked={awayPicked} />
			{/if}
		</div>
		<div class="text-right">
			<PointsCellKo {stagePoints} {hits} applicable={seeded && !isThirdPlace} />
		</div>
	</div>

	<!-- Mobile stacked card -->
	<div class="flex flex-col gap-1.5 px-3 py-2.5 sm:hidden">
		<div class="flex items-center justify-between gap-2">
			<span class="flex items-center gap-2 {homeLoses ? 'opacity-60' : ''}">
				{#if seeded && hasFlag(fixture.home_team)}
					<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="h-auto w-5 rounded-sm" />
				{/if}
				<span class="text-[13px] font-semibold"
					>{seeded ? displayTeamName(fixture.home_team) : fixture.home_team}</span
				>
			</span>
			<span class="font-display text-[15px] {isLive ? 'text-error' : ''}">
				{#if score}{score.home_score}{:else}<span class="text-base-content/30">—</span>{/if}
			</span>
		</div>
		<div class="flex items-center justify-between gap-2">
			<span class="flex items-center gap-2 {awayLoses ? 'opacity-60' : ''}">
				{#if seeded && hasFlag(fixture.away_team)}
					<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="h-auto w-5 rounded-sm" />
				{/if}
				<span class="text-[13px] font-semibold"
					>{seeded ? displayTeamName(fixture.away_team) : fixture.away_team}</span
				>
			</span>
			<span class="font-display text-[15px] {isLive ? 'text-error' : ''}">
				{#if score}{score.away_score}{:else}<span class="text-base-content/30">—</span>{/if}
			</span>
		</div>
		<div
			class="mt-0.5 flex items-center justify-between gap-2 border-t border-dashed border-base-300/40 pt-1.5"
		>
			<span class="flex items-center gap-1 text-[12px] text-base-content/55">
				{#if isLive}
					<span class="font-bold text-error">LIVE {fixture.minute ? `${fixture.minute}'` : ''}</span>
					<span>·</span>
				{/if}
				{#if !seeded || isThirdPlace}
					<span class="text-base-content/30">—</span>
				{:else}
					<BracketChip team={fixture.home_team} picked={homePicked} />
					<BracketChip team={fixture.away_team} picked={awayPicked} />
				{/if}
			</span>
			<PointsCellKo {stagePoints} {hits} applicable={seeded && !isThirdPlace} />
		</div>
	</div>
</a>
```

- [ ] **Step 4: Create KnockoutRoundTable**

```svelte
<script lang="ts">
	/** Fixtures card for KO rounds — bracket-call column + stage-specific
	 *  points. Subtotal counts each fixture's hits × stage points. */
	import type { Fixture } from '$types';
	import type { RoundDef } from '$lib/types/results';
	import FixtureRowKo from './FixtureRowKo.svelte';
	import { fixtureKoHits } from '$lib/utils/koPoints';

	export let round: RoundDef;
	export let fixtures: Fixture[];
	export let roundPicks: Set<string>;
	export let stagePoints: number;

	$: subtotal = fixtures.reduce(
		(s, f) => s + fixtureKoHits(f, roundPicks).hits * stagePoints,
		0
	);
</script>

<div class="mt-4 overflow-hidden rounded-box border border-base-300/60 bg-base-200">
	<div
		class="hidden items-center gap-2.5 border-b border-base-300/50 bg-base-300/20 px-3.5 py-2 sm:grid sm:grid-cols-[minmax(130px,1fr)_86px_minmax(130px,1fr)_64px_118px]"
	>
		<div class="text-[11px] font-extrabold uppercase tracking-[0.1em] text-base-content/70">
			{round.label}
		</div>
		<div></div>
		<div></div>
		<div class="text-center text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
			Your bracket
		</div>
		<div class="text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
			Points
		</div>
	</div>
	<div
		class="border-b border-base-300/50 bg-base-300/20 px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.1em] text-base-content/70 sm:hidden"
	>
		{round.label}
	</div>

	{#if fixtures.length === 0}
		<div class="px-8 py-8 text-center text-[13px] text-base-content/55">
			No fixtures for this round yet.
		</div>
	{:else}
		{#each fixtures as f, i (f.id)}
			<FixtureRowKo fixture={f} {roundPicks} {stagePoints} striped={i % 2 === 1} />
		{/each}
	{/if}

	<div class="flex items-center justify-end gap-3 border-t border-base-300/50 px-3.5 py-2.5">
		<span class="text-[12.5px] font-bold tracking-[0.06em] text-primary">Round Total</span>
		<span class="font-display text-[18px] {subtotal > 0 ? 'text-primary' : 'text-base-content/70'}"
			>{subtotal}</span
		>
	</div>
</div>
```

- [ ] **Step 5: Overlay + gates** (`npm run check` — 0 new errors).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/components/results/v4/BracketChip.svelte frontend/src/lib/components/results/v4/PointsCellKo.svelte frontend/src/lib/components/results/v4/FixtureRowKo.svelte frontend/src/lib/components/results/v4/KnockoutRoundTable.svelte
git commit -m "feat(results-v4): knockout fixtures table with bracket chips + stage points"
```

---

## Task 10: `MissedPicksCard.svelte` + `ProgressingCard.svelte`

**Files:**
- Create: `frontend/src/lib/components/results/v4/MissedPicksCard.svelte`
- Create: `frontend/src/lib/components/results/v4/ProgressingCard.svelte`

- [ ] **Step 1: Create MissedPicksCard**

Dashed red border. Pills = flag + name ONLY (no reason chip — spec F.1). Subtitle templates the unrealised value from stage points.

```svelte
<script lang="ts">
	/** R32 bracket picks that bombed out in the group stage. Pills carry
	 *  flag + name only (spec F.1 — no reason chip). The unrealised value
	 *  templates from stage points (C.1). */
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	export let roundLabel: string;
	export let teams: string[];
	export let stagePoints: number;
</script>

<div class="mt-4 rounded-box border border-dashed border-error/50 bg-error/5 p-4">
	<div class="flex items-start gap-3">
		<div
			class="grid h-7 w-7 flex-none place-items-center rounded-full bg-error/20 text-[13px] font-bold text-error"
		>
			✗
		</div>
		<div>
			<div class="text-[13px] font-bold">{roundLabel} picks that didn't make it</div>
			<div class="text-[11.5px] text-base-content/55">
				{teams.length} of your bracket picks were knocked out in the group stage
				<span class="ml-1.5 text-error">· –{teams.length * stagePoints} unrealised</span>
			</div>
		</div>
	</div>
	<div class="mt-3 flex flex-wrap gap-2">
		{#each teams as team (team)}
			<span
				class="inline-flex items-center gap-1.5 rounded-full border border-error/30 bg-base-200 px-2.5 py-1 text-[12px] font-semibold"
			>
				{#if hasFlag(team)}
					<img src={getFlagUrl(team, 'sm')} alt="" class="h-auto w-4 rounded-sm" />
				{/if}
				<span>{displayTeamName(team)}</span>
			</span>
		{/each}
	</div>
</div>
```

- [ ] **Step 2: Create ProgressingCard**

```svelte
<script lang="ts">
	/** Winners of this round's finished fixtures, split by membership in
	 *  the entry's NEXT-round bracket. Locked-in value templates from the
	 *  NEXT stage's points (C.1). */
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	export let nextLabel: string;
	export let inNext: string[];
	export let notInNext: string[];
	export let nextStagePoints: number;

	$: banked = inNext.length * nextStagePoints;
	$: totalWinners = inNext.length + notInNext.length;
</script>

<div class="mt-4 rounded-box border border-success/40 bg-success/5 p-4">
	<div class="flex items-start gap-3">
		<div
			class="grid h-7 w-7 flex-none place-items-center rounded-full bg-success/20 text-[13px] font-bold text-success"
		>
			→
		</div>
		<div>
			<div class="text-[13px] font-bold">Progressing to {nextLabel}</div>
			<div class="text-[11.5px] text-base-content/55">
				<b class="text-success">{inNext.length}</b> of {totalWinners} fixture winners are in your
				{nextLabel} bracket
				<span class="ml-1.5 text-success">· locks in +{banked} on the {nextLabel} page</span>
			</div>
		</div>
	</div>
	<div class="mt-3 flex flex-wrap gap-2">
		{#each inNext as team (team)}
			<span
				class="inline-flex items-center gap-1.5 rounded-full border border-success/40 bg-base-200 px-2.5 py-1 text-[12px] font-semibold"
			>
				{#if hasFlag(team)}
					<img src={getFlagUrl(team, 'sm')} alt="" class="h-auto w-4 rounded-sm" />
				{/if}
				<span>{displayTeamName(team)}</span>
				<span class="rounded-badge bg-success/20 px-1.5 text-[10px] font-bold text-success"
					>+{nextStagePoints}</span
				>
			</span>
		{/each}
		{#each notInNext as team (team)}
			<span
				class="inline-flex items-center gap-1.5 rounded-full border border-base-300/60 bg-base-200 px-2.5 py-1 text-[12px] font-semibold opacity-70"
			>
				{#if hasFlag(team)}
					<img src={getFlagUrl(team, 'sm')} alt="" class="h-auto w-4 rounded-sm" />
				{/if}
				<span>{displayTeamName(team)}</span>
				<span class="rounded-badge bg-base-300/40 px-1.5 text-[10px] font-bold text-base-content/55"
					>not picked</span
				>
			</span>
		{/each}
	</div>
</div>
```

- [ ] **Step 3: Overlay + type-check.** **Step 4: Commit**

```bash
git add frontend/src/lib/components/results/v4/MissedPicksCard.svelte frontend/src/lib/components/results/v4/ProgressingCard.svelte
git commit -m "feat(results-v4): missed-picks + progressing cards"
```

---

## Task 11: `SummaryView.svelte` + `WinnerView.svelte`

**Files:**
- Create: `frontend/src/lib/components/results/v4/SummaryView.svelte`
- Create: `frontend/src/lib/components/results/v4/WinnerView.svelte`

- [ ] **Step 1: Create SummaryView**

Three subtotal cards (Group / Knockouts / Tournament total — the grand card is THE ONLY glow on the page) + per-round table with LIVE dots (D.1b), clickable rows jumping to tabs.

```svelte
<script lang="ts">
	/** Summary tab — tournament-wide decomposition. The grand-total card is
	 *  the page's single glow element. Per-round rows mirror the round-tab
	 *  LIVE dots from the same roundsWithLive set (D.1b). Tournament total
	 *  here = match + bracket + winner rounds; bonus-question points are a
	 *  separate surface (leaderboard) by design — noted in spec. */
	import type { Fixture } from '$types';
	import type {
		MatchPredictionWithPoints,
		RoundDef,
		RoundId,
		ScoringRules
	} from '$lib/types/results';
	import type { BracketPrediction } from '$types';
	import { bracketPicksForRound, fixtureKoHits, stagePointsForRound } from '$lib/utils/koPoints';

	export let rounds: RoundDef[];
	export let fixtureById: Map<string, Fixture>;
	export let predictionsByFixture: Map<string, MatchPredictionWithPoints>;
	export let bracket: BracketPrediction | null;
	export let rules: ScoringRules;
	export let liveRounds: Set<RoundId>;
	export let onJump: (id: RoundId) => void;

	interface Row {
		id: RoundId;
		label: string;
		dates: string;
		isKO: boolean;
		isWinner: boolean;
		pending: boolean;
		exact: number;
		result: number;
		rarity: number;
		hits: number;
		total: number;
	}

	function championOfFinal(): string | null {
		const fRound = rounds.find((r) => r.id === 'f');
		for (const fid of fRound?.fixtureIds ?? []) {
			const f = fixtureById.get(fid);
			if (f && f.stage === 'final' && f.status === 'finished' && f.score) {
				if (f.score.outcome === '1') return f.home_team;
				if (f.score.outcome === '2') return f.away_team;
			}
		}
		return null;
	}

	$: rows = rounds
		.filter((r) => r.id !== 'summary')
		.map((r): Row => {
			if (r.id === 'winner') {
				const champion = championOfFinal();
				const correct = !!champion && !!bracket?.winner && champion === bracket.winner;
				return {
					id: r.id, label: r.label, dates: r.dates || '—',
					isKO: true, isWinner: true, pending: !champion,
					exact: 0, result: 0, rarity: 0,
					hits: correct ? 1 : 0,
					total: correct ? rules.advancement.winner : 0
				};
			}
			if (r.isKnockout) {
				const picks = bracketPicksForRound(bracket, r.id);
				const stagePts = stagePointsForRound(rules.advancement, r.id);
				let hits = 0;
				for (const fid of r.fixtureIds) {
					const f = fixtureById.get(fid);
					if (f) hits += fixtureKoHits(f, picks).hits;
				}
				return {
					id: r.id, label: r.label, dates: r.dates, isKO: true, isWinner: false,
					pending: false, exact: 0, result: 0, rarity: 0, hits, total: hits * stagePts
				};
			}
			let exact = 0, result = 0, rarity = 0, total = 0;
			for (const fid of r.fixtureIds) {
				const pts = predictionsByFixture.get(fid)?.points;
				if (!pts) continue;
				total += pts.total;
				if (pts.base_kind === 'exact') exact++;
				else if (pts.base_kind === 'result') result++;
				if (pts.rarity > 0) rarity++;
			}
			return {
				id: r.id, label: r.label, dates: r.dates, isKO: false, isWinner: false,
				pending: false, exact, result, rarity, hits: 0, total
			};
		});

	$: groupTotal = rows.filter((b) => !b.isKO).reduce((s, b) => s + b.total, 0);
	$: koTotal = rows.filter((b) => b.isKO).reduce((s, b) => s + b.total, 0);
	$: grand = groupTotal + koTotal;
	$: totalExact = rows.reduce((s, b) => s + b.exact, 0);
	$: totalResult = rows.reduce((s, b) => s + b.result, 0);
	$: totalRarity = rows.reduce((s, b) => s + b.rarity, 0);
	$: totalHits = rows.filter((b) => b.isKO && !b.isWinner).reduce((s, b) => s + b.hits, 0);
</script>

<div class="mt-4 flex flex-col gap-4">
	<!-- Subtotal cards -->
	<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
		<div class="flex flex-col gap-2.5 rounded-box border border-base-300/60 bg-base-200 p-4">
			<div>
				<div class="font-display text-[11.5px] font-extrabold uppercase tracking-[0.06em]">
					Group stage
				</div>
				<div class="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-base-content/55">
					Rounds 1–3
				</div>
			</div>
			<div class="font-hero text-[40px] leading-none">{groupTotal}</div>
			<div class="flex flex-wrap gap-2 border-t border-base-300/40 pt-2 text-[11px] font-bold text-base-content/70">
				<span class="inline-flex items-center gap-1.5">
					<span class="grid h-[18px] w-[18px] place-items-center rounded-[5px] bg-success/20 font-display text-[10px] text-success">E</span>
					<span class="font-display text-[13px] text-base-content">{totalExact}</span>
					<span class="text-base-content/55">Exact</span>
				</span>
				<span class="inline-flex items-center gap-1.5">
					<span class="grid h-[18px] w-[18px] place-items-center rounded-[5px] bg-warning/20 font-display text-[10px] text-warning-text">R</span>
					<span class="font-display text-[13px] text-base-content">{totalResult}</span>
					<span class="text-base-content/55">Result</span>
				</span>
				<span class="inline-flex items-center gap-1.5">
					<span class="grid h-[18px] w-[18px] place-items-center rounded-[5px] bg-primary/20 font-display text-[10px] text-primary">★</span>
					<span class="font-display text-[13px] text-base-content">{totalRarity}</span>
					<span class="text-base-content/55">Rarity</span>
				</span>
			</div>
		</div>
		<div class="flex flex-col gap-2.5 rounded-box border border-base-300/60 bg-base-200 p-4">
			<div>
				<div class="font-display text-[11.5px] font-extrabold uppercase tracking-[0.06em]">
					Knockouts
				</div>
				<div class="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-base-content/55">
					R32 → Finals
				</div>
			</div>
			<div class="font-hero text-[40px] leading-none">{koTotal}</div>
			<div class="flex flex-wrap gap-2 border-t border-base-300/40 pt-2 text-[11px] font-bold text-base-content/70">
				<span class="inline-flex items-center gap-1.5">
					<span class="grid h-[18px] w-[18px] place-items-center rounded-[5px] bg-success/20 font-display text-[10px] text-success">✓</span>
					<span class="font-display text-[13px] text-base-content">{totalHits}</span>
					<span class="text-base-content/55">Bracket hits</span>
				</span>
			</div>
		</div>
		<!-- Tournament total — THE one glow element on the page -->
		<div
			class="flex flex-col gap-2.5 rounded-box border border-primary bg-gradient-to-b from-primary/15 to-base-200 p-4 shadow-glow-gold"
		>
			<div>
				<div class="font-display text-[11.5px] font-extrabold uppercase tracking-[0.06em]">
					Tournament total
				</div>
				<div class="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-base-content/55">
					All rounds
				</div>
			</div>
			<div class="font-hero text-[48px] leading-none text-primary">{grand}</div>
		</div>
	</div>

	<!-- Per-round table -->
	<div class="overflow-hidden rounded-box border border-base-300/60 bg-base-200">
		<div
			class="grid grid-cols-[minmax(120px,1.4fr)_minmax(90px,1fr)_minmax(110px,1.1fr)_64px_24px] items-center gap-3 border-b border-base-300/50 bg-base-300/20 px-4 py-2.5"
		>
			<span class="text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">Round</span>
			<span class="text-center text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">Dates</span>
			<span class="text-center text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">Hits</span>
			<span class="text-right text-[9.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">Points</span>
			<span></span>
		</div>
		{#each rows as b (b.id)}
			<button
				type="button"
				class="group grid w-full grid-cols-[minmax(120px,1.4fr)_minmax(90px,1fr)_minmax(110px,1.1fr)_64px_24px] items-center gap-3 border-t border-base-300/45 px-4 py-2.5 text-left transition-colors first:border-t-0 hover:bg-primary/5"
				on:click={() => onJump(b.id)}
				aria-label={`Jump to ${b.label}`}
			>
				<span class="flex min-w-0 items-center gap-2.5">
					<span
						class="rounded-badge px-1.5 py-px text-[9px] font-extrabold {b.isKO
							? 'bg-success/20 text-success'
							: 'bg-primary/20 text-primary'}">{b.isKO ? 'KO' : 'GP'}</span
					>
					<span class="flex items-center gap-1.5 truncate text-[13px] font-semibold">
						{b.label}
						{#if liveRounds.has(b.id)}
							<span class="h-[7px] w-[7px] flex-none rounded-full bg-error animate-pulse-soft" title="Match in progress"></span>
						{/if}
					</span>
				</span>
				<span class="text-center text-[11.5px] text-base-content/55">{b.dates}</span>
				<span class="flex justify-center">
					{#if b.isWinner}
						{#if b.pending}
							<span class="text-[11px] font-bold text-base-content/40">pending</span>
						{:else if b.hits > 0}
							<span class="rounded-badge bg-success/20 px-1.5 py-px text-[11px] font-bold text-success">🏆 +{b.total}</span>
						{:else}
							<span class="text-[11px] font-bold text-base-content/40">✗ missed</span>
						{/if}
					{:else if b.isKO}
						{#if b.hits > 0}
							<span class="rounded-badge bg-success/20 px-1.5 py-px text-[11px] font-bold text-success">✓ {b.hits}</span>
						{:else}
							<span class="text-[11px] font-bold text-base-content/40">—</span>
						{/if}
					{:else if b.exact + b.result + b.rarity > 0}
						<span class="flex gap-1">
							{#if b.exact > 0}<span class="rounded-badge bg-success/20 px-1.5 py-px text-[11px] font-bold text-success">E {b.exact}</span>{/if}
							{#if b.result > 0}<span class="rounded-badge bg-warning/20 px-1.5 py-px text-[11px] font-bold text-warning-text">R {b.result}</span>{/if}
							{#if b.rarity > 0}<span class="rounded-badge bg-primary/20 px-1.5 py-px text-[11px] font-bold text-primary">★ {b.rarity}</span>{/if}
						</span>
					{:else}
						<span class="text-[11px] font-bold text-base-content/40">—</span>
					{/if}
				</span>
				<span class="text-right font-display text-[15px] {b.total > 0 ? 'text-primary' : 'text-base-content/30'}">{b.total}</span>
				<span class="text-base-content/40 transition-transform group-hover:translate-x-0.5 group-hover:text-primary">→</span>
			</button>
		{/each}
		<div class="flex items-center justify-between border-t border-base-300/50 px-4 py-3">
			<span class="text-[12.5px] font-bold tracking-[0.06em] text-primary">Tournament Total</span>
			<span class="font-display text-[20px] text-primary">{grand}</span>
		</div>
	</div>
</div>
```

Check `font-hero` (Bebas Neue) exists in the Tailwind config; if not, fall back to `font-display` — CLAUDE.md lists `font-hero` as opt-in, so it should exist.

- [ ] **Step 2: Create WinnerView**

```svelte
<script lang="ts">
	/** Champion card — your pick vs actual champion. +N values template
	 *  from rules.advancement.winner (C.1). The champion resolves from the
	 *  FINISHED final fixture only (winner credit requires final whistle). */
	import type { Fixture } from '$types';
	import type { BracketPrediction } from '$types';
	import type { ScoringRules } from '$lib/types/results';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	export let bracket: BracketPrediction | null;
	export let finalFixture: Fixture | null;
	export let rules: ScoringRules;

	$: pick = bracket?.winner || null;
	$: champion =
		finalFixture && finalFixture.status === 'finished' && finalFixture.score
			? finalFixture.score.outcome === '1'
				? finalFixture.home_team
				: finalFixture.score.outcome === '2'
				? finalFixture.away_team
				: null
			: null;
	$: correct = !!champion && !!pick && champion === pick;
	$: winnerPts = rules.advancement.winner;
</script>

<div
	class="mx-auto mt-4 max-w-xl rounded-box border border-primary/60 bg-gradient-to-b from-primary/10 to-base-200 p-6 text-center"
>
	<div class="mb-5 inline-block rounded-full bg-primary/20 px-3 py-1 text-[11px] font-extrabold tracking-[0.08em] text-primary">
		🏆 World Cup 2026 · Champion
	</div>
	<div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
		<div>
			<div class="mb-3 text-[10px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
				Your pick
			</div>
			{#if pick}
				<div class="flex flex-col items-center gap-2.5">
					{#if hasFlag(pick)}
						<img src={getFlagUrl(pick, 'lg')} alt="" class="h-[58px] w-[84px] rounded-md object-cover shadow-card" />
					{/if}
					<div class="font-display text-[18px] font-extrabold">{displayTeamName(pick)}</div>
					{#if champion}
						{#if correct}
							<span class="rounded-full bg-success/20 px-2.5 py-1 text-[11px] font-bold text-success">✓ +{winnerPts} banked</span>
						{:else}
							<span class="rounded-full bg-error/20 px-2.5 py-1 text-[11px] font-bold text-error">✗ no points</span>
						{/if}
					{:else}
						<span class="rounded-full bg-base-300/40 px-2.5 py-1 text-[11px] font-bold text-base-content/55">pending · +{winnerPts} if they lift it</span>
					{/if}
				</div>
			{:else}
				<div class="text-[13px] text-base-content/55">No champion pick on this entry.</div>
			{/if}
		</div>
		<div>
			<div class="mb-3 text-[10px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
				Actual champion
			</div>
			{#if champion}
				<div class="flex flex-col items-center gap-2.5">
					{#if hasFlag(champion)}
						<img src={getFlagUrl(champion, 'lg')} alt="" class="h-[58px] w-[84px] rounded-md object-cover shadow-card" />
					{/if}
					<div class="font-display text-[18px] font-extrabold">{displayTeamName(champion)}</div>
					<span class="rounded-full bg-primary/20 px-2.5 py-1 text-[11px] font-bold text-primary">🏆 lifted the trophy</span>
				</div>
			{:else}
				<div class="flex flex-col items-center gap-2.5">
					<div class="grid h-[58px] w-[84px] place-items-center rounded-md border-2 border-dashed border-base-300/80 text-[22px] text-base-content/30">?</div>
					<div class="font-display text-[18px] font-extrabold text-base-content/30">TBD</div>
					<span class="rounded-full bg-base-300/40 px-2.5 py-1 text-[11px] font-bold text-base-content/55">final not yet played</span>
				</div>
			{/if}
		</div>
	</div>
</div>
```

Check `getFlagUrl(team, 'lg')` supports a large size; if the util only has 'sm', use the available size and scale via CSS.

- [ ] **Step 3: Overlay + type-check.** **Step 4: Commit**

```bash
git add frontend/src/lib/components/results/v4/SummaryView.svelte frontend/src/lib/components/results/v4/WinnerView.svelte
git commit -m "feat(results-v4): summary + winner tabs"
```

---

# Group D — The page shell

## Task 12: Rewrite `/results/+page.svelte`

**Files:**
- Modify: `frontend/src/routes/results/+page.svelte` (full rewrite — the `SHOW_CONTENT` stub and its V3 BreakdownCard wiring are deleted; `BreakdownCard.svelte` itself stays on disk untouched)

Responsibilities:
1. **Gating (D.2):** `phase1Deadline < now` → render V4; else render the existing "Results open at kickoff" stub markup (carry it over verbatim).
2. **Data load on mount:** fixtures, entries (via `loadEntries`), leaderboard (rank map), scoring rules. Then per-entry: match predictions + bracket via the entry-scoped API for the SELECTED entry (the predictions store is wired to `activeEntryId` — reuse `setActiveEntry` + the store fetchers; this also persists the selection to Match Detail for free).
3. **Round state:** `selectedRound` initialised from `defaultRound(...)` (D.1), synced to the `?round=` URL search param (shallow replaceState, no nav) so refresh keeps the tab.
4. **Entry switching:** updates `activeEntryId`, refetches predictions + bracket, recomputes everything reactively.
5. **Compose:** EntryPillBar (multi-entry only) + PointsSummary → RoundTabs → RoundExplainer → per-tab body (Summary / Winner / Group table / KO table + Missed/Progressing cards).

- [ ] **Step 1: Write the new page**

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import { fetchAllFixtures, fixtureById, fixtures } from '$stores/fixtures';
	import {
		bracketPrediction,
		fetchBracketPredictions,
		fetchMatchPredictions,
		matchPredictions,
		resetPredictions
	} from '$stores/predictions';
	import { activeEntryId, entries, loadEntries, setActiveEntry } from '$stores/entries';
	import { phase1Deadline } from '$stores/phase';
	import { pageTitle } from '$stores/pageTitle';
	import { getLeaderboard, getScoringRules } from '$api/leaderboard';
	import type {
		EntryRankInfo,
		MatchPredictionWithPoints,
		RoundId,
		ScoringRules
	} from '$lib/types/results';
	import { buildRounds, NEXT_ROUND, ROUND_LABELS } from '$lib/utils/resultsRounds';
	import { defaultRound, roundsWithLive } from '$lib/utils/roundsLive';
	import {
		bracketPicksForRound,
		missedR32Picks,
		progressingSplit,
		stagePointsForRound
	} from '$lib/utils/koPoints';
	import EntryPillBar from '$lib/components/results/v4/EntryPillBar.svelte';
	import PointsSummary from '$lib/components/results/v4/PointsSummary.svelte';
	import RoundTabs from '$lib/components/results/v4/RoundTabs.svelte';
	import RoundExplainer from '$lib/components/results/v4/RoundExplainer.svelte';
	import GroupRoundTable from '$lib/components/results/v4/GroupRoundTable.svelte';
	import KnockoutRoundTable from '$lib/components/results/v4/KnockoutRoundTable.svelte';
	import MissedPicksCard from '$lib/components/results/v4/MissedPicksCard.svelte';
	import ProgressingCard from '$lib/components/results/v4/ProgressingCard.svelte';
	import SummaryView from '$lib/components/results/v4/SummaryView.svelte';
	import WinnerView from '$lib/components/results/v4/WinnerView.svelte';

	$: if (!$isAuthenticated) goto('/login');

	// ── Gate (spec D.2): deadline passed → V4; else pre-tournament stub ──
	$: resultsOpen = $phase1Deadline ? new Date($phase1Deadline).getTime() < Date.now() : false;

	let loading = true;
	let rules: ScoringRules | null = null;
	let rankByEntry = new Map<string, EntryRankInfo>();

	const VALID_ROUNDS: RoundId[] = ['summary', 'r1', 'r2', 'r3', 'r32', 'r16', 'qf', 'sf', 'f', 'winner'];
	let selectedRound: RoundId = 'r1';
	let roundInitialised = false;

	onMount(() => pageTitle.set('Results'));

	onMount(async () => {
		if (!$isAuthenticated || !resultsOpen) {
			loading = false;
			return;
		}
		await Promise.all([fetchAllFixtures(), $user?.id ? loadEntries($user.id) : Promise.resolve()]);

		// Pick the active entry: keep the store's selection if it belongs to
		// this user, else the most recently updated submitted entry, else first.
		if (!$activeEntryId || !$entries.some((e) => e.id === $activeEntryId)) {
			const candidate = $entries[0];
			if (candidate) setActiveEntry(candidate.id);
		}

		const [leaderboard, scoringRules] = await Promise.all([
			getLeaderboard().catch(() => null),
			getScoringRules()
		]);
		rules = scoringRules;
		if (leaderboard) {
			rankByEntry = new Map(
				leaderboard.entries.map((e) => [
					e.entry_id,
					{ position: e.position, total_points: e.total_points }
				])
			);
		}

		await Promise.all([fetchMatchPredictions(), fetchBracketPredictions()]);
		loading = false;
	});

	// ── Round selection: URL param → default logic (D.1) ──
	$: rounds = buildRounds($fixtures);
	$: liveRounds = roundsWithLive(rounds, $fixtureById);
	$: if (!roundInitialised && !loading && $fixtures.length > 0) {
		const fromUrl = $page.url.searchParams.get('round') as RoundId | null;
		selectedRound =
			fromUrl && VALID_ROUNDS.includes(fromUrl)
				? fromUrl
				: defaultRound(rounds, $fixtureById, new Date());
		roundInitialised = true;
	}

	function selectRound(id: RoundId) {
		selectedRound = id;
		const url = new URL($page.url);
		url.searchParams.set('round', id);
		history.replaceState(history.state, '', url);
	}

	async function selectEntry(entryId: string) {
		if (entryId === $activeEntryId) return;
		setActiveEntry(entryId);
		resetPredictions();
		await Promise.all([fetchMatchPredictions(), fetchBracketPredictions()]);
	}

	// ── Derived view data ──
	$: typedPredictions = $matchPredictions as MatchPredictionWithPoints[];
	$: predictionsByFixture = new Map(typedPredictions.map((p) => [p.fixture_id, p]));
	$: activeRound = rounds.find((r) => r.id === selectedRound);
	$: roundFixtures = (activeRound?.fixtureIds ?? [])
		.map((fid) => $fixtureById.get(fid))
		.filter((f): f is NonNullable<typeof f> => !!f);
	$: roundPicks = bracketPicksForRound($bracketPrediction, selectedRound);
	$: stagePts = rules ? stagePointsForRound(rules.advancement, selectedRound) : 0;
	$: nextId = NEXT_ROUND[selectedRound] ?? null;
	$: nextStagePts = rules && nextId ? stagePointsForRound(rules.advancement, nextId) : 0;
	$: nextPicks = nextId ? bracketPicksForRound($bracketPrediction, nextId) : new Set<string>();
	$: progressing =
		activeRound?.isKnockout && nextId ? progressingSplit(roundFixtures, nextPicks) : null;
	$: missedTeams =
		selectedRound === 'r32' ? missedR32Picks(roundFixtures, roundPicks) : [];
	$: finalFixture =
		rounds
			.find((r) => r.id === 'f')
			?.fixtureIds.map((fid) => $fixtureById.get(fid))
			.find((f) => f?.stage === 'final') ?? null;
	$: finalDateLabel = finalFixture
		? new Date(finalFixture.kickoff).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
		: '';
	$: multiEntry = $entries.length > 1;
</script>

<svelte:head>
	<title>Results — Predictor v2</title>
</svelte:head>

{#if $isAuthenticated && !resultsOpen}
	<!-- Pre-deadline stub (carried over from the V3 page verbatim) -->
	<div class="hero min-h-[60vh]">
		<div class="hero-content text-center">
			<div class="max-w-md">
				<h2 class="font-display text-3xl tracking-wide">Results open at kickoff</h2>
				<p class="mt-3 text-base-content/60">
					You'll see your match results here as the tournament unfolds.
				</p>
				<a href="/entries" class="btn btn-primary btn-lg mt-6 shadow-glow-gold">
					Lock in your predictions
				</a>
			</div>
		</div>
	</div>
{:else if $isAuthenticated}
	<div class="container mx-auto mobile-padding max-w-[1180px] py-6">
		<h1 class="font-display text-3xl tracking-wide sm:text-4xl">Results</h1>

		{#if loading || !rules}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else}
			<!-- Top strip: pills (multi-entry) + points summary -->
			<div class="mt-4 flex flex-col gap-3 lg:flex-row lg:items-stretch lg:justify-between">
				{#if multiEntry && $activeEntryId}
					<EntryPillBar
						entries={$entries}
						selectedId={$activeEntryId}
						{rankByEntry}
						onSelect={selectEntry}
					/>
				{/if}
				<PointsSummary predictions={typedPredictions} fullWidth={!multiEntry} />
			</div>

			<RoundTabs {rounds} selected={selectedRound} {liveRounds} onSelect={selectRound} />

			<RoundExplainer roundId={selectedRound} {rules} finalDate={finalDateLabel} />

			{#if selectedRound === 'summary'}
				<SummaryView
					{rounds}
					fixtureById={$fixtureById}
					{predictionsByFixture}
					bracket={$bracketPrediction}
					{rules}
					{liveRounds}
					onJump={selectRound}
				/>
			{:else if selectedRound === 'winner'}
				<WinnerView bracket={$bracketPrediction} {finalFixture} {rules} />
			{:else if activeRound?.isKnockout}
				{#if missedTeams.length > 0}
					<MissedPicksCard roundLabel={activeRound.label} teams={missedTeams} stagePoints={stagePts} />
				{/if}
				<KnockoutRoundTable
					round={activeRound}
					fixtures={roundFixtures}
					{roundPicks}
					stagePoints={stagePts}
				/>
				{#if progressing && nextId && progressing.inNext.length + progressing.notInNext.length > 0}
					<ProgressingCard
						nextLabel={ROUND_LABELS[nextId]}
						inNext={progressing.inNext}
						notInNext={progressing.notInNext}
						nextStagePoints={nextStagePts}
					/>
				{/if}
			{:else if activeRound}
				<GroupRoundTable round={activeRound} fixtures={roundFixtures} {predictionsByFixture} />
			{/if}
		{/if}
	</div>
{/if}
```

**Verify against the real store APIs before finalizing:** the exact names of `fetchBracketPredictions` / `resetPredictions` in `$stores/predictions` (read the store file; the fetcher may be named `fetchBracketPrediction` singular or take a phase arg) and whether the explainer banner belongs above or below MissedPicksCard per the bundle (HANDOVER §3: explainer first, then missed card, then table — the code above matches).

- [ ] **Step 2: Overlay + full gates**

```bash
docker-compose exec -T frontend-dev npx vitest run src/lib/utils src/lib/components/results/v4
docker-compose exec -T frontend-dev npm run check
docker-compose restart frontend-dev   # Vite watch unreliable on this mount
```

Expected: tests PASS, 0 new check errors, dev server boots clean (`docker logs predictorv2-frontend-dev-1 --tail 20`).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/results/+page.svelte
git commit -m "feat(results-v4): rewrite /results shell — gating, tabs, entry switching (replaces stub)"
```

---

# Group E — Browser smoke + close-out

## Task 13: Chrome smoke at desktop + 375px, both themes

The dev DB is pre-tournament (no FINISHED fixtures, deadline in the future), so two temporary tweaks are needed **in the overlay copy only — never committed**:

- [ ] **Step 1: Temporarily force the gate open in the MAIN-WORKTREE copy only**

After overlaying, edit the main worktree's `frontend/src/routes/results/+page.svelte` line `$: resultsOpen = …` to `$: resultsOpen = true;`. This file gets restored after the smoke, so the tweak never reaches the branch.

- [ ] **Step 2: Smoke checklist (Chrome, logged in as the dev admin)**

Desktop (~1440px), `premium-night`:
- `/results` renders: title, entry pills (the dev user has 4+ entries → pills visible), points summary with zeros, round tabs, explainer, R1 table with picks + `—` points cells.
- Tabs switch; explainer copy changes per round; KO tabs show TBD seed slots + `—` cells; `?round=` updates in the URL bar; refresh restores the tab.
- Summary tab: three subtotal cards all zeros, only the Tournament-total card glows, rows jump to tabs.
- Winner tab: champion card with the entry's pick, "pending · +100 if they lift it" chip (value from yml), TBD right column.
- Entry switcher: clicking another pill swaps predictions (pick column changes), active pill gets the gold outline, no glow.
- Console: no NEW errors (the layout `pathname` TypeError is pre-existing).

375px (devtools responsive), both themes (toggle via the navbar):
- No horizontal scroll on any tab.
- Fixture rows render as stacked cards with the divider + pick/points line.
- Round tabs scroll horizontally; active tab scrolled into view.
- `hybrid` theme: cards lift on white, explainer/cards keep contrast, amber text readable (text-warning-text).

LIVE-state spot check (no DB mutation): not coverable pre-tournament — the live-dot + auto-select path is pinned by `roundsLive.test.ts`; visual verification lands during the tournament. Note this gap in the close-out report.

- [ ] **Step 3: Restore the main worktree** (remove the gate tweak with the rest):

```bash
# from the main worktree — restore ONLY plan-owned files
git checkout -- frontend/src/routes/results/+page.svelte frontend/src/lib/api/leaderboard.ts
rm -r frontend/src/lib/components/results/v4 frontend/src/lib/types/results.ts \
      frontend/src/lib/utils/resultsRounds.ts frontend/src/lib/utils/resultsRounds.test.ts \
      frontend/src/lib/utils/roundsLive.ts frontend/src/lib/utils/roundsLive.test.ts \
      frontend/src/lib/utils/koPoints.ts frontend/src/lib/utils/koPoints.test.ts
docker-compose restart frontend-dev
git status --short   # must show ONLY the user's pre-existing WIP
```

- [ ] **Step 4: No commit** — smoke is verification only.

---

## Task 14: Phase 2 close-out

- [ ] **Step 1: Full regression**

```bash
docker-compose exec -T frontend-dev npx vitest run
docker-compose exec -T backend pytest tests/ -q
```

Expected: all green (frontend suite includes the parity tests; backend unchanged from Phase 1).

- [ ] **Step 2: Self-review checklist**

- [ ] No hardcoded point values in any `.svelte` file under `components/results/v4/` — `grep -rn '+5\|+15\|+20\|+25\|+100' frontend/src/lib/components/results/v4/ frontend/src/routes/results/` returns only templated `+{...}` expressions, no literals in copy.
- [ ] No instance of the word "Outcome" in V4 user-facing copy (vocabulary lock).
- [ ] No "Phase 1"/"Phase 2" in V4 copy.
- [ ] Only glow on the page = Tournament-total card (`shadow-glow-gold` appears exactly once under `v4/`).
- [ ] `text-warning` never used bare — only `text-warning-text` or `bg-warning/...`.
- [ ] `roundsWithLive` derived once in the page, passed to BOTH RoundTabs and SummaryView.
- [ ] Main worktree clean of plan files; user WIP untouched (`git status` in main shows only their pre-existing entries + the DevPhaseSwitcher stub).
- [ ] All commits conventional-prefixed.

- [ ] **Step 3: Hand off to Phase 3** (Match Detail page — `/results/[fixture_id]`, prev/next nav, pool list, rarity explainer rendering `RarityDetailOut.note`, upset heuristic `upsetOfRound.ts`, scoreline spread). Version bump + changelog still deferred to end of Phase 3.

---

# Known gaps accepted in this phase

1. **Match Detail route untouched** — group/KO rows link to `/results/{id}` which still renders the V3 drill-down (or 404s if none exists — check; if the route doesn't exist yet, rows still link there and Phase 3 fills it in. Acceptable for a branch that ships all three phases together).
2. **LIVE visuals unverified in browser** — no live fixtures exist pre-tournament; covered by unit tests.
3. **Summary "Tournament total" excludes bonus-question points** by design (mockup contract); the leaderboard remains the official total. If the user wants a footnote line ("+N from bonus questions — see Standings"), it's a five-line follow-up.
4. **Layout `pathname` TypeError stays** — the fix lives in the user's WIP file; cannot touch without clobbering.
```
