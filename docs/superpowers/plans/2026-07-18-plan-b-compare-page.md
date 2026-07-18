# /compare Page + Shared Comparison Engine (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pure `compareEntries.ts` delta engine + two shared components, and a `/compare` page answering "why didn't I win?" — every pick side by side with ranked swings. Zero new backend.

**Architecture:** The engine consumes exactly what the leaderboard EntryDrawer already fetches per entry (`getEntryBreakdown`, `getMatchPredictions`, `getBracketPredictions`, `getEntryBonusReads`, `getBonusQuestions`) plus the shared fixtures store. Tasks B1–B3 (engine + components) are the dependency for Plan C's "How the title was won" matrix — build them first. The page (B4) trails and ships admin-gated.

**Tech Stack:** SvelteKit + TypeScript, Vitest, existing `$api` clients.

**Spec:** `docs/superpowers/specs/2026-07-18-compare-page-design.md`

**Testing note:** frontend checks run against the main worktree per the overlay pattern: copy changed files over, `docker-compose exec -T frontend-dev npx vitest run <file>` and `npm run check`, restore, commit here. Static checks need no dev-server restart.

**Key type facts (extracted, do not re-derive):**
- `MatchPredictionWithPoints = MatchPrediction & { points?: PickPoints | null }`; `PickPoints = { base; base_kind: 'miss'|'result'|'exact'; rarity; total }` (`types/results.ts:13-23`).
- `BracketPrediction` keys: `round_of_32`, `round_of_16`, `quarter_finals`, `semi_finals`, `final` (string[]), `winner` (string) — QF/SF **plural** (`types/index.ts:112`).
- `ScoringRules.advancement` keys are **singular** (`round_of_32 … winner`) (`types/results.ts:183`).
- `BonusPredictionRead = { question_id; answer; category; points: number|null; hit: boolean|null }` (`types/leaderboard.ts:81`).
- `Fixture` has `match_number: number|null`, `stage`, `score: FixtureScore|null` (`types/index.ts:52`).
- `LbEntryV4` extends `LeaderboardEntry` (`entry_id`, `user_name`, `entry_name`, `position`, `total_points`, `breakdown`, …) with `champion_pick`, `bonus_group_points`, `bonus_knockout_points`.

---

### Task B1: Engine — types, summary, match rows

**Files:**
- Create: `frontend/src/lib/utils/compareEntries.ts`
- Create: `frontend/src/lib/utils/compareEntries.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/utils/compareEntries.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import type { Fixture } from '$types';
import type { MatchPredictionWithPoints } from '$lib/types/results';
import {
	buildMatchRows,
	buildSummary,
	type CompareEntryInput
} from './compareEntries';

const FX = (id: string, n: number, home: string, away: string, hs: number, as_: number, stage = 'group'): Fixture =>
	({
		id, home_team: home, away_team: away, kickoff: '2026-06-12T18:00:00Z',
		stage, group: stage === 'group' ? 'A' : null, match_number: n,
		status: 'finished', minute: null, is_locked: true, time_until_lock: null,
		score: { home_score: hs, away_score: as_, home_score_et: null, away_score_et: null, home_penalties: null, away_penalties: null, outcome: hs > as_ ? '1' : hs < as_ ? '2' : 'X' },
		venue_city: null, venue_country: null, venue_country_code: null
	}) as Fixture;

const PICK = (fixtureId: string, hs: number, as_: number, total: number, kind: 'miss' | 'result' | 'exact'): MatchPredictionWithPoints =>
	({
		id: fixtureId + '-p', entry_id: 'e', fixture_id: fixtureId,
		home_score: hs, away_score: as_, phase: 'phase_1',
		locked_at: null, created_at: '', updated_at: '', is_locked: true,
		points: total === 0 ? { base: 0, base_kind: 'miss', rarity: 0, total: 0 } : { base: kind === 'exact' ? 10 : 5, base_kind: kind, rarity: total - (kind === 'exact' ? 10 : 5), total }
	}) as MatchPredictionWithPoints;

const fixtures = new Map<string, Fixture>([
	['f1', FX('f1', 11, 'England', 'Iran', 2, 0)],
	['f2', FX('f2', 42, 'Japan', 'Poland', 1, 1)]
]);

function input(partial: Partial<CompareEntryInput>): CompareEntryInput {
	return {
		entryId: 'e', displayName: 'E', finalRank: 1, totalPoints: 0,
		groupPoints: 0, knockoutPoints: 0, bonusPoints: 0,
		matches: [], bracket: null, bonusReads: [], questionLabels: new Map(),
		...partial
	};
}

describe('buildSummary', () => {
	it('deltas are A minus B per bucket', () => {
		const a = input({ totalPoints: 612, groupPoints: 348, knockoutPoints: 214, bonusPoints: 50 });
		const b = input({ totalPoints: 598, groupPoints: 356, knockoutPoints: 202, bonusPoints: 40 });
		expect(buildSummary(a, b)).toEqual({ total: 14, group: -8, knockout: 12, bonus: 10 });
	});
});

describe('buildMatchRows', () => {
	it('joins picks by fixture and computes delta', () => {
		const a = input({ matches: [PICK('f1', 2, 0, 13.2, 'exact'), PICK('f2', 0, 0, 0, 'miss')] });
		const b = input({ matches: [PICK('f1', 1, 0, 5, 'result'), PICK('f2', 1, 1, 14.1, 'exact')] });
		const rows = buildMatchRows(a, b, fixtures);
		expect(rows).toHaveLength(2);
		const m11 = rows.find((r) => r.fixtureId === 'f1')!;
		expect(m11.label).toBe('M11 · England 2–0 Iran');
		expect(m11.aPoints).toBeCloseTo(13.2);
		expect(m11.bPoints).toBe(5);
		expect(m11.delta).toBeCloseTo(8.2);
		expect(m11.aKind).toBe('exact');
		expect(m11.bKind).toBe('result');
	});

	it('skips fixtures without a finished score', () => {
		const unf = new Map(fixtures);
		unf.set('f3', { ...FX('f3', 99, 'A', 'B', 0, 0), status: 'scheduled', score: null } as Fixture);
		const a = input({ matches: [PICK('f3', 1, 0, 0, 'miss')] });
		expect(buildMatchRows(a, input({}), unf)).toHaveLength(0);
	});
});
```

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose exec -T frontend-dev npx vitest run src/lib/utils/compareEntries.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

Create `frontend/src/lib/utils/compareEntries.ts`:

```ts
/**
 * compareEntries — THE delta engine for head-to-head entry comparison.
 * Consumed by /compare (Plan B) and the wrap-up "How the title was won"
 * matrix (Plan C). One engine, two surfaces — never re-derive deltas
 * elsewhere. Pure: rarity/points always come from served PickPoints,
 * never recomputed client-side (scoring-parity rule).
 */

import type { Fixture } from '$types';
import type { BracketPrediction } from '$types';
import type { BonusPredictionRead } from '$lib/types/leaderboard';
import type { MatchPredictionWithPoints } from '$lib/types/results';

export interface CompareEntryInput {
	entryId: string;
	displayName: string;
	finalRank: number;
	totalPoints: number;
	groupPoints: number;
	knockoutPoints: number;
	bonusPoints: number;
	matches: MatchPredictionWithPoints[];
	bracket: BracketPrediction | null;
	bonusReads: BonusPredictionRead[];
	questionLabels: Map<string, string>;
}

export interface CompareSummary {
	total: number;
	group: number;
	knockout: number;
	bonus: number;
}

export type PickKind = 'exact' | 'result' | 'miss' | 'none';

export interface MatchRow {
	fixtureId: string;
	label: string; // "M11 · England 2–0 Iran"
	aPick: string | null; // "2–0"
	bPick: string | null;
	aPoints: number;
	bPoints: number;
	aKind: PickKind;
	bKind: PickKind;
	delta: number;
}

export function buildSummary(a: CompareEntryInput, b: CompareEntryInput): CompareSummary {
	return {
		total: a.totalPoints - b.totalPoints,
		group: a.groupPoints - b.groupPoints,
		knockout: a.knockoutPoints - b.knockoutPoints,
		bonus: a.bonusPoints - b.bonusPoints
	};
}

function fixtureLabel(f: Fixture): string {
	const score = f.score ? `${f.score.home_score}–${f.score.away_score}` : '';
	const num = f.match_number != null ? `M${f.match_number} · ` : '';
	return `${num}${f.home_team} ${score} ${f.away_team}`.replace(/\s+/g, ' ').trim();
}

function pickOf(m: MatchPredictionWithPoints | undefined): {
	pick: string | null;
	points: number;
	kind: PickKind;
} {
	if (!m) return { pick: null, points: 0, kind: 'none' };
	return {
		pick: `${m.home_score}–${m.away_score}`,
		points: m.points?.total ?? 0,
		kind: (m.points?.base_kind as PickKind) ?? 'none'
	};
}

export function buildMatchRows(
	a: CompareEntryInput,
	b: CompareEntryInput,
	fixtureById: Map<string, Fixture>
): MatchRow[] {
	const byFixtureA = new Map(a.matches.map((m) => [m.fixture_id, m]));
	const byFixtureB = new Map(b.matches.map((m) => [m.fixture_id, m]));
	const ids = new Set([...byFixtureA.keys(), ...byFixtureB.keys()]);
	const rows: MatchRow[] = [];
	for (const id of ids) {
		const f = fixtureById.get(id);
		if (!f || f.status !== 'finished' || !f.score) continue;
		if (f.stage === 'third_place') continue; // unscored-stage invariant
		const pa = pickOf(byFixtureA.get(id));
		const pb = pickOf(byFixtureB.get(id));
		rows.push({
			fixtureId: id,
			label: fixtureLabel(f),
			aPick: pa.pick,
			bPick: pb.pick,
			aPoints: pa.points,
			bPoints: pb.points,
			aKind: pa.kind,
			bKind: pb.kind,
			delta: pa.points - pb.points
		});
	}
	rows.sort((x, y) => {
		const fx = fixtureById.get(x.fixtureId)!;
		const fy = fixtureById.get(y.fixtureId)!;
		return new Date(fx.kickoff).getTime() - new Date(fy.kickoff).getTime();
	});
	return rows;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `docker-compose exec -T frontend-dev npx vitest run src/lib/utils/compareEntries.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils/compareEntries.ts frontend/src/lib/utils/compareEntries.test.ts
git commit -m "feat(compare): compareEntries engine — summary + match rows"
```

---

### Task B2: Engine — bracket rows, bonus rows, ranked swings

**Files:**
- Modify: `frontend/src/lib/utils/compareEntries.ts`
- Modify: `frontend/src/lib/utils/compareEntries.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to the test file:

```ts
import type { ScoringRules } from '$lib/types/results';
import { buildBonusRows, buildBracketRows, buildSwings } from './compareEntries';

const RULES: ScoringRules = {
	mode: 'logarithmic',
	match: { correct_outcome: 5, exact_score: 10, rarity_cap: 5 },
	advancement: { round_of_32: 2, round_of_16: 4, quarter_final: 8, semi_final: 16, final: 32, winner: 64 }
};

const bracket = (over: Partial<import('$types').BracketPrediction>) => ({
	group_winners: {}, round_of_32: [], round_of_16: [],
	quarter_finals: [], semi_finals: [], final: [], winner: '',
	...over
});

describe('buildBracketRows', () => {
	it('per-stage hits vs actual advancement, points from rules', () => {
		const a = input({ bracket: bracket({ semi_finals: ['Argentina', 'France', 'Spain', 'England'], winner: 'Argentina' }) });
		const b = input({ bracket: bracket({ semi_finals: ['Argentina', 'Brazil', 'Spain', 'Portugal'], winner: 'France' }) });
		const actual = { semi_final: new Set(['Argentina', 'France', 'Spain', 'Morocco']), winner: new Set(['Argentina']) };
		const rows = buildBracketRows(a, b, actual, RULES);
		const sf = rows.find((r) => r.stage === 'semi_final')!;
		expect(sf.aHits).toBe(3);
		expect(sf.bHits).toBe(2);
		expect(sf.aPoints).toBe(48); // 3 × 16
		expect(sf.delta).toBe(16);
		const w = rows.find((r) => r.stage === 'winner')!;
		expect(w.aHits).toBe(1);
		expect(w.bHits).toBe(0);
		expect(w.delta).toBe(64);
	});
});

describe('buildBonusRows + buildSwings', () => {
	it('bonus rows join labels; swings rank every differing element by |delta|', () => {
		const labels = new Map([['q1', 'Knockout Top / Flop']]);
		const a = input({
			matches: [PICK('f1', 2, 0, 13.2, 'exact')],
			bonusReads: [{ question_id: 'q1', answer: 'Türkiye', category: 'top_flop', points: 10, hit: true }],
			questionLabels: labels,
			bracket: bracket({ winner: 'Argentina' })
		});
		const b = input({
			matches: [PICK('f1', 1, 0, 5, 'result')],
			bonusReads: [{ question_id: 'q1', answer: 'Belgium', category: 'top_flop', points: 0, hit: false }],
			questionLabels: labels,
			bracket: bracket({ winner: 'France' })
		});
		const actual = { winner: new Set(['Argentina']) };
		const bonusRows = buildBonusRows(a, b);
		expect(bonusRows[0].label).toBe('Knockout Top / Flop');
		expect(bonusRows[0].delta).toBe(10);

		const swings = buildSwings(a, b, fixtures, actual, RULES);
		// winner stage (64) > bonus (10) > match (8.2)
		expect(swings.map((s) => s.kind)).toEqual(['bracket', 'bonus', 'match']);
		expect(swings[0].delta).toBe(64);
		expect(swings[2].delta).toBeCloseTo(8.2);
		// equal elements are excluded
		expect(swings.every((s) => s.delta !== 0)).toBe(true);
	});
});
```

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose exec -T frontend-dev npx vitest run src/lib/utils/compareEntries.test.ts`
Expected: FAIL — new exports missing

- [ ] **Step 3: Implement**

Append to `compareEntries.ts`:

```ts
import type { ScoringRules } from '$lib/types/results';

/** Bridge: BracketPrediction keys (plural QF/SF) ↔ stage keys (singular). */
const BRACKET_STAGES: { key: keyof BracketPrediction; stage: string; label: string }[] = [
	{ key: 'round_of_32', stage: 'round_of_32', label: 'Round of 32' },
	{ key: 'round_of_16', stage: 'round_of_16', label: 'Round of 16' },
	{ key: 'quarter_finals', stage: 'quarter_final', label: 'Quarter-finals' },
	{ key: 'semi_finals', stage: 'semi_final', label: 'Semi-finals' },
	{ key: 'final', stage: 'final', label: 'Final' }
];

export type ActualAdvancement = Partial<Record<string, Set<string>>>;

export interface BracketRow {
	stage: string;
	label: string;
	aTeams: string[];
	bTeams: string[];
	aHits: number;
	bHits: number;
	aPoints: number;
	bPoints: number;
	delta: number;
}

export function buildBracketRows(
	a: CompareEntryInput,
	b: CompareEntryInput,
	actual: ActualAdvancement,
	rules: ScoringRules
): BracketRow[] {
	const rows: BracketRow[] = [];
	for (const { key, stage, label } of BRACKET_STAGES) {
		const reached = actual[stage];
		if (!reached || reached.size === 0) continue; // stage not settled yet
		const aTeams = (a.bracket?.[key] as string[] | undefined) ?? [];
		const bTeams = (b.bracket?.[key] as string[] | undefined) ?? [];
		const per = rules.advancement[stage] ?? 0;
		const aHits = aTeams.filter((t) => reached.has(t)).length;
		const bHits = bTeams.filter((t) => reached.has(t)).length;
		rows.push({
			stage, label, aTeams, bTeams, aHits, bHits,
			aPoints: aHits * per, bPoints: bHits * per,
			delta: (aHits - bHits) * per
		});
	}
	const winners = actual['winner'];
	if (winners && winners.size > 0) {
		const per = rules.advancement['winner'] ?? 0;
		const aHit = a.bracket?.winner && winners.has(a.bracket.winner) ? 1 : 0;
		const bHit = b.bracket?.winner && winners.has(b.bracket.winner) ? 1 : 0;
		rows.push({
			stage: 'winner', label: 'Winner',
			aTeams: a.bracket?.winner ? [a.bracket.winner] : [],
			bTeams: b.bracket?.winner ? [b.bracket.winner] : [],
			aHits: aHit, bHits: bHit,
			aPoints: aHit * per, bPoints: bHit * per,
			delta: (aHit - bHit) * per
		});
	}
	return rows;
}

export interface BonusRow {
	questionId: string;
	label: string;
	aAnswer: string | null;
	bAnswer: string | null;
	aPoints: number;
	bPoints: number;
	aHit: boolean | null;
	bHit: boolean | null;
	delta: number;
}

export function buildBonusRows(a: CompareEntryInput, b: CompareEntryInput): BonusRow[] {
	const byIdB = new Map(b.bonusReads.map((r) => [r.question_id, r]));
	const ids = new Set([
		...a.bonusReads.map((r) => r.question_id),
		...b.bonusReads.map((r) => r.question_id)
	]);
	const byIdA = new Map(a.bonusReads.map((r) => [r.question_id, r]));
	const rows: BonusRow[] = [];
	for (const id of ids) {
		const ra = byIdA.get(id);
		const rb = byIdB.get(id);
		rows.push({
			questionId: id,
			label: a.questionLabels.get(id) ?? b.questionLabels.get(id) ?? 'Bonus question',
			aAnswer: ra?.answer ?? null,
			bAnswer: rb?.answer ?? null,
			aPoints: ra?.points ?? 0,
			bPoints: rb?.points ?? 0,
			aHit: ra?.hit ?? null,
			bHit: rb?.hit ?? null,
			delta: (ra?.points ?? 0) - (rb?.points ?? 0)
		});
	}
	return rows;
}

export interface Swing {
	kind: 'match' | 'bracket' | 'bonus';
	label: string;
	why: string; // "A exact (13.2) · B result (5)"
	delta: number;
}

const KIND_WORD: Record<PickKind, string> = {
	exact: 'exact', result: 'result', miss: 'miss', none: 'no pick'
};

export function buildSwings(
	a: CompareEntryInput,
	b: CompareEntryInput,
	fixtureById: Map<string, Fixture>,
	actual: ActualAdvancement,
	rules: ScoringRules
): Swing[] {
	const swings: Swing[] = [];
	for (const r of buildMatchRows(a, b, fixtureById)) {
		if (r.delta === 0) continue;
		swings.push({
			kind: 'match',
			label: r.label,
			why: `${KIND_WORD[r.aKind]} (${r.aPoints}) · ${KIND_WORD[r.bKind]} (${r.bPoints})`,
			delta: r.delta
		});
	}
	for (const r of buildBracketRows(a, b, actual, rules)) {
		if (r.delta === 0) continue;
		swings.push({
			kind: 'bracket',
			label: `Bracket — ${r.label}`,
			why: `${r.aHits} vs ${r.bHits} correct (+${r.aPoints} / +${r.bPoints})`,
			delta: r.delta
		});
	}
	for (const r of buildBonusRows(a, b)) {
		if (r.delta === 0) continue;
		swings.push({
			kind: 'bonus',
			label: `Bonus — ${r.label}`,
			why: `${r.aAnswer ?? '—'} (+${r.aPoints}) · ${r.bAnswer ?? '—'} (+${r.bPoints})`,
			delta: r.delta
		});
	}
	swings.sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta));
	return swings;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `docker-compose exec -T frontend-dev npx vitest run src/lib/utils/compareEntries.test.ts`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils/compareEntries.ts frontend/src/lib/utils/compareEntries.test.ts
git commit -m "feat(compare): bracket/bonus rows + ranked swings in the engine"
```

---

### Task B3: Shared components — CompareSummaryStrip + SwingList

**Files:**
- Create: `frontend/src/lib/components/compare/CompareSummaryStrip.svelte`
- Create: `frontend/src/lib/components/compare/SwingList.svelte`

- [ ] **Step 1: CompareSummaryStrip**

```svelte
<script lang="ts">
	import type { CompareSummary } from '$lib/utils/compareEntries';

	export let summary: CompareSummary;
	export let aName: string;
	export let bName: string;

	const TILES: { key: keyof CompareSummary; label: string }[] = [
		{ key: 'total', label: 'Total gap' },
		{ key: 'group', label: 'Group stage' },
		{ key: 'knockout', label: 'Knockout' },
		{ key: 'bonus', label: 'Bonus' }
	];

	const fmt = (n: number) => (n > 0 ? `+${round1(n)}` : `${round1(n)}`);
	const round1 = (n: number) => Math.round(n * 10) / 10;
	const tone = (n: number) => (n > 0 ? 'text-success' : n < 0 ? 'text-error' : 'text-base-content/55');
</script>

<div>
	<p class="text-xs text-base-content/55 mb-2">{aName} vs {bName} — positive = {aName} ahead</p>
	<div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
		{#each TILES as t}
			<div class="rounded-box border border-base-300/60 bg-base-100 px-3 py-2">
				<p class="text-[10px] uppercase tracking-wider text-base-content/40">{t.label}</p>
				<p class="font-display text-xl font-extrabold {tone(summary[t.key])}">{fmt(summary[t.key])}</p>
			</div>
		{/each}
	</div>
</div>
```

- [ ] **Step 2: SwingList**

```svelte
<script lang="ts">
	import type { Swing } from '$lib/utils/compareEntries';

	export let swings: Swing[];
	export let limit = 5;
	export let expandable = true;

	let expanded = false;
	$: visible = expanded ? swings : swings.slice(0, limit);

	const fmt = (n: number) => (n > 0 ? `+${Math.round(n * 10) / 10}` : `${Math.round(n * 10) / 10}`);
</script>

<div class="space-y-1.5">
	{#each visible as s (s.kind + s.label)}
		<div class="flex items-center justify-between gap-3 rounded-btn border border-base-300/60 bg-base-100 px-3 py-1.5">
			<div class="min-w-0">
				<p class="text-sm truncate">{s.label}</p>
				<p class="text-xs text-base-content/55 truncate">{s.why}</p>
			</div>
			<span
				class="flex-none rounded-badge px-2 py-0.5 font-display text-sm font-extrabold
					{s.delta > 0 ? 'bg-success/15 text-success' : 'bg-error/15 text-error'}"
			>{fmt(s.delta)}</span>
		</div>
	{/each}
	{#if expandable && swings.length > limit}
		<button class="btn btn-ghost btn-xs text-primary" on:click={() => (expanded = !expanded)}>
			{expanded ? 'Show top 5' : `Show all ${swings.length}`}
		</button>
	{/if}
</div>
```

- [ ] **Step 3: svelte-check**

Run: `docker-compose exec -T frontend-dev npm run check`
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/compare/
git commit -m "feat(compare): shared CompareSummaryStrip + SwingList components"
```

---

### Task B4: /compare page

**Files:**
- Create: `frontend/src/routes/compare/+page.svelte`
- Modify: `frontend/src/lib/analytics/index.ts` (EventName union)

- [ ] **Step 1: Analytics events**

Add to the `EventName` union in `frontend/src/lib/analytics/index.ts` (~line 47):

```ts
	| 'compare_opened'
	| 'compare_pair_changed'
	| 'compare_tab_changed'
```

(These are already registered in `FEATURE_GROUPS` by Plan A Task A10.)

- [ ] **Step 2: Implement the page**

Create `frontend/src/routes/compare/+page.svelte`. Gate = V4 recipe; data = the EntryDrawer fan-out per entry; entry list from `getLeaderboardV4()`; actual advancement derived from fixtures like the drawer does (`seededByStage`/eliminated helpers exist in `leaderboardV4.ts` — but the engine needs `ActualAdvancement`; derive it from FINISHED/named KO fixtures):

```svelte
<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { isAuthenticated, user } from '$stores/auth';
	import { postDeadlineLive } from '$stores/phase';
	import { fixtureById, fixtures, fetchAllFixtures } from '$stores/fixtures';
	import { getLeaderboardV4, getEntryBonusReads, getScoringRules } from '$api/leaderboard';
	import { getMatchPredictions, getBracketPredictions } from '$api/predictions';
	import { getBonusQuestions } from '$api/bonus';
	import { track } from '$lib/analytics';
	import { rowDisplayName, searchRows, groupPtsOf, koPtsOf } from '$lib/utils/leaderboardV4';
	import {
		buildBonusRows, buildBracketRows, buildMatchRows, buildSummary, buildSwings,
		type ActualAdvancement, type CompareEntryInput
	} from '$lib/utils/compareEntries';
	import CompareSummaryStrip from '$lib/components/compare/CompareSummaryStrip.svelte';
	import SwingList from '$lib/components/compare/SwingList.svelte';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { MatchPredictionWithPoints, ScoringRules } from '$lib/types/results';

	// ── Gate: V4 recipe. Release = delete the is_admin clause + redeploy. ──
	const V4_COMPARE_ENABLED = true;
	$: compareOpen = V4_COMPARE_ENABLED && $user?.is_admin === true;
	$: if (browser && !$isAuthenticated) goto('/login');

	let rows: LbEntryV4[] = [];
	let rules: ScoringRules | null = null;
	let multiOwners = new Set<string>();
	let loading = true;

	let aId: string | null = null;
	let bId: string | null = null;
	let inputA: CompareEntryInput | null = null;
	let inputB: CompareEntryInput | null = null;
	let tab: 'matches' | 'bracket' | 'bonus' = 'matches';

	// KO stages where real (non-slot) teams are seeded = "reached" (lineup-based
	// advancement rule; per-side seeded check, never binary).
	$: actual = deriveActual($fixtures);
	function deriveActual(fx: typeof $fixtures): ActualAdvancement {
		const out: Record<string, Set<string>> = {};
		const real = (t: string | null | undefined) => !!t && !t.startsWith('slot:');
		for (const f of fx) {
			if (f.stage === 'group' || f.stage === 'third_place') continue;
			const set = (out[f.stage] ??= new Set<string>());
			if (real(f.home_team)) set.add(f.home_team);
			if (real(f.away_team)) set.add(f.away_team);
			if (f.stage === 'final' && f.status === 'finished' && f.score) {
				const w = f.score.outcome === '1' ? f.home_team : f.score.outcome === '2' ? f.away_team : null;
				if (w) (out['winner'] ??= new Set()).add(w);
			}
		}
		return out;
	}

	async function loadBoard() {
		loading = true;
		const [lb, sr] = await Promise.all([getLeaderboardV4(), getScoringRules(), fetchAllFixtures()]);
		rows = lb.entries;
		rules = sr;
		const counts = new Map<string, number>();
		for (const r of rows) counts.set(r.user_id, (counts.get(r.user_id) ?? 0) + 1);
		multiOwners = new Set([...counts].filter(([, n]) => n > 1).map(([id]) => id));
		// defaults: A = viewer's best entry, B = current #1 (the champion once concluded)
		const mine = rows.filter((r) => r.user_id === $user?.id);
		aId = $page.url.searchParams.get('a') ?? mine[0]?.entry_id ?? rows[0]?.entry_id ?? null;
		bId = $page.url.searchParams.get('b') ?? rows[0]?.entry_id ?? null;
		loading = false;
		track('compare_opened', { default_pair: !$page.url.searchParams.get('a') });
	}
	onMount(() => void loadBoard());

	async function loadEntry(id: string): Promise<CompareEntryInput | null> {
		const row = rows.find((r) => r.entry_id === id);
		if (!row) return null;
		const [m, br, bq, qs] = await Promise.all([
			getMatchPredictions(id) as Promise<MatchPredictionWithPoints[]>,
			getBracketPredictions(id, 'phase_1'),
			getEntryBonusReads(id),
			getBonusQuestions().catch(() => [])
		]);
		return {
			entryId: id,
			displayName: rowDisplayName(row, multiOwners),
			finalRank: row.position,
			totalPoints: row.total_points,
			groupPoints: groupPtsOf(row, row.bonus_group_points),
			knockoutPoints: koPtsOf(row, row.bonus_knockout_points),
			bonusPoints: (row.bonus_group_points ?? 0) + (row.bonus_knockout_points ?? 0),
			matches: m,
			bracket: br,
			bonusReads: bq,
			questionLabels: new Map(qs.map((q) => [q.id, q.label]))
		};
	}

	let loadedPair = '';
	$: if (browser && aId && bId && rows.length && `${aId}|${bId}` !== loadedPair) {
		loadedPair = `${aId}|${bId}`;
		void Promise.all([loadEntry(aId), loadEntry(bId)]).then(([ia, ib]) => {
			inputA = ia;
			inputB = ib;
			const url = new URL($page.url);
			url.searchParams.set('a', aId!);
			url.searchParams.set('b', bId!);
			history.replaceState({}, '', url);
		});
	}

	$: summary = inputA && inputB ? buildSummary(inputA, inputB) : null;
	$: swings = inputA && inputB && rules ? buildSwings(inputA, inputB, $fixtureById, actual, rules) : [];
	$: matchRows = inputA && inputB ? buildMatchRows(inputA, inputB, $fixtureById) : [];
	$: bracketRows = inputA && inputB && rules ? buildBracketRows(inputA, inputB, actual, rules) : [];
	$: bonusRows = inputA && inputB ? buildBonusRows(inputA, inputB) : [];

	function swap() {
		[aId, bId] = [bId, aId];
		track('compare_pair_changed', { via: 'swap' });
	}

	// picker dropdown with search (searchRows — accent-insensitive)
	let pickerOpen: 'a' | 'b' | null = null;
	let query = '';
	$: pickerRows = searchRows(rows, query);
	function choose(side: 'a' | 'b', id: string) {
		if (side === 'a') aId = id;
		else bId = id;
		pickerOpen = null;
		query = '';
		track('compare_pair_changed', { via: 'picker' });
	}
	function setTab(t: typeof tab) {
		tab = t;
		track('compare_tab_changed', { tab: t });
	}

	const fmtPts = (n: number) => Math.round(n * 10) / 10;
</script>

<svelte:head><title>Compare entries — The Predictor</title></svelte:head>

{#if $isAuthenticated && !compareOpen}
	<div class="hero min-h-[60vh]"><div class="hero-content text-center"><div class="max-w-md">
		<h1 class="text-2xl font-display font-extrabold">Head-to-head is coming</h1>
		<p class="text-base-content/60 mt-2">The compare view opens after the Final.</p>
	</div></div></div>
{/if}

{#if $isAuthenticated && compareOpen}
	<div class="container mx-auto max-w-[980px] mobile-padding pb-10 pt-3">
		<h1 class="font-display text-xl font-extrabold mb-1">Head-to-head</h1>
		<p class="text-sm text-base-content/55 mb-4">Every pick, side by side — and the exact moments the gap was made.</p>

		{#if loading}
			<div class="stadium-card no-glow p-8 text-center text-base-content/50">Loading…</div>
		{:else if inputA && inputB && summary}
			<!-- picker bar -->
			<div class="grid grid-cols-1 sm:grid-cols-[1fr_44px_1fr] gap-2 items-stretch mb-4">
				{#each [{ side: 'a', input: inputA }, { side: 'b', input: inputB }] as p}
					<div class="relative">
						<button
							class="w-full rounded-box border px-3 py-2 text-left bg-base-100
								{p.side === 'b' ? 'border-primary/50' : 'border-base-300/60'}"
							on:click={() => (pickerOpen = pickerOpen === p.side ? null : (p.side as 'a' | 'b'))}
						>
							<p class="text-[10px] uppercase tracking-wider text-base-content/40">
								Entry {p.side.toUpperCase()} {p.side === 'a' ? '· you' : ''}
							</p>
							<p class="font-bold truncate">{p.input.displayName} ▾</p>
							<p class="text-xs text-base-content/55">{p.input.totalPoints} pts · #{p.input.finalRank}</p>
						</button>
						{#if pickerOpen === p.side}
							<div class="absolute z-30 mt-1 w-full rounded-box border border-base-300 bg-base-200 p-2 shadow-card">
								<input
									class="input input-sm input-bordered w-full mb-1"
									placeholder="Search person or entry name…"
									bind:value={query}
								/>
								<div class="max-h-64 overflow-y-auto">
									{#each pickerRows.slice(0, 50) as r (r.entry_id)}
										<button
											class="flex w-full items-center justify-between gap-2 rounded-btn px-2 py-1 text-left text-sm hover:bg-base-300/40"
											on:click={() => choose(p.side as 'a' | 'b', r.entry_id)}
										>
											<span class="truncate">{rowDisplayName(r, multiOwners)}</span>
											<span class="flex-none text-xs text-base-content/50">#{r.position} · {r.total_points}</span>
										</button>
									{/each}
								</div>
							</div>
						{/if}
					</div>
					{#if p.side === 'a'}
						<button class="hidden sm:grid place-items-center rounded-box border border-base-300/60 bg-base-100 text-base-content/60" on:click={swap} aria-label="Swap entries">⇄</button>
					{/if}
				{/each}
			</div>

			<div class="stadium-card no-glow p-4 mb-4">
				<CompareSummaryStrip {summary} aName={inputA.displayName} bName={inputB.displayName} />
			</div>

			<div class="stadium-card no-glow p-4 mb-4">
				<h2 class="font-display font-extrabold mb-2">Where the gap was made</h2>
				<SwingList {swings} limit={5} />
			</div>

			<!-- tabs -->
			<div class="flex gap-1.5 mb-2">
				{#each ['matches', 'bracket', 'bonus'] as t}
					<button
						class="rounded-badge px-3.5 py-1 text-xs font-semibold border
							{tab === t ? 'bg-primary/15 border-primary/50 text-primary' : 'border-base-300/60 text-base-content/55'}"
						on:click={() => setTab(t as typeof tab)}
					>{t === 'matches' ? 'Matches' : t === 'bracket' ? 'Bracket' : 'Bonus'}</button>
				{/each}
			</div>

			<div class="stadium-card no-glow p-4 overflow-x-auto">
				{#if tab === 'matches'}
					<table class="w-full text-sm">
						<thead><tr class="text-left text-[10px] uppercase tracking-wider text-base-content/40">
							<th class="py-1 pr-2">Match</th><th class="py-1 pr-2">{inputA.displayName}</th>
							<th class="py-1 pr-2 text-right">Pts</th><th class="py-1 pr-2">{inputB.displayName}</th>
							<th class="py-1 pr-2 text-right">Pts</th><th class="py-1 text-right">Δ</th>
						</tr></thead>
						<tbody>
							{#each matchRows as r (r.fixtureId)}
								<tr class="border-t border-base-300/40">
									<td class="py-1.5 pr-2 whitespace-nowrap max-w-[180px] truncate">{r.label}</td>
									<td class="py-1.5 pr-2 {r.aKind === 'exact' ? 'text-primary font-bold' : r.aKind === 'result' ? 'text-success' : 'text-base-content/40'}">{r.aPick ?? '—'}</td>
									<td class="py-1.5 pr-2 text-right tabular-nums">{fmtPts(r.aPoints)}</td>
									<td class="py-1.5 pr-2 {r.bKind === 'exact' ? 'text-primary font-bold' : r.bKind === 'result' ? 'text-success' : 'text-base-content/40'}">{r.bPick ?? '—'}</td>
									<td class="py-1.5 pr-2 text-right tabular-nums">{fmtPts(r.bPoints)}</td>
									<td class="py-1.5 text-right tabular-nums font-bold {r.delta > 0 ? 'text-success' : r.delta < 0 ? 'text-error' : 'text-base-content/40'}">{r.delta > 0 ? '+' : ''}{fmtPts(r.delta)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else if tab === 'bracket'}
					<table class="w-full text-sm">
						<thead><tr class="text-left text-[10px] uppercase tracking-wider text-base-content/40">
							<th class="py-1 pr-2">Stage</th><th class="py-1 pr-2 text-right">{inputA.displayName}</th>
							<th class="py-1 pr-2 text-right">{inputB.displayName}</th><th class="py-1 text-right">Δ</th>
						</tr></thead>
						<tbody>
							{#each bracketRows as r (r.stage)}
								<tr class="border-t border-base-300/40">
									<td class="py-1.5 pr-2">{r.label}</td>
									<td class="py-1.5 pr-2 text-right tabular-nums">{r.aHits}/{r.aTeams.length || '—'} · +{r.aPoints}</td>
									<td class="py-1.5 pr-2 text-right tabular-nums">{r.bHits}/{r.bTeams.length || '—'} · +{r.bPoints}</td>
									<td class="py-1.5 text-right tabular-nums font-bold {r.delta > 0 ? 'text-success' : r.delta < 0 ? 'text-error' : 'text-base-content/40'}">{r.delta > 0 ? '+' : ''}{r.delta}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else}
					<table class="w-full text-sm">
						<thead><tr class="text-left text-[10px] uppercase tracking-wider text-base-content/40">
							<th class="py-1 pr-2">Question</th><th class="py-1 pr-2">{inputA.displayName}</th>
							<th class="py-1 pr-2">{inputB.displayName}</th><th class="py-1 text-right">Δ</th>
						</tr></thead>
						<tbody>
							{#each bonusRows as r (r.questionId)}
								<tr class="border-t border-base-300/40">
									<td class="py-1.5 pr-2">{r.label}</td>
									<td class="py-1.5 pr-2 {r.aHit ? 'text-success font-semibold' : 'text-base-content/50'}">{r.aAnswer ?? '—'} {r.aHit ? '✓' : r.aHit === false ? '✗' : ''}</td>
									<td class="py-1.5 pr-2 {r.bHit ? 'text-success font-semibold' : 'text-base-content/50'}">{r.bAnswer ?? '—'} {r.bHit ? '✓' : r.bHit === false ? '✗' : ''}</td>
									<td class="py-1.5 text-right tabular-nums font-bold {r.delta > 0 ? 'text-success' : r.delta < 0 ? 'text-error' : 'text-base-content/40'}">{r.delta > 0 ? '+' : ''}{r.delta}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</div>
		{/if}
	</div>
{/if}
```

(`groupPtsOf`/`koPtsOf` signatures: verify against `leaderboardV4.ts:215-223` and pass arguments exactly as the leaderboard page does. If `$user?.id` doesn't exist on the auth store's user, use whatever field the leaderboard page uses for "own entries".)

- [ ] **Step 3: svelte-check + vitest**

Run: `docker-compose exec -T frontend-dev npm run check` → 0 errors
Run: `docker-compose exec -T frontend-dev npx vitest run` → all pass

- [ ] **Step 4: Overlay smoke test in the browser**

Overlay onto the main worktree, `docker compose restart frontend-dev` (live-server rule), sign in as admin, open `http://localhost:5173/compare`, verify: pickers search + swap, summary strip, swings, three tabs, `?a=&b=` round-trips.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/compare/+page.svelte frontend/src/lib/analytics/index.ts
git commit -m "feat(compare): /compare page — searchable pickers, summary, swings, three tabs (admin-gated)"
```

---

### Task B5: Release checklist (do NOT execute until the admin says so)

Documented for the release moment — not part of the build:

1. Delete the `$user?.is_admin === true` clause: `$: compareOpen = V4_COMPARE_ENABLED;` (kill switch stays).
2. Add the nav item in `frontend/src/routes/+layout.svelte` `navItems` (~line 102):
   ```ts
   { href: '/compare', label: 'Compare', icon: 'M8 7h12m0 0l-4-4m4 4l-4 4M16 17H4m0 0l4 4m-4-4l4-4' },
   ```
3. Version bump + changelog entry per the release process; commit `chore(version)`.
4. Push — **deploy only on the admin's explicit ship signal.**
